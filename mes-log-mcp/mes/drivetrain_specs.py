"""Stelvio 2.0T (GU) drivetrain specs and torques -- pure stdlib data module.

Companion data to ``docs/reference/STELVIO_20T_DRIVETRAIN_SPECS.md``; read that
file for prose, full sourcing detail and the "what is UNKNOWN" summary. Every
row here mirrors a row in that document.

Shape note
----------
``mes-log-mcp/mes/service_specs.py`` (the general oil-change / brakes /
suspension torque ledger, written by another agent) existed by the time this
module was finished, so the ``TORQUES`` row shape here is copied field-for-
field from its ``_torque()`` helper: ``key``, ``component``, ``categories``
(tuple), ``value``, ``unit`` ("Nm" or "lb-ft"), ``value_nm``, ``value_lbft``,
``value_range``, ``display``, ``angle``, ``single_use``, ``source``,
``confidence``, ``notes``, ``platform_note`` -- plus one addition this module
needs and ``service_specs.py`` does not: a ``section`` key naming which of
the five ``SECTIONS`` below the row belongs to. The four confidence
constants and ``TECHAUTHORITY`` are redefined locally (identical string
values) rather than imported, so this module has no import-time dependency
on ``service_specs.py``.

``service_specs.py`` already carries a handful of driveline rows under its
own "transmission" / "transfer_case" / "differential" categories (it is the
whole-car service ledger, this module is the drivetrain-only deep dive) --
where its research turned up something this module's own research pass had
marked UNKNOWN (the rear differential plug torque, notably), that value is
folded in here too, credited to its original source.

``SPECS`` has no equivalent list in ``service_specs.py`` to match, so its
shape is this module's own: ``key``, ``component``, ``categories`` (tuple),
``value`` (str), ``unit``, ``source``, ``confidence``, ``notes``, ``section``.

Organisation
------------
``SECTIONS`` groups everything into five self-contained drivetrain areas,
each its own dict of ``{"specs": [...], "torques": [...], "jobs": {...}}``
(plus a few section-specific extras: ``dtcs``, ``tsbs``, ``issues``):

    transmission   -- ZF 8HP50/75, including its cooling
    transfer_case  -- Magna Q4 active on-demand transfer case
    differentials  -- front and rear, as sub-dicts "front" / "rear", plus
                       section-level "specs"/"torques" combining both
    driveline      -- propshaft/driveshaft, CV axles, hub nuts
    mounts         -- engine and transmission mounts

``SPECS``, ``TORQUES`` and ``JOBS`` below are flat views of the same rows
(every row carries its own ``section`` key), for callers that want one table
rather than the sectioned view.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"

CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN)

TECHAUTHORITY = "use the service manual (TechAuthority)"

VEHICLE = ("2018 Alfa Romeo Stelvio 2.0T (GU), 2.0L GME-T4 turbo I4, sales "
           "code EC2, US market, Magna Q4 AWD, ZF 8HP50 automatic (MES: "
           "'ZF 8HP50/75')")

NM_PER_LBFT = 1.35582
LBFT_PER_NM = 0.737562149


def nm_to_lbft(nm: Optional[float]) -> Optional[float]:
    if nm is None:
        return None
    return round(nm * LBFT_PER_NM, 1)


def lbft_to_nm(lbft: Optional[float]) -> Optional[float]:
    if lbft is None:
        return None
    return round(lbft * NM_PER_LBFT, 1)


# ---------------------------------------------------------------------------
# TORQUES -- row shape matches service_specs.py's _torque() output exactly,
# plus a "section" key.
# ---------------------------------------------------------------------------

TORQUES: list[dict[str, Any]] = []


def _torque(section: str, key: str, component: str, categories: Iterable[str],
            value: Optional[float], unit: Optional[str], *,
            value_range: Optional[tuple[float, float]] = None,
            angle: Optional[str] = None, single_use: bool = False,
            source: Optional[str] = None, confidence: str = UNKNOWN,
            notes: str = "", platform_note: Optional[str] = None,
            display: Optional[str] = None) -> None:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    value_nm = value if unit == "Nm" else (lbft_to_nm(value) if unit == "lb-ft" else None)
    value_lbft = value if unit == "lb-ft" else (nm_to_lbft(value) if unit == "Nm" else None)
    if not notes and confidence == UNKNOWN:
        notes = TECHAUTHORITY
    TORQUES.append({
        "section": section,
        "key": key,
        "component": component,
        "categories": tuple(categories),
        "value": value,
        "unit": unit,
        "value_nm": value_nm,
        "value_lbft": value_lbft,
        "value_range": value_range,
        "display": display or (f"{value} {unit}" if value is not None else "UNKNOWN"),
        "angle": angle,
        "single_use": single_use,
        "source": source,
        "confidence": confidence,
        "notes": notes.strip(),
        "platform_note": platform_note,
    })


# --- 1. transmission (ZF 8HP50/75) ------------------------------------------

_torque("transmission", "transmission_pan_bolts",
        "ZF 8HP pan/filter assembly bolts (13x)", ["transmission"],
        10, "Nm",
        source="docs/reference/ZF8HP_SERVICE_DATA.md (ZF doc 1087.754.107c)",
        confidence=CONFIRMED,
        notes="Integrated pan/filter assembly, not separately serviceable; "
              "gasket reusable if undamaged. No bolt sequence stated in the "
              "source doc.")

_torque("transmission", "transmission_drain_plug",
        "ZF 8HP transmission fluid drain plug", ["transmission"],
        None, "Nm", confidence=UNKNOWN,
        notes="Giorgio-specific value not found. " + TECHAUTHORITY)

_torque("transmission", "transmission_fill_plug",
        "ZF 8HP transmission fluid fill/level plug", ["transmission"],
        None, "Nm", confidence=UNKNOWN,
        notes="Giorgio-specific value not found; the 4th-gen 8HP fill/level "
              "check requires an OEM scan-tool routine, not a manual "
              "plug-and-check, per docs/reference/ZF8HP_SERVICE_DATA.md #1. "
              + TECHAUTHORITY)

_torque("transmission", "bmw_mechatronics_bolts",
        "BMW G30 reference: mechatronics-to-transmission bolts M6x59/M6x20",
        ["transmission"], 8, "Nm", single_use=True,
        source="docs/reference/ZF8HP_SERVICE_DATA.md (BMW G30 service info)",
        confidence=CORROBORATED,
        notes="Sequence 1->17; screws replaced every time. BMW 8HP family -- "
              "NOT independently confirmed for Giorgio.",
        platform_note="BMW G30, not Alfa-specific.")

_torque("transmission", "bmw_output_speed_sensor",
        "BMW G30 reference: output speed sensor", ["transmission"],
        4, "Nm", angle="+12 deg",
        source="docs/reference/ZF8HP_SERVICE_DATA.md (BMW G30 service info)",
        confidence=CORROBORATED,
        notes="BMW 8HP family -- NOT independently confirmed for Giorgio.",
        platform_note="BMW G30, not Alfa-specific.")

_torque("transmission", "bmw_pan_bolts",
        "BMW G30 reference: pan bolts M6 (13x)", ["transmission"],
        10, "Nm", single_use=True,
        source="docs/reference/ZF8HP_SERVICE_DATA.md (BMW G30 service info)",
        confidence=CORROBORATED,
        notes="Sequence 1->13; pan itself must be replaced each time it is "
              "released. BMW 8HP family -- NOT independently confirmed for "
              "Giorgio, whose pan/filter is documented as an integrated "
              "non-serviceable assembly in the FCA text.",
        platform_note="BMW G30, not Alfa-specific.")

_torque("transmission", "bmw_drain_plug",
        "BMW G30 reference: drain plug M18", ["transmission"],
        8, "Nm",
        source="docs/reference/ZF8HP_SERVICE_DATA.md (BMW G30 service info)",
        confidence=CORROBORATED,
        notes="BMW 8HP family -- NOT independently confirmed for Giorgio.",
        platform_note="BMW G30, not Alfa-specific.")

# --- 2. transfer case (Magna Q4) --------------------------------------------

_torque("transfer_case", "transfer_case_drain_plug",
        "Transfer case (Q4) drain plug", ["transfer_case"],
        None, "Nm", confidence=UNKNOWN,
        notes="A stelvioforum thread asking this exact question cites the "
              "rear differential's 26 Nm as known but leaves the transfer "
              "case itself as an open, unanswered question -- do not assume "
              "'probably the same as the diff', that is speculation, not a "
              "source. " + TECHAUTHORITY,
        source="https://www.stelvioforum.com/threads/transfer-case-drain-fill-plug-torque-specs.24693/")

_torque("transfer_case", "transfer_case_fill_plug",
        "Transfer case (Q4) fill plug", ["transfer_case"],
        None, "Nm", confidence=UNKNOWN,
        notes="Same open question as transfer_case_drain_plug. " + TECHAUTHORITY,
        source="https://www.stelvioforum.com/threads/transfer-case-drain-fill-plug-torque-specs.24693/")

# --- 3. differentials --------------------------------------------------------

_torque("differentials", "front_diff_drain_plug",
        "Front differential drain plug", ["differential", "front"],
        None, "Nm", confidence=UNKNOWN,
        notes="Not found. " + TECHAUTHORITY)

_torque("differentials", "front_diff_fill_plug",
        "Front differential fill plug", ["differential", "front"],
        None, "Nm", confidence=UNKNOWN,
        notes="Not found. " + TECHAUTHORITY)

_torque("differentials", "rear_diff_drain_plug",
        "Rear differential (rear axle) drain plug", ["differential", "rear"],
        26, "Nm",
        source="https://www.stelvioforum.com/threads/transfer-case-drain-fill-plug-torque-specs.24693/",
        confidence=SINGLE_SOURCE,
        notes="Stated as known/given by the original poster in a thread "
              "actually asking about the transfer case plug; not "
              "independently corroborated elsewhere.")

_torque("differentials", "rear_diff_fill_plug",
        "Rear differential (rear axle) fill plug", ["differential", "rear"],
        26, "Nm",
        source="https://www.stelvioforum.com/threads/transfer-case-drain-fill-plug-torque-specs.24693/",
        confidence=SINGLE_SOURCE,
        notes="Same source as rear_diff_drain_plug; drain and fill plugs "
              "are commonly the same fastener spec on this style of axle, "
              "but that has not been independently confirmed as true here.")

# --- 4. driveline (propshaft, CV axles, hub nuts) ---------------------------

_torque("driveline", "propshaft_flange_nut",
        "Propshaft flange/centre-carrier nut", ["driveline"],
        None, "Nm",
        source="none for the Giorgio platform -- use the service manual (TechAuthority)",
        confidence=UNKNOWN,
        notes="DO NOT USE the 72-101 lb-ft figure that circulates online: fact-check "
              "(2026-09-26) traced it to the 1970s Alfa 2000 shop manual (10-14 m-kg), a "
              "different car and driveline, not the Stelvio's Q4 propshaft. Use the FCA "
              "service manual value for this VIN.",
        display="UNKNOWN - use service manual")

_torque("driveline", "q4_central_m14_bolt",
        "Central M14 bolt, Q4 (4x4) versions", ["driveline", "mounts"],
        None, "Nm", value_range=(124, 136),
        source="forum synthesis (alfaowner.com)",
        confidence=SINGLE_SOURCE,
        notes="Location not independently confirmed -- possibly a "
              "front-driveline or subframe pivot fastener unique to AWD "
              "cars; may instead be an engine-mount-to-subframe pivot bolt "
              "(see the mounts section's identical entry). Not resolved "
              "which fastener this actually is.",
        display="124-136 Nm")

_torque("driveline", "axle_hub_nut",
        "Front/rear axle (hub) nut", ["driveline"],
        52, "lb-ft", angle="+47 deg", single_use=True,
        source="stelvioforum.com forum synthesis",
        confidence=SINGLE_SOURCE,
        notes="Torque-then-angle procedure; always fit a NEW nut.")

_torque("driveline", "hub_mount_bolts",
        "Front/rear hub mounting bolts", ["driveline"],
        74, "lb-ft",
        source="forum synthesis (stelvioforum.com)",
        confidence=SINGLE_SOURCE,
        notes="")

_torque("driveline", "wheel_lug_reference",
        "Wheel lug bolts (reference only, not a drivetrain fastener)",
        ["driveline"], 89, "lb-ft",
        source="forum synthesis (giuliaforums.com/alfaowner.com)",
        confidence=SINGLE_SOURCE,
        notes="Included for completeness only; see service_specs.py's own "
              "wheel_lug row (121 Nm / CORROBORATED) for the vetted figure "
              "used by the general service ledger -- the two were not "
              "reconciled against each other in this pass.")

# --- 5. mounts (engine and transmission) ------------------------------------

_torque("mounts", "engine_mount_bolts",
        "Engine mount bolts into aluminium block", ["mounts"],
        None, "Nm", value_range=(22, 27),
        source="forum synthesis (alfaowner.com)",
        confidence=SINGLE_SOURCE,
        notes="",
        display="22-27 Nm")

_torque("mounts", "longitudinal_mount_bolts",
        "Longitudinal mount (torque strut / dogbone) bolts", ["mounts"],
        None, "Nm", value_range=(25, 31), single_use=True,
        source="forum synthesis (alfaowner.com); aftermarket install-"
               "instruction PDF (binary/encoded, not text-extractable this pass)",
        confidence=SINGLE_SOURCE,
        notes="Alfa Romeo specifies the mount itself must be replaced on "
              "removal, not just the bolts.",
        display="25-31 Nm")

_torque("mounts", "q4_central_m14_bolt_mounts",
        "Central M14 bolt, Q4 versions (mounts-context duplicate)",
        ["mounts", "driveline"], None, "Nm", value_range=(124, 136),
        source="forum synthesis (alfaowner.com)",
        confidence=SINGLE_SOURCE,
        notes="Same figure and same unresolved-location caveat as "
              "driveline's q4_central_m14_bolt -- kept here too since which "
              "section it truly belongs to was not resolved this pass.",
        display="124-136 Nm")

_torque("mounts", "trans_mount_bracket_fasteners",
        "Transmission-bracket-to-transmission-case fasteners", ["mounts"],
        None, "Nm", single_use=True,
        source="forum synthesis (alfaowner.com), citing an unidentified FCA TSB",
        confidence=SINGLE_SOURCE,
        notes="Fasteners reported one-time-use per a referenced TSB for the "
              "2021 Stelvio; bulletin number not independently verified "
              "this pass, and no torque value was found. " + TECHAUTHORITY)


def torque_by_key(key: str) -> Optional[dict[str, Any]]:
    for t in TORQUES:
        if t["key"] == key:
            return dict(t)
    return None


def torques_for_section(section: str) -> list[dict[str, Any]]:
    return [dict(t) for t in TORQUES if t["section"] == section]


# ---------------------------------------------------------------------------
# SPECS -- non-torque facts (fluids, capacities, intervals, DIDs, ...).
# No equivalent list exists in service_specs.py to match; shape is this
# module's own, but deliberately close (key/component/categories/confidence).
# ---------------------------------------------------------------------------

SPECS: list[dict[str, Any]] = []


def _spec(section: str, key: str, component: str, categories: Iterable[str],
          value: str, unit: str = "", *, source: str = "",
          confidence: str = UNKNOWN, notes: str = "") -> None:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    if not notes and confidence == UNKNOWN:
        notes = TECHAUTHORITY
    SPECS.append({
        "section": section,
        "key": key,
        "component": component,
        "categories": tuple(categories),
        "value": value,
        "unit": unit,
        "source": source,
        "confidence": confidence,
        "notes": notes,
    })


# --- 1. transmission ---------------------------------------------------------

_spec("transmission", "fluid_identity", "ZF 8HP transmission fluid",
      ["transmission", "fluid"],
      "ZF LifeguardFluid 8 / Mopar '8 & 9 Speed ATF', P/N 68218925AA -- "
      "NOT compatible with ATF+4 or any other current FCA ATF", "",
      source="docs/reference/ZF8HP_SERVICE_DATA.md #1 (ZF doc 1087.754.107c); "
             "giuliaforums.com 'How-To: ZF 8HP50/75 Fluid and Filter Change'",
      confidence=CORROBORATED,
      notes="Fluid identity/incompatibility CONFIRMED via repo doc; the "
            "Mopar part number itself is SINGLE-SOURCE.")

_spec("transmission", "dry_fill_capacity", "ZF 8HP overhaul dry fill",
      ["transmission", "fluid"], "9.0 (9.5 qt); +0.7 if cooler replaced", "L",
      source="docs/reference/ZF8HP_SERVICE_DATA.md #1 (ZF doc 1087.754.107c, Table 1)",
      confidence=CONFIRMED,
      notes="Poured through the side plug, unit tipped, before installation.")

_spec("transmission", "owner_manual_capacity",
      "ZF 8HP owner/service-manual capacity, 2.0 AWD",
      ["transmission", "fluid"], "9.3 (9.8 qt)", "L",
      source="giuliatech.com/t/alfa-romeo-giulia-fluid-specs-and-capacities/91",
      confidence=SINGLE_SOURCE,
      notes="Close to but not reconciled with the 9.0 L ZF dry-fill figure.")

_spec("transmission", "service_fill_quantity",
      "ZF 8HP service drain-and-fill (pan drop) quantity",
      ["transmission", "fluid"],
      "not established -- 'a few quarts' pan volume + 0.5 L overfill during level check",
      "L", source="giuliaforums.com 'How-To' thread", confidence=UNKNOWN,
      notes="Forum practice, not an OEM spec. " + TECHAUTHORITY)

_spec("transmission", "fill_temp_window", "ZF 8HP fill/level-check temperature window",
      ["transmission", "fluid"], "30-50 (86-122 F)", "°C",
      source="docs/reference/ZF8HP_SERVICE_DATA.md #1", confidence=CONFIRMED,
      notes="General 8HP family window; matches this car's family per ZF "
            "Table 1 and FCA OEM text.")

_spec("transmission", "level_check_procedure", "ZF 8HP level-check procedure",
      ["transmission", "fluid"],
      "ZF: engine running, P, 2000rpm 30s, idle, cycle P-R-D-1-2 >=10s dwell "
      "each, P, check temp+plug. FCA equivalent: fill, R 5s, D 5s, "
      "accelerate 2nd 5s, N@2000rpm 5s, P.", "",
      source="docs/reference/ZF8HP_SERVICE_DATA.md #1 (ZF doc Section 5)",
      confidence=CONFIRMED,
      notes="4th-gen 8HP (this box) requires an OEM scan-tool routine -- no "
            "manual plug procedure exists.")

_spec("transmission", "pan_filter", "ZF 8HP pan/filter", ["transmission"],
      "integrated assembly, not separately serviceable; gasket reusable if undamaged",
      "", source="docs/reference/ZF8HP_SERVICE_DATA.md #1", confidence=CONFIRMED)

_spec("transmission", "interval_fca", "ZF 8HP service interval, FCA position",
      ["transmission", "interval"], "no FCA-published mileage number found this pass",
      "", confidence=UNKNOWN,
      notes="The 2018 US owner's manual Maintenance Plan lists no automatic "
            "transmission fluid change (checked 2026-09-26). " + TECHAUTHORITY)

_spec("transmission", "interval_zf", "ZF 8HP service interval, ZF generic guidance",
      ["transmission", "interval"], "50000-75000", "mi",
      source="forum synthesis (ZF-attributed)", confidence=SINGLE_SOURCE,
      notes="Forum-attributed to ZF; not FCA/owner's-manual sourced.")

_spec("transmission", "interval_severe", "ZF 8HP severe-duty guidance",
      ["transmission", "interval"], "not found for this vehicle", "",
      confidence=UNKNOWN, notes=TECHAUTHORITY)

_spec("transmission", "adaptation_relearn", "ZF 8HP adaptation relearn after service",
      ["transmission", "adaptation"],
      "Fast Filling Adaptation + Standard Clutch Filling Adaptation via "
      "wiTECH; MES: QUICK LEARN / STATIC ADAPTATION (STADA) + separate "
      "RESET ADAPTIVE VALUES", "",
      source="docs/reference/ZF8HP_SERVICE_DATA.md #5-7", confidence=CONFIRMED,
      notes="Not required for a routine fluid+filter change; not required "
            "after a TCM/TCMA re-flash alone; NOT lost on battery "
            "disconnect (non-volatile EEPROM).")

_spec("transmission", "cooler", "ZF 8HP cooler", ["transmission", "cooling"],
      "oil-to-coolant heat exchanger with thermostatic element (keeps box "
      "warm for warm-up/emissions)", "",
      source="docs/research/TRANSMISSION_ZF8HP_Q4.md #6", confidence=CONFIRMED,
      notes="Track-only bypass is a modification, not a service step.")

_spec("transmission", "oil_temp_did", "Gearbox oil temperature -- live DID",
      ["transmission", "cooling", "live_data"],
      "TCM DID 04FE, header 18DA18F1, formula A-40", "°C",
      source="docs/reference/GIORGIO_MODULE_MAP.md Table C; "
             "cuore/live/addressing.py:674-683; cuore/live/ops.py:485-496",
      confidence=SINGLE_SOURCE,
      notes="Implemented as DidSpec(module='TCM', did=0x04FE, ...) in "
            "cuore/live/addressing.py. Read live via "
            "cuore.live.ops.module_did('TCM', '04FE', vin=<VIN>), or the "
            "obd2 MCP 'read_did' tool against module TCM, DID 0x04FE. "
            "Formula is UNVERIFIED on this 2.0T specifically (sourced from "
            "a 2.2D Giulia PID repo) -- confirm against this car's own scan.")

TRANSMISSION_DTCS: list[tuple[str, str]] = [
    ("P1DB7-00", "TCC Performance (functional equivalent of P0741; "
                 "P0740/P0741/P0742 do not exist on 8HP)"),
    ("P0731-P0735,P0729,P076F,P07D9", "Per-gear ratio error, non-contiguous "
                                       "numbering (gears 1-8)"),
    ("P1D8F-P1D93,P1D96-P1D9F,P1DA0-P1DA8,P1D95",
     "Clutch-resolved ratio faults: single/pair/triplet/undetermined"),
    ("P1731", "Incorrect Gear Engaged; turbine slip > 300 RPM is the only "
              "published hard threshold"),
    ("P167A", "Calibration Mismatch (software vs Hydraulic ID in TCMA EEPROM)"),
    ("P1DC6", "TCM Not Programmed"),
    ("P0610,U3002-00", "VIN mismatch after TCM replacement"),
    ("P1500", "Vehicle configuration (PROXI) mismatch"),
    ("P07E4,P1DB2,P0716,P1B14,P0733,P1D90,P1DB7,P1B13",
     "Master 8HP shift-quality/valve-body TSB code set"),
]

TRANSMISSION_TSBS: list[dict[str, Any]] = [
    {
        "number": "21-035-20", "date": "2020-05-08",
        "applies_to_this_car": True,
        "summary": "Flash: TCM Update. Applies explicitly to 2018 (GU) "
                    "Stelvio, 2.0L I4 DI Turbo (EC2), North America. Fixes "
                    "MIL w/ P0002-00, P026E-00, P1066-00, P26E4-00, "
                    "P2B61-00, P2BC1-00, U1008-00; transmission shift-"
                    "quality improvements; turbo coolant-pump after-run "
                    "update. Labor op 18-19-05-MX, 0.3 hr. PCM must also be "
                    "updated to latest at completion.",
        "source": "static.nhtsa.gov/odi/tsbs/2020/MC-10176569-9999.pdf (fetched directly)",
        "confidence": CONFIRMED,
    },
    {
        "number": "21-044-19", "date": "2019-12-17",
        "applies_to_this_car": False,
        "summary": "Flash: TCM Update. Applies to 2019 (GU) Stelvio built "
                    "on/before 2019-10-10 -- not this car's model year. Same "
                    "symptom/DTC set and shift-quality fix, prior software "
                    "revision. Labor op 18-19-05-MU.",
        "source": "static.nhtsa.gov/odi/tsbs/2019/MC-10170397-9999.pdf (fetched directly)",
        "confidence": CONFIRMED,
    },
    {
        "number": "S2621000003 REV. A", "date": "2026-03-09",
        "applies_to_this_car": True,
        "summary": "8HP master TSB, 2017-2026 Giulia (GA) and 2018-2026 "
                    "Stelvio (GU), covers 8HP45/50/70/75/90/95. Burnt-fluid "
                    "smell / fine metallic content normal. Valve body "
                    "replacement before transmission replacement. "
                    "P1B13/P1B14 -> check MPR cable. P0733 -> 21-029-25 "
                    "REV. A (8HP75 clutch-D repair, not this car's box size).",
        "source": "docs/reference/TSB_CATALOGUE.md #3",
        "confidence": CONFIRMED,
    },
]

# --- 2. transfer case ---------------------------------------------------------

_spec("transfer_case", "behaviour", "Q4 transfer case behaviour",
      ["transfer_case", "architecture"],
      "rear-biased; 100% rear normally, on-demand up to 60% front via "
      "controlled clutch (not a centre differential)", "",
      source="docs/research/TRANSMISSION_ZF8HP_Q4.md #5", confidence=CONFIRMED)

_spec("transfer_case", "actuator_architecture", "Q4 actuator architecture",
      ["transfer_case", "architecture"],
      "hypothesis: electric-motor-driven ball ramp applying a multi-plate "
      "wet clutch (Magna Active Transfer Case pattern, shared with BMW "
      "xDrive / Jeep Active Drive)", "",
      source="docs/research/TRANSMISSION_ZF8HP_Q4.md #5", confidence=UNKNOWN,
      notes="Resolve via MES DTCM parameter-name read per repo doc's method.")

_spec("transfer_case", "fluid_identity", "Q4 transfer case fluid",
      ["transfer_case", "fluid"],
      "Petronas Tutela Transmission Transfer Case (Q4) -- Tutela "
      "Transmission Hypoide Gear Oil, Synthetic SAE 75W, FIAT approval "
      "9.55550-DA11", "",
      source="docs/research/TRANSMISSION_ZF8HP_Q4.md #5; giuliatech.com "
             "fluid-specs table (independent second source, same FIAT number)",
      confidence=CORROBORATED,
      notes="Do not substitute ATF or generic 75W GL-5; friction "
            "characteristics matched to the clutch pack.")

_spec("transfer_case", "capacity", "Q4 transfer case capacity",
      ["transfer_case", "fluid"],
      "conflicting: ~1 L (repo doc) vs 0.7 L (giuliatech.com)", "L",
      source="docs/research/TRANSMISSION_ZF8HP_Q4.md #5; giuliatech.com",
      confidence=SINGLE_SOURCE,
      notes="Unreconciled -- confirm exact fill quantity at dealer parts "
            "counter by VIN or in TechAuthority before doing the job.")

_spec("transfer_case", "interval", "Q4 transfer case service interval",
      ["transfer_case", "interval"], "80000 mi (128000 km) / 8 years", "",
      source="https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf", confidence=CONFIRMED,
      notes="2018 Stelvio US owner's manual, Maintenance Plan (2.0 T4 MAir), row "
            "'Replace transfer case oil (AWD models only)': one mandatory mark in the "
            "80k mi / 128k km / year-8 column (read from the PDF's column positions, "
            "2026-09-26). This car is past that mileage: due unless already done.")

_spec("transfer_case", "adj_routine", "DTCM ADJ routine", ["transfer_case", "adaptation"],
      "hypothesis: actuator position / clutch-clearance learn, drives to "
      "mechanical end stops and records encoder positions", "",
      source="docs/research/TRANSMISSION_ZF8HP_Q4.md #5", confidence=UNKNOWN,
      notes="Read the MES procedure text before running; do NOT run with "
            "vehicle on the ground or on a single-axle dyno.")

_spec("transfer_case", "torque_split_tuning", "Q4 torque-split calibration availability",
      ["transfer_case", "tuning"],
      "almost certainly not available -- no tool ecosystem lists a Giorgio DTCM", "",
      source="docs/research/TRANSMISSION_ZF8HP_Q4.md #1, #5", confidence=SINGLE_SOURCE)

TRANSFER_CASE_DTCS: list[tuple[str, str]] = [
    ("U0100-87", "Lost Comm with ECM -- observed as a bystander code from "
                 "whole-vehicle serial UDS sweeps on this exact car's own "
                 "scan (SCAN_2609041953), not a real fault"),
    ("U0102", "Lost Communication With Transfer Case Control Module/AWD on "
              "a RWD car -- configuration fault (AWD software on RWD "
              "vehicle) after ECM replace/flash; NOT applicable to a "
              "factory Q4 car, listed for completeness"),
]

# --- 3. differentials ---------------------------------------------------------

_spec("differentials", "front_fluid_identity", "Front differential fluid",
      ["differential", "front", "fluid"],
      "SAE 75W-80, API GL-5, synthetic, FIAT approval 9.55550-DA10", "",
      source="giuliatech.com fluid-specs table", confidence=SINGLE_SOURCE)

_spec("differentials", "front_capacity_20t", "Front differential capacity, 2.0T",
      ["differential", "front", "fluid"], "0.5", "L",
      source="giuliatech.com", confidence=SINGLE_SOURCE)

_spec("differentials", "front_capacity_qv", "Front differential capacity, 2.9 QV (reference only)",
      ["differential", "front", "fluid"], "0.45", "L",
      source="giuliatech.com", confidence=SINGLE_SOURCE,
      notes="Reference only, not this car.")

_spec("differentials", "front_interval", "Front differential service interval",
      ["differential", "front", "interval"],
      "anecdotally lasts to ~100000 km without visible wear", "km",
      source="forum synthesis (giuliaforums.com/stelvioforum.com)",
      confidence=SINGLE_SOURCE, notes="Not an OEM schedule.")

_spec("differentials", "front_lsd_additive", "Front differential LSD additive",
      ["differential", "front", "fluid"],
      "not applicable -- fixed-ratio open unit on 2.0T Q4, no front LSD option found",
      "", confidence=SINGLE_SOURCE,
      notes="Inference from architecture (Q4 clutch does front torque "
            "modulation, not a front LSD).")

_spec("differentials", "rear_fluid_identity_20t",
      "Rear differential fluid, 2.0T variants (195 open / 230-LSD / 210-eLSD)",
      ["differential", "rear", "fluid"],
      "SAE 75W-85, synthetic, FIAT approval 9.55550-DA9", "",
      source="giuliatech.com fluid-specs table", confidence=SINGLE_SOURCE)

_spec("differentials", "rear_fluid_identity_qv",
      "Rear differential fluid, 2.9 QV torque-vectoring 230-TV (reference only)",
      ["differential", "rear", "fluid"],
      "SAE 75W-85, API GL-5, synthetic, FIAT approval 9.55550-DA8", "",
      source="giuliatech.com", confidence=SINGLE_SOURCE,
      notes="Reference only, not this car.")

_spec("differentials", "rear_capacity_20t", "Rear differential capacity, 2.0T variants",
      ["differential", "rear", "fluid"],
      "0.9-1.1 (varies by internal type: 195 / 230-LSD / 210-eLSD)", "L",
      source="giuliatech.com", confidence=SINGLE_SOURCE)

_spec("differentials", "rear_capacity_qv",
      "Rear differential capacity, 2.9 QV TV (reference only)",
      ["differential", "rear", "fluid"],
      "main 0.8 + left TV 0.5 + right TV 0.6 (Giulia) or 0.61-0.68 (Stelvio); "
      "3-chamber unit", "L",
      source="giuliatech.com", confidence=SINGLE_SOURCE, notes="Reference only, not this car.")

_spec("differentials", "rear_interval", "Rear differential service interval",
      ["differential", "rear", "interval"],
      "~50000-60000 (rear wears faster than front per forum guidance)", "km",
      source="forum synthesis", confidence=SINGLE_SOURCE, notes="Not an OEM schedule.")

_spec("differentials", "rear_which_unit_fitted",
      "Rear differential trim/option (which unit is fitted to this VIN)",
      ["differential", "rear", "identification"],
      "depends on trim/options: open 195 / mechanical-LSD 230-LSD / "
      "electronic 210-eLSD; Ti Sport and Q4-package cars most likely carry "
      "the LSD/eLSD unit", "",
      source="user-provided trim context; giuliatech.com option-code naming",
      confidence=UNKNOWN,
      notes="Decode the build sheet / option codes, or confirm at a dealer "
            "parts counter by VIN, before ordering fluid or parts for THIS car.")

_spec("differentials", "rear_lsd_additive", "Rear differential LSD additive (230-LSD unit)",
      ["differential", "rear", "fluid"],
      "not found as a separate additive requirement; unconfirmed whether "
      "the listed fluid is already friction-modified", "",
      confidence=UNKNOWN,
      notes="Do not assume a standard GL-5 is friction-safe for the LSD "
            "unit without checking. " + TECHAUTHORITY)

# --- 4. driveline --------------------------------------------------------------

_spec("driveline", "propshaft_construction", "Propshaft material/construction",
      ["driveline", "identification"],
      "referenced as a carbon-fibre driveshaft on 2017-2025 Giulia/Stelvio "
      "by an aftermarket parts vendor (page body could not be fully retrieved)",
      "", source="go-parts.com garage article (title/metadata only, HTTP 403 on body fetch)",
      confidence=SINGLE_SOURCE,
      notes="Confirm construction (steel vs carbon-fibre, one- vs two-piece "
            "with centre bearing) against the parts catalogue for this VIN "
            "before ordering.")

_spec("driveline", "propshaft_centre_bearing", "Propshaft centre support bearing",
      ["driveline", "identification"], "not confirmed present or absent", "",
      confidence=UNKNOWN)

_spec("driveline", "front_flex_disc", "Front flex disc / coupling",
      ["driveline", "identification"],
      "bolts possibly torque-to-yield, requiring replacement", "",
      source="forum synthesis (alfabb.com)", confidence=SINGLE_SOURCE)

DRIVELINE_ISSUES: list[tuple[str, str]] = [
    ("front flex-disc bolts", "may be torque-to-yield; must be replaced, not reused"),
    ("PTU/stubshaft seal (9004150)", "if replacing the stubshaft for an ATX "
                                     "fluid leak, do NOT also replace the PTU seals"),
    ("no TSB addresses propshaft failure", "explicit finding from the full TSB corpus sweep"),
]

# --- 5. mounts -----------------------------------------------------------------

MOUNTS_ISSUES: list[tuple[str, str]] = [
    ("transmission mount clunk/vibration",
     "referenced as a common complaint by an aftermarket parts vendor's "
     "diagnostic guide for 2017-2025 Giulia/Stelvio/Grecale 2.0L (page body "
     "could not be retrieved, HTTP 403) -- treat as a plausible lead, not a "
     "confirmed failure pattern"),
]


def specs_for_section(section: str) -> list[dict[str, Any]]:
    return [dict(s) for s in SPECS if s["section"] == section]


# ---------------------------------------------------------------------------
# JOBS -- job name -> ordered steps, each with an optional torque checkpoint
# (referencing a TORQUES row's "key").
# ---------------------------------------------------------------------------

JOBS: dict[str, list[dict[str, Any]]] = {
    "transmission_fluid_service": [
        {"step": "Confirm fluid identity: ZF LifeguardFluid 8 / Mopar 68218925AA only, never ATF+4.",
         "torque_ref": None},
        {"step": "Warm to 30-50C fill/level window; on this 4th-gen box, level check requires an OEM scan-tool routine.",
         "torque_ref": None},
        {"step": "Drop pan/filter (integrated assembly, not separately serviceable).",
         "torque_ref": None},
        {"step": "Reinstall pan/filter.", "torque_ref": "transmission_pan_bolts"},
        {"step": "Refill; forum practice overfills ~0.5 L and bleeds back at "
                 "the level-check plug (unverified shop practice, prefer the "
                 "OEM scan-tool fill routine).", "torque_ref": None},
        {"step": "Torque drain/fill plug.", "torque_ref": "transmission_drain_plug"},
        {"step": "Do NOT run an adaptation reset for a routine fluid-and-filter "
                 "change; not required per OEM text.", "torque_ref": None},
        {"step": "Clear DTCs, road test, re-scan; check for TSB 21-035-20 "
                 "before condemning hardware.", "torque_ref": None},
    ],
    "transfer_case_service": [
        {"step": "Confirm fluid: Tutela Transmission Transfer Case (Q4), SAE "
                 "75W, FIAT 9.55550-DA11. Do not substitute ATF or generic "
                 "75W GL-5.", "torque_ref": None},
        {"step": "Capacity is unreconciled (0.7 L vs ~1 L) -- confirm exact "
                 "quantity for this VIN before ordering fluid.", "torque_ref": None},
        {"step": "Torque drain/fill plug.", "torque_ref": "transfer_case_drain_plug"},
        {"step": "Before condemning transfer-case hardware for shudder/bind/"
                 "ratio DTCs, verify tyre circumference match within 1/8\" "
                 "across all four tyres (TSB S1821000001 REV. A).", "torque_ref": None},
        {"step": "If a DTCM ADJ (actuator learn) routine is called for, read "
                 "its MES procedure text first; never run with wheels on the "
                 "ground or on a single-axle dyno.", "torque_ref": None},
    ],
    "differential_service_front": [
        {"step": "Fluid: SAE 75W-80 GL-5 synthetic, FIAT 9.55550-DA10, ~0.5 L.",
         "torque_ref": None},
        {"step": "Torque fill/drain plug.", "torque_ref": "front_diff_fill_plug"},
    ],
    "differential_service_rear": [
        {"step": "Decode this VIN's rear differential type first (195 open / "
                 "230-LSD / 210-eLSD) -- fluid and any LSD-additive "
                 "requirement may differ.", "torque_ref": None},
        {"step": "Fluid: SAE 75W-85 synthetic, FIAT 9.55550-DA9, ~0.9-1.1 L "
                 "depending on internal type.", "torque_ref": None},
        {"step": "Do not assume a generic 75W-85/90 GL-5 is friction-safe for "
                 "a mechanical-LSD rear unit without checking for an LSD "
                 "additive requirement.", "torque_ref": None},
        {"step": "Torque fill/drain plug (26 Nm reported, SINGLE-SOURCE).",
         "torque_ref": "rear_diff_fill_plug"},
    ],
    "axle_propshaft_service": [
        {"step": "Confirm propshaft construction (material, one- vs two-piece, "
                 "centre bearing presence) against the parts catalogue for "
                 "this VIN before ordering.", "torque_ref": None},
        {"step": "Torque propshaft flange/centre-carrier nut (treat as "
                 "unconfirmed pending TechAuthority check).",
         "torque_ref": "propshaft_flange_nut"},
        {"step": "Always fit a NEW front/rear axle (hub) nut -- torque then angle.",
         "torque_ref": "axle_hub_nut"},
        {"step": "Torque hub mounting bolts.", "torque_ref": "hub_mount_bolts"},
        {"step": "If replacing the stubshaft for a fluid leak, do NOT replace "
                 "the PTU seals at the same time.", "torque_ref": None},
        {"step": "Check any flex-disc/coupling bolts for a torque-to-yield "
                 "callout before reusing them.", "torque_ref": None},
        {"step": "After any driveline disassembly on a Q4 car, verify tyre "
                 "circumference match (1/8\") before returning the car.",
         "torque_ref": None},
    ],
    "mount_replacement": [
        {"step": "Torque engine mount bolts to aluminium block.",
         "torque_ref": "engine_mount_bolts"},
        {"step": "Replace and torque longitudinal (dogbone) mount -- mount "
                 "itself is single-use, do not reinstall a removed mount.",
         "torque_ref": "longitudinal_mount_bolts"},
        {"step": "On Q4 cars, confirm exact location of the central M14 bolt "
                 "before relying on the 124-136 Nm figure (ambiguous between "
                 "engine-mount pivot and driveline flange).",
         "torque_ref": "q4_central_m14_bolt_mounts"},
        {"step": "Fit new transmission-mount-bracket fasteners; confirm actual "
                 "torque value in TechAuthority since none was found independently.",
         "torque_ref": "trans_mount_bracket_fasteners"},
        {"step": "Inspect this mount before condemning the transmission or "
                 "driveline on a clunk/vibration complaint.", "torque_ref": None},
    ],
}

# ---------------------------------------------------------------------------
# SECTIONS -- the five self-contained drivetrain areas required by the
# organisation requirement: each holds its own specs, torques and jobs.
# ---------------------------------------------------------------------------

SECTIONS: dict[str, dict[str, Any]] = {
    "transmission": {
        "specs": specs_for_section("transmission"),
        "torques": torques_for_section("transmission"),
        "dtcs": TRANSMISSION_DTCS,
        "tsbs": TRANSMISSION_TSBS,
        "jobs": {"transmission_fluid_service": JOBS["transmission_fluid_service"]},
    },
    "transfer_case": {
        "specs": specs_for_section("transfer_case"),
        "torques": torques_for_section("transfer_case"),
        "dtcs": TRANSFER_CASE_DTCS,
        "jobs": {"transfer_case_service": JOBS["transfer_case_service"]},
    },
    "differentials": {
        "front": {
            "specs": [s for s in specs_for_section("differentials") if "front" in s["categories"]],
            "torques": [t for t in torques_for_section("differentials") if "front" in t["categories"]],
            "jobs": {"differential_service_front": JOBS["differential_service_front"]},
        },
        "rear": {
            "specs": [s for s in specs_for_section("differentials") if "rear" in s["categories"]],
            "torques": [t for t in torques_for_section("differentials") if "rear" in t["categories"]],
            "jobs": {"differential_service_rear": JOBS["differential_service_rear"]},
        },
        "specs": specs_for_section("differentials"),
        "torques": torques_for_section("differentials"),
        "jobs": {
            "differential_service_front": JOBS["differential_service_front"],
            "differential_service_rear": JOBS["differential_service_rear"],
        },
    },
    "driveline": {
        "specs": specs_for_section("driveline"),
        "torques": torques_for_section("driveline"),
        "issues": DRIVELINE_ISSUES,
        "jobs": {"axle_propshaft_service": JOBS["axle_propshaft_service"]},
    },
    "mounts": {
        "specs": specs_for_section("mounts"),
        "torques": torques_for_section("mounts"),
        "issues": MOUNTS_ISSUES,
        "jobs": {"mount_replacement": JOBS["mount_replacement"]},
    },
}


def by_confidence(confidence: str) -> list[dict[str, Any]]:
    """All SPECS/TORQUES rows at a given confidence level, e.g. 'UNKNOWN'."""
    want = confidence.upper()
    return [row for row in SPECS + TORQUES if row["confidence"] == want]


def find(text: str) -> list[dict[str, Any]]:
    """Case-insensitive search across SPECS and TORQUES component names."""
    needle = text.lower()
    return [row for row in SPECS + TORQUES if needle in row["component"].lower()]


__all__ = [
    "CONFIRMED", "CORROBORATED", "SINGLE_SOURCE", "UNKNOWN",
    "CONFIDENCE_LEVELS", "TECHAUTHORITY", "VEHICLE",
    "SPECS", "TORQUES", "JOBS", "SECTIONS",
    "TRANSMISSION_DTCS", "TRANSMISSION_TSBS", "TRANSFER_CASE_DTCS",
    "DRIVELINE_ISSUES", "MOUNTS_ISSUES",
    "torque_by_key", "torques_for_section", "specs_for_section",
    "by_confidence", "find", "nm_to_lbft", "lbft_to_nm",
]
