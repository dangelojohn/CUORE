"""Checks for mes/dtc_text.py: the MES language-file lazy loader.

Synthetic fixtures only -- these are small files this test writes itself,
never MES's own shipped content (see docs/format/MES_LANGUAGE_FILES.md for
what the real English.dat/English.txt actually contain: a UTF-16LE/UTF-8
id=text string table with NO DTC-code key at all). The synthetic fixtures
below deliberately DO include a couple of code-keyed lines, so the lookup
mechanism itself gets exercised even though nothing in the real install
looks like that today.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mes import dtc_text as dt
from mes import paths

ok_count = 0
fail_count = 0


def check(label, cond, detail=""):
    global ok_count, fail_count
    if cond:
        ok_count += 1
        print(f"  OK   {label}")
    else:
        fail_count += 1
        print(f"  FAIL {label}  {detail}")


# --- build a small synthetic MES install ------------------------------------

tmp = Path(tempfile.mkdtemp(prefix="mes_lang_fixture_"))
lang_dir = tmp / "Lang"
lang_dir.mkdir(parents=True)

# English.txt: UTF-8 with BOM, matches the real file's header + id=text shape.
english_txt = (
    "Title=English\r\n"
    "------------------------------\r\n"
    "1001=Select\r\n"
    "1006=Connect\r\n"
    "1006T=Connect to selected module.\r\n"
    "3101=General electrical failure\r\n"
    "3102=General signal failure\r\n"
)
(lang_dir / "English.txt").write_bytes(english_txt.encode("utf-8-sig"))

# English.dat: UTF-16LE with BOM, same grammar, bigger id space -- plus two
# DTC-shaped keys (P0999, one module-scoped) that no real MES install has,
# purely to prove the lookup mechanics work when a key like this DOES exist.
english_dat = (
    "Title=English\r\n"
    "------------------------------\r\n"
    "20001='AUTO' lever switch stuck\r\n"
    "23360=Evaporation system leak\r\n"
    "P0999=Synthetic test code - injected for fixture coverage\r\n"
    "P0999@PCM=Synthetic test code, PCM-scoped variant\r\n"
)
(lang_dir / "English.dat").write_bytes(english_dat.encode("utf-16-le"))

os.environ[dt.INSTALL_DIR_ENV] = str(tmp)
cache = dt.reload()

print(f"synthetic fixture: {tmp}")
print(f"files loaded: {cache['files_loaded']}")
print(f"entries loaded: {dt.loaded_count()}")

check("both fixture files loaded",
      set(cache["files_loaded"]) == {"English.txt", "English.dat"},
      cache["files_loaded"])
check("entry count matches fixture (9 unique keys)", dt.loaded_count() == 9,
      dt.loaded_count())

# --- grammar edge cases ------------------------------------------------------

entries = dt._load()["entries"]
check("BOM stripped from first key", "1001" in entries, list(entries)[:3])
check("header lines excluded", "Title" not in entries and "---" not in "".join(entries))
check("tooltip suffix kept as its own key", entries.get("1006T", "").startswith("Connect to"))
check("base id and suffix id are distinct", entries.get("1006") == "Connect")

# --- describe(): the mechanism, exercised against synthetic code keys -------

hit = dt.describe("P0999")
check("bare synthetic code resolves", hit is not None and hit["code"] == "P0999", hit)
check("source is labelled MES English.dat", hit and hit["source"] == "MES English.dat", hit)
check("unscoped hit carries no scoped_module", hit and hit["scoped_module"] is None, hit)

hit_ftb = dt.describe("P0999-00")
check("failure-type-byte suffix is stripped before lookup",
      hit_ftb is not None and hit_ftb["text"] == hit["text"], hit_ftb)

hit_scoped = dt.describe("P0999", module="PCM")
check("module-scoped key preferred when present",
      hit_scoped is not None and "PCM-scoped" in hit_scoped["text"], hit_scoped)
check("scoped_module echoed on a scoped hit",
      hit_scoped and hit_scoped["scoped_module"] == "PCM", hit_scoped)

hit_other_module = dt.describe("P0999", module="BCM")
check("falls back to the unscoped key when the module doesn't match",
      hit_other_module is not None and hit_other_module["scoped_module"] is None,
      hit_other_module)

miss = dt.describe("P0455")
check("a code with no key in the fixture returns None (never fabricated)",
      miss is None, miss)

check("empty code returns None", dt.describe("") is None)
check("whitespace-only code returns None", dt.describe("   ") is None)

# case-insensitivity
hit_lower = dt.describe("p0999")
check("lookup is case-insensitive", hit_lower is not None and hit_lower["code"] == "P0999")

print(f"\nfixture checks: {ok_count} ok, {fail_count} failed")

# --- optional: real install, if present -------------------------------------

del os.environ[dt.INSTALL_DIR_ENV]
real_lang_dir = Path(paths.DEFAULT_ROOT) / "Lang"
if real_lang_dir.is_dir():
    print(f"\n--- real install found at {paths.DEFAULT_ROOT} ---")
    real_cache = dt.reload()
    print(f"files loaded: {real_cache['files_loaded']}")
    print(f"entries loaded: {dt.loaded_count()}")
    for code in ("P0455", "P0456", "P0440"):
        # No assertion on the result's shape or presence -- documented in
        # docs/format/MES_LANGUAGE_FILES.md that the real English.dat/
        # English.txt carry no DTC-code key, so None here is the CORRECT
        # answer, not a failure. The only thing under test is "does not
        # crash".
        try:
            result = dt.describe(code)
            print(f"  describe({code!r}) -> {result}")
        except Exception as exc:  # pragma: no cover - the one thing we guard
            fail_count += 1
            print(f"  FAIL describe({code!r}) raised {exc!r}")
else:
    print(f"\n--- no real MES install found at {paths.DEFAULT_ROOT}, "
          "skipping real-install check ---")

print(f"\nTOTAL: {ok_count} ok, {fail_count} failed")
if fail_count:
    sys.exit(1)
