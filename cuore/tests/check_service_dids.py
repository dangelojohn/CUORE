"""Checks for the read-only service-value discovery (cuore.live.service_dids).

Run:  .venv/Scripts/python.exe -X utf8 cuore/tests/check_service_dids.py
"""

from __future__ import annotations

import os
import random
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="cuore-check-svcdids-")
os.environ["CUORE_STATE_DIR"] = _TMP
os.environ["CUORE_OBD_PORT"] = "COM99"
os.environ.pop("OBD_PORT", None)
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cuore.live import audit, interlock, service_dids as sd, store  # noqa: E402
from cuore.live.stream import Stream  # noqa: E402
from cuore.live.transport import AdapterLink, set_link  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures: list[str] = []
checks = 0
interlock.mes_status = lambda: {"running": False, "pids": [], "state": "not_running",
                                "label": None}


def check(label, cond, detail=""):
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- plan ---------------------------------------------------------------------------------
p = sd.plan(VIN)
check("plan: IPC and ECM on can_c", [m["code"] for m in p["modules"]] == ["IPC", "ECM"]
      and all(m["bus"] == "can_c" for m in p["modules"]), str(p["modules"]))
check("plan: services is exactly 0x22", p["services"] == ["0x22"])
check("plan: never lists the write services",
      all(s in p["never"] for s in ("0x27", "0x2E", "0x31", "0x3D")))
check("plan: capped, under 3 minutes", 0 < p["max_requests"] <= sd.MAX_REQUESTS
      and p["est_seconds"] <= 180, f"{p['max_requests']} {p['est_seconds']}")
p2 = sd.plan(VIN, modules=["IPC", "ABS", "HVAC", "NOPE"])
check("plan: non-CAN-C modules refused, not planned",
      [m["code"] for m in p2["modules"]] == ["IPC"]
      and {r["code"] for r in p2["refused"]} == {"ABS", "HVAC", "NOPE"}, str(p2["refused"]))

# --- match --------------------------------------------------------------------------------
exp = {"values": [
    {"name": "next service km", "value": 16000, "unit": "km", "source": {}},
    {"name": "last service date", "value": "2026-10-23", "unit": "date", "source": {}},
]}
r1 = {"module": "IPC", "did": "0123", "bytes": ["3E", "80", "00"]}
m1 = sd.match([r1], exp)
check("match: u16 big-endian 16000 at offset 0",
      any(c["offset"] == 0 and c["decoding"] == "u16 big-endian" and c["value"] == 16000
          and c["matches"] == "next service km = 16000" and c["status"] == sd.STATUS
          for c in m1), str(m1))
r2 = {"module": "IPC", "did": "0124", "bytes": ["FF", "26", "10", "23", "00"]}
m2 = sd.match([r2], exp)
check("match: BCD date YYMMDD at offset 1",
      any(c["offset"] == 1 and "BCD YMD" in c["decoding"] and "last service date" in c["matches"]
          for c in m2), str(m2))
dbl = {"values": [{"name": "next service days", "value": 365, "unit": "days"},
                  {"name": "service period days", "value": 365, "unit": "days"}]}
m3 = sd.match([{"module": "IPC", "did": "0125", "bytes": ["01", "6D"]}], dbl)
check("match: double match listed under both with a warning",
      {c["matches"] for c in m3} == {"next service days = 365", "service period days = 365"}
      and all(c.get("warning") for c in m3), str(m3))
rng = random.Random(7)
noise = [{"module": "IPC", "did": f"{i:04X}",
          "bytes": [f"{rng.randrange(256):02X}" for _ in range(8)]} for i in range(20)]
check("match: nothing on random bytes", sd.match(noise, exp) == [], str(sd.match(noise, exp))[:200])
check("match: bad data never raises", sd.match([{"bytes": ["ZZ"]}, None, {}], exp) == []
      and sd.match(None, None) == [])

# --- expected_values on a synthetic Service-log fixture ----------------------------------
logs = Path(tempfile.mkdtemp(prefix="cuore-svc-logs-"))
body = """(Multiecuscan 5.4)
10/23/2026 1:13:10 AM
Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir
Service Interval Reset
--------------------------------------------------------------

ECU ISO code: 00 03 50 8B 14

READING PARAMETERS:
Odometer: 148207.0 km
Last service date: 10/23/2026
Distance till next service: 16000.0 km
Days till next service: 365 days
"""
(logs / "FESLog_2610230114_x.txt").write_text(body, encoding="utf-8")
(logs / "FESLog_2610200620_x.txt").write_text(
    body.replace("Service Interval Reset\n",
                 "Service Interval Reset\nSIMULATION MODE!!! THE DATA IS NOT REAL!!!\n")
    .replace("148207.0", "37").replace("16000.0", "39").replace("10/23/2026 1", "10/20/2026 1"),
    encoding="utf-8")
(logs / "FESLog_2610241300_x.txt").write_text(
    "(Multiecuscan 5.4)\n10/24/2026 12:59:36 PM\nAlfa\nService Interval Reset\n---\n\n"
    "ECU ISO code: 00 03 50 8B 14\n\nEXECUTING ADJUSTMENT...\nNEXT SERVICE KM RESET\nCOMPLETED\n",
    encoding="utf-8")
ev = sd.expected_values(VIN, log_dir=logs)
got = {v["name"]: v for v in ev["values"]}
check("expected: the four values", {k: got[k]["value"] for k in got} == {
    "next service km": 16000, "next service days": 365, "odometer": 148207,
    "last service date": "2026-10-23"}, str(ev["values"]))
check("expected: sources carry log and date, simulated log excluded",
      all(v["source"]["log"] == "FESLog_2610230114_x.txt"
          and v["source"]["at"] == "2026-10-23T01:13:10" for v in ev["values"]), str(ev["values"]))
check("expected: later adjustment without read-back is noted",
      "FESLog_2610241300_x.txt" in ev["note"], ev["note"])
check("expected: missing dir never raises", sd.expected_values(VIN, log_dir=logs / "nope")["values"] == [])


# --- run on a fake adapter ----------------------------------------------------------------
def _frames(header, payload):
    return f"{header}{len(payload) // 2:02X}{payload}"


class FakeCluster(Stream):
    """Answers 22 0123 and 22 0124 on the IPC (target 0x60); every other DID: no data."""
    ANSWERS = {"220123": "6201233E80", "220124": "620124261023"}

    def __init__(self):
        self.sent, self.proto, self._buf, self._open = [], "", bytearray(), False

    def open(self): self._open = True
    def close(self): self._open = False
    def is_open(self): return self._open

    @property
    def describe(self): return "serial COM99@115200 (fake)"

    def _reply(self, cmd):
        if not cmd:
            return ""
        if cmd.startswith("STP "):
            self.proto = cmd[4:]
            return "OK"
        if cmd in ("STM", "STMA"):
            return "1E36000100112233\r1E36000B00112233"
        if cmd.startswith(("AT", "ST")):
            return {"ATI": "ELM327 v2.3", "STI": "STN1170 v4.3.2", "ATRV": "12.4V"}.get(cmd, "OK")
        ans = self.ANSWERS.get(cmd.upper())
        return _frames("18DAF160", ans) if ans else "NO DATA"

    def write(self, data):
        cmd = data.decode("ascii", errors="replace").strip()
        self.sent.append(cmd)
        self._buf.extend(self._reply(cmd).encode("ascii") + b"\r>")

    def read(self, n):
        chunk = bytes(self._buf[:max(n, 1)])
        del self._buf[:max(n, 1)]
        return chunk

    def reset_input_buffer(self): self._buf.clear()
    def in_waiting(self): return len(self._buf)


car = FakeCluster()
lk = AdapterLink(stream_factory=lambda p, b: car, process="check_service_dids")
lk.auto_verify_seconds = 0.2
set_link(lk)
store.confirm_target(VIN, "IPC", 0x60, "check")
small = {"modules": [{"code": "IPC", "bus": "can_c", "why": "t"}],
         "did_ranges": [{"module": "IPC", "start": "0120", "end": "0127", "count": 8, "why": "t"}],
         "services": ["0x22"], "max_requests": 8}
res = sd.run(VIN, max_seconds=30, _plan=small, log_dir=logs, label="before")
check("run: two replies, eight requests", res["replies"] == 2 and res["requests"] == 8, str(res))
check("run: matcher found the planted 16000 and date",
      any(c["did"] == "0123" and c["matches"] == "next service km = 16000" for c in res["matches"])
      and any(c["did"] == "0124" and "last service date" in c["matches"] for c in res["matches"]),
      str(res["matches"]))
check("run: only 0x22 and adapter setup on the wire",
      all(c.startswith(("22", "AT", "ST")) or c in ("", "0100") for c in car.sent), str(sorted(set(c for c in car.sent if not c.startswith(("AT", "ST", "22"))))))
obs = store.recent_observations(50, vin=VIN, kind="service_dids")
check("run: replies recorded as service_dids observations",
      sum(1 for o in obs if o["data"].get("entry") == "reply") == 2
      and sum(1 for o in obs if o["data"].get("entry") == "summary") == 1, str(len(obs)))
atext = ""
try:
    atext = Path(audit.log_path()).read_text(encoding="utf-8")
except Exception as exc:  # noqa: BLE001
    atext = str(exc)
check("run: audited", "service_dids_run_end" in atext and "discover_dids" in atext, atext[:120])
rs = sd.results(VIN)
check("results: candidates plus next step", rs["ran"] and len(rs["candidates"]) >= 2
      and "then diff" in rs["next_step"] and "last_diff" not in rs, str(rs)[:200])
check("results: unknown VIN never raises", sd.results("X" * 17)["ran"] is False)


# --- runs and diff ------------------------------------------------------------------------
runs1 = sd.list_runs(VIN)
check("runs: first run kept with id and label", len(runs1) == 1 and runs1[0]["label"] == "before"
      and runs1[0]["run_id"] and runs1[0]["replies"] == 2, str(runs1))
check("diff: refuses with one run", sd.diff(VIN)["ok"] is False)
# second run: 0123 changes 0x2834 -> 0x3E80 in a fresh baseline; build both fake runs directly
vin2 = "ZASFAKPN5J7B00002"
exp16 = {"values": [{"name": "next service km", "value": 16000, "unit": "km", "source": {}}]}


def fake_run(v, label, replies, tag):
    store.record_observation(sd.OBS_KIND, {
        "entry": "summary", "run_id": tag, "label": label, "started": "2026-10-26T10:0" + tag[-1] + ":00",
        "requests": 8, "replies": len(replies), "matches": [], "errors": [], "aborted_reason": None,
        "reply_data": replies, "expected": exp16["values"]}, vin=v, bus="can_c", cable="", stream="fake")


fake_run(vin2, "before", [
    {"module": "IPC", "did": "0123", "bytes": ["28", "34", "00"]},
    {"module": "IPC", "did": "0124", "bytes": ["01", "02"]},
    {"module": "IPC", "did": "0130", "bytes": ["AA"]}], "run1")
fake_run(vin2, "after", [
    {"module": "IPC", "did": "0123", "bytes": ["3E", "80", "00"]},
    {"module": "IPC", "did": "0124", "bytes": ["01", "02"]},
    {"module": "IPC", "did": "0131", "bytes": ["BB"]}], "run2")
check("runs: two fake runs listed with labels", [(r["run_id"], r["label"]) for r in sd.list_runs(vin2)]
      == [("run1", "before"), ("run2", "after")], str(sd.list_runs(vin2)))
df = sd.diff(vin2, log_dir=logs / "nope")
check("diff: ok, ids and labels", df["ok"] and df["run_a"] == "run1" and df["run_b"] == "run2"
      and df["label_a"] == "before" and df["label_b"] == "after", str(df)[:200])
ch = df["changed"]
check("diff: one changed DID, before/after bytes", len(ch) == 1 and ch[0]["did"] == "0123"
      and ch[0]["before"] == "28 34 00" and ch[0]["after"] == "3E 80 00", str(ch))
top = ch[0]["decodings"][0] if ch and ch[0]["decodings"] else {}
check("diff: u16 BE 10292 -> 16000 at offset 0, annotated against next service km",
      top.get("encoding") == "u16 BE" and top.get("offset") == 0 and top.get("before") == 10292
      and top.get("after") == 16000 and "next service km" in top.get("note", "")
      and "matches the new value" in top["note"], str(ch))
check("diff: status says candidate, never confirmed",
      "candidate write target" in ch[0]["status"] and "third run" in ch[0]["status"])
check("diff: unchanged count", df["unchanged_count"] == 1, str(df["unchanged_count"]))
check("diff: DIDs in one run only listed apart",
      [d["did"] for d in df["only_in_a"]] == ["0130"] and [d["did"] for d in df["only_in_b"]] == ["0131"],
      str(df["only_in_a"]) + str(df["only_in_b"]))
wc = df["write_candidates"]
check("diff: write_candidate summary, unconfirmed",
      len(wc) == 1 and wc[0]["module"] == "IPC" and wc[0]["did"] == "0123" and wc[0]["offset"] == 0
      and wc[0]["encoding"] == "u16 BE" and wc[0]["before"] == 10292 and wc[0]["after"] == 16000
      and wc[0]["length"] == 3 and "unconfirmed" in wc[0]["status"], str(wc))
rs2 = sd.results(vin2)
check("results: last_diff with two runs", rs2["ran"] and rs2["last_diff"]["ok"]
      and rs2["last_diff"]["changed"][0]["did"] == "0123", str(rs2)[:200])
check("diff: explicit ids and bad id", sd.diff(vin2, "run1", "run2")["ok"]
      and sd.diff(vin2, "run1", "nope")["ok"] is False)

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
