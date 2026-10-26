import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mes import paths, fes, catalog

files = sorted((p for p in paths.iter_log_files()
                if paths.classify_name(p.name)[0] == "fes"), key=lambda p: p.name)
print(f"{len(files)} FES logs\n")

errors, sim, real_with_dtc = 0, 0, []
for p in files:
    try:
        log = fes.load_fes(p, timestamp=str(catalog.parse_stamp(paths.classify_name(p.name)[1]) or ""))
    except Exception as e:
        errors += 1
        print(f"!! PARSE FAIL {p.name}: {type(e).__name__}: {e}")
        continue
    if log.simulation:
        sim += 1
        continue
    if log.dtcs or log.actuators or log.samples or log.warnings:
        real_with_dtc.append(log)

print(f"parse failures: {errors} | simulation: {sim} | real w/ content: {len(real_with_dtc)}\n")

for log in real_with_dtc:
    print(f"=== {log.name}")
    print(f"    session={log.session_time} ecu={log.ecu_description}")
    print(f"    vin={log.vin} odo={log.odometer_km} reads={log.read_sections} clears={log.clear_events} nofault={log.reported_no_faults}")
    for d in log.dtcs:
        ff = len(d.freeze_frame)
        print(f"      {d.full:10} {d.status.value:9} ff={ff:2}  {d.description}")
    for a in log.actuators:
        print(f"      [{a.kind}] {a.operation!r} -> {a.outcome or '(none)'} {a.reason}")
    if log.samples:
        print(f"      samples={len(log.samples)} params={len(log.param_names())}")
    for w in log.warnings:
        print(f"      WARN: {w}")
    print()

# --- strip_control equivalence + memo invalidation ---------------------------
import os, tempfile
from mes import encoding

tricky = "a\x00b\x03c\td\ne\rf\x0bg\x0ch\x1fi\x7fj°k\x08"
assert encoding.strip_control(tricky) == ("abc\td\ne\rfghi\x7fj°k", 6), "strip_control"
assert encoding.strip_control("clean\r\n") == ("clean\r\n", 0)

with tempfile.TemporaryDirectory() as td:
    tp = Path(td) / "FESLog_2601010000_x.txt"
    tp.write_text("(Multiecuscan 5.0)\n1/1/2026 10:00:00 AM\nCar A\nECU A\n", encoding="utf-8")
    first = fes.load_fes(tp)
    assert fes.load_fes(tp) is first, "memo should hit for an unchanged file"
    tp.write_text("(Multiecuscan 5.0)\n1/1/2026 10:00:00 AM\nCar B\nECU B\n", encoding="utf-8")
    os.utime(tp, ns=(1_800_000_000 * 10**9, 1_800_000_000 * 10**9))
    second = fes.load_fes(tp)
    assert second is not first and second.vehicle == "Car B", "memo must refresh after mtime change"
print("memo/strip_control checks OK")
