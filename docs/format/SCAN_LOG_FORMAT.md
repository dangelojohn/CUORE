# MultiEcuScan `SCAN_*.txt` Format Specification

**Derived from:** all `SCAN_*.txt` files in `C:\Program Files (x86)\MultiEcuScan\` (9 as of 2026-08-27; the corpus is live and MES writes new ones while running).
**Captured:** 2026-08-27.

---

## The single most important structural fact

A SCAN file is **not a document** — it is an append-only transcript of the "Scan vehicle" UI panel. Everything the panel printed lands in the file, including **the same modules dumped two or three times** (once for the live scan, once for the formatted `VEHICLE SCAN REPORT`, once per clear operation). Section order varies between files.

**A parser must treat the file as a sequence of phases and pick which phase it wants, not assume one module list.**

---

## 1. Preamble — and the vehicle/VIN question

There is **no version, no date, and no vehicle-name header.** Every file begins byte-identically:

```
Scan vehicle for available modules and check each module for errors...
<blank>
```

That is the entire preamble. This differs from `FESLog_*.txt`, which carries a 4-6 line header with version, timestamp, vehicle and ECU.

### Can you index SCAN logs by vehicle? Yes — via VIN, with caveats.

Four recovery paths, descending reliability:

**(a) `VIN code:` lines — the good one.** Present in 7 of 8 files examined (absent only from the connection-failure file). **In every file all VIN lines agree.** VIN density varies by ECU: on the Fiat 500L only BCM and ETM report it; on the Stelvio nearly every module does.

> **Rule:** VIN = first `^VIN code: (.+)$` capture; assert uniqueness and flag conflicts.

**(b) `VEHICLE MAKE/MODEL/YEAR` footer — unreliable free text.** Only in 4 of 8 files, user-typed:
```
VEHICLE MAKE: fiat            VEHICLE MODEL: 500l      VEHICLE YEAR: 2014
VEHICLE MAKE: stelvio         VEHICLE MODEL: 2.0l      VEHICLE YEAR:
VEHICLE MAKE: Alfa Stelvio    VEHICLE MODEL: 2.0L      VEHICLE YEAR:
VEHICLE MAKE: stelvio         VEHICLE MODEL: stelvio   VEHICLE YEAR:
VEHICLE MAKE: alfa 3          VEHICLE MODEL:           VEHICLE YEAR:
```
Note `MAKE: stelvio` (a model in the make field), `MODEL: 2.0l` (engine size in the model field), empty years emitted as `VEHICLE YEAR: ` with a trailing space. **Weak hint only, never a key.**

**(c) ECU description fingerprint.** Line 2 of each module block names the ECU (`Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)` vs `... IAW 8GMW CF5/EOBD Injection (1.4)`). Deterministic enough to distinguish vehicles.

**(d) Filename-timestamp correlation with FESLog — heuristic, last resort.** Works in this corpus, but on 2025-10-15 two *different* vehicles have FESLogs at the same minute. **Prefer VIN.**

---

## 2. Module block structure

All lines flush-left — **zero indentation anywhere in any file**.

```
<HEADING>
<ECU description>
ISO Code: <5 hex bytes, space-separated>
[VIN code: <17 chars>]              <- optional
Hardware number: <text> - Ver: <hex>
Software number: <text> - Ver: <hex>
[Errors found:]                     <- optional
[<DTC line>]...                     <- 1..n, only if "Errors found:" present
<blank>
```

### Heading grammar

```
<Category> " / " <Abbrev>[ "(" <LongName> ")"]
```

`<Abbrev>` **may itself contain `/`** (alias sets): `ABS/BSM`, `NAB/ORC`, `TCM/NCA/NCR`, `ESM/GSM/NSC`.
**So you cannot split the heading on `/`** — split on the *first* `" / "` (space-slash-space) only. And even that is insufficient alone: see §5.

**All 15 distinct headings observed:**

| Heading (verbatim) |
|---|
| `ABS / ABS/BSM (Brake System Module)` |
| `Airbag / NAB/ORC (Airbag/Occupant Restraint Module)` |
| `Body / BCM (Body Computer Module)` |
| `Body / BCM (Body Control Module)` |
| `Body / RFHUB (Radio Frequency Hub Module)` |
| `Climate control / HVAC (Heating Ventilation Air Conditioning)` |
| `Dashboard / ETM (Entertainment Telematic Module)` |
| `Dashboard / IPC (Instrument Panel Cluster)` |
| `Electric Steering / EPS (Electric Steering Module)` |
| `Engine / ECM` |
| `Gearbox / DTCM (Drive Train Control Module)` |
| `Gearbox / ESM/GSM/NSC (Gearbox Selector Module)` |
| `Gearbox / TCM/NCA/NCR (Automatic Transmission)` |
| `Other / DASM (Driver Assistant System Module)` |
| `Other / TPMS (Tire Pressure Module)` |

**Two load-bearing gotchas:**

1. **`Engine / ECM` is the only heading with no parenthetical long name.** The `(...)` part must be optional.
2. **`Body / BCM` appears under two long names** — `(Body Control Module)` in one file, `(Body Computer Module)` in six others, same physical ECU (identical `ISO Code: BF 83 91 0E B6`). An MES database string change. **Key modules on `Category + Abbrev`, or better on ISO Code — never on the full heading string.**

Categories seen: `ABS`, `Airbag`, `Body`, `Climate control`, `Dashboard`, `Electric Steering`, `Engine`, `Gearbox`, `Other`.

### ECU description line

Free text, no grammar. Includes `UNKNOWN/UNSUPPORTED` — see §3. Note `Uconnect Radio/Nav 6.5"` contains a **double-quote**.

### ISO Code / Hardware / Software

```
ISO Code: BF 83 91 0E B6
Hardware number: BC330I.0100 - Ver: 04
Software number: 04440005138 - Ver: 0509
```

`ISO Code` is always exactly 5 uppercase hex byte pairs. **It is the only field repeated in every context (scan, report, clear) and is therefore the best module join key.**

HW/SW values are free text that can contain spaces and double spaces: `Software number: F330 MD  bd - Ver: 1062`. **Split on the LAST ` - Ver: `, not the first.**

---

## 3. Per-module status — full enumeration

Only **two** per-module scan states exist:

**State A — clean.** *No status line at all.* The block ends after `Software number:`. There is no "no faults found" / "OK" / "no errors" text anywhere in any SCAN file. **Absence of `Errors found:` IS the clean signal.**

**State B — faults present.** Exactly one phrasing, always immediately after `Software number:` (or after `FAILED`):

```
Errors found:
```

### There is NO per-module not-responding / not-present / not-supported line

- **A module that does not respond is simply omitted from the file.** You cannot distinguish "not fitted" from "not responding" from "not scanned" from a SCAN log.
- **`UNKNOWN/UNSUPPORTED` is NOT a status line.** It occupies the *ECU description* slot and means MES talked to the ECU fine but has no name for it in its database. The block is otherwise complete and normal. **Treat as a null ECU-name sentinel, keep the ISO/HW/SW as identity, surface as "responded but unidentified by MES" — never as a module named UNKNOWN.**

**Session-level failure phrasing:**
```
Connection failed!
```

**Clear-phase-only status lines** (never in the scan phase), always immediately after an `ISO Code:` line:
```
SUCCESS
FAILED
```
`FAILED` observed only on `Gearbox / TCM/NCA/NCR` — the self-calibration codes that cannot be cleared.

---

## 4. DTC lines

```
<CODE>-<FTB> - <Component/circuit text>[ - <Failure-type text>]
```

Real examples:
```
B1011-18 - Number plate lights - Current too low/below threshold
B11A1-11 - Left daylight - Short circuit to ground
U0019-88 - B-CAN line - Bus OFF
U0100-87 - No communication with engine control unit (ECU) - Missing message
C141C-86 - Private CAN between HALF and DASM - Signal/message invalid
B1176-97 - Rear left window riser - Component or system operation obstructed or blocked
P1D34-00 - End of line / service self-calibration
```

- Code: `[PBCU]` + 4 uppercase hex chars.
- Suffix: always exactly 2 uppercase hex chars, always present, no spaces around the hyphen. This is the **ISO 14229 failure-type byte, not a status byte.**
- FTBs observed: `00 11 15 18 2F 64 86 87 88 97`.

### The description-splitting trap

The description is **one or two** ` - `-separated segments, and both segments can contain `/` and parentheses. **Do not naively split on ` - `.**

Observed rule (inference, n=6): FTB `00` yields **one** segment; every other FTB yields **two** (component, then a failure phrase matching the FTB). The FTB↔phrase mapping is perfectly self-consistent across the corpus, which supports the theory.

> **Safe implementation:** match `^([PBCU][0-9A-F]{4})-([0-9A-F]{2})(?: - (.*))?$`, keep the remainder as one string, and split on the **LAST** ` - ` only if you need the component/failure split. Tolerate its absence.

Note `P1D34-00 - End of line / service self-calibration` contains ` / ` — the same token used by module headings. This is exactly why heading detection must not key on ` / ` alone.

### Bare DTC lines — a second variant

Inside a `FAILED` clear block, codes are printed **code-only** with no description:
```
Errors found:
P1D34-00
P1D33-00
```
**The ` - description` tail must be optional.**

### Freeze frames: CONFIRMED ABSENT

`grep -il freeze` over all 86 `.txt` files returns **zero hits**. SCAN logs contain no freeze-frame, snapshot, or environmental data of any kind — no RPM, coolant, or mileage-at-fault. Code + suffix + description, nothing more.

### DTC status: NOT MARKED

No status qualifier on any DTC line. No active/stored/pending/intermittent, no occurrence counters, no `[A]`/`[S]` markers. The only status semantics available is the section header `CLEARING STORED FAULT CODES...`, which implies the listed codes were *stored*. **You cannot recover DTC status from a SCAN log** — it must come from a FESLog or a live read.

---

## 5. Block delimiting — how to split reliably

Blocks are separated by a **single empty line** (`\r\n\r\n`). No dashes, no rules, no indentation.

**Blank-line splitting is fragile:**

1. **Runs of >1 blank line occur** — up to **5 consecutive**. Naive `split("\n\n")` yields phantom empty records.
2. **Non-module records are also blank-line-delimited.** Clear-result blocks look exactly like module blocks for their first three lines, so a blank-line splitter hands you clear-results as scan-results, double- or triple-counting modules.
3. **A DTC line can contain ` / `**, so "line contains slash ⇒ heading" is wrong.

### The robust rule — holds for 100% of blocks in all files

> A module block starts at line *N* iff line *N+2* matches `^ISO Code: ([0-9A-F]{2} ){4}[0-9A-F]{2}$`.
> Then line *N* is the heading, line *N+1* is the ECU description, and the block runs until the next empty line.

Validated mechanically against all 122 `ISO Code:` lines in the corpus: the line two above is always the heading and the line three above is always empty or file-start. **Zero irregularities.** Anchoring on `ISO Code:` and walking backwards is far safer than forward-scanning for headings.

Distinguish a *scan* block from a *clear-result* block by what follows the `ISO Code:` line: `SUCCESS`/`FAILED` ⇒ clear-result; `VIN code:`/`Hardware number:` ⇒ scan result.

---

## 6. Phases, banners, footer

**No summary line, no elapsed time, no module count, no fault total.** Compute counts yourself.

| Literal | Meaning |
|---|---|
| `Scan vehicle for available modules and check each module for errors...` | file start, always line 1 |
| `Connection failed!` | interface/vehicle comms failure |
| `Errors found:` | DTC list follows |
| `************************************************************` | banner rule, **exactly 60 asterisks** |
| `VEHICLE SCAN REPORT` | between two banner rules |
| `Scanning ...` | first line after report banner (**space before dots**) |
| `COMPLETED` | end of a phase |
| `VEHICLE MAKE:` / `MODEL:` / `YEAR:` | user-entered metadata footer |
| `SENDING DIAGNOSTIC REPORT ...` | upload step (**space before dots**) |
| `CLEARING STORED FAULT CODES...` | clear phase, no space, 3 dots |
| `CLEARING STORED FAULT CODES` | clear phase, **no ellipsis at all** |
| `SUCCESS` / `FAILED` | per-module clear result |

**Punctuation traps:** both `CLEARING STORED FAULT CODES...` and the bare form are real and appear **in the same file**. Spacing before ellipses is inconsistent (`Scanning ...` vs `CODES...`). Match with a tolerant `\s*\.{0,3}$`.

### Phase orderings — four distinct patterns in 8 files

```
scan -> REPORT -> COMPLETED+META -> SENDING -> CLEAR
scan -> CLEAR                                        (no report at all)
scan -> CLEAR -> REPORT -> COMPLETED -> CLEAR(bare) -> COMPLETED+META -> SENDING
preamble -> 5x Connection failed!                    (nothing else)
```

**Do not hardcode a sequence.** Half the files have no `VEHICLE SCAN REPORT` section.

---

## 7. Encoding

`ASCII text, with CRLF line terminators` — uniform across all files. No BOM. No UTF-8 multi-byte, no high bytes.

**Caveat:** ASCII-only is a property of *this* corpus (English UI). MES ships localized DTC databases; a German/Italian/French install would plausibly emit accented characters, and MES 5.x is a Delphi app that would most likely write **Windows-1252**. Decode with a cp1252 fallback rather than strict ASCII/UTF-8.

Files are small (174 B - 6.5 kB). Read whole.

---

## 8. Simulation — the dangerous gap

**No SCAN file contains `SIMULATION MODE`.** By contrast, **54 of 78 FESLog files do**, with the marker at line 5:

```
SIMULATION MODE!!! THE DATA IS NOT REAL!!!
```

**This is a real risk.** Because a SCAN log has no simulation marker *and* no version header, a simulated SCAN — if MES can produce one — would be **indistinguishable from a real one**, and would carry a plausible-looking VIN.

> **Treat the absence of the marker in a SCAN log as "provenance unknown", never as "confirmed real".**

---

## 9. Anomalies

**a) The corpus is live.** A new SCAN file appeared mid-analysis. Any indexer must tolerate files appearing and potentially being **read mid-write** — a partially flushed file looks exactly like a truncated scan. Use a settle delay or verify the file ends with a complete block.

**b) Aborted scan** — one 174-byte file is nothing but the preamble plus 5x `Connection failed!`. Zero modules, zero VIN, zero metadata. **Unindexable — no way to attribute it to a vehicle.** Detect via `module_count == 0`. Timing (11:12 failure, 11:31 success) suggests an "adapter wasn't connected yet" retry pattern.

**c) No truncated files** observed; all non-failure files end with a complete block plus a trailing blank line.

**d) Massive duplicate module entries — normal.** One file has **21 `ISO Code:` lines for 8 physical modules** (8 live scan + 8 report + 5 clear). **Counting `ISO Code:` occurrences as "modules scanned" is wrong by 2-3x.** Deduplicate by ISO Code within the chosen phase.

**e) The report phase is a fresh re-scan, not a copy.** In one file the clear phase runs *before* the report, so the report re-reads post-clear state. Consequence: for "faults as found" use the **first scan phase**; for "faults after clearing" use the **report phase**. They genuinely differ and can disagree.

**f) Empty `VEHICLE YEAR:`** emitted in 3 of 4 metadata footers — key present, value empty. A parser requiring a non-empty value will drop the line or throw.

---

## 10. Bottom line

**Solid facts** (uniform across all files): the constant line-1 preamble; absence of version/date/vehicle header; the `heading / description / ISO Code:` three-line opener with `ISO Code:` always at offset +2; CRLF, ASCII, no BOM; `Errors found:` as the sole fault marker; absence-of-marker as the sole clean marker; no freeze-frame; no DTC status; no summary footer; blank-line separation with runs up to 5.

**Inferences, flagged:** the FTB-`00`⇒single-description-segment rule (n=6); the cp1252 recommendation for localized installs (defensive, no direct evidence); the claim that simulation mode does not produce SCAN logs (absence of evidence only); the meaning of the 5x `Connection failed!` retry count (n=1).
