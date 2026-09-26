"""Checks for the live-data dashboard UI API: layouts, replay, custom
channels, snapshots, triggers.

Same posture as ``check_live_data.py``: plain script, no mocking framework,
runs against a throwaway state directory so it never touches the bench's real
state. Builds its own minimal FastAPI app around ``cuore.api.live_ui.router``
(rather than the full ``cuore.app``) with the same ``BridgeError``/``MesError``
exception handlers ``cuore/app.py`` registers, so validation failures come
back as 400/404 instead of 500.

Run:
    .venv/Scripts/python.exe cuore/tests/check_live_ui_api.py
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# Before any cuore import: state must go to a throwaway directory, and MES's
# CSV roots must point at a throwaway directory too, so this never touches
# C:\ProgramData\cuore or a real MultiEcuScan export folder.
_STATE_TMP = tempfile.mkdtemp(prefix="cuore-check-live-ui-state-")
_MES_CSV_TMP = tempfile.mkdtemp(prefix="cuore-check-live-ui-mescsv-")
os.environ["CUORE_STATE_DIR"] = _STATE_TMP
os.environ["MES_CSV_DIR"] = _MES_CSV_TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_ROOT / "mes-log-mcp"))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401  -- side effect: mes on sys.path
from cuore.api import known_good as known_good_api  # noqa: E402
from cuore.api import live_ui  # noqa: E402
from cuore.live import channels as channels_mod  # noqa: E402
from cuore.live import layouts as layouts_mod  # noqa: E402
from cuore.live import replay as replay_mod  # noqa: E402
from cuore.live import ui_store  # noqa: E402
from cuore.config import load as load_settings  # noqa: E402
from cuore.models import ErrorBody  # noqa: E402
from cuore.services.errors import BridgeError  # noqa: E402

from mes import csvlog  # noqa: E402
from mes.errors import MesError  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


def check_eq(label: str, got, want, extra: str = "") -> None:
    detail = f"got {got!r} want {want!r}"
    if extra:
        detail += f" ({extra})"
    check(label, got == want, detail)


def create_test_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = load_settings()  # require_token reads app.state.settings

    @app.exception_handler(BridgeError)
    async def _bridge_error(request: Request, exc: BridgeError):
        body = ErrorBody(error=type(exc).__name__, detail=str(exc), status=exc.status)
        return JSONResponse(status_code=exc.status, content=body.model_dump())

    @app.exception_handler(MesError)
    async def _mes_error(request: Request, exc: MesError):
        body = ErrorBody(error=type(exc).__name__, detail=str(exc), status=400)
        return JSONResponse(status_code=400, content=body.model_dump())

    app.include_router(live_ui.router, prefix="/api")
    app.include_router(known_good_api.router, prefix="/api")
    return app


client = TestClient(create_test_app())


# ===========================================================================
# 0. state containment -- nothing touches the real state dir
# ===========================================================================

check("CUORE_STATE_DIR really is the temp dir",
      os.environ["CUORE_STATE_DIR"] == _STATE_TMP)
check("layouts_dir sits under the temp state dir",
      str(layouts_mod.layouts_dir()).startswith(_STATE_TMP), str(layouts_mod.layouts_dir()))
check("custom_channels_path sits under the temp state dir",
      str(ui_store.custom_channels_path()).startswith(_STATE_TMP))
check("snapshots_path sits under the temp state dir",
      str(ui_store.snapshots_path()).startswith(_STATE_TMP))
check("triggers_path sits under the temp state dir",
      str(ui_store.triggers_path()).startswith(_STATE_TMP))
check("cuore recordings dir sits under the temp state dir",
      str(replay_mod.cuore_recordings_dir()).startswith(_STATE_TMP))


# ===========================================================================
# 1. layouts
# ===========================================================================

BUILTIN_IDS = {"stelvio_engine", "stelvio_boost", "stelvio_evap",
              "stelvio_transmission", "stelvio_tpms", "mes_parameters"}

r = client.get("/api/live/layouts")
check_eq("GET /live/layouts is 200", r.status_code, 200)
listed = {row["id"]: row for row in r.json()["layouts"]}
check("every built-in layout is listed", BUILTIN_IDS <= set(listed), str(sorted(listed)))
check("built-in layouts are marked builtin=True",
      all(listed[i]["builtin"] is True for i in BUILTIN_IDS))

r = client.get("/api/live/layouts/stelvio_engine")
check_eq("GET one built-in layout is 200", r.status_code, 200)
engine_layout = r.json()
check("stelvio_engine has at least one page with widgets",
      len(engine_layout["pages"]) >= 1 and len(engine_layout["pages"][0]["widgets"]) > 0,
      str(engine_layout))
check("every stelvio_engine widget channel exists in the registry",
      all(c in channels_mod.registry() for p in engine_layout["pages"]
          for w in p["widgets"] for c in w["channels"]))

r = client.get("/api/live/layouts/stelvio_evap")
evap_layout = r.json()
check("stelvio_evap includes a stacked widget for Test A",
      any(w["type"] == "stacked" for p in evap_layout["pages"] for w in p["widgets"]),
      str(evap_layout))

r = client.get("/api/live/layouts/stelvio_tpms")
tpms_layout = r.json()
check("stelvio_tpms uses a tiles widget",
      any(w["type"] == "tiles" for p in tpms_layout["pages"] for w in p["widgets"]),
      str(tpms_layout))

r = client.get("/api/live/layouts/mes_parameters")
mes_params_layout = r.json()
check("mes_parameters has a table and a multiline graph",
      {"table", "multiline"} <= {w["type"] for p in mes_params_layout["pages"]
                                 for w in p["widgets"]},
      str(mes_params_layout))

# -- known-good bands wired into built-in layouts --------------------------

from cuore.services import known_good_bridge  # noqa: E402

engine_widgets = {w["id"]: w for p in engine_layout["pages"] for w in p["widgets"]}
rpm_band = known_good_bridge.sourced_band("engine_rpm")
check("engine_rpm known-good row is sourced (not UNKNOWN)", rpm_band is not None)
check_eq("w_engine_rpm min comes from known_good", engine_widgets["w_engine_rpm"]["min"],
        rpm_band["min"])
check_eq("w_engine_rpm max comes from known_good", engine_widgets["w_engine_rpm"]["max"],
        rpm_band["max"])
check_eq("w_engine_rpm warn band comes from known_good",
        engine_widgets["w_engine_rpm"]["warn"], rpm_band["warn"])
check_eq("w_engine_rpm alarm band comes from known_good",
        engine_widgets["w_engine_rpm"]["alarm"], rpm_band["alarm"])
check_eq("w_engine_rpm carries known_good's confidence",
        engine_widgets["w_engine_rpm"].get("confidence"), rpm_band["confidence"])
check_eq("w_engine_rpm carries known_good's source",
        engine_widgets["w_engine_rpm"].get("source"), rpm_band["source"])
check("w_engine_rpm carries a note", bool(engine_widgets["w_engine_rpm"].get("note")))

iat_band = known_good_bridge.sourced_band("intake_air_temp")
check("intake_air_temp known-good row is UNKNOWN (no sourced band)", iat_band is None)
check("w_intake_air_temp carries no confidence/source when UNKNOWN",
      "confidence" not in engine_widgets["w_intake_air_temp"]
      and "source" not in engine_widgets["w_intake_air_temp"])

evap_widgets = {w["id"]: w for p in evap_layout["pages"] for w in p["widgets"]}
check_eq("w_commanded_evap_purge keeps its explicit fallback min/max "
        "(known_good is UNKNOWN for EVAP purge)",
        (evap_widgets["w_commanded_evap_purge"]["min"],
         evap_widgets["w_commanded_evap_purge"]["max"]), (0, 100))

trans_layout = client.get("/api/live/layouts/stelvio_transmission").json()
trans_widgets = {w["id"]: w for p in trans_layout["pages"] for w in p["widgets"]}
tcm_band = known_good_bridge.sourced_band("tcm_04fe")
check_eq("w_tcm_04fe min/max come from known_good",
        (trans_widgets["w_tcm_04fe"]["min"], trans_widgets["w_tcm_04fe"]["max"]),
        (tcm_band["min"], tcm_band["max"]))

r = client.get("/api/live/layouts/no_such_layout")
check_eq("GET unknown layout is 404", r.status_code, 404)

r = client.put("/api/live/layouts/stelvio_engine", json=engine_layout)
check_eq("PUT over a built-in layout is 400", r.status_code, 400)

r = client.delete("/api/live/layouts/stelvio_engine")
check_eq("DELETE a built-in layout is 400", r.status_code, 400)


def _widget(wid, wtype, channels, size=(1, 1), **extra):
    w = {"id": wid, "type": wtype, "title": wid, "channels": channels, "size": list(size)}
    w.update(extra)
    return w


def _layout_body(lid, widgets):
    return {"id": lid, "name": lid, "version": 1,
           "pages": [{"id": "p1", "title": "Page 1", "widgets": widgets}]}


good_layout = _layout_body("my_layout", [_widget("w1", "digital", ["engine_rpm"])])
r = client.put("/api/live/layouts/my_layout", json=good_layout)
check_eq("PUT a valid user layout is 200", r.status_code, 200, r.text)
check_eq("saved layout id matches the path", r.json()["id"], "my_layout")

r = client.get("/api/live/layouts/my_layout")
check_eq("GET the saved user layout is 200", r.status_code, 200)
check("saved layout round-trips its widget", r.json()["pages"][0]["widgets"][0]["id"] == "w1")

r = client.get("/api/live/layouts")
check("the user layout now appears in the list",
      any(row["id"] == "my_layout" and row["builtin"] is False for row in r.json()["layouts"]))

# -- validation failures --------------------------------------------------

bad = _layout_body("bad1", [_widget("w1", "not_a_type", ["engine_rpm"])])
check_eq("unknown widget type is 400",
        client.put("/api/live/layouts/bad1", json=bad).status_code, 400)

bad = _layout_body("bad2", [_widget("w1", "digital", ["engine_rpm", "vehicle_speed"])])
check_eq("single-channel widget with 2 channels is 400",
        client.put("/api/live/layouts/bad2", json=bad).status_code, 400)

five = ["engine_rpm", "vehicle_speed", "engine_coolant_temp", "intake_air_temp",
       "absolute_load"]
bad = _layout_body("bad3", [_widget("w1", "multiline", five)])
check_eq("multiline widget with 5 channels (max 4) is 400",
        client.put("/api/live/layouts/bad3", json=bad).status_code, 400)

seven = five + ["throttle_position", "battery_voltage"]
bad = _layout_body("bad4", [_widget("w1", "stacked", seven)])
check_eq("stacked widget with 7 channels (max 6) is 400",
        client.put("/api/live/layouts/bad4", json=bad).status_code, 400)

ok = _layout_body("ok_stacked", [_widget("w1", "stacked", seven[:6])])
check_eq("stacked widget with exactly 6 channels is 200",
        client.put("/api/live/layouts/ok_stacked", json=ok).status_code, 200)

bad = _layout_body("bad5", [_widget("w1", "scatter", ["engine_rpm"])])
check_eq("scatter widget with 1 channel is 400",
        client.put("/api/live/layouts/bad5", json=bad).status_code, 400)

ok = _layout_body("ok_scatter", [_widget("w1", "scatter", [], xChannel="engine_rpm",
                                        yChannel="vehicle_speed")])
r = client.put("/api/live/layouts/ok_scatter", json=ok)
check_eq("scatter widget with xChannel/yChannel only is 200", r.status_code, 200, r.text)
check_eq("scatter widget's channels auto-fill from x/yChannel",
        sorted(r.json()["pages"][0]["widgets"][0]["channels"]),
        sorted(["engine_rpm", "vehicle_speed"]))

bad = _layout_body("bad6", [_widget("w1", "digital", ["engine_rpm"], size=[5, 1])])
check_eq("widget size width out of range (1-4) is 400",
        client.put("/api/live/layouts/bad6", json=bad).status_code, 400)

bad = _layout_body("bad7", [_widget("w1", "digital", ["engine_rpm"], size=[1, 0])])
check_eq("widget size height out of range (1-3) is 400",
        client.put("/api/live/layouts/bad7", json=bad).status_code, 400)

bad = _layout_body("bad8", [_widget("w1", "dial", ["engine_coolant_temp"], warn=[5])])
check_eq("malformed warn band is 400",
        client.put("/api/live/layouts/bad8", json=bad).status_code, 400)

r = client.delete("/api/live/layouts/my_layout")
check_eq("DELETE a user layout is 200", r.status_code, 200)
check_eq("GET the deleted layout is 404",
        client.get("/api/live/layouts/my_layout").status_code, 404)

# -- export / import round trip --------------------------------------------

r = client.get("/api/live/layouts/stelvio_engine/export")
check_eq("export a built-in layout is 200", r.status_code, 200)
check("export sets a download filename",
      "stelvio_engine" in r.headers.get("content-disposition", ""),
      r.headers.get("content-disposition"))
exported = r.json()
check_eq("exported layout id matches", exported["id"], "stelvio_engine")

r = client.post("/api/live/layouts/import", json=exported)
check_eq("importing a layout whose id collides with a built-in is 200", r.status_code, 200)
imported_id = r.json()["id"]
check("import assigns a free id rather than colliding",
      imported_id != "stelvio_engine" and imported_id.startswith("stelvio_engine"),
      imported_id)

r = client.post("/api/live/layouts/import", json=exported)
imported_id_2 = r.json()["id"]
check("importing again assigns yet another free id",
      imported_id_2 not in (imported_id, "stelvio_engine"), imported_id_2)

roundtrip = _layout_body("roundtrip_a", [_widget("w1", "digital", ["engine_rpm"])])
client.put("/api/live/layouts/roundtrip_a", json=roundtrip)
exported_rt = client.get("/api/live/layouts/roundtrip_a/export").json()
client.delete("/api/live/layouts/roundtrip_a")
r = client.post("/api/live/layouts/import", json=exported_rt)
check_eq("re-importing after delete gets the same free id back",
        r.json()["id"], "roundtrip_a")
check_eq("round-tripped layout's pages are unchanged",
        r.json()["pages"], exported_rt["pages"])


# ===========================================================================
# 2. custom channels
# ===========================================================================

r = client.get("/api/live/custom-channels")
check_eq("GET /live/custom-channels starts empty", r.json(), {"channels": []})

did_channel = {"id": "my_trans_temp", "name": "My trans temp", "unit": "C", "kind": "did",
              "module": "TCM", "did": "04FE", "formula": "(A*256+B)/10-40"}
r = client.put("/api/live/custom-channels", json={"channels": [did_channel]})
check_eq("PUT a valid Torque-formula DID custom channel is 200", r.status_code, 200, r.text)

bad = dict(did_channel, module="ZZZ")
check_eq("unknown module is 400",
        client.put("/api/live/custom-channels", json={"channels": [bad]}).status_code, 400)

bad = dict(did_channel, did="12")
check_eq("did not 4 hex digits is 400",
        client.put("/api/live/custom-channels", json={"channels": [bad]}).status_code, 400)

bad = dict(did_channel, formula="A & B")
check_eq("formula with a character outside the arithmetic grammar is 400",
        client.put("/api/live/custom-channels", json={"channels": [bad]}).status_code, 400)

computed_ok = {"id": "half_rpm", "name": "Half RPM", "unit": "rpm", "kind": "computed",
              "expr": "engine_rpm / 2"}
r = client.put("/api/live/custom-channels", json={"channels": [computed_ok]})
check_eq("computed channel referencing a real registry channel is 200", r.status_code, 200,
        r.text)

computed_bad = {"id": "bogus_calc", "name": "Bogus", "unit": "", "kind": "computed",
               "expr": "no_such_channel * 2"}
check_eq("computed channel referencing an unknown id is 400",
        client.put("/api/live/custom-channels", json={"channels": [computed_bad]}).status_code,
        400)

cyc_a = {"id": "cyc_a", "name": "A", "unit": "", "kind": "computed", "expr": "cyc_b + 1"}
cyc_b = {"id": "cyc_b", "name": "B", "unit": "", "kind": "computed", "expr": "cyc_a + 1"}
check_eq("a cycle between two custom computed channels is 400",
        client.put("/api/live/custom-channels", json={"channels": [cyc_a, cyc_b]}).status_code,
        400)

dup = {"id": "half_rpm", "name": "dup", "unit": "", "kind": "computed", "expr": "engine_rpm"}
check_eq("duplicate custom channel id in one submission is 400",
        client.put("/api/live/custom-channels", json={"channels": [computed_ok, dup]}).status_code,
        400)

collide = {"id": "engine_rpm", "name": "collide", "unit": "", "kind": "computed",
          "expr": "1"}
check_eq("custom channel id colliding with a built-in channel is 400",
        client.put("/api/live/custom-channels", json={"channels": [collide]}).status_code, 400)

r = client.put("/api/live/custom-channels", json={"channels": [did_channel, computed_ok]})
check_eq("final PUT with two valid custom channels is 200", r.status_code, 200, r.text)
r = client.get("/api/live/custom-channels")
check_eq("GET reflects the saved custom channels", {c["id"] for c in r.json()["channels"]},
        {"my_trans_temp", "half_rpm"})

loaded = ui_store.load_custom_channels()
by_id = {c.id: c for c in loaded}
check("load_custom_channels returns Channel objects for both", set(by_id) == {"my_trans_temp",
                                                                              "half_rpm"})
check_eq("did custom channel kind", by_id["my_trans_temp"].kind, "did")
check_eq("did custom channel confidence is USER-DEFINED",
        by_id["my_trans_temp"].confidence, "USER-DEFINED")
check_eq("computed custom channel kind", by_id["half_rpm"].kind, "computed")
check_eq("computed custom channel depends_on", by_id["half_rpm"].depends_on, ("engine_rpm",))


# ===========================================================================
# 3. snapshots
# ===========================================================================

snap_body = {"layout": "stelvio_engine", "page": "engine", "source": "live",
            "values": {"engine_rpm": {"value": 2000.0, "unit": "rpm"},
                      "vehicle_speed": {"value": 60.0, "unit": "km/h"}},
            "note": "bench check"}
r = client.post("/api/live/snapshots", json=snap_body)
check_eq("POST a valid snapshot is 200", r.status_code, 200, r.text)
snap = r.json()
check("snapshot got an id and timestamp", bool(snap.get("id")) and bool(snap.get("at")))

bad_snap = dict(snap_body, source="bogus")
check_eq("snapshot with an invalid source is 400",
        client.post("/api/live/snapshots", json=bad_snap).status_code, 400)

bad_snap2 = dict(snap_body, values={"engine_rpm": 2000.0})
check_eq("snapshot whose values aren't {channel: {value,...}} objects is 400",
        client.post("/api/live/snapshots", json=bad_snap2).status_code, 400)

r = client.get("/api/live/snapshots")
check("snapshot list includes the one just saved",
      any(s["id"] == snap["id"] for s in r.json()["snapshots"]))
check("snapshot list is newest first", r.json()["snapshots"][0]["id"] == snap["id"])

r = client.get(f"/api/live/snapshots/{snap['id']}")
check_eq("GET one snapshot is 200", r.status_code, 200)
check_eq("fetched snapshot matches what was saved", r.json()["note"], "bench check")

check_eq("GET a nonexistent snapshot is 404",
        client.get("/api/live/snapshots/no_such_snapshot").status_code, 404)

r = client.get(f"/api/live/snapshots/{snap['id']}/csv")
check_eq("GET snapshot CSV is 200", r.status_code, 200)
csv_lines = r.text.splitlines()
check_eq("snapshot CSV has 3 lines (names, units, one data row)", len(csv_lines), 3, r.text)
check("snapshot CSV header row starts with Time and ends with TAG",
      csv_lines[0].startswith('"Time"') and csv_lines[0].endswith('"TAG"'), csv_lines[0])
check("snapshot CSV names row includes the snapshotted channel",
      "engine_rpm" in csv_lines[0], csv_lines[0])
check("snapshot CSV units row includes rpm", "rpm" in csv_lines[1], csv_lines[1])


# ===========================================================================
# 4. triggers
# ===========================================================================

check_eq("GET /live/triggers starts empty", client.get("/api/live/triggers").json(),
        {"rules": []})

rule_op = {"id": "r1", "enabled": True,
          "when": {"channel": "engine_rpm", "op": ">", "value": 3000},
          "action": "snapshot", "cooldown_s": 5}
rule_alarm = {"id": "r2", "when": {"alarm": "warn"}, "action": "beep"}
r = client.put("/api/live/triggers", json={"rules": [rule_op, rule_alarm]})
check_eq("PUT two valid trigger rules is 200", r.status_code, 200, r.text)
saved_rules = r.json()["rules"]
check_eq("rule defaults filled in (enabled, cooldown_s)",
        (saved_rules[1]["enabled"], saved_rules[1]["cooldown_s"]), (True, 0.0))

r = client.get("/api/live/triggers")
check_eq("GET reflects the saved rules", {rr["id"] for rr in r.json()["rules"]}, {"r1", "r2"})

bad_rule = {"id": "bad", "when": {"channel": "engine_rpm", "op": "~~", "value": 1},
           "action": "beep"}
check_eq("trigger with a bad op is 400",
        client.put("/api/live/triggers", json={"rules": [bad_rule]}).status_code, 400)

bad_rule2 = {"id": "bad", "when": {"channel": "no_such_channel", "op": ">", "value": 1},
            "action": "beep"}
check_eq("trigger referencing an unknown channel is 400",
        client.put("/api/live/triggers", json={"rules": [bad_rule2]}).status_code, 400)

bad_rule3 = {"id": "bad", "when": {"channel": "engine_rpm", "op": ">", "value": 1},
            "action": "not_a_real_action"}
check_eq("trigger with an invalid action is 400",
        client.put("/api/live/triggers", json={"rules": [bad_rule3]}).status_code, 400)

check_eq("duplicate trigger ids in one submission is 400",
        client.put("/api/live/triggers", json={"rules": [rule_op, rule_op]}).status_code, 400)

# -- dtc triggers: {"dtc": "any"} or {"dtc": "<code>"} -------------------

rule_dtc_any = {"id": "r3", "when": {"dtc": "any"}, "action": "record_start"}
r = client.put("/api/live/triggers", json={"rules": [rule_op, rule_alarm, rule_dtc_any]})
check_eq("PUT valid trigger rules including a {'dtc': 'any'} rule is 200", r.status_code, 200,
        r.text)
saved = {rr["id"]: rr for rr in r.json()["rules"]}
check_eq("the dtc rule's when is saved as given", saved["r3"]["when"], {"dtc": "any"})

rule_dtc_code = {"id": "r4", "when": {"dtc": "P0456"}, "action": "mark", "text": "P0456 set"}
r = client.put("/api/live/triggers", json={"rules": [rule_dtc_code]})
check_eq("PUT a trigger scoped to one DTC code is 200", r.status_code, 200, r.text)
check_eq("a code-scoped dtc trigger's when.dtc round-trips",
        r.json()["rules"][0]["when"], {"dtc": "P0456"})

bad_dtc_empty = {"id": "bad", "when": {"dtc": ""}, "action": "beep"}
check_eq("a trigger with an empty dtc value is 400",
        client.put("/api/live/triggers", json={"rules": [bad_dtc_empty]}).status_code, 400)

bad_dtc_type = {"id": "bad", "when": {"dtc": 123}, "action": "beep"}
check_eq("a trigger with a non-string dtc value is 400",
        client.put("/api/live/triggers", json={"rules": [bad_dtc_type]}).status_code, 400)

bad_when_neither = {"id": "bad", "when": {}, "action": "beep"}
check_eq("a trigger whose when names neither channel/op/value, alarm, nor dtc is 400",
        client.put("/api/live/triggers", json={"rules": [bad_when_neither]}).status_code, 400)


# ===========================================================================
# 5. replay
# ===========================================================================

CUORE_CSV = (
    '"Time"\t"Engine speed"\t"Fuel pressure"\t"TAG"\n'
    '"sec"\t"rpm"\t"bar"\t" "\n'
    '0.00\t1000.0000\t300.0000\t""\n'
    '0.02\t1100.0000\t305.0000\t""\n'
    '0.04\t1200.0000\t310.0000\t"P0455"\n'
)
cuore_rec_path = replay_mod.cuore_recordings_dir() / "live_20260101-000000.csv"
cuore_rec_path.write_text(CUORE_CSV, encoding="utf-8")

MES_CSV = (
    '"Time"\t"Boost pressure"\t"TAG"\n'
    '"sec"\t"kPa"\t" "\n'
    '0.00\t100.0000\t""\n'
    '0.02\t110.0000\t""\n'
)
(Path(_MES_CSV_TMP) / "sample.csv").write_text(MES_CSV, encoding="utf-8")

r = client.get("/api/live/recordings")
check_eq("GET /live/recordings is 200", r.status_code, 200)
recs = {rec["id"]: rec for rec in r.json()["recordings"]}
check("the cuore recording is listed", "cuore:live_20260101-000000.csv" in recs, str(recs))
check("the MES recording is listed", "mes:sample.csv" in recs, str(recs))
cuore_rec = recs.get("cuore:live_20260101-000000.csv", {})
check_eq("cuore recording source", cuore_rec.get("source"), "cuore")
check("cuore recording lists its columns by name",
      "Engine speed" in cuore_rec.get("channels", []), str(cuore_rec))
check_eq("cuore recording started parsed from filename",
        cuore_rec.get("started"), "2026-01-01 00:00:00")
mes_rec = recs.get("mes:sample.csv", {})
check_eq("mes recording source", mes_rec.get("source"), "mes")

r = client.get("/api/live/replay/cuore:live_20260101-000000.csv/channels")
check_eq("GET replay channels is 200", r.status_code, 200)
rc = r.json()["channels"]
check("engine speed column has a slug id with name+unit",
      any(v["name"] == "Engine speed" and v["unit"] == "rpm" for v in rc.values()), str(rc))
engine_slug = next(k for k, v in rc.items() if v["name"] == "Engine speed")

check_eq("GET replay channels for an unknown recording is 404",
        client.get("/api/live/replay/cuore:no_such.csv/channels").status_code, 404)
check_eq("GET replay channels for a malformed id is 400",
        client.get("/api/live/replay/nocolon/channels").status_code, 400)

r = client.get(f"/api/live/replay/cuore:live_20260101-000000.csv/stream?speed=0")
check_eq("GET replay stream (speed=0) is 200", r.status_code, 200)
check("replay stream content-type is SSE",
      "text/event-stream" in r.headers.get("content-type", ""))
lines = [ln for ln in r.text.splitlines() if ln.startswith("data:")]
messages = [json.loads(ln[len("data:"):].strip()) for ln in lines]
check("replay stream ends with an end event",
      bool(messages) and messages[-1] == {"type": "end"}, str(messages[-3:]))
value_msgs = [m for m in messages if m.get("channel") == engine_slug]
check_eq("replay emitted 3 samples for the engine-speed column", len(value_msgs), 3,
        str(value_msgs))
check("every replay value message is flagged replay:true and has t/unit",
      all(m.get("replay") is True and "t" in m and "unit" in m for m in value_msgs),
      str(value_msgs))
check_eq("first replayed engine-speed value", value_msgs[0]["value"], 1000.0)
check_eq("last replayed engine-speed value", value_msgs[-1]["value"], 1200.0)
tag_msgs = [m for m in messages if m.get("type") == "tag"]
check_eq("the TAG row produced exactly one tag event", len(tag_msgs), 1, str(tag_msgs))
check_eq("tag event carries the TAG text", tag_msgs[0]["text"], "P0455")

check_eq("replay stream with speed above 16 is 400",
        client.get(f"/api/live/replay/cuore:live_20260101-000000.csv/stream?speed=100"
                  ).status_code, 400)
check_eq("replay stream with speed between 0 and 0.25 is 400",
        client.get(f"/api/live/replay/cuore:live_20260101-000000.csv/stream?speed=0.1"
                  ).status_code, 400)
check_eq("replay stream for an unknown recording is 404",
        client.get("/api/live/replay/cuore:no_such.csv/stream?speed=0").status_code, 404)
check_eq("replay stream for an unknown source is 400",
        client.get("/api/live/replay/bogus:whatever.csv/stream?speed=0").status_code, 400)

# replay never writes an observation
check_eq("replay never appends to observations.jsonl",
        (Path(_STATE_TMP) / "observations.jsonl").exists(), False)


# ===========================================================================
# 6. known-good endpoint
# ===========================================================================

r = client.get("/api/live/known-good")
check_eq("GET /live/known-good (no vin) is 200", r.status_code, 200)
kg_body = r.json()
check("known-good response has a channels map", isinstance(kg_body.get("channels"), dict))
check("known-good response has no vin/observed without a vin param",
      "vin" not in kg_body and "observed" not in kg_body, str(sorted(kg_body)))
check("known-good channels map includes engine_rpm",
      "engine_rpm" in kg_body["channels"])
check_eq("known-good engine_rpm confidence matches the library",
        kg_body["channels"]["engine_rpm"]["confidence"], "SINGLE-SOURCE")
check("known-good includes a documented UNKNOWN row (intake_air_temp)",
      kg_body["channels"].get("intake_air_temp", {}).get("confidence") == "UNKNOWN")
check("known-good UNKNOWN row still carries a TechAuthority note",
      "TechAuthority" in (kg_body["channels"]["intake_air_temp"].get("notes") or ""))
check("every known-good row's channel id exists in the channel registry",
      all(cid in channels_mod.registry() for cid in kg_body["channels"]))

def _bands_ordered(row):
    for key in ("normal", "warn", "alarm"):
        band = row.get(key)
        if band is not None and band[0] > band[1]:
            return False
    return True

check("every known-good band is ordered lo <= hi",
      all(_bands_ordered(row) for row in kg_body["channels"].values()))

r = client.get("/api/live/known-good", params={"vin": "ZASFAKPN5J7B88115"})
check_eq("GET /live/known-good with a vin is 200", r.status_code, 200, r.text)
kg_vin_body = r.json()
check_eq("known-good response echoes the vin", kg_vin_body.get("vin"), "ZASFAKPN5J7B88115")
check("known-good response includes observed_ranges when a vin is given",
      isinstance(kg_vin_body.get("observed"), dict))


# --- regression 2026-09-26: known-good bands must not invert widget levels ----
from cuore.live import layouts as _lay  # noqa: E402
_eng = _lay.get_layout("stelvio_engine") if hasattr(_lay, "get_layout") else None
if _eng is None:
    _eng = client.get("/api/live/layouts/stelvio_engine").json()
_ws = {w["channels"][0]: w for p in _eng["pages"] for w in p["widgets"] if len(w.get("channels", [])) == 1}
_rpm = _ws.get("engine_rpm")
check("RPM widget gets no idle-only warn/alarm band (would read ALARM at idle)",
      _rpm is not None and _rpm.get("warn") is None and _rpm.get("alarm") is None, str(_rpm))
check("RPM widget scale is not the idle range", _rpm is not None and _rpm.get("max") != 900.0, str(_rpm))
_ct = _ws.get("engine_coolant_temp")
check("coolant widget keeps its one-sided 'too hot' bands",
      _ct is not None and _ct.get("warn") and _ct["warn"][0] >= 100, str(_ct))


# --- regression 2026-09-26: layout ids cannot escape the layouts dir ----------
_secret = Path(os.environ["CUORE_STATE_DIR"]) / "outside_secret.json"
_secret.write_text('{"id": "x", "name": "SECRET", "pages": []}', encoding="utf-8")
for _bad in ("..\outside_secret", "..%5Coutside_secret", "..\..\outside_secret"):
    _r = client.get(f"/api/live/layouts/{_bad}")
    check(f"layout read with traversal id {_bad!r} is refused", _r.status_code in (400, 404) and "SECRET" not in _r.text,
          f"{_r.status_code} {_r.text[:80]}")
    _r = client.get(f"/api/live/layouts/{_bad}/export")
    check(f"layout export with traversal id {_bad!r} is refused", _r.status_code in (400, 404) and "SECRET" not in _r.text,
          f"{_r.status_code} {_r.text[:80]}")

# ===========================================================================
# report
# ===========================================================================

passed = checks - len(failures)

print(f"{passed}/{checks} checks passed")
if failures:
    for f in failures:
        print("  -", f)
    sys.exit(1)
