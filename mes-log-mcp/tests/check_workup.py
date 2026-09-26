"""Smoke checks for the workup dossier and the TSB knowledge table.

Runs against the real corpus (the Stelvio's history is the fixture), so the
assertions pin the facts that are already established in the logs: the
chronic P0456, the 2026-08-27 clear of the three EVAP codes, and the empty
post-clear re-read that must not be allowed to look like a healthy car.

That last one is addressed BY NAME, never as "whatever is newest" -- the
corpus is live, and a fresh capture landing on this VIN would otherwise
silently retire the assertion instead of failing it.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import knowledge  # noqa: E402
from mes.catalog import CATALOG  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


print("=== knowledge table ===")
check("failure byte ignored", [b.number for b in knowledge.tsb_for("P0456-00")]
      == [b.number for b in knowledge.tsb_for("P0456")])
check("P0456 finds the quick-connect and SLVT bulletins",
      {"S2125000002", "18-048-23"}
      <= {b.number for b in knowledge.tsb_for("P0456")})
check("unknown code matches nothing", knowledge.tsb_for("P9999") == [])
m = knowledge.match_codes(["P0440-00", "P0456-00"])
check("two EVAP codes fire the family finding",
      any(f["family"] == "EVAP" for f in m["family_findings"]), m)
m1 = knowledge.match_codes(["P0456-00"])
check("one EVAP code alone does not",
      not any(f["family"] == "EVAP" for f in m1["family_findings"]))
mu = knowledge.match_codes(["U0100", "U0121", "U0140"])
check("three U-codes fire the network finding",
      any(f["family"] == "network" for f in mu["family_findings"]))
check("every bulletin carries its source",
      all(b.to_dict().get("source") for b in knowledge.BULLETINS))

print("=== workup dossier (real corpus) ===")
d = json.loads(server.workup(vin=VIN))
check("identity has odometer span",
      d["identity"]["odometer_first_km"] and d["identity"]["odometer_last_km"])
cp = d["current_picture"]
check("latest session present in the current picture",
      bool(cp.get("latest_session", {}).get("file")))
ca = cp.get("clear_assessment")
check("clear assessment says not proof of repair (when one applies -- the "
      "corpus is live, so the latest session may not contain a clear at "
      "all)",
      ca is None or "NOT proof" in ca.get("verdict", ""))
check("P0456 classified chronic",
      any(r["dtc"] == "P0456-00" for r in d["history"]["chronic"]))
check("TSBs matched for the EVAP codes",
      {"P0440", "P0455", "P0456"} <= set(d["tsb_matches"]["per_code"]))
check("EVAP family finding present",
      any(f["family"] == "EVAP"
          for f in d["tsb_matches"]["family_findings"]))
check("blind spots name the closing tool",
      d["blind_spots"] and all(b.get("closes_it") for b in d["blind_spots"]))
check("EVAP fuel-window blind spot included",
      any("15-85%" in b["why_unknown"] for b in d["blind_spots"]))
check("attempted work listed", len(d["already_attempted"]) > 0)

nomatch = json.loads(server.workup(vin="NOPE123"))
check("unknown VIN is an error, not an empty dossier", "error" in nomatch)

print("=== post-clear look-behind (pinned by name, not by recency) ===")
# These three used to read "whatever is newest", so the first new capture on
# this VIN broke them. They are pinned to the 2026-08-27 pair instead: the
# three EVAP codes were read and erased at 11:19, and 11:20 is the empty
# re-read one minute later. That re-read must never present as a healthy car.
STELVIO = "_Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir.txt"
POST_CLEAR = "FESLog_2608271120" + STELVIO
WITH_FINDINGS = "FESLog_2608271119" + STELVIO
# An older empty re-read, used to prove the look-behind only reaches back:
# the newest findings session BEHIND it is the 2025-09-24 five-code session,
# not the 2026-08-27 one that sits after it.
OLDER_EMPTY = "FESLog_2606071008" + STELVIO
EARLIER_FINDINGS = "FESLog_2509241345" + STELVIO

check("the named logs are still in the corpus",
      all(CATALOG.by_name(n).kind == "fes"
          for n in (POST_CLEAR, WITH_FINDINGS, OLDER_EMPTY,
                    EARLIER_FINDINGS)))

pc = json.loads(server.workup(vin=VIN, name=POST_CLEAR))["current_picture"]
check("name= anchors the current picture on that session, not the newest",
      pc["latest_session"]["file"] == POST_CLEAR,
      pc["latest_session"]["file"])
check("the pinned post-clear re-read is empty on its own",
      pc["latest_session"]["dtcs"] == [], pc["latest_session"]["dtcs"])
lf = pc.get("last_session_with_findings")
check("findings session surfaced behind it", lf is not None
      and lf["file"] == WITH_FINDINGS
      and {x["code"] for x in lf["dtcs"]} == {"P0455", "P0440", "P0456"}, lf)
check("pinned clear assessment says not proof of repair",
      "NOT proof" in pc.get("clear_assessment", {}).get("verdict", ""),
      pc.get("clear_assessment"))
check("all three freeze frames attached",
      set(pc.get("freeze_frames", {})) ==
      {"P0455-00", "P0440-00", "P0456-00"},
      sorted(pc.get("freeze_frames", {})))

ob = json.loads(server.workup(vin=VIN, name=OLDER_EMPTY))["current_picture"]
ol = ob.get("last_session_with_findings")
check("look-behind reaches backwards only, never to a later session",
      ol is not None and ol["file"] == EARLIER_FINDINGS
      and ol["timestamp"] < ob["latest_session"]["timestamp"], ol)

check("naming a scan is an error, not a silent fallback to the newest FES",
      "error" in json.loads(server.workup(name="SCAN_2608271141.txt")))
check("naming a log that does not exist is an error",
      "error" in json.loads(
          server.workup(name="FESLog_9901010000_Nope.txt")))

print()
if failures:
    print(f"{len(failures)} FAILURES: {failures}")
    sys.exit(1)
print("all checks passed")
