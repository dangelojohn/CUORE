import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mes import analysis, catalog, scan, fes

print("=== catalog stats ===")
print(json.dumps(catalog.CATALOG.stats(), indent=2)[:1200])

print("\n=== vehicles ===")
for v in catalog.CATALOG.vehicles():
    print(f"  {v['key'][:20]:22} vin={v['vin'] or '-':20} logs={v['logs']:3} "
          f"real={v['real_logs']:3} sim={v['simulated_logs']:3} {v['first_seen'][:10]}..{v['last_seen'][:10]}")
    for n in v['names'][:2]:
        print(f"      {n}")

print("\n=== Stelvio DTC history (chronic / returned first) ===")
h = analysis.dtc_history(vin="ZASFAKPN5J7B88115")
for code, rec in sorted(h.items(), key=lambda kv: kv[1].first_seen):
    d = rec.to_dict()
    span = d.get("distance_span_km")
    print(f"  {code:10} sessions={d['sessions']} {d['first_seen'][:16]} -> {d['last_seen'][:16]}"
          f"{'  span=' + str(span) + 'km' if span else ''}")
    if "assessment" in d:
        print(f"       ** {d['assessment']}")
    print(f"       {d['descriptions']}")

print("\n=== network event detection on the 11:31 scan ===")
log = scan.load_scan_by_name("SCAN_2608271131.txt", timestamp="2026-08-27 11:31")
by_mod = {m.name: m.dtcs for m in log.modules if m.dtcs}
ev = analysis.detect_network_event(by_mod)
if ev:
    out = ev.to_dict()
    print(f"  confidence={out['confidence']} modules={out['module_count']} dtcs={out['dtc_count']}")
    print(f"  {out['modules_reporting']}")
    print(f"  subjects: {out['subjects_referenced']}")
    print(f"  -> {out['interpretation'][:200]}...")
excluded = [m for m in by_mod if m not in (ev.modules_involved if ev else [])]
print(f"  NOT part of the cascade (genuine component faults): {excluded}")

print("\n=== post-clear assessment on today's FES session ===")
f = fes.load_fes_by_name("FESLog_2608271119_Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir.txt")
a = analysis.post_clear_assessment(f)
print(json.dumps(a.to_dict(), indent=2))
