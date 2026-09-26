"""Reference data: 2018 Alfa Romeo Stelvio 2.0T (US) service specs.

Read-only reference data -- nothing here touches the corpus or the car. It
backs :mod:`mes.service` (the oil-change / general-service / brakes-wheels-
tyres ledger) and cuore's service pages. Every leaf value carries where it
came from and how sure we are of it, because a torque spec a mechanic
trusts wrongly is worse than one plainly marked unknown.

Confidence levels (never invented -- an absent value is recorded as
UNKNOWN, never guessed):

* ``CONFIRMED``     -- an actual manufacturer document (owner's manual,
                       Mopar/FCA parts catalog, FCA/Alfa service
                       information, TechAuthority excerpt).
* ``CORROBORATED``  -- two independent non-manufacturer sources agree.
* ``SINGLE_SOURCE`` -- exactly one source found, not cross-checked.
* ``UNKNOWN``       -- nothing credible found. ``value`` is ``None``, never
                       a placeholder number -- ``notes`` always points at
                       the service manual.

The 2018 Giulia 2.0T shares this car's GME-T4 MultiAir engine (sales code
EC2) and much of its running gear, so a fair amount of this is corroborated
from Giulia-specific sources. Every row that leans on Giulia sourcing says
so in ``platform_note`` -- it is offered as corroboration, not silently
folded in as if it were Stelvio-specific.

Research pass done 2026-09-26 by web search against public sources (Mopar/
FCA parts listings, vehicleinfo.mopar.com, stelvioforum.com,
giuliaforums.com, alfaowner.com, alfabb.com, parts/tool sites) plus this
repo's own ``docs/reference/ZF8HP_SERVICE_DATA.md``, which traces to actual
FCA/Alfa OEM service information for this platform. No paywalled FCA/
Stellantis TechAuthority document was reached directly -- every value that
names TechAuthority as its authority is a pointer to go get it, not a claim
that document was actually read.

See ``docs/reference/STELVIO_20T_SERVICE_SPECS.md`` for the human-readable
writeup with the same data and full source links.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"

CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN)

TECHAUTHORITY = "use the service manual (TechAuthority)"

VEHICLE = ("2018 Alfa Romeo Stelvio 2.0T (GU), 2.0L GME-T4 MultiAir turbo, "
          "sales code EC2, US market, Q4 AWD, ZF 8HP automatic")

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


# --- oil service -------------------------------------------------------------

OIL_SPEC: dict[str, dict[str, Any]] = {
    "viscosity": {
        "value": "0W-30", "unit": None,
        "source": "https://bobistheoilguy.com/forums/threads/alfa-romeo-giulia-oil-fiat-spec-9-55535-gs1.344407/",
        "confidence": CORROBORATED,
        "notes": "0W-30 full synthetic is what the US 2.0T manuals call "
                 "for. Owners report 5W-40 (the Euro 'Selenia' spec "
                 "sharing this engine) is also approved and commonly used "
                 "in warmer climates -- SINGLE-SOURCE for that "
                 "substitution; treat 0W-30 as the primary US spec and "
                 "confirm against the filler-cap/owner's-manual sticker "
                 "on this specific car.",
        "platform_note": "Giulia-sourced; same engine as this Stelvio.",
    },
    "spec_approval": {
        "value": "FCA/Mopar MS-13340, API SN (2017-2018 build); "
                 "historically also cited as Fiat 9.55535-GS1",
        "unit": None,
        "source": "https://www.giuliaforums.com/threads/giulia-2-0l-oil-specifications-sn-versus-sn-plus-and-ms13340.50969/",
        "confidence": CORROBORATED,
        "notes": "Two independent threads (giuliaforums MS-13340 "
                 "discussion, bobistheoilguy 9.55535-GS1 thread) describe "
                 "the same spec: 2017-2018 MY calls for API SN meeting "
                 "MS-13340 / 9.55535-GS1 in 0W-30; 2019+ manuals move to "
                 "SN PLUS. Do NOT use MS-12633 (Pennzoil 0W-40 SN) -- that "
                 "is the Quadrifoglio/SRT-shared V6 spec, not this "
                 "engine's.",
        "platform_note": "Giulia-sourced; same engine as this Stelvio.",
    },
    "capacity_with_filter_qt": {
        "value": 5.5, "unit": "qt", "value_l": 5.2,
        "source": "https://www.amsoil.com/lookup/auto-and-light-truck/2018/alfa-romeo/stelvio/2-0l-4-cyl-engine-code-n-ec2-n-turbo/",
        "confidence": SINGLE_SOURCE,
        "notes": "AMSOIL's VIN/engine-code lookup tool, keyed to this "
                 "exact engine code (N) and sales code (EC2) -- a "
                 "parts-fitment lookup, not a manufacturer document, so "
                 "kept at SINGLE-SOURCE despite being VIN-specific. "
                 "Disregard aggregator pages quoting a wider 5.5-7.4 qt "
                 "range -- that clearly blends the 2.0T and the 2.9L V6 "
                 "into one page.",
        "platform_note": None,
    },
}

OIL_FILTER_PARTS: list[dict[str, Any]] = [
    {"brand": "Mopar", "part_no": "4892339 (suffix revised over "
     "production -- BE / AB / AC seen; reported as 'same filter, revised "
     "part number')",
     "source": "https://www.giuliaforums.com/threads/oil-filter-2-0-part-number-change.49369/",
     "confidence": SINGLE_SOURCE,
     "notes": "The 2.0L-engine cartridge filter. Do NOT use 68191349AA/"
              "AC -- that family is the 3.0L/3.2L/3.6L V6 filter and "
              "appears repeatedly in search noise for this query. Confirm "
              "the exact current suffix against this VIN at a Mopar parts "
              "counter before ordering."},
    {"brand": "(aftermarket cross-reference)", "part_no": None,
     "source": None, "confidence": UNKNOWN,
     "notes": "No confidently-sourced Mann/Bosch/K&N cross-reference for "
              "the 2.0L cartridge filter turned up in this research pass "
              "(a Magneti Marelli OEM-equivalent was mentioned on one "
              "forum without a part number). Cross-reference the Mopar "
              "4892339 number at a parts counter (RockAuto, FCP Euro) "
              "rather than guessing a Mann/Bosch number here."},
]

DRAIN_PLUG = {
    "part_no": None, "source": None, "confidence": UNKNOWN,
    "notes": "No separate drain-plug part number found. One source "
             "(see the drain-plug torque row) describes the 2.0T plug as "
             "having a built-in/captive rubber gasket rather than using a "
             "separate crush washer -- if true, replacing the whole plug "
             "may be the only way to renew the seal. " + TECHAUTHORITY,
}

DRAIN_PLUG_WASHER = {
    "part_no": None, "reusable": None, "source": None, "confidence": UNKNOWN,
    "notes": "See DRAIN_PLUG -- SINGLE-SOURCE reports a captive gasket, "
             "not a separate washer. A washer part number (670050349) is "
             "documented for the Quadrifoglio V6, not the 2.0T -- do not "
             "assume it fits. Confirm plug design either from "
             "TechAuthority or by inspecting the removed plug.",
}

SERVICE_INTERVAL = {
    "miles": 8000, "months": 12,
    "km": round(8000 * 1.60934),
    "source": "https://www.giuliaforums.com/threads/oil-change-frequency.47281/",
    "confidence": CORROBORATED,
    "notes": "8,000 miles / 12 months (whichever comes first) with full "
             "synthetic is the figure repeated across Costa Oil Change "
             "model-year guides and the giuliaforums/stelvioforum 'Oil "
             "Change Frequency' threads for both the Stelvio and Giulia "
             "2.0T. Conventional oil is explicitly NOT approved for this "
             "turbo engine. Owners report shortening to 5,000-6,000 miles "
             "for short-trip/stop-and-go/hard driving. MANUFACTURER LIMIT "
             "(CONFIRMED, 2018 Stelvio US owner's manual, Maintenance Plan "
             "note 3): the interval is set by the dash oil-change indicator "
             "and must never exceed 1 year / 10,000 miles (16,000 km); "
             "severe duty (dusty/off-road, mostly idling or very low RPM) "
             "4,000 miles (6,500 km). The 8,000 mi figure above is the "
             "conservative shop interval, inside the FCA limit.",
    "manufacturer_max": {"miles": 10000, "km": 16000, "months": 12,
                         "severe_duty_miles": 4000, "severe_duty_km": 6500,
                         "confidence": CONFIRMED, "source": "https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf"},
    "oil_life_system": {
        "present": True,
        "behavior": "Algorithmic oil-life / service-due monitor driving "
                    "the cluster reminder, on top of the fixed interval "
                    "above -- described as an onboard oil-degradation "
                    "monitor that can trigger the reminder earlier based "
                    "on actual driving conditions. Treat the fixed "
                    "interval as the floor, the dash reminder as the "
                    "ceiling, whichever comes first.",
        "reset_methods": [
            "MES (MultiEcuScan) -- reported as the fastest/most reliable "
            "method, clears both the cluster reminder and day/mile "
            "counter in seconds.",
            "wiTECH (dealer tool) -- IPC module, Misc Functions, "
            "Maintenance Reset, follow prompts.",
            "Accelerator-pedal method (no tool) -- ignition on/engine "
            "off, fully depress and release the accelerator pedal slowly "
            "3 times (some cluster software revisions reportedly need "
            "4-6 pumps), 1 second apart, then start the engine. "
            "Unofficial and reported inconsistent across software "
            "revisions.",
        ],
        "source": "https://www.stelvioforum.com/threads/alfa-romeo-stelvio-giulia-oil-change-maintenance-reset.19336/",
        "confidence": SINGLE_SOURCE,
    },
}


# --- torque library ----------------------------------------------------------
#
# One row per fastener/job. ``categories`` lets one fastener appear on more
# than one job's checklist (the wheel lug bolt matters to "oil_change" --
# because a tech often rotates tyres at the same visit -- as well as
# "wheels" and both brake categories).

TORQUES: list[dict[str, Any]] = []


def _torque(key: str, component: str, categories: Iterable[str],
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


# oil change / wheels ---------------------------------------------------------
_torque("drain_plug", "Oil drain plug", ["oil_change"], 20, "Nm",
        source="https://www.stelvioforum.com/threads/oil-drain-bolt-torque-for-the-2-0t-multiair-280-bhp-engine.12917/",
        confidence=SINGLE_SOURCE,
        notes="Reported for the 2.0T MultiAir drain plug, described by "
              "this source as having a built-in rubber gasket. Low torque "
              "for a drain plug -- easy to overtighten past this into the "
              "pan threads; use a torque wrench, not feel.")

_torque("filter_cap", "Oil filter housing cap (cartridge filter)",
        ["oil_change"], 25, "Nm",
        source="https://www.alfaowner.com/threads/multiair-oil-filter-torque-setting.1116586/",
        confidence=SINGLE_SOURCE,
        notes="This engine uses a cartridge filter under a screw-on "
              "plastic housing cap with its own O-ring, not a spin-on "
              "canister. Do not overtighten -- the housing is plastic.",
        platform_note="Giulia-sourced (2016 MY reference in the thread).")

_torque("wheel_lug", "Wheel lug bolts",
        ["oil_change", "wheels", "brakes_front", "brakes_rear",
         "wheel_bearing"],
        121, "Nm", value_range=(120.7, 122.0),
        source="https://www.alfaowner.com/threads/wheel-bolt-torque-settings.1071610/",
        confidence=CORROBORATED,
        notes="Bolts threaded into the hub, NOT nuts on studs -- "
              "confirmed by all sources. Two independent threads "
              "(alfaowner 'Wheel bolt torque settings', stelvioforum "
              "'Stelvio Veloce wheel bolt torque setting') land at "
              "89-90 ft-lb (~121-122 Nm); use that. A third alfaowner "
              "thread reports 110 Nm/81 ft-lb for '14mm bolts', possibly "
              "a different bolt/thread size on a different wheel option "
              "-- confirm which bolt is fitted before trusting either "
              "figure; this is a safety-critical fastener. Torque in a "
              "star/cross pattern, snug then final torque.")

_torque("spark_plug", "Spark plugs", ["oil_change", "spark_plugs"],
        19.5, "Nm", value_range=(19, 20),
        source="https://www.giuliaforums.com/threads/inconsistent-spark-plug-torque-specs-2-0l.64916/",
        confidence=CORROBORATED,
        notes="Two figures close enough to treat as agreeing within "
              "rounding: ~20 Nm and 168 in-lb/14 ft-lb (~19 Nm). The "
              "thread's own title ('Inconsistent spark plug torque specs "
              "2.0L') flags that published specs vary by source/year -- "
              "do not stack this with anti-seize unless the plug maker "
              "calls for it; seat torque affects thread depth into the "
              "aluminum head on this engine.",
        platform_note="Giulia-sourced; same engine as this Stelvio.")

_torque("undertray", "Undertray / belly-pan / splash-shield fasteners",
        ["oil_change", "undertray"], None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque spec found. Typically plastic push-pin/"
              "screw retainers with no meaningful torque value (hand-"
              "tight); any metal bolts holding structural shield brackets "
              "should follow TechAuthority.")

# brakes -----------------------------------------------------------------
_torque("caliper_slider_front", "Brake caliper guide/slide pin bolt, front",
        ["brakes_front"], 30, "Nm",
        source="https://www.giuliaforums.com/threads/brake-guide-bolt-torque-spec.52844/",
        confidence=CORROBORATED,
        notes="Reported consistently (~22 ft-lb / 30 Nm) for the single "
              "guide-pin bolt (between the alignment pins) on Brembo-"
              "fitted cars. Apply medium-strength (blue) threadlocker per "
              "source -- reusable bolt, but refresh threadlocker each "
              "time it's disturbed.",
        platform_note="Giulia-sourced, Brembo-fitted cars.")

_torque("caliper_bracket_front", "Brake caliper bracket/carrier-to-knuckle "
                                  "bolt, front", ["brakes_front"],
        None, "Nm", confidence=UNKNOWN,
        notes="Conflicting forum reports: one 2018 2.0L thread settled on "
              "~57 ft-lb (~77 Nm) with threadlocker after testing 55 then "
              "60 ft-lb by feel; a separate thread quotes 77 ft-lb "
              "(~104 Nm) outright. These do not agree closely enough to "
              "treat as corroborating, and neither traces to a "
              "manufacturer document -- do not pick one. " + TECHAUTHORITY
              + "; this bolt clamps the whole caliper assembly to the "
                "knuckle.")

_torque("caliper_slider_rear", "Brake caliper guide/slide pin bolt, rear",
        ["brakes_rear"], 27, "Nm", value_range=(26, 28),
        source="https://www.giuliaforums.com/threads/2018-2-0l-caliper-bolt-torque.58102/",
        confidence=SINGLE_SOURCE,
        notes="From one 2018 2.0L thread (~20 ft-lb / 27 Nm), read via a "
              "search-engine summary only -- the full thread was behind a "
              "paywall during this research pass, so treat as "
              "lower-confidence than a normal SINGLE-SOURCE. It is also "
              "unclear whether this figure is the guide pin, the bracket "
              "bolt, or both -- confirm which fastener it covers. Rear "
              "caliper also carries the electric parking brake actuator: "
              "put the EPB into service mode before loosening (see "
              "BRAKE_SPEC['epb_service_mode']).",
        platform_note="Giulia-sourced.")

_torque("caliper_bracket_rear", "Brake caliper bracket/carrier-to-knuckle "
                                 "bolt, rear", ["brakes_rear"],
        None, "Nm", confidence=UNKNOWN,
        notes="Not distinguished from the rear guide-pin figure in any "
              "source found. " + TECHAUTHORITY)

_torque("rotor_retaining_screw", "Rotor retaining screw",
        ["brakes_front", "brakes_rear"], None, "Nm", confidence=UNKNOWN,
        notes="Confirmed as an M10 x 1.25 thread (~16.4mm length) from "
              "parts listings, but no torque value found. These screws "
              "are low-torque and easy to snap/strip -- do not guess; "
              "use TechAuthority.")

# ignition ------------------------------------------------------------------
_torque("coil_pack_bolt", "Ignition coil pack retaining bolt/screw",
        ["spark_plugs", "coils"], None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque value found.")

# EVAP ------------------------------------------------------------------
_torque("evap_canister_mount", "EVAP canister / ESIM mounting bolts",
        ["evap"], None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque value found. Forum how-tos describe "
              "removing 'the bolts holding the canister in' without "
              "giving a spec. Directly relevant to the current EVAP "
              "(P0440/P0455/P0456) diagnosis on this VIN.")

_torque("evap_esim_mount", "EVAP ESIM / leak-detection pump mounting "
                            "fasteners", ["evap"], None, "Nm",
        confidence=UNKNOWN,
        notes="Not distinguished from the canister mounting bolts in any "
              "source found. " + TECHAUTHORITY)

_torque("evap_purge_valve_mount", "EVAP purge valve/solenoid mounting "
                                   "bracket bolt", ["evap"],
        None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque value found.")

# electrical / battery ------------------------------------------------------
_torque("battery_terminal", "Battery terminal clamp bolts", ["battery"],
        None, "Nm", confidence=UNKNOWN,
        notes="No vehicle-specific value found. Do not substitute a "
              "generic terminal-bolt range -- confirm against "
              "TechAuthority; overtightening cracks the terminal post.")

_torque("battery_hold_down", "Battery hold-down clamp bolt", ["battery"],
        None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque value found.")

# suspension ------------------------------------------------------------------
_torque("sway_bar_link_front", "Sway bar (stabilizer) end link nut, front",
        ["suspension"], None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque value found.")

_torque("sway_bar_link_rear", "Sway bar (stabilizer) end link nut, rear",
        ["suspension"], None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque value found.")

_torque("tie_rod_end", "Tie rod end nut", ["suspension"],
        92.5, "Nm", value_range=(90, 95),
        source="https://www.alfabb.com/threads/steering-tie-rod-torque-specs.179364/",
        confidence=SINGLE_SOURCE,
        notes="Source thread title references the INNER tie rod (to the "
              "steering rack), which may not be the same joint as the "
              "OUTER tie rod end (to the knuckle) a suspension job "
              "usually disturbs -- confirm which joint this covers. If a "
              "castellated nut with a cotter pin, torque to the low end "
              "of the range and continue to the next pin slot rather "
              "than backing off.")

_torque("upper_control_arm", "Upper control arm to knuckle bolt",
        ["suspension"], None, "Nm", confidence=UNKNOWN,
        notes="No sourced value. Fact-check 2026-09-26: the 51 Nm previously listed was "
              "attributed to a go-parts.com article that publishes no torque figure (it "
              "says specs must come from the factory service manual). " + TECHAUTHORITY)

_torque("strut_to_lca", "Front strut to lower control arm bolt",
        ["suspension"], None, "Nm", single_use=True, confidence=UNKNOWN,
        notes="No sourced value. Fact-check 2026-09-26: the '60 Nm + 135 deg' previously "
              "listed was attributed to a go-parts.com article that contains no torque "
              "spec; it must not be used on this structural bolt. Treat the bolt as "
              "single-use until the service manual says otherwise. " + TECHAUTHORITY)

_torque("lower_control_arm_knuckle", "Lower control arm to knuckle bolt",
        ["suspension"], None, "Nm", confidence=UNKNOWN,
        notes="Not distinguished from the strut-to-LCA bolt in any source "
              "found; the underlying search summary explicitly states "
              "verified Giulia/Stelvio torque specs here are not readily "
              "public. " + TECHAUTHORITY)

_torque("lower_control_arm_subframe", "Lower control arm to subframe bolt",
        ["suspension"], None, "Nm", confidence=UNKNOWN,
        notes="No sourced torque value found. Many platforms specify "
              "this bolt be torqued at curb/ride height (suspension "
              "loaded) rather than on a lift -- confirm procedure before "
              "assuming a lift torque is valid.")

_torque("wheel_bearing_hub_nut", "Wheel bearing/hub retaining nut or bolts",
        ["wheel_bearing"], None, "Nm", confidence=UNKNOWN, single_use=True,
        notes="No sourced torque value found. Hub nuts on many AWD "
              "platforms are single-use, high (200+ Nm) torque-to-yield "
              "fasteners -- treat as single-use until confirmed "
              "otherwise. " + TECHAUTHORITY)

# driveline (ZF 8HP, transfer case, differential) ----------------------------
_torque("transmission_pan_bolts", "ZF 8HP transmission pan/filter "
                                   "assembly bolts (13x)", ["transmission"],
        10, "Nm",
        source="docs/reference/ZF8HP_SERVICE_DATA.md",
        confidence=CONFIRMED,
        notes="From this repo's own ZF8HP_SERVICE_DATA.md, sourced to "
              "FCA/Alfa OEM service information for this exact vehicle "
              "(ZF doc 1087.754.107c + FCA text): 13 bolts at 10 N*m "
              "(89 in-lb). Pan and filter are one integrated, non-"
              "separately-serviceable assembly; the pan gasket is "
              "reusable if undamaged. This is the PAN bolt torque, not "
              "the drain/fill plug below.")

_torque("transmission_drain_plug", "ZF 8HP transmission fluid drain plug",
        ["transmission"], None, "Nm", confidence=UNKNOWN,
        notes="Not found. The ZF 8HP pan/filter is an integrated "
              "assembly with no conventional dipstick service; a "
              "separate drain plug (if this pan variant has one) was not "
              "identified in this research pass -- see "
              "transmission_pan_bolts above for the related, confirmed "
              "spec. " + TECHAUTHORITY)

_torque("transmission_fill_plug", "ZF 8HP transmission fluid fill/level "
                                   "plug", ["transmission"],
        None, "Nm", confidence=UNKNOWN,
        notes="Not found. ZF 8HP fill is a temperature-controlled "
              "level-plug procedure (fluid must be 30-50 C at the fill "
              "hole per FCA/ZF service info in "
              "docs/reference/ZF8HP_SERVICE_DATA.md), not a simple "
              "fill-to-plug -- see that document for the procedure. "
              + TECHAUTHORITY)

_torque("transfer_case_drain_plug", "Transfer case (Q4 power transfer "
                                     "unit) drain plug", ["transfer_case"],
        None, "Nm", confidence=UNKNOWN,
        notes="A stelvioforum thread asking this exact question cites "
              "the rear differential's 26 Nm as known but leaves the "
              "transfer case as an open question for the poster -- this "
              "is an unresolved question in the community, not a settled "
              "value. Do not assume 'probably the same as the diff' -- "
              "that is speculation, not a source.")

_torque("transfer_case_fill_plug", "Transfer case (Q4 power transfer "
                                    "unit) fill plug", ["transfer_case"],
        None, "Nm", confidence=UNKNOWN,
        notes="Same as transfer_case_drain_plug -- open question, not "
              "sourced.")

_torque("rear_diff_drain_plug", "Rear differential (rear axle) drain plug",
        ["differential"], 26, "Nm",
        source="https://www.stelvioforum.com/threads/transfer-case-drain-fill-plug-torque-specs.24693/",
        confidence=SINGLE_SOURCE,
        notes="Stated as known/given by the original poster in a thread "
              "actually asking about the transfer case (see "
              "transfer_case_drain_plug); not independently corroborated "
              "elsewhere in this research pass.")

_torque("rear_diff_fill_plug", "Rear differential (rear axle) fill plug",
        ["differential"], 26, "Nm",
        source="https://www.stelvioforum.com/threads/transfer-case-drain-fill-plug-torque-specs.24693/",
        confidence=SINGLE_SOURCE,
        notes="Same source as rear_diff_drain_plug; drain and fill plugs "
              "are commonly the same fastener spec on this style of axle "
              "but that has not been independently confirmed as true "
              "here.")


# Safety net, not a per-row habit to maintain by hand: every UNKNOWN torque
# row must point at TechAuthority (the module's own stated invariant, see the
# docstring), even one written with a specific enough ``notes`` string that
# the author forgot to say so explicitly. Idempotent -- running this twice
# does not double up the pointer.
for _row in TORQUES:
    if _row["confidence"] == UNKNOWN and TECHAUTHORITY not in (_row.get("notes") or ""):
        _row["notes"] = (_row["notes"] + " " if _row["notes"] else "") + TECHAUTHORITY
del _row


CATEGORIES: tuple[str, ...] = (
    "oil_change", "wheels", "brakes_front", "brakes_rear", "spark_plugs",
    "coils", "evap", "undertray", "battery", "suspension", "transmission",
    "transfer_case", "differential", "wheel_bearing",
)

CATEGORY_LABELS: dict[str, str] = {
    "oil_change": "Oil change",
    "wheels": "Wheels / tyres",
    "brakes_front": "Brakes, front",
    "brakes_rear": "Brakes, rear",
    "spark_plugs": "Spark plugs",
    "coils": "Ignition coils",
    "evap": "EVAP system",
    "undertray": "Undertray / splash shields",
    "battery": "Battery",
    "suspension": "Suspension",
    "transmission": "Transmission (ZF 8HP)",
    "transfer_case": "Transfer case (Q4)",
    "differential": "Rear differential",
    "wheel_bearing": "Wheel bearing / hub",
}


def torques_for_category(category: str) -> list[dict[str, Any]]:
    """Every torque row tagged with ``category``, in table order."""
    return [dict(t) for t in TORQUES if category in t["categories"]]


def torques_for_categories(categories: Iterable[str]) -> list[dict[str, Any]]:
    """Union of :func:`torques_for_category` over several categories,
    de-duplicated by key, in first-seen order."""
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for cat in categories:
        for row in torques_for_category(cat):
            if row["key"] in seen:
                continue
            seen.add(row["key"])
            out.append(row)
    return out


def checklist_for(categories: Any) -> list[dict[str, Any]]:
    """``torques_for_category``/``torques_for_categories`` unified: accepts
    either a single category string or an iterable of them."""
    if isinstance(categories, str):
        return torques_for_category(categories)
    return torques_for_categories(categories)


def search_torques(q: str = "", category: str = "") -> list[dict[str, Any]]:
    """Torque rows matching a free-text query and/or a category filter.

    Backs the searchable ``/v/{vin}/torque`` page and its JSON mirror.
    UNKNOWN rows are never excluded -- the point of the page is that a
    missing spec stays visible with a TechAuthority pointer, not that it
    disappears.
    """
    q = (q or "").strip().lower()
    category = (category or "").strip()
    rows = torques_for_category(category) if category else [dict(t) for t in TORQUES]
    if not q:
        return rows
    out = []
    for row in rows:
        haystack = " ".join([
            row.get("component", ""), row.get("notes", "") or "",
            " ".join(row.get("categories", ())),
            row.get("platform_note") or "",
        ]).lower()
        if q in haystack:
            out.append(row)
    return out


def torque_by_key(key: str) -> Optional[dict[str, Any]]:
    for t in TORQUES:
        if t["key"] == key:
            return dict(t)
    return None


# alias kept for callers that think in terms of a single lookup-by-id
get_torque = torque_by_key


# --- brakes / wheels / tyres -------------------------------------------------

BRAKE_SPEC: dict[str, dict[str, Any]] = {
    "pad_min_mm": {
        "front": {"value": None, "source": None, "confidence": UNKNOWN,
                  "notes": "No FCA-specific minimum pad thickness found; "
                           "forum chatter cites a generic industry "
                           "rule-of-thumb (~2-3 mm), not a manufacturer "
                           "spec. This car also has an electronic "
                           "pad-wear sensor on the inner pad. "
                           + TECHAUTHORITY},
        "rear": {"value": None, "source": None, "confidence": UNKNOWN,
                 "notes": "Same as front -- no sourced FCA figure. "
                          + TECHAUTHORITY},
    },
    "rotor_new_mm": {
        "front": {"value": 28, "diameter_mm": 330, "source":
                  "https://www.go-parts.com/garage/disc-brake-rotor-alfa-romeo-giulia-alfa-romeo-stelvio-2018-2025",
                  "confidence": SINGLE_SOURCE,
                  "notes": "Aftermarket parts-site aggregation, not a "
                           "manufacturer document."},
        "rear": {"value": 22, "diameter_mm": 320, "source":
                 "https://www.go-parts.com/garage/disc-brake-rotor-alfa-romeo-giulia-alfa-romeo-stelvio-2018-2025",
                 "confidence": SINGLE_SOURCE,
                 "notes": "Same source as front."},
    },
    "rotor_min_mm": {
        "front": {"value": 25.5, "source": "https://www.go-parts.com/garage/disc-brake-rotor-alfa-romeo-giulia-alfa-romeo-stelvio-2018-2025",
                  "confidence": SINGLE_SOURCE,
                  "notes": "Discard/minimum-machining thickness; single "
                           "aftermarket-aggregator source, not "
                           "cross-checked. The rotor's own cast-in "
                           "'MIN TH' marking is the most reliable check "
                           "on the actual part."},
        "rear": {"value": None, "source": None, "confidence": UNKNOWN,
                 "notes": "No widely-published rear minimum found -- the "
                          "source that gave the front figure explicitly "
                          "says so. Read the cast-in MIN TH marking off "
                          "the physical rotor. " + TECHAUTHORITY},
    },
    "rotor_runout_max_mm": {
        "value": None, "source": None, "confidence": UNKNOWN,
        "notes": "Not found in this research pass. " + TECHAUTHORITY,
    },
    "fluid_spec": {
        "value": "DOT 4", "source": "forum consensus (stelvioforum, alfabb, giuliaforums); no "
                                   "FCA document located", "confidence": SINGLE_SOURCE,
        "notes": "Forum consensus across stelvioforum/alfabb/giuliaforums "
                 "threads; no Mopar/FCA document located specifying this "
                 "explicitly for this VIN -- confirm against the "
                 "reservoir cap markings on this specific car. FCA has "
                 "specified DOT 4 Low Viscosity on some contemporaneous "
                 "EPB-equipped platforms, which is not necessarily "
                 "interchangeable with plain DOT 4 even though both meet "
                 "the DOT 4 boiling-point floor.",
    },
    "fluid_change_interval": {
        "miles": None, "months": 24, "source": "https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf",
        "confidence": CONFIRMED,
        "notes": "2018 Stelvio US owner's manual, Maintenance Plan note 6: "
                 "'The brake fluid replacement has to be done every two "
                 "years, irrespective of the mileage.' (Corrected "
                 "2026-09-26; previously listed as a forum rule of thumb.)",
    },
    "oe_tire_size": {
        "base_18in": {"value": "235/60R18", "source": "wheel-size.com; tiresize.com",
                      "confidence": CORROBORATED,
                      "notes": "Multiple independent tyre-fitment "
                               "databases (wheel-size.com, tiresize.com) "
                               "agree. Read this VIN's actual fitment off "
                               "the door-jamb placard rather than "
                               "assuming from trim level."},
        "ti_19in": {"value": "235/55R19, load/speed index 101V",
                    "source": "wheel-size.com; tiresize.com", "confidence": CORROBORATED,
                    "notes": "Ti/19-inch-wheel option. A staggered "
                             "front/rear fitment applies to the "
                             "Quadrifoglio, not the base 2.0T -- confirm "
                             "this VIN's actual wheel/tyre fitment before "
                             "assuming a square (rotatable) set."},
    },
    "tire_pressure_kpa": {
        "front": {"value": 207, "psi": 30, "source": "HaynesPro-sourced aggregator, 19-inch "
                                                       "fitment only; not re-findable",
                  "confidence": SINGLE_SOURCE,
                  "notes": "Reported for the 19-inch fitment "
                           "(HaynesPro-sourced aggregator); the official "
                           "Mopar owner's-manual placard PDF found during "
                           "research was image-based with no extractable "
                           "text, so this could not be confirmed directly "
                           "against the manufacturer document. READ THE "
                           "ACTUAL DOOR-JAMB PLACARD on this VIN -- "
                           "pressure varies by wheel/tyre option and "
                           "load, and no reliable figure was found for "
                           "the 18-inch base fitment specifically."},
        "rear": {"value": 228, "psi": 33, "source": "HaynesPro-sourced aggregator, 19-inch "
                                                      "fitment only; not re-findable",
                 "confidence": SINGLE_SOURCE,
                 "notes": "Same caveat as front."},
    },
    "rotation_pattern": {
        "value": "Base 2.0T (square, non-staggered 18in or 19in Ti "
                 "fitment): standard front-to-rear rotation. Staggered "
                 "fitments (Quadrifoglio and any car actually fitted with "
                 "different front/rear sizes): DO NOT ROTATE.",
        "source": "inferred from tyre-fitment databases; no FCA rotation guidance located",
        "confidence": SINGLE_SOURCE,
        "notes": "Inferred from consistent single-tyre-size listings "
                 "across fitment databases for the base 2.0T -- no "
                 "explicit FCA rotation-pattern statement found. Confirm "
                 "this VIN's actual fitment (matching vs. staggered) "
                 "before rotating.",
    },
    "epb_service_mode": {
        "present": True,
        "note": "Rear brakes use an electric parking brake (EPB) with a "
                "motorized caliper piston. Reported procedure: "
                "infotainment Settings > Passive Safety > Brake Service "
                "Mode, ignition on/engine off, in Park with the foot "
                "brake released; the screen confirms once the actuators "
                "retract. No wiTECH/scan tool is reported as required for "
                "a routine pad change via this menu path; MultiEcuScan's "
                "own coverage of an equivalent routine was not confirmed "
                "in this research pass. Never force the rear piston back "
                "mechanically without service mode active -- it can strip "
                "the actuator's gears/spindle. Press pistons straight "
                "back (do not rotate -- tears the seal); if the battery "
                "is disconnected while the caliper is off, pump the "
                "brake pedal before reconnecting to avoid setting fault "
                "codes.",
        "source": "https://www.servicereset.net/",
        "confidence": SINGLE_SOURCE,
    },
}

TPMS_DIDS = {
    "module": "RFHUB",
    "dids": {"FL": 0x40B1, "FR": 0x40B2, "RL": 0x40B3, "RR": 0x40B4},
    "note": "Live TPMS pressure/temperature can be read from the RFHUB "
            "over UDS at DIDs 40B1-40B4 (one per corner); see "
            "cuore/live/addressing.py and cuore/live/did_catalog.py. This "
            "module only documents the mapping -- it performs no live "
            "reads itself; the brakes/wheels/tyres page shows the latest "
            "matching observation from mes.live_obs, read-only, if one "
            "exists.",
}


def oil_change_specs() -> dict[str, Any]:
    """Everything the oil-change checklist needs, bundled with sources."""
    return {
        "oil": OIL_SPEC,
        "filters": OIL_FILTER_PARTS,
        "drain_plug": DRAIN_PLUG,
        "drain_plug_washer": DRAIN_PLUG_WASHER,
        "interval": SERVICE_INTERVAL,
        "torques": torques_for_category("oil_change"),
    }


def brake_wheel_tire_specs() -> dict[str, Any]:
    """Everything the brakes/wheels/tyres checklist needs, with sources."""
    return {
        "brake": BRAKE_SPEC,
        "tpms": TPMS_DIDS,
        "torques": torques_for_categories(["brakes_front", "brakes_rear",
                                           "wheels", "wheel_bearing"]),
    }


__all__ = [
    "CONFIRMED", "CORROBORATED", "SINGLE_SOURCE", "UNKNOWN",
    "CONFIDENCE_LEVELS", "TECHAUTHORITY", "VEHICLE", "OIL_SPEC",
    "OIL_FILTER_PARTS", "DRAIN_PLUG", "DRAIN_PLUG_WASHER",
    "SERVICE_INTERVAL", "TORQUES", "CATEGORIES", "CATEGORY_LABELS",
    "BRAKE_SPEC", "TPMS_DIDS", "torques_for_category",
    "torques_for_categories", "checklist_for", "search_torques",
    "torque_by_key", "get_torque", "oil_change_specs",
    "brake_wheel_tire_specs", "nm_to_lbft", "lbft_to_nm",
]
