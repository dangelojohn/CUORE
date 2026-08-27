import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mes import modules

print(json.dumps(modules.registry_stats(), indent=2))
print("\nnormalisation of every heading abbrev seen in the corpus:")
corpus = ["ABS/BSM", "NAB/ORC", "BCM", "RFHUB", "HVAC", "ETM", "IPC", "EPS",
          "ECM", "DTCM", "ESM/GSM/NSC", "TCM/NCA/NCR", "DASM", "TPMS",
          "NBC", "NCM", "NFR", "NGE", "NQS", "NCL", "NSP", "NPB", "NBS",
          "NPG", "RFHM", "CTM", "NRR", "SCM", "HALF", "SGW", "NOPE123"]
for a in corpus:
    d = modules.describe(a)
    flag = "  " if d["domain"] != "unknown" else "??"
    print(f"{flag} {a:14} -> {d['code']:14} {d['tier']:14} {d['domain']:16} {d['name']}")

print("\nCTM collision:")
for cat in ("Dashboard", "Climate control"):
    d = modules.describe("CTM", category=cat)
    print(f"   category={cat:16} -> {d['code']:12} {d['name']}")

print("\nreport sort order (corpus modules):")
for a in sorted(["BCM","ECM","DASM","IPC","RFHUB","DTCM","TPMS","ETM","HVAC","ABS","ORC","EPS"],
                key=modules.sort_key):
    print("  ", a, modules.sort_key(a))
