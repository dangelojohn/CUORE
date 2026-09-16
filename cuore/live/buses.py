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

CABLES = ("none", "blue_a5", "grey_a6")


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
            "STP 34 (or STP 33 for the legislated 11-bit 7E0/7E8 pair); STPBRR expected 500000.",
        ),
        Route(
            "none",
            "33",
            None,
            "untested",
            "11-bit legislated pair 7E0/7E8 at 500k. Giorgio broadcast traffic on CAN-C is "
            "largely 11-bit, so a monitor opened 29-bit-only can report zero frames on a "
            "perfectly healthy bus. Listened for after STP 34, never preferred for UDS.",
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
            "HS transceiver re-pinned onto 3/11 by the cable; never use STP 53/54 with the cable fitted",
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
        "set STCMM 0 before STPO when the rate is in doubt."
    ),
)

CAN_CH = Bus(
    key="can_ch",
    name="CAN-CH (chassis / ADAS / safety)",
    pins=(12, 13),
    bitrate=500000,
    bitrate_confidence="inferred",
    id_bits=29,
    routes=(
        Route(
            "grey_a6",
            "34",
            None,
            "confirmed",
            "bitrate inferred 500k; if silent try STP 36 then STPBR 125000",
        ),
    ),
    transmit_needs_confirmation=True,
    modules_seen=("ABS", "EPS", "ORC", "AFLS", "PAM", "HALF"),
    notes=(
        "Never transmit on CAN-CH without explicit human confirmation: "
        "brakes, airbag squibs and steering assist live here. Listen first "
        "with STCMM 0 + STM. FEPS hazard: the vLinker FS is a Ford tool "
        "whose 18V FEPS output is OBD pin 13, which on Giorgio is "
        "CAN-CH(-). Never issue any FEPS or programming-voltage command on "
        "this vehicle; whether the FS can be commanded to FEPS over serial "
        "is UNVERIFIED, treat as live."
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
