"""cache.recent_observations must equal live.store.recent_observations, re-read after an append;
dossier_bridge._state_fingerprint ignores the probe file / audit.jsonl but sees real state files."""
import json, os, sys, tempfile, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
tmp = tempfile.mkdtemp(prefix="cuore-check-cacheobs-")
os.environ["CUORE_STATE_DIR"] = tmp
os.environ.pop("MES_LIVE_OBSERVATIONS", None)
from cuore.live import store
from cuore.services import cache, dossier_bridge

fails = []
def check(ok, label):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        fails.append(label)

p = Path(tmp) / "observations.jsonl"
check(cache.recent_observations(5) == [] == store.recent_observations(5), "no file -> []")
rows = [{"at": f"2026-10-0{i}", "kind": "a" if i % 2 else "b", "vin": "V1" if i < 6 else "V2", "data": {"i": i}} for i in range(1, 9)]
p.write_text("\n".join(json.dumps(r) for r in rows[:5]) + "\nnot json\n", encoding="utf-8")
for args in [(50, "", ""), (2, "", ""), (50, "V1", ""), (50, "V1", "a"), (1, "", "b"), (0, "", "a")]:
    check(cache.recent_observations(*args) == store.recent_observations(*args), f"same as store {args}")
time.sleep(0.02)
with p.open("a", encoding="utf-8") as f:
    for r in rows[5:]:
        f.write(json.dumps(r) + "\n")
check([o["data"]["i"] for o in cache.recent_observations(50, "V2")] == [6, 7, 8], "an append is seen")
check(cache.recent_observations(3) == store.recent_observations(3), "same after append")
got = cache.recent_observations(1)
got[0]["data"]["i"] = 99
check(cache.recent_observations(1)[0]["data"]["i"] == 8, "callers get fresh dicts")

fp = dossier_bridge._state_fingerprint()
time.sleep(0.05)
(Path(tmp) / "audit.jsonl").write_text("x\n", encoding="utf-8")
(Path(tmp) / ".write-test").write_text("", encoding="utf-8")
check(dossier_bridge._state_fingerprint() == fp, "audit.jsonl / probe file do not move the fingerprint")
time.sleep(0.05)
(Path(tmp) / "notes.jsonl").write_text("{}\n", encoding="utf-8")
check(dossier_bridge._state_fingerprint() > fp, "a real state file does")
print(f"{'all green' if not fails else str(len(fails)) + ' FAILED'}")
sys.exit(1 if fails else 0)
