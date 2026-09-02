"""Corpus-backed smoke checks for the CUORE service.

Same posture as ``mes-log-mcp/tests/*``: no mocks, no fixtures. The real MES
corpus on this machine *is* the fixture, and the assertions pin facts that are
already established in it -- the chronic P0456 and its 26,500 km span, the
2026-08-27 clear that must not read as a healthy car, the two vehicles with
real logs.

Run:
    .venv/Scripts/python.exe cuore/tests/check_api.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import mes_bridge  # noqa: E402
from cuore.services.errors import BridgeError  # noqa: E402

VIN = "ZASFAKPN5J7B88115"          # the Stelvio -- 17 logs, all real
VIN_500L = "ZFBCFABH1EZ020882"     # the Fiat 500L -- 4 real logs

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


client = TestClient(create_app())


# --- the capability contract ---------------------------------------------

caps = client.get("/api/capabilities")
check("capabilities responds", caps.status_code == 200)
body = caps.json()
check("profile is bench", body["profile"] == "bench", str(body.get("profile")))
check("corpus advertised", body["features"]["corpus"] is True)
check("live_obd is False at P1", body["features"]["live_obd"] is False)
check("drive_recorder is False at P1", body["features"]["drive_recorder"] is False)
check("actuators is False at P1", body["features"]["actuators"] is False)
check("adapter reported absent", body["adapter"]["present"] is False)
check("every declared feature is present in the payload",
      set(body["features"]) >= {"corpus", "workup", "fault_tree", "verdict",
                                "live_obd", "live_can", "drive_recorder"})
check("corpus counts are real", body["corpus"]["total_logs"] > 0,
      str(body["corpus"]["total_logs"]))


# --- vehicles -------------------------------------------------------------

real = client.get("/api/vehicles?real_only=true").json()
vins = {v["vin"] for v in real["vehicles"]}
check("Stelvio present among real vehicles", VIN in vins, str(vins))
check("500L present among real vehicles", VIN_500L in vins, str(vins))
check("simulation pseudo-vehicles excluded", "5188214" not in vins)

everything = client.get("/api/vehicles").json()
check("unfiltered list is larger than the real one",
      everything["count"] > real["count"],
      f"{everything['count']} vs {real['count']}")


# --- the dossier ----------------------------------------------------------

d = client.get(f"/api/vehicle/{VIN}")
check("dossier responds", d.status_code == 200)
dossier = d.json()
check("dossier names its blind spots", len(dossier["blind_spots"]) >= 3)
check("blind spots name the tool that closes each",
      all(b.get("closes_it") for b in dossier["blind_spots"]))
check("provenance note present", bool(dossier.get("provenance_note")))

chronic = {r["dtc"] for r in dossier["history"]["chronic"]}
check("P0456 classified chronic", "P0456-00" in chronic, str(chronic))

p0456 = next((r for r in dossier["history"]["chronic"]
              if r["dtc"] == "P0456-00"), None)
check("P0456 record found", p0456 is not None)
if p0456:
    check("P0456 spans real distance, not one visit",
          p0456.get("distance_span_km", 0) > 20000,
          str(p0456.get("distance_span_km")))
    check("P0456 first seen 2025-09-24",
          p0456["first_seen"].startswith("2025-09-24"), p0456["first_seen"])
    check("P0456 last seen 2026-08-27",
          p0456["last_seen"].startswith("2026-08-27"), p0456["last_seen"])

# The whole point of the clear assessment: silence after an erase is not a
# repair. If this ever starts reading as a clean bill of health, the tool has
# become dangerous rather than merely wrong.
clear = dossier["current_picture"].get("clear_assessment")
check("clear assessment present", clear is not None)
if clear:
    verdict_text = clear["verdict"].lower()
    check("a clear is not reported as proof of repair",
          "not proof" in verdict_text or "carries no information" in verdict_text,
          clear["verdict"][:90])
    check("clear assessment says what to do next", bool(clear.get("next_step")))

scan = dossier["current_picture"].get("latest_scan")
check("SCAN provenance is unverifiable, never clean",
      scan is None or "unverifiable" in scan.get("provenance", ""),
      str(scan.get("provenance") if scan else None))


# --- codes ----------------------------------------------------------------

dtcs = client.get(f"/api/vehicle/{VIN}/dtcs").json()
check("codes listed", dtcs["count"] > 0)
check("simulation excluded by default", dtcs["simulation_included"] is False)
check("every code carries an explicit severity",
      all("severity" in r for r in dtcs["dtcs"]))
check("severity uses the known vocabulary",
      {r["severity"] for r in dtcs["dtcs"]} <=
      {"returned", "chronic", "cleared", "seen-once", "recurring"},
      str({r["severity"] for r in dtcs["dtcs"]}))
check("chronic booleans survive serialisation",
      any(r.get("chronic") for r in dtcs["dtcs"]))
check("returned-after-clear sorts before the rest",
      not dtcs["dtcs"] or dtcs["dtcs"][0]["severity"] in ("returned", "chronic"),
      dtcs["dtcs"][0]["severity"] if dtcs["dtcs"] else "")

hist = client.get(f"/api/vehicle/{VIN}/dtc/P0456")
check("single code history responds", hist.status_code == 200)
check("history matched P0456",
      hist.json()["matches"][0]["dtc"].startswith("P0456"))

check("unknown code is 404, not an empty 200",
      client.get(f"/api/vehicle/{VIN}/dtc/P9999").status_code == 404)
check("unknown vehicle is 404",
      client.get("/api/vehicle/NOSUCHVIN00000").status_code == 404)


# --- fault tree and the gate ---------------------------------------------

tree = client.get(f"/api/vehicle/{VIN}/tree").json()
check("a tree routes from the car's own codes", bool(tree.get("trees")),
      str(tree.get("error")))
check("the tree is annotated with this car's evidence",
      "vehicle_evidence" in tree)

weak = client.post(f"/api/vehicle/{VIN}/verdict", json={
    "codes": "P0456", "component": "purge valve", "mechanism": "",
    "measurements": [], "disconfirming_test": ""})
check("gate accepts a submission", weak.status_code == 200, weak.text[:120])
wbody = weak.json()
check("a bare part name is NOT confirmed", wbody["verdict"] != "CONFIRMED",
      wbody.get("verdict"))
check("gate names what is missing", len(wbody["missing"]) >= 3,
      str(wbody.get("missing")))
check("gate gives a next test for each unmet criterion",
      all(c.get("next_test") for c in wbody["criteria"].values()
          if not c["met"]))
check("gate warns about the low-yield purge solenoid",
      any("purge" in w.lower() for w in wbody.get("component_warnings", [])))

check("gate refuses a submission with no codes",
      client.post(f"/api/vehicle/{VIN}/verdict",
                  json={"codes": ""}).status_code == 400)

# The HTML form is the surface with real user input and hand-rolled parsing of
# the parallel m_* fields, so it gets exercised separately from the JSON body.
form_weak = client.post(f"/v/{VIN}/gate", data={
    "codes": "P0456", "component": "purge valve", "mechanism": "",
    "disconfirming_test": "", "m_type": ["actuator"]})
check("gate form accepts a post", form_weak.status_code == 200)
check("gate form refuses a bare part name",
      "NOT CONFIRMED" in form_weak.text)

# A case that should pass: a stated mechanism, an actuator citation the corpus
# can actually verify on this VIN, and a disconfirming test.
form_strong = client.post(f"/v/{VIN}/gate", data={
    "codes": "P0456",
    "component": "EVAP canister",
    "mechanism": ("Saturated canister restricts the vent path so the "
                  "natural-vacuum test cannot pull the required depression "
                  "and the ECM logs a small leak."),
    "disconfirming_test": ("Actuated the purge valve KOEO: it responds and "
                           "holds, so the valve is not the restriction."),
    "m_type": ["actuator"],
    "m_operation_0": "Evaporation control valve"})
check("gate form confirms a properly evidenced case",
      "CONFIRMED" in form_strong.text
      and "NOT CONFIRMED" not in form_strong.text,
      "the gate should pass a case with mechanism, a corpus-verified "
      "measurement and disconfirmation")
check("measurement rows survive the m_* parsing",
      "Evaporation control valve" in form_strong.text)


# --- path containment -----------------------------------------------------
# The security boundary. An earlier MCP version built paths by concatenation,
# which on Windows let both `..` and an absolute path escape the log root --
# every file the process could read was reachable. These must never pass.

TRAVERSALS = [
    "../../Windows/win.ini",
    "..\\..\\Windows\\win.ini",      # backslash: a real separator on Windows
    "C:\\Windows\\win.ini",
    "C:/Windows/win.ini",
    "/etc/passwd",
    "....//....//Windows/win.ini",
    "FESLog_..\\..\\..\\win.ini",
    "",
]
for candidate in TRAVERSALS:
    try:
        mes_bridge.read_log(candidate)
        failures.append(f"CONTAINMENT BREACH: read_log accepted {candidate!r}")
        checks += 1
    except BridgeError:
        checks += 1
    except Exception as exc:  # any refusal is acceptable; silence is not
        checks += 1
        if "Traceback" in str(exc):
            failures.append(f"read_log({candidate!r}) failed oddly: {exc}")

# And over HTTP, where the router gets a say first.
for candidate in ["../../Windows/win.ini", "..%2F..%2FWindows%2Fwin.ini",
                  "..%5C..%5CWindows%5Cwin.ini", "C:/Windows/win.ini"]:
    status = client.get(f"/api/log/{candidate}").status_code
    check(f"HTTP rejects {candidate}", status in (400, 404), str(status))

# A legitimate read still works -- containment that blocks everything is easy
# and useless.
newest = client.get(f"/api/logs?vin={VIN}&limit=1").json()["logs"][0]["file"]
good = client.get(f"/api/log/{newest}")
check("a real log still reads", good.status_code == 200, good.text[:120])
check("the log carries its decoded text", bool(good.json().get("text")))


# --- pages render ---------------------------------------------------------

PAGES = [
    "/", f"/v/{VIN}", f"/v/{VIN}/codes", f"/v/{VIN}/code/P0456",
    f"/v/{VIN}/tree", f"/v/{VIN}/gate", f"/v/{VIN}/codes?include_simulation=true",
    f"/v/{VIN_500L}", f"/v/{VIN_500L}/codes", f"/v/{VIN_500L}/tree",
    "/modules", "/recordings", "/logs", f"/logs?vin={VIN}",
]
for page in PAGES:
    resp = client.get(page)
    check(f"page {page} renders", resp.status_code == 200, str(resp.status_code))
    if resp.status_code == 200:
        check(f"page {page} is HTML", "<html" in resp.text.lower())

bad_page = client.get("/v/NOSUCHVIN00000")
check("a bad VIN gets a page, not raw JSON", bad_page.status_code == 404)
check("the error page is HTML", "<html" in bad_page.text.lower())


# --- auth -----------------------------------------------------------------

from cuore.config import Settings  # noqa: E402

guarded = TestClient(create_app(Settings(token="s3cret")))
check("token enforced when configured",
      guarded.get("/api/capabilities").status_code == 401)
check("correct token in header accepted",
      guarded.get("/api/capabilities",
                  headers={"X-Cuore-Token": "s3cret"}).status_code == 200)
check("correct token in query accepted",
      guarded.get("/api/capabilities?token=s3cret").status_code == 200)
check("wrong token rejected",
      guarded.get("/api/capabilities?token=nope").status_code == 401)


# --- report ---------------------------------------------------------------

print(f"checks run: {checks}")
if failures:
    print(f"FAILURES: {len(failures)}")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print("all green")
