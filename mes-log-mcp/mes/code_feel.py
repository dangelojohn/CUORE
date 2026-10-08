""""What would the driver feel?" -- a sourced knowledge table, by DTC.

A mechanic reading a dossier sees codes; a driver only ever reports feelings.
This module is the bridge between the two: for a given code it says what a
driver should (and should not) expect to notice, grounded in real sources,
so ``cuore.services.timeline_bridge`` can hold "the codes say X" next to "the
driver reported Y" and name the gap instead of leaving it implicit.

Nothing here is invented. Every entry below was built from either an external
source (cited in ``source``) or this repository's own corpus-grounded code
(cited the same way other ``mes`` modules cite ``docs/...`` paths). A code
with no sourced finding gets ``confidence: "UNKNOWN"`` and a note pointing at
the service manual -- never a guessed answer.

Confidence levels, strongest first:

* ``CONFIRMED``    -- stated in the vehicle's own service documentation or
                      this project's corpus-grounded code (e.g. a failure-type
                      byte read off a real ECU).
* ``CORROBORATED`` -- the same finding appears in two or more independent
                      sources agreeing with each other.
* ``SINGLE-SOURCE`` -- one source only; treat as a lead, not a settled fact.
* ``UNKNOWN``      -- no sourced finding; the entry says so rather than
                      guessing, and points at TechAuthority.

Lookup is by exact code first (failure-type byte stripped, same rule as
``mes.knowledge.base_code``), then by family when the exact code is not
tabulated: any ``U`` code falls back to the generic network-fault entry, any
``P03xx`` falls back to the generic misfire entry. Everything else with no
exact entry returns ``None`` -- a missing answer, not a wrong one.
"""

from __future__ import annotations

import re
from typing import Any, Optional

#: Strip the failure-type byte: "P0456-00" -> "P0456". Mirrors
#: ``mes.knowledge.base_code``, reimplemented rather than imported so this
#: module stays a standalone lookup table with no cross-module coupling.
_BASE_RE = re.compile(r"^([PBCU][0-9A-F]{4})", re.IGNORECASE)

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"

_UNKNOWN_NOTE = "not established in any source checked -- use the service manual (TechAuthority)"


def base_code(code: str) -> str:
    m = _BASE_RE.match((code or "").strip().upper())
    return m.group(1) if m else (code or "").strip().upper()


# --- EVAP -------------------------------------------------------------------
#
# The EVAP finding is consistent across every source checked: the fault is
# isolated from the combustion/drivetrain path, so a driver who notices
# nothing is the EXPECTED pattern, not evidence the leak is intermittent.
# Sources: carparts.com, fs1inc.com, obd2beginner.com, edmunds.com (symptom
# surveys for P0440/P0455/P0456/P0457); ricksfreeautorepairadvice.com and
# innova.com (EVAP is a federal two-trip monitor: a fault must be confirmed
# on a second consecutive drive cycle before the MIL comes on).

_EVAP_SOURCE = ("https://www.carparts.com/blog/p0455-code-evaporative-emission-system-large-leak-detected/ ; "
               "https://www.fs1inc.com/blog/dtc-p0455-evap-system-leak-detected-large-leak/ ; "
               "https://ricksfreeautorepairadvice.com/getting-the-evaporative-emissions-system-monitor-ready/")

_EVAP_NOT_EXPECTED = ["rough_idle", "hesitation", "loss_of_power", "hard_start"]

_EVAP_GENERIC = {
    "feel": ("Almost always nothing a driver notices -- the EVAP system is "
            "isolated from the engine's running operation, so no drivability "
            "change is expected. The warning light is usually the only clue."),
    "expect": ["mil_on"],
    "not_expected": _EVAP_NOT_EXPECTED,
    "mil": "two-trip",
    "notes": ("EVAP monitors are federally mandated two-trip monitors: a leak "
             "must be confirmed on a second consecutive drive cycle before "
             "the MIL is commanded on. A code with no driver complaint is the "
             "expected pattern for this family, not a sign the fault is "
             "intermittent or has gone away."),
    "confidence": CORROBORATED,
    "source": _EVAP_SOURCE,
}


def _evap(**overrides: Any) -> dict[str, Any]:
    out = dict(_EVAP_GENERIC)
    out.update(overrides)
    return out


# --- misfire -----------------------------------------------------------------
#
# Sources: identifix.com, haynes (uk.haynes.com), obd2beginner.com,
# cartreatments.com, fs1inc.com -- all agree misfire is one of the few DTC
# families a driver reliably feels, and that a misfire severe enough to
# threaten the catalytic converter flashes the MIL rather than holding it
# steady (the "Type A, one-trip" monitor behaviour).

_MISFIRE_SOURCE = ("https://www.identifix.com/blogs/p0300-code-the-guide-to-diagnostics-and-repair/ ; "
                   "https://uk.haynes.com/blogs/tips-tutorials/how-to-fix-fault-code-p0300 ; "
                   "https://cartreatments.com/p0301/")

_MISFIRE_GENERIC = {
    "feel": ("Usually very noticeable: a rough, shaking idle, a stumble or "
            "hesitation under acceleration, occasional jerking, reduced "
            "power, and sometimes occasional stalling. A check-engine light "
            "that FLASHES rather than stays steady means the misfire rate is "
            "high enough to risk catalytic-converter damage and should not "
            "be driven through."),
    "expect": ["rough_idle", "hesitation", "loss_of_power", "vibration", "mil_on"],
    "not_expected": ["drives_normally"],
    "mil": "one-trip",
    "notes": ("Misfire is a continuous, Type A, one-trip monitor: the MIL can "
             "be commanded on (and flash, if severe) the first time the "
             "fault is detected, unlike EVAP's two-trip behaviour."),
    "confidence": CORROBORATED,
    "source": _MISFIRE_SOURCE,
}


def _misfire(cylinder: Optional[int] = None) -> dict[str, Any]:
    out = dict(_MISFIRE_GENERIC)
    if cylinder is not None:
        out["feel"] = f"Cylinder #{cylinder} misfire. " + out["feel"]
    return out


# --- network / U-codes -------------------------------------------------------
#
# Sources: fs1inc.com (per-U-code symptom write-ups), obdguides.com (U-code
# overview). General pattern across both: a driver usually feels nothing
# drivability-wise; the tell is a warning light (sometimes several modules'
# worth at once) or an accessory/feature dropping out, not a performance
# change -- consistent with this project's own network-cascade finding in
# mes.analysis.detect_network_event.

_NETWORK_SOURCE = ("https://www.fs1inc.com/blog/dtc-u0101-lost-communication-tcm/ ; "
                   "https://obdguides.com/u-codes/ ; "
                   "mes-log-mcp/mes/analysis.py (detect_network_event, corpus-grounded)")

_NETWORK_GENERIC = {
    "feel": ("Usually nothing felt in how the car drives -- these are module-"
            "to-module communication faults, not component failures. The "
            "tell is a warning light (sometimes several at once, across "
            "unrelated systems) or a feature/accessory that stops working, "
            "not a change in acceleration, idle or power."),
    "expect": ["warning_message"],
    "not_expected": ["rough_idle", "hesitation", "loss_of_power", "hard_start"],
    "mil": "unknown",
    "notes": ("MIL behaviour for U-codes varies by module and manufacturer "
             "policy; several at once pointing at unrelated modules is "
             "usually one supply or bus event, not several separate module "
             "failures -- see mes.analysis.detect_network_event."),
    "confidence": CORROBORATED,
    "source": _NETWORK_SOURCE,
}

# --- fuel trim ---------------------------------------------------------------
#
# Sources: carista.com, oreillyauto.com, foxwelldiag.com (P0171/P0172 symptom
# write-ups). Trip-count policy for the Fuel System monitor was not confirmed
# in any source checked for THIS code specifically, so ``mil`` stays
# "unknown" rather than asserting the common two-trip convention unsourced.

_FUEL_TRIM_SOURCE = ("https://carista.com/en-us/pages/obd2-diagnostic-trouble-codes/p0171 ; "
                     "https://www.oreillyauto.com/how-to-hub/check-engine-light-code-p0172-and-p0175-fuel-system-rich ; "
                     "https://www.foxwelldiag.com/blogs/car-diagnostic/p0171-fuel-trim-system-lean-bank-1-symptoms-fix-diagnose")


# --- the table ----------------------------------------------------------------

_CODES: dict[str, dict[str, Any]] = {
    "P0440": _evap(feel=_EVAP_GENERIC["feel"] + " (General EVAP system fault -- "
                                                 "no leak size is implied.)"),
    "P0441": _evap(feel="Incorrect EVAP purge flow. " + _EVAP_GENERIC["feel"]),
    "P0455": _evap(
        feel=("Large EVAP leak. Usually nothing felt in how the car drives; "
             "the leak is big enough that a fuel-vapour smell near the tank "
             "or filler, especially right after fuelling, is the most common "
             "secondary clue beyond the warning light."),
        expect=["mil_on", "fuel_smell"],
    ),
    "P0456": _evap(feel=("Small EVAP leak. Almost always nothing felt -- a small "
                        "leak rarely produces a noticeable fuel smell, so the "
                        "warning light is typically the only clue.")),
    "P0457": _evap(
        feel=("EVAP leak consistent with a loose, missing or faulty fuel "
             "cap. Usually nothing felt; occasionally a faint fuel smell "
             "after refuelling and a slightly steady (not flashing) MIL."),
        expect=["mil_on", "fuel_smell"],
        notes=_EVAP_GENERIC["notes"] + " Check the cap is seated and undamaged "
                                       "before looking further into the system.",
    ),
    "P1CEA": _evap(
        feel=("Boost-side EVAP purge system performance (ejector-tee / purge-"
             "hose integrity between the intake and the tank). Usually "
             "nothing felt; a minority of owners with an aftermarket intake "
             "or air filter have reported a mild rough idle alongside it."),
        notes=(_EVAP_GENERIC["notes"] + " On this platform P1CEA is commonly "
              "traced to the ejector tee in the clean-air duct, or an "
              "aftermarket intake disturbing the purge-side plumbing."),
        confidence=SINGLE_SOURCE,
        source="https://www.giuliaforums.com/threads/resolved-cel-p1cea-boost-side-evap-purge-system-performance.38810/ ; "
              "https://www.stelvioforum.com/threads/eurocompulsion-p1cea00-error-code.12635/",
    ),

    "P0300": _misfire(),
    "P0301": _misfire(1),
    "P0302": _misfire(2),
    "P0303": _misfire(3),
    "P0304": _misfire(4),

    "P0171": {
        "feel": ("Fuel trim too lean (bank 1). May be completely invisible, "
                "or may show as a rough or stalling idle, hesitation on "
                "acceleration and reduced power; a vacuum leak large enough "
                "to cause this can sometimes be heard as a hiss under the "
                "hood."),
        "expect": ["rough_idle", "hesitation", "loss_of_power", "noise"],
        "not_expected": [],
        "mil": "unknown",
        "notes": ("Trip-count policy for this code was not confirmed in the "
                 "sources checked; the federal Fuel System monitor is "
                 "commonly a two-trip monitor by convention, but that was "
                 "not verified against this code specifically."),
        "confidence": CORROBORATED,
        "source": _FUEL_TRIM_SOURCE,
    },
    "P0172": {
        "feel": ("Fuel trim too rich (bank 1). May be completely invisible, "
                "or may show as a rough idle, a strong fuel smell or black "
                "smoke from the exhaust, misfires and reduced power."),
        "expect": ["rough_idle", "fuel_smell", "loss_of_power", "hesitation"],
        "not_expected": [],
        "mil": "unknown",
        "notes": ("Trip-count policy for this code was not confirmed in the "
                 "sources checked; see the P0171 entry's note."),
        "confidence": CORROBORATED,
        "source": _FUEL_TRIM_SOURCE,
    },

    # --- Giorgio-platform body/network codes ---------------------------------
    "B1176": {
        "feel": ("Hypothesis, not established: not a drivability fault. The "
                "failure-type byte (-97, 'operation obstructed or blocked') and "
                "the component this code names on this platform would point at "
                "a power window that will not fully travel, may stall partway, "
                "or needs repeated attempts -- not a dashboard warning most "
                "drivers would separately report. This is this project's own "
                "FTB mapping, not a manufacturer definition for this exact "
                "code -- confirm against the window/regulator circuit before "
                "relying on it."),
        "expect": ["other", "noise"],
        "not_expected": ["rough_idle", "hesitation", "loss_of_power", "hard_start"],
        "mil": "unknown",
        "notes": _UNKNOWN_NOTE,
        "confidence": UNKNOWN,
        "source": "",
    },
    "C141B": {
        "feel": _UNKNOWN_NOTE,
        "expect": [],
        "not_expected": [],
        "mil": "unknown",
        "notes": _UNKNOWN_NOTE,
        "confidence": UNKNOWN,
        "source": "",
    },
    "C141C": {
        "feel": ("Private-CAN communication fault between the headlight/fog-"
                "light module (HALF) and the driver-assistance module "
                "(DASM) -- effectively a camera/ADAS network fault, not a "
                "drivetrain one. Typically no change in how the car drives, "
                "but forward-camera-dependent features (lane-keep assist, "
                "adaptive cruise, automatic high beams) may be unavailable "
                "and a warning message may appear."),
        "expect": ["warning_message"],
        "not_expected": ["rough_idle", "hesitation", "loss_of_power", "hard_start"],
        "mil": "unknown",
        "notes": ("Two independent sources agree on the HALF<->DASM private-"
                 "CAN reading for this exact code; neither states a MIL "
                 "trip-count policy."),
        "confidence": CORROBORATED,
        "source": "https://www.dtcdecode.com/Alfa-Romeo/C141C-86 ; "
                 "https://www.giuliaforums.com/threads/alfa-giulia-dtc-find-errors-in-many-modules.57936/",
    },
}


def _family_fallback(base: str) -> Optional[dict[str, Any]]:
    if not base:
        return None
    if base[0] == "U":
        return _NETWORK_GENERIC
    if re.match(r"^P03\d{2}$", base):
        return _MISFIRE_GENERIC
    return None


def lookup(code: str, include_siblings: bool = False) -> Optional[dict[str, Any]]:
    """"What would the driver feel?" for one DTC.

    Resolves the exact code first (failure-type byte stripped); if that is
    not tabulated, falls back to a family generic (any ``U`` code -> network,
    any ``P03xx`` -> misfire). Returns ``None`` -- not a guess -- for
    anything else. The returned dict always carries ``code`` (what was
    looked up) and ``matched`` (``"exact"`` or ``"family:<name>"``) on top of
    the table fields (``feel``, ``expect``, ``not_expected``, ``mil``,
    ``notes``, ``confidence``, ``source``).

    ``include_siblings=True`` adds a ``"siblings"`` key: entries for sourced
    sibling platforms (grecale/levante -- see :mod:`mes.platform``) that
    would apply the same finding there, each flagged ``{"sibling_of":
    <model>, "verify_fit": True}``. This table carries no per-vehicle-model
    field at all (every entry here is a physical/engineering finding, not
    tied to one car), so -- per house rule, never present an unverified
    relationship as fact -- ``"siblings"`` is always ``[]``: nothing in
    this table has been confirmed to transfer to a sibling car, so nothing
    is tagged. Callers that want the sourced platform relationship itself
    should use :func:`mes.platform.siblings`.
    """
    base = base_code(code)
    if not base:
        return None
    exact = _CODES.get(base)
    if exact is not None:
        out = dict(exact)
        out["code"] = base
        out["matched"] = "exact"
    else:
        family = _family_fallback(base)
        if family is None:
            return None
        out = dict(family)
        out["code"] = base
        out["matched"] = ("family:network" if base[0] == "U" else "family:misfire")
    if include_siblings:
        out["siblings"] = []
    return out


__all__ = ["CONFIRMED", "CORROBORATED", "SINGLE_SOURCE", "UNKNOWN",
          "base_code", "lookup"]
