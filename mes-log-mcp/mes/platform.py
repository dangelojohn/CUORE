"""Platform relationships between this project's car and its "similar"
Stellantis/Maserati siblings.

The user has described the 2018 Alfa Romeo Stelvio 2.0T's two "similar"
sibling cars as the Maserati Levante and the Maserati Grecale. House rule
(see ``feedback_...`` memory): never present an unverified relationship as
fact. This module is a small, sourced table of what is actually shared
between these cars' platforms -- and, just as importantly, what is NOT --
so the rest of the project (``mes.experience``, ``mes.parts``,
``mes.code_feel`` and their ``cuore`` bridges) can label a sibling-platform
result "verify fit" instead of presenting it as settled.

Confidence levels (never invented -- an absent/unverified relationship is
recorded as UNKNOWN, never guessed):

* ``CONFIRMED``     -- stated directly by a primary source (the
                       manufacturer's own platform article/spec sheet).
* ``CORROBORATED``  -- two independent sources agree (e.g. Wikipedia's
                       Grecale article plus the FCA Global Medium Engine
                       article both naming the same shared engine family).
* ``SINGLE_SOURCE``  -- exactly one source found, not cross-checked.
* ``UNKNOWN``       -- nothing credible found, or the two cars are
                       confirmed to NOT share the thing being asked about
                       (e.g. Levante and Stelvio do not share a platform).

Research pass: 2026-10-07, via web search + page fetch of:

* https://en.wikipedia.org/wiki/Maserati_Grecale -- "the Grecale shares the
  company's Giorgio platform with the Alfa Romeo Stelvio and the fifth
  generation Jeep Grand Cherokee."
* https://en.wikipedia.org/wiki/FCA_Global_Medium_Engine -- the GME T4 2.0L
  turbo engine family, first fitted to the Giulia/Stelvio, also used in the
  Grecale.
* https://en.wikipedia.org/wiki/Alfa_Romeo_Stelvio -- Giorgio platform,
  ZF 8HP50 (base/Ti) / ZF 8HP75 (Quadrifoglio) transmissions.
* https://en.wikipedia.org/wiki/Maserati_Levante -- infobox states
  "Platform: Chrysler LX platform" (i.e. NOT the Giorgio platform the
  Stelvio/Grecale share); "The Levante gains an eight speed ZF automatic
  transmission from the sixth generation Maserati Quattroporte."
* https://en.wikipedia.org/wiki/Maserati_Ghibli_(M157) -- M157/Quattroporte
  VI-derived platform, same ZF 8HP-family transmission line as the Levante.
* https://www.go-parts.com/garage/wire-harness-trans-maserati-quattroporte-maserati-ghibli-maserati-levante-2014-2022
  -- names the Ghibli, Quattroporte and Levante as sharing the AWD
  transmission/harness (ZF 8HP70).
* https://www.go-parts.com/garage/transmission-assembly-alfa-romeo-giulia-alfa-romeo-stelvio-2017-2025
  -- Giulia/Stelvio 2.0L AWD use the ZF 8HP50, a different member of the
  same ZF 8HP transmission family, not an identical part.
* https://dot.report/wmi/ZN6 -- "Maserati North America, Inc." holds WMI
  ``ZN6``, used for BOTH the Levante (2017-2024) and the Grecale
  (2023-present) -- no sourced way to tell the two models apart from the
  WMI alone.

The headline finding: **Grecale and Stelvio are genuine platform-mates**
(Giorgio platform, shared GME T4 2.0L engine family) -- a CORROBORATED,
sourced relationship. **Levante and Stelvio are NOT platform-mates** -- the
Levante's own Wikipedia infobox names the Chrysler LX platform, not
Giorgio -- so anything in common between a Levante and this Stelvio is
component-level at best (the ZF 8HP transmission *family*, not the same
part) and everything else is UNKNOWN rather than assumed.
"""

from __future__ import annotations

import re
from typing import Any, Optional

CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNKNOWN = "UNKNOWN"
CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNKNOWN)

#: ``shared_with`` model names this module recognises as "sibling platform,
#: not this car" -- the set ``mes.experience``/``mes.parts`` check an
#: entry's ``vehicle_fit``/``fits`` field against before tagging it with
#: ``sibling_of``.
SIBLING_MODELS = frozenset({"grecale", "levante"})


def _share(model: str, what_is_shared: list[str], confidence: str,
           source: str) -> dict[str, Any]:
    if confidence not in CONFIDENCE_LEVELS:
        raise ValueError(f"bad confidence {confidence!r} for shared_with[{model!r}]")
    if not source:
        raise ValueError(f"shared_with[{model!r}] has no source")
    return {"model": model, "what_is_shared": list(what_is_shared),
            "confidence": confidence, "source": source}


_WIKI_GRECALE = "https://en.wikipedia.org/wiki/Maserati_Grecale"
_WIKI_GME = "https://en.wikipedia.org/wiki/FCA_Global_Medium_Engine"
_WIKI_STELVIO = "https://en.wikipedia.org/wiki/Alfa_Romeo_Stelvio"
_WIKI_GIULIA = "https://en.wikipedia.org/wiki/Alfa_Romeo_Giulia_(2015)"
_WIKI_LEVANTE = "https://en.wikipedia.org/wiki/Maserati_Levante"
_WIKI_GHIBLI = "https://en.wikipedia.org/wiki/Maserati_Ghibli_(M157)"
_GOPARTS_GIULIA_STELVIO_ZF = ("https://www.go-parts.com/garage/transmission-assembly-"
                               "alfa-romeo-giulia-alfa-romeo-stelvio-2017-2025")
_GOPARTS_MASERATI_ZF = ("https://www.go-parts.com/garage/wire-harness-trans-maserati-"
                          "quattroporte-maserati-ghibli-maserati-levante-2014-2022")
_DOT_REPORT_ZN6 = "https://dot.report/wmi/ZN6"

_GIORGIO_PLATFORM_GME = [
    "Giorgio platform (body structure, suspension architecture)",
    "GME T4 2.0L turbocharged inline-4 engine family",
]
_NOT_PLATFORM_SHARED_ZF_ONLY = [
    "ZF 8HP-family automatic transmission (different member of the family: "
    "this car's 2.0T uses a ZF 8HP50/8HP75; the Levante uses a ZF 8HP70 -- "
    "same supplier family, not an identical part). NOT a shared platform: "
    "Levante is built on the Chrysler LX platform per its own Wikipedia "
    "infobox, this car on Giorgio. Any other component overlap "
    "(suspension, electronics, suppliers) is UNKNOWN -- not checked this "
    "pass.",
]

PLATFORMS: dict[str, dict[str, Any]] = {
    "stelvio": {
        "platform": "FCA/Stellantis Giorgio platform",
        "years": "2017-present (2018 model year, this project's VIN)",
        "shared_with": [
            _share("giulia", _GIORGIO_PLATFORM_GME, CORROBORATED,
                   f"{_WIKI_STELVIO} ; {_WIKI_GIULIA} ; {_WIKI_GME}"),
            _share("grecale", _GIORGIO_PLATFORM_GME, CORROBORATED,
                   f"{_WIKI_GRECALE} (\"the Grecale shares the company's "
                   f"Giorgio platform with the Alfa Romeo Stelvio\") ; {_WIKI_GME}"),
            _share("levante", _NOT_PLATFORM_SHARED_ZF_ONLY, SINGLE_SOURCE,
                   f"{_GOPARTS_GIULIA_STELVIO_ZF} ; {_WIKI_LEVANTE}"),
        ],
    },
    "giulia": {
        "platform": "FCA/Stellantis Giorgio platform",
        "years": "2015/2016-present",
        "shared_with": [
            _share("stelvio", _GIORGIO_PLATFORM_GME, CORROBORATED,
                   f"{_WIKI_STELVIO} ; {_WIKI_GIULIA} ; {_WIKI_GME}"),
            _share("grecale", _GIORGIO_PLATFORM_GME, CORROBORATED,
                   f"{_WIKI_GRECALE} ; {_WIKI_GME}"),
            _share("levante", _NOT_PLATFORM_SHARED_ZF_ONLY, SINGLE_SOURCE,
                   f"{_GOPARTS_GIULIA_STELVIO_ZF} ; {_WIKI_LEVANTE}"),
        ],
    },
    "grecale": {
        "platform": "FCA/Stellantis Giorgio platform (Maserati execution)",
        "years": "2023-present",
        "shared_with": [
            _share("stelvio", _GIORGIO_PLATFORM_GME, CORROBORATED,
                   f"{_WIKI_GRECALE} ; {_WIKI_GME}"),
            _share("giulia", _GIORGIO_PLATFORM_GME, CORROBORATED,
                   f"{_WIKI_GRECALE} ; {_WIKI_GME}"),
            _share("levante", ["no sourced platform or component overlap found "
                                "this pass -- Grecale (Giorgio) and Levante "
                                "(Chrysler LX) are different platforms; both "
                                "share WMI ZN6 as Maserati North America "
                                "products, which is a VIN-registration fact, "
                                "not a shared-parts fact"],
                   UNKNOWN, f"{_WIKI_GRECALE} ; {_WIKI_LEVANTE} ; {_DOT_REPORT_ZN6}"),
        ],
    },
    "levante": {
        "platform": "Chrysler LX platform (per Wikipedia's Levante infobox); "
                     "informally described in some coverage as sharing the "
                     "Ghibli/Quattroporte VI-era Maserati architecture, but "
                     "that specific platform-identity claim was not confirmed "
                     "against a primary source this pass -- treat as UNKNOWN, "
                     "not as the Giorgio platform this project's car uses.",
        "years": "2016-2024",
        "shared_with": [
            _share("ghibli", ["ZF 8HP70 automatic transmission (same "
                                "transmission the Levante \"gains ... from "
                                "the sixth generation Maserati Quattroporte\"; "
                                "Ghibli, Quattroporte and Levante share this "
                                "line per the sourced parts-vendor page)",
                                "AWD transmission wiring harness (per sourced "
                                "parts-vendor page)"],
                   CORROBORATED, f"{_WIKI_LEVANTE} ; {_WIKI_GHIBLI} ; {_GOPARTS_MASERATI_ZF}"),
            _share("stelvio", _NOT_PLATFORM_SHARED_ZF_ONLY, SINGLE_SOURCE,
                   f"{_GOPARTS_GIULIA_STELVIO_ZF} ; {_WIKI_LEVANTE}"),
            _share("grecale", ["no sourced platform or component overlap found "
                                "this pass -- see grecale/levante entry above"],
                   UNKNOWN, f"{_WIKI_LEVANTE} ; {_WIKI_GRECALE} ; {_DOT_REPORT_ZN6}"),
        ],
    },
    "ghibli": {
        "platform": "Maserati M157 platform (Quattroporte VI-derived)",
        "years": "2013-present",
        "shared_with": [
            _share("levante", ["ZF 8HP70 automatic transmission", "AWD "
                                "transmission wiring harness"],
                   CORROBORATED, f"{_WIKI_GHIBLI} ; {_WIKI_LEVANTE} ; {_GOPARTS_MASERATI_ZF}"),
        ],
    },
}

for _model, _rec in PLATFORMS.items():
    for _s in _rec["shared_with"]:
        if not _s.get("source"):
            raise ValueError(f"{_model} -> {_s['model']} has no source")

#: VIN prefix (WMI, the first 3 characters) this project's own car's VIN
#: starts with -- confirmed directly against the project VIN
#: ``ZASFAKPN5J7B88115`` (see project_stelvio_evap.md memory).
_WMI_STELVIO_RE = re.compile(r"^ZASF", re.IGNORECASE)

#: WMI ``ZN6`` is held by "Maserati North America, Inc." (sourced:
#: https://dot.report/wmi/ZN6) and is used for BOTH the Levante
#: (2017-2024) and the Grecale (2023-present) -- no sourced VIN position
#: was found this pass that reliably distinguishes the two models from the
#: WMI alone, so a VIN starting with this prefix resolves to UNKNOWN rather
#: than guessing which Maserati SUV it is. ``ZN7`` was searched for and no
#: source was found assigning it to any Maserati model -- also UNKNOWN.
_WMI_MASERATI_SUV_RE = re.compile(r"^(ZN6|ZN7)", re.IGNORECASE)


def siblings(model: str) -> list[dict[str, Any]]:
    """Sourced sibling-platform relationships for ``model`` (e.g.
    ``"stelvio"``). Each item: ``{model, shared, confidence, source}``.
    Returns ``[]`` for an unrecognised model -- never a guess.
    """
    key = (model or "").strip().lower()
    rec = PLATFORMS.get(key)
    if rec is None:
        return []
    return [
        {"model": s["model"], "shared": list(s["what_is_shared"]),
         "confidence": s["confidence"], "source": s["source"]}
        for s in rec.get("shared_with", [])
    ]


def model_for_vin(vin: str) -> str:
    """Best-effort model name from a VIN's WMI (first 3-4 characters).

    Returns ``"stelvio"`` for this project's own car's VIN prefix, and
    ``"UNKNOWN"`` for anything not confidently sourced -- including a
    Maserati ``ZN6``/``ZN7`` WMI, which this research pass could not
    reliably split between Levante and Grecale (see module docstring).
    Never guesses a specific model from an ambiguous WMI.
    """
    v = (vin or "").strip().upper()
    if not v:
        return UNKNOWN
    if _WMI_STELVIO_RE.match(v):
        return "stelvio"
    if _WMI_MASERATI_SUV_RE.match(v):
        return UNKNOWN
    return UNKNOWN


def platform_for(model: str) -> Optional[dict[str, Any]]:
    """The platform record for ``model``, or ``None`` if unrecognised."""
    key = (model or "").strip().lower()
    rec = PLATFORMS.get(key)
    if rec is None:
        return None
    return {"model": key, "platform": rec["platform"], "years": rec["years"],
            "shared_with": siblings(key)}


__all__ = ["CONFIRMED", "CORROBORATED", "SINGLE_SOURCE", "UNKNOWN",
          "CONFIDENCE_LEVELS", "SIBLING_MODELS", "PLATFORMS",
          "siblings", "model_for_vin", "platform_for"]
