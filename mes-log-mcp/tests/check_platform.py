"""Smoke checks for mes.platform (sibling-platform relationships).

Plain script style, like check_parts.py: no test framework, no corpus/state
dependency -- this module is pure data plus a few lookup functions.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_platform.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mes import platform as pf  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


EXPECTED_MODELS = {"stelvio", "giulia", "grecale", "levante", "ghibli"}

# --- shape -----------------------------------------------------------------

check("PLATFORMS has exactly the specified models",
      set(pf.PLATFORMS.keys()) == EXPECTED_MODELS,
      str(set(pf.PLATFORMS.keys()) ^ EXPECTED_MODELS))

for model, rec in pf.PLATFORMS.items():
    check(f"{model}: has platform and years",
          bool(rec.get("platform")) and bool(rec.get("years")))
    check(f"{model}: shared_with is a non-empty list",
          isinstance(rec.get("shared_with"), list) and len(rec["shared_with"]) > 0)
    for s in rec.get("shared_with", []):
        check(f"{model}->{s.get('model')}: confidence is a valid level",
              s.get("confidence") in pf.CONFIDENCE_LEVELS, s.get("confidence"))
        check(f"{model}->{s.get('model')}: has a non-empty source "
              "(no entry lacks a source)",
              bool((s.get("source") or "").strip()), s)
        check(f"{model}->{s.get('model')}: what_is_shared is a non-empty list",
              isinstance(s.get("what_is_shared"), list) and len(s["what_is_shared"]) > 0)

# --- siblings() --------------------------------------------------------------

print("=== siblings('stelvio') includes grecale, sourced ===")
stelvio_siblings = pf.siblings("stelvio")
by_model = {s["model"]: s for s in stelvio_siblings}
check("stelvio has a grecale sibling entry", "grecale" in by_model, str(by_model.keys()))
if "grecale" in by_model:
    grecale_entry = by_model["grecale"]
    check("stelvio->grecale confidence is sourced (not UNKNOWN)",
          grecale_entry["confidence"] != pf.UNKNOWN, grecale_entry)
    check("stelvio->grecale has a source", bool(grecale_entry.get("source")))
check("stelvio has a levante sibling entry (component-level only)",
      "levante" in by_model, str(by_model.keys()))

print("=== grecale<->stelvio is CORROBORATED on the Giorgio platform ===")
grecale_siblings = {s["model"]: s for s in pf.siblings("grecale")}
check("grecale->stelvio is CORROBORATED",
      grecale_siblings.get("stelvio", {}).get("confidence") == pf.CORROBORATED,
      str(grecale_siblings.get("stelvio")))

print("=== siblings() for an unrecognised model returns [] ===")
check("siblings('bugatti') == []", pf.siblings("bugatti") == [])

# --- model_for_vin() ---------------------------------------------------------

print("=== model_for_vin ===")
check('model_for_vin("ZASFAKPN5J7B88115") == "stelvio"',
      pf.model_for_vin("ZASFAKPN5J7B88115") == "stelvio")
check("model_for_vin is case-insensitive",
      pf.model_for_vin("zasfakpn5j7b88115") == "stelvio")
check('model_for_vin("ZN6PMDDC8R7000000") == "UNKNOWN" (ambiguous WMI, '
      "not guessed between Levante/Grecale",
      pf.model_for_vin("ZN6PMDDC8R7000000") == pf.UNKNOWN)
check('model_for_vin("") == "UNKNOWN"', pf.model_for_vin("") == pf.UNKNOWN)
check('model_for_vin("1FAFP404X1F123456") == "UNKNOWN" (unrelated VIN)',
      pf.model_for_vin("1FAFP404X1F123456") == pf.UNKNOWN)

# --- platform_for() -----------------------------------------------------------

print("=== platform_for ===")
stelvio_platform = pf.platform_for("stelvio")
check("platform_for('stelvio') returns a record", stelvio_platform is not None)
check("platform_for('stelvio') includes shared_with",
      bool(stelvio_platform and stelvio_platform.get("shared_with")))
check("platform_for('nonexistent') returns None", pf.platform_for("nonexistent") is None)

# --- no entry lacks a source (global sweep) ----------------------------------

print("=== no entry in PLATFORMS lacks a source ===")
no_source = [
    f"{model}->{s['model']}"
    for model, rec in pf.PLATFORMS.items()
    for s in rec.get("shared_with", [])
    if not (s.get("source") or "").strip()
]
check("every shared_with entry has a source", no_source == [], str(no_source))


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
