# MES Language / Description Files (`Lang\English.txt`, `Lang\English.dat`)

**Status: CONFIRMED for the file format; CONFIRMED-NEGATIVE for the one thing
this document was written to find.** Unlike `CSV_LOG_FORMAT.md`, everything
here comes from read-only inspection of the actual files shipped with this
install (MultiEcuScan 5.4.0.0), cross-checked against the real log corpus and
against `docs/research/MES_INTEGRATION_SURFACE.md` (2026-08-27, independent
prior investigation that reached the same numbers). Confidence is marked per
item.

**Bottom line up front:** these files are a UI/localization string table, not
a DTC database. They hand you every *fragment of text* MES might ever print
next to a fault, but not which fragment belongs to which 5-character code.
That mapping lives in the encrypted `Files\data01.dat`…`data06.dat`, which
this investigation did not attempt to break (see §4).

---

## 1. File format

| Item | Value | Confidence |
|---|---|---|
| `Lang\English.txt` encoding | UTF-8 with BOM (`EF BB BF`) | `CONFIRMED` |
| `Lang\English.dat` encoding | UTF-16LE with BOM (`FF FE`) | `CONFIRMED` |
| Line grammar (both files) | `<id>[<suffix>]=<text>`, CRLF-terminated, one entry per line | `CONFIRMED` |
| `<id>` | decimal integer, used as a lookup key | `CONFIRMED` |
| `<suffix>` | optional single letter (observed: `T`) marking a tooltip/help variant of the base id, e.g. `1006=Connect` / `1006T=Connect to selected module...` | `CONFIRMED` |
| Header | first line `Title=English` (or the language name), then a `---...` separator line, both non-data | `CONFIRMED` |
| Other `Lang\*.dat` files | same id space and grammar, 14 other languages (Deutsch, French, Italian, Russian, Korean, ...) | `CONFIRMED` (spot-checked structure only; content not parsed) |

`English.dat` is exactly the same key-value grammar as `English.txt`, just a
bigger table and a different (double-byte) encoding — this is one format, not
two.

---

## 2. What's actually in the tables

Parsing every `id=text` line and grouping by contiguous id range gives three
clearly distinct namespaces. None of them is keyed by anything that looks
like a DTC.

### `English.txt` — 466 entries, ids 1001–8302

General program UI: menu items, dialog text, connection/PROXI strings,
settings labels. One sub-range matters for DTC work:

- **ids 3101–3204 (104 entries): failure-type-byte phrases.** This is the
  exact source `mes/dtc.py`'s own module docstring already cites as
  `"mes-table" — MultiEcuScan's shipped string table (Lang/English.txt, ids
  3101-3199)`. This investigation confirms that file, at that id range, still
  exists in the current install and still holds that phrase list (`General
  electrical failure`, `General signal failure`, `Short circuit to ground`,
  ... down to `Component or system operating conditions`). `dtc.py`'s
  `_FTB_TABLE` was built by anchoring this vendor-ordered phrase list to
  corpus-observed byte values (its own comment explains the method and the
  per-entry `confidence` — `confirmed`/`likely`/`offset`). This document does
  not re-derive or second-guess that anchoring; it only confirms the source
  table is genuine and present. **Confidence: `CONFIRMED`** (table exists,
  content matches what `dtc.py` already assumed).
- ids 3001–3099: error-status UI (`No fault codes`, `CLEARING STORED FAULT
  CODES`, generic explanatory sentences MES prints around a fault).
- ids 1001–1222, 2001–2004, 4001–8302: connection/adapter/PROXI, units,
  graph/CSV, actuator/adjustment UI, settings — general program chrome, not
  DTC-related.

### `English.dat` — 6,326 entries, ids 10001–23452 (nine contiguous runs with
### small gaps, collapsing into three namespaces)

| Namespace | ID range | Count | Content | Sorted by |
|---|---|---:|---|---|
| Parameters/components | 10001–12386 | 2,385 | Live-data parameter names, actuator/adjustment target names, component names (`A/C pressure`, `Urea/AdBlue tank reset`, `5th bow lifting solenoid valve`) — one flat shared vocabulary, not split by kind | alphabetical |
| Enumerated values | 18001–18494 | 492 | State/value labels used in dropdowns and readouts (`Active`, `Failed`, `High`, `In progress (1)`) | alphabetical |
| **DTC component fragments** | 20001–23452 | **3,449** | Short circuit/component-name phrases matching the vendor's own "component" half of a displayed DTC (`Evaporation system leak`, `Evaporation control valve`, `2-4 or 2C hydraulic pressure`) | alphabetical |

The 3,449 figure matches the earlier project-roadmap note ("`English.dat`
decode tables, 3,449 DTC descriptions") exactly — confirmed by direct count
(23452 − 20001 + 1 = 3452, minus 3 single-id gaps at 20922/21401/21443 = 3449).
**Confidence: `CONFIRMED`.**

Calling this range "DTC descriptions" is accurate but easy to over-read: it
is **3,449 reusable component-name fragments**, not 3,449 complete per-code
descriptions. See §3.

---

## 3. Critical finding: there is no DTC-code key anywhere in these files

Searched every line of `English.txt`, `English.dat`, and — for completeness —
all 14 other `Lang\*.dat` language files (same id space, different text), for
any token shaped like a DTC (`[PBCU][0-9A-F]{4}`), as either the key or inside
a value.

**Result: zero matches, in every file.** No line reads `P0455=...`, no value
contains `P0455` as a substring, in any language. **Confidence: `CONFIRMED`
(exhaustive: full-text search across all 16 shipped language files).**

Corroborating evidence for what these fragments actually are, from the real
log corpus on this install (`docs/reference/CORPUS_BASELINE.md` plus a direct
grep of the FES/SCAN `.txt` logs here):

| Code (as MES prints it) | Corpus text | Same fragment also present in `English.dat` at |
|---|---|---|
| `P0440-00` | `Evaporation control valve` | id `20759` |
| `P0455-00` | `Evaporation system leak` | id `23360` |
| `P0456-00` | `Evaporation system leak` | id `23360` — **the same string for two different codes** |

`P0455` and `P0456` share the identical component text in both the real logs
and `English.dat` — direct confirmation that these are shared building
blocks, not one fragment per code. This matches `CORPUS_BASELINE.md`'s
independent finding that "MES descriptions are not a unique key" (four
strings each shared by two different codes in the corpus).

**Working model (inferred, well-corroborated, not directly observed):** when
MES has a live DTC to display, it builds the text as
`[component fragment, from the 20001-23452 range] + " - " + [failure-type
fragment, from the 3101-3199 range]`, using a per-code-and-module lookup that
tells it *which* component fragment applies. That lookup is not in the
language files — it lives in the vehicle/ECU database. **Confidence:
`INFERRED`, corroborated by exact string matches above; not directly observed
in a data structure.**

### Module/ECU scoping

Not observed, and not testable from these files: since no code key exists at
all, there is nothing to check for per-module variation against. The prior
research note (`MES_INTEGRATION_SURFACE.md` §5) states the same conclusion
independently: *"strings are not keyed to ECUs — this is a flat global
vocabulary. Which string applies to which ECU is decided by the encrypted
DB."* **Confidence: `CONFIRMED`** (for "not scoped in the language files
themselves"); whether the *encrypted* mapping varies the same code's text by
module is **`UNKNOWN`** — the corpus has no example of one code showing
different component text on two different modules to check against.

---

## 4. Where the real mapping lives — encrypted, stopped here per instructions

`Files\data01.dat` … `Files\data06.dat` (six files, ~81 MB total) are the only
other data MES ships. They are almost certainly the per-vehicle/per-ECU
database that holds the code → component-fragment (and presumably →
failure-type-fragment) mapping.

| File | Size | Shannon entropy (bits/byte, 200 KB sample) | First 4 bytes |
|---|---:|---:|---|
| `data01.dat` | 37,563,930 | 7.999 | `65 5A D1 D8` |
| `data02.dat` | 6,758,884 | 7.085 | `00 22 38 3E` |
| `data03.dat` | 34,394,310 | 7.019 | `01 66 79 79` |
| `data04.dat` | 45,812 | 7.860 | `00 27 01 26` |
| `data05.dat` | 1,121,352 | 7.999 | `5E D7 4E D4` |
| `data06.dat` | 1,185,849 | 7.999 | `83 B0 F8 04` |

All six use the full 256-value byte alphabet at 7.0–8.0 bits/byte — visually
and statistically indistinguishable from random data, no recognizable
container magic bytes (not zip/gzip/sqlite/etc). This matches
`MES_INTEGRATION_SURFACE.md`'s independent, more thorough finding (same
entropy range measured differently, plus: `Multiecuscan.exe` itself is a
packed .NET assembly with `ObfuscationAttribute`, 96.6% opaque blob, an
AES-decrypting loader stub, and anti-debug `OpenProcess`/`ReadProcessMemory`
hooks) — that document's verdict is **"the ECU definition DB is not
recoverable without runtime key extraction"** and **"decrypting
data01-06.dat: CONFIRMED infeasible."**

**Per the task instructions, this investigation stopped at these six files.**
No decryption, key-recovery, or debugging of `Multiecuscan.exe` was attempted.
This is licensed vendor content and the encryption is not "simple decoding."

---

## 5. Practical consequence for `mes/dtc_text.py`

Because no code key exists in the shipped language files today, a lookup of
`describe("P0455")` against the real install returns `None` — there is
nothing to find. `dtc_text.py` still implements the generic `id=text` lookup
faithfully (including a `CODE@MODULE` scoped-key convention, untested against
real data because no scoping evidence exists, but exercised by synthetic
fixtures) so that:

1. the parsing/caching mechanism itself is correct and tested independent of
   what today's install happens to contain;
2. if a future MES release, a different install, or any other source ever
   supplies a code-keyed line (`P0455=...` or `P0455@PCM=...`) in one of
   these files, it is picked up automatically with no code change;
3. every other id=text lookup this format doc identified (FTB phrases, enum
   labels, component fragments) is available programmatically for other
   uses (e.g. cross-referencing corpus text against the vendor's own
   spelling), even though a direct per-code reverse lookup isn't possible.

## Confidence summary

| Claim | Confidence |
|---|---|
| `id[suffix]=text` grammar, both files/encodings | `CONFIRMED` |
| `English.txt` 3101–3204 is the same failure-type phrase table `dtc.py` already cites | `CONFIRMED` |
| `English.dat` 20001–23452 is a 3,449-entry DTC component-fragment library | `CONFIRMED` |
| No DTC-code key exists in any of the 16 shipped language files | `CONFIRMED` (exhaustive search) |
| Component fragments are combined with FTB fragments via an encrypted per-vehicle table | `INFERRED`, well-corroborated |
| Per-module scoping of the same code's text | `UNKNOWN` — untestable from available data |
| `Files\data01-06.dat` are encrypted proprietary content | `CONFIRMED` (entropy + prior research); **not attempted to break** |
