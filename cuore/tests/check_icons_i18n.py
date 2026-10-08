"""Smoke checks for the pictogram sprite (icons.svg/icons.py) and the UI
string dictionary (i18n.py).

No live server, no browser -- this just imports the two modules and reads
the sprite file as text, same lightweight style as the other `check_*.py`
scripts that don't need a running app (see e.g. check_feedback.py for the
heavier pattern that spins up a TestClient; not needed here since icons.py
and i18n.py have no routes of their own).

Run:
    .venv/Scripts/python.exe cuore/tests/check_icons_i18n.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "mes-log-mcp"))

from cuore.web import icons as icons_mod  # noqa: E402
from cuore.web import i18n  # noqa: E402

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# ---------------------------------------------------------------------------
# Reference lists pulled straight from the source-of-truth modules, so this
# test fails loudly if mes-log-mcp adds/renames a system or symptom tag and
# nobody updated cuore.web.icons to match.
# ---------------------------------------------------------------------------

try:
    from mes.systems import SYSTEMS  # type: ignore
    SYSTEM_KEYS = list(SYSTEMS.keys())
except Exception as exc:  # noqa: BLE001
    SYSTEM_KEYS = []
    failures.append(f"could not import mes.systems.SYSTEMS -- {exc}")

try:
    from mes.symptoms import SYMPTOM_TAGS  # type: ignore
    SYMPTOM_KEYS = list(SYMPTOM_TAGS)
except Exception as exc:  # noqa: BLE001
    SYMPTOM_KEYS = []
    failures.append(f"could not import mes.symptoms.SYMPTOM_TAGS -- {exc}")


# ---------------------------------------------------------------------------
# Check 1: every ICONS key has a matching <symbol id="i-<key>"> in icons.svg
# ---------------------------------------------------------------------------

svg_path = REPO_ROOT / "cuore" / "web" / "static" / "icons.svg"
svg_text = svg_path.read_text(encoding="utf-8")
symbol_ids = set(re.findall(r'<symbol\s+id="([^"]+)"', svg_text))

for key, entry in icons_mod.ICONS.items():
    want_id = f"i-{entry['symbol']}"
    check(f"icons.svg has symbol for ICONS[{key!r}]", want_id in symbol_ids,
          f"expected <symbol id=\"{want_id}\"> in icons.svg")

check("icons.svg has no stray/duplicate symbol ids",
      len(symbol_ids) == len(re.findall(r'<symbol\s+id="', svg_text)),
      "duplicate <symbol id=...> found in icons.svg")

# ---------------------------------------------------------------------------
# Check 2: every step / system / symptom / status / priority has an icon
# ---------------------------------------------------------------------------

for key in icons_mod.STEP_KEYS:
    check(f"step {key!r} is in ICONS", key in icons_mod.ICONS)

for sys_key in SYSTEM_KEYS:
    icon_key = f"sys_{sys_key}"
    check(f"system {sys_key!r} has icon {icon_key!r}", icon_key in icons_mod.ICONS)

check("ICONS has exactly the 25 mes.systems keys (no drift)",
      sorted(k for k in icons_mod.ICONS if k.startswith("sys_"))
      == sorted(f"sys_{k}" for k in SYSTEM_KEYS))

for tag in SYMPTOM_KEYS:
    icon_key = f"symptom_{tag}"
    check(f"symptom tag {tag!r} has icon {icon_key!r}", icon_key in icons_mod.ICONS)

for key in icons_mod.STATUS_KEYS:
    check(f"status {key!r} is in ICONS", key in icons_mod.ICONS)

for key in icons_mod.PRIORITY_KEYS:
    check(f"priority {key!r} is in ICONS", key in icons_mod.ICONS)

# ---------------------------------------------------------------------------
# Check 3: STRINGS has "it" and "en" for every key; t() falls back to
# English when the requested language is missing a translation, and to the
# bare key when the key doesn't exist in STRINGS at all.
# ---------------------------------------------------------------------------

for key, entry in i18n.STRINGS.items():
    check(f"STRINGS[{key!r}] has 'en'", bool(entry.get("en")), "missing English text")
    check(f"STRINGS[{key!r}] has 'it'", bool(entry.get("it")), "missing Italian text")

check("t() returns the bare key for an unknown key",
      i18n.t("__no_such_key__", "it") == "__no_such_key__")

check("DEFAULT_LANG is Italian", i18n.DEFAULT_LANG == "it")
check("SUPPORTED_LANGS includes it and en",
      "it" in i18n.SUPPORTED_LANGS and "en" in i18n.SUPPORTED_LANGS)

_PROBE_KEY = "__check_icons_i18n_probe__"
i18n.STRINGS[_PROBE_KEY] = {"en": "Probe text"}  # no "it" on purpose
try:
    check("t() falls back to English when the requested language's "
          "translation is missing",
          i18n.t(_PROBE_KEY, "it") == "Probe text")
    check("t() returns the English text when lang is English",
          i18n.t(_PROBE_KEY, "en") == "Probe text")
finally:
    del i18n.STRINGS[_PROBE_KEY]

check("lang_from_cookie defaults unknown/empty values to Italian",
      i18n.lang_from_cookie(None) == "it" and i18n.lang_from_cookie("xx") == "it")
check("lang_from_cookie accepts a supported language",
      i18n.lang_from_cookie("en") == "en")

_picker = str(i18n.pick_language_html("en"))
check("pick_language_html mentions Italiano and English",
      "Italiano" in _picker and "English" in _picker)
check("pick_language_html buttons are 44px tall",
      "height:44px" in _picker)

# ---------------------------------------------------------------------------
# Check 4: icon() output contains the aria-label and the use href.
# ---------------------------------------------------------------------------

_sample_keys = list(icons_mod.STEP_KEYS) + list(icons_mod.STATUS_KEYS) \
    + list(icons_mod.PRIORITY_KEYS) + ["tools", "parts", "camera"]

for key in _sample_keys:
    out = str(icons_mod.icon(key))
    entry = icons_mod.ICONS[key]
    check(f"icon({key!r}) contains aria-label", "aria-label=" in out)
    check(f"icon({key!r}) contains its label text", entry["label_en"] in out)
    check(f"icon({key!r}) contains the use href for its symbol",
          f'/static/icons.svg' in out and f'#i-{entry["symbol"]}"' in out)

_custom = str(icons_mod.icon("tools", label="Attrezzi"))
check("icon() honours an explicit label override", "Attrezzi" in _custom)

_unknown = str(icons_mod.icon("__not_a_real_key__"))
check("icon() degrades gracefully for an unknown key (no raise, has aria-label)",
      "aria-label=" in _unknown)


# ---------------------------------------------------------------------------

print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print(f"FAIL: {f}")
sys.exit(1 if failures else 0)
