"""Checks for the tappable Systems map (cuore/services/systems_interactive.py + _systems_interactive.html), synthetic
systems and faults in a temp CUORE_STATE_DIR.

  1. node colour / word follows the worst present fault (board order), history-only and no-fault get their own class
  2. selecting a system: dependency chain as a readable line, the parts / buses / upstream systems it depends on,
     the systems that share a cause with it (fault group) with evidence counts, and only those
  3. no-JS output: ?system= draws the selection on the server (classes + words), a details.fold lists one card per
     system with faults, "Electrical path for:" and "Open in layout" and the fault code links are present
  4. routes: 200, unknown ?system= -> 404, unknown VIN still renders; the Jinja global is registered
  5. cache: a warm call rebuilds nothing and takes well under 0.3 s
  6. type scale / 44 px / no sideways scroll constructs in the new css and partial
  7. JS (headless Edge, if present): a tap highlights dependency + shared-cause nodes, shows the card, Escape clears

Run:  .venv/Scripts/python.exe cuore/tests/check_systems_interactive.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

STATE = tempfile.mkdtemp(prefix="cuore-check-sysint-")
os.environ["CUORE_STATE_DIR"] = STATE
os.environ.pop("CUORE_AUDIT_PATH", None)
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore import bootstrap  # noqa: E402,F401
from cuore.app import create_app  # noqa: E402
from cuore.services import cache, systems_interactive as si  # noqa: E402
from cuore.web import systems_interactive_routes as sir  # noqa: E402

VIN = "TESTVIN0000000005"
WEB = ROOT / "cuore" / "web"
failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


# --- synthetic systems (the same shape mes.systems emits) ----------------------------------------------------
def dep(system, carries, conf, path=None, bus=None, why="because"):
    return {"system": system, "why": why, "confidence": conf, "source": "test source",
            "technical": {"carries": carries, "propagates": "it propagates", **({"path": path} if path else {}), **({"bus": bus} if bus else {})}}


GRAPH = {
    "electrical_supply": {"key": "electrical_supply", "label": "Electrical supply", "components": ["12V battery"], "depends_on": [],
                          "technical": {"modules": []}},
    "network": {"key": "network", "label": "Network / CAN buses", "components": ["CAN-C"], "technical": {"modules": [{"code": "BCM", "bus": "CAN-C"}]},
                "depends_on": [dep("electrical_supply", "12 V supply", "CONFIRMED",
                                   path=["f82", "bcm_feed_20a", "bcm", "xy201", "g003a", "g003b"], bus={"name": "CAN-C", "speed": "500 kbit/s"})]},
    "fuel": {"key": "fuel", "label": "Fuel", "components": [], "depends_on": [], "technical": {"modules": []}},
    "evap": {"key": "evap", "label": "EVAP (evaporative emissions)", "components": ["purge valve"], "technical": {"modules": []},
             "depends_on": [dep("electrical_supply", "12 V supply", "SINGLE-SOURCE", path=["esim_connector", "esim_ground"]),
                            dep("fuel", "fuel vapor pressure", "CORROBORATED")]},
    "brakes_abs": {"key": "brakes_abs", "label": "Brakes / ABS", "components": [], "depends_on": [], "technical": {"modules": []}},
}


def card(code, module, status, desc, last="2026-10-26T08:00:00"):
    return {"key": f"code:{module}:{code}", "kind": "code", "code": code, "module": module, "label": f"{code} {desc}", "description": desc,
            "status": status, "last_seen": last, "href": f"/v/{VIN}/code/{code}"}


BOARD = [card("P0440", "ECM", "active", "EVAP leak"), card("U0100", "BCM", "pending", "Lost comms with ECM"),
         card("P0455", "ECM", "pending", "EVAP gross leak"), card("P0171", "ECM", "history", "System too lean")]
GROUPS = [{"id": "sim:code:BCM:U0100", "label": "Fuse F82", "why": "shared Fuse F82", "why_elements": [{"label": "Fuse F82"}],
           "history": {"together": 3, "either": 5, "cleared": 2}, "members": ["code:ECM:P0440", "code:BCM:U0100"], "n": 2, "n_present": 2}]
SYS_OF = {"P0440": "evap", "P0455": "evap", "U0100": "network", "P0171": "fuel"}
builds = {"n": 0}
state = {"board": BOARD, "key": ("k", 1)}

si._graph = lambda: GRAPH
si._cards = lambda vin: state["board"]
si._groups = lambda vin: (GROUPS, False)
si._data_key = lambda vin: state["key"]
si._primary_systems = lambda code, desc, memo: [SYS_OF[code]] if code in SYS_OF else []
_real_build = si._build


def counting_build(*a, **k):
    builds["n"] += 1
    return _real_build(*a, **k)


si._build = counting_build
cache.clear()

# --- 1. node colour follows the worst present fault
m = si.map(VIN)
nodes = {n["key"]: n for n in m["nodes"]}
check(set(nodes) >= {"evap", "network", "fuel", "electrical_supply"}, f"nodes: {sorted(nodes)}")
check(nodes["evap"]["cls"] == "sev-act" and nodes["evap"]["worst"]["code"] == "P0440" and nodes["evap"]["word"] == "Active now",
      f"evap worst = active P0440: {nodes['evap']['cls']} {nodes['evap']['worst']}")
check(nodes["evap"]["n_present"] == 2, "evap counts both present faults")
check(nodes["network"]["cls"] == "sev-pend" and nodes["network"]["word"] == "Pending", "network pending -> amber class with word")
check(nodes["fuel"]["cls"] == "sev-hist" and nodes["fuel"]["worst"] is None and nodes["fuel"]["word"] == "History only", "history-only fault is not 'present'")
check(nodes["electrical_supply"]["cls"] == "sev-none" and nodes["electrical_supply"]["word"] == "No fault on record", "no fault -> neutral class with word")
check(all(n["glyph"] and n["word"] for n in m["nodes"]), "every node has a glyph and a word (never colour alone)")
state["board"] = [BOARD[2], BOARD[0]] + BOARD[1:2] + BOARD[3:]            # the Faults list puts the pending one first
state["key"] = ("k", 2)
m2 = si.map(VIN)
n2 = {n["key"]: n for n in m2["nodes"]}
check(n2["evap"]["worst"]["code"] == "P0455" and n2["evap"]["cls"] == "sev-pend", "worst follows the Faults list order")
state["board"] = [dict(BOARD[0], status="history")] + BOARD[1:]
state["key"] = ("k", 3)
n3 = {n["key"]: n for n in si.map(VIN)["nodes"]}
check(n3["evap"]["cls"] == "sev-pend" and n3["evap"]["worst"]["code"] == "P0455", "an active fault going to history changes the colour")
state["board"] = BOARD
state["key"] = ("k", 1)

# --- 2. selecting a system
s = si.map(VIN, "evap")
sel = s["selected"]
check(sel and sel["key"] == "evap", "selected card is evap")
check(sel["chain_text"].startswith("EVAP \u2190 ") and "ESIM connector" in sel["chain_text"] and "Electrical supply" in sel["chain_text"]
      and "Fuel" in sel["chain_text"], f"chain line: {sel['chain_text']}")
dn = {n["key"]: n for n in s["nodes"]}
deps = set(dn["evap"]["deps"].split())
check({"s:electrical_supply", "s:fuel", "p:esim_connector", "p:esim_ground"} <= deps, f"depends-on tokens: {sorted(deps)}")
check(dn["evap"]["rels"] == ["selected"] and dn["electrical_supply"]["rels"] == ["dep"] and dn["fuel"]["rels"] == ["dep"], "dependency nodes get the dep relation")
check(dn["network"]["rels"] == ["shared"], "shared-cause system gets the second relation")
check("brakes_abs" not in dn, "a system with no fault, no dependency and no shared cause is not drawn")
g = sel["groups"][0]
check(g["n"] == 2 and g["n_present"] == 2 and [o["key"] for o in g["others"]] == ["network"], f"shared-cause group: others {g['others']}")
check(any("appeared together in 3 of 5 reads" in e for e in g["evidence"]) and any("cleared together 2 times" in e for e in g["evidence"])
      and any("Fuse F82" in e for e in g["evidence"]), f"evidence counts: {g['evidence']}")
check({p["id"] for p in s["parts"] if "dep" in p["rels"]} >= {"p:esim_connector", "p:esim_ground"}, "dependency parts highlighted on the drawing")
check(all(p["rel_text"] for p in s["parts"] if p["rels"]) and all(n["rel_text"] for n in s["nodes"] if n["rels"]), "every highlighted item carries a word")
on = {(e["a"], e["b"]) for e in s["edges"] if e["on"]}
check(("evap", "electrical_supply") in on and ("evap", "fuel") in on and ("network", "electrical_supply") not in on, f"dependency edges lit: {sorted(on)}")
check([f["code"] for f in sel["faults"]] == ["P0440", "P0455"] and sel["faults"][0]["age"], "present faults, in Faults-list order, with last seen")
net = si.map(VIN, "network")["selected"]
check("Fuse F82" in net["chain_text"] and "BCM" in net["chain_text"] and net["deps"][0]["bus"] == "CAN-C", f"network chain: {net['chain_text']}")
check(si.map(VIN, "no_such_system") is None, "unknown system -> None")
sup = si.map(VIN, "electrical_supply")["selected"]
check([d["key"] for d in sup["dependents"]] == ["evap", "network"] or {d["key"] for d in sup["dependents"]} == {"evap", "network"},
      "a supply card lists the dependent systems that have present faults")
only = si.map(VIN, "brakes_abs")
check(only and only["selected"] and any(n["key"] == "brakes_abs" for n in only["nodes"]), "a system on the graph but undrawn can still be selected")

# --- 3/4. no-JS output and routes
app = create_app()
app.router.routes[0:0] = sir.router.routes      # must precede system_routes' /systems/{key}
client = TestClient(app)
r = client.get(f"/v/{VIN}/systems/map?system=evap")
html = r.text
check(r.status_code == 200, f"route 200 ({r.status_code})")
check('<details class="fold sx-fold"' in html and " open" not in html.split('<details class="fold sx-fold"')[1][:40], "details.fold present (closed while a system is selected)")
r0 = client.get(f"/v/{VIN}/systems/map")
check(r0.status_code == 200 and '<details class="fold sx-fold" id="sx-fold" open>' in r0.text, "no selection: fold open by default")
for k in ("evap", "network", "fuel"):
    check(f'id="sx-card-{k}"' in html, f"card for {k} rendered without JS")
check("EVAP \u2190 " in html.replace("&larr;", "\u2190") or "&larr;" in html, "dependency chain rendered in the page")
check("Electrical path for: EVAP (evaporative emissions)" in html and "Open in layout" in html, "Electrical path for: and Open in layout")
check(f'href="/v/{VIN}/code/P0440"' in html and f"/v/{VIN}/electrical?code=P0440" in html, "fault code page + electrical path links")
check(re.search(r'class="sx-node [^"]*rel-selected[^"]*"[^>]*id="sx-node-evap"', html) is not None, "server draws the selected node")
check(re.search(r'id="sx-node-electrical_supply"', html) and "rel-dep" in html and "rel-shared" in html and "Depends on" in html and "Shares a cause" in html, "server draws dependency + shared-cause words")
check(re.search(r'<div class="sx-pop"[^>]*>(?!\s*</div>)', html) and "hidden" not in re.search(r'<div class="sx-pop"[^>]*>', html).group(0), "inline card visible without JS")
check(all(f'href="?system={k}#sx"' in html for k in ("evap", "network", "fuel")), "each node is a link to ?system=KEY (no JS)")
check(client.get(f"/v/{VIN}/systems/map?system=zzz").status_code == 404, "unknown ?system= -> 404")
check(client.get("/v/NOSUCHVIN00000001/systems/map").status_code == 200, "unknown VIN renders")
check("systems_interactive_map" in sir.templates.env.globals and sir.systems_interactive_map(VIN, "zzz") is not None, "Jinja global registered; unknown system falls back")
check(client.get(f"/v/{VIN}/systems/map?token=abc&system=evap").text.count("token=abc") > 3, "token carried on links")

# --- 5. cache
cache.clear()
builds["n"] = 0
si.map(VIN, "evap")
t0 = time.perf_counter()
for k in ("evap", "network", "fuel", None):
    si.map(VIN, k)
dt = time.perf_counter() - t0
check(builds["n"] == 1, f"base model built once, then served from the cache ({builds['n']} builds)")
check(dt / 4 < 0.3, f"warm call {dt / 4 * 1000:.1f} ms")

# --- 6. type scale, 44 px
css = (WEB / "static" / "systems_interactive.css").read_text(encoding="utf-8")
css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
sizes = re.findall(r"font-size\s*:\s*([^;}\n]+)", css_nc)
check(sizes and all(re.fullmatch(r"var\(--fs-(md|lg|xl|2xl|3xl)\)", z.strip()) for z in sizes), f"css font sizes are --fs-md and up: {set(sizes)}")
tpl = (WEB / "templates" / "_systems_interactive.html").read_text(encoding="utf-8")
check("font-size" not in tpl and "<style" not in tpl, "no inline font sizes or style blocks")
check(re.search(r"\.sx-node \{[^}]*min-height: 44px", css_nc) and re.search(r"\.sx-btn \{[^}]*min-height: 44px", css_nc)
      and re.search(r"\.sx-part \{[^}]*min-height: 44px", css_nc), "nodes, buttons and part chips are at least 44 px")
check("overflow-x" not in css_nc and "min-width: 3" not in css_nc and "white-space: nowrap" not in css_nc.replace("clip: rect(0 0 0 0); white-space: nowrap", ""), "no horizontal-scroll constructs")
check("minmax(0, 1fr)" in css_nc, "grid columns can shrink (400 px)")

# --- 7. the script, headless Edge
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if os.path.exists(EDGE):
    frag = re.sub(r"<script[^>]*></script>|<link[^>]*>", "", r0.text)
    js = (WEB / "static" / "systems_interactive.js").read_text(encoding="utf-8")
    harness = f"""<!doctype html><html><body>{frag}<pre id="out"></pre>
<script>{js}</script>
<script>
document.addEventListener('DOMContentLoaded', function () {{
var out = {{}};
try {{
  var cls = function (id) {{ return document.getElementById(id).className; }};
  out.fold_closed = !document.getElementById("sx-fold").hasAttribute("open");
  out.pop_hidden0 = document.getElementById("sx-pop").hidden;
  document.getElementById("sx-node-evap").dispatchEvent(new MouseEvent("click", {{bubbles: true, cancelable: true}}));
  out.evap = cls("sx-node-evap"); out.sup = cls("sx-node-electrical_supply"); out.net = cls("sx-node-network"); out.fuel = cls("sx-node-fuel");
  out.sup_tag = document.querySelector("#sx-node-electrical_supply .sx-tag").textContent;
  out.net_tag = document.querySelector("#sx-node-network .sx-tag").textContent;
  out.part = document.querySelector('.sx-part[data-id="p:esim_connector"]').className;
  out.part_other = document.querySelector('.sx-part[data-id="p:f82"]') ? document.querySelector('.sx-part[data-id="p:f82"]').className : "";
  out.edges_on = document.querySelectorAll(".sx-edge.is-on").length;
  out.pop_hidden1 = document.getElementById("sx-pop").hidden;
  out.pop_text = document.getElementById("sx-pop").textContent;
  document.getElementById("sx-node-evap").dispatchEvent(new MouseEvent("click", {{bubbles: true, cancelable: true}}));
  out.toggled_off = document.getElementById("sx-pop").hidden && cls("sx-node-network").indexOf("rel-") < 0;
  document.getElementById("sx-node-network").dispatchEvent(new MouseEvent("click", {{bubbles: true, cancelable: true}}));
  out.net2 = cls("sx-node-network"); out.pop_net = document.getElementById("sx-pop").textContent.indexOf("Fuse F82") > -1;
  document.dispatchEvent(new KeyboardEvent("keydown", {{key: "Escape"}}));
  out.esc = document.getElementById("sx-pop").hidden && cls("sx-node-network").indexOf("rel-") < 0 && document.querySelectorAll(".sx-edge.is-on").length === 0;
}} catch (x) {{ out.err = String(x); }}
document.getElementById("out").textContent = JSON.stringify(out);
}});
</script></body></html>"""
    hp = Path(STATE) / "harness.html"
    hp.write_text(harness, encoding="utf-8")
    proc = subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-first-run", f"--user-data-dir={STATE}/edge",
                           "--virtual-time-budget=3000", "--dump-dom", hp.as_uri()], capture_output=True, text=True, timeout=90)
    mo = re.search(r'<pre id="out">(.*?)</pre>', proc.stdout, re.S)
    res = json.loads(re.sub(r"&quot;", '"', re.sub(r"&amp;", "&", mo.group(1)))) if mo else {}
    check(bool(res) and "err" not in res, f"script ran: {res.get('err') or ('no output' if not res else '')}")
    if res and "err" not in res:
        check(res["fold_closed"] and res["pop_hidden0"], "JS: fold closed, card hidden until a tap")
        check("rel-selected" in res["evap"] and "rel-dep" in res["sup"] and "rel-dep" in res["fuel"] and "rel-shared" in res["net"], f"JS: tap lights selected / dep / shared: {res['evap']} | {res['sup']} | {res['net']}")
        check(res["sup_tag"] == "Depends on" and res["net_tag"] == "Shares a cause", "JS: words on highlighted nodes")
        check("rel-dep" in res["part"] and "rel-dep" not in res["part_other"], "JS: dependency parts lit, others not")
        check(res["edges_on"] >= 2, "JS: dependency lines lit")
        check(not res["pop_hidden1"] and "Dependency chain" in res["pop_text"] and "Electrical path for:" in res["pop_text"], "JS: inline card shown")
        check(res["toggled_off"], "JS: second tap clears")
        check("rel-selected" in res["net2"] and res["pop_net"], "JS: other node selects and shows its own chain")
        check(res["esc"], "JS: Escape clears")
else:
    print("note: Edge not found; JS checks skipped")

print(f"{passed} passed, {len(failures)} failed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
