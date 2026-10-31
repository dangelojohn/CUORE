"""Add Service screens ("/add"): page, Menu, no network option, typed-VIN decode to the
card, field sources, the live NDJSON path with a simulated adapter, create-service,
no duplicate car. Fakes and a temporary state directory only; never COM3, and never
the real store (RULE 11: simulated data must not reach it).

The JavaScript is not executed here (no JS engine in this environment); its wiring is
checked as text and the data it renders is checked at the API.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_add_service.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-addsvc-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ["CUORE_AUTOSTART"] = "0"
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "obd2-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import interlock  # noqa: E402
from cuore.live.config import state_dir  # noqa: E402
from cuore.services import car_identify as ci  # noqa: E402

interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running", "label": None}
failures: list[str] = []
checks = 0


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# RULE 11: every write below lands in the temporary directory.
check("state directory is the temporary one", str(state_dir()).startswith(STATE), str(state_dir()))

from mes import jobs as jobs_mod, shop as shop_mod  # noqa: E402

NEW = "ZASFAKPN5J7B88777"      # not on file anywhere; invented for this test
READ_VIN = "ZASFAKPN5J7B88778"  # the simulated adapter reports this one
UNKNOWN_WMI = "1HGCM82633A004352"
c = TestClient(create_app(), follow_redirects=False, raise_server_exceptions=False)

# --- page, Menu, wiring ------------------------------------------------------------------------
r = c.get("/add")
check("/add renders", r.status_code == 200, str(r.status_code))
page = r.text
check("S1 question and the two tiles", "How do we find the car?" in page and 'data-act="plug"' in page
      and 'data-act="type"' in page and "Read this car" in page)
check("no camera or photo tile, not even disabled", not re.search(r"camera|photo|scan the|ocr", page, re.I))
check("Menu is populated and offers Add Service at /add",
      'data-nav="home"' in page and 'data-nav="start"' in page and 'href="/add"' in page and "Add Service" in page)
check("page loads its own css and js", "add_service.css" in page and "add_service.js" in page)
check("no-script fallback keeps /start reachable", 'href="/start"' in page.split("<noscript>")[1].split("</noscript>")[0])
check("make picker built from the brand data", all(f'data-make="{n}"' in page for n in ("Alfa Romeo", "Maserati", "Ferrari")))
check("third tile: Choose, pick from the lists, same icon style", 'data-act="choose"' in page and "Pick from the lists" in page
      and page.count('class="as-pic"') == 3 and page.count('stroke-width="3"') >= 3)
check("Choose screen: four drop-downs in order, VIN field, VIN line, Continue",
      [page.find(i) for i in ('id="as-c-brand"', 'id="as-c-model"', 'id="as-c-year"', 'id="as-c-engine"', 'id="as-cvin"')]
      == sorted(page.find(i) for i in ('id="as-c-brand"', 'id="as-c-model"', 'id="as-c-year"', 'id="as-c-engine"', 'id="as-cvin"'))
      and page.count("<select") == 4 and "Choose the car" in page and "The VIN files this car's records." in page
      and 'id="as-choose-go"' in page)
check("Choose: later lists start disabled", all(re.search(rf'id="{i}"[^>]*disabled', page) for i in ("as-c-model", "as-c-year", "as-c-engine")))
check("five reason tiles", len(re.findall(r'class="as-reason"', page)) == 5)
check("/start still works", c.get("/start").status_code == 200)
check("Add a car card on the car list points at /add for its brand",
      'href="/add?brand=alfa"' in c.get("/cars?brand=alfa").text and 'href="/start"' not in c.get("/cars?brand=alfa").text.split("car-grid")[1].split("</a>")[0])
check("landing stays the brand picker", c.get("/").status_code == 200 and c.get("/").text.count('class="brand-tile') == 3)

# --- no online option, no recall check ---------------------------------------------------------
js = (ROOT / "cuore/web/static/add_service.js").read_text(encoding="utf-8")
css = (ROOT / "cuore/web/static/add_service.css").read_text(encoding="utf-8")
tpl = (ROOT / "cuore/web/templates/add_service.html").read_text(encoding="utf-8")
for word in ("online", "lookup", "nhtsa", "vpic", "recall", "xmlhttp"):
    check(f"nothing about '{word}' in page, script or style", word not in (page.split("</header>", 1)[-1] + js + css + tpl).lower(), word)
urls = set(re.findall(r'(?:fetch|assign)\(\s*["\']([^"\']+)', js))
check("script calls only this server", all(u.startswith(("/api/car/", "/add/")) for u in urls) and "http" not in " ".join(urls), str(urls))
check("backend lookup stays off", ci.ONLINE_LOOKUP_ENABLED is False and ci.online_lookup(NEW, enabled=True)["performed"] is False)

# --- typed VIN: decode reaches the card, sources shown -----------------------------------------
d = c.post("/api/car/identify", json={"vin": NEW, "read_car": False})
card = d.json()["card"]
f = card["fields"]
check("typed-VIN decode answers with no events and read-only", d.status_code == 200 and d.json()["events"] == [] and card["read_only"])
check("card: make and model decoded", f["make"]["value"] == "Alfa Romeo" and f["model"]["value"] == "Stelvio"
      and f["make"]["source"] == ci.SRC_DECODED and f["model_year"]["value"] == 2018)
check("card: typed VIN is 'typed in'", f["vin"]["source"] == ci.SRC_TYPED and f["vin"]["value"] == NEW)
check("card: unverified decoded field says so", f["plant"]["verified"] is False and "UNVERIFIED" in f["plant"]["detail"])
check("card: market unknown, not guessed", f["market"]["value"] is None and f["market"]["source"] == ci.SRC_NONE)
check("card: no engine or trim invented", "engine" not in f and "trim" not in f)
check("script knows every backend source string", all(s in js for s in ci.SOURCES))
check("script has the four chips", all(w in js for w in ('"Read"', '"Decoded"', '"Entered"', '"Unknown"')))
check("script words for an unidentified model", "model not identified" in js and "Car not identified" in js)
unk = c.post("/api/car/identify", json={"vin": UNKNOWN_WMI, "read_car": False}).json()["card"]["fields"]
check("unknown WMI: make stays unknown (picker case)", unk["make"]["value"] is None and 'id="as-make-picker"' in tpl)
bad = c.post("/api/car/identify", json={"vin": "ZASFAKPN5J7B8877O", "read_car": False}).json()["card"]
check("typed bad characters reported by the backend", not bad["validation"]["ok"] and bad["validation"]["errors"])
chk = ci.validate_vin(NEW)
check("check digit is only a warning for this market", chk["ok"] and (chk["warnings"] or chk["check_digit"]["valid"]))
check("script blocks only on backend errors, shows warnings", "v.ok" in js and "v.warnings" in js)

# --- the live path with a simulated adapter ----------------------------------------------------


class FakeProbe:
    """Same read-only methods as the real probe; touches no port."""
    def __init__(self, silent=("ABS",), vin_error=""):
        self.silent, self.vin_error, self.calls = set(silent), vin_error, []

    def cable(self): self.calls.append("cable"); return "none"
    def mes_running(self): self.calls.append("mes_running"); return False
    def bus_ready(self, bus, cable): self.calls.append("bus_ready"); return (True, "")
    def read_vin(self):
        self.calls.append("read_vin")
        return {"error": self.vin_error} if self.vin_error else {"vin": READ_VIN}
    def modules(self, bus):
        self.calls.append("modules")
        return [{"code": k, "name": n, "usable": True, "present": True, "target": k}
                for k, n in (("ECM", "Engine"), ("ABS", "Brakes"), ("BCM", "Body"))]
    def identity(self, code, vin, confirm):
        self.calls.append("identity:" + code)
        if code in self.silent:
            return {"error": "NOT READ: no answer from the module, do not treat as clean"}
        return {"fields": {"F190": {"ascii": vin, "bytes": ["41"]}, "F188": {"ascii": "SW-" + code, "bytes": ["41"]}}}


made: list[FakeProbe] = []
real_probe = ci.CarProbe
ci.CarProbe = lambda: made.append(FakeProbe()) or made[-1]  # the real one would open the adapter
try:
    s = c.post("/api/car/identify", json={"read_car": True, "stream": True})
    events = [json.loads(x) for x in s.text.splitlines() if x.strip()]
    kinds = [e["event"] for e in events]
    check("stream is NDJSON, one event per line", s.status_code == 200 and "ndjson" in s.headers["content-type"], s.headers.get("content-type", ""))
    check("events arrive in order: start, vin, modules one by one, done",
          kinds == ["start", "vin", "module", "module", "module", "done"], str(kinds))
    check("simulated adapter only", len(made) == 1 and made[0].calls[0] == "cable")
    done = events[-1]["card"]
    check("VIN READ, modules 2 of 3, silent module has its reason",
          done["fields"]["vin"]["source"] == ci.SRC_READ and done["fields"]["modules_answered"]["value"] == "2 of 3"
          and "NOT READ" in done["silent_modules"][0]["reason"])
    made.clear()
    bare = [json.loads(x) for x in c.post("/api/car/identify", json={"read_car": True, "stream": True}).text.splitlines()]
    ci.CarProbe = lambda: FakeProbe(silent=("ECM", "ABS", "BCM"))
    allsilent = [json.loads(x) for x in c.post("/api/car/identify", json={"read_car": True, "stream": True}).text.splitlines()]
    cd = allsilent[-1]["card"]
    check("VIN read but every module silent: decoded fields still arrive, modules not found",
          cd["fields"]["model"]["value"] == "Stelvio" and cd["fields"]["software_ids"]["source"] == ci.SRC_NONE
          and len(cd["silent_modules"]) == 3)
    ci.CarProbe = lambda: FakeProbe(vin_error="ADAPTER/BUS ERROR: no answer")
    novin = [json.loads(x) for x in c.post("/api/car/identify", json={"read_car": True, "stream": True}).text.splitlines()]
    check("no VIN from the car: vin step carries the reason, card has no VIN",
          novin[1]["answered"] is False and novin[1]["reason"] and novin[-1]["card"]["fields"]["vin"]["source"] == ci.SRC_NONE)
finally:
    ci.CarProbe = real_probe
check("test never left the simulated probe in place", ci.CarProbe is real_probe)
check("script reads the stream and posts read_car true only from the Plug in tile",
      js.count("read_car: true") == 1 and js.count("read_car: false") == 1 and "stream: true" in js)
check("script never sets confirm or a bus (guarded defaults only)", "confirm" not in js and '"bus"' not in js)

# --- story, art --------------------------------------------------------------------------------
st = c.get(f"/add/story?vin={NEW}").json()
check("unknown VIN: first visit, nothing invented", st["first_visit"] is True and st["last_visit"] is None and st["open_jobs"] == [])
check("story needs a VIN", c.get("/add/story?vin=").status_code == 400)
check("art for a model that has it", "ink" in c.get("/add/art?model=Stelvio").json())
check("no art: 404, no stand-in", c.get("/add/art?model=Quadrifoglio").status_code == 404 and c.get("/add/art").status_code == 404)

# --- create-service ----------------------------------------------------------------------------
fields = {**f, "vin": ci.make_field(NEW, ci.SRC_TYPED)}
fields["engine"] = {"value": "2.0 turbo", "source": ci.SRC_TYPED, "detail": "entered by the technician"}
r1 = c.post("/api/car/create-service", json={"fields": fields, "reason": "shudder: at 40 km/h", "odometer": 61234, "unit": "km"})
j1 = r1.json()
check("new car: created, job opened", r1.status_code == 200 and j1["created"] and not j1["existing_car"] and bool(j1["job_id"]), str(j1)[:200])
check("odometer recorded with its unit", j1["odometer"]["value"] == 61234 and j1["odometer"]["unit"] == "km")
check("entered field kept as ENTERED", j1["card"]["fields"]["engine"]["source"] == ci.SRC_TYPED)
# The job page needs scan logs in the corpus (existing behaviour of every /v/{vin} page, same for /start),
# so the landing check uses a VIN the corpus already holds; its job lives only in the temporary store.
ON_CORPUS = "ZASFAKPN5J7B88115"
check("corpus VIN is not already in the temporary store", not shop_mod.load(ON_CORPUS))
jc = c.post("/api/car/create-service", json={"fields": {"vin": {"value": ON_CORPUS, "source": ci.SRC_READ}}, "reason": "noise"}).json()
check("job page is where the button lands (car with logs)", c.get(f"/v/{jc['vin']}/job").status_code == 200)
check("reason stored on the job", jobs_mod.current(NEW)["complaint"] == "shudder: at 40 km/h")
check("title wording stored with the visit", shop_mod.load(NEW)[0]["vehicle"] == "Alfa Romeo Stelvio 2018", str(shop_mod.load(NEW)[0].get("vehicle")))
check("car appears under its brand", f'href="/v/{NEW}/menu"' in c.get("/cars?brand=alfa").text)

r2 = c.post("/api/car/create-service", json={"fields": fields, "reason": "again", "odometer": None})
j2 = r2.json()
check("same VIN again: existing car, existing job, no duplicate",
      j2["existing_car"] and not j2["created"] and j2["already_open"] and j2["job_id"] == j1["job_id"]
      and len(shop_mod.load(NEW)) == 1 and len(jobs_mod.load(NEW)) == 1)
check("skipped odometer is flagged", j2["odometer_missing"] is True)
for need in ("existing_car", "already_open", "created", "odometer_missing", "warnings"):
    check(f"script reads '{need}' from the answer", need in js)
check("script says no duplicate was made", "No duplicate" in js)
st2 = c.get(f"/add/story?vin={NEW}").json()
check("story now reads from CUORE's own records",
      st2["on_file"] and not st2["first_visit"] and st2["last_visit"]["reason"] == "shudder: at 40 km/h"
      and len(st2["open_jobs"]) == 1)

rej = c.post("/api/car/create-service", json={"fields": {"vin": {"value": "BAD", "source": ci.SRC_TYPED}}})
check("bad VIN refused with a readable reason, nothing created", rej.status_code == 400 and not shop_mod.load("BAD"), rej.text[:120])

# --- a never-scanned car lands on real pages, with nothing claimed about it ---------------------
for path in ("/job", "", "/liveboard", "/report", "/bay-sheet", "/modules", "/codes"):
    rr = c.get(f"/v/{NEW}{path}")
    check(f"new car: /v/VIN{path} renders", rr.status_code == 200, str(rr.status_code))
check("new car is on its brand's car list", NEW in c.get("/cars?brand=alfa").text)
check("a VIN nobody opened still answers 404", c.get(f"/v/{READ_VIN}/job").status_code == 404)

# --- Choose: the pick lists, the page wiring, and a chosen field through create-service -----------
choices = json.loads((ROOT / "cuore/data/car_choices.json").read_text(encoding="utf-8"))
OTHER = choices["other"]
brand_names = [b["name"] for b in json.loads((ROOT / "cuore/data/brands.json").read_text(encoding="utf-8"))["brands"]]
check("pick list says it is not evidence", "not evidence" in choices["_about"])
check("pick list covers exactly the brands in brands.json, same order", [b["name"] for b in choices["brands"]] == brand_names, str(brand_names))
this_year = __import__("datetime").date.today().year
for b in choices["brands"]:
    ms = b["models"]
    check(f"{b['name']}: models listed and the list ends with Other", len(ms) > 1 and ms[-1]["name"] == OTHER and ms[-1].get("other") is True)
    check(f"{b['name']}: no duplicate model", len({m["name"] for m in ms}) == len(ms))
    for m in ms:
        eng = m["engines"]
        check(f"{b['name']} {m['name']}: engines end with the Other option, no duplicates",
              eng[-1] == OTHER and eng.count(OTHER) == 1 and len(set(eng)) == len(eng) and (len(eng) > 1 or m.get("other")))
        ly = m["last_year"]
        check(f"{b['name']} {m['name']}: years sane",
              isinstance(m["first_year"], int) and 1950 <= m["first_year"] <= this_year + 1
              and (ly is None or (isinstance(ly, int) and m["first_year"] <= ly <= this_year + 1)))
        check(f"{b['name']} {m['name']}: says where it came from", bool(str(m.get("basis", "")).strip()))
by = {b["name"]: {m["name"]: m for m in b["models"]} for b in choices["brands"]}
check("Stelvio 2018- and Giulia 2017- (North America), Levante to 2024 as the repo records",
      by["Alfa Romeo"]["Stelvio"]["first_year"] == 2018 and by["Alfa Romeo"]["Giulia"]["first_year"] == 2017
      and by["Maserati"]["Levante"]["last_year"] == 2024)
check("the page carries the pick lists inline, no fetch", 'id="as-choices"' in page and "/add/choices" not in js)
check("script has the Choose wiring and the same Other wording as the data",
      f'"{OTHER}"' in js and "chosen from the list" in js and "yearsFor" in js and "choiceConflict" in js and "wireVin" in js
      and 'data-act="choose"' in tpl and "openChoose" in js)
check("Choose and Type share the one VIN check (still a single read_car false)", js.count("wireVin(") == 3)  # definition + two uses

# A chosen field is stored as typed in ("chosen from the list") and beats the VIN decode, even when they disagree.
CHOSEN_VIN = "ZASFAKPN5J7B88779"   # decodes to Alfa Romeo Stelvio 2018; invented for this test
dec = c.post("/api/car/identify", json={"vin": CHOSEN_VIN, "read_car": False}).json()["card"]["fields"]
picked = {k: {"value": v, "source": ci.SRC_TYPED, "detail": "chosen from the list", "verified": True}
          for k, v in (("make", "Alfa Romeo"), ("model", "Giulia"), ("model_year", 2019), ("engine", "2.0L turbo I4"))}
rc = c.post("/api/car/create-service", json={"fields": {**dec, **picked}, "reason": "service"})
jc2 = rc.json()
cf = jc2["card"]["fields"]
check("chosen service opened", rc.status_code == 200 and jc2["created"], rc.text[:160])
check("chosen model beats the decode (Giulia, not Stelvio) and stays ENTERED with its detail",
      cf["model"]["value"] == "Giulia" and cf["model"]["source"] == ci.SRC_TYPED and cf["model"]["detail"] == "chosen from the list")
check("chosen year and engine stay ENTERED too", cf["model_year"]["value"] == 2019 and cf["model_year"]["source"] == ci.SRC_TYPED
      and cf["engine"]["value"] == "2.0L turbo I4" and cf["engine"]["source"] == ci.SRC_TYPED)
check("fields not chosen keep their decode", cf["plant"]["source"] == ci.SRC_DECODED and cf["vin"]["value"] == CHOSEN_VIN)
check("title wording uses the choice", shop_mod.load(CHOSEN_VIN)[0]["vehicle"] == "Alfa Romeo Giulia 2019", str(shop_mod.load(CHOSEN_VIN)[0].get("vehicle")))
nolst = {k: v for k, v in picked.items() if k != "engine"}
rn = c.post("/api/car/create-service", json={"fields": {**dec, **nolst, "vin": ci.make_field("ZASFAKPN5J7B88780", ci.SRC_TYPED)}, "reason": "service"}).json()
check("engine left at Not sure stays unknown, not invented", "engine" not in rn["card"]["fields"] or rn["card"]["fields"]["engine"]["value"] is None)

# --- look and feel rules -----------------------------------------------------------------------
check("css uses tokens: no hex colours, no px font sizes", not re.search(r"#[0-9a-fA-F]{3,8}\b|font-size:\s*\d+px", css))
check("accent used on the primary button only", css.count("var(--accent)") == 2 and re.search(r"\.as-go \{[^}]*var\(--accent\)", css) is not None
      and "var(--accent-ink)" in css)
check("display weight 300 token and 44px+ targets", "var(--fw-light)" in css and css.count("min-height: 64px") >= 6 and "var(--tap)" in css)
check("phone width: single column, nothing forces width", "max-width: 640px" in css and "minmax(min(100%" in css)
check("reduced motion respected", "prefers-reduced-motion" in css)
check("script escapes by construction (no innerHTML)", "innerHTML" not in js)

# --- the brand path: /add?brand=maserati and ferrari ------------------------------------------------
def test_vin(prefix8: str, tail8: str) -> str:
    """A TEST VIN: invented here, with a correct position-9 check digit (49 CFR 565.15). Not a real car."""
    tr = dict(zip("ABCDEFGH", range(1, 9))); tr.update(dict(zip("JKLMN", range(1, 6)))); tr.update({"P": 7, "R": 9})
    tr.update(dict(zip("STUVWXYZ", range(2, 10)))); tr.update({str(d): d for d in range(10)})
    wts = (8, 7, 6, 5, 4, 3, 2, 10, 0, 9, 8, 7, 6, 5, 4, 3, 2)
    raw = prefix8 + "0" + tail8
    total = sum(tr[ch] * w for ch, w in zip(raw, wts))
    chk = "X" if total % 11 == 10 else str(total % 11)
    return raw[:8] + chk + raw[9:]


MAS_VIN = test_vin("ZN6TS57S", "LA000011")   # TEST VIN, invented for this check: Maserati ZN6 rule
FER_VIN = test_vin("ZFFTS57S", "LF000012")   # TEST VIN, invented for this check: Ferrari ZFF rule
check("test VINs are 17 characters with a correct check digit",
      all(len(v) == 17 and ci.validate_vin(v)["ok"] and ci.validate_vin(v)["check_digit"]["valid"] for v in (MAS_VIN, FER_VIN)), f"{MAS_VIN} {FER_VIN}")
for key, name in (("maserati", "Maserati"), ("ferrari", "Ferrari")):
    pg = c.get(f"/add?brand={key}")
    check(f"/add?brand={key} renders", pg.status_code == 200, str(pg.status_code))
    check(f"/add?brand={key}: page is themed {key}", f'<html lang="en" data-marque="{key}"' in pg.text and f'data-brand="{key}"' in pg.text)
    check(f"/add?brand={key}: logo slot names {name}", f"{name} badge" in pg.text)
    check(f"/add?brand={key}: its mark is in the page for the art area", f'data-brand-key="{key}"' in pg.text and f'data-brand-name="{name}"' in pg.text)
    check(f"/add?brand={key}: Menu follows (Add Service still offered)", 'data-nav="home"' in pg.text and "Add Service" in pg.text)
    cl = c.get(f"/cars?brand={key}").text
    check(f"/cars?brand={key}: Add Service links to its brand", f'href="/add?brand={key}"' in cl)
    check(f"/cars?brand={key}: honest test note, empty state, centred layout",
          "Test: no real vehicle data for this brand yet" in cl and f"No {name} cars yet" in cl and "cars-sole" in cl)
odd = c.get("/add?brand=nonsense")
check("unknown brand: today's Alfa page", odd.status_code == 200 and '<html lang="en" data-marque="alfa"' in odd.text and 'data-brand=""' in odd.text)
check("no brand: today's Alfa page", 'data-brand=""' in page and '<html lang="en" data-marque="alfa"' in page)
check("script preselects the page brand on Choose and keeps the model list ready",
      'choose: { brand: pageName' in js and 'data-brand' in js and "setTheme" in js)
check("script: logo disc for Maserati and Ferrari, never the Stelvio art; Alfa keeps its message",
      "NO_DRAWING = { maserati: true, ferrari: true }" in js and "cloneNode(true)" in js and "No drawing yet for the" in js)
check("script: after Open service job every brand goes to /menu, not /job", '"/menu"' in js and '"/job"' not in js)
check("script: VIN of another marque warns naming both; unknown WMI uses the page brand as entered",
      "decodes to" in js and "was started under" in js and "the brand this service was started under" in js)

mas_dec = c.post("/api/car/identify", json={"vin": MAS_VIN, "read_car": False}).json()["card"]["fields"]
fer_dec = c.post("/api/car/identify", json={"vin": FER_VIN, "read_car": False}).json()["card"]["fields"]
check("Maserati VIN: make decoded, model NOT invented", mas_dec["make"]["value"] == "Maserati" and mas_dec["model"]["value"] is None)
check("Ferrari VIN: make decoded but flagged unverified, model NOT invented",
      fer_dec["make"]["value"] == "Ferrari" and fer_dec["make"]["verified"] is False and "UNVERIFIED" in fer_dec["make"]["detail"]
      and fer_dec["model"]["value"] is None)
check("a model with no WMI rule is never filled in", all(f_["model"]["value"] is None for f_ in (mas_dec, fer_dec)))

opened = {}
for vin, key, dec, model in ((MAS_VIN, "maserati", mas_dec, "Quattroporte"), (FER_VIN, "ferrari", fer_dec, "Roma")):
    picked = {"make": ci.make_field(key.capitalize(), ci.SRC_TYPED), "model": ci.make_field(model, ci.SRC_TYPED)}
    ro = c.post("/api/car/create-service", json={"fields": {**dec, **picked}, "reason": "service"})
    jo = ro.json()
    opened[key] = jo
    check(f"{key}: service opened, new car", ro.status_code == 200 and jo["created"] and not jo["existing_car"], ro.text[:160])
    check(f"{key}: a chosen model stays ENTERED", jo["card"]["fields"]["model"]["value"] == model and jo["card"]["fields"]["model"]["source"] == ci.SRC_TYPED)
    check(f"{key}: Menu page of the new car renders (where the button lands)", c.get(f"/v/{vin}/menu").status_code == 200)
    again = c.post("/api/car/create-service", json={"fields": {**dec, **picked}, "reason": "again"}).json()
    check(f"{key}: same VIN again is the existing car", again["existing_car"] and again["already_open"] and not again["created"])
    lst = c.get(f"/cars?brand={key}").text
    grid = lst.split("car-grid")[1]
    check(f"{key}: car is on its own brand's list, linking to its Menu", f'href="/v/{vin}/menu"' in lst)
    check(f"{key}: card is clean: no art, no Stelvio, state word NOT READ",
          "<svg" not in grid and "Stelvio" not in lst and "NOT READ" in lst)
    other = "ferrari" if key == "maserati" else "maserati"
    check(f"{key}: not on the {other} or Alfa list", vin not in c.get(f"/cars?brand={other}").text and vin not in c.get("/cars?brand=alfa").text)
check("the two test cars stayed in the temporary store", shop_mod.load(MAS_VIN) and shop_mod.load(FER_VIN) and str(state_dir()).startswith(STATE))
check("art for Maserati and Ferrari models is 404 (the page draws the logo disc, not a Stelvio)",
      all(c.get(f"/add/art?model={m}").status_code == 404 for m in ("Quattroporte", "Roma", "Levante", "Grecale")))
check("page css centres the logo disc in the art area", ".as-art .as-disc" in css and "margin: 0 auto" in css)

print(f"{checks} checks, {len(failures)} failures")
for x in failures:
    print("FAIL:", x)
sys.exit(1 if failures else 0)
