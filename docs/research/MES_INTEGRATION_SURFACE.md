# MultiEcuScan 5.4 — Integration Surface and Stelvio Coverage

**Captured:** 2026-08-27, from read-only inspection of the local install plus vendor documentation.

---

## Bottom line

**MES has no API, SDK, COM interface, plugin system, scripting host, or usable command line. CONFIRMED by exhaustion** — no COM/TypeLib registration in the registry, no developer section on the vendor site (12 probed URLs all 404), and zero mentions of API/SDK/script/plugin/macro/automation in the official manual.

But the investigation surfaced something better than an API: **the vendor publishes a complete, machine-parseable per-module capability *and licensing* matrix** — 532 vehicles, ~7,310 module entries — telling you what MES can do on any ECU, offline, before anyone touches a car. **That is the integration.**

---

## 1. THE ACTIONABLE PART: Stelvio 2.0T module coverage

All 29 modules MES lists for this vehicle are `ELM` class (CAN). What differs is **which OBD pins they live on** — see §3.

### Reachable with a plain ELM327 on pins 6/14 — no adapter
`ECM` · `ZF 8HP` transmission · `Q4 transfer case` · gear-shift module · `DASM` · `IPC` · `BCM 949` · **PROXI Alignment (949)** · `RFHUB` · Service Interval Reset

*These are exactly the 8 modules that appear in the shop's scans, plus the procedures.*

### Require the **A6 / grey** cable (CAN moved to pins 12/13) — chassis & safety
`ABS MK C1` · `HALF` forward camera · torque vectoring · **airbag** · steering lock · **electric steering** · adaptive headlights · parking

### Require the **A5 / blue** cable (CAN moved to pins 3/11) — comfort & infotainment
radio/nav · amplifier · `ESEM` · comfort seats · climate · blind-spot · power liftgate

> **This is the single highest-value gap.** Buying the A5 and A6 cables roughly triples addressable module count on this car — from 10 to 29 — including airbag, ABS and electric steering. No software change can substitute.

---

## 2. ⚠️ SAFETY WARNING — applies to this vehicle

Vendor, verbatim:

> **"DO NOT USE MODIFIED INTERFACES WITH SHORT CIRCUIT BETWEEN PINS 1 AND 9 ON … GIULIA, STELVIO, …"**

On these cars pins 1/9 are a CAN pair, and shorting them **drops the bus**. Many cheap "universal" FCA cables do exactly this because it is required on older Fiats. Check any adapter cable before plugging it into the Stelvio.

---

## 3. The adapter cable routing table (from vendor schematics)

Every cable passes pin 16 straight through and bridges grounds 4+5.

| Cable | Routing | Purpose |
|---|---|---|
| **A1** green | 7 → 7, 9, 12, 1 | **K-line** re-router (ABS/airbag/EPS) |
| **A2** red | 7 → 3 | **K-line** to pin 3 (old airbags) |
| **A3** yellow | 6→1, 14→9, 7→12 | **CAN to pins 1/9** + K-line to 12 (Grande Punto/500/MiTo/Doblo B-CAN) |
| **A4** purple | 7 → 7, 8, 11, 13 | **K-line** re-router (Bravo '07, Delta '08) |
| **A5** blue | 6→3, 14→11 | **CAN to pins 3/11** — Giulia/Stelvio comfort & infotainment |
| **A6** grey | 6→12, 14→13 | **CAN to pins 12/13** — Giulia/Stelvio chassis & safety |

A1/A2/A4 relocate the **K-line** (pin 7); A3/A5/A6 relocate **CAN-H/CAN-L** (pins 6/14). Interfaces with a hardware pin switch use the `P1/P3/P9/P12/P13` tokens instead.

---

## 4. Coverage statistics across the whole MES catalogue

~7,310 module rows across 532 vehicles.

| Interface requirement | Rows | Share |
|---|---:|---:|
| `ELM` only (CAN-capable mandatory) | 4,919 | 67% |
| `KL` + `ELM` (either) | 1,480 | 20% |
| `KL` only | 746 | 10% |
| Neither (PROXI/CAN Setup procedures) | 170 | 2% |

Capabilities: INFO 7,165 · DTC 6,415 · PRM 5,844 · **ADJ 4,535** · **ACT 4,400** · DTC EX 3,276.
Adapter demand: none 3,951 · A3 1,371 · A1 841 · 3-Pin 412 · **A5 277** · A2 223 · **A6 180** · A4 60.
Makes: Fiat 317, Alfa 108, Lancia 68, Jeep 11, Chrysler 8, Dodge 7, Ducati 7, Moto Guzzi 3, Suzuki 2.

**Practical read:** a plain KKL cable reaches ~30% of listings; a good ELM327 v1.3+/OBDLink reaches ~87% but needs one of six cables for ~46% of those; only **CANtieCAR or vLinker MS** reaches everything without swapping cables.

---

## 5. Local install facts

**Version** 5.4.0.0, FESSoft Ltd., released 15/08/2025 — latest for 12+ months, the longest gap in the product's 92-release history. Manifest declares `requireAdministrator`, which is why it writes logs into Program Files and settings into HKLM.

### The executable is a packed .NET assembly — hard dead end
PE32 .NET with `ObfuscationAttribute`. CLR metadata is **3.4% of the 4.3 MB file**; 96.6% is an opaque blob. Only **21 string literals** survive — the loader stub's `AesCryptoServiceProvider`, `CryptoConfig`, and licence templates. The stub AES-decrypts the real assembly at runtime and imports `OpenProcess`/`ReadProcessMemory`/`WriteProcessMemory` (anti-debug).

**`Files\data01-06.dat` (~81 MB, entropy 7.02-8.00 bits/byte) — the ECU definition DB is not recoverable** without runtime key extraction.

### Settings live in HKLM
`HKLM\SOFTWARE\Multiecuscan`, 68 values. `HKCU` holds only `installed=1`.

| Value | Current | Note |
|---|---|---|
| `Interface 0/1 Port` | **`COM3`** | **collides with the obd2 MCP server** |
| `Interface Type Ex` / `Port Speed` | `7` / `115200` | |
| `Export Folder` / `LOG Folder` | `.` / `.` | why output lands in Program Files |
| `CSV Separator` | `Tab` | |
| `Lic Number` | 18 chars | registered licence present |

**ACL caution:** `BUILTIN\Users` has only `ReadKey` there. Changing folders needs elevation or the MES Settings dialog.

### `Lang\English.txt` — UI string table (18 KB, UTF-8, `ID=text`)
1001-1222 connection/adapter/PROXI · 1101-1121 the 11 system categories · 3001-3099 error statuses · **3101-3204 the 104 DTC failure-type descriptions** · 4001-4101 units · 5001-5041 graph/CSV · 6001-6225 actuators (incl. error codes 6501-6509) · 7001-7103 adjustments · 8101-8302 settings.

### `Lang\English.dat` — data string table (437 KB, **UTF-16LE**, 6,326 entries)
Decode with `open(p,'rb').read().decode('utf-16-le')`.

| Namespace | IDs | Count | Content |
|---|---|---|---|
| **DATA** | 10001-12386 | 2,385 | parameters, components, actuator targets, adjustment routines — *one shared namespace* |
| **ENUM** | 18001-18494 | 492 | enumerated value texts |
| **DTC** | 20001-23452 | 3,449 | DTC descriptions |

**Structural caveat:** MES does **not** separate actuators from adjustments from parameters by ID range, and strings are **not keyed to ECUs** — this is a flat global vocabulary. Which string applies to which ECU is decided by the encrypted DB.

Recovered content includes **66 CAN node names**, 103 service/adjustment routines, all 11 `Replacement of *` routines, all 20 bleed/purge/drain routines, and 81 distinct `Lost communication with <module>` DTC entries.

### CSV export format (the real streaming path — never used here)
**UTF-16LE with BOM**, separator per Settings, text quoted:
```
"Time"  "Engine speed"  "Fuel pressure"  "TAG"
"sec"   "rpm"           "bar"            " "
0.00    1215.0000       366.3000         ""
```
Row 1 = names, **row 2 = units**, first column always `Time` in seconds, last column `TAG`. Enabling `Monitor DTCs` also writes DTCs into the CSV.

### Export formats — four; **no XML**
`.txt` session log · `.txt` SCAN report · **CSV** · **PDF** (PdfSharp 1.32.2608).

### Logs are written at completion, not streamed
MES ran from 10:57 and emitted discrete closed files at 11:12 / 11:19 / 11:20 / 11:31 / 11:36 / 11:41. **File-watching gives per-operation latency, not live telemetry.**

Also: **filename timestamp = write/close time, not the header time** (`FESLog_2608271119` carries header `10:57:50 AM`). Parsers must not conflate them — ours does not.

---

## 6. Licensing — two nuances that matter

Tiers: **REGISTERED EUR 50** (single computer, 1 yr updates) · **MULTIPLEXED EUR 342** (CANtieCAR, unlimited computers, locked to the interface) · **Multiecuscan MS EUR 234** (vLinker MS + REGISTERED) · extension EUR 50/yr.

**Nuance 1 — gating is per-module, not per-function.** 5,814 of ~7,310 module rows (**79%**) are FREE-restricted. PROXI Alignment and CAN Monitor are among them.

**Nuance 2 — MULTIPLEXED is not a superset.** It *drops* support for KL, ELM327, OBDKey, OBDLink and Vgate entirely. It is a hardware-locked SKU, not an upgrade.

FREE limits: 20-minute session cap, max 4 parameters, no reset/programming, no CAN-module diagnostics, no auto-saved session logs. **Manual CSV export does work in FREE.**

### Simulation mode is the capability enumerator
> *"lets you explore the functionality of the program without actual connection to a car. Using this mode you can see which parameters, tests and calibrations are available for any control module."*

CTRL+F10, available in **every tier including FREE**. Writes a normal FESLog stamped `SIMULATION MODE!!!`. **This is the only route to the authoritative per-ECU capability list locked inside the encrypted DB.** It explains why 54 of 79 FES logs here are simulated — that is someone enumerating capability, not practising.

---

## 7. Recommendations, ranked

1. **Ingest the vendor's capability matrix — SAFE / READ-ONLY. Highest value, trivially feasible.** 532 vehicles x ~7,310 modules with INFO/DTC/DTC EX/PRM/ACT/ADJ, interface class, required adapter and pin. **Parse the HTML, not the plain text**: `<font style="color: Red;">` wraps exactly 5,814 module names, giving per-module FREE-vs-REGISTERED gating for free. Build to SQLite/JSON, expose as `mes_capabilities(vehicle, module)`.
2. **Ship `English.dat` + `English.txt` as decode tables — SAFE. High value, trivial.** Enrich DTCs via the FTB table, resolve enums, normalise the 66 node names. Also makes parsing **localisation-independent** — 14 other language files map to the same IDs.
3. **Use simulation mode as a per-ECU capability enumerator — SAFE, manual.** Cannot be automated; treat as a data-collection ritual whose output we ingest.
4. **Turn on CSV recording — REQUIRES CONFIG CHANGE (elevation).** The real streaming path, never used here. Set `Export Folder` via the MES Settings dialog.
5. **Resolve the COM3 contention.** MES is configured for COM3; the obd2 MCP server uses COM3; MES holds the port exclusively. Gate behind a lock, or move MES to COM8/9/10 (all free).
6. **Move `LOG Folder` out of Program Files** — hygiene, needs elevation.
7. **Watch the log folder** for per-operation completion events (seconds granularity, not telemetry).
8. **Register a forum account** — `forum.multiecuscan.net` is entirely login-gated: 20,696 posts / 4,061 topics / 14,075 members, all invisible to guests. Use `https://multiecuscan.net/forum/` (the `http://forum.` cert does not cover that subdomain).

### Explicit dead ends — do not spend time here

| Dead end | Status |
|---|---|
| API / SDK / plugin / macro / scripting | **CONFIRMED absent** |
| COM automation / TypeLib / ProgID | **CONFIRMED absent** (registry verified) |
| Usable command-line arguments | **LIKELY absent** |
| Decompiling `Multiecuscan.exe` | **CONFIRMED futile** — packed, 21 literals, anti-debug |
| Decrypting `data01-06.dat` | **CONFIRMED infeasible** without runtime key extraction |
| `FES_Templates.ini` as a parameter API | **Tested and refuted** — per-ECU indices |
| XML export | **CONFIRMED nonexistent** |
| Published log/CSV format spec | **CONFIRMED nonexistent** |
| Streaming live data from `.txt` logs | Written on completion, not appended — use CSV |
| A "MULTISCAN" adapter | **Does not exist** — it is CANtieCAR / vLinker MS |
| Third-party MES driver or protocol reimplementation | **None exists** |

**Documentation caveat:** the manual shipped in this install is byte-identical to the one the vendor still serves — and **both are the 2012 guide for Multiecuscan 1.0**, ~14 years stale. **Trust the website over the manual.**

**Known blind spot:** the login-gated forum archive is the biggest one. Reddit/FiatForum/AlfaOwner were unreachable during research.
