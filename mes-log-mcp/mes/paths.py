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

import contextlib
import json
import os
import re
import time
from pathlib import Path
from typing import Any

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


# --- CSV recordings ---------------------------------------------------------
#
# The MES graph subsystem exports timestamped CSV (the only streaming-shaped
# output MES has; the .txt session log is written at completion). No CSV has
# ever been recorded on this install, so the filename convention is UNKNOWN --
# which is why, unlike .txt logs, any bare "*.csv" name is accepted. The
# security posture is unchanged: bare filename only, containment-checked
# against the configured roots after .resolve().

CSV_RE = re.compile(r"^.+\.csv$", re.IGNORECASE)


def csv_roots() -> list[Path]:
    """Directories searched for MES CSV recordings, in priority order.

    MES writes CSV to its Settings "Export Folder", which is configured
    independently of the log folder (both default to the install dir). So the
    CSV roots get their own overrides -- ``MES_CSV_DIRS`` then ``MES_CSV_DIR``
    -- and fall back to the log roots when neither is set.
    """
    raw = os.environ.get("MES_CSV_DIRS")
    if raw:
        candidates = [c.strip() for c in raw.split(os.pathsep) if c.strip()]
    elif os.environ.get("MES_CSV_DIR"):
        candidates = [os.environ["MES_CSV_DIR"]]
    else:
        return configured_roots()

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


def existing_csv_roots() -> list[Path]:
    """CSV roots that actually exist on disk."""
    return [r for r in csv_roots() if r.is_dir()]


def resolve_csv(name: str) -> Path:
    """Resolve a bare ``*.csv`` filename to a real path inside a CSV root.

    Same containment contract as :func:`resolve_log`: traversal-shaped names
    are rejected before touching the filesystem, and the resolved real path
    must sit inside a configured root.
    """
    _reject_traversal(name)
    if not CSV_RE.match(name):
        raise MesPathError(f"{name!r} is not a CSV filename")

    roots = csv_roots()
    for root in roots:
        candidate = root / name
        try:
            real = candidate.resolve()
        except (OSError, ValueError):
            continue
        if not _contained(real, root):
            raise MesPathError(
                f"refusing {name!r}: resolves to {real} which is outside {root}"
            )
        if real.is_file():
            return real

    searched = ", ".join(str(r) for r in roots) or "(no roots configured)"
    raise MesNotFound(f"no CSV named {name!r} in any configured root: {searched}")


def iter_csv_files() -> list[Path]:
    """Every ``*.csv`` across the CSV roots; first root wins on name clashes."""
    out: list[Path] = []
    claimed: set[str] = set()
    for root in existing_csv_roots():
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
            if CSV_RE.match(p.name):
                claimed.add(key)
                out.append(p)
    return out


# --- append-only JSONL helpers shared by the record stores -------------------


def read_jsonl(p: Path) -> list[dict[str, Any]]:
    """Every parseable JSON-object line of an append-only store.

    One bad line must never sink the store, so: undecodable bytes (a write
    torn mid-character) are replaced instead of raising, lines are split on
    ``\n`` only (``str.splitlines`` also splits on U+2028/U+2029/U+0085,
    which ``json.dumps(ensure_ascii=False)`` writes raw -- a note containing
    one would be cut in two and lost), unparseable lines are skipped, and a
    valid-JSON line that is not an object is skipped (callers do
    ``rec.get(...)``).
    """
    try:
        if not p.exists():
            return []
        text = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


@contextlib.contextmanager
def _append_lock(p: Path):
    """Cross-process mutex for appends to one store (best effort).

    On Windows an ``O_APPEND`` write is "seek to end, then write" -- two
    processes (the CUORE server and an MCP server both write the same
    stores) can seek to the same offset and overwrite each other's record.
    Measured: 4 processes x 150 appends kept 522 of 600 lines. A byte-range
    lock on a sidecar ``<store>.lock`` file serialises them; if it cannot
    be taken within ~2 s the append goes ahead unlocked rather than failing.
    """
    fd = None
    locked = False
    try:
        fd = os.open(str(p.with_name(p.name + ".lock")), os.O_RDWR | os.O_CREAT)
        try:
            import msvcrt
        except ImportError:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
            locked = True
        else:
            for _ in range(400):
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    locked = True
                    break
                except OSError:
                    time.sleep(0.005)
    except OSError:
        pass
    try:
        yield
    finally:
        if fd is not None:
            if locked:
                try:
                    import msvcrt
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except (ImportError, OSError):
                    pass  # flock (non-Windows) is released by close
            os.close(fd)


def append_jsonl(p: Path, entry: dict[str, Any]) -> None:
    """Append one record as a single write. If a previous writer died
    mid-line (file does not end in a newline) the new record starts on a
    fresh line instead of being glued onto the torn one and lost with it."""
    p.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(entry, ensure_ascii=False) + "\n").encode("utf-8")
    with _append_lock(p), p.open("a+b") as f:
        try:
            f.seek(0, os.SEEK_END)
            if f.tell() > 0:
                f.seek(-1, os.SEEK_END)
                if f.read(1) not in (b"\n", b""):
                    data = b"\n" + data
        except OSError:
            pass
        f.seek(0, os.SEEK_END)
        f.write(data)
        f.flush()


# --- state_dir memo ---------------------------------------------------------

_STATE_TTL = 30.0


def memo_state_dir(fn):
    """Memoise a ``state_dir()`` that probes writability by creating a file.

    A page render calls ``state_dir()`` hundreds of times and each call did a
    mkdir + write + unlink. The answer only changes when the environment does
    or the directory goes away, so key on those and re-probe at least every
    ``_STATE_TTL`` seconds (a directory that turned read-only is still noticed).
    """
    import functools
    cache: dict[tuple, tuple[float, float, Path]] = {}

    @functools.wraps(fn)
    def wrapper():
        env = os.environ
        ov = env.get("CUORE_STATE_DIR")
        if ov and not os.path.isabs(ov):
            return fn()                      # cwd-relative: never memoise
        key = (ov, env.get("PROGRAMDATA"), env.get("LOCALAPPDATA"))
        hit = cache.get(key)               # (checked_at, probed_at, dir)
        now = time.monotonic()
        if hit and now - hit[1] < _STATE_TTL:
            if now - hit[0] < 2.0:
                return hit[2]
            if os.path.isdir(hit[2]):
                cache[key] = (now, hit[1], hit[2])
                return hit[2]
        value = fn()
        cache[key] = (now, now, value)
        return value

    wrapper.__wrapped_state_dir__ = fn
    return wrapper
