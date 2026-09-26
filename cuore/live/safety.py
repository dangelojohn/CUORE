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


__all__ = [
    "WRITE_SERVICES", "AT_READ_ONLY", "ST_READ_ONLY", "MONITOR_COMMANDS", "READ_ONLY_UDS",
    "ACTUATION_UDS", "ACTUATION_BLOCKED_MODULES",
    "validate_command", "classify_command", "assert_read_only_uds", "assert_transmit_allowed",
    "assert_actuation_allowed", "assert_actuation_module_allowed",
]
