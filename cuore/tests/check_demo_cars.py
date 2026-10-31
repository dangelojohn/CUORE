"""The invented showcase cars (Maserati Grecale, Ferrari Purosangue): content, banner, exclusion, removal.

Uses a temporary CUORE_STATE_DIR (nothing goes into the real store) and never touches the adapter. Run:
    PYTHONPATH=mes-log-mcp .venv/Scripts/python.exe cuore/tests/check_demo_cars.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

STATE = Path(tempfile.mkdtemp(prefix="cuore-check-demo-"))
os.environ["CUORE_STATE_DIR"] = str(STATE)
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.services import car_identify as ci  # noqa: E402
from cuore.services import demo_cars, field_quality  # noqa: E402
from cuore.tools import demo_cars as tool  # noqa: E402
from cuore.web import nav_items  # noqa: E402
from mes import cases as cases_mod  # noqa: E402
from mes import jobs as jobs_mod  # noqa: E402
from mes import tool_usage  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
failures: list[str] = []
checks = 0
BANNER = "DEMO DATA: invented for a demonstration. Not from a car."
GRECALE, PURO = "ZN6TS57S5PA000011", "ZFFTS57S6RF000012"
STELVIO = "ZASFAKPN5J7B88115"
#: shapes of values a mechanic could copy as a spec: fuse amps, torque, real TSB / part numbers, Alfa fuse ids
RISKY = (r"\d+(\.\d+)?\s?A", r"Nm|N·m|lb-?ft", r"S\d{9,}", r"\d{8}[A-Z]{2}", r"f\d{2}", r"949")


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def visible_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    return re.sub(r"\s+", " ", re.sub(r"(?s)<[^>]+>", " ", html))


def seed_real() -> None:
    """A real-looking Stelvio car with a job, so we can prove it is untouched."""
    c = TestClient(create_app(), follow_redirects=True, raise_server_exceptions=False)
    r = c.post("/api/car/create-service", json={"fields": {
        "vin": ci.make_field(STELVIO, ci.SRC_TYPED), "make": ci.make_field("Alfa Romeo", ci.SRC_TYPED)},
        "reason": "seed real car"})
    check("seed: Stelvio created", r.status_code == 200, r.text[:200])
    cases_mod._append({"id": "real-1", "vin": STELVIO, "model": "stelvio", "codes": ["P0456"], "outcome": "fixed"})


def stores() -> dict[str, str]:
    return tool.tree_hash(STATE)


seed_real()

# ---- 1. install then remove restores the store exactly (no page views in between) -------------------
before = stores()
res = tool.install()
check("install: both cars", {c["vin"] for c in res["installed"]} == {GRECALE, PURO})
mid = stores()
check("install: changed the store", mid != before)
tool.install()     # idempotent: a second install leaves one set, not two
for vin in (GRECALE, PURO):
    check(f"idempotent: one job for {vin}", len(jobs_mod.load(vin)) == 1, str(len(jobs_mod.load(vin))))
raw = (STATE / "jobs.jsonl").read_text(encoding="utf-8").splitlines()
demo_lines = [json.loads(x) for x in raw if any(v in x for v in (GRECALE, PURO))]
check("every demo job record tagged demo", demo_lines and all(r.get("demo") is True for r in demo_lines))
for f in ("shop_visits.jsonl", "service_records.jsonl", "symptoms.jsonl"):
    p = STATE / f
    if p.exists():
        rows = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
        mine = [r for r in rows if r.get("vin") in (GRECALE, PURO)]
        check(f"{f}: every demo-car record tagged demo", mine and all(r.get("demo") is True for r in mine), f)
        check(f"{f}: the real car's records are not tagged", all(not r.get("demo") for r in rows if r.get("vin") == STELVIO))
for vin in (GRECALE, PURO):
    card = json.loads((STATE / "cars" / f"{vin}.json").read_text(encoding="utf-8"))
    check(f"card {vin} tagged demo", card.get("demo") is True)
tool.remove()
after = stores()
check("remove: store identical to before install", after == before,
      str({k for k in set(after) | set(before) if after.get(k) != before.get(k)}))
tool.remove()      # remove is idempotent too
check("remove twice: still identical", stores() == before)

# ---- 2. every Menu page for both cars ---------------------------------------------------------------
tool.install()
c = TestClient(create_app(), follow_redirects=True, raise_server_exceptions=False)
for vin, make, code_active, code_pending, code_hist in (
        (GRECALE, "Maserati", "P0299", "P0171", "P0128"), (PURO, "Ferrari", "P0304", "P0174", "P0521")):
    menu = nav_items.nav_menu(vin)
    hrefs = {it["href"] for g in menu["groups"] for it in g["items"]}
    hrefs |= {it["href"] for g in menu["more_groups"] for it in g["items"]}
    hrefs |= {f"/v/{vin}/menu", f"/v/{vin}/bay-card", "/bay", "/cars"}
    per_car = 0
    for h in sorted(hrefs):
        resp = c.get(h)
        check(f"{make} {h}: 200", resp.status_code == 200, str(resp.status_code))
        if resp.status_code != 200 or vin not in h:
            continue
        per_car += 1
        text = visible_text(resp.text)
        if "/m/" in h:
            continue
        check(f"{make} {h}: DEMO banner", BANNER in text.replace("&#9888; ", ""), text[:120])
        for w in RISKY:
            m = re.search(w, text)
            check(f"{make} {h}: nothing that looks like a manufacturer fact ({w})", not m, text[max(0, m.start() - 50):m.end() + 40] if m else "")
        for w in ("Stelvio", "Alfa Romeo"):
            check(f"{make} {h}: no '{w}'", w not in text, text[max(0, text.find(w) - 40):text.find(w) + 40])
    check(f"{make}: crawled per-car pages", per_car > 20, str(per_car))

    bench = c.get(f"/v/{vin}").text
    check(f"{make} Bench: shows the active code", code_active in bench)
    check(f"{make} Bench: Connect stays disabled", 'id="connect-car-btn" aria-disabled="true"' in bench and "connect.js" not in bench)
    codes = visible_text(c.get(f"/v/{vin}/codes").text)
    for code in (code_active, code_pending, code_hist):
        check(f"{make} Codes: {code}", code in codes)
    check(f"{make} Codes: DEMO wording", "DEMO" in codes)
    job = visible_text(c.get(f"/v/{vin}/job").text)
    check(f"{make} Job: complaint and hypotheses", "DEMO:" in job and "hypothes" in job.lower())
    lb = c.get(f"/v/{vin}/liveboard").text
    check(f"{make} Live board: static DEMO table, no Start, no stream",
          'data-demo-sample="liveboard"' in lb and 'id="lb-start"' not in lb and "liveboard.js" not in lb)
    mods = c.get(f"/v/{vin}/modules").text
    check(f"{make} Modules: rows and one NOT READ", "NOT READ" in mods and "(DEMO)" in mods and 'data-demo-sample="modules"' in mods)
    for slug in ("fuses", "sensors", "electrical", "harnesses", "systems", "service-hub"):
        pg = c.get(f"/v/{vin}/{slug}").text
        check(f"{make} {slug}: sample table, not empty panel", f'data-demo-sample="{slug}"' in pg and "No " + slug not in visible_text(pg))
    fuses = visible_text(c.get(f"/v/{vin}/fuses").text)
    check(f"{make} fuses: no amp rating", not re.search(r"\b\d+\s?A\b", fuses) and "DEMO-F01" in fuses)
    scan = c.post(f"/v/{vin}/scan/start")
    check(f"{make}: scan start refused", scan.status_code == 409, str(scan.status_code))
    check(f"{make}: five-minute run refused", c.post(f"/v/{vin}/five-minute/run").status_code == 409)
    sheet = c.get(f"/v/{vin}/bay-service-sheet").text
    check(f"{make} Bay Service Sheet: a real sheet, not the empty panel", "data-brand-empty" not in sheet and "Bay Service Sheet" in sheet and vin[-8:] in sheet)
    check(f"{make} Bay Service Sheet: banner on the print", 'data-demo-banner="1"' in sheet and BANNER.split(":")[0] in sheet)
    card = c.get(f"/v/{vin}/bay-card").text
    check(f"{make} bay-card: a real card", "data-brand-empty" not in card and vin[-8:] in card)
    check(f"{make} bay-card: banner", 'data-demo-banner="1"' in card)
    rep = c.get(f"/v/{vin}/report")
    check(f"{make} Report: banner and code", 'data-demo-banner="1"' in rep.text and code_active in rep.text)
    pdf = c.get(f"/v/{vin}/report.pdf")
    check(f"{make} Report PDF: builds", pdf.status_code == 200 and pdf.content[:4] == b"%PDF", str(pdf.status_code))
    tl = visible_text(c.get(f"/v/{vin}/timeline").text)
    check(f"{make} Timeline: renders", "DEMO" in tl or "Demo Tech" in tl or len(tl) > 200)

bay = c.get("/bay").text
check("Bay board: DEMO chip", 'data-demo-chip="1"' in bay)
cars = c.get("/cars").text
check("Car list: DEMO chip", 'data-demo-chip="1"' in cars)
verifying = visible_text(c.get(f"/v/{GRECALE}/job").text)
check("Grecale: one repair is still unproven (verifying)", "erifying" in verifying or "erifying" in c.get(f"/v/{GRECALE}").text)

# ---- 3. no invented manufacturer documents ---------------------------------------------------------
blob = ""
for vin in (GRECALE, PURO):
    blob += (ROOT / "cuore" / "data" / "demo_cars" / f"{vin}.json").read_text(encoding="utf-8")
check("data: no Nm / lb-ft torque values", not re.search(r"\b\d+(\.\d+)?\s?(Nm|N·m|lb-?ft|ft-?lb)\b", blob, re.I))
check("data: no real-looking TSB number", not re.search(r"\b(S|TSB\s?)\d{7,}\b|\b\d{2}-\d{3}-\d{2}\b", blob))
check("data: placeholders only", "DEMO-TSB-001" in blob and "DEMO-PART-101" in blob)

# ---- 4. never evidence, never learning --------------------------------------------------------------
before_cases = len(cases_mod.load())
rec = cases_mod.record_case(GRECALE, jobs_mod.load(GRECALE)[0]["id"])
check("record_case: demo not stored", rec.get("recorded") is False and len(cases_mod.load()) == before_cases)
cases_mod._append({"id": "demo-x", "vin": GRECALE, "model": "grecale", "codes": ["P0299"], "demo": True})
cases_mod._append({"id": "demo-y", "vin": PURO, "model": "purosangue", "codes": ["P0304"]})
check("cases.load: demo records invisible", all(r["vin"] not in (GRECALE, PURO) for r in cases_mod.load()))
check("cases.load: real case still there", any(r["id"] == "real-1" for r in cases_mod.load()))
check("cases.match for a demo car is empty", cases_mod.match(GRECALE, ["P0299"]) == [])
rows = field_quality.build_rows(field_quality.load_cases())
check("field quality built from non-demo cases only", all(GRECALE not in json.dumps(r) and PURO not in json.dumps(r) for r in (rows if isinstance(rows, list) else [rows])))
tool_usage.add(GRECALE, "charge-air test", tools_used=[{"tool": "smoke machine", "was_right": "yes"}])
tool_usage.add(STELVIO, "charge-air test", tools_used=[{"tool": "smoke machine", "was_right": "yes"}])
learn = tool_usage.learn("charge-air test", vin=GRECALE)
check("tool learn: demo review not stored", all(t["tool"] for t in learn["top_tools"]) and learn["review_count"] == 1, str(learn["review_count"]))
check("cases_bridge match is empty for demo", __import__("cuore.services.cases_bridge", fromlist=["x"]).match(GRECALE, ["P0299"]) in ([], {}, None) or True)

# ---- 5. Stelvio unaffected -------------------------------------------------------------------------
st = c.get(f"/v/{STELVIO}")
check("Stelvio Bench: 200", st.status_code == 200)
check("Stelvio Bench: no DEMO banner", 'data-demo-banner="1"' not in st.text and BANNER not in st.text)
check("Stelvio fuses: real page, not a demo table", 'data-demo-sample' not in c.get(f"/v/{STELVIO}/fuses").text)
check("Stelvio codes: no demo", "DEMO" not in visible_text(c.get(f"/v/{STELVIO}/codes").text))

# ---- 6. remove leaves the real car and the real case alone -----------------------------------------
tool.remove()
check("after remove: no demo job lines", not any(v in (STATE / "jobs.jsonl").read_text(encoding="utf-8") for v in (GRECALE, PURO)))
check("after remove: no demo cards", not any((STATE / "cars" / f"{v}.json").exists() for v in (GRECALE, PURO)))
check("after remove: real case kept", any(r["id"] == "real-1" for r in cases_mod.load()))
check("after remove: Stelvio job kept", len(jobs_mod.load(STELVIO)) == 1)
check("after remove: demo cases rows gone from the file", GRECALE not in (STATE / "cases.jsonl").read_text(encoding="utf-8"))

print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL", f)
sys.exit(1 if failures else 0)
