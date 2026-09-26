"""Lazy loader for MES's own shipped language/description files.

See ``docs/format/MES_LANGUAGE_FILES.md`` for the full investigation this
module is built on. The short version:

MultiEcuScan ships ``Lang\\English.txt`` (UTF-8) and ``Lang\\English.dat``
(UTF-16LE), both a plain ``<id>[<suffix>]=<text>`` string table used for its
own UI. One id range in each file is relevant to DTCs: ``English.txt``
3101-3204 is the failure-type-byte phrase table :mod:`mes.dtc` already
reconstructs positionally, and ``English.dat`` 20001-23452 (3,449 entries) is
an alphabetised library of DTC "component" name fragments (``Evaporation
system leak``, ``2-4 or 2C hydraulic pressure``, ...).

**Neither file contains a DTC code as a key.** Searched exhaustively (see the
format doc): zero lines, in any of the 16 shipped language files, have a
``[PBCU][0-9A-F]{4}``-shaped token anywhere. The actual code -> fragment
mapping lives in the encrypted ``Files\\data01.dat``...``data06.dat`` (Shannon
entropy 7.0-8.0 bits/byte, no recognisable container format) -- proprietary,
licensed vehicle-database content that this project does not attempt to
decrypt.

So :func:`describe` is honest rather than clever: it loads whatever
``id=text`` entries MES's files actually contain, and looks a code up under a
few plausible key shapes (bare code, ``CODE@MODULE``). Against the currently
installed English.dat/English.txt this returns ``None`` for essentially every
real DTC, because there is nothing to find -- and that is the correct answer,
not a bug. The mechanism is still worth having: it is exercised end-to-end by
synthetic fixtures (a hypothetical MES table that *does* carry code keys), it
is forward-compatible with any future MES release or install that ships one,
and every fragment it loads (FTB phrases, enum labels, component names) stays
available for other cross-referencing uses even without a direct per-code
answer.

Nothing here reads or copies MES's shipped text into this repository -- the
files are read from the user's own install at runtime, on every process,
never persisted or vendored.
"""

from __future__ import annotations

import os
import re
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import paths

#: Env var that overrides the MES install directory this module reads from.
#: Tests point this at a small synthetic fixture directory; production leaves
#: it unset and falls back to :data:`mes.paths.DEFAULT_ROOT` (the same
#: install path ``mes.paths`` uses for logs).
INSTALL_DIR_ENV = "MES_INSTALL_DIR"

#: MES's shipped English string tables, in load order, each with the
#: encoding this investigation confirmed for it. Both are the same
#: ``id[suffix]=text`` grammar; only the byte encoding differs.
LANG_FILES: tuple[tuple[str, str], ...] = (
    ("English.txt", "utf-8-sig"),
    ("English.dat", "utf-16-le"),
)

#: One line of a MES language file: ``<key>=<text>``. The key is whatever
#: precedes the first ``=`` verbatim (decimal id, optional letter suffix like
#: ``1006T``, or -- for a hypothetical future/other table, or a synthetic
#: test fixture -- a literal DTC token). Deliberately permissive: this
#: project does not know every id shape MES has ever shipped, and being
#: stricter here would silently drop entries rather than fail loudly.
_ENTRY_RE = re.compile(r"^([^=\r\n]+)=(.*)$")

#: A bare DTC, optionally with its failure-type-byte suffix stripped.
_BASE_CODE_RE = re.compile(r"^([PBCU][0-9A-F]{4})", re.IGNORECASE)

_SOURCE = "MES English.dat"

_lock = threading.Lock()
_cache: dict[str, Any] | None = None
_cache_install_dir: Path | None = None


@dataclass(frozen=True)
class DtcText:
    """One resolved description, with where it came from."""

    code: str
    text: str
    source: str = _SOURCE
    scoped_module: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "text": self.text,
            "source": self.source,
            "scoped_module": self.scoped_module,
        }


def base_code(code: str) -> str:
    """Strip a failure-type-byte suffix: ``"P0456-00"`` -> ``"P0456"``."""
    m = _BASE_CODE_RE.match(code.strip().upper())
    return m.group(1) if m else code.strip().upper()


def _install_dir() -> Path:
    override = os.environ.get(INSTALL_DIR_ENV)
    if override:
        return Path(override)
    return Path(paths.DEFAULT_ROOT)


def _parse_lang_file(path: Path, encoding: str) -> dict[str, str]:
    """Parse one ``id=text`` file. Missing or unreadable files yield ``{}``,
    never an exception -- a language file that isn't there (or is a
    differently-versioned MES install that dropped it) is not a crash."""
    try:
        raw = path.read_bytes()
    except OSError:
        return {}
    try:
        text = raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        return {}

    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.lstrip("﻿")
        if not line or line.startswith("---") or line.startswith("Title="):
            continue
        m = _ENTRY_RE.match(line)
        if not m:
            continue
        key = m.group(1).strip()
        if key and key not in out:
            out[key] = m.group(2)
    return out


def _load(*, force: bool = False) -> dict[str, Any]:
    """Load and cache MES's language tables from the configured install dir.

    Cached in memory per install dir for the life of the process -- these
    files do not change while MES is running, and re-parsing ~450 KB of
    UTF-16 text on every lookup would be wasteful. ``force`` (used by
    :func:`reload`) re-reads even if a cache is already present, which is
    what test fixtures need when they point ``MES_INSTALL_DIR`` at a new
    directory mid-process.
    """
    global _cache, _cache_install_dir
    install_dir = _install_dir()
    with _lock:
        if _cache is not None and not force and _cache_install_dir == install_dir:
            return _cache

        lang_dir = install_dir / "Lang"
        merged: dict[str, str] = {}
        files_loaded: list[str] = []
        for name, encoding in LANG_FILES:
            entries = _parse_lang_file(lang_dir / name, encoding)
            if entries:
                files_loaded.append(name)
                for key, value in entries.items():
                    merged.setdefault(key, value)

        _cache = {
            "entries": merged,
            "files_loaded": files_loaded,
            "install_dir": str(install_dir),
            "lang_dir": str(lang_dir),
        }
        _cache_install_dir = install_dir
        return _cache


def reload() -> dict[str, Any]:
    """Force a re-read of the language files from the current install dir.

    Tests use this after changing ``MES_INSTALL_DIR`` mid-process; production
    code never needs to call it (the files do not change while a process is
    running).
    """
    return _load(force=True)


def stats() -> dict[str, Any]:
    """Diagnostics: how many entries loaded, from which files, from where."""
    cache = _load()
    return {
        "install_dir": cache["install_dir"],
        "lang_dir": cache["lang_dir"],
        "files_loaded": list(cache["files_loaded"]),
        "entries_loaded": len(cache["entries"]),
    }


def loaded_count() -> int:
    """Total ``id=text`` entries currently loaded, across all language files."""
    return len(_load()["entries"])


def describe(code: str, module: str | None = None) -> dict[str, Any] | None:
    """Look up a DTC's description in MES's own shipped language files.

    Tries, in order, a module-scoped key (``"P0455@PCM"``), the code exactly
    as given, and the code with any failure-type-byte suffix stripped. Returns
    ``None`` when none of those keys exist in the loaded tables.

    Against the currently installed English.dat/English.txt this returns
    ``None`` for virtually every real code -- confirmed in
    ``docs/format/MES_LANGUAGE_FILES.md``, no DTC-code key exists in those
    files today. That is the correct, honest answer: this function never
    fabricates a description. It exists so that (a) the lookup mechanism
    itself is correct and tested, and (b) any future install or MES release
    that *does* ship a code-keyed entry is picked up automatically.
    """
    if not code or not code.strip():
        return None
    raw = code.strip().upper()
    base = base_code(raw)
    entries = _load()["entries"]

    candidates: list[tuple[str, str | None]] = []
    mod = module.strip().upper() if module and module.strip() else None
    if mod:
        candidates.append((f"{base}@{mod}", mod))
        candidates.append((f"{raw}@{mod}", mod))
    candidates.append((raw, None))
    candidates.append((base, None))

    for key, scoped in candidates:
        if key in entries:
            return DtcText(code=base, text=entries[key], source=_SOURCE,
                           scoped_module=scoped).to_dict()
    return None
