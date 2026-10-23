"""Checks for the ESIM switch probe (cuore.live.esim_probe): three groups.

  1. Parser: good lines, ignored lines (banner, comment, blank), malformed lines.
  2. State rules: CLOSED / OPEN / FAULT boundaries, the NO_REF option, and the
     refusal of COM3 as a probe port.
  3. Simulator feed: the scripted trace through ProbeFeed, then a probe-only
     live session (no OBD adapter) with a recording, the "esim-switch-watch"
     preset, and the live board listing the probe channels.

No hardware, no COM port, no network. Run:
    .venv/Scripts/python.exe cuore/tests/check_esim_probe.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-esim-probe-")
os.environ.pop("CUORE_AUDIT_PATH", None)
os.environ.pop("CUORE_ESIM_PROBE_PORT", None)
os.environ.pop("CUORE_ESIM_PROBE_NO_REF", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from cuore import bootstrap  # noqa: E402,F401
from cuore.live import channels as channels_mod  # noqa: E402
from cuore.live import esim_probe as ep  # noqa: E402
from cuore.live import poller as poller_mod  # noqa: E402
from cuore.live.errors import Refused  # noqa: E402
from cuore.services import liveboard_bridge  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(label)
    print(("PASS " if cond else "FAIL ") + label + (f"  [{detail}]" if detail and not cond else ""))


def wait_until(pred, timeout: float = 8.0) -> bool:
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if pred():
            return True
        time.sleep(0.02)
    return pred()


# ---------------------------------------------------------------------------
# 1. parser
# ---------------------------------------------------------------------------
s = ep.parse_line("ESIM,12345,4960,5010,OPEN\r\n")
check("parse: good OPEN line", s == ep.ProbeSample(12345, 4960, 5010, "OPEN"), str(s))
s = ep.parse_line("esim-nope")
check("parse: banner is ignored (None)", s is None)
check("parse: '# comment' and blank are ignored",
      ep.parse_line("# ESIM probe v1 115200") is None and ep.parse_line("") is None
      and ep.parse_line("   \n") is None)
check("parse: lower-case state accepted", ep.parse_line("ESIM,1,100,5000,closed").state == "CLOSED")
bad = ["ESIM,1,2,3", "ESIM,1,2,3,OPEN,9", "ESIM,x,2,3,OPEN", "ESIM,1,2,3,MAYBE",
       "ESIM,-5,100,5000,OPEN", "ESIM,1,99999,5000,OPEN", "ESIM,1,4000.5,5000,OPEN"]
raised = []
for line in bad:
    try:
        ep.parse_line(line)
        raised.append(False)
    except ep.ProbeParseError:
        raised.append(True)
check("parse: every malformed ESIM line raises ProbeParseError", all(raised), str(raised))

# ---------------------------------------------------------------------------
# 2. state rules
# ---------------------------------------------------------------------------
cs = ep.classify_state
check("rule: sig 120 mV, ref 5000 mV = CLOSED", cs(120, 5000) == "CLOSED")
check("rule: sig 799 / ref 4501 = CLOSED (inside both limits)", cs(799, 4501) == "CLOSED")
check("rule: sig 800 = not CLOSED (limit is strict <)", cs(800, 5000) == "FAULT")
check("rule: sig 120 with ref 4500 = FAULT (ref must be > 4.5 V)", cs(120, 4500) == "FAULT")
check("rule: sig 120 with ref 0 (open reference) = FAULT", cs(120, 0) == "FAULT")
check("rule: sig 4001 = OPEN, sig 4000 = FAULT (limit is strict >)",
      cs(4001, 5000) == "OPEN" and cs(4000, 5000) == "FAULT")
check("rule: sig 2500 (between the thresholds) = FAULT", cs(2500, 5000) == "FAULT")
check("rule: sig 0 / ref 0 (dead wiring) = FAULT", cs(0, 0) == "FAULT")
check("rule: require_ref=False ignores the reference", cs(120, 0, require_ref=False) == "CLOSED")
for bad_port in ("COM3", "com3", " Com3 "):
    try:
        ep.validate_port(bad_port)
        refused = False
    except Refused:
        refused = True
    check(f"safety: probe port {bad_port!r} is refused", refused)
check("safety: 'sim' needs no port", ep.validate_port("sim") == "sim")
check("safety: another COM port is accepted", ep.validate_port("COM7") == "COM7")

# ---------------------------------------------------------------------------
# 3. simulator feed
# ---------------------------------------------------------------------------
got: dict[str, list] = {c: [] for c in ep.CHANNEL_IDS}
transitions: list[str] = []
feed = ep.ProbeFeed(ep._SimSource(loops=1, realtime=False), set(ep.CHANNEL_IDS),
                    lambda cid, v, u: got[cid].append((v, u)), lambda cid, t: None,
                    on_transition=transitions.append)
for line in ep.sim_lines(loops=1):
    feed.handle_line(line)
n = len(got[ep.CH_STATE])
check("sim: one loop publishes the same count on all three channels",
      n > 400 and n == len(got[ep.CH_SIG]) == len(got[ep.CH_REF]), str(n))
codes = {v for v, _u in got[ep.CH_STATE]}
check("sim: trace contains OPEN, CLOSED and FAULT", codes == {0, 1, -1}, str(codes))
check("sim: units are state / mV / mV",
      got[ep.CH_STATE][0][1] == "state" and got[ep.CH_SIG][0][1] == "mV" and got[ep.CH_REF][0][1] == "mV")
check("sim: no state mismatch and no bad line", feed.state_mismatches == 0 and feed.bad_lines == 0,
      str(feed.status()))
check("sim: transitions seen (open->closed->open..., bounce, fault)",
      transitions[:2] == ["CLOSED", "OPEN"] and transitions.count("CLOSED") >= 4
      and "FAULT" in transitions, str(transitions[:10]))

# registry, preset, recording preset
reg = channels_mod.registry()
check("registry: probe channels exist with kind 'probe'",
      all(reg[c].kind == "probe" for c in ep.CHANNEL_IDS))
rp = channels_mod.recording_presets().get("esim-switch-watch")
want = ["esim_switch_state", "esim_signal_mV", "esim_ref_mV", "commanded_evap_purge",
        "short_fuel_trim_b1", "engine_rpm", "vehicle_speed", "fuel_level"]
check("preset: 'esim-switch-watch' recording preset lists probe + PIDs 2E 06 0C 0D 2F",
      rp is not None and rp["channels"] == want, str(rp and rp["channels"]))
check("preset: hyphen name resolves like the underscore one",
      [c.id for c in channels_mod.resolve_channels(preset="esim-switch-watch")] == want)

# board
b = liveboard_bridge.board()
grp = next((g for g in b["groups"] if g["id"] == "probe"), None)
check("board: ESIM probe group lists the three channels",
      grp is not None and {c["id"] for c in grp["channels"]} == set(ep.CHANNEL_IDS),
      str(grp and [c["id"] for c in grp["channels"]]))
try:
    channels_mod.resolve_channels(b["all_channel_ids"], "")
    resolves = True
except Exception as e:  # noqa: BLE001
    resolves = False
    print("   ", e)
check("board: every all_channel_ids entry still resolves", resolves)

# a probe-only live session: no OBD adapter, fast simulator, with a recording
os.environ[ep.ENV_PORT] = "sim"
orig_make = ep.make_source
go = __import__("threading").Event()


class _GatedSim(ep._SimSource):
    """Fast simulator that holds its first line until the recording is running."""

    def lines(self, stop):
        go.wait(5)
        yield from super().lines(stop)


ep.make_source = lambda port, realtime=True: _GatedSim(loops=1, realtime=False)
p = poller_mod.LivePoller()
try:
    st = p.start(channels_mod.resolve_channels(list(ep.CHANNEL_IDS)))
    check("session: probe-only session starts with no OBD adapter", st["active"] is True, str(st))
    rec = p.start_recording("esim-sim")
    check("session: recording started", bool(rec.get("recording")), str(rec))
    go.set()
    ok = wait_until(lambda: p._probe is not None and p._probe.samples >= 540)
    snap = p.snapshot()["channels"]
    check("session: all three probe channels carry values",
          ok and all(snap[c]["value"] is not None for c in ep.CHANNEL_IDS), str(snap))
    check("session: status carries the probe block",
          p.status()["esim_probe"]["samples"] >= 540, str(p.status()["esim_probe"]))
    done = p.stop_recording()
    p.stop()
finally:
    ep.make_source = orig_make
    os.environ.pop(ep.ENV_PORT, None)
text = Path(done["path"]).read_text(encoding="utf-8").splitlines()
check("recording: header names the probe columns",
      "ESIM switch signal" in text[0] and "ESIM 5 V reference" in text[0] and text[1].count("mV") == 2,
      text[0][:120])
check("recording: about one row per sample and transition tags written",
      done["rows"] >= 500 and any('"ESIM CLOSED"' in ln for ln in text) and any('"ESIM OPEN"' in ln for ln in text),
      str(done["rows"]))
os.environ[ep.ENV_PORT] = "COM3"
try:
    poller_mod.LivePoller().start(channels_mod.resolve_channels(list(ep.CHANNEL_IDS)))
    refused = False
except Refused:
    refused = True
finally:
    os.environ.pop(ep.ENV_PORT, None)
check("session: CUORE_ESIM_PROBE_PORT=COM3 refuses to start", refused)

print(f"\n{checks - len(failures)}/{checks} checks passed")
if failures:
    print("FAILED:", *failures, sep="\n  ")
    sys.exit(1)
