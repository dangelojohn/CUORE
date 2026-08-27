"""Smoke-check the SCAN parser against every SCAN log in the corpus."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from mes import paths, scan  # noqa: E402

files = sorted((p for p in paths.iter_log_files()
                if paths.classify_name(p.name)[0] == "scan"),
               key=lambda p: p.name)

print(f"{len(files)} SCAN logs\n")
total_dtc = 0
for p in files:
    log = scan.load_scan(p)
    mods = log.modules
    faulty = [m for m in mods if m.dtcs]
    total_dtc += len(log.all_dtcs)
    print(f"{p.name}  enc={log.encoding_used} phases={','.join(log.phases_seen)}")
    print(f"   VIN={log.vin or '(none)'}  raw_blocks={len(log.entries)} "
          f"dedup_modules={len(mods)} faulty={len(faulty)} "
          f"dtcs={len(log.all_dtcs)} aborted={log.aborted} "
          f"conn_fail={log.connection_failures}")
    if log.make or log.model or log.year:
        print(f"   meta: make={log.make!r} model={log.model!r} year={log.year!r}")
    for m in faulty:
        print(f"   [{m.category} / {m.abbrev}] {m.ecu_description}")
        for d in m.dtcs:
            ft = d.failure
            print(f"       {d.full:10} {d.component or d.description}"
                  f"  | ftb={ft.text if ft else '-'} ({ft.confidence if ft else '-'})"
                  f"  | {d.status.value}")
    cr = log.clear_results
    if cr:
        ok = sum(1 for c in cr if c.clear_result == "SUCCESS")
        bad = [c for c in cr if c.clear_result == "FAILED"]
        print(f"   clear: {ok} SUCCESS, {len(bad)} FAILED")
        for c in bad:
            print(f"       FAILED {c.category}/{c.abbrev}: "
                  f"{[d.full for d in c.dtcs]}")
    print()

print(f"TOTAL dtcs across scan phases: {total_dtc}")

# Heading parse regression checks -- the shapes that break naive splitting.
cases = [
    ("Engine / ECM", ("Engine", "ECM", "")),
    ("Gearbox / TCM/NCA/NCR (Automatic Transmission)",
     ("Gearbox", "TCM/NCA/NCR", "Automatic Transmission")),
    ("Airbag / NAB/ORC (Airbag/Occupant Restraint Module)",
     ("Airbag", "NAB/ORC", "Airbag/Occupant Restraint Module")),
    ("Climate control / HVAC (Heating Ventilation Air Conditioning)",
     ("Climate control", "HVAC", "Heating Ventilation Air Conditioning")),
]
print("\nheading parse:")
for raw, want in cases:
    got = scan._parse_heading(raw)
    print(("  OK   " if got == want else "  FAIL ") + raw + f" -> {got}")

print("\nversion split (value contains ' - ' / double space):")
for raw in ["BC330I.0100 - Ver: 04", "F330 MD  bd - Ver: 1062",
            "AR952 HL - Ver: 203C"]:
    print(f"  {raw!r} -> {scan._split_ver(raw)}")
