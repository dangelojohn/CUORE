"""Checks for the per-system dive-in page (``/v/{vin}/systems/{key}``,
phase 1 -- see ``cuore/services/system_detail_bridge.py``).

No Edge/CDP here -- ``fastapi.testclient.TestClient`` only, per this
feature's own test instructions. ``CUORE_STATE_DIR`` is pointed at a
throwaway directory before ``cuore`` is imported (same posture as
``cuore/tests/check_systems_page.py``), and ``cuore/web/system_routes.py``
is included on the app itself if ``create_app()`` did not already pick it
up.

Run:
    .venv/Scripts/python.exe cuore/tests/check_system_page.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-system-")
os.environ.pop("CUORE_AUDIT_PATH", None)

# Network-event / BCM check-first fixture: ``mes.live_obs.observations_path``
# picks the first *writable* CUORE_STATE_DIR candidate that already holds a
# file, else falls through to %PROGRAMDATA%\cuore\observations.jsonl. Copying
# just the 2026-10-13 lines (tonight's live module sweep: BCM U1713-2F
# failing now, U1765-86/U1736-87 history, IPC U1736-86/87, RFHUB B1040-64)
# into CUORE_STATE_DIR makes this fixture deterministic -- read-only against
# the real file, never modified, never relied on to still hold these exact
# lines next time it is read.
_REAL_OBSERVATIONS = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData")) / "cuore" / "observations.jsonl"
if _REAL_OBSERVATIONS.exists():
    _fixture_lines = [ln for ln in _REAL_OBSERVATIONS.read_text(encoding="utf-8").splitlines()
                      if '"2026-10-13' in ln]
    (Path(os.environ["CUORE_STATE_DIR"]) / "observations.jsonl").write_text(
        "\n".join(_fixture_lines) + ("\n" if _fixture_lines else ""), encoding="utf-8")

# Freeze the MES corpus at this fixture's own date (same pattern as check_bench.py): a later real
# clear/scan (e.g. 2026-10-31) turns U1713 "Stale" and the page then has no open code to build the
# network fault tree from, though nothing in the page logic changed.
import re as _re  # noqa: E402
import shutil as _shutil  # noqa: E402
_REAL_MES_DIR = Path(r"C:\Program Files (x86)\MultiEcuScan")
_MES_LOG_DIR = Path(tempfile.mkdtemp(prefix="cuore-check-system-logs-"))
os.environ["MES_LOG_DIR"] = str(_MES_LOG_DIR)
if _REAL_MES_DIR.exists():
    for _f in _REAL_MES_DIR.iterdir():
        _m = _re.search(r"_(\d{6})\d{4}", _f.name)
        if _f.is_file() and not (_m and _m.group(1) > "261013"):
            _shutil.copyfile(_f, _MES_LOG_DIR / _f.name)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import cache, systems_bridge  # noqa: E402
from cuore.web import system_routes, systems_routes, systems_svg  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- real corpus, chronic P0455/P0440/P0456

#: the 8 section headings every system page must carry, exactly as
#: cuore/web/templates/system.html renders them (h2 text, counts stripped).
SECTION_HEADINGS = [
    "Status", "Relationships", "Components", "How it fails here",
    "Hypotheses", "What this car has taught", "Others' experience",
    "What else should I look at?",
]

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


def _app_with_routers():
    app = create_app()
    if not any(getattr(r, "path", "").startswith("/v/{vin}/systems/{key}") for r in app.routes):
        app.include_router(system_routes.router)
    if not any(getattr(r, "path", "") == "/v/{vin}/systems" for r in app.routes):
        app.include_router(systems_routes.router)
    return app


client = TestClient(_app_with_routers())

print("=== all 25 system keys render 200 with the 8 section headings ===")
all_keys = list(systems_bridge.systems().keys())
check("systems() returned the expected 25 keys", len(all_keys) == 25, str(len(all_keys)))

for key in all_keys:
    resp = client.get(f"/v/{VIN}/systems/{key}")
    ok = resp.status_code == 200
    check(f"{key}: page responds 200", ok, str(resp.status_code))
    if not ok:
        continue
    check(f"{key}: no template error leaked onto the page",
          "Jinja2" not in resp.text and "Traceback" not in resp.text)
    missing = [h for h in SECTION_HEADINGS if h not in resp.text]
    check(f"{key}: all 8 section headings present", not missing, str(missing))

print("=== EVAP page lists its chronic codes ===")
evap_resp = client.get(f"/v/{VIN}/systems/evap")
check("evap page responds 200", evap_resp.status_code == 200, str(evap_resp.status_code))
for code in ("P0440", "P0455", "P0456"):
    check(f"evap page lists {code}", f">{code}<" in evap_resp.text)

print("=== EVAP status strip shows P0440 from the car (2026-10-13 live module sweep) ===")
check("evap page shows P0440's live chip (from tonight's ECM UDS read)",
      "from the car" in evap_resp.text and "P0440-00" in evap_resp.text)

print("=== network-cascade system (body/BCM) shows the BCM-supply test ===")
body_resp = client.get(f"/v/{VIN}/systems/body_comfort")
check("body_comfort page responds 200", body_resp.status_code == 200, str(body_resp.status_code))
check("body_comfort page carries the U1713-2F live chip",
      "U1713-2F" in body_resp.text and "BCM" in body_resp.text)
check("body_comfort's 'how it fails here' names the network-cascade's own first test",
      "check BCM supply and grounds first" in body_resp.text)

print("=== unknown key 404s ===")
bad_resp = client.get(f"/v/{VIN}/systems/not_a_real_system")
check("unknown system key responds 404", bad_resp.status_code == 404, str(bad_resp.status_code))

print("=== hot-only edges never say \"depends on\" ===")
# A system pair that only co-occurs (no documented dependency) must read
# "seen together on this car", never "depends on" -- the wording rule a
# dependency edge and a mere correlation must never share. Checked across
# every page's hot-only section, not just one system.
violations = []
for key in all_keys:
    resp = client.get(f"/v/{VIN}/systems/{key}")
    if resp.status_code != 200:
        continue
    text = resp.text
    marker = "Seen together on this car (no documented dependency)"
    if marker in text:
        section = text.split(marker, 1)[1]
        # Only the hot-only block itself (up to the next <details>) matters.
        section = section.split("</details>", 1)[0]
        if "depends on" in section.lower():
            violations.append(key)
check("no \"depends on\" wording inside any hot-only-edges block", not violations, str(violations))

print("=== MECHANIC_REVIEW_3_TESTS_SYSTEMS_LIVE_2026-10-13.md regressions ===")

print("--- F2: vehicle name is never (unnamed vehicle), cold server ---")
cache.clear()
cold_client = TestClient(_app_with_routers())
cold_detail = cold_client.get(f"/v/{VIN}/systems/evap")
check("cold /systems/evap responds 200", cold_detail.status_code == 200, str(cold_detail.status_code))
check("cold /systems/evap never shows (unnamed vehicle)",
     "(unnamed vehicle)" not in cold_detail.text)
check("cold /systems/evap names the Stelvio", "Stelvio" in cold_detail.text)

print("--- F2: visiting /tests first cannot poison the map's vehicle name ---")
poison_client = TestClient(create_app())
poison_client.get(f"/v/{VIN}/tests")
map_after = poison_client.get(f"/v/{VIN}/systems")
check("map (/systems) still responds 200 after /tests", map_after.status_code == 200,
     str(map_after.status_code))
check("map (/systems) still names the Stelvio after /tests was visited first",
     "Stelvio" in map_after.text and "(unnamed vehicle)" not in map_after.text)

print("--- F1: every system's 'Record inspection' href lands on a real id=\"el-*\" ---")
el_id_re = re.compile(r'id="(el-[^"]+)"')
href_re = re.compile(r'href="(/v/[^"]+/electrical\?system=[^"#]*#el-[^"]+)"')
electrical_page_cache: dict[str, set] = {}
dead_links: list[str] = []
checked_links = 0
for key in all_keys:
    resp = client.get(f"/v/{VIN}/systems/{key}")
    if resp.status_code != 200:
        continue
    for href in href_re.findall(resp.text):
        checked_links += 1
        path, _, frag = href.partition("#")
        anchor = "el-" + frag[len("el-"):] if frag.startswith("el-") else frag
        if path not in electrical_page_cache:
            dest = client.get(path)
            electrical_page_cache[path] = set(el_id_re.findall(dest.text)) if dest.status_code == 200 else set()
        if anchor not in electrical_page_cache[path]:
            dead_links.append(f"{key}: {href}")
check("at least one 'Record inspection' link was found to check", checked_links > 0, str(checked_links))
check("every 'Record inspection' href lands on a page with a matching id=\"el-*\"",
     not dead_links, str(dead_links))

print("--- F5: the map's own SVG node links are >=44px tappable ---")
demo_nodes = [{"key": "evap", "label": "EVAP", "status": "active", "code_count": 1}]
svg = systems_svg.render(demo_nodes, [], vin=VIN)
hit_rects = re.findall(r'<rect x="(-?[0-9.]+)" y="(-?[0-9.]+)" width="([0-9.]+)" height="([0-9.]+)" fill="transparent"/>', svg)
check("the node <a> wraps a transparent hit rect", len(hit_rects) >= 1, svg[:400])
if hit_rects:
    _, _, w, h = hit_rects[0]
    check("the node hit rect is >=44px on both axes",
         float(w) >= 44 and float(h) >= 44, f"{w}x{h}")

print("--- F7: the dependency graph has a horizontal-scroll hint, no page-level overflow ---")
evap_page = client.get(f"/v/{VIN}/systems/evap")  # sanity: system detail pages are unaffected
map_resp = client.get(f"/v/{VIN}/systems")
check("map page responds 200", map_resp.status_code == 200, str(map_resp.status_code))
check("map page carries a scroll hint for the graph wrap", "sys-graph-hint" in map_resp.text)
check("the graph wrap stays scoped to overflow-x (never page-level overflow)",
     "overflow-x" in (ROOT / "cuore" / "web" / "static" / "systems.css").read_text(encoding="utf-8"))

print("=== network event: U-codes across modules collapse into one event ===")
network_resp = client.get(f"/v/{VIN}/systems/network")
check("network page responds 200", network_resp.status_code == 200, str(network_resp.status_code))
check("network page shows U1713-2F", "U1713-2F" in network_resp.text)
check("network page marks U1713-2F failing now", "failing now" in network_resp.text)
check("network page gives U1713's FTB meaning (signal erratic)",
     "signal erratic" in network_resp.text)
check("network page names the reporting modules (BCM/IPC/RFHUB)",
     "BCM" in network_resp.text and "IPC" in network_resp.text and "RFHUB" in network_resp.text)
check("network page collapses >=3 comms codes into one event (mes.analysis wording)",
     "one power or bus event" in network_resp.text)

_ne_marker = "Network event ("
_ne_idx = network_resp.text.find(_ne_marker)
check("network page has a Network event section", _ne_idx != -1)
if _ne_idx != -1:
    _ne_section = network_resp.text[_ne_idx:].split("</details>", 1)[0]
    check("the network event section lists at least 3 codes",
         _ne_section.count('class="sysd-row"') >= 3, str(_ne_section.count('class="sysd-row"')))

print("=== U1713's fault tree: diagnostic order before suspecting the bus ===")
check("network page's fault tree checks supply/ground/connector before the bus",
     "before suspecting the bus" in network_resp.text)
check("that diagnostic-order line carries both confidence qualifiers",
     "CORROBORATED" in network_resp.text and "SINGLE-SOURCE" in network_resp.text)

print("=== BCM check-first checklist (body_comfort page) ===")
check("body_comfort page has a Check first section", "Check first (" in body_resp.text)
_cf_idx = body_resp.text.find("Check first (")
if _cf_idx != -1:
    _cf_section = body_resp.text[_cf_idx:].split("</details>", 1)[0]
    _cf_rows = _cf_section.count('class="sysd-row"')
    check("BCM check-first checklist has >=5 rows", _cf_rows >= 5, str(_cf_rows))
    check("check-first rows link to the inspection form or the test page",
         "Record inspection" in _cf_section and "Run test" in _cf_section)
    check("check-first checklist includes the battery, a BCM ground and the CAN termination test",
         "Battery terminals" in _cf_section and "BCM ground" in _cf_section
         and "CAN-C/IHS termination" in _cf_section)
else:
    check("BCM check-first checklist has >=5 rows", False)
    check("check-first rows link to the inspection form or the test page", False)
    check("check-first checklist includes the battery, a BCM ground and the CAN termination test", False)

print("=== EVAP <-> network cross-reference ===")
_xref_re = re.compile(
    r"Network codes have appeared alongside EVAP codes in (\d+) of (\d+) sessions on this car")
_xref_match = _xref_re.search(evap_resp.text)
check("evap page shows the network/EVAP cross-reference line", bool(_xref_match))
if _xref_match:
    together, total = int(_xref_match.group(1)), int(_xref_match.group(2))
    check("cross-reference counts are real (positive, together <= total)",
         0 < together <= total, f"{together} of {total}")
check("evap cross-reference links to the network event, never claims a cause",
     f'/v/{VIN}/systems/network' in evap_resp.text and "the fuel-level signal reaches the ECM over the bus" in evap_resp.text)

print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    print(f"{checks - len(failures)}/{checks} checks passed")
    sys.exit(1)
print(f"{checks}/{checks} checks passed")
