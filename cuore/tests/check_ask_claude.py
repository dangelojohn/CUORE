"""Checks for the Ask Claude panel (prompt builder, privacy filter, routes,
save-back) and the headless runner (subprocess mocked -- the real CLI is never run).

Run:
    .venv/Scripts/python.exe cuore/tests/check_ask_claude.py
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-askclaude-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "mes-log-mcp"))

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402
from cuore.services import ask_claude, ask_claude_runner as runner  # noqa: E402

VIN = "ZASFAKPN5J7B88115"
CODE = "U1713"
failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- builder ---------------------------------------------------------------
b = ask_claude.build(VIN, CODE)
full = b["head"] + b["tail"]
for sec in ("1. Vehicle", "2. The code", "3. History", "4. Context", "5. Work done",
            "6. Cross-references", "## The ask", "## Ground rules", "BEGIN CUORE DATA"):
    check(f"builder has section {sec}", sec in full)
check("VIN present", VIN in full)
check("ground rules forbid clearing and raw scripts",
      "Do not clear DTCs" in full and "raw adapter scripts" in full)
check("missing data says 'not recorded'", "not recorded" in full)
check("record ids shown for tool lookups", "mcp" in full.lower() or "cuore_read_scan" in full)

# an unknown code on a real VIN still builds and says not recorded
ghost = ask_claude.build(VIN, "P9999")
check("unknown code builds with 'not recorded'", "not recorded" in ghost["head"])

# --- privacy filter --------------------------------------------------------
dirty = ("mail john.doe@example.com call (416) 555-1234 at 12 Maple Street "
         "token = abc123secretvalue key sk-ABCDEFGHIJKLMNOPQRSTUV owner: Mario Rossi")
clean = ask_claude.privacy_filter(dirty)
check("email removed", "example.com" not in clean)
check("phone removed", "555-1234" not in clean)
check("address removed", "Maple Street" not in clean)
check("token removed", "abc123secretvalue" not in clean and "sk-ABCDEF" not in clean)
check("owner name removed", "Rossi" not in clean)
check("[removed] marker used", "[removed]" in clean)
check("VIN and DTC survive the filter",
      ask_claude.privacy_filter(f"{VIN} {CODE}-2F 2026-10-19 00:39:00") == f"{VIN} {CODE}-2F 2026-10-19 00:39:00")
check("compose filters tech inputs",
      "secret@x.org" not in ask_claude.compose(VIN, CODE, "mail secret@x.org", "q"))

# --- routes ----------------------------------------------------------------
client = TestClient(create_app())
page = client.get(f"/v/{VIN}/code/{CODE}")
check("code page renders 200", page.status_code == 200, str(page.status_code))
check("Ask Claude panel present", 'id="ask-claude"' in page.text)
check("observe/question boxes", "What did you observe?" in page.text
      and "What do you want to know?" in page.text)
check("copy button + paste hint", "Copy for Claude" in page.text
      and "Paste into Claude Code in this folder" in page.text)
check("prompt shown as readonly text without JS", "readonly" in page.text and "BEGIN CUORE DATA" in page.text)

save = client.post(f"/v/{VIN}/code/{CODE}/ask-claude/save",
                   data={"text": "Likely BCM ground. <b>x</b>"}, follow_redirects=False)
check("save-back redirects", save.status_code == 303, str(save.status_code))
from mes import notes as notes_mod  # noqa: E402
saved = notes_mod.load(VIN, target_kind="code", target_id=CODE)
mine = [n for n in saved if "claude-analysis" in (n.get("tags") or [])]
check("labelled note created", len(mine) == 1 and mine[0]["text"].startswith(ask_claude.SAVE_PREFIX),
      str(saved))
page2 = client.get(f"/v/{VIN}/code/{CODE}").text
check("saved analysis shown labelled", "Saved Claude analyses" in page2 and "not evidence" in page2)
check("saved text is escaped", "<b>x</b>" not in page2 and "&lt;b&gt;x" in page2)

# --- runner (mocked) -------------------------------------------------------
cmd = runner.build_command("claude")
joined = " ".join(cmd)
check("flags: -p, json, tool lists", "-p" in cmd and "json" in cmd
      and "--allowedTools" in cmd and "--disallowedTools" in cmd)
allowed = cmd[cmd.index("--allowedTools") + 1].split(",")
denied = cmd[cmd.index("--disallowedTools") + 1].split(",")
check("allowed tools are read-only mes-log only",
      all(t.startswith("mcp__mes-log__") for t in allowed)
      and not any(w in t for t in allowed for w in ("add_", "edit_", "hide_", "set_", "open")))
check("no obd2 tool allowed", not any("obd2" in t for t in allowed))
check("obd2 server + Bash/Edit/Write denied",
      {"mcp__obd2", "Bash", "Edit", "Write"} <= set(denied))

runner.available = lambda: True  # type: ignore[assignment]
runner.cli_path = lambda: "claude"  # type: ignore[assignment]
calls: list[dict] = []


class P:
    returncode = 0
    stdout = '{"result": "<script>alert(1)</script> answer", "is_error": false}'
    stderr = ""


def fake_ok(args, **kw):
    calls.append({"args": args, **kw})
    return P()


subprocess.run = fake_ok  # type: ignore[assignment]
r = runner.start("PROMPT", wait=True)
st = runner.status(r["job_id"])
check("mock run done with answer", st["state"] == "done" and "answer" in st["answer"], str(st))
check("prompt sent on stdin, cwd is repo",
      calls[0]["input"] == "PROMPT" and calls[0]["cwd"] == str(ROOT), str(calls[0].keys()))
check("timeout set to 5 minutes", calls[0]["timeout"] == 300)

# lock: hold it, second start is busy
runner._lock.acquire()
check("second run refused while locked", runner.start("x").get("busy") is True)
runner._lock.release()


def fake_timeout(args, **kw):
    raise subprocess.TimeoutExpired(args, kw["timeout"])


subprocess.run = fake_timeout  # type: ignore[assignment]
r = runner.start("PROMPT", wait=True)
st = runner.status(r["job_id"])
check("timeout reported, lock released", st["state"] == "error" and "Timed out" in st["error"]
      and runner.start.__name__ and runner._lock.acquire(blocking=False))
runner._lock.release()

subprocess.run = fake_ok  # type: ignore[assignment]
rr = client.post(f"/v/{VIN}/code/{CODE}/ask-claude/run", data={"observed": "o", "question": "q"})
check("run route returns job id", rr.status_code == 200 and "job_id" in rr.json(), rr.text)
import time  # noqa: E402
for _ in range(50):
    sj = client.get(f"/v/{VIN}/code/{CODE}/ask-claude/status/{rr.json()['job_id']}").json()
    if sj["state"] != "running":
        break
    time.sleep(0.1)
check("status route returns the answer as JSON data", sj["state"] == "done" and "alert(1)" in sj["answer"], str(sj))
js = (ROOT / "cuore/web/static/ask_claude.js").read_text(encoding="utf-8")
check("page JS renders answers via textContent, never innerHTML",
      "textContent" in js and "innerHTML" not in js)

print(f"{checks - len(failures)}/{checks} checks passed")
for f in failures:
    print("FAIL:", f)
sys.exit(1 if failures else 0)
