"""Checks for cuore/services/job_log.py (organised repair log) on synthetic actions.

Run:  .venv/Scripts/python.exe cuore/tests/check_job_log.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-joblog-")
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from cuore.services.job_log import faults_of, job_log_context, log_view, summarise  # noqa: E402

failures: list[str] = []
n = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global n
    n += 1
    if not cond:
        failures.append(f"{label} -- {detail}" if detail else label)


def act(i, kind, text, day, ref=None):
    return {"id": f"a{i}", "kind": kind, "text": text, "ref": ref, "at": f"{day}T10:00:00",
            "event_date": day, "effective_date": day, "date_uncertain": False}


actions = [act(1, "repair", "Replaced the ESIM valve. P0455 was the trigger.", "2026-10-01"),
           act(2, "part", "Fitted new gas cap.", "2026-10-02"),
           act(3, "test", "Smoke test showed no leak. P0440 still stored.", "2026-10-03"),
           act(4, "inspection", "Hoses inspected, all seated.", "2026-10-04"),
           act(5, "note", "Owner says the lamp comes on after refuelling (P0456-00).", "2026-10-05",
               {"kind": "bulletin", "id": "TSB-1", "label": "TSB-1"})]
codes = [["P0440-00"], ["P0440-00"], [], ["P0440-00"], []]     # codes listed before each MES clear
for i, cs in enumerate(codes):
    d = f"2026-09-{10 + i:02d}"
    tail = ("Codes present before the clear: " + ", ".join(cs) + ".") if cs else \
        "Codes present before the clear: none listed in this log."
    actions.append(act(10 + i, "clear", f"MES cleared fault codes (SCAN_26091{i}.txt). {tail}", d))
actions.append(act(99, "note", "x " * 200 + "end", "2026-10-06"))
job = {"vin": "VINTEST", "opened_at": "2026-09-01T08:00:00", "closed_at": None,
       "actions": actions, "retracted_actions": [act(50, "note", "retracted nonsense", "2026-10-07")]}
today = date(2026, 10, 10)

v = log_view(job, today=today)
cnt = {c["id"]: c["count"] for c in v["chips"]}
check("counts per kind", cnt == {"": 11, "repair": 2, "test": 1, "inspection": 1, "clear": 5,
                                 "note": 2, "reading": 0}, str(cnt))
check("chip labels are plain", [c["label"] for c in v["chips"]][:3] == ["All", "Repairs & parts", "Tests"])
check("retracted hidden but counted",
      v["retracted_count"] == 1 and "retracted nonsense" not in str(v["rows"]) and v["total"] == 11)

g = [r for r in v["rows"] if r["group"]]
check("5 clears fold into one group", len(g) == 1 and g[0]["count"] == 5 and len(g[0]["entries"]) == 5)
check("group date span", g and (g[0]["first"], g[0]["last"]) == ("2026-09-10", "2026-09-14"))
check("group label", g and g[0]["label"].startswith("5 clears, 2026-09-10 → 2026-09-14"), g[0]["label"])
# comparable pairs: (c0,c1) both listed -> returned; (c1,c2) c2 none -> not; (c2,c3) -> not; (c3,c4) -> not
check("returned computed from data", g and (g[0]["returned"], g[0]["returned_of"]) == (1, 4),
      str(g and (g[0]["returned"], g[0]["returned_of"])))
check("lines fewer than entries", v["lines"] == 11 - 5 + 1, str(v["lines"]))

f = log_view(job, kind="test", today=today)
check("kind filter", f["lines"] == 1 and f["rows"][0]["chip"] == "test" and f["matched"] == 1)
check("kind filter keeps whole-log counts", {c["id"]: c["count"] for c in f["chips"]}["clear"] == 5)
check("bad kind ignored", log_view(job, kind="zzz", today=today)["kind"] is None)
check("fault filter", [r["id"] for r in log_view(job, fault="P0440", today=today)["rows"] if not r["group"]] == ["a3"]
      or log_view(job, fault="P0440", today=today)["matched"] == 7)
check("text search", log_view(job, q="smoke", today=today)["matched"] == 1)
check("search multiword AND", log_view(job, q="smoke valve", today=today)["matched"] == 0)

nw = [r["id"] for r in log_view(job, kind="repair", sort="newest", today=today)["rows"]]
od = [r["id"] for r in log_view(job, kind="repair", sort="oldest", today=today)["rows"]]
check("newest sort", nw == ["a2", "a1"], str(nw))
check("oldest sort", od == ["a1", "a2"], str(od))
kd = [r["chip"] for r in log_view(job, sort="kind", today=today)["rows"]]
check("kind sort groups repair first", kd[:2] == ["repair", "repair"], str(kd))
fs = [r.get("faults") for r in log_view(job, sort="fault", kind="test", today=today)["rows"]]
check("fault sort", fs == [["P0440"]])

check("fault extraction", faults_of("P0455-00 and p0440 U1713-2F, B1176, C141B-97 P0455") ==
      ["P0455", "U1713", "B1176", "C141B"], str(faults_of("P0455-00 and p0440 U1713-2F, B1176, C141B-97 P0455")))
ent = {e["id"]: e for e in log_view(job, today=today)["rows"] if not e["group"]}
check("entry fault from text and ref", ent["a5"]["faults"] == ["P0456"] and ent["a1"]["faults"] == ["P0455"])
check("per-fault first/last", {x["code"]: (x["first"], x["last"]) for x in v["faults"]}["P0440"][0] == "2026-09-10")

long = ent["a99"]
check("summary max length, whole words", len(long["summary"]) <= 140 and long["long"] and long["text"].endswith("end"))
check("summary keeps numbers", summarise("Engine idle 414 s, coolant 64 C. Next sentence.") == "Engine idle 414 s, coolant 64 C.")
check("summary not cut mid-word", not summarise("alpha " * 40).rstrip("…").endswith("alph"))
check("days ago and event date", ent["a1"]["days_ago"] == "9 days ago" and ent["a1"]["date"].startswith("2026-10-01"))
check("job open N days", v["open_days"] == 39 and v["span_first"] == "2026-09-10" and v["span_last"] == "2026-10-06")
check("ref link only where a page exists", ent["a5"]["ref"]["href"] == "/tsb?vin=VINTEST" and ent["a1"]["ref"] is None)

ctx = job_log_context(job, {"log_kind": "clear", "log_sort": "oldest", "log_q": "", "log_fault": ""})
check("context function", ctx["log"]["kind"] == "clear" and ctx["log"]["sort"] == "oldest")
check("chip links are plain GET", "log_kind=test" in v["chips"][2]["href"] and v["chips"][2]["href"].endswith("#job-log"))

try:   # the partial renders against this context
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(str(ROOT / "cuore" / "web" / "templates")), autoescape=True)
    env.globals["static_url"] = lambda p: "/static/" + p
    html = env.get_template("_job_log.html").render(**job_log_context(job, {}))
    check("partial renders groups, chips and search", "jl-group" in html and "Repairs &amp; parts" in html
          and 'name="log_q"' in html and "retracted nonsense" not in html)
except Exception as exc:   # noqa: BLE001
    check("partial renders", False, repr(exc))

print()
if failures:
    print(f"{len(failures)}/{n} failed:")
    for x in failures:
        print("  -", x)
    sys.exit(1)
print(f"all {n} checks passed")
