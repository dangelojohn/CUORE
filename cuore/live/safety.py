"""The gates. Every rule that decides whether a command reaches the adapter.

Three independent checks, all pure functions of their inputs:

* :func:`validate_command` -- one command per call; CR, LF and the STN batch
  separator are rejected so nothing can smuggle a second command past the
  classifier.
* :func:`classify_command` -- read / vehicle_write / adapter_state / blocked,
  with allowlists for AT and ST reads rather than a deny-list.
* :func:`assert_read_only_uds` and :func:`assert_transmit_allowed` -- the HTTP
  layer's guarantee that it has no write path, and the cable protocol that
  keeps a 500 kbps preset off a 125 kbps bus.
"""

from __future__ import annotations

import re

from .errors import BadCommand, Refused

#: UDS services that change vehicle state, with what they actually do.
WRITE_SERVICES: dict[str, str] = {
    "10": "UDS DiagnosticSessionControl - changes the module's session; an extended "
          "session suppresses normal broadcasts and can itself trigger network DTCs",
    "11": "UDS ECUReset - resets the module",
    "14": "UDS ClearDiagnosticInformation - erases DTCs and readiness monitors",
    "27": "UDS SecurityAccess - repeated failures can lock the module out",
    "28": "UDS CommunicationControl - silences or alters bus traffic",
    "2C": "UDS DynamicallyDefineDataIdentifier - writes a definition into the module",
    "2E": "UDS WriteDataByIdentifier - writes configuration to a module",
    "2F": "UDS InputOutputControl - physically actuates hardware",
    "31": "UDS RoutineControl - runs adaptations and service routines",
    "34": "UDS RequestDownload - reflashing, can brick a module",
    "35": "UDS RequestUpload - reflashing related",
    "36": "UDS TransferData - reflashing, can brick a module",
    "37": "UDS RequestTransferExit - reflashing related",
    "3D": "UDS WriteMemoryByAddress - writes module memory",
    "85": "UDS ControlDTCSetting - suppresses DTC logging",
    "87": "UDS LinkControl - changes bus timing",
}

#: AT commands that only read adapter state. Anything else AT-prefixed
#: reconfigures the adapter.
AT_READ_ONLY = frozenset({"ATI", "AT@1", "AT@2", "AT@3", "ATRV", "ATDP", "ATDPN",
                          "ATPPS", "ATIGN", "ATRD", "ATCS"})

#: STN commands that only read adapter state.
ST_READ_ONLY = frozenset({"STI", "STIX", "STDI", "STDIX", "STMFR", "STSN", "STPR",
                          "STPRS", "STPBRR", "STSLCS", "STCTRR", "STDICPO", "STDICES",
                          "STDITPO", "STVR", "STVRX", "STPTOR", "STCSWMR"})

#: Monitor modes never return to the prompt; they run only through capture.py.
MONITOR_COMMANDS = ("ATMA", "ATMR", "ATMT")
_ST_MONITOR_RE = re.compile(r"^STMA?\d*$")

HEX_DIGITS = frozenset("0123456789ABCDEF")


def is_adapter_only(cmd: str) -> bool:
    """True for an AT/ST command that only reads the adapter itself (identity,
    battery voltage, current protocol, ...) and never puts a frame on the
    vehicle bus -- ``ATI``, ``ATRV``, ``STPRS``, ``ATDPN``, ``STI``, ``STDI``
    and the rest of :data:`AT_READ_ONLY`/:data:`ST_READ_ONLY`.

    Used to keep these commands off the bus-silence guard: refusing ``ATRV``
    because CAN-C looks silent is wrong on its face, since ``ATRV`` never
    touches CAN-C at all.
    """
    compact = cmd.strip().upper().replace(" ", "")
    return compact in AT_READ_ONLY or compact in ST_READ_ONLY


def validate_command(cmd: str) -> str:
    """One command, one line. Raises :class:`BadCommand` otherwise."""
    if not cmd or not cmd.strip():
        raise BadCommand("empty command")
    if "\r" in cmd or "\n" in cmd:
        raise BadCommand("command contains a line terminator; one command per call")
    if "|" in cmd:
        raise BadCommand("command contains '|', the STN batch separator; one command per call")
    if any(ord(c) > 126 or ord(c) < 32 for c in cmd):
        raise BadCommand("command contains non-printable or non-ASCII characters")
    return cmd.strip()


#: Service codes that configure or code the vehicle -- refused on EVERY
#: module, unconditionally, with no override flag and independent of
#: :data:`ACTUATION_BLOCKED_MODULES`. 2026-10-14 rule: a module-name
#: blocklist is not enough, because a module nobody thought to put on it can
#: still carry safety-relevant CONFIGURATION. The case that forced this: the
#: BCM's own "CAN Setup" PROXI byte 156 (paddle-shift NA/Euro characteristic
#: -- see docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md). BCM is not,
#: and should never need to be, in ACTUATION_BLOCKED_MODULES -- it is not an
#: actuator-test target -- yet a 0x2E WriteDataByIdentifier to it is exactly
#: the class of write that belongs in MultiEcuScan/wiTECH, never here. So
#: this gate is keyed on the SERVICE (the operation class), checked before
#: any module lookup, and applies to every module whether or not anyone ever
#: named it. Reads (0x22 ReadDataByIdentifier, 0x19 ReadDTCInformation, 0x3E
#: TesterPresent, legislated OBD Modes 01-0A) are never affected -- they are
#: not in this table at all. A catalogued actuator-test RoutineControl
#: (0x31) still runs through its own module-and-consent gate in
#: cuore.live.actuate (:func:`assert_actuation_allowed` /
#: :func:`assert_actuation_module_allowed`) -- that path never reaches
#: :func:`classify_command` or :func:`assert_read_only_uds` at all, so
#: blocking 0x31 here never touches it.
CONFIGURATION_WRITE_SERVICES: frozenset[int] = frozenset({0x27, 0x2E, 0x31, 0x34, 0x36, 0x37, 0x85})


def assert_not_configuration_write(service: int, module_code: str = "") -> None:
    """Raise :class:`Refused` for any service in
    :data:`CONFIGURATION_WRITE_SERVICES`, regardless of ``module_code`` --
    the point is that this check never consults a module list at all, so a
    module nobody blocklisted by name is refused exactly the same as one
    that is (see the rule documented on that constant). ``module_code`` is
    accepted only to name the target in the refusal message; passing "" (the
    default, e.g. from :func:`classify_command`, which has no module in
    scope yet) still refuses every module equally once the request actually
    reaches one.
    """
    if service in CONFIGURATION_WRITE_SERVICES:
        why = WRITE_SERVICES.get(format(service, "02X"), "configuration/coding write")
        where = f" to {module_code}" if module_code else ""
        raise Refused(
            f"UDS service 0x{service:02X}{where} is a configuration/coding write and is "
            f"refused on every module, with no override and regardless of "
            f"ACTUATION_BLOCKED_MODULES (2026-10-14 rule: a module-name blocklist alone missed "
            f"the BCM 'CAN Setup' PROXI byte-156 case -- {why}); use MultiEcuScan or wiTECH for "
            f"this.")


def classify_command(cmd: str) -> tuple[str, str]:
    """Return ``(kind, reason)``; kind is read, vehicle_write, adapter_state or blocked."""
    compact = cmd.strip().upper().replace(" ", "")
    if not compact:
        return "blocked", "empty command"

    if compact.startswith("AT"):
        if compact.startswith(MONITOR_COMMANDS):
            return "blocked", f"{compact[:4]} is a monitor mode; it never returns to the prompt"
        if compact.startswith("ATSH"):
            return "vehicle_write", ("ATSH redirects requests to another module, which can "
                                     "turn a following command into a write to an unintended ECU")
        if compact in AT_READ_ONLY:
            return "read", ""
        return "adapter_state", (f"{compact} changes adapter configuration (protocol, "
                                 f"headers, filters, timing, baud or persistent settings)")

    if compact.startswith("ST"):
        if _ST_MONITOR_RE.match(compact):
            return "blocked", "STM/STMA monitor modes never return to the prompt"
        if compact.startswith("STPX"):
            return "vehicle_write", ("STPX transmits an arbitrary CAN frame with an arbitrary "
                                     "ID and payload; that is a write to the bus")
        if compact in ST_READ_ONLY:
            return "read", ""
        return "adapter_state", (f"{compact} changes adapter configuration (protocol, "
                                 f"filters, segmentation, periodic messages, baud or "
                                 f"power settings)")

    if any(c not in HEX_DIGITS for c in compact):
        return "blocked", f"{cmd!r} is neither an AT/ST command nor hex"

    if compact in ("04", "0400"):
        return "vehicle_write", ("OBD-II Mode 04 clears DTCs and resets readiness monitors; "
                                 "use the clear tool, which captures evidence first")
    service = compact[:2]
    try:
        assert_not_configuration_write(int(service, 16))
    except Refused as e:
        return "blocked", str(e)
    if service in WRITE_SERVICES:
        return "vehicle_write", WRITE_SERVICES[service]
    return "read", ""


#: The only UDS services the live layer may emit, and the sub-functions
#: allowed where it matters. There is no code path to anything else.
READ_ONLY_UDS: dict[int, frozenset[int] | None] = {
    0x10: frozenset({0x01}),   # default session only
    0x19: None,                # ReadDTCInformation, any sub-function
    0x22: None,                # ReadDataByIdentifier
    0x3E: None,                # TesterPresent
}


def assert_read_only_uds(service: int, payload: bytes = b"") -> None:
    """Raise :class:`Refused` unless the service is on the read-only allowlist."""
    assert_not_configuration_write(service)
    allowed = READ_ONLY_UDS.get(service, "absent")
    if allowed == "absent":
        why = WRITE_SERVICES.get(format(service, "02X"), "not on the read-only allowlist")
        raise Refused(f"UDS service 0x{service:02X} is not permitted on the live link: {why}")
    if allowed is not None:
        sub = payload[0] if payload else None
        if sub is None or (sub & 0x7F) not in allowed:
            raise Refused(f"UDS service 0x{service:02X} sub-function "
                          f"{'none' if sub is None else format(sub, '02X')} is not permitted; "
                          f"allowed: {sorted(format(s, '02X') for s in allowed)}")


def assert_transmit_allowed(*, bus_key: str, bus_cable_ok: bool, verified: bool,
                            needs_confirmation: bool, confirmed: bool) -> None:
    """The cable protocol, enforced before any request leaves the adapter.

    ``bus_cable_ok`` is whether the declared cable reaches this bus at all;
    ``verified`` is whether a passive listen has seen traffic on it under the
    current declaration; ``needs_confirmation`` is the per-bus flag (CAN-CH)
    and ``confirmed`` the per-session consent.
    """
    if not bus_cable_ok:
        raise Refused(f"bus {bus_key} is not reachable with the declared cable; "
                      f"declare the right cable first (set_cable / POST /api/live/cable)")
    if not verified:
        raise Refused(f"bus {bus_key} has not been verified under the current cable; "
                      f"run a passive listen first (verify_bus / POST /api/live/verify)")
    if needs_confirmation and not confirmed:
        raise Refused(f"bus {bus_key} carries brakes, airbag and steering; transmitting on it "
                      f"requires confirm=True on this call")


#: UDS services/sub-functions an actuator-test *replay* may send. Distinct
#: from READ_ONLY_UDS: this adds 0x2F (InputOutputControlByIdentifier) and
#: 0x31 (RoutineControl) -- what an actuator test actually is -- and allows
#: 0x10 sub 0x03 (the extended session most actuator tests run in) alongside
#: the default session. Never anything else: no 0x27, no 0x2E, no reflash or
#: reset service. :mod:`actuate` applies this same allowlist at *learning*
#: time (:func:`actuate.extract_procedure`) to decide whether a captured
#: procedure is replayable at all; this function is the belt on the wire.
ACTUATION_UDS: dict[int, frozenset[int] | None] = {
    0x10: frozenset({0x01, 0x03}),   # default or extended-diagnostic session only
    0x19: None,                      # ReadDTCInformation
    0x22: None,                      # ReadDataByIdentifier
    0x2F: None,                      # InputOutputControlByIdentifier
    0x31: None,                      # RoutineControl
    0x3E: None,                      # TesterPresent
}

#: Modules an actuator-test replay refuses outright, regardless of consent
#: or confirm: brakes, airbag, steering, torque vectoring, the steering
#: lock, and (via the bus check below) anything else on CAN-CH.
ACTUATION_BLOCKED_MODULES: frozenset[str] = frozenset({
    "ABS", "EPS", "ORC", "HALF", "DASM", "ESL", "TVM",
    # Driveline and security: shift-by-wire / park lock (TCM, ESM), the Q4
    # transfer case (DTCM) and the immobiliser/keyless hub (RFHUB). Actuating
    # any of these on a parked car can release park or disable starting.
    "TCM", "ESM", "DTCM", "RFHUB",
})


def assert_actuation_allowed(service: int, payload: bytes = b"") -> None:
    """Raise :class:`Refused` unless the service is on the actuation allowlist.

    This is the gate every request an actuator replay sends must pass
    immediately before it reaches the adapter -- :meth:`Session.uds` sends
    any service, so this is the only thing standing between a learned
    procedure and the wire. It never loosens :data:`READ_ONLY_UDS`: a
    0x2F/0x31 request is still refused on the read-only path in :mod:`uds`.
    """
    allowed = ACTUATION_UDS.get(service, "absent")
    if allowed == "absent":
        why = WRITE_SERVICES.get(format(service, "02X"), "not on the actuation allowlist")
        raise Refused(f"UDS service 0x{service:02X} is not permitted during actuator replay: {why}")
    if allowed is not None:
        sub = payload[0] if payload else None
        if sub is None or (sub & 0x7F) not in allowed:
            raise Refused(f"UDS service 0x{service:02X} sub-function "
                          f"{'none' if sub is None else format(sub, '02X')} is not permitted "
                          f"during actuator replay; allowed: "
                          f"{sorted(format(s, '02X') for s in allowed)}")


def assert_actuation_module_allowed(module_code: str, bus_key: str) -> None:
    """Raise :class:`Refused` for a module an actuator replay must never touch.

    Checked before any traffic, independent of consent or confirm: this is
    not a confirmable risk, it is a refusal.
    """
    code = (module_code or "").upper()
    if code in ACTUATION_BLOCKED_MODULES or bus_key == "can_ch":
        raise Refused(
            f"actuator tests are refused on {code}: safety-critical (brakes, airbag, steering, "
            f"torque vectoring, driveline/park lock, immobiliser, or the CAN-CH bus); use "
            f"MultiEcuScan or wiTECH for this test, "
            f"never a replay here")


#: Modules a raw vehicle write (send_raw) is refused on, whatever the consent:
#: everything an actuator replay refuses (brakes, airbag/ORC, steering, torque
#: vectoring, driveline/park lock, immobiliser/keyless hub) plus the instrument
#: cluster (odometer / mileage storage). Reflash services (34/35/36/37) are
#: refused for every module by :func:`classify_command`. CAN-CH is refused too.
RAW_WRITE_BLOCKED_MODULES: frozenset[str] = ACTUATION_BLOCKED_MODULES | frozenset({"IPC"})


def raw_write_phrase(cmd: str, module_code: str) -> str:
    """The exact consent phrase a raw vehicle write needs: ``SEND RAW <SERVICE> TO <MODULE>``
    (service = the command's first byte as two hex digits, e.g. ``SEND RAW 2F TO ECM``)."""
    compact = cmd.strip().upper().replace(" ", "")
    return f"SEND RAW {compact[:2]} TO {(module_code or '').strip().upper()}"


def assert_raw_write_allowed(cmd: str, module_code: str, consent: str,
                             bus_key: str = "") -> None:
    """Raise :class:`Refused` unless a raw vehicle write may be sent to ``module_code``.

    Order: a write with no nameable module (ATSH, STPX arbitrary frames, Mode 04)
    is refused outright -- the module blocklist could not be applied to it; then
    the module blocklist / CAN-CH; then the typed consent phrase.
    """
    compact = cmd.strip().upper().replace(" ", "")
    if compact in ("04", "0400"):
        raise Refused("Mode 04 clears emissions codes: use the clear_dtcs tool (it captures "
                      "evidence first and needs its own consent phrase)")
    if compact.startswith(("AT", "ST")):
        raise Refused(f"{compact[:4]} would send an arbitrary frame or redirect later requests, "
                      f"so the module blocklist cannot be applied to it; send_raw refuses it. "
                      f"Send the UDS request itself with module= set")
    code = (module_code or "").strip().upper()
    if not code:
        raise Refused("a vehicle write through send_raw must name its target module (module=); "
                      f"consent phrase for it will be 'SEND RAW {compact[:2]} TO <MODULE>'")
    if code in RAW_WRITE_BLOCKED_MODULES or bus_key == "can_ch":
        raise Refused(f"raw writes are refused on {code}: safety-critical (brakes, airbag/ORC, "
                      f"steering, driveline/park lock, immobiliser, odometer/cluster) or on "
                      f"CAN-CH; use MultiEcuScan or wiTECH, never a raw send here")
    want = raw_write_phrase(cmd, code)
    if (consent or "").strip().upper() != want:
        raise Refused(f"this command writes to {code}; type the consent phrase exactly: {want!r}")


__all__ = [
    "WRITE_SERVICES", "AT_READ_ONLY", "ST_READ_ONLY", "MONITOR_COMMANDS", "READ_ONLY_UDS",
    "ACTUATION_UDS", "ACTUATION_BLOCKED_MODULES", "CONFIGURATION_WRITE_SERVICES",
    "validate_command", "classify_command", "is_adapter_only", "assert_read_only_uds",
    "assert_transmit_allowed", "assert_actuation_allowed", "assert_actuation_module_allowed",
    "assert_not_configuration_write",
    "RAW_WRITE_BLOCKED_MODULES", "raw_write_phrase", "assert_raw_write_allowed",
]
