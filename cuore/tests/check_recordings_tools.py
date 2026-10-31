"""Checks for saved value sets, replay, two-recording comparison table and print on the Recordings pages.

A fake live layer stands in for the poller (no adapter, no port); CUORE_STATE_DIR is a throwaway directory.

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_recordings_tools.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

_tmp = tempfile.mkdtemp(prefix="cuore-rect-")
os.environ["CUORE_STATE_DIR"] = _tmp
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import channel_sets as S  # noqa: E402
from cuore.services import recordings as R  # noqa: E402
from cuore.services import value_groups  # noqa: E402
from cuore.web import recordings_routes as RR  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


VIN = "ZASFAKPN5J7B88115"
group = next(g for g in value_groups.groups() if value_groups.group_channel_ids(g))
gids = value_groups.group_channel_ids(group)

# --- sets: service
check(S.listing(VIN, [])[:0] == [] and all(r["kind"] == "group" for r in S.listing(VIN)), "no own sets at first, ready-made ones listed")
S.save(VIN, "  Idle   check ", ["rpm", "speed", "rpm"])
own = [r for r in S.listing(VIN) if r["kind"] == "own"]
check(len(own) == 1 and own[0]["name"] == "Idle check" and own[0]["channels"] == ["rpm", "speed"], "save trims the name and drops duplicates")
S.save(VIN, "idle CHECK", ["rpm"])
own = [r for r in S.listing(VIN) if r["kind"] == "own"]
check(len(own) == 1 and own[0]["channels"] == ["rpm"], "same name replaces, case-insensitive")
l = S.listing(VIN, ["speed"])
check([r for r in l if r["kind"] == "own"][0]["missing"] == ["rpm"], "own set keeps a channel the session lacks and reports it missing")
check(all(r["kind"] != "group" for r in l), "ready-made set with no channel in the session is left out")
l = S.listing(VIN, [gids[0]])
check(any(r["kind"] == "group" and r["here"] == [gids[0]] for r in l), "ready-made set offered with the channels present")
for bad, why in (("", ["a"]), ("x" * 41, ["a"]), ("n", []), ("n", ["a\x00b"]), ("n", [str(i) for i in range(61)])):
    try:
        S.save(VIN, bad, why)
        check(False, f"refused: {bad[:5]!r} {why[:1]!r}")
    except S.SetError:
        check(True, "bad set refused")
try:
    S.save("../x", "n", ["a"])
    check(False, "bad VIN refused")
except S.SetError:
    check(True, "bad VIN refused")
check(S.delete(VIN, "Idle Check") is True and S.delete(VIN, "Idle Check") is False, "delete once, then nothing to delete")
(Path(_tmp) / "channel_sets" / f"{VIN}.json").write_text("{torn", encoding="utf-8")
check(S.listing(VIN, []) == [] or all(r["kind"] == "group" for r in S.listing(VIN)), "a torn file reads as no own sets")

# --- fake live layer + pages
live = {"active": True}
R._status = lambda: {"active": live["active"], "channels": [{"id": "rpm"}, {"id": "speed"}, {"id": "e</script>x"}]}
R._snapshot = lambda: {"active": True, "channels": {}}
client = TestClient(create_app(), follow_redirects=False)

r = client.post(f"/v/{VIN}/recordings/sets/save", data={"set_name": "Drive", "channels": ["rpm", "speed"]})
check(r.status_code == 303 and "Saved%20set%20Drive" in r.headers["location"], "POST save redirects with the result")
r = client.post(f"/v/{VIN}/recordings/sets/save", data={"set_name": "", "channels": ["rpm"]})
check(r.status_code == 303 and "Give%20the%20set%20a%20name" in r.headers["location"], "POST save without a name says why")
p = client.get(f"/v/{VIN}/recordings")
check(p.status_code == 200 and "Drive (2)" in p.text, "page offers the saved set with its count")
check('aria-label="Delete set Drive"' in p.text and "Save ticked values as a set" in p.text and "Tick all" in p.text, "page has delete, save and tick controls")
check(re.search(r'<button type="submit" hidden[^>]*recordings/start', p.text) is not None, "Enter submits Start, never Delete")
check("e</script>x" not in p.text and "e&lt;/script&gt;x" in p.text, "hostile channel name is escaped on the form")
r = client.post(f"/v/{VIN}/recordings/sets/delete", data={"set_name": "Drive"})
check(r.status_code == 303 and "Deleted%20set%20Drive" in r.headers["location"], "POST delete redirects")
check("Drive (" not in client.get(f"/v/{VIN}/recordings").text, "deleted set is gone from the page")

# --- replay, comparison, print
def make(rid: str, label: str, n: int, base: float) -> None:
    d = Path(_tmp) / "recordings" / VIN
    d.mkdir(parents=True, exist_ok=True)
    lines = [{"type": "header", "id": rid, "label": label, "vin": VIN, "channels": ["rpm", "e</script>x"],
              "units": {"rpm": "rpm"}, "start": "2026-10-31T10:00:00", "rate_hz": 2.0}]
    for i in range(n):
        lines.append({"type": "row", "t": i * 0.5, "at": "2026-10-31T10:00:00", "v": {"rpm": base + i, "e</script>x": None if i % 2 else 1.0}})
    lines.append({"type": "end", "reason": "stopped", "rows": n})
    (d / f"{rid}.jsonl").write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")


make("rec-a", "Before", 1500, 800.0)
make("rec-b", "After", 20, 900.0)
a = R.load(VIN, "rec-a")
rp = RR.replay_data(a)
check(len(rp["t"]) <= RR.MAX_POINTS + 1 and rp["t"][0] == 0.0 and rp["t"][-1] == a["rows"][-1]["t"], "replay thinned, first and last sample kept")
check(rp["v"]["rpm"][0] == 800.0 and len(rp["v"]["rpm"]) == len(rp["t"]), "replay values are the recorded ones")
pg = client.get(f"/v/{VIN}/recordings/rec-a")
check(pg.status_code == 200 and 'id="rc-replay"' in pg.text and 'id="rp-slider"' in pg.text, "replay controls on the recording page")
check(pg.text.count("</script>x") == 0 and (chr(92) + "u003c/script") in pg.text, "hostile channel name cannot close the data script")
check("window.print()" in pg.text and "Print this recording" in pg.text and "@media print" in pg.text, "print button and print rules")
check('id="rc-diff"' not in pg.text, "no comparison table without a second recording")
cm = client.get(f"/v/{VIN}/recordings/rec-a?vs=rec-b")
check(cm.status_code == 200 and 'id="rc-diff"' in cm.text and "What changed between the two" in cm.text, "comparison table with a second recording")
rows = RR.compare_rows(RR.build_charts(a, R.load(VIN, "rec-b"))["charts"])
rpm = next(x for x in rows if x["channel"] == "rpm")
check(abs(rpm["a_avg"] - (800 + 1499 / 2)) < 1e-6 and abs(rpm["d_avg"] - (rpm["b_avg"] - rpm["a_avg"])) < 1e-9, "difference is computed from the samples")
check("does not say which one was normal" in cm.text, "comparison makes no normality claim")

print(f"{passed}/{passed + len(failures)} checks passed")
for f_ in failures:
    print("FAIL:", f_)
sys.exit(1 if failures else 0)
