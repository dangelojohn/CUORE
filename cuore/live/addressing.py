"""Pure-data description of Giorgio-platform UDS addresses and DIDs.

Source of truth: docs/reference/GIORGIO_MODULE_MAP.md (Table A, the
"never answered" table, Table C, and the hazard notes). This module
encodes exactly what that document says. Where the document says
"unknown", this module uses ``None``. Confidences are never upgraded
past what the document states -- in particular, the seven stelvio_scan
self-declared constants and the danardi78 EPS inference stay at
UNVERIFIED / INFERRED, never CONFIRMED.

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Confidence(str, Enum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNVERIFIED = "unverified"
    UNKNOWN = "unknown"


TESTER = 0xF1
FUNCTIONAL_REQUEST = 0x18DB33F1
RESERVED_TARGETS = frozenset({0xF1, 0x33, 0xBA})  # tester, functional, BACCAble squat

_STELVIO_SCAN_SOURCE = "stelvio_scan uds/addresses.py (self-declared unsourced)"


@dataclass(frozen=True)
class ECUAddress:
    code: str
    name: str
    bus_key: str  # "can_c" | "can_ihs" | "can_ch"
    bus_confidence: str  # "confirmed" for Table A rows, "inferred" for never-seen rows
    target: int | None  # 29-bit target address byte, None if unknown
    confidence: Confidence  # of the TARGET
    source: str
    note: str = ""
    hazard: str | None = None
    iso_code: str | None = None
    hw_number: str | None = None
    sw_number: str | None = None
    present: str = "confirmed"  # "confirmed" (in scan logs) | "unverified" (database only)

    @property
    def request_id(self) -> int | None:
        if self.target is None:
            return None
        return 0x18DA0000 | (self.target << 8) | TESTER

    @property
    def response_id(self) -> int | None:
        if self.target is None:
            return None
        return 0x18DAF100 | self.target

    @property
    def request_hex(self) -> str | None:
        if self.request_id is None:
            return None
        return f"{self.request_id:08X}"

    @property
    def response_hex(self) -> str | None:
        if self.response_id is None:
            return None
        return f"{self.response_id:08X}"

    @property
    def usable(self) -> bool:
        return self.target is not None and self.confidence is Confidence.CONFIRMED


def address_pair(target: int) -> tuple[str, str]:
    """("18DA10F1", "18DAF110") for any target byte."""
    request_id = 0x18DA0000 | (target << 8) | TESTER
    response_id = 0x18DAF100 | target
    return f"{request_id:08X}", f"{response_id:08X}"


MODULES: tuple[ECUAddress, ...] = (
    # --- Table A: modules present on this car -----------------------------
    ECUAddress(
        code="ECM",
        name="Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=0x10,
        confidence=Confidence.CONFIRMED,
        source="danardi78 header DA10F1; ClaudeMarais ESP32 repo",
        note="STP 34 (STP 33 for legislated 7E0/7E8)",
        iso_code="00 01 50 40 18",
        hw_number="MM10JAHW232 (00)",
        sw_number="P235QB39 (0000)",
        present="confirmed",
    ),
    ECUAddress(
        code="TCM",
        name="ZF 8HP50/75 Automatic Gearbox",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=0x18,
        confidence=Confidence.CONFIRMED,
        source="danardi78 header DA18F1",
        note="STP 34",
        iso_code="00 0B 50 AA 14",
        hw_number="10344202761 (20)",
        sw_number="GK0902OE2HN (0003)",
        present="confirmed",
    ),
    ECUAddress(
        code="BCM",
        name="Body Computer Marelli (949), gateway",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=0x40,
        confidence=Confidence.CONFIRMED,
        source="danardi78 header DA40F1 (IBS, key position, light switch)",
        note="Diagnostically reachable on CAN-C; gateways to CAN-IHS. STP 34",
        iso_code="00 00 70 7C 15",
        hw_number="BCM949M_C02 (01)",
        sw_number="04441660441 (1454)",
        present="confirmed",
    ),
    ECUAddress(
        code="IPC",
        name="Instrument Panel Continental",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=0x60,
        confidence=Confidence.CONFIRMED,
        source="danardi78 header DA60F1",
        note="STP 34",
        iso_code="00 03 50 8B 14",
        hw_number="A2C11140400 (01)",
        sw_number="AR952 HL (203C)",
        present="confirmed",
    ),
    ECUAddress(
        code="RFHUB",
        name="Radio frequency hub Continental",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=0xC7,
        confidence=Confidence.CONFIRMED,
        source="danardi78 header DAC7F1 (TPMS 2240B1..B4)",
        note="Address CONFIRMED; that it is RFHUB is INFERRED. STP 34",
        hazard=(
            "Do not use 0x18DABAF1: squatted by the BACCAble project's "
            "board. 0x18DAC7F1 carries a documented immobiliser hazard if "
            "a BACCAble board is fitted; none is fitted here, so reading "
            "TPMS is safe, but keep the warning in the data."
        ),
        iso_code="00 41 50 89 15",
        hw_number="10161500AA (01)",
        sw_number="10307064AB (0940)",
        present="confirmed",
    ),
    ECUAddress(
        code="DTCM",
        name="Magna Q4 Transfer Case",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=0x29,
        confidence=Confidence.UNVERIFIED,
        source=_STELVIO_SCAN_SOURCE,
        note="STP 34",
        iso_code="00 43 50 91 14",
        hw_number="M0045027.01 (21)",
        sw_number="M0099947 (0501)",
        present="confirmed",
    ),
    ECUAddress(
        code="ESM",
        name="ZF Electronic Gear Shift Module",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="STP 34",
        iso_code="00 16 50 B4 14",
        hw_number="1000597140 (08)",
        sw_number="1000678050 (0019)",
        present="confirmed",
    ),
    ECUAddress(
        code="DASM",
        name="Driver assistance radar Bosch",
        bus_key="can_c",
        bus_confidence="confirmed",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="CONFIRMED present 7/7 scans without cable. STP 34",
        iso_code="00 39 70 7E 15",
        hw_number="MRR1evo14F (00)",
        sw_number="52081920 (0500)",
        present="confirmed",
    ),
    ECUAddress(
        code="ABS",
        name="Continental ABS MK C1",
        bus_key="can_ch",
        bus_confidence="confirmed",
        target=0x28,
        confidence=Confidence.UNVERIFIED,
        source=_STELVIO_SCAN_SOURCE,
        note="STP 34 (500k assumed)",
        iso_code="00 06 50 5B 14",
        hw_number="28554010535 (00)",
        sw_number="XJ_RAL00165 (83C1)",
        present="confirmed",
    ),
    ECUAddress(
        code="EPS",
        name="ZF Electric Steering",
        bus_key="can_ch",
        bus_confidence="confirmed",
        target=0x2A,
        confidence=Confidence.INFERRED,
        source=(
            "danardi78 header DA2AF1 returns steering angle; conflicts "
            "with stelvio_scan SAS 0x76"
        ),
        note="INFERRED (medium). STP 34",
        iso_code="00 02 40 5F 14",
        hw_number="7806277500 (30)",
        sw_number="880802D0243 (A410)",
        present="confirmed",
    ),
    ECUAddress(
        code="ORC",
        name="Airbag / Occupant Restraint (MES: unsupported)",
        bus_key="can_ch",
        bus_confidence="confirmed",
        target=0x50,
        confidence=Confidence.UNVERIFIED,
        source=_STELVIO_SCAN_SOURCE,
        note="STP 34",
        iso_code="00 1A 70 84 15",
        hw_number="0285013327 (30)",
        sw_number="BB70578 (0403)",
        present="confirmed",
    ),
    ECUAddress(
        code="AFLS",
        name="Automotive Lighting adaptive headlights",
        bus_key="can_ch",
        bus_confidence="confirmed",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="STP 34",
        iso_code="00 1D 50 C7 14",
        hw_number="1470000328 (02)",
        sw_number="1409910330 (000C)",
        present="confirmed",
    ),
    ECUAddress(
        code="PAM",
        name="Parking control Bosch",
        bus_key="can_ch",
        bus_confidence="confirmed",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="STP 34",
        iso_code="00 18 50 87 15",
        hw_number="19490108 (03)",
        sw_number="1.38 (0304)",
        present="confirmed",
    ),
    ECUAddress(
        code="HALF",
        name="Haptical lane feedback camera Bosch (MFK2)",
        bus_key="can_ch",
        bus_confidence="confirmed",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="CONFIRMED, MES lists ELMA6. STP 34",
        iso_code="00 1E 50 72 14",
        hw_number="0203500279 (01)",
        sw_number="1037601726 (1001)",
        present="confirmed",
    ),
    # --- Modules MES lists for this car that have never answered ----------
    ECUAddress(
        code="HVAC",
        name="Climate control (TRW)",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=0x68,
        confidence=Confidence.UNVERIFIED,
        source=_STELVIO_SCAN_SOURCE,
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="ETM",
        name="AlfaConnect radio-nav / uConnect",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=0x6F,
        confidence=Confidence.UNVERIFIED,
        source=_STELVIO_SCAN_SOURCE,
        note="never scanned; aka EMCM/DSM",
        present="unverified",
    ),
    ECUAddress(
        code="AMP",
        name="Amplifier",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="ESEM",
        name="Engine sound enhancement",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="CSWM",
        name="Comfort seat and wheel",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="CRSM",
        name="Rear seat",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="LBSS",
        name="Blind-spot sensor, left",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="RBSS",
        name="Blind-spot sensor, right",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="PLGM",
        name="Power liftgate",
        bus_key="can_ihs",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="never scanned",
        present="unverified",
    ),
    ECUAddress(
        code="TVM",
        name="Torque vectoring",
        bus_key="can_ch",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="did not answer on the A6 scan; likely not fitted (QV item)",
        present="unverified",
    ),
    ECUAddress(
        code="ESL",
        name="Steering lock (TRW)",
        bus_key="can_ch",
        bus_confidence="inferred",
        target=None,
        confidence=Confidence.UNKNOWN,
        source="",
        note="did not answer on the A6 scan; aka NBS",
        present="unverified",
    ),
)


def by_code(code: str) -> ECUAddress | None:
    for module in MODULES:
        if module.code == code:
            return module
    return None


def on_bus(bus_key: str) -> list[ECUAddress]:
    return [module for module in MODULES if module.bus_key == bus_key]


def confirmed() -> list[ECUAddress]:
    """Usable targets only."""
    return [module for module in MODULES if module.usable]


def sweep_candidates(bus_key: str, *, include_unverified_first: bool = True) -> list[int]:
    """All 0x00..0xFF minus RESERVED_TARGETS, best guesses first.

    Any INFERRED/UNVERIFIED targets belonging to modules on ``bus_key`` are
    moved to the front (in Table-A order) so a sweep tries them first.
    """
    guesses: list[int] = []
    if include_unverified_first:
        for module in on_bus(bus_key):
            if module.target is None:
                continue
            if module.confidence in (Confidence.INFERRED, Confidence.UNVERIFIED):
                if module.target not in guesses:
                    guesses.append(module.target)

    rest = [
        target
        for target in range(0x00, 0x100)
        if target not in RESERVED_TARGETS and target not in guesses
    ]
    return guesses + rest


@dataclass(frozen=True)
class DidSpec:
    module: str  # MES code
    did: int
    name: str
    formula: str  # CarScanner syntax verbatim from Table C, "" if none
    unit: str
    source: str
    confidence: str  # "confirmed" | "unverified"
    diesel_only: bool = False
    note: str = ""


ANNEX_C: dict[int, str] = {
    0xF190: "VIN",
    0xF187: "spare part",
    0xF188: "ECU SW",
    0xF189: "SW version",
    0xF18C: "serial",
    0xF191: "HW",
    0xF192: "HW",
    0xF193: "HW",
    0xF194: "supplier SW",
    0xF195: "supplier SW",
    0xF197: "system name",
    0xF18B: "manufacture date",
    0xF199: "programming date",
    0xF186: "active session",
    0xF198: "last tester",
}

DIDS: tuple[DidSpec, ...] = (
    # --- ECM, Magneti Marelli IAW 10JA, header 18DA10F1 --------------------
    DidSpec(
        module="ECM",
        did=0x1000,
        name="Engine RPM",
        formula="((A*256)+B)/4",
        unit="rpm",
        source="danardi78",
        confidence="unverified",
        note="CONFIRMED on Giulia 2.2D, UNVERIFIED on 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x1002,
        name="Vehicle speed",
        formula="((A*256)+B)/124",
        unit="km/h",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x1003,
        name="Coolant temperature",
        formula="(((A*256)+B)*0.02)-40",
        unit="°C",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x1302,
        name="Engine oil temperature",
        formula="B",
        unit="°C",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED; single-byte B looks like a truncated 2-byte field",
    ),
    DidSpec(
        module="ECM",
        did=0x130A,
        name="Engine oil pressure",
        formula="A*10/255",
        unit="bar",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x195A,
        name="Boost pressure",
        formula="((A*256+B)-32768)/1000-1",
        unit="bar",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T; highest-value DID for this engine, verify first",
    ),
    DidSpec(
        module="ECM",
        did=0x1935,
        name="Intake air temp (post-turbo)",
        formula="(((A*256)+B)*0.02)-40",
        unit="°C",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x1955,
        name="Battery voltage",
        formula="((A*256)+B)*(0.5/1000)",
        unit="V",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x192D,
        name="Current engaged gear",
        formula="A",
        unit="",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T",
    ),
    DidSpec(
        module="ECM",
        did=0x19BD,
        name="IBS state of charge",
        formula="A",
        unit="%",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T",
    ),
    # Diesel-only ECM group -- "do not encode for this car" (petrol 2.0T).
    # Kept in DIDS for completeness, flagged diesel_only=True; excluded by
    # dids_for() unless include_diesel=True is passed explicitly.
    DidSpec(
        module="ECM",
        did=0x1946,
        name="Rail pressure / DPF / regen (diesel)",
        formula="",
        unit="",
        source="danardi78",
        confidence="unverified",
        diesel_only=True,
        note="Diesel-only; do not encode for this car",
    ),
    DidSpec(
        module="ECM",
        did=0x1904,
        name="Rail pressure / DPF / regen (diesel)",
        formula="",
        unit="",
        source="danardi78",
        confidence="unverified",
        diesel_only=True,
        note="Diesel-only; do not encode for this car",
    ),
    DidSpec(
        module="ECM",
        did=0x18E4,
        name="Rail pressure / DPF / regen (diesel)",
        formula="",
        unit="",
        source="danardi78",
        confidence="unverified",
        diesel_only=True,
        note="Diesel-only; do not encode for this car",
    ),
    DidSpec(
        module="ECM",
        did=0x18DE,
        name="Rail pressure / DPF / regen (diesel)",
        formula="",
        unit="",
        source="danardi78",
        confidence="unverified",
        diesel_only=True,
        note="Diesel-only; do not encode for this car",
    ),
    DidSpec(
        module="ECM",
        did=0x18A4,
        name="Rail pressure / DPF / regen (diesel)",
        formula="",
        unit="",
        source="danardi78",
        confidence="unverified",
        diesel_only=True,
        note="Diesel-only; do not encode for this car",
    ),
    DidSpec(
        module="ECM",
        did=0x3807,
        name="Rail pressure / DPF / regen (diesel)",
        formula="",
        unit="",
        source="danardi78",
        confidence="unverified",
        diesel_only=True,
        note="Diesel-only; do not encode for this car",
    ),
    # --- TCM, ZF 8HP50, header 18DA18F1 -------------------------------------
    DidSpec(
        module="TCM",
        did=0x1018,
        name="Torque as received from ECM",
        formula="((A*256+B)-500)",
        unit="Nm",
        source="danardi78",
        confidence="unverified",
        note=(
            "UNVERIFIED on 2.0T. The 8HP never measures torque, it is told "
            "torque over CAN, so this is the most informative value on "
            "the box"
        ),
    ),
    DidSpec(
        module="TCM",
        did=0x04FE,
        name="Gearbox oil temperature",
        formula="A-40",
        unit="°C",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED on 2.0T; fluid temp heads the 8HP failure chain, verify early",
    ),
    DidSpec(
        module="TCM",
        did=0x0518,
        name="DNA mode selector",
        formula="A",
        unit="",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED",
    ),
    DidSpec(
        module="TCM",
        did=0x0540,
        name="DNA mode selector (alt byte)",
        formula="C",
        unit="",
        source="danardi78",
        confidence="unverified",
        note="UNVERIFIED; determine which is authoritative",
    ),
    # --- Other confirmed headers worth encoding -----------------------------
    DidSpec(
        module="BCM",
        did=0x1004,
        name="Battery voltage",
        formula="A/10",
        unit="V",
        source="",
        confidence="unverified",
        note="conflicts with web_research.md listing 1004 under DA10F1; resolve by reading both",
    ),
    DidSpec(
        module="BCM",
        did=0x1005,
        name=(
            "IBS composite: SoC B %, temp G-40 °C, voltage "
            "((J*256)+K)/800 V, current (((L*256)+M)-32768)/100*0.8 A"
        ),
        formula="multi-field",
        unit="",
        source="",
        confidence="unverified",
        note="the ground-strap / parasitic-draw instrument",
    ),
    DidSpec(
        module="BCM",
        did=0x0131,
        name="Key ignition position",
        formula="A",
        unit="",
        source="",
        confidence="unverified",
    ),
    DidSpec(
        module="BCM",
        did=0x0133,
        name="External light switch",
        formula="(A*256)+B",
        unit="",
        source="",
        confidence="unverified",
    ),
    DidSpec(
        module="IPC",
        did=0x0104,
        name="IPC brightness",
        formula="A",
        unit="",
        source="",
        confidence="unverified",
    ),
    DidSpec(
        module="EPS",
        did=0x083C,
        name="Steering angle",
        formula="(SIGNED(A)*256+B)/16",
        unit="°",
        source="",
        confidence="unverified",
        note="answered on pins 6/14 for danardi, so possibly reachable without the grey cable; test here",
    ),
    DidSpec(
        module="RFHUB",
        did=0x40B1,
        name="Tire pressure/temp, FL",
        formula="pressure=((A*256)+B)/1000; temp=E-50",
        unit="bar, °C",
        source="",
        confidence="unverified",
    ),
    DidSpec(
        module="RFHUB",
        did=0x40B2,
        name="Tire pressure/temp, FR",
        formula="pressure=((A*256)+B)/1000; temp=E-50",
        unit="bar, °C",
        source="",
        confidence="unverified",
    ),
    DidSpec(
        module="RFHUB",
        did=0x40B3,
        name="Tire pressure/temp, RL",
        formula="pressure=((A*256)+B)/1000; temp=E-50",
        unit="bar, °C",
        source="",
        confidence="unverified",
    ),
    DidSpec(
        module="RFHUB",
        did=0x40B4,
        name="Tire pressure/temp, RR",
        formula="pressure=((A*256)+B)/1000; temp=E-50",
        unit="bar, °C",
        source="",
        confidence="unverified",
    ),
)


def dids_for(module: str, *, include_diesel: bool = False) -> list[DidSpec]:
    return [
        did
        for did in DIDS
        if did.module == module and (include_diesel or not did.diesel_only)
    ]
