import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mes import dtc as d
from mes.params import parse_kv_line

print(f"FTB table: {len(d.FAILURE_TYPES)} entries")
by_conf = {}
for ft in d.FAILURE_TYPES.values():
    by_conf.setdefault(ft.confidence, []).append(ft.byte)
for k in ("confirmed","likely","offset"):
    v = by_conf.get(k, [])
    print(f"  {k:10} {len(v):3}  {' '.join(sorted(v))}")

print("\ncorpus anchors (must all be confirmed/corpus):")
for b in ["00","11","15","18","2F","64","86","87","88","97"]:
    ft = d.failure_type(b)
    ok = ft.source == "corpus" and ft.confidence == "confirmed"
    print(f"  {'OK ' if ok else 'BAD'} {b} -> {ft.text}  [{ft.source}/{ft.confidence}]")

print("\nunknown / out-of-range handling:")
for b in ["9A","0F","A5","FF","ZZ","2E"]:
    ft = d.failure_type(b)
    print(f"  {b:3} -> [{ft.confidence}] {ft.text}")

print("\nprecision fix (odometer must not round):")
for line in ["  Odometer: 140572.6 km", "  Gas pedal position: 0.00 %",
             "  Spark advance: -8.188 deg.", "  Battery voltage: 14.3 V"]:
    pv = parse_kv_line(line)
    print(f"  {line.strip():34} -> display={pv.display!r}  value={pv.number}")
