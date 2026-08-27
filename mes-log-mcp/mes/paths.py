"""Log-root discovery and containment-safe path resolution.

Security note
-------------
The v1 server built target paths with ``Path(LOG_DIR) / name``. On Windows that
does not contain anything: a name of ``..\..\Windows\win.ini`` escapes via the
parent refs, and an *absolute* name replaces the base entirely (pathlib
semantics). Every file the server process could read was reachable through a
tool call.

Everything in this module exists to make that impossible. Callers never build
paths themselves -- they hand a bare filename to :func:`resolve_log`, which
enforces, in order:

1. the name is a bare filename with no directory separators and no drive letter
2. the basename matches a known MES log pattern
3. the fully resolved real path is inside one of the configured roots

Step 3 is the backstop and it runs after ``.resolve()``, so a symlink planted
inside a root that points outside it is still rejected.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from .errors import MesNotFound, MesPathError

# MES filename patterns.
#   FESLog_YYMMDDHHMM_<vehicle description>.txt  -> full engineering session
#   SCAN_YYMMDDHHMM.txt                          -> "scan all systems" summary
FES_RE = re.compile(r"^FESLog_(\d{10})_(.+)\.txt$", re.IGNORECASE)
SCAN_RE = re.compile(r"^SCAN_(\d{10})\.txt$", re.IGNORECASE)

DEFAULT_ROOT = r"C:\Program Files (x86)\MultiEcuScan"

#: Characters that must never appear in a caller-supplied log name.
_SEPARATORS = ("/", "\\", "\x00")


def configured_roots() -> list[Path]:
    """Return the log directories to search, in priority order.

    ``MES_LOG_DIRS`` (os.pathsep-separated) wins, then ``MES_LOG_DIR``, then the
    default MultiEcuScan install path. Multiple roots are supported because MES
    can be pointed at a different log folder, and technicians commonly keep an
    archive directory alongside the live one.
    """
    raw = os.environ.get("MES_LOG_DIRS")
    if raw:
        candidates = [c.strip() for c in raw.split(os.pathsep) if c.strip()]
    else:
        candidates = [os.environ.get("MES_LOG_DIR") or DEFAULT_ROOT]

    roots: list[Path] = []
    seen: set[str] = set()
    for c in candidates:
        try:
            p = Path(c).resolve()
        except (OSError, ValueError):
            continue
        key = str(p).lower()
        if key not in seen:
            seen.add(key)
            roots.append(p)
    return roots


def existing_roots() -> list[Path]:
    """Configured roots that actually exist on disk."""
    return [r for r in configured_roots() if r.is_dir()]


def classify_name(name: str) -> tuple[str, str, str]:
    """Classify a bare filename.

    Returns ``(kind, raw_timestamp, vehicle)`` where kind is ``"fes"``,
    ``"scan"`` or ``""`` for a non-log name. ``raw_timestamp`` is the
    undecoded ``YYMMDDHHMM`` string; ``vehicle`` is empty for SCAN logs, whose
    filenames carry no vehicle.
    """
    m = FES_RE.match(name)
    if m:
        return "fes", m.group(1), m.group(2)
    m = SCAN_RE.match(name)
    if m:
        return "scan", m.group(1), ""
    return "", "", ""


def is_log_name(name: str) -> bool:
    """True if ``name`` is a recognised MES log filename."""
    return classify_name(name)[0] != ""


def _reject_traversal(name: str) -> None:
    if not name or not name.strip():
        raise MesPathError("empty log name")
    for sep in _SEPARATORS:
        if sep in name:
            raise MesPathError(
                f"log name must be a bare filename, got {name!r} "
                "(directory separators are not allowed)"
            )
    # Guards a Windows drive-relative name such as "C:foo.txt", which pathlib
    # treats as anchored and which would otherwise slip past the separator test.
    if len(name) >= 2 and name[1] == ":":
        raise MesPathError(f"log name must not contain a drive letter: {name!r}")
    if name in (".", ".."):
        raise MesPathError(f"invalid log name: {name!r}")


def _contained(child: Path, root: Path) -> bool:
    try:
        child.relative_to(root)
    except ValueError:
        return False
    return True


def resolve_log(name: str, *, require_log_pattern: bool = True) -> Path:
    """Resolve a bare log filename to a real path inside a configured root.

    Raises :class:`MesPathError` if the name is unsafe or resolves outside every
    root, and :class:`MesNotFound` if it is safe but no such file exists.
    """
    _reject_traversal(name)

    if require_log_pattern and not is_log_name(name):
        raise MesPathError(
            f"{name!r} is not a MES log filename "
            "(expected FESLog_YYMMDDHHMM_<vehicle>.txt or SCAN_YYMMDDHHMM.txt)"
        )

    roots = configured_roots()
    for root in roots:
        candidate = root / name
        try:
            real = candidate.resolve()
        except (OSError, ValueError):
            continue
        # Containment is checked against the resolved real path, so a symlink
        # inside the root that points elsewhere does not get through.
        if not _contained(real, root):
            raise MesPathError(
                f"refusing {name!r}: resolves to {real} which is outside {root}"
            )
        if real.is_file():
            return real

    searched = ", ".join(str(r) for r in roots) or "(no roots configured)"
    raise MesNotFound(f"no log named {name!r} in any configured root: {searched}")


def iter_log_files() -> list[Path]:
    """Every recognised MES log file across all existing roots, unsorted.

    Duplicate basenames across roots are resolved by root priority: the first
    root that provides a given filename wins, so an archive root cannot shadow
    the live one.
    """
    out: list[Path] = []
    claimed: set[str] = set()
    for root in existing_roots():
        try:
            entries = list(root.iterdir())
        except OSError:
            continue
        for p in entries:
            key = p.name.lower()
            if key in claimed:
                continue
            try:
                if not p.is_file():
                    continue
            except OSError:
                continue
            if is_log_name(p.name):
                claimed.add(key)
                out.append(p)
    return out
