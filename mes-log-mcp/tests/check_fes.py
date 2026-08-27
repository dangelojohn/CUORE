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
