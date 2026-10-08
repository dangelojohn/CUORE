"""Reference data: which tools a job/step actually needs, and why.

Read-only reference data -- nothing here touches the corpus or the car. It
is the tools counterpart to :mod:`mes.service_specs` (torques) and
:mod:`mes.maintenance_specs` (parts/fluid/intervals): a mechanic opening a
job should see *what to bring to the car* before he starts, not just what
fastener spec to use once a wrench is already in hand.

House rule, same as ``mes.service_specs``/``mes.maintenance_specs``: never
invent a size or a specialist tool number. A tool whose spec is not actually
sourced carries ``confidence=UNKNOWN`` and a ``spec`` of ``None`` --
:func:`recommend` always renders that as "UNKNOWN -- confirm on the car /
service manual (TechAuthority)", never a guessed number. Where a size *is*
sourced, it is sourced exactly once, in :mod:`mes.service_specs`'s
``TORQUES`` table -- this module points at that table by ``torque_keys``
rather than re-typing a number that could then drift out of sync.

Two tables:

* ``TOOLS``     -- keyed by tool key: ``{name, kind, spec, why, source,
                   confidence}``. ``kind`` is one of hand | torque |
                   special | diagnostic | lift | consumable.
* ``JOB_TOOLS`` -- keyed by job/step key: a list of ``{tool, required,
                   alternatives, note}`` rows, in the order a mechanic
                   would actually reach for them.

:func:`recommend` is the one public read: resolve a job/step key (or an
EVAP-style family prefix covering several step keys at once) into tool rows
with ``TOOLS`` merged in and any referenced torque spec resolved live from
``mes.service_specs`` -- never duplicated here as a bare number.
"""

from __future__ import annotations

from typing import Any, Optional

from .service_specs import TECHAUTHORITY, torque_by_key

KINDS: tuple[str, ...] = ("hand", "torque", "special", "diagnostic", "lift", "consumable")

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"
CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN)


def _tool(key: str, name: str, kind: str, *, spec: Optional[str] = None,
          why: str = "", source: Optional[str] = None,
          confidence: str = UNKNOWN) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"bad kind {kind!r}")
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r}")
    if spec is None and confidence == UNKNOWN:
        spec = "UNKNOWN -- confirm on the car / service manual (TechAuthority)"
    return {"key": key, "name": name, "kind": kind, "spec": spec, "why": why.strip(),
            "source": source, "confidence": confidence}


# --- the tool catalogue ------------------------------------------------------

TOOLS: dict[str, dict[str, Any]] = {t["key"]: t for t in [
    _tool("ratchet_metric_set", "Metric ratchet + socket set (1/4\"-1/2\" drive)", "hand",
          spec="6-19mm sockets cover nearly everything on this car",
          why="General fastener removal across every job below.",
          confidence=CORROBORATED),
    _tool("torque_wrench_small", "Torque wrench, small (click-type, ~5-60 Nm)", "torque",
          spec="5-60 Nm range",
          why="Low-torque fasteners where overtightening damages soft threads or "
              "plastic housings -- drain plug, filter cap, spark plugs.",
          confidence=CORROBORATED),
    _tool("torque_wrench_large", "Torque wrench, large (click-type, ~40-200 Nm)", "torque",
          spec="40-200 Nm range",
          why="Higher-torque fasteners -- wheel lug bolts, caliper bracket bolts.",
          confidence=CORROBORATED),
    _tool("torque_angle_gauge", "Torque angle gauge", "torque",
          why="Any fastener specced as torque-plus-angle rather than torque alone.",
          confidence=UNKNOWN),
    _tool("oil_filter_housing_wrench", "Oil filter housing cap wrench/socket", "special",
          why="This engine's cartridge filter sits under a screw-on plastic "
              "housing cap -- a strap wrench round the cap damages it; use the "
              "correct cap socket.",
          source="https://www.alfaowner.com/threads/multiair-oil-filter-torque-setting.1116586/",
          confidence=SINGLE_SOURCE),
    _tool("oil_drain_pan", "Drain pan (low-profile, >=6 L)", "consumable",
          why="Catches the ~4.25-4.5 L of 0W-30 full synthetic this engine takes.",
          confidence=CORROBORATED),
    _tool("floor_jack", "Floor jack, rated for the car's weight", "lift",
          why="Lifting for anything done from under the car.", confidence=CORROBORATED),
    _tool("jack_stands", "Jack stands (pair, rated)", "lift",
          why="Never work under a car on a jack alone.", confidence=CORROBORATED),
    _tool("wheel_chocks", "Wheel chocks", "lift",
          why="Blocks the wheels staying on the ground before jacking.",
          confidence=CORROBORATED),
    _tool("impact_wrench", "Impact wrench (or breaker bar)", "hand",
          why="Breaking loose wheel lug bolts and other high-torque fasteners "
              "before final torque with a torque wrench -- never to final-tighten.",
          confidence=CORROBORATED),
    _tool("spark_plug_socket", "Spark plug socket (thin-wall, w/ rubber insert)", "special",
          spec="UNKNOWN exact size -- confirm on the car / service manual (TechAuthority)",
          why="Pulling/seating the plugs without cracking the porcelain.",
          confidence=UNKNOWN),
    _tool("ignition_coil_puller", "Ignition coil puller tool", "special",
          why="Coils can seize onto the plug tube; a puller avoids levering "
              "against the cam cover.",
          confidence=UNKNOWN),
    _tool("trim_clip_tool", "Plastic trim/clip removal tool", "hand",
          why="Air filter box and undertray push-pin retainers -- a screwdriver "
              "breaks these.", confidence=CORROBORATED),
    _tool("serpentine_belt_tool", "Serpentine belt tensioner tool (18mm wrench or dedicated tool)", "special",
          spec="UNKNOWN exact drive/size -- confirm on the car / service manual (TechAuthority)",
          why="Relieving tensioner spring load to route the new belt.",
          confidence=UNKNOWN),
    _tool("battery_terminal_tool", "Battery terminal puller + wire brush", "hand",
          why="Corrosion on 12V terminals is a common no-start cause; clean "
              "contact matters more than torque here.", confidence=CORROBORATED),
    _tool("battery_tester", "Battery/charging-system tester", "diagnostic",
          why="Confirms the battery itself vs. a charging-system fault before "
              "replacing a battery that was never the problem.",
          confidence=CORROBORATED),
    _tool("hand_vacuum_pump", "Hand-held vacuum pump (Mityvac-style, w/ gauge)", "special",
          why="ESIM Test A -- pulls vacuum on the EVAP system and watches decay "
              "to find a leak the smoke test alone won't localize.",
          confidence=CORROBORATED),
    _tool("smoke_machine", "EVAP smoke machine", "special",
          why="Injects visible smoke under light pressure into the EVAP system "
              "to see a leak directly rather than inferring one.",
          confidence=CORROBORATED),
    _tool("quick_connect_tool", "Fuel-line quick-connect release tool set", "special",
          spec="UNKNOWN exact size/profile -- confirm on the car / service manual (TechAuthority)",
          why="EVAP/fuel quick-connect fittings use a collar release that a "
              "flat-blade screwdriver can damage or fail to release cleanly.",
          confidence=UNKNOWN),
    _tool("dvom", "Digital volt-ohm meter (DVOM)", "diagnostic",
          why="Electrical inspection -- voltage, resistance, continuity readings "
              "a scan tool alone can't give.", confidence=CORROBORATED),
    _tool("back_probe_set", "Back-probe pin set", "diagnostic",
          why="Reads a live connector's signal without unplugging it or piercing "
              "insulation.", confidence=CORROBORATED),
    _tool("flare_nut_wrench_set", "Flare-nut (line) wrench set, metric", "hand",
          spec="UNKNOWN exact sizes -- confirm on the car / service manual (TechAuthority)",
          why="Turbo oil feed/return and coolant line fittings -- a flare-nut "
              "wrench grips more of the fitting than an open-end, reducing the "
              "risk of rounding it off.",
          confidence=UNKNOWN),
    _tool("crowfoot_flare_set", "Crowfoot flare-nut set (for a torque wrench)", "special",
          spec="UNKNOWN exact sizes -- confirm on the car / service manual (TechAuthority)",
          why="Torquing a line fitting in a tight space a standard flare-nut "
              "wrench can't swing in, without losing torque accuracy.",
          confidence=UNKNOWN),
    _tool("zf8hp_fill_adapter", "ZF 8HP transmission fill adapter", "special",
          why="The ZF 8HP fill/level procedure is temperature-controlled through "
              "a level plug, not a dipstick -- a generic funnel can't seal to "
              "the fill hole for a controlled fill.",
          confidence=UNKNOWN),
    _tool("elm327_stn", "ELM327/STN OBD-II adapter", "diagnostic",
          spec="connects on COM3 in this shop's setup",
          why="Live PID/DTC access and MES bridge connectivity for every "
              "diagnostics step.", confidence=CORROBORATED),
    _tool("mes_laptop", "Laptop running MultiEcuScan (MES)", "diagnostic",
          why="Module-level scan, freeze frames, actuators, adjustments -- the "
              "shop's primary scan tool for this platform.", confidence=CORROBORATED),
    _tool("witech_vci", "wiTECH VCI pod + dongle", "diagnostic",
          why="Dealer-level bidirectional tests (e.g. SLVT) MES cannot run -- "
              "EPB service mode and some actuator tests need this.",
          confidence=CORROBORATED),
]}


def tool(key: str) -> Optional[dict[str, Any]]:
    """One tool row by key, or ``None``."""
    row = TOOLS.get(key)
    return dict(row) if row is not None else None


# --- "don't have it" decision support ----------------------------------------
#
# One worked example, not a general feature: when a *required* tool isn't
# owned, ``cuore.services.tools_kb_bridge`` looks a (step, tool) pair up here
# for the extra context a mechanic needs to decide buy/borrow/rent/skip --
# where in the diagnosis it's actually used, and sourced cost options. Never
# invented: a cost with no real source is UNKNOWN, not a guess, and "where
# in the diagnosis" cites this corpus's own fault tree/bulletins.
#
# Keyed by (step_key, tool_key). An absent pair means no extra decision
# content has been written for it yet -- :func:`decision_for` returns
# ``None``, and the UI simply shows the plain recommendation with no card.

DECISIONS: dict[tuple[str, str], dict[str, Any]] = {
    ("evap_smoke_test", "smoke_machine"): {
        "used_when": (
            "After E1 (recirculation-line mid-point quick-connect, STAR "
            "S2125000002) and E3 (KOEO purge/vent actuator tests) are done "
            "and clean -- the smoke test is the next step in the EVAP fault "
            "tree, used to isolate which section (tank/canister/purge) "
            "leaks before condemning the canister or ESIM."),
        "used_when_source": "mes.faulttree EVAP_LEAK tree (steps E1, E3, E7); "
                            "docs/research/EVAP_SMOKE_TEST.md Section 4 (isolation sequence)",
        "frequency": (
            "EVAP codes (P0455/P0456/P0440 family) are this corpus's own "
            "chronic, recurring fault family on this Giorgio-platform "
            "engine -- the canister module is named the dominant failure "
            "mode. No quantified owner-population failure rate was found; "
            "treat this as qualitative, not a number."),
        "frequency_confidence": UNKNOWN,
        "frequency_source": "mes.faulttree EVAP_LEAK tree notes",
        "alternatives": [
            {"option": "borrow", "note": "A shop/mobile-mechanic contact's "
             "machine, if the car can be worked where it sits."},
            {"option": "rent", "note": "UNKNOWN -- no sourced automotive-tool "
             "rental listing found for an EVAP smoke machine; check local "
             "rental chains directly before counting on this."},
            {"option": "dealer/shop", "note": "Pay a shop to run the test "
             "instead of buying the tool.",
             "cost": {"range": "$80-150", "unit": "USD per visit",
                       "source": "https://www.expresslubeplano.com/blog/evap-smoke-test-cost/",
                       "confidence": SINGLE_SOURCE}},
            {"option": "different test", "note": "ESIM Test A (hand vacuum "
             "pump, pull vacuum and watch decay) can substitute for "
             "localizing a leak on the ESIM/canister branch without a "
             "smoke machine, though it doesn't split tank/canister/purge "
             "as cleanly as the smoke isolation sequence."},
        ],
        "cost_options": [
            {"tier": "low-cost", "range": "$59.99-$79.99", "unit": "USD",
             "what": "no flow meter, no UV dye",
             "source": "https://www.autolinepro.com/collections/automotive-smoke-machines "
                       "(HyperSmoke, fetched 2026-10-08)",
             "confidence": SINGLE_SOURCE},
            {"tier": "professional", "range": "$1,689.76", "unit": "USD",
             "what": "built-in flow meter calibrated to 0.020in/0.040in "
                    "reference orifices -- matching the EPA/SAE P0456/"
                    "P0455 leak-size definitions -- plus UltraTraceUV dye kit",
             "source": "https://1sourcetool.com/products/otc-6522-smoke-machine-leak-detection-system-with-flow-meter "
                       "(OTC 6522, fetched 2026-10-08)",
             "confidence": SINGLE_SOURCE},
        ],
        "practical_difference": (
            "For a leak near the 0.020 in (P0456) threshold, a flow-metered "
            "machine tells you whether one section's leak is actually big "
            "enough to be the code-causing one, not just that smoke showed "
            "up somewhere -- the isolation sequence in "
            "docs/research/EVAP_SMOKE_TEST.md Section 4 depends on reading "
            "flow against the 0.020in/0.040in reference orifices, not "
            "just seeing smoke. A low-cost machine without a flow meter "
            "can still show WHERE smoke escapes, but can't confirm a small "
            "leak is large enough to be the one the code requires."),
    },
}


def decision_for(step: str, tool_key: str) -> Optional[dict[str, Any]]:
    """Extra buy/borrow/rent/skip context for one (step, tool) pair, or
    ``None`` if nothing has been written for it -- see :data:`DECISIONS`."""
    return DECISIONS.get(((step or "").strip(), (tool_key or "").strip()))


# --- per-job/step tool lists --------------------------------------------------
#
# Each row: {tool, required, alternatives, note}. ``torque_keys`` (optional)
# names ``mes.service_specs.TORQUES`` keys :func:`recommend` resolves live
# and attaches to that row as ``torques`` -- never a bare number here.

def _row(tool_key: str, *, required: bool = True, alternatives: Optional[list[str]] = None,
         note: str = "", torque_keys: Optional[list[str]] = None) -> dict[str, Any]:
    return {"tool": tool_key, "required": required, "alternatives": alternatives or [],
            "note": note.strip(), "torque_keys": torque_keys or []}


JOB_TOOLS: dict[str, list[dict[str, Any]]] = {
    "oil_change": [
        _row("ratchet_metric_set"),
        _row("torque_wrench_small", torque_keys=["drain_plug", "filter_cap"],
             note="Drain plug and filter housing cap are both low-torque, "
                  "soft-thread/plastic -- do not use feel."),
        _row("oil_filter_housing_wrench"),
        _row("oil_drain_pan"),
        _row("floor_jack"), _row("jack_stands"),
        _row("torque_wrench_large", required=False, torque_keys=["wheel_lug"],
             note="Only if also rotating tyres at this visit."),
        _row("trim_clip_tool", required=False, note="If the undertray needs to come off."),
    ],
    "spark_plugs": [
        _row("ratchet_metric_set"),
        _row("spark_plug_socket"),
        _row("ignition_coil_puller", required=False, alternatives=["ratchet_metric_set"]),
        _row("torque_wrench_small", torque_keys=["spark_plug"]),
    ],
    "engine_air_filter": [
        _row("trim_clip_tool", required=False),
        _row("ratchet_metric_set", required=False, note="Box clamps are sometimes bolted."),
    ],
    "cabin_air_filter": [
        _row("trim_clip_tool", required=False, note="Glovebox/panel clips, if fitted."),
    ],
    "brake_fluid": [
        _row("ratchet_metric_set"),
        _row("flare_nut_wrench_set", required=False, note="Bleeder valve, if a line wrench fits better."),
        _row("witech_vci", note="EPB service mode must be entered via MES/wiTECH before "
                                "opening the rear brake hydraulics -- an electric parking "
                                "brake that self-applies mid-bleed is a real hazard."),
    ],
    "brakes_front": [
        _row("ratchet_metric_set"),
        _row("torque_wrench_large", torque_keys=["wheel_lug", "caliper_slider_front"]),
        _row("impact_wrench", required=False),
        _row("floor_jack"), _row("jack_stands"),
    ],
    "brakes_rear": [
        _row("ratchet_metric_set"),
        _row("torque_wrench_large", torque_keys=["wheel_lug"]),
        _row("impact_wrench", required=False),
        _row("floor_jack"), _row("jack_stands"),
        _row("witech_vci", note="Rear calipers are EPB-actuated -- service mode via "
                                "MES/wiTECH before retracting the caliper piston."),
    ],
    "transfer_case": [
        _row("ratchet_metric_set"),
        _row("torque_wrench_small", torque_keys=["transfer_case_drain_plug",
                                                  "transfer_case_fill_plug"]),
        _row("floor_jack"), _row("jack_stands"),
    ],
    "drive_belt": [
        _row("ratchet_metric_set"),
        _row("serpentine_belt_tool"),
    ],
    "battery_12v": [
        _row("battery_terminal_tool"),
        _row("battery_tester"),
        _row("ratchet_metric_set"),
    ],
    "evap_smoke_test": [
        _row("smoke_machine"),
        _row("quick_connect_tool", required=False, note="If a line needs disconnecting to isolate a section."),
    ],
    "evap_esim_test_a": [
        _row("hand_vacuum_pump"),
    ],
    "evap_purge_valve_actuation": [
        _row("mes_laptop", note="Actuator command to cycle the purge valve under MES."),
        _row("dvom", required=False, note="Confirm the valve is actually drawing current when commanded."),
    ],
    "evap_quick_connect_release": [
        _row("quick_connect_tool"),
    ],
    "electrical_inspection": [
        _row("dvom"),
        _row("back_probe_set"),
        _row("mes_laptop", required=False, note="Live parameters alongside the DVOM reading."),
    ],
    "network_voltage_drop": [
        _row("dvom"),
        _row("back_probe_set"),
    ],
    "turbo_replacement": [
        _row("ratchet_metric_set"),
        _row("flare_nut_wrench_set",
             note="Oil feed/return and coolant line fittings. Sizes UNKNOWN -- "
                  "confirm on the car / service manual (TechAuthority). The wrong "
                  "wrench here (open-end on a flare fitting) risks rounding the "
                  "fitting, which turns a planned job into hours chasing a leak "
                  "or a seized/damaged line -- budget the time to get the right "
                  "tool before starting, not after rounding one off."),
        _row("crowfoot_flare_set", required=False, alternatives=["flare_nut_wrench_set"],
             note="For a fitting a straight flare-nut wrench can't swing in."),
        _row("torque_wrench_small", required=False, note="If a sourced torque spec exists for the fitting in hand."),
        _row("floor_jack"), _row("jack_stands"),
    ],
    "zf8hp_fluid": [
        _row("zf8hp_fill_adapter"),
        _row("mes_laptop", note="Fluid temperature read via MES/cuore -- the fill/level "
                               "procedure is temperature-controlled, not fill-to-plug."),
        _row("ratchet_metric_set"),
        _row("floor_jack"), _row("jack_stands"),
    ],
    "wheel_tyre": [
        _row("impact_wrench", required=False),
        _row("torque_wrench_large", torque_keys=["wheel_lug"],
             note="121 Nm, star/cross pattern, snug then final torque."),
        _row("floor_jack"), _row("jack_stands"), _row("wheel_chocks"),
    ],
    "diagnostics": [
        _row("elm327_stn"),
        _row("mes_laptop"),
        _row("witech_vci", required=False, note="For dealer-level bidirectional tests MES can't run."),
    ],
}


def _resolve_torques(torque_keys: list[str]) -> list[dict[str, Any]]:
    out = []
    for k in torque_keys:
        row = torque_by_key(k)
        if row is not None:
            out.append(row)
        else:
            out.append({"key": k, "component": k, "display": "UNKNOWN", "confidence": UNKNOWN,
                       "notes": TECHAUTHORITY})
    return out


def recommend(job_or_step: str) -> list[dict[str, Any]]:
    """Tool rows for one job/step key, each merged with its :data:`TOOLS`
    entry and any referenced torque spec resolved live from
    ``mes.service_specs`` (never a bare number duplicated here).

    An exact key in :data:`JOB_TOOLS` is used as-is. Otherwise, if
    ``job_or_step`` is a family prefix (e.g. ``"evap"`` for
    ``evap_smoke_test``/``evap_esim_test_a``/...), every matching step's
    rows are unioned, tool-key de-duplicated, in first-seen order. An
    unknown key returns an empty list -- never invented tools for a job
    this module doesn't know.
    """
    key = (job_or_step or "").strip().lower()
    if not key:
        return []
    if key in JOB_TOOLS:
        rows = JOB_TOOLS[key]
    else:
        prefix = key if key.endswith("_") else f"{key}_"
        rows = []
        seen: set[str] = set()
        for step_key, step_rows in JOB_TOOLS.items():
            if step_key == key or step_key.startswith(prefix):
                for row in step_rows:
                    if row["tool"] in seen:
                        continue
                    seen.add(row["tool"])
                    rows.append(row)
        if not rows:
            return []

    out = []
    for row in rows:
        entry = dict(row)
        entry["tool_info"] = tool(row["tool"]) or {
            "key": row["tool"], "name": row["tool"], "kind": "hand",
            "spec": None, "why": "", "source": None, "confidence": UNKNOWN,
        }
        entry["alternatives_info"] = [tool(a) for a in row["alternatives"] if tool(a)]
        entry["torques"] = _resolve_torques(row["torque_keys"])
        out.append(entry)
    return out


__all__ = ["KINDS", "CONFIDENCE_LEVELS", "CONFIRMED", "CORROBORATED",
          "SINGLE_SOURCE", "UNKNOWN", "TOOLS", "JOB_TOOLS", "tool", "recommend",
          "DECISIONS", "decision_for"]
