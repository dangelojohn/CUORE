import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server

def show(label, raw, limit=700):
    print(f"--- {label} ---")
    print(raw[:limit] + ("..." if len(raw) > limit else ""))
    print()

# The security case first.
print("=== containment ===")
for bad in [r'..\..\Windows\win.ini', r'C:\Windows\win.ini', 'passwd', '../../etc/passwd']:
    r = json.loads(server.read_log(bad))
    ok = "error" in r
    print(f"  {'BLOCKED' if ok else '!! LEAK'}  {bad!r} -> {r.get('error','LEAKED CONTENT')}")

show("status", server.status())
show("vehicles", server.vehicles(), 900)
show("get_freeze_frame P0456", server.get_freeze_frame(code="P0456"), 1400)
show("failure_type 2F", server.failure_type("2F"))
show("failure_type AB (unknown)", server.failure_type("AB"))
show("parameter_series Canister fill", server.parameter_series("Canister fill"), 900)
