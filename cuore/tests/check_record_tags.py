"""Checks for keyed recording tags (0-9) and per-channel poll priority (1-5).

Uses the scripted LiveFakeStream from check_live_data.py (its definitions only; nothing
there runs a session), so no adapter or COM port is ever touched.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_record_tags.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_src = (Path(__file__).resolve().parent / "check_live_data.py").read_text(encoding="utf-8")
exec(compile(_src.split("fake1 = LiveFakeStream()")[0], "check_live_data_defs", "exec"))  # noqa: S102

from mes import csvlog  # noqa: E402
from cuore.live import replay  # noqa: E402

fake = LiveFakeStream()
set_link(AdapterLink(stream_factory=lambda p, b: fake, process="check_record_tags"))
from cuore.live.transport import link  # noqa: E402
link().mark_verified(CAN_C, 10)

VIN = "ZASFAKPN5J7B88115"
p = poller_mod.LivePoller()
poller_mod.set_poller(p)
chans = channels_mod.resolve_channels(["engine_rpm", "vehicle_speed"])
p.start(chans, rates={"engine_rpm": 10.0, "vehicle_speed": 10.0}, priorities={"vehicle_speed": 4})

# priority: divisor reported, default 1, bad value refused, slow channel read less often
st = p.status()
check_eq("divisors in status", st["channel_rates"]["vehicle_speed"]["divisor"], 4)
check_eq("default priority is 1", st["channel_rates"]["engine_rpm"]["divisor"], 1)
check("priority 9 is refused", raises(BadCommand, lambda: poller_mod._clean_priority(9, "x")))

# tags: not recording -> None; recording -> one row per tag, labels from the per-VIN store
check("no tag when not recording", ops.live_record_tag("3", vin=VIN) is None)
ui_store_mod.save_tag_labels(VIN, {"3": "Shudder felt"})
check_eq("renamed label stored", ui_store_mod.load_tag_labels(VIN)["3"], "Shudder felt")
check_eq("default label", ui_store_mod.load_tag_labels(VIN)["4"], "Tag 4")
check("bad key refused", raises(BadCommand, lambda: ops.live_record_tag("12", vin=VIN)))
rec_info = p.start_recording()
wait_until(lambda: p.snapshot()["channels"]["engine_rpm"]["value"] is not None)
e1 = ops.live_record_tag("3", vin=VIN)
time.sleep(0.4)
e2 = ops.live_record_tag("4", vin=VIN)
time.sleep(2.0)
tags_status = p.status()["recording_tags"]
st = p.status()
stop_info = p.stop_recording()
p.stop()
check("two tag events in status", [t["key"] for t in tags_status] == ["3", "4"], str(tags_status))
check_eq("event label", e1["label"], "Shudder felt")
check("event row numbers rise", 0 < e1["row"] < e2["row"] <= stop_info["rows"], f"{e1} {e2}")
check("slow channel polled less often than the fast one",
      st["achieved_hz"]["vehicle_speed"] < 0.7 * st["achieved_hz"]["engine_rpm"], str(st["achieved_hz"]))

# the CSV stays readable by the MES parser and by CUORE replay, tags on exactly their rows
path = Path(rec_info["recording"])
rec = csvlog.load_csv(path)
texts = [t.text for t in rec.tags]
check_eq("MES parser sees exactly the two tags", texts, ["TAG 3: Shudder felt", "TAG 4: Tag 4"])
check("tag times are in the recording's own clock", rec.tags[0].time < rec.tags[1].time)
check("rows still parse", len(rec.times) == stop_info["rows"], f"{len(rec.times)} vs {stop_info['rows']}")
replayed = [m["text"] for m in replay.open_replay_stream("cuore:" + path.name, speed=0) if m.get("type") == "tag"]
check_eq("CUORE replay yields the same tags", replayed, texts)

# API: 409 when nothing is recording; labels round-trip
from fastapi.testclient import TestClient  # noqa: E402
from cuore.app import create_app  # noqa: E402
api = TestClient(create_app())
check_eq("tag with no recording is 409", api.post("/api/live/record/tag", json={"key": "3", "vin": VIN}).status_code, 409)
check_eq("labels over HTTP", api.get("/api/live/record/tag-labels", params={"vin": VIN}).json()["labels"]["3"], "Shudder felt")

print(f"{checks} checks, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
