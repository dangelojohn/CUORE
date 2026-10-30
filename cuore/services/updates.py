"""Update channel: check, apply and roll back a CUORE release from a folder or URL.

The source (``<state_dir>/update_source.json`` ``{"source": "<folder or URL>"}``) holds
a release as built by ``installer/build-release.ps1``: ``release.json`` plus the files
it lists. Nothing is applied unless every file's SHA-256 matches the manifest. Only
files named in the manifest are ever touched, so the venv and the state directory are
never modified. The previous version is kept in ``<install>/.rollback`` (one level).

CLI (used by installer/update-cuore.ps1):
    python -m cuore.services.updates check|apply|rollback --install-dir D [--source S] [--state-dir D]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from .. import __version__

MANIFEST = "release.json"
ROLLBACK = ".rollback"
STAGING = ".staging"


class UpdateError(Exception):
    pass


def install_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _state() -> Path:
    from ..live.config import state_dir
    return state_dir()


def parse_version(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(p) for p in str(v).strip().lstrip("v").split("."))
    except ValueError as e:
        raise UpdateError(f"bad version string: {v!r}") from e


def is_newer(candidate: str, current: str) -> bool:
    a, b = parse_version(candidate), parse_version(current)
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def installed_info(install_dir: Path | None = None) -> dict[str, Any]:
    """Version, build date and commit of this install (a git checkout has no release.json)."""
    root = install_dir or install_root()
    p = root / MANIFEST
    if p.is_file():
        try:
            m = json.loads(p.read_text(encoding="utf-8-sig"))
            return {"version": m.get("version", __version__), "build_date": m.get("build_date", "unknown"),
                    "git_commit": m.get("git_commit", "unknown"), "kind": "release"}
        except (OSError, ValueError):
            pass
    return {"version": __version__, "build_date": "not a release build",
            "git_commit": "unknown", "kind": "checkout"}


# -- source configuration ----------------------------------------------------

def source_path(state: Path | None = None) -> Path:
    return (state or _state()) / "update_source.json"


def get_source(state: Path | None = None) -> str | None:
    try:
        s = json.loads(source_path(state).read_text(encoding="utf-8-sig")).get("source")
        return (str(s).strip() or None) if s else None
    except (OSError, ValueError, AttributeError):
        return None


def set_source(source: str | None, state: Path | None = None) -> None:
    p = source_path(state)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"source": source or ""}, indent=2), encoding="utf-8")


def is_url(source: str) -> bool:
    return source.lower().startswith(("http://", "https://"))


def is_local_folder(source: str | None) -> bool:
    return bool(source) and not is_url(source) and Path(source).is_dir()


# -- manifest + file access --------------------------------------------------

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fetch(source: str, rel: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if is_url(source):
        url = source.rstrip("/") + "/" + rel
        with urllib.request.urlopen(url, timeout=60) as r, open(dest, "wb") as f:  # noqa: S310
            shutil.copyfileobj(r, f)
    else:
        shutil.copy2(Path(source) / rel, dest)


def read_manifest(source: str) -> dict[str, Any]:
    try:
        if is_url(source):
            with urllib.request.urlopen(source.rstrip("/") + "/" + MANIFEST, timeout=30) as r:  # noqa: S310
                text = r.read().decode("utf-8-sig")
        else:
            text = (Path(source) / MANIFEST).read_text(encoding="utf-8-sig")
        m = json.loads(text)
    except (OSError, ValueError) as e:
        raise UpdateError(f"cannot read {MANIFEST} from {source}: {e}") from e
    if not isinstance(m.get("files"), dict) or "version" not in m:
        raise UpdateError("release.json is missing 'version' or 'files'")
    parse_version(m["version"])
    return m


def _safe_rel(rel: str) -> str:
    p = PurePosixPath(rel.replace("\\", "/"))
    if p.is_absolute() or ".." in p.parts or not p.parts or ":" in rel:
        raise UpdateError(f"unsafe path in manifest: {rel!r}")
    if p.parts[0] in {".venv", ".git", ROLLBACK, STAGING} or p.as_posix() == MANIFEST:
        raise UpdateError(f"manifest may not contain: {rel!r}")
    return p.as_posix()


# -- check -------------------------------------------------------------------

def check(source: str | None = None, install_dir: Path | None = None, state: Path | None = None) -> dict[str, Any]:
    """Compare the source's version with this install. Never raises; errors are in the result."""
    src = source or get_source(state)
    cur = installed_info(install_dir)
    out: dict[str, Any] = {"source": src, "current": cur["version"], "latest": None,
                           "available": False, "error": None}
    if not src:
        out["error"] = "no update source configured (updates are off)"
        return out
    try:
        m = read_manifest(src)
        out["latest"] = m["version"]
        out["available"] = is_newer(m["version"], cur["version"])
        out["build_date"] = m.get("build_date")
    except UpdateError as e:
        out["error"] = str(e)
    return out


# -- apply / rollback --------------------------------------------------------

def apply(source: str | None = None, install_dir: Path | None = None, state: Path | None = None,
          force: bool = False) -> dict[str, Any]:
    root = (install_dir or install_root()).resolve()
    src = source or get_source(state)
    if not src:
        raise UpdateError("no update source configured")
    if (root / ".git").exists():
        raise UpdateError("this is a git checkout, not an installed release; refusing to overwrite it")
    m = read_manifest(src)
    cur = installed_info(root)
    if not force and not is_newer(m["version"], cur["version"]):
        raise UpdateError(f"source version {m['version']} is not newer than installed {cur['version']}")
    files = {_safe_rel(k): str(v).lower() for k, v in m["files"].items()}
    st = (state or _state()).resolve()
    for rel in files:
        if (root / rel).resolve().is_relative_to(st):
            raise UpdateError(f"manifest path {rel!r} lies inside the state directory")

    # 1. stage and verify everything before touching the install
    stage = root / STAGING
    shutil.rmtree(stage, ignore_errors=True)
    changed: list[str] = []
    try:
        for rel, want in files.items():
            dest = root / rel
            same = dest.is_file() and sha256_file(dest) == want
            if is_url(src) and same:
                continue
            tmp = stage / rel
            _fetch(src, rel, tmp)
            got = sha256_file(tmp)
            if got != want:
                raise UpdateError(f"hash mismatch for {rel}: manifest {want[:12]}, file {got[:12]}; nothing applied")
            if same:
                tmp.unlink()
            else:
                changed.append(rel)
    except UpdateError:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    except OSError as e:
        shutil.rmtree(stage, ignore_errors=True)
        raise UpdateError(f"could not read the release: {e}") from e

    # 2. keep the previous version
    old_manifest: dict[str, Any] = {}
    if (root / MANIFEST).is_file():
        try:
            old_manifest = json.loads((root / MANIFEST).read_text(encoding="utf-8-sig"))
        except ValueError:
            old_manifest = {}
    old_files = [_safe_rel(k) for k in old_manifest.get("files", {})]
    removed = [r for r in old_files if r not in files and (root / r).is_file()]
    replaced = [r for r in changed if (root / r).is_file()]
    added = [r for r in changed if not (root / r).is_file()]
    rb = root / ROLLBACK
    shutil.rmtree(rb, ignore_errors=True)
    (rb / "files").mkdir(parents=True)
    for rel in replaced + removed:
        (rb / "files" / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, rb / "files" / rel)
    if (root / MANIFEST).is_file():
        shutil.copy2(root / MANIFEST, rb / MANIFEST)
    (rb / "rollback.json").write_text(json.dumps({
        "from_version": cur["version"], "to_version": m["version"],
        "added": added, "replaced": replaced, "removed": removed,
        "had_manifest": (root / MANIFEST).is_file()}, indent=2), encoding="utf-8")

    # 3. swap in; on any failure put the old files back
    try:
        for rel in changed:
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(stage / rel), str(dest))
        for rel in removed:
            (root / rel).unlink()
        (root / MANIFEST).write_text(json.dumps(m, indent=2), encoding="utf-8")
    except Exception as e:
        rollback(root)
        raise UpdateError(f"apply failed and was rolled back: {e}") from e
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    return {"from": cur["version"], "to": m["version"], "changed": len(changed), "removed": len(removed)}


def rollback(install_dir: Path | None = None) -> dict[str, Any]:
    root = (install_dir or install_root()).resolve()
    rb = root / ROLLBACK
    meta_p = rb / "rollback.json"
    if not meta_p.is_file():
        raise UpdateError("nothing to roll back to")
    meta = json.loads(meta_p.read_text(encoding="utf-8"))
    for rel in meta["replaced"] + meta["removed"]:
        dest = root / _safe_rel(rel)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(rb / "files" / rel, dest)
    for rel in meta["added"]:
        p = root / _safe_rel(rel)
        if p.is_file():
            p.unlink()
    if meta.get("had_manifest") and (rb / MANIFEST).is_file():
        shutil.copy2(rb / MANIFEST, root / MANIFEST)
    elif (root / MANIFEST).is_file() and not meta.get("had_manifest"):
        (root / MANIFEST).unlink()
    shutil.rmtree(rb, ignore_errors=True)
    return {"restored_version": meta["from_version"], "from": meta["to_version"]}


def has_rollback(install_dir: Path | None = None) -> bool:
    return ((install_dir or install_root()) / ROLLBACK / "rollback.json").is_file()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="cuore.services.updates")
    ap.add_argument("action", choices=["check", "apply", "rollback"])
    ap.add_argument("--install-dir", type=Path, default=None)
    ap.add_argument("--state-dir", type=Path, default=None)
    ap.add_argument("--source", default=None)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.action == "check":
            r = check(a.source, a.install_dir, a.state_dir)
        elif a.action == "apply":
            r = apply(a.source, a.install_dir, a.state_dir, a.force)
        else:
            r = rollback(a.install_dir)
    except UpdateError as e:
        print(f"ERROR: {e}")
        return 2
    print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
