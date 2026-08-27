# MultiEcuScan `FESLog_*.txt` Format Specification

**Derived from:** all 79 `FESLog_*.txt` files in `C:\Program Files (x86)\MultiEcuScan\`, MES 5.4.
**Status:** reverse-engineered from the corpus. Confidence is marked per item; §10 lists what is a guess.
**Captured:** 2026-08-27.

---

## 0. Filename convention

`FESLog_YYMMDDhhmm_<Vehicle description>.txt`

- `YYMMDDhhmm` is the **save** time, 2-digit year. `2606071008` = 2026-06-07 10:08.
- Vehicle description = preamble line 3 **with `/` removed** (path-illegal):
  `Fiat 500L 1.4 16V T-Jet/MultiAir` -> `Fiat 500L 1.4 16V T-JetMultiAir`. **Never join filename to content on this string.**
- **The filename timestamp is NOT the internal timestamp.** Internal date = session start; filename = save time. Divergence can be days: `FESLog_2511151050_*` has internal date `11/13/2025 11:52:42 PM`, nearly 2 days earlier.
- Filenames are not unique on timestamp: `FESLog_2510150209_...Stelvio 2.0...` and `FESLog_2510150209_...Stelvio 2.9 V6...` coexist.

---

## 1. Preamble

Standard form, 5 or 6 lines, then one blank line:

```
(Multiecuscan 5.4)
6/7/2026 10:03:48 AM
Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
--------------------------------------------------------------
```

| Line | Content |
|---|---|
| 1 | `(Multiecuscan 5.4)` literal. All 79 files are 5.4; other versions unverified. |
| 2 | Date/time |
| 3 | Vehicle description (free text) |
| 4 | ECU / module description (free text) |
| 4b | *optional* `SIMULATION MODE!!! THE DATA IS NOT REAL!!!` |
| 5/6 | Separator: exactly **62** hyphens |

### 1.1 Date/time line

Always US `M/D/YYYY h:mm:ss AM/PM`, unpadded month/day/hour, 2-digit min/sec.
Regex: `^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}:\d{2} (AM|PM)$` — 79/79 files, zero near-misses.

**Caveat (inference, not observed):** MES is a Delphi/.NET app using locale default formatting. A non-US Windows locale will very likely emit `dd/MM/yyyy HH:mm:ss`. Do not hard-fail on non-US dates.

### 1.2 The preamble is NOT always at the top

- **4 files** begin with a CAN/PROXI prologue; the standard preamble appears at line 19 or 23.
  (`FESLog_2510151628_*`, `FESLog_2510211520_*`, `FESLog_2510211525_*`, `FESLog_2511151635_*`)
- **1 file** has a stray line containing just `1` as line 1 (`FESLog_2510220004_Alfa Romeo 166 3.0 V6 24V.txt`).
- **Several files contain multiple concatenated sessions** — more than one `(Multiecuscan 5.4)` header. Iterate all header indices; do not take only the first.

> **Parser rule: locate the preamble by scanning for the `(Multiecuscan ` line, then take +2 (vehicle) and +3 (ECU). Never assume line 1.**

### 1.3 "ECU description" is really "MES function description"

Line 4 may be a pseudo-module, not an ECU:
`Service Interval Reset`, `Service Interval Reset (MCA 2017+)`,
`CAN Setup / PROXI Alignment Procedure (949)` / `(952)` / `(330)` / `(330 MY19)`.

Note the PROXI string contains `" / "` and will collide with a `<Group> / <ABBREV>` heading regex if that regex is applied to FES line 4.

---

## 2. Header key/value block

Follows separator + blank line, runs until the **first blank line**. Format `Key: value` — key, colon, one space, value. **Header values have no unit suffix.** An empty value renders as `Key: ` with a trailing space, never bare `Key:`.

```
ECU ISO code: 00 01 50 40 18
VIN code: ZASFAKPN5J7B88115
ECU serial number: TD4192427B17540
Spare part number: 50544870
Hardware number: MM10JAHW232
Hardware version: 00
Software number: P235QB39
Software version: 0000
Homologation number: FIBA00
FIAT drawing number: 52055320
Functioning time (EEPROM): 282292
Operating time: 282311
Startups counter: 13865
VIN lock status: Locked by odometer
PROXI configuration write counter: 1
```

### 2.1 Complete key inventory

| Key | Files (of 79) | Value format |
|---|---|---|
| `ECU ISO code` | 75 | 5 space-separated hex bytes |
| `Software version` | 70 | 4 alnum chars |
| `Homologation number` | 70 | free text; may be empty, may contain **raw binary**, may have a leading space |
| `Hardware version` | 70 | 2 chars |
| `VIN code` | 69 | 17-char VIN, or bare number (`5188214`) in sim logs, or empty |
| `FIAT drawing number` | 69 | digits, binary garbage, or empty |
| `Software number` | 68 | `P235QB39`, `635054AD`, or raw binary |
| `Hardware number` | 68 | `MM10JAHW232`, `CFC 8TDW.01` (contains space), or empty |
| `Operating time` | 67 | unsigned int, no unit in header |
| `Functioning time (EEPROM)` | 67 | unsigned int |
| `ECU serial number` | 58 | may have **leading spaces preserved** (`   UV`) |
| `VIN lock status` | 56 | `Locked by odometer`, `Unknown`, or empty |
| `Startups counter` | 56 | int |
| `PROXI configuration write counter` | 56 | int or empty |
| `Spare part number` | 32 | digits or empty |
| `VIN code (original)` | 18 | follows `VIN code` directly |
| `Odometer` | 16 | decimal, no unit in header |
| `ECU programming date` | **1** | `07/13/2003` — zero-padded `MM/DD/YYYY`. **Single observation.** |
| `WARNING` | **1** | `WARNING: Unknown ISO code. Module cannot be identified!` — pseudo-key, last line of header |

**Not header keys** despite appearance: `Number of programmings`, `Odometer at last programming`, `Universal code` — these occur only inside `READING PARAMETERS:` blocks. Respect block boundaries.

### 2.2 Key order is NOT stable

14 distinct orderings observed. Key *set* and *order* differ per ECU family; in one shape `FIAT drawing number` and `Hardware number` swap places. **Parse as an ordered list, never by fixed index.**

### 2.3 PROXI/CAN variant header

The 4 CAN-prologue files carry a node-status header instead:

```
Body Computer Node (BCM/NBC): EOL Ok
Engine Control Node (ECM/NCM): EOL Ok
Driver Door Node (NPG): Removed
Climate Control Node (HVAC/NCL): EOL Failed
Parking Brake Control Node (NPB): Added
```

Status values (exhaustive): `EOL Ok` (33), `Ok` (4), `EOL Failed` (4), `Removed` (4), `Added` (3).

Node names seen: `Body Computer Node (BCM/NBC)`, `Engine Control Node (ECM/NCM)`, `Dashboard Node (IPC/NQS)`, `Radio Frequency Hub Node (RFHM)`, `Driver Door Node (NPG)`, `Climate Control Node (HVAC/NCL)`, `Parking Brake Control Node (NPB)`, `Entertainment Telematic Node (ETM)`, `Electric Steering Node (EPS/NGE)`, `Brake System Node (ABS/BSM/NFR)`, `Steering Lock Node (NBS)`, `Parking Sensor Node (PAM/NSP)`, `Airbag Node (NAB/ORC)`, `Receiver Radio (NRR)` *(no "Node")*, `Convergence Telematic Node (CTM)`.

---

## 3. Section markers — complete inventory

| Literal | Count | Notes |
|---|---|---|
| `READING PARAMETERS:` | 815 | §6, only 4 files |
| `READING ERROR CODES:` | 23 | §4 |
| `EXECUTING ADJUSTMENT...` | 39 | §5, three ASCII dots |
| `EXECUTING ACTUATOR...` | 21 | §5 |
| `CLEARING STORED FAULT CODES...` | 9 | §3.3 |
| `  ERROR DETAILS:` | 6 | **2-space indented**, inside a DTC block |
| `Reading CAN configuration data ...` | 4 | mixed case, **space before dots** |
| `CAN CONFIGURATION DATA:` | 4 | prologue only |
| `SIMULATION MODE!!! THE DATA IS NOT REAL!!!` | 54 | §8 |
| 62 hyphens | 79 | separator |

Outcome literals: `COMPLETED` (40), `FAILED TO EXECUTE` (13), `No fault codes` (8).

> `PROXI ALIGNMENT PROCEDURE` and `NEXT SERVICE KM RESET` **look** like banners but are operation-name lines inside `EXECUTING ADJUSTMENT...` blocks. Identify operation names **positionally** (line after the banner), never by case or pattern.

### 3.3 `CLEARING STORED FAULT CODES...`

**Has no outcome line at all** — banner followed directly by a blank line. Success/failure of the clear is not recorded in FES logs. (SCAN logs *do* record `SUCCESS`/`FAILED` per module.) Confirmed across all 9 occurrences.

### 3.4 CAN configuration prologue

Banner, `CAN CONFIGURATION DATA:`, **3 hex-dump lines** (longest 434 chars — the max line length in the corpus; some encode ASCII), then a bare list of node names with no `: value`, then the standard preamble.

---

## 4. DTC blocks

### 4.1 Grammar

```
READING ERROR CODES:
<N>. <CODE>[ - <Description>]
··<param>: <value>[ <unit>]
··...
··                         <- terminator: line of EXACTLY two spaces
<N+1>. <CODE>...
```

- `N` is 1-based sequential, `.` then one space.
- **The ` - Description` suffix is optional.** Codes without: `1. B0110-15`, `2. P068A-68` (both simulation placeholders).
- **Descriptions are never multi-line.** No wrapping anywhere in the corpus.
- Freeze-frame lines indented **exactly 2 spaces**.
- Each freeze frame terminated by a line of **exactly two spaces** (not empty). After the last DTC: that 2-space line, then a genuine blank line.

### 4.2 `ERROR DETAILS:` sub-banner

Some modules insert `  ERROR DETAILS:` (2-space indent, same as params) before the freeze frame. 6 blocks / 2 files.

### 4.3 No-fault case

The **only** no-error phrasing in the corpus:

```
READING ERROR CODES:
No fault codes
```

8 occurrences. Other MES versions/ECUs may differ — unverified.

### 4.4 Code shape

`[PBCU]` + 4 hex chars + `-` + 2 hex chars. Regex `^[A-Z][0-9A-F]{4}-[0-9A-F]{2}$`.
**Note `P068A`, `P00F5`, `P105E`, `P1D33` contain hex letters — `\d{4}` fails.**

Codes seen in FES logs: `B0110-15`, `P0098-00`, `P00F5-00`, `P0440-00`, `P0455-00`, `P0456-00`, `P068A-68`, `P105E-00`, `P1189-00`, `P1D33-00`, `P1D34-00`.

### 4.5 Freeze-frame parameter inventory

| Parameter | Unit | Form |
|---|---|---|
| `Operating time` | `min` | int |
| `Startups counter` | *(none)* | int + trailing space |
| `Engine speed` | `rpm` | int |
| `Vehicle speed` | `km/h` | decimal |
| `Gas pedal position` | `%` | decimal 2dp |
| `Throttle angle` | `deg.` | decimal 2dp |
| `Spark advance` | `deg.` | decimal 3dp, may be negative |
| `Gear engaged` / `Gear requested` | *(none)* | `N` or int + trailing space |
| `Odometer` | `km` | decimal 1dp |
| `Engine temperature` / `Air temperature` / `Engine oil temperature` / `Gearbox oil temperature` | `°C` | int, may be negative |
| `Battery voltage` | `V` | decimal |
| `Intake pressure` / `Boost pressure` / `Atmospheric pressure` | `mbar` | int |
| `Hydraulic circuit pressure` | `bar` | decimal 1dp |
| `Air flow rate` | `Kg/h` | decimal 2dp (capital K) |
| `Fuel level` | `%` | decimal 2dp |
| `IBS Battery charge status` | `%` | int |
| `Electromagnetic interference` | `%` | decimal 1dp |
| `Clutch pedal` / `Clutch contact 2` | — | `Released` |
| `Brake pedal` / `Brake contact 2` | — | `Released` / `Pressed` |
| `Brake booster vacuum switch` | — | `Open` |
| `STOP&START temporary deactivation status` | — | `Speed<10km/h`, `Oil temperature` |
| `UniAir electrovalve actuation mode` | — | `Late opening`, `Hybrid` |
| `Universal code` | — | `Not received` |
| `Engine startup` | — | `Allowed` |

---

## 5. Actuator / adjustment blocks

`EXECUTING ACTUATOR...` and `EXECUTING ADJUSTMENT...` share one grammar:

```
EXECUTING (ACTUATOR|ADJUSTMENT)...
<operation name>          <- free text, exactly one line
[Old value: <v>]          <- adjustment-with-value only
[New value: <v>]
<outcome>
[Status: <code>]          <- COMPLETED only
```

`Status:` values observed: `00` and `UNKNOWN` only (10 samples — assume the space is larger).

### 5.1 Failure reasons (all 13 failures)

- `Incorrect conditions to run this test!` (7)
- `Request out of range error` (3)
- `Engine running` (2)
- `Transmission not in Park` (1)

### 5.2 Operation inventory

**Actuators:** `Evaporation control valve`, `Wastegate solenoid valve`, `Turbo vacuum valve`, `EGR solenoid valve`, `Electronic thermostat`, `Fan 1st speed`, `Acoustic signal (buzzer)`, `Tire pressure warning light`.

**Adjustments:** `Clutch self-calibration enable`, `Clutch replacement`, `Clutch drain`, `Position sensor calibration`, `System calibration`, `Actuator base adjustment`, `Self-adaptation parameters reset`, `Overboost counter reset`, `Replacement of turbocharger`, `Replacement of intelligent alternator (IAM)`, `Fuel supply circuit purge`, `Hydraulic unit bleed`, `Hydraulic unit bleed (Simulator)`, `Hydraulic circuit bleed (Rear Right)`, `Front left wheel identification`, `Rear right wheel identification`, `Front wheels pressure reference`, `Dynamic control selector`, `Last service date`, `Service interval`, `NEXT SERVICE KM RESET`, `PROXI ALIGNMENT PROCEDURE`, `Oil change`.

### 5.3 Blocks that break the grammar

- **No outcome at all** — operation name followed directly by the next banner. A parser must not assume an outcome follows.
- **Orphan outcome** — a bare `COMPLETED` with no preceding banner (`FESLog_2511151630_*` line 52).
- **Truncated** — 2 files end right after the operation name with no outcome and a single trailing CRLF. MES writes banner+name at start, outcome on return; if the app closes first the file is left short.

---

## 6. Live parameter logging (`READING PARAMETERS:`)

**Only 4 files contain it:** `FESLog_2510150207_*` (494 blocks), `FESLog_2510271230_*` (152), `FESLog_2606071008_*` (99), `FESLog_2510150219_*` (70). All Stelvio 2.0.

### 6.1 Layout

**NOT CSV. NOT a column table. No column headers. No per-sample timestamps.** It is a repeating key/value block, one block per sample:

```
READING PARAMETERS:
<Key>: <value>[ <unit>]
<Key>: <value>[ <unit>]

READING PARAMETERS:
...
```

### 6.2 Blocks are variable-length and grow

In `FESLog_2606071008_*`: 12 blocks of 1 param, 6 of 2, 4 of 3, ... rising to 135 params (12 blocks). The operator is adding parameters to the MES watch list live; each block snapshots whatever is selected at that moment.

**Consequences:**
- Cannot assume a fixed schema. Build the union of keys, or keep each block as its own ordered list.
- **No sample index and no timestamp.** Ordering is file order only; sampling rate and wall-clock time of any sample are unrecoverable.

### 6.3 Duplicate keys within one block — critical

```
Engine oil pressure: Low
Engine oil pressure: 2.20 bar
Engine oil level: 4.278 l
Engine oil level: 69.4 mm
```

**A `dict[str, str]` silently loses data.** Use an ordered list of `(key, value, unit)`, or key by `(name, unit)`.

### 6.4 Value / unit grammar

Line is `{Key}: {value} {unit}` — **always** a space before the unit slot, which may be empty. Five surface forms:

| Form | Meaning | Example |
|---|---|---|
| `Key: 14.0 V` | numeric + unit | `Battery voltage: 14.0 V` |
| `Key: Released ` | enum, empty unit -> trailing space | `Clutch pedal: Released ` |
| `Key: 0.97491 ` | unitless number -> trailing space | `Lambda sensor 1 integrator: 0.97491 ` |
| `Key:  V` | **empty value**, unit present -> double space | `Atmospheric pressure signal:  V` |
| `Key:  ` | empty value AND empty unit | `Failure indicator light:  ` |

Empty values are common (18 distinct keys). **Do not `strip()` blindly then assume the last token is the unit.** Split on the **first** `": "`, then split the remainder on the **last** space.

Decimal separator is always `.` in this corpus. Negatives use leading `-`. No thousands separators.

### 6.5 Unit inventory (live + freeze frames)

`deg.` (trailing period), `bar`, `ms`, `°C`, `%`, `l`, `mm`, `V`, `mV`, `mA`, `km`, `km/h`, `mbar`, `rpm`, `sec`, `Kg/h`, `l/h`, *(empty)*.

### 6.6 EVAP parameters of interest

```
Evaporation control valve opening: 0.0 %
Canister fill: 50.00 %
```

Both appear 24 times in `FESLog_2606071008_*` (24 blocks once added to the watch list).

The Stelvio 2.0 ECM exposes ~135 live parameters. Full set includes injection timing, fuel pressure (low/measured/calculated), per-cylinder knock and spark reduction, lambda control/temperature/current/integrators, exhaust and catalyst temperature, boost desired vs actual, throttle tracks 1/2, VVT learned tooth positions 1-6, UniAir solenoid angles, oil pressure/level/degradation, cruise control, A/C, and the two EVAP params above.

### 6.7 Interleaving

Param blocks can interleave with other operations. Param blocks are never indented.

---

## 7. Encoding and line endings

- **CRLF universally.** Zero LF-only lines.
- **No BOM in any of the 79 files.**
- **UTF-8.** 8 files contain the only multi-byte sequence: `C2 B0` = `°` in `°C`.
- **45 files contain raw control bytes `0x03`, `0x07`, `0x13`** — this is why `file(1)` reports them as `data` and why `grep` needs `-a`. They are unfiltered raw ECU response bytes echoed into string fields (`Software number:`, `Homologation number:`, `FIAT drawing number:`), always in simulation logs. `|?O??` is another placeholder in the same fields.
- **Strip `\r` before comparing strings**, or `Magna Q4 Transfer Case\r` and `Magna Q4 Transfer Case` become two modules.
- Recommendation: decode UTF-8 -> cp1252 -> latin-1 ladder, then strip stray control chars. Naive `encoding='ascii'` fails on the 8 degree-sign files.

---

## 8. Simulation logs

Exact marker, 3 exclamation marks each side:

```
SIMULATION MODE!!! THE DATA IS NOT REAL!!!
```

- **54 of 79 files.** Exactly one occurrence per file.
- Position: line 5 in 49 files (after ECU description, before separator). Line 6 in 1 file (the stray-`1` file). Lines 19/23 in the 4 CAN-prologue files.
- **Detect by substring search anywhere in the file, never by fixed line number.**

**Simulation tell-tales:** `ECU ISO code: 7C 86 4F FF FF`, `VIN code: 5188214` (7-digit fake), `ECU serial number: 281011421`, `Functioning time (EEPROM): 2089177087`, DTCs `B0110-15` / `P068A-68`, `Vehicle speed: 3240 km/h`.

**Any DTC extraction pipeline must discard or hard-flag these files.**

---

## 9. Anomalies

| Anomaly | Files | Detail |
|---|---|---|
| Stray leading `1` line | 1 | `FESLog_2510220004_*` |
| Preamble not at top | 4 | CAN prologue at line 19/23 |
| Truncated mid-operation | 2 | `FESLog_2511151119_*`, `FESLog_2511151135_*` |
| No operations at all | **30** | preamble + header only; smallest is 9 lines |
| Header = one key | 5 | `ECU ISO code` only |
| Orphan `COMPLETED` | 1 | `FESLog_2511151630_*` |
| Operation with no outcome | 2 | |
| Raw binary in string fields | 45 | `\x03\x07\x13` |
| Non-preamble date format | 1 | `ECU programming date: 07/13/2003` |
| Pseudo-key `WARNING:` in header | 1 | |
| Multiple sessions in one file | several | multiple `(Multiecuscan 5.4)` headers |

**No empty files.** Smallest 243 bytes, largest 175,477 bytes. All 79 parseable.

### 9.2 Trailing whitespace rules

| Context | Trailing space? |
|---|---|
| Preamble lines | No |
| Header `Key: value` | No (the space after `:` is the separator) |
| `READING PARAMETERS:` value lines | **Yes when the unit is empty** |
| Freeze-frame value lines | Same rule |
| DTC block terminator | The line is **exactly two spaces**, not empty |
| Banners, outcomes, operation names | No |

> **Never `rstrip()` before splitting value from unit — the trailing space is load-bearing (it is the empty unit slot).**

### 9.3 Blank lines

Preamble separator, header terminator, param-block separator: exactly 1 blank line.
After `COMPLETED`/`Status:`: 1 blank in 8 cases, 2 in 31 — inconsistent.
EOF: 77 files end `\r\n\r\n`; the 2 truncated files end with a single `\r\n`.

**Parse blank-line runs as "one or more", never a fixed count.**

---

## 10. Confidence summary

**Solid** (many observations, no counterexamples): preamble shape and date format (79/79); `Key: value` grammar with first-`": "` split; the `{value} {unit}` split with empty-unit trailing space; `READING PARAMETERS:` repeating-block structure with growing schema and duplicate keys; DTC block grammar incl. optional description, 2-space indent, 2-space terminator; `EXECUTING (ACTUATOR|ADJUSTMENT)...` -> name -> outcome and the `FAILED TO EXECUTE` + reason pair; CRLF/UTF-8/no-BOM/control bytes; the simulation marker and its position.

**Guesses / single observations — build tolerantly, do not hard-code:**
- `ECU programming date` zero-padded format — 1 sample
- `WARNING:` header pseudo-key — 1 sample
- `Old value:` / `New value:` in adjustments — 1 sample each; there may be other extra fields
- `Status:` values `00`/`UNKNOWN` — only 2 values in 10 samples
- `No fault codes` as the only no-error phrasing — 8 samples, one MES version
- The `(Multiecuscan 5.4)` version line format across other releases — unverified
- Locale dependence of the date format — reasoned, not observed
- CAN prologue always 3 hex lines — 4 samples
- Whether a DTC can have **zero** freeze-frame lines — not observed (min 1), but plausible
