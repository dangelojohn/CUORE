"""Checks for the single-column layout override (mechanics dislike split
screens -- see cuore/web/static/cuore.css's "Single column" section).

Two checks:

  1. The CSS override exists: a marked "Single column" section in
     cuore.css forces `.cols`/`.cols.two`/`.cols.wide-left`/`.cols.three`
     to a single `minmax(0, 1fr)` track with `!important`.
  2. No stylesheet rule outside that override sets a *multi*-column
     `grid-template-columns` on a `.cols` selector without being covered
     by the override (parsed by text, not a real CSS engine -- this is a
     guardrail against regressions, not a full cascade simulator).

Plus a smoke check that the dossier page still renders 200 (same corpus
and posture as check_dossier_page.py).

Run:
    .venv/Scripts/python.exe cuore/tests/check_single_column.py
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-single-column-")
os.environ.pop("CUORE_AUDIT_PATH", None)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

failures: list[str] = []
checks = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not cond:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- check 1: the override section exists -----------------------------------

CSS_PATH = ROOT / "cuore" / "web" / "static" / "cuore.css"
raw_css = CSS_PATH.read_text(encoding="utf-8")

check("cuore.css has a marked 'Single column' section", "Single column" in raw_css)

OVERRIDE_RE = re.compile(
    r"\.cols\s*,\s*\.cols\.two\s*,\s*\.cols\.wide-left\s*,\s*\.cols\.three\s*\{"
    r"[^}]*grid-template-columns\s*:\s*minmax\(\s*0\s*,\s*1fr\s*\)\s*!important\s*;",
    re.S,
)
override_match = OVERRIDE_RE.search(raw_css)
check(
    "override rule forces .cols/.cols.two/.cols.wide-left/.cols.three to a "
    "single minmax(0, 1fr) track with !important",
    override_match is not None,
)


# --- check 2: no un-overridden multi-column .cols rule elsewhere ------------

def strip_comments(text: str) -> str:
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def top_level_tracks(value: str) -> list[str]:
    """Split a grid-template-columns value on whitespace that is NOT
    inside parentheses, so "minmax(0, 1fr) minmax(0, 1fr)" counts as two
    tracks but "minmax(0, 1fr)" (one comma, zero top-level spaces) counts
    as one, and "repeat(auto-fit, minmax(140px, 1fr))" counts as one."""
    depth = 0
    tokens: list[str] = []
    cur = ""
    for ch in value:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch.isspace() and depth == 0:
            if cur:
                tokens.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        tokens.append(cur)
    return tokens


clean_css = strip_comments(raw_css)

# Innermost {...} blocks -- this also flattens one level of @media nesting,
# e.g. "@media (...) { .cols.two { grid-template-columns: A B; } }" yields
# the inner (".cols.two", "grid-template-columns: A B;") pair directly,
# which is exactly the rule we want to inspect.
BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")

overridden_selectors: set[str] = set()
bare_multicolumn: list[tuple[str, str]] = []  # (selector, value)

COLS_CLASS_RE = re.compile(r"\.cols\b")

for selector_text, body_text in BLOCK_RE.findall(clean_css):
    selectors = [s.strip() for s in selector_text.split(",") if s.strip()]
    cols_selectors = [s for s in selectors if COLS_CLASS_RE.search(s)]
    if not cols_selectors:
        continue
    for value in re.findall(r"grid-template-columns\s*:\s*([^;]+);?", body_text):
        important = "!important" in value
        plain_value = value.replace("!important", "").strip()
        tracks = top_level_tracks(plain_value)
        if important and len(tracks) == 1:
            overridden_selectors.update(cols_selectors)
        elif len(tracks) >= 2:
            for sel in cols_selectors:
                bare_multicolumn.append((sel, plain_value))

unprotected = [
    f"{sel!r} sets grid-template-columns: {value!r} and is not covered by "
    f"the !important single-column override"
    for sel, value in bare_multicolumn
    if sel not in overridden_selectors
]
check(
    "every multi-column .cols rule is covered by the single-column override",
    not unprotected,
    "; ".join(unprotected),
)


# --- smoke check: dossier page still renders 200 -----------------------------

from fastapi.testclient import TestClient  # noqa: E402

from cuore.app import create_app  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio -- same real corpus as check_dossier_page.py

client = TestClient(create_app())
page = client.get(f"/v/{VIN}")
check("dossier page renders 200", page.status_code == 200, str(page.status_code))


print()
if failures:
    print(f"{len(failures)}/{checks} check(s) failed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"all {checks} checks passed")
