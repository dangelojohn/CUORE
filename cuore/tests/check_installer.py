"""Checks for the installer and update channel: release build exclusions, manifest, dry-run install, updates.py, /about.
Run: .venv/Scripts/python.exe -X utf8 cuore/tests/check_installer.py   (no network; temp dirs only)"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP = Path(tempfile.mkdtemp(prefix="cuore_installer_check_"))
os.environ["CUORE_STATE_DIR"] = str(TMP / "state_for_app")
sys.path.insert(0, str(ROOT))

import cuore  # noqa: E402
from cuore.services import updates  # noqa: E402

failures: list[str] = []
count = 0


def check(cond: bool, label: str) -> None:
    global count
    count += 1
    if not cond:
        failures.append(label)


def ps(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                           str(ROOT / "installer" / script), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=600)


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


# -- build ---------------------------------------------------------------------
out = TMP / "dist"
r = ps("build-release.ps1", "-OutDir", str(out), "-SkipZip")
check(r.returncode == 0, f"build-release exit 0 ({r.stderr[-300:]})")
rel = out / f"cuore-{cuore.__version__}"
check(rel.is_dir(), "release folder exists")
check("Excluded by rule" in r.stdout, "exclusions are printed")
check(not any((rel / "docs" / d).exists() for d in ("vehicles", "research", "project", "design", "sessions"))
      and (rel / "docs" / "integration" / "cuore_bundle.schema.json").exists()
      and (rel / "docs" / "handbook").is_dir(), "docs limited to guides + reference + bundle schema")
names = [p for p in rel.rglob("*") if p.is_file()]
low = [str(p.relative_to(rel)).replace("\\", "/") for p in names]
check(not any(x.startswith(".git") or "/.git/" in x for x in low), "no .git")
check(not any(x.startswith(".venv") for x in low), "no .venv")
check(not any("state-backup" in x for x in low), "no state-backup")
check(not any(x.endswith(".jsonl") for x in low), "no jsonl")
check(not any(x.startswith("docs/sessions") or "/sessions/" in x for x in low), "no session folders")
check(not any(x.startswith("data/captures") for x in low), "no captures")
check(not any(k in Path(x).name.lower() for x in low for k in ("password", "secret", "token")), "no secret-named files")
check(not any(Path(x).name.startswith(".env") for x in low), "no .env")
check("cuore/app.py" in low and "mes-log-mcp/mes/__init__.py" in low and "start-cuore.ps1" in low, "app, mes, scripts present")
check("installer/install-cuore.ps1" in low and "requirements.txt" in low, "installer scripts + requirements present")

man = json.loads((rel / "release.json").read_text(encoding="utf-8-sig"))
check(man["version"] == cuore.__version__, "manifest version")
check((rel / "VERSION").read_text().strip() == cuore.__version__, "VERSION matches __version__")
check(bool(man["build_date"]) and "git_commit" in man, "manifest has build date and commit")
check(set(man["files"]) == set(low) - {"release.json"}, "manifest lists every file")
check(all(sha(rel / k) == v for k, v in man["files"].items()), "manifest hashes match files")

# -- installer dry run ------------------------------------------------------------
inst, state = TMP / "inst", TMP / "state"
r = ps("install-cuore.ps1", "-DryRun", "-InstallDir", str(inst), "-StateDir", str(state), "-ReleaseDir", str(rel))
check(r.returncode == 0, f"dry run exit 0 ({r.stdout[-300:]} {r.stderr[-300:]})")
check("Dry run finished" in r.stdout and "web token" in r.stdout and "api/health" in r.stdout, "dry run lists steps")
check(not inst.exists() and not state.exists(), "dry run creates nothing")


# -- updates.py -------------------------------------------------------------------
def make_source(version: str, tag: str) -> Path:
    s = TMP / f"source_{tag}"
    (s / "cuore").mkdir(parents=True)
    files = {"cuore/app.py": "app = 1\n", "cuore/new_mod.py": "x = 1\n", "cuore/changed.py": f"v = '{version}'\n"}
    for k, v in files.items():
        (s / k).write_bytes(v.encode())
    (s / "release.json").write_text(json.dumps({"version": version, "build_date": "2026-01-01", "git_commit": "abc",
                                                "files": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in files.items()}}),
                                    encoding="utf-8")
    return s


check(updates.is_newer("0.2.0", "0.1.0") and not updates.is_newer("0.1.0", "0.1.0") and updates.is_newer("0.10.0", "0.9.0"), "version compare")
live = TMP / "live_install"
(live / "cuore").mkdir(parents=True)
(live / ".venv").mkdir()
(live / ".venv" / "marker.txt").write_text("venv")
old_files = {"cuore/app.py": "app = 1\n", "cuore/changed.py": "v = 'old'\n", "cuore/old_gone.py": "gone = 1\n"}
for k, v in old_files.items():
    (live / k).write_bytes(v.encode())
(live / "release.json").write_text(json.dumps({"version": cuore.__version__, "build_date": "x", "git_commit": "y",
    "files": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in old_files.items()}}), encoding="utf-8")
state2 = TMP / "state2"
state2.mkdir()
(state2 / "keep.txt").write_text("customer data")

check(updates.check(None, live, state2)["error"] is not None, "no source = updates off")
src = make_source("0.2.0", "good")
updates.set_source(str(src), state2)
check(updates.get_source(state2) == str(src), "source stored in update_source.json")
c = updates.check(None, live, state2)
check(c["available"] and c["latest"] == "0.2.0" and c["current"] == cuore.__version__, "newer version detected")
check(not updates.check(str(make_source("0.1.0", "same")), live, state2)["available"], "same version not an update")

bad = make_source("0.3.0", "bad")
(bad / "cuore" / "changed.py").write_text("v = 'tampered'\n", encoding="utf-8")
try:
    updates.apply(str(bad), live, state2)
    check(False, "tampered file rejected")
except updates.UpdateError as e:
    check("hash mismatch" in str(e), "tampered file rejected (hash mismatch)")
check((live / "cuore" / "changed.py").read_bytes() == b"v = 'old'\n" and not (live / "cuore" / "new_mod.py").exists(), "tampered update changed nothing")
check(not (live / updates.STAGING).exists(), "staging cleaned after rejection")

res = updates.apply(str(src), live, state2)
check(res["to"] == "0.2.0" and (live / "cuore" / "new_mod.py").is_file(), "good update applied")
check("0.2.0" in (live / "release.json").read_text(), "installed manifest now 0.2.0")
check(updates.has_rollback(live), "previous version kept")
check((state2 / "keep.txt").read_text() == "customer data" and sorted(p.name for p in state2.iterdir()) == ["keep.txt", "update_source.json"], "state dir untouched")
check(not (live / "cuore" / "old_gone.py").exists() and (live / ".venv" / "marker.txt").is_file(), "dropped file removed, .venv left alone")
try:
    updates.apply(str(src), live, state2)
    check(False, "re-applying same version refused")
except updates.UpdateError:
    check(True, "re-applying same version refused")

rb = updates.rollback(live)
check(rb["restored_version"] == cuore.__version__, "rollback restores previous version number")
check((live / "cuore" / "changed.py").read_bytes() == b"v = 'old'\n" and not (live / "cuore" / "new_mod.py").exists() and (live / "cuore" / "old_gone.py").is_file(), "rollback restored old files, removed added ones")
check(updates.installed_info(live)["version"] == cuore.__version__ and not updates.has_rollback(live), "rollback consumed")

try:
    updates.apply(str(src), ROOT, state2)
    check(False, "git checkout refused")
except updates.UpdateError as e:
    check("git checkout" in str(e), "git checkout refused")

r = ps("update-cuore.ps1", "-DryRun", "-InstallDir", str(live), "-StateDir", str(state2))
check(r.returncode == 0 and "dry run" in r.stdout, "update-cuore dry run")

# -- /about and /api/health -----------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

app_state = Path(os.environ["CUORE_STATE_DIR"])
cl = TestClient(create_app())
h = cl.get("/api/health").json()
check(h["version"] == cuore.__version__ and "build_date" in h and "git_commit" in h, "/api/health shows version, build date, commit")
from cuore.web import about_routes  # noqa: E402

if not any(getattr(rt, "path", "") == "/about" for rt in cl.app.routes):
    cl.app.include_router(about_routes.router)  # until app.py includes it
page = cl.get("/about")
check(page.status_code == 200 and cuore.__version__ in page.text and "Updates are off" in page.text, "/about renders, updates off by default")
updates.set_source(str(src), app_state)
page = cl.get("/about")
check("Update available: 0.2.0" in page.text, "/about auto-checks a local folder source")
updates.set_source("http://127.0.0.1:9/never", app_state)
page = cl.get("/about")
check(page.status_code == 200 and "has not looked" in page.text, "/about does not touch a URL source on load")

shutil.rmtree(TMP, ignore_errors=True)
print(f"check_installer: {count - len(failures)}/{count} passed")
if failures:
    print("FAILED:\n  " + "\n  ".join(failures))
    sys.exit(1)
