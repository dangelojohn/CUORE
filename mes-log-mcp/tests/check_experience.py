"""Smoke checks for mes.experience (others' experience: YouTube/forum links).

Cut-down per orchestrator direction: 5 focused checks, plus an optional
network re-verification of 5 random URLs (skipped if offline). A later pass
(2026-10-07) verified several forum threads via headless-browser CDP (see
mes/experience.py module docstring) and added forum_thread entries, so
P0455 is now asserted to have at least one forum_thread alongside video
entries.
"""

import json
import random
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import server  # noqa: E402
from mes import experience  # noqa: E402

failures = []


def check(label, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f" -- {detail}" if detail and not cond else ""))
    if not cond:
        failures.append(label)


CODE_RE = re.compile(r"^[PBCU][0-9A-F]{4}$")

print("=== schema: every entry well-formed, keys known ===")
bad_keys = []
seen_ids = set()
dupes = []
for e in experience.LINKS:
    for field in ("id", "title", "url", "source", "kind", "covers", "verified_at", "verified_how"):
        if not str(e.get(field, "")).strip():
            bad_keys.append(f"{e.get('id')}.{field} empty")
    if e["id"] in seen_ids:
        dupes.append(e["id"])
    seen_ids.add(e["id"])
    for k in e["keys"]:
        if not (CODE_RE.match(k) or k in experience.KNOWN_NON_CODE_KEYS):
            bad_keys.append(f"{e['id']}: unknown key {k!r}")
check("no missing required fields", not bad_keys, str(bad_keys))
check("no duplicate ids", not dupes, str(dupes))

print("=== for_code('P0455') has >=2 entries incl. one how_to_video + one forum_thread ===")
p0455 = experience.for_code("P0455")
check("at least 2 entries for P0455", len(p0455) >= 2, str(p0455))
check("at least one how_to_video for P0455",
      any(e["kind"] == "how_to_video" for e in p0455), str(p0455))
check("at least one forum_thread for P0455",
      any(e["kind"] == "forum_thread" for e in p0455), str(p0455))

print("=== for_job('oil_change') returns tabulated entries ===")
oil = experience.for_job("oil_change")
check("oil_change has at least 1 entry", len(oil) >= 1)

print("=== all() matches LINKS length, no cross-function drift ===")
check("all() returns every entry", len(experience.all()) == len(experience.LINKS))

print("=== MCP tool experience_links ===")
tool_p0455 = json.loads(server.experience_links(code="P0455"))
check("tool code= path matches library", len(tool_p0455) == len(p0455))

# --- optional network re-verification (skipped if offline) -----------------
print("=== optional: re-verify 5 random URLs (skipped if offline) ===")
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
# browser_cdp entries (forum threads) were verified by a real headless
# browser passing a JS bot challenge -- a plain urllib GET cannot pass that
# challenge (it will get HTTP 202, not the thread), so they are excluded
# from this plain-HTTP re-verification sample rather than re-checked wrong.
replayable = [e for e in experience.LINKS if e["verified_how"] != "browser_cdp"]
sample = random.sample(replayable, min(5, len(replayable)))
offline = False
for e in sample:
    url = e["url"]
    try:
        if e["verified_how"] == "youtube_oembed":
            oembed = "https://www.youtube.com/oembed?url=" + urllib.parse.quote(url, safe="") + "&format=json"
            req = urllib.request.Request(oembed, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                ok = resp.status == 200
        else:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=15) as resp:
                ok = resp.status == 200
        check(f"{e['id']} still verifies", ok, url)
    except (urllib.error.URLError, TimeoutError) as exc:
        print(f"  [skip] {e['id']} -- network unavailable ({exc})")
        offline = True
        break

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("all checks passed")
