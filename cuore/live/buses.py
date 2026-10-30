"""Pure-data description of the Giorgio-platform CAN buses on this car.

Source of truth: docs/reference/GIORGIO_MODULE_MAP.md (Table B, the
structural finding, and the hazard entries). This module encodes exactly
what that document says. Where the document says "unknown", this module
uses ``None``. Confidences are never upgraded past what the document
states.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass

#: "witech_splitter" is not a bypass cable: it declares an OBD Y-splitter that puts this adapter on
#: the same CAN-C pins as the manufacturer's wiTECH pod. It reaches CAN-C only, at CAN-C's own
#: 500k, and is LISTEN-ONLY (transport refuses any non-passive session under it).
CABLES = ("none", "blue_a5", "grey_a6", "witech_splitter")


@dataclass(frozen=True)
class Route:
    cable: str  # one of CABLES
    stn_protocol: str  # STN "STP" preset number as a string, e.g. "34", "54"
    bitrate_override: int | None  # e.g. 125000 when the HS preset must be re-rated after a re-pinning cable
    status: str  # "confirmed" | "untested" | "unreachable"
    note: str


@dataclass(frozen=True)
class Bus:
    key: str  # "can_c" | "can_ihs" | "can_ch"
    name: str
    pins: tuple[int, int]
    bitrate: int  # the bus's own bitrate
    bitrate_confidence: str  # "confirmed" | "inferred"
    id_bits: int  # 29
    routes: tuple[Route, ...]  # every way to reach it, in preference order
    transmit_needs_confirmation: bool  # True for can_ch
    modules_seen: tuple[str, ...]  # MES codes actually observed on this bus on this car
    notes: str  # safety text from Table B
    nm_ids_seen: tuple[str, ...] = ()  # keep-alive / network-management ids heard on the 29-bit route


CAN_C = Bus(
    key="can_c",
    name="CAN-C (diagnostic / powertrain)",
    pins=(6, 14),
    bitrate=500000,
    bitrate_confidence="confirmed",
    id_bits=29,
    routes=(
        Route(
            "none",
            "34",
            None,
            "confirmed",
            "STP 34 (or STP 33 for the legislated 11-bit 7E0/7E8 pair); STPBRR expected 500000. "
            "On 2018+ Giorgio cars (Security Gateway Module) CAN-C is gateway-isolated: there is "
            "NO broadcast traffic on it at all, in either width -- a passive listen on STP 34 "
            "reading 0 frames does not mean the bus is dead. See the STP 33 route's note; "
            "ops.verify_bus() falls back to an active Mode 01 PID 00 probe for exactly this case.",
        ),
        Route(
            "none",
            "33",
            None,
            "untested",
            "11-bit legislated pair 7E0/7E8 at 500k. Giorgio broadcast traffic on CAN-C is "
            "largely 11-bit, so a monitor opened 29-bit-only can report zero frames on a "
            "perfectly healthy bus. Listened for after STP 34, never preferred for UDS. On "
            "2018+ cars behind the Security Gateway Module this route still carries no "
            "broadcast traffic either -- the gateway only answers a request, it never emits "
            "anything unprompted -- so a passive listen here is also 0 frames on a healthy "
            "car; verification instead sends one legislated Mode 01 PID 00 request (7DF) and "
            "accepts any 7E8-7EF reply as proof the bus is alive.",
        ),
        Route(
            "witech_splitter",
            "34",
            None,
            "confirmed",
            "OBD Y-splitter shared with the wiTECH pod: same CAN-C pins, 500000 bps (no override). "
            "Listen-only: transport refuses any transmitting session while this is declared.",
        ),
    ),
    transmit_needs_confirmation=False,
    modules_seen=("ECM", "IPC", "TCM", "DTCM", "ESM", "BCM", "RFHUB", "DASM"),
    notes=(
        "Live powertrain bus. Writes gated. Whole-vehicle serial UDS sweeps "
        "manufacture -87/-2F bystander codes (SCAN_2609041953 shows exactly "
        "that: DTCM U0100-87, BCM U171x-2F, EPS U1960-83). Pull DTC EX before "
        "clearing."
    ),
)

CAN_IHS = Bus(
    key="can_ihs",
    name="CAN-IHS (body / comfort / infotainment)",
    pins=(3, 11),
    bitrate=125000,
    bitrate_confidence="confirmed",
    id_bits=29,
    routes=(
        Route(
            "blue_a5",
            "34",
            125000,
            "untested",
            "HS transceiver re-pinned onto 3/11 by the cable; never use STP 53/54 with the cable fitted. "
            "INTERLOCK (2026-10-23): nothing is transmitted unless the passive listen in the same call "
            "heard at least 5 frames at 125 kbit/s in the last 10 s. Silence is never a reason to "
            "send (the old 'silence -> functional 3E 00' fallback was removed: after the cable was "
            "pulled it put two 3E 00 frames at 125k onto CAN-C, CAN ERROR).",
        ),
        Route(
            "blue_a5",
            "33",
            125000,
            "confirmed",
            "CONFIRMED on the car 2026-10-15 (awake): 317 frames/2 s over 54 ids (3E2, 3E4, "
            "3E6, 3E8, 2F0, 3DC, 3DE, 3E0, ...). 11-bit broadcast listen route at 125k (STP 33 + STPBR 125000 + ATCAF0 + STMA), "
            "mirroring the CAN-CH finding of 2026-10-14 that Giorgio periodic traffic is "
            "11-bit and invisible to a 29-bit filtered monitor. Listen only; UDS stays on "
            "the 29-bit route above. Never any rate but 125k.",
        ),
        Route(
            "none",
            "54",
            None,
            "untested",
            "MS-CAN transceiver on adapter pins 3/11; verify STPRS changes and STPBRR reads 125000; auto-switch firmware may override",
        ),
    ),
    transmit_needs_confirmation=False,
    modules_seen=(),
    notes=(
        "Do not mix routes: with the A5 fitted, adapter pins 3/11 map to "
        "nothing defined, so use the HS preset plus STPBR, never STP "
        "53/54. Opening a 500k preset on a 125k bus emits error frames; "
        "set STCMM 0 before STPO when the rate is in doubt. Awake signature (car, "
        "2026-10-15, blue A5, adapter switch HS): STP 33 + STPBR 125000 + ATCAF0 + STMA = "
        "317 frames/2 s over 54 11-bit ids; the 29-bit STP 34 route hears only ~9/s keep-alive "
        "ids. 29-bit 22 F190 discovery (1.5 s wait) to 45,30,24,03,0A,33,34,67,00,68,6F,01,02 "
        "got no reply; functional 3E 00 on 18DB33F1 got NO DATA: no IHS module address is "
        "confirmed. HYPOTHESIS (untested): the low byte of a 1E34xxxx keep-alive id may be "
        "the node's diagnostic address (AUTOSAR CAN NM style)."
    ),
    nm_ids_seen=(
        "1E340000", "1E340003", "1E34000A", "1E340024", "1E340030",
        "1E340033", "1E340034", "1E340045", "1E340067",
    ),
)

CAN_CH = Bus(
    key="can_ch",
    name="CAN-CH (chassis / ADAS / safety)",
    pins=(12, 13),
    bitrate=500000,
    bitrate_confidence="confirmed",
    id_bits=29,
    routes=(
        Route(
            "grey_a6",
            "34",
            None,
            "confirmed",
            "29-bit UDS route at 500k (STPBRR read 500000 on the car, 2026-10-14). "
            "NEVER open CAN-CH at any other rate: three ~2 s receive-only windows at "
            "250k/125k lit the AIRBAG lamp with a chime on the car (2026-10-14 23:58). "
            "A silent 29-bit listen is normal here; the STP 33 route below hears the bus.",
        ),
        Route(
            "grey_a6",
            "33",
            None,
            "confirmed",
            "11-bit broadcast listen route: STP 33 + ATCAF0 + STMA heard 818 frames in 2 s "
            "over 29 IDs (0DE, 0EE, 0FC, 106, 10E, 116, 11C, 122, ...) at 500k on the car, "
            "2026-10-14. Listen only; UDS stays on the 29-bit route above.",
        ),
    ),
    transmit_needs_confirmation=True,
    modules_seen=("ABS", "EPS", "ORC", "AFLS", "PAM", "HALF"),
    notes=(
        "Never transmit on CAN-CH without explicit human confirmation: "
        "brakes, airbag squibs and steering assist live here. Listen first "
        "with STCMM 0 + STMA (ATCAF0). FEPS hazard: the vLinker FS is a Ford tool "
        "whose 18V FEPS output is OBD pin 13, which on Giorgio is "
        "CAN-CH(-). Never issue any FEPS or programming-voltage command on "
        "this vehicle; whether the FS can be commanded to FEPS over serial "
        "is UNVERIFIED, treat as live. Awake vs asleep (car, 2026-10-15): the 29-bit "
        "STP 34 route hears only ~12 frames/s of 1E34xxxx/1E36xxxx keep-alive ids "
        "(1E340000, 1E36001E, 1E360018, 1E36001A, 1E360002, 1E360006, 1E36001D) in BOTH "
        "states, so it cannot tell them apart; awake = STP 33 hears ~400 frames/s over "
        "~30 11-bit ids (0DE, 0EE, 0FC, 106, 10E, 116, 11C, 122, ...), asleep (~25 min "
        "after ignition-on, engine off) = STP 33 silent and the ABS stops answering UDS. "
        "Keep-alive ids seen 2026-10-15 on the 29-bit route (grey A6, 500k): 1E340000, "
        "1E340006, 1E360002, 1E360006, 1E360018, 1E36001A, 1E36001D, 1E36001E. HYPOTHESIS "
        "(untested): the low byte of a 1E34xxxx keep-alive id may be the node's diagnostic "
        "address (AUTOSAR CAN NM style)."
    ),
    nm_ids_seen=(
        "1E340000", "1E340006", "1E360002", "1E360006",
        "1E360018", "1E36001A", "1E36001D", "1E36001E",
    ),
)

BUSES: dict[str, Bus] = {
    "can_c": CAN_C,
    "can_ihs": CAN_IHS,
    "can_ch": CAN_CH,
}

PIN_1_9_WARNING = (
    "do not use modified interfaces with a short between pins 1 and 9 on "
    "Giulia or Stelvio; it drops the bus. Continuity-check any cable "
    "before fitting."
)

_HEADER_BITS_BY_PROTOCOL: dict[str, int] = {
    # ISO 15765-4 CAN STN "STP" preset numbers.
    "31": 11,
    "33": 11,
    "35": 11,
    "51": 11,
    "53": 11,
    "32": 29,
    "34": 29,
    "36": 29,
    "52": 29,
    "54": 29,
    # ELM-style short forms.
    "6": 11,
    "8": 11,
    "7": 29,
    "9": 29,
}


def route_for(bus: Bus, cable: str) -> Route | None:
    """The route on ``bus`` that works with ``cable``, or None."""
    for route in bus.routes:
        if route.cable == cable:
            return route
    return None


def routes_for(bus: Bus, cable: str) -> list[Route]:
    """Every route on ``bus`` that works with ``cable``, in preference order.

    A bus can be reachable under more than one adapter protocol. ``route_for``
    returns the preferred one and is what normal operations use; this returns
    the full candidate list, so a passive listen can try them all before
    concluding a bus is silent.
    """
    return [route for route in bus.routes if route.cable == cable]


def adapter_switch(bus_key: str, cable: str) -> str:
    """Which way the vLinker FS adapter's HS/MS switch must sit: "HS" or "MS".

    Decided by the route (its STN protocol), never by the bus bitrate. Both
    MES bypass cables (blue A5, grey A6) bridge the car's bus pins onto the
    adapter's normal HS pins (6/14), so with either cable fitted the switch
    stays on HS even for the 125k CAN-IHS bus. MS is only for the cable-less
    MS-CAN route (STP 53/54 on adapter pins 3/11). Raises ValueError when
    ``bus_key`` has no route for ``cable``.
    """
    route = route_for(BUSES[bus_key], cable)
    if route is None:
        raise ValueError(f"no route for bus {bus_key!r} with cable {cable!r}")
    return "MS" if route.stn_protocol in ("51", "52", "53", "54") else "HS"


def buses_for_cable(cable: str) -> list[Bus]:
    """Buses reachable with ``cable``, in preference order."""
    result = []
    for bus in BUSES.values():
        if route_for(bus, cable) is not None:
            result.append(bus)
    return result


def header_bits_for_protocol(stn_protocol: str) -> int:
    """11 or 29, per the STN STP preset (or ELM short form)."""
    return _HEADER_BITS_BY_PROTOCOL[stn_protocol]


# --- Sibling-platform bus data (added 2026-10-14) ---------------------------
#
# Additive only: BUSES/CAN_C/CAN_IHS/CAN_CH above (this car's own
# Giorgio-platform buses) are unchanged by anything below.
#
# See docs/research/SIBLING_PLATFORMS_BUS_TOPOLOGY_2026-10-14.md and
# mes.platform.BUS_TOPOLOGY for the full sourced research pass into the
# Grecale's, Levante's and Purosangue's own OBD bus topology. This dict is
# meant to carry over only the facts that pass graded CONFIRMED or
# CORROBORATED (the same bar PLATFORMS uses) -- which, for all three cars,
# turned out to be none at the pin/bitrate/module level: every concrete
# bus fact came back UNKNOWN; only a generic, non-car-specific regulatory
# fact and two unrelated platform/chassis-code facts cleared CORROBORATED.
# It is therefore empty BY DESIGN, not an oversight -- adding a ``Bus``
# here that is not at least CORROBORATED would invent pin/bitrate data for
# a car this bench has never been connected to, which the CUORE core
# directive ("diagnose on evidence") forbids.
#
# NEVER selected for a Giorgio VIN: this car's own live-bus selection
# (``cuore.live.ops`` and friends) reads ``BUSES`` only and never consults
# this dict. Routing to a sibling platform at all happens one layer up,
# via ``mes.platform.marque_for_vin()``/``model_for_vin()`` -- which, for a
# Maserati SUV WMI (``ZN6``/``ZN7``), already returns ``UNKNOWN`` rather
# than guessing Levante vs. Grecale (see that module's docstring), so a
# Giorgio VIN can never land here even by mistake.
SIBLING_PLATFORM_BUSES: dict[str, dict[str, Bus]] = {}


def sibling_platform_bus(model: str, bus_key: str) -> Bus | None:
    """A ``Bus`` record for a sibling platform (``"grecale"``,
    ``"levante"``, ``"purosangue"``), if this project has ever recorded one
    at CORROBORATED-or-better confidence. Always returns ``None`` today --
    see :data:`SIBLING_PLATFORM_BUSES`'s docstring for why -- and is never
    consulted by this car's own live-bus selection, which is keyed off
    :data:`BUSES` only.
    """
    return SIBLING_PLATFORM_BUSES.get((model or "").strip().lower(), {}).get(bus_key)
