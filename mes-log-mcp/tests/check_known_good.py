"""Smoke checks for mes.known_good.

Schema, honesty rules and the observed_ranges() percentile machinery. No
mocks, no synthetic corpus -- observed_ranges() is exercised against
whatever the real corpus does or doesn't have for the given VIN, and must
never raise either way, but its numeric-correctness assertions are written
against a synthetic sample so they hold regardless of what the real corpus
contains.

Run:
    .venv/Scripts/python.exe mes-log-mcp/tests/check_known_good.py
"""

from __future__ import annotations

import sys
from pathlib import Path

_MES_ROOT = Path(__file__).resolve().parents[1]
_REPO_ROOT = _MES_ROOT.parent
sys.path.insert(0, str(_MES_ROOT))
sys.path.insert(0, str(_REPO_ROOT))

from mes import known_good, service_specs  # noqa: E402
from cuore.live import channels as channels_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- KNOWN_GOOD: shape ---------------------------------------------------------

check("KNOWN_GOOD is non-empty", len(known_good.KNOWN_GOOD) > 0)

REQUIRED_KEYS = {"id", "name", "unit", "conditions", "normal", "warn", "alarm",
                 "direction", "confidence", "source", "notes", "generic"}
check("every row has exactly the documented keys",
      all(set(row.keys()) == REQUIRED_KEYS for row in known_good.KNOWN_GOOD.values()),
      str([cid for cid, row in known_good.KNOWN_GOOD.items()
          if set(row.keys()) != REQUIRED_KEYS]))

check("every row's id matches its dict key",
      all(row["id"] == cid for cid, row in known_good.KNOWN_GOOD.items()))

check("every row has a confidence in the shared CONFIDENCE_LEVELS",
      all(row["confidence"] in service_specs.CONFIDENCE_LEVELS
          for row in known_good.KNOWN_GOOD.values()))

check("every row has a direction of above/below/both",
      all(row["direction"] in ("above", "below", "both")
          for row in known_good.KNOWN_GOOD.values()))

check("every row's generic flag is a bool",
      all(isinstance(row["generic"], bool) for row in known_good.KNOWN_GOOD.values()))


# --- KNOWN_GOOD: house-style honesty rules -------------------------------------

check("every non-UNKNOWN row cites a source",
      all(row["source"] for row in known_good.KNOWN_GOOD.values()
          if row["confidence"] != known_good.UNKNOWN),
      str([cid for cid, row in known_good.KNOWN_GOOD.items()
          if row["confidence"] != known_good.UNKNOWN and not row["source"]]))

check("every UNKNOWN row has no normal/warn/alarm numbers (never invented)",
      all(row["normal"] is None and row["warn"] is None and row["alarm"] is None
          for row in known_good.KNOWN_GOOD.values()
          if row["confidence"] == known_good.UNKNOWN),
      str([cid for cid, row in known_good.KNOWN_GOOD.items()
          if row["confidence"] == known_good.UNKNOWN
          and (row["normal"] or row["warn"] or row["alarm"])]))

check("every UNKNOWN row points at TechAuthority",
      all(known_good.TECHAUTHORITY in row["notes"]
          for row in known_good.KNOWN_GOOD.values()
          if row["confidence"] == known_good.UNKNOWN),
      str([cid for cid, row in known_good.KNOWN_GOOD.items()
          if row["confidence"] == known_good.UNKNOWN
          and known_good.TECHAUTHORITY not in row["notes"]]))


def _ordered(band) -> bool:
    return band is None or band[0] <= band[1]


check("every row's normal/warn/alarm band is ordered lo <= hi",
      all(_ordered(row["normal"]) and _ordered(row["warn"]) and _ordered(row["alarm"])
          for row in known_good.KNOWN_GOOD.values()),
      str([cid for cid, row in known_good.KNOWN_GOOD.items()
          if not (_ordered(row["normal"]) and _ordered(row["warn"])
                  and _ordered(row["alarm"]))]))


# --- KNOWN_GOOD: every id exists in the live-channel registry ------------------

REGISTRY = channels_mod.registry()
check("every KNOWN_GOOD channel id exists in cuore.live.channels' registry",
      all(cid in REGISTRY for cid in known_good.KNOWN_GOOD),
      str([cid for cid in known_good.KNOWN_GOOD if cid not in REGISTRY]))


# --- accessors ------------------------------------------------------------------

check("known_good() returns a copy, not the live row",
      known_good.known_good("engine_rpm") is not known_good.KNOWN_GOOD["engine_rpm"])
check("known_good() of an unknown id is None", known_good.known_good("no_such_channel") is None)
check("all_known_good() returns every row", len(known_good.all_known_good()) ==
      len(known_good.KNOWN_GOOD))

# a spot check on one deliberately UNKNOWN, EVAP-relevant channel -- the
# whole reason observed_ranges() exists
evap_row = known_good.known_good("commanded_evap_purge")
check("commanded_evap_purge is UNKNOWN (no OEM/corroborated purge-duty spec found)",
      evap_row is not None and evap_row["confidence"] == known_good.UNKNOWN)


# --- observed_ranges(): input validation ---------------------------------------

try:
    known_good.observed_ranges("")
    check("observed_ranges rejects an empty VIN", False)
except ValueError:
    check("observed_ranges rejects an empty VIN", True)

# must never raise for a VIN with no logs at all
try:
    empty = known_good.observed_ranges("NO_SUCH_VIN_AT_ALL")
    check("observed_ranges on an unknown VIN returns a dict, not an error",
          isinstance(empty, dict))
    check("observed_ranges on an unknown VIN returns no channels",
          empty == {})
except Exception as exc:  # pragma: no cover - this must never happen
    check("observed_ranges on an unknown VIN returns a dict, not an error", False, repr(exc))

# --- observed_ranges(): against the real corpus, whatever it holds ------------

real = known_good.observed_ranges(VIN)
check("observed_ranges(VIN) returns a dict", isinstance(real, dict))
check("every observed_ranges channel id exists in the channel registry",
      all(cid in REGISTRY for cid in real))
check("every observed_ranges row has min <= p10 <= p50 <= p90 <= max",
      all(row["min"] <= row["p10"] <= row["p50"] <= row["p90"] <= row["max"]
          for row in real.values()),
      str({cid: row for cid, row in real.items()
          if not (row["min"] <= row["p10"] <= row["p50"] <= row["p90"] <= row["max"])}))
check("every observed_ranges row's n matches at least one contributing log",
      all(row["n"] > 0 for row in real.values()))
check("every observed_ranges row cites at least one source log/recording",
      all(row["sources"]["fes_logs"] or row["sources"]["csv_recordings"]
          for row in real.values()))


# --- observed_ranges(): percentile math on a synthetic sample ------------------

synthetic = list(range(1, 101))  # 1..100
synthetic.sort()
check("_quantile(50th) of 1..100 is the median (50.5)",
      known_good._quantile([float(v) for v in synthetic], 0.5) == 50.5)
check("_quantile(0th) of 1..100 is the min",
      known_good._quantile([float(v) for v in synthetic], 0.0) == 1.0)
check("_quantile(100th) of 1..100 is the max",
      known_good._quantile([float(v) for v in synthetic], 1.0) == 100.0)
check("_quantile of a single-element list returns that element",
      known_good._quantile([42.0], 0.9) == 42.0)


# --- _best_match(): the fuzzy-alias matcher used by observed_ranges -----------

names = ["Max. engine speed time", "Maximum engine over-rev RPM", "Engine speed",
        "Desired idle RPM"]
check("_best_match prefers the plain signal name over a qualified variant",
      known_good._best_match(names, "engine speed") == "Engine speed")
check("_best_match returns an exact match when one exists",
      known_good._best_match(["Battery voltage"], "battery voltage") == "Battery voltage")
check("_best_match returns None when nothing matches",
      known_good._best_match(["Fuel level"], "engine speed") is None)
check("_best_match falls back to a disqualified name rather than nothing",
      known_good._best_match(["Desired idle RPM"], "idle rpm") == "Desired idle RPM")


# --- report -------------------------------------------------------------------

print(f"{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILURES:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("OK")
