"""Checks for cuore/services/dtc_text.py (MES-printed code text). Run:
.venv/Scripts/python.exe -X utf8 cuore/tests/check_dtc_text.py
"""
from __future__ import annotations

import json, os, sys, tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-dtctext-")
os.environ["CUORE_STATE_DIR"] = _TMP
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from cuore.services import dtc_text, find, mes_bridge  # noqa: E402

failures: list[str] = []
n = 0


def check(label, cond, detail=""):
    global n
    n += 1
    if not cond:
        failures.append(f"{label} {detail}")


SCAN = """Body / BCM (Body Computer Module)
Body Computer
ISO Code: 00 11 22 33 44
VIN code: ZASFAKPN5J7B88115
Errors found:
B101D-15 - Windscreen heated washers - Short to +V or open circuit
P0456-00
"""
rows = dtc_text.rows_from_scan_text(SCAN, "SCAN_2610230112.txt", "2026-10-23 01:12:00")
check("only the code with printed text gets a row", [r["code"] for r in rows] == ["B101D"], str(rows))
check("row fields", rows and rows[0]["source_kind"] == "mes_display" and rows[0]["failure_type"] == "15"
      and rows[0]["source_log"] == "SCAN_2610230112.txt")
dtc_text.path_for().parent.mkdir(parents=True, exist_ok=True)
dtc_text.path_for().write_text(json.dumps(dtc_text.merge(rows)), encoding="utf-8")
check("file under state_dir/knowledge/949", dtc_text.path_for() == Path(_TMP, "knowledge", "949", "dtc_text.json"))
hit = dtc_text.lookup("B101D-15")
check("lookup with tag", hit and hit["source_tag"] == "MES display" and "washers" in hit["description"])
check("bare code with one text resolves", dtc_text.lookup("B101D") is not None)
check("unknown code blank", dtc_text.lookup("P0456") is None and dtc_text.lookup("P0456-00") is None)
check("other failure type of a known code not invented", dtc_text.lookup("B101D-99") is None)
check("garbage blank", dtc_text.lookup("hello") is None)

# precedence: manufacturer beats mes_display; forum does not
base = dict(rows[0])
manu = dict(base, text="Manufacturer wording", source_kind="manufacturer")
forum = dict(base, text="Forum wording", source_kind="forum")
dtc_text.path_for().write_text(json.dumps(dtc_text.merge([manu])), encoding="utf-8")
check("manufacturer replaces mes_display", dtc_text.lookup("B101D-15")["description"] == "Manufacturer wording")
dtc_text.path_for().write_text(json.dumps(dtc_text.merge([forum])), encoding="utf-8")
check("forum does not replace manufacturer", dtc_text.lookup("B101D-15")["description"] == "Manufacturer wording")
dtc_text.path_for().write_text(json.dumps(dtc_text.merge(rows)), encoding="utf-8")
dtc_text.path_for().write_text(json.dumps(dtc_text.merge([forum])), encoding="utf-8")
check("forum does not replace mes_display", dtc_text.lookup("B101D-15")["description"] != "Forum wording")

# display wiring (fresh file with the MES-printed row only)
dtc_text.path_for().write_text(json.dumps(rows), encoding="utf-8")
d = mes_bridge.describe_dtc("B101D-15")
check("describe_dtc falls back to printed text", "washers" in d["description"] and d["source_tag"] == "MES display")
try:
    mes_bridge.describe_dtc("P0456")
    check("describe_dtc unknown raises", False)
except Exception:
    check("describe_dtc unknown raises", True)
res = find._codes("B101D-15", "")
check("find shows text and source tag", res and "washers" in res[0]["says"] and "MES display" in res[0]["says"], str(res))
res = find._codes("P0456", "")
check("find unknown stays 'Fault code'", res and res[0]["says"] == "Fault code")

print(f"{n} checks, {len(failures)} failed")
for f in failures:
    print("FAIL", f)
sys.exit(1 if failures else 0)
