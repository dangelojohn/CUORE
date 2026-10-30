"""Checks for /hardware with fakes only (no serial port is ever opened).
Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_hardware_page.py"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore_hw_check_")
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.live import adapter_check, ops, transport  # noqa: E402
from cuore.web import hardware_routes  # noqa: E402

failures: list[str] = []


def check(cond: bool, label: str) -> None:
    if not cond:
        failures.append(label)


# data file shape
hw = adapter_check.load_hardware()
items = {i["id"]: i for i in hw["items"]}
for i in hw["items"]:
    check({"id", "name", "kind", "chip", "can_do", "tested_on"} <= set(i), f"shape {i.get('id')}")
check(items["vlinker-fs-usb"]["tested_on"] and items["cable-a5-can-ihs"]["tested_on"]
      and items["cable-a6-can-ch"]["tested_on"], "tested items have records")
check(all(i["tested_on"] == [] for k, i in items.items() if k in ("obdlink-mx-plus", "generic-elm327-clone")),
      "untested items have no records")
check(all(t["source"] == "CUORE session records" for i in hw["items"] for t in i["tested_on"]), "sources cited")

# verdicts
stn = adapter_check.check_adapter({"ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2", "STDI": "vLinker FS"})
check(all(v["verdict"] == "pass" for v in stn["verdicts"].values()), "STN verdicts pass")
elm = adapter_check.check_adapter({"ATI": "ELM327 v1.5"})
check(elm["verdicts"]["listen_only"]["verdict"] == "limited"
      and "frames may be lost" in elm["verdicts"]["listen_only"]["reason"], "ELM clone listen-only limited")
check(elm["verdicts"]["basic_obd"]["verdict"] == "pass", "ELM basic pass")
unk = adapter_check.check_adapter({})
check(all(v["verdict"] == "not tested" for v in unk["verdicts"].values()), "unknown not tested")
check(adapter_check.check_adapter({"ATI": "x"}, bus_test={"ok": False})["verdicts"]["bypass_buses"]["verdict"] == "fail",
      "failed bus test is fail")
check(adapter_check.check_adapter({"ATI": "ELM327 v1.5"}, voltage=9.0)["verdicts"]["basic_obd"]["verdict"] == "limited",
      "low voltage limits")


# page with fakes; any adapter contact is a failure
def boom(*a, **k):
    raise AssertionError("adapter contacted")


ops.probe = boom  # type: ignore[assignment]
transport.AdapterLink.session = boom  # type: ignore[assignment]
ops.status = lambda: {"port": "COM3", "baud": 115200, "adapter_identity": {"ATI": "ELM327 v2.3", "STI": "STN1170", "STDI": "vLinker FS"}}  # type: ignore[assignment]
ops.mes_settings = lambda: {"interfaces": [{"index": 0, "type_ex": 7, "port": "COM3", "speed": 115200}]}  # type: ignore[assignment]

c = TestClient(create_app())
r = c.get("/hardware")
check(r.status_code == 200, "GET /hardware 200")
t = r.text
check("Coming from MES" in t and "Is my adapter good enough?" in t, "sections")
check("Interface 0: port COM3, speed 115200" in t, "MES interface shown")
rows = [i for i in json.loads(Path(hardware_routes.PARITY).read_text(encoding="utf-8"))["items"]
        if i["cuore"]["has"] == "yes"]
check(len(rows) > 0 and len(hardware_routes.parity_rows()) == len(rows), "rows equal parity yes rows")
page = t[t.index("<div class=\"hw\">"):t.index("id=\"keyhelp\"")]
body = page.split("In MES you used")[-1]
check(body.count("<tr>") == len(rows), f"table row count {body.count(chr(60)+'tr>')} vs {len(rows)}")
check("Recommended" not in t and "Recommended" not in json.dumps(hw), "no Recommended")
check(not re.search(r"[$€£]|\bUSD\b|\bCAD\b", t + json.dumps(hw)), "no price or currency")
check("<script" not in page, "no JavaScript in page body")

if failures:
    print("FAIL:", *failures, sep="\n  ")
    sys.exit(1)
print("OK: hardware page checks passed")
