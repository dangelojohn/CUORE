"""Checks for the mechanic-first codes page (call, Go-to chips, grouping, folds, search).

Run:  .venv/Scripts/python.exe cuore/tests/check_codes_page.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import codes_call  # noqa: E402

failures: list[str] = []
passed = 0


def check(cond: bool, label: str) -> None:
    global passed
    if cond:
        passed += 1
    else:
        failures.append(label)


def R(dtc, sev, bucket="EVAP", job=True, mods=("Engine / ECM",), descs=("Evaporation system leak - x",)):
    return {"dtc": dtc, "severity": sev, "system_bucket": bucket, "in_job": job, "modules": list(mods),
            "descriptions": list(descs)}


# pure: short names
check(codes_call.short_module("Body / BCM (Body Computer Module)") == "BCM", "short module BCM")
check(codes_call.short_module("Dashboard / IPC (Instrument Panel Cluster)") == "IPC", "short module IPC")
check(codes_call.short_module("Continental ABS MK C1") == "ABS", "short module without slash")
check(codes_call.short_desc(["Communication with Body Computer - Signal plausibility"]) == "Communication with Body Computer",
      "short description drops the failure-type tail")

# pure: the call
rows = [R("P0440-00", "chronic"), R("P0455-00", "chronic"), R("P0456-00", "chronic"),
        R("U1713-2F", "chronic", "Network", mods=("Body / BCM (x)",)), R("P0098-00", "seen-once", job=False)]
c = codes_call.build_call(rows, set(), "fuel out of window", "V1")
check(c["call"].startswith("3 EVAP codes chronic: P0440, P0455, P0456 - fuel level first"), "call names the EVAP trio: " + c["call"])
check(any(s["href"] == "/v/V1/code/P0440" for s in c["call_segs"]), "call codes link to their code page")
check(any(t["href"] == "/v/V1" for t in c["targets"]), "fuel blocker adds the bench chip")
c2 = codes_call.build_call(rows, set(), None, "V1")
check("fuel" not in c2["call"], "no fuel advice without the fuel blocker")
check(c2["call"].endswith("."), "call without blocker still ends cleanly")
check("P0098" not in c["call"], "codes outside the job are not in the call")
check(codes_call.build_call([R("P1", "seen-once", job=False)], set(), None, "V1")["call"].startswith("No open codes"),
      "no job codes -> honest no-open-codes line")

# pure: grouping
g = codes_call.group_rows([R("A", "seen-once", job=False), R("B", "chronic", job=False), R("C", "chronic"), R("D", "cleared")])
check([x["key"] for x in g] == ["chronic", "cleared", "seen-once"], "groups in diagnosis order, empty dropped")
check([r["dtc"] for r in g[0]["rows"]] == ["C", "B"], "job codes first inside a group")
check(g[2]["open"] is False and g[0]["open"] is True, "seen-once folded, chronic open")

# page
client = TestClient(create_app())
VIN = "ZASFAKPN5J7B88115"
r = client.get(f"/v/{VIN}/codes")
t = r.text
check(r.status_code == 200, "page 200")
check('id="codes-call"' in t and re.search(r'id="codes-call">[^<]*(<a [^>]*>[^<]*</a>[^<]*)*codes? ', t) is not None, "one-line call present")
check(t.index('id="codes-call"') < t.index('class="cd-search"'), "call sits above the search")
rq = client.get(f"/v/{VIN}/codes?q=zzzznomatch")
tq = rq.text
check(rq.status_code == 200 and "No code matches" in tq.split('id="codes-call"')[1][:300],
      "filtered call line reflects the filtered (empty) rows")
check('class="cd-gochip cd-go-state"' not in tq, "chips with 0 rows are hidden under a search")
check("unfiltered" in tq, "unfiltered total kept in small text")
check('aria-label="Go to"' in t and 'href="#grp-chronic"' in t, "Go-to chips link to the groups")
check('id="cd-legend"' in t and "What the states mean" in t, "state legend in a fold")
check('id="cd-adv"' in t and t.index('id="cd-adv"') < t.index("Include simulation") < t.index("</details>", t.index('id="cd-adv"')),
      "Include simulation lives inside the Advanced fold")
check(re.search(r'<details class="cd-group cd-g-seen-once" id="grp-seen-once">', t) is not None, "Seen once group is folded")
check(re.search(r'<details class="cd-group cd-g-chronic" id="grp-chronic" open>', t) is not None, "Chronic group is open")
check(t.count('class="row-link cd-row"') >= 30, "every code is a row link")
check(re.search(r'href="/v/' + VIN + r'/code/P0456"', t) is not None, "rows drill to the code page")
check("Distance</dt>" not in re.sub(r'<dt>Distance</dt><dd>[^<]+km', "", t) or "—" not in t, "no empty distance cells")
check("<th" not in t, "the nine-column table is gone")
check(re.search(r"\b\d+\s?(d|mo|y)\s+ago\b", t) is not None, "dates are in the row detail")
check("Reading the state column" not in t and "Ordered by what decides" not in t, "old lede and legend block removed")
m = re.search(r'class="cd-count[^>]*>([^<]+)<', t)
check(bool(m) and "codes over" not in m.group(1) and len(m.group(1)) < 70, "count line is short")
check("cd-mod" in t and "(Body Computer Module)" not in re.sub(r'<dd>[^<]*</dd>', "", t), "long module names only in the detail")
rs = client.get(f"/v/{VIN}/codes?include_simulation=true")
check(rs.status_code == 200 and "Exclude simulation" in rs.text, "simulation toggle round-trips")

# search
rq = client.get(f"/v/{VIN}/codes?q=evap")
check(rq.status_code == 200 and "P0456" in rq.text and "B1176" not in rq.text.split('id="cd-adv"')[0].split('class="cd-count')[0].split("</form>", 1)[1],
      "search evap keeps EVAP codes only")
check('value="evap"' in rq.text and "Clear search" in rq.text, "query kept in the box, clear link shown")
check(re.search(r'id="grp-seen-once"[^>]* open', client.get(f"/v/{VIN}/codes?q=P0098").text) is not None, "a match inside Seen once opens the fold")
rn = client.get(f"/v/{VIN}/codes?q=zzzz")
check("No code matches" in rn.text and "Try a code" in rn.text, "no-match message with hint")

print(f"{passed}/{passed + len(failures)} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
