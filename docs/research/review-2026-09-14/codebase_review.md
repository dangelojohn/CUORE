# Architecture Review — Alfa/Stellantis Diagnostic Toolchain (C:\Users\User\mcp-servers)

**Scope:** read-only. Reviewed all of `mes-log-mcp/`, `obd2-mcp/`, `cuore/`, `docs/`, plus read-only inspection of the MES install at `C:\Program Files (x86)\Multiecuscan` and its registry key. No files were modified.

**One-line finding:** the toolchain is a *forensic* system — it reads what MES already wrote and, separately, can poke the car over a generic ELM327. It has **zero live coupling to MES** (no watcher, no process awareness, no port arbitration, no automation), and the OBD side is a **Mode 01/02/03/04/07/09 tool only** — no UDS, no ISO-TP, no CAN monitoring, no ST-series support, and no Mode $06. Everything in `COMPANION_APP_SPEC.md` beyond the mechanic-mode read path is unbuilt.

---

## 1. Every existing connection to MES and to the car

### 1.1 Log discovery — polling on demand, no file watching

There is **no file watcher anywhere in the repo** (`watchdog` is not a dependency; `mes-log-mcp/requirements.txt` is just `mcp>=1.2.0`).

Discovery is a directory scan re-run on **every tool call**:

- `mes/paths.py:157` `iter_log_files()` -> `root.iterdir()` over each existing root, filtered by filename regex.
- Roots resolve in `mes/paths.py:43` `configured_roots()`: `MES_LOG_DIRS` (os.pathsep) -> `MES_LOG_DIR` -> `DEFAULT_ROOT` = the MultiEcuScan install dir (`paths.py:37`).
- Filename patterns, `paths.py:34-35`: `FESLog_(\d{10})_(.+)\.txt` and `SCAN_(\d{10})\.txt`.
- `mes/catalog.py:188` `Catalog.entries()` rebuilds the index per call; `catalog.py:162` `_entry_for()` caches parsed metadata per file keyed on `(st_mtime, st_size)` (`catalog.py:172-174`).
- **Half-written-file handling:** `catalog.py:36` `SETTLE_SECONDS = 3.0`; a file touched within 3 s is flagged `possibly_incomplete` and **deliberately not cached** (`catalog.py:180-185`) so it is re-read once MES finishes.

So: *pull-based polling at tool-call granularity*, not push. Nothing runs between tool calls. Ordering is by **filename timestamp**, with mtime only as fallback (`catalog.py:77-81`) — a deliberate fix for backup round-trips.

**Path containment** is the security boundary and is well done: `paths.resolve_log()` (`paths.py:123`) rejects separators/drive letters (`paths.py:98-112`), requires a MES log pattern, and re-checks containment **after** `.resolve()` so a planted symlink fails (`paths.py:146`).

### 1.2 Parsing

- `mes/fes.py` (712 lines) — FES engineering sessions. Anchors on the `(Multiecuscan ...)` preamble regex (`fes.py:51`) rather than line 1, because 5 corpus files open with a CAN/PROXI prologue. Section markers at `fes.py:58-61`: `READING PARAMETERS:`, `CLEARING STORED FAULT CODES`, `EXECUTING (ACTUATOR|ADJUSTMENT)`, `Reading CAN configuration data`. Simulation detection is the literal string `SIMULATION MODE` (`fes.py:55`).
- `mes/scan.py` (408 lines) — all-systems scans; module blocks found by anchoring on `ISO Code:` and walking back two lines; handles MES repeating every module 2-3x per phase.
- `mes/encoding.py` (144 lines) — BOM sniff (5 BOMs, `encoding.py:24`), strict-UTF-8 -> cp1252 -> latin-1 ladder (`encoding.py:35`), and stray control-byte stripping with a reported count (`encoding.py:40`, `:78`).

### 1.3 CSV recordings

- `mes/csvlog.py` (442 lines). **Never validated against a real file** — `csvlog.py:26-30`: "No CSV has ever been recorded on this install, so this parser is validated against synthetic fixtures."
- Separate root config: `paths.csv_roots()` (`paths.py:198`) uses `MES_CSV_DIRS`/`MES_CSV_DIR`, falling back to the log roots, because MES's Settings "Export Folder" is configured independently.
- Filename convention is **UNKNOWN**, so `CSV_RE` (`paths.py:195`) accepts any bare `*.csv` — containment still enforced (`paths.py:233`).
- Separator is sniffed from tab / semicolon / comma (`csvlog.py:49`); UTF-16LE expected; row 1 names, row 2 units, col 1 `Time` (s), last col `TAG`.
- Genuine capability the `.txt` path lacks: measured sample rate and **dropout detection** at `GAP_FACTOR = 3.0` (`csvlog.py:68`), threshold-crossing "excursion interval" queries (`_COND_RE`, `csvlog.py:57`), and DTC extraction from TAG cells (`_DTC_RE`, `csvlog.py:54`).

Exposed via five MCP tools: `list_recordings`, `read_recording`, `recording_series`, `recording_events`, `recording_snapshot` (`mes-log-mcp/server.py:588-688`).

### 1.4 `obd2-mcp/server.py` — what it actually does

**628 lines, 13 tools, `pyserial` + `mcp` only.** State is a single module-global `STATE = Conn()` (`obd2-mcp/server.py:33`) holding one open `serial.Serial` **for the lifetime of the process**.

| Aspect | Reality |
|---|---|
| Adapter assumed | Generic ELM327-compatible on a COM port. Defaults `OBD_PORT` env, **`OBD_BAUD=38400`** (`server.py:36`), `OBD_TIMEOUT=4` (`:37`) |
| Init sequence | `ATZ, ATE0, ATL0, ATS0, ATH0, ATSP0` then `ATI` (`server.py:257`, `:267`) |
| Protocol handling | **`ATSP0` auto only.** No `ATDPN`->`ATSP6` pinning, no `ATAT`/`ATST` timing control, no `ATH1` |
| OBD modes | 01 (`read_pid`, `read_supported_pids`), 02 (`read_freeze_frame`), 03/07/0A (DTCs), 04 (`clear_dtcs`), 09 PID 02 (`read_vin`) |
| Readiness | `read_readiness` (`server.py:493`) decodes Mode 01 PID 01 and PID 41 — 8 non-continuous + 3 continuous monitors (`server.py:437`, `:449`), plus warmups/distance counters, and emits an explicit `evap_verdict` |
| **UDS** | **None.** No `0x19`, `0x22`, `0x2F`, `0x31`, `0x10`, `0x3E`. UDS appears only as a *blocklist* (`_WRITE_SERVICES`, `server.py:589`) and as prose in `read_dtcs` (`server.py:308-309`) |
| **ISO-TP / multi-frame** | Only cosmetic: `_hex_pairs` strips a leading `0:` / `1:` index when the head is <= 2 chars (`server.py:158-163`). **No flow-control configuration** (`ATFCSH/ATFCSD/ATFCSM`, `ATCFC`), no `ATCRA` receive filter, no frame reassembly, no `0x78 responsePending` handling |
| **CAN monitoring** | **None.** No `ATMA`/`ATMR`/`ATMT`, no DBC, no `python-can` |
| **ST-series (STN/OBDLink)** | **Not supported and not recognised** — see section 4.2, it is also a safety hole |
| Mode $06 | Not implemented (named as a blind spot at `mes/workup.py:176`) |
| Port sharing with MES | **Nothing enforced.** Only a docstring: "only one program can hold the COM port. Close MultiEcuScan first." (`server.py:236`) |

**Error handling is the strong part.** `ADAPTER_ERRORS` (`server.py:114`, 13 conditions) and `adapter_error()` (`server.py:126`) exist specifically so a bus fault is never reported as "no codes". `_hex_pairs` (`server.py:139`) handles spaced *and* unspaced output — the file documents that the v1 parser returned `[]` for essentially every read. `_decode_dtcs` (`server.py:181`) implements correct ISO 15031-6 category math (`letter = "PCBU"[high >> 2]`, `server.py:209`), fixing a v1 bug that rendered every C/B/U code as P.

**`send_raw` (`server.py:557`)** is the escape hatch. It classifies the command via `_classify_write()` (`server.py:602`) and refuses unless `i_understand_this_writes_to_the_vehicle=True`. Blocked: Mode `04`/`0400`, `ATSH*`, and UDS services `14, 27, 2E, 2F, 31, 34, 35, 36, 37`. Everything else — including all other `AT` commands and every read service — passes unguarded. There is **no allowlist**; it is a deny-list.

### 1.5 How `cuore` exposes all this

`cuore/services/mes_bridge.py` (598 lines) is the **only** module importing `mes`, mirroring the MCP surface call-for-call (stated at `mes_bridge.py:1-13`). HTTP routes:

- `cuore/api/vehicles.py:22-116` — vehicles, workup, report, dtcs, dtc detail, freeze, actuators, tree, session, scan, parameters, parameter, POST verdict.
- `cuore/api/logs.py`, `cuore/api/recordings.py`, `cuore/api/reference.py`, `cuore/api/system.py` (capabilities / health / status / roots).
- `cuore/web/routes.py` — server-rendered bench pages over the same bridge.
- Memoisation keyed on `(vin, newest mtime)` (`cuore/services/cache.py`), which self-invalidates when MES writes a new log.

**`cuore` has no connection to the car at all.** `cuore/profiles.py:36-38` declares `live_obd`, `live_can`, `drive_recorder`, `actuators` — all `False` on both profiles (`profiles.py:51-54`, `:69-72`). `AdapterInfo` is hard-coded `present=False, note="live link not built yet (P2)"` (`cuore/models.py:38-52`) and `cuore/api/system.py:60` always constructs a bare `AdapterInfo()`. `websockets>=12` is in `cuore/requirements.txt` but nothing imports it. The `/api/live/*` and `WS /api/live/stream` surface from spec section 11 does not exist.

### 1.6 MES surfaces that exist on this machine but nothing reads (verified directly)

These go beyond what the docs record and are the most actionable part of this review:

1. **`HKLM\SOFTWARE\Multiecuscan` is world-readable and carries live MES state.** Confirmed values include:
   - `Interface 0 Port = COM3`, `Interface 0 Port Speed = 115200`, `Interface 0 Type Ex = 7` — **the obd2 server defaults to 38400** (`obd2-mcp/server.py:36`), a straight mismatch with how MES drives the same adapter.
   - `Export Folder = .`, `LOG Folder = .`, `CSV Separator = Tab` — exactly what `mes/paths.py` and `mes/csvlog.py` assume, but **neither reads the registry to confirm it**. Both are hard-coded/env-driven guesses that would silently go stale if the user moves the folder.
   - `Last Selection = 10622` and `Recent Vehicles = (695),(757),(646),(694);(106),(101),...` — **mutable MES session state**. Polling these is the cheapest possible "what vehicle/ECU does MES currently have selected" signal, and nothing in the repo touches it.
   - ACL confirmed: `BUILTIN\Users` has **`ReadKey` only** — reading is free, writing (e.g. moving MES off COM3) needs elevation, exactly as `COMPANION_APP_SPEC.md:160` says.
2. **Two plain-text INI files in the install dir**: `FES_Tags.ini` (10 tag slots, `0 = ` ... `9 = `) and `FES_Templates.ini` (ID lists, e.g. `0=1989,1802,1872,1804`), both last written 2025-09-04. `MES_INTEGRATION_SURFACE.md:175` records `FES_Templates.ini` as a parameter API "tested and refuted" — but these are the **only** MES config files outside the elevated registry key, and `FES_Tags.ini` plausibly seeds the CSV `TAG` column the toolchain already parses.
3. **`Multiecuscan.exe` is a .NET/WinForms assembly** — confirmed the CLR `BSJB` metadata signature at offset 3471944, an `mscoree` import, and `System.Windows.Forms` in the string data. The research doc correctly calls *decompilation* futile (packed + obfuscated + AES-decrypted at runtime), but it says nothing about **UI Automation**: a WinForms app exposes a full UIA tree, which is a real, unexplored control surface for driving MES (see 3.2).
4. `Files\data01-06.dat` (~80 MB, encrypted) and `Lang\English.dat` (437 KB UTF-16LE, 6,326 strings) / `English.txt` (18 KB, ID=text) are present and unreferenced by any code here.

---

## 2. Proposed but NOT yet built

### 2.1 From `docs/COMPANION_APP_SPEC.md`

| # | Idea | Where | Status |
|---|---|---|---|
| 1 | **The MES interlock** — 3 layers | 4.3, lines 141-161 | **Not built.** "Before any adapter open, poll for `Multiecuscan.exe`"; "Advisory lock file. `%PROGRAMDATA%\cuore\adapter.lock` holds pid + port + purpose"; "Lazy per-operation open. Open the port for the operation, close immediately. Never hold COM3 for the server's lifetime." The obd2 server does the **opposite** — it holds the port. |
| 2 | Handoff checklist (finish operation -> exit MES -> wait S3 ~5 s or `10 01` -> `ATWS` + full re-init) | lines 155-157 | Not built |
| 3 | **Drive node** (`cuore serve --profile drive`) on Pi Zero 2 W / old Android | 4.4, lines 162-174 | Profile enum exists (`cuore/profiles.py:24`); every capability is `False` |
| 4 | Sync drive-node -> bench, content-hash names, rsync-shaped | 4.5 | Not built |
| 5 | **DRIVER mode**: live cluster, warm-up gate, "Silent watchdog ... No LLM in this path", MIL-on capture | 5.1 | Not built |
| 6 | **ENTHUSIAST mode**: drive log in `csvlog` schema, sessions/overlays, 0-100, health trends | 5.2 | Not built |
| 7 | **Mode $06** — "The only non-dealer route to 'the test ran and passed at X against limit Y.' Reachable today via `send_raw`; needs MID iteration and ISO 15031-5 UAS scaling. **The highest-value unbuilt read in the whole toolchain.**" | lines 242-245 | Not built |
| 8 | Repair-verification verdict (readiness + $0A + $06 + warmups as one answer) | lines 238-241 | Components exist separately; no combined verdict |
| 9 | Module map with bus / capability flags / licence gating | line 247 | `mes/modules.py` has 126 modules but **no bus or capability-flag fields** |
| 10 | Guided procedures (EVAP, P1CEA, ZF 8HP adaptation reset, service reset, clutch calibration) | line 249 | Not built |
| 11 | **Tier-2 CAN sniffing** with `fca_giorgio.dbc`; "`0x0F1` is the single highest-value measurement available for this car" (100 Hz `MAYBE_VOLTAGE`) | 6.2, lines 279-307 | Not built; needs CAN hardware |
| 12 | Tier-1 tuning: "Pin the protocol (`ATDPN` once, then `ATSP6` — never leave `ATSP0` re-searching). `ATH1` mandatory for multi-ECU. `ATAT0` + explicit `ATST hh`" | lines 270-271 | **Not done — the server does the opposite** (`ATS0`, `ATH0`, `ATSP0`) |
| 13 | **Claude Layer 0** — deterministic thresholds, no LLM in the safety path | 9.1 | Not built |
| 14 | **Claude Layer 1** — PWA calls Anthropic directly, prompt caching with the knowledge pack behind a `cache_control` breakpoint | 9.2 | Not built |
| 15 | **Claude Layer 2** — "Claude gets **real tool access to the 28 `mes` tools and the OBD tools** ... the difference between an assistant that was told about the car and one that can go look." | 9.3 | Not built (Claude Code already does this via MCP — but not via cuore) |
| 16 | **Claude Layer 3** — Batch API post-drive analysis at 50% cost; scheduled nightly review | 9.4 | Not built |
| 17 | Layer 4 — voice | 9.5 | Deferred |
| 18 | **Safety / write policy** (12 rules): no writes in motion; "Claude never holds a write tool. Not in any layer."; two-step confirm; precondition checks; never interrupt an actuator test; "`send_raw` ... with `0x2E`/`0x34`/`0x36`/`0x37` blocked outright"; await `0x78`; pins 1/9 check; "Pull `DTC EX` before any clear"; scan discipline; LAN-only node | 12, lines 511-545 | **Only rule 6 is partially implemented** (`_classify_write`). Nothing else exists in code |
| 19 | `/api/live/*` + `WS /api/live/stream` + `POST /api/procedure/{kind}` | 11 | Not built |
| 20 | Web Push -> Apple Watch alerting | 8 | Not built |
| 21 | Data model (`Vehicle/Session/Recording/Sample/Event/DtcObservation/Verdict/Procedure`) with append-only `Procedure` table | 10 | Not built; no persistence layer at all |

Phasing (section 14) puts these at **P2-P9**; the repo is at **P1**. Open decisions (section 15) include "Does MES move off COM3? Recommend yes; COM8/9/10 are free" and "Mode $06 MID availability on the IAW 10JA — a ten-minute check on the car."

### 2.2 From `docs/research/`

**`MES_INTEGRATION_SURFACE.md`** — the load-bearing constraint, line 9:
> "**MES has no API, SDK, COM interface, plugin system, scripting host, or usable command line. CONFIRMED by exhaustion** — no COM/TypeLib registration in the registry, no developer section on the vendor site (12 probed URLs all 404), and zero mentions of API/SDK/script/plugin/macro/automation in the official manual."

Its ranked proposals (lines 154-164), none built:
1. **Ingest the vendor capability matrix to SQLite/JSON as `mes_capabilities(vehicle, module)`** — line 156: "Parse the HTML, not the plain text: the red-font wrapper marks exactly 5,814 module names, giving per-module FREE-vs-REGISTERED gating for free."
2. Ship `English.dat` (6,326 entries: DATA 10001-12386, ENUM 18001-18494, DTC 20001-23452) + `English.txt` as decode tables (line 157).
3. Use **simulation mode (Ctrl+F10)** as a per-ECU capability enumerator — "Cannot be automated; treat as a data-collection ritual" (line 158).
4. Turn on CSV recording — "The real streaming path, never used here" (line 159).
5. **Resolve COM3 contention** (line 160); 6. move `LOG Folder` out of Program Files (line 161).
7. **Watch the log folder for per-operation completion events** — "seconds granularity, not telemetry" (line 162).

**`CONNECTIVITY_AND_SGW.md`** — line 161: "**Structural fix:** open the port lazily per operation and close immediately, rather than holding COM3 for the server's life." Also proposes an **empirically derived FCA body-module CAN ID table** — line 188: "blocks per-module UDS work. Derive empirically" / line 106 "**Derive empirically; do not guess.**" Adapter is confirmed COM3 = FTDI FT231X "vLinker FS" (VID_0403/PID_6015) — the **Ford** variant, not the MES-endorsed MS.

**`MES_CAPABILITY_GAPS.md`** — line 19: "**MES implements no generic OBD-II mode at all.**" Unbuilt items: Mode $06 tool (line 53 "the highest-value remaining read"; line 59 "A proper tool would iterate MIDs and apply ISO 15031-5 UAS scaling"), VIN-keyed service-history index (line 98 "best value-to-effort ratio"), local knowledge base, high-rate voltage logging (PID 42 or `0x0F1`), and arbitrary UDS over `send_raw` — line 96: "the most dangerous item in this document — `0x2E`/`0x34`/`0x36`/`0x37` can brick a module ... Ranked low despite being feasible."

**`DIAGNOSTIC_ASSURANCE_FRAMEWORK.md`** — six pillars; three built (`workup`, `fault_tree`, `diagnosis_verdict`), one partial (repair verification), two open. Pillar 2 is called **the** gap (lines 46-53): "A live value without a limit is noise. Needed: per-parameter spec table for the IAW 10JA / GME-T4 — nominal range, condition (idle/cruise/KOEO), source, confidence ... Then `recording_series` / `snapshot` / `parameter_series` flag in/out-of-range automatically."

**`GIORGIO_PLATFORM.md`** — proposes ingesting `fca_giorgio.dbc` (243 lines, one commit 2024-09-18, ~40% still `NEW_SIGNAL_n`) with a full address table (`0x0DE` EPS_1, `0x0EE` ABS_1 wheel speeds @100 Hz, **`0x0F1` MAYBE_VOLTAGE**, `0x0FA`/`0x0FC`/`0x0FE`/`0x101`/`0x106`/`0x10E`/`0x122`/`0x5A2`), CRC-8 poly `0x2F` (SAE J1850) checksum with the counter in the low nibble of byte n-1. Also proposes the NHTSA complaints API as a pattern source. Caveat at line 178: **zero UDS content — broadcast traffic only**.

`ECU_TUNING_IAW10JA.md` and `TRANSMISSION_ZF8HP_Q4.md` add a MES byte-editor surface (**Ctrl+Alt+C on the Adjustment tab**, with a verified byte dictionary incl. battery type byte 63) and an in-house Q4 architecture determination via MES parameter names under simulation mode — both manual rituals, neither automated.

### 2.3 `docs/design/`

Contains **only** `cuore-bay-tablet.html` (44 KB) — a self-contained dark-theme UI mockup of the bay-tablet drill-down, using cuore's own CSS tokens. It is a *presentation* design, not an integration design; it contains no live/OBD/WebSocket plumbing beyond one "OBD Injection" label.

### 2.4 One documented contradiction worth resolving

`MES_INTEGRATION_SURFACE.md:130` says "Logs are written at completion, not streamed ... File-watching gives per-operation latency, not live telemetry." But `docs/format/FES_LOG_FORMAT.md:271` says: "MES writes banner+name at start, outcome on return; if the app closes first the file is left short" — which describes **incremental per-operation flushing within a single open file**, and `SCAN_LOG_FORMAT.md:10` calls a SCAN file "an append-only transcript of the 'Scan vehicle' UI panel", with `:284` noting a file appeared mid-analysis and "must tolerate files ... being read mid-write."

Those are reconcilable (each MES operation-session produces its own file, flushed per operation), but the practical consequence is stronger than the pessimistic doc implies: **a tail on the active `FESLog_*.txt` yields operation-start events, not just completion events** — roughly a 1-3 s view into a running MES session. Nobody has built that tailer.

---

## 3. Gaps and limitations in the current design

### 3.1 Real-time observation of a running MES session

- **No watcher process exists.** Everything is pull-based at MCP-tool granularity (`mes/paths.py:157` -> `iterdir()` per call). Claude cannot be *notified* that MES just cleared a code; it can only be asked to look again.
- `catalog.SETTLE_SECONDS = 3.0` is the only concession to live files, and it is a *suppression* mechanism (flag as incomplete, don't cache) rather than an *observation* mechanism.
- The active FES log is a single growing file with a **fixed filename created at session start** — ideal for tailing — yet no tool reads partial content incrementally. `read_log` (`mes-log-mcp/server.py:123`) reads whole-file with a `max_bytes` cap from the front; there is no offset/tail parameter.
- **Un-exploited signals nothing reads:** `HKLM\SOFTWARE\Multiecuscan\Last Selection` and `Recent Vehicles` change as MES is used; the process table tells you whether `Multiecuscan.exe` is running at all; `Report1.pdf` in the install dir marks a PDF export.
- Practical consequence: the single most valuable thing Claude could do during a bench session — *watch over the technician's shoulder and comment as each operation returns* — is structurally impossible today, and is closer than the docs imply.

### 3.2 Triggering MES actions

- **There is no mechanism at all, and the docs conclude there cannot be one via a supported interface** (`MES_INTEGRATION_SURFACE.md:9`, confirmed by exhaustion).
- What the docs have **not** evaluated, and which I verified is available: `Multiecuscan.exe` is a **.NET WinForms** binary, so it exposes a complete **UI Automation tree**. FlaUI / pywinauto-UIA driving of a WinForms app is a well-trodden path and does not require decompiling or defeating the packer — the obfuscation that makes static analysis futile is irrelevant to UIA, which reads the live control tree. This is the one genuinely unexplored MES control surface.
- Risk this creates and which section 12 does not yet cover: UIA can click **Execute Actuator** as easily as **Read Parameters**. `COMPANION_APP_SPEC.md:418` says "writes stay human-initiated, full stop" — a UIA layer needs its own allowlist of clickable controls, or it silently hands Claude every write MES can do, on the one path where MES's own preconditions and licence gating are the only remaining guard.
- Lesser surfaces: `FES_Tags.ini` / `FES_Templates.ini` are the only writable MES config (registry needs elevation — `BUILTIN\Users: ReadKey` confirmed). `FES_Templates.ini` was "tested and refuted" per `MES_INTEGRATION_SURFACE.md:175`, but with no recorded methodology; `FES_Tags.ini` was never tested and plausibly seeds the CSV `TAG` column the parser already reads.

### 3.3 Reading MES's live parameter stream

- MES's `.txt` parameter blocks have **no per-sample timestamps** — the library says so explicitly and refuses to fake a rate (`mes-log-mcp/server.py:399-400`: "MES records no per-sample timestamp; order is file order and the sample rate is unknown").
- Only **4 corpus files** contain `READING PARAMETERS:` blocks at all (`FES_LOG_FORMAT.md` section 6: 494 / 152 / 99 / 70 blocks). The parameter set **grows mid-session** as the operator adds watch items, so `list_parameters` returns a union (`server.py:355-358`).
- The `static` flag (`params.ParamSeries.stats()`, `params.py:205`) is the sharpest tool here — a value pinned across every sample flags a substituted default rather than a measurement — and it is surfaced with an explicit interpretation (`server.py:401-407`).
- **The CSV path is the only real stream, and it has never been exercised.** `csvlog.py:26` is unambiguous. So the one MES output with real timing is parsed entirely against synthetic fixtures, with the filename convention, DTC-in-TAG rendering, decimal separator and absolute-timestamp questions all marked `UNCONFIRMED` in `docs/format/CSV_LOG_FORMAT.md`.
- Gap: even with a CSV in hand, there is **no known-good reference data** to compare values against (`DIAGNOSTIC_ASSURANCE_FRAMEWORK.md:46-53`). `mes/params.py` canonicalises 27 units but encodes **zero expected ranges**.

### 3.4 Correlating MES logs with live OBD data

This is the widest structural gap, and it is architectural rather than a missing feature:

1. **Two separate MCP servers with no shared identity.** `obd2-mcp` has no concept of a VIN beyond `read_vin()` returning a string; it never consults the corpus. `mes-log-mcp` never calls the car. Nothing joins them.
2. **No common time base.** MES `.txt` has no per-sample timestamps; MES CSV has relative seconds from an unknown wall-clock start (`CSV_LOG_FORMAT.md`: absolute timestamps `UNCONFIRMED`); `obd2-mcp` returns bare strings with no timestamps at all.
3. **No common vocabulary.** `mes/params.py` has **no parameter-name canonicalisation or synonym table** (names used verbatim as MES printed them), and **no PID mapping** — while `obd2-mcp/server.py:40` has a 31-entry `PIDS` dict keyed on its own friendly names. MES's "Engine speed" and obd2's `engine_rpm` are unrelated strings in two processes.
4. **No persistence.** `cuore` has no database; `cache.py` is a 16-entry in-memory LRU. There is nowhere to *store* a correlated observation even if one were made. The `Recording`/`Event`/`Sample` model in spec section 10 is unbuilt.
5. `obd2-mcp` returns human-readable strings (`server.py:388`) rather than JSON — the opposite of the deliberate choice made in `mes-log-mcp/server.py:8-9` ("Tools return **JSON**, not hand-formatted text"). Only `read_readiness` returns JSON (`server.py:554`). Any correlation layer would have to re-parse prose.
6. **Not even raw byte decoding is done.** `read_pid` returns `data=['0B','4C']` — the caller must apply the J1979 formula itself. The `PIDS` table stores `(pid, unit)` but **no formula**, despite the comment at `server.py:39` claiming `name -> (pid, formula, unit)`.

The one place correlation *is* implemented is inside the evidence gate: `mes/verdict.py:94` `_verify_measurement` dispatches over 6 citation types and verifies `actuator` / `freeze_frame` / `parameter` / `recording_event` against the corpus. But live OBD is **not an accepted citation type** (`_VERIFIABLE`, `verdict.py:44`) — a live readiness result or a Mode $06 measurement can only enter as `type: "manual"`, i.e. merely *attested*, not verified. That is the single highest-leverage extension point in the codebase.

### 3.5 FCA Security Gateway (SGW)

**For this specific car the question is settled**, and settled by strong local evidence — `CONNECTIVITY_AND_SGW.md:50`:
> "`CONFIRMED (local)`: MES performs full bidirectional writes to the powertrain ECU on this car — DTC clearing, physical actuator commands, adaptation routines — over an ELM327-class adapter, with no bypass cable and no authentication step anywhere in the logs."

Corroborated at `MES_CAPABILITY_GAPS.md:94`: the one bidirectional failure in the whole corpus was UDS `0x22 conditionsNotCorrect` (Fan 1st speed, "Engine running") — a **precondition refusal, not a gateway block**. `mes-log-mcp/server.py:485-488` even encodes this as a note on `actuator_history`.

**The gaps are all about generalisation and about handling failure:**

- **Fitment is by production date, not model year** — NAFTA Giulia/Stelvio from **Feb-2018 production** (`CONNECTIVITY_AND_SGW.md:61-70`). Nothing in the code models this. `mes/modules.py`'s `ModuleInfo` has 9 fields (`code, name, description, domain, tier, giorgio, aliases, source, note`) and **no SGW field**. The spec's data model has `Vehicle.sgw_status` (section 10, line 457) — unbuilt. There is no build-date extraction from VIN anywhere.
- **The failure mode is undefined.** `CONNECTIVITY_AND_SGW.md:80`: "What NRC an SGW returns when blocking is **UNRESOLVED** ... generic OBD Modes 01/03 keep working and clearing is the specific thing blocked." So `obd2-mcp` has **no SGW-aware error handling at all** — a gateway-blocked write would surface through `adapter_error()` only if it happens to contain one of the 13 `ADAPTER_ERRORS` strings; a UDS negative response like `7F 14 33` (securityAccessDenied) is not recognised anywhere, and `_hex_pairs` would hand it back as three anonymous bytes. There is **no NRC decoder** in the repo.
- **MES cannot help.** `CONNECTIVITY_AND_SGW.md:56-59` quotes MES's own banner: "It is not possible to unlock the SGW module with Multiecuscan", and "MES cannot use AutoAuth — its only sanctioned routes are a hardware bypass or tapping CAN behind the gateway."
- **Options, none integrated:** hardware bypass dongles (`SGB0001` / `SGB0001.B01`, Centerline `FI504` ~$59.95, GaleMotorsport ~EUR 49) — "Not compatible with 2021+ where SGW is integrated into the BCM", and per `ECU_TUNING_IAW10JA.md:65` "make sure that the bypass supports the second high-speed CAN bus. A generic FCA bypass sold for a Ram or Wrangler may leave you unable to reach the chassis modules." AutoAuth is $5/mo but unusable by MES. Bench work sidesteps it entirely.
- **Consequence for the wider goal:** the moment this toolchain is pointed at a second, post-Feb-2018 car, every write path silently changes behaviour with no code path to detect or explain it. A `vehicle.sgw_status` field, a build-date-from-VIN check, and an NRC decoder (`0x33`, `0x7F`, `0x78`) are prerequisites for anything beyond this one Stelvio.

---

## 4. Code-quality and safety concerns in `obd2-mcp/server.py`

Ordered by how much they matter for extending the file.

### 4.1 `send_raw` write gate is bypassable by command injection — most serious

`_classify_write()` operates on `cmd` (stripped/uppercased), but `_cmd()` transmits the **original** `command` (`server.py:572` vs `:584`). `_write()` only strips the ends and appends CR (`server.py:85`). An embedded carriage return therefore sends **two commands** while only the first is classified:

```
send_raw("ATI<CR>04")
  -> compact.startswith("AT") -> _classify_write returns ""   (allowed)
  -> wire: "ATI<CR>04<CR>"    -> ELM runs ATI, then Mode 04 = clear DTCs
```

The same trick reaches `2F` (actuator), `31` (routine), `34`/`36` (reflash). This defeats the entire stated purpose of the gate (`server.py:566-570`). Fix: classify **every** CR/LF-separated segment, and reject embedded terminators outright.

### 4.2 ST-series commands pass the gate as "read-only"

`_classify_write` (`server.py:602`) has three branches: `AT*` (only `ATSH` blocked), non-hex -> `""`, hex -> service lookup. An **`ST` command is neither** `AT`-prefixed nor pure hex, so it falls through the non-hex test at `server.py:615` and returns `""` — **allowed with no confirmation**. That includes `STWBR`/`STSBR` (change baud — can desync the link), `STPX` (single-shot extended transmit, i.e. an arbitrary CAN frame with arbitrary ID and payload — a full write primitive), and `STP`/`STM` mode changes. The server doesn't *support* ST commands, but it doesn't *guard* them either, and the plan to move to an STN adapter makes this live.

Related: **every `AT` command except `ATSH` is treated as read-only.** `ATPP xx SV yy` + `ATPP xx ON` writes **persistent** adapter configuration that survives power cycles; `ATBRD` changes baud; `ATCAF0` disables CAN formatting, changing how every subsequent response is framed. None are vehicle writes, but all are silent state changes that make later reads wrong.

### 4.3 `adapter_error()` is applied inconsistently — the exact bug class the file was rewritten to fix

`ADAPTER_ERRORS` exists (per `server.py:110-113`) "so a bus fault [is not] indistinguishable from 'no codes' — the worst possible failure mode for a diagnostic tool." It is checked in `read_dtcs` (`server.py:299`) and `read_readiness` (`server.py:513`, `:541`). It is **not** checked in:

- `read_pending_dtcs` (`server.py:314`) -> reports "pending DTCs: (none)" on a `BUS ERROR`
- `read_permanent_dtcs` (`server.py:326`) -> same, and permanent DTCs are the *proof of repair* path
- `read_pid` (`server.py:362`), `read_supported_pids` (`server.py:391`), `read_freeze_frame` (`server.py:350`), `read_vin` (`server.py:403`), `send_raw` (`server.py:557`)

`_hex_pairs` silently drops error lines (`server.py:156`), so the caller sees an empty list and the tool prints "(none)". Three of the four DTC-reading tools have exactly the failure mode the module docstring calls unacceptable.

### 4.4 `clear_dtcs` guard is thin relative to the stated policy

`clear_dtcs` (`server.py:336`) requires only `confirm=True`. Missing, relative to `COMPANION_APP_SPEC.md` section 12:

- **No pre-clear evidence capture.** 12.9: "Pull `DTC EX` before any clear. Clearing destroys the only evidence. The app should make this automatic, not advisory." The tool clears without reading DTCs, freeze frames, or readiness first — and freeze frames are *the* evidence `mes/workup.py` and `mes/verdict.py` are built around.
- **No speed check.** 12.1 requires speed == 0 verified from the vehicle. `vehicle_speed` is PID `0D` in the table (`server.py:49`) and is never consulted.
- **No post-clear readback.** The result is a bare echo of the raw string. `44` (success) and `NO DATA` / `BUS ERROR` are indistinguishable to the caller.
- **No record.** `mes/analysis.py:358` `ClearAssessment` encodes four careful verdict rules about what a clear does and does not prove; an obd2-initiated clear leaves no artifact for any of that to act on.

### 4.5 Port lifetime directly contradicts the designed interlock

`STATE.ser` is opened in `connect()` (`server.py:247`) and stays open until `disconnect()`. `COMPANION_APP_SPEC.md:149-151` specifies the opposite — "Lazy per-operation open ... Never hold COM3 for the server's lifetime. This is the structural fix identified in `CONNECTIVITY_AND_SGW.md` section 5 and it makes handoff a non-event."

Additionally:
- **No MES process check, no lock file** — the only protection is a docstring (`server.py:236`).
- **Baud mismatch:** default `38400` (`server.py:36`) vs MES's registry-configured `115200` on the same COM3.
- **Port collision is the documented default state:** MES `Interface 0/1 Port = COM3` and `obd2-mcp` defaults to COM3 as well. `COMPANION_APP_SPEC.md:595` lists this as open decision #5.
- **No concurrency guard.** `STATE` is a bare module global with no lock (`server.py:33`). FastMCP can dispatch concurrent tool calls; two overlapping `_cmd()` calls interleave writes and reads on a stateful half-duplex REPL. Given `CONNECTIVITY_AND_SGW.md:149` calls misattributed responses on an actuator-capable device "a **safety** problem", this deserves an explicit lock.

### 4.6 Timeouts

- `send_raw(timeout_seconds: float = DEFAULT_TIMEOUT)` (`server.py:558`) is **unbounded** — a caller can pass 3600 and wedge the server. No clamp.
- `_read_until_prompt` (`server.py:89`) busy-loops on `read(1)`; on a dead link each `read(1)` blocks the full `DEFAULT_TIMEOUT` (4 s) and the outer deadline test then allows one more iteration — worst case ~2x the requested timeout.
- `connect()` uses a 3 s per-command timeout for init (`server.py:259`) and swallows per-command exceptions into a log string (`server.py:260-263`), so a fully failed init still returns "Connected ...".
- `_open()` sets `timeout` and `write_timeout` but never `inter_byte_timeout`, and never drains the port after `ATZ` (which emits a banner asynchronously).

### 4.7 Protocol / parsing correctness issues that will bite an extension

- **`ATH0` + `ATSP0` is the wrong baseline** for anything multi-ECU (`server.py:257`). Without `ATH1` you cannot tell which module answered — fatal for UDS work, and directly contrary to `COMPANION_APP_SPEC.md:271` ("`ATH1` mandatory for multi-ECU"). With headers off, `_hex_pairs`'s header-stripping branch (`server.py:169`) is dead code in practice.
- **`_decode_dtcs` assumes a count byte always follows the response byte** (`server.py:189-190`, `idx = 2`). True on CAN; not on ISO 9141 / KWP2000, where the response is `43` + DTC pairs. It also cannot separate responses from multiple ECUs — they concatenate into one pair list.
- **`PIDS` has no formulas.** The docstring claims `name -> (pid, formula, unit)` (`server.py:39`) but the tuples are `(pid, unit)` (`server.py:40`). `read_pid` returns raw bytes; no scaling is applied anywhere. Every consumer must know J1979 itself.
- `read_freeze_frame` returns a raw repr with no decoding at all (`server.py:359`).
- `_hex_pairs` odd-nibble handling truncates from the **right** (`server.py:175-176`) — reasonable, but silent; no warning is surfaced.
- Tool returns are prose strings, not JSON (except `read_readiness`), which blocks programmatic correlation (3.4).

### 4.8 Minor / hygiene

- `Conn.protocol` (`server.py:30`) is set at construction and never read or updated.
- `list_ports` (`server.py:216`) does no filtering despite the docstring hint; it cannot tell you which port MES is using (the registry can).
- No `ATRV` tool despite `send_raw`'s docstring advertising it (`server.py:562`) — battery voltage is a first-class diagnostic on this platform (`GIORGIO_PLATFORM.md` ranks a 100 Hz voltage trace as the top measurement).
- Tests (`obd2-mcp/tests/test_fixes.py`, `test_readiness.py`, 172 lines total) are plain scripts, not pytest, and cover only parsing + the write gate. They do **not** cover the CR injection in 4.1 — `test_fixes.py:56-58` tests `04`, `ATSH 7E0`, `2F0102`, `34`, `ATRV`, `ATDP` but no compound command.

### 4.9 Repo hygiene (non-blocking)

`README.md:21` and `:66` still document `web-ui/`, which was deleted in commit `4ec3686` ("Remove web-ui: cuore reaches parity"); `DIAGNOSTIC_ASSURANCE_FRAMEWORK.md:115-134` also still points at it. Four `mes/` modules that the MCP server imports — `csvlog.py`, `faulttree.py`, `knowledge.py`, `verdict.py` — plus `docs/format/CSV_LOG_FORMAT.md` and `docs/research/DIAGNOSTIC_ASSURANCE_FRAMEWORK.md` are **untracked in git** (`git status` shows them as `??`), so a clone of this repo does not have a working `mes-log-mcp/server.py`.

---

## 5. Knowledge already encoded in `mes/` — do not duplicate

All counts below were produced by importing the package and calling `len()`, not estimated. Package total: 3,579 lines across 10 modules (plus the `fes.py` / `scan.py` / `csvlog.py` parsers).

### 5.1 Master table of every named registry

| File : line | Constant | Exact count | Maps |
|---|---|---|---|
| `modules.py:529` | **`REGISTRY`** | **126** | code -> ModuleInfo |
| `modules.py:537` | **`ALIASES`** | **161** | alias token (upper) -> canonical code |
| `modules.py:546` | `MES_GROUPS` | 11 | MES's own group labels (English.txt 1101-1111) |
| `modules.py:38` / `:54` | `Domain` / `Tier` enums | 11 / 3 | taxonomy + `Tier.rank` |
| `dtc.py:149` | **`_FTB_TABLE`** | **99** | (byte, meaning, source, confidence) |
| `dtc.py:264` | **`FAILURE_TYPES`** | **99** | byte -> FailureType |
| `dtc.py:115` | `FTB_GROUPS` | 10 | first nibble 0-9 -> ISO 14229-1 group name |
| `dtc.py:43` | `NON_DTC_KEYS` | 20 | header keys whose values look like DTCs but aren't |
| `dtc.py:309` | `SYSTEM_NAMES` | 4 | P/B/C/U -> Powertrain/Body/Chassis/Network |
| `dtc.py:53` | `DtcStatus` (+ 6-entry maps at `:75`, `:87`) | 6 | stored/cleared/returned/uncleared/absent/unknown |
| `dtc.py:271` | `MANUFACTURER_SPECIFIC_FROM` | `0xA0` | FTB threshold |
| `knowledge.py:63` | **`BULLETINS`** | **17** (16 distinct DTCs) | TSB / STAR cross-reference |
| `knowledge.py:198` | `EVAP_FAMILY` | 5 | P0440/P0441/P0455/P0456/P1CEA |
| `faulttree.py:304` | **`TREES`** | **2** | 12 steps + 3 verification + 7 do-not rules |
| `params.py:54` | **`_UNIT_CANON`** | **27** | unit spelling -> canonical |
| `params.py:42` / `:46` | `_TRUE_STATES` / `_FALSE_STATES` | 14 / 15 | enum-to-boolean |
| `verdict.py:49` | `_COMPONENT_WARNINGS` | 4 rules / 8 keywords | platform do-not-condemn list |
| `verdict.py:44` / `:45` | `_VERIFIABLE` / `_ATTESTED` | 4 / 1 | citation types |
| `analysis.py:32` | `COMMUNICATION_FTBS` | 5 (2F, 64, 86, 87, 88) | "couldn't talk to something" bytes |
| `analysis.py:36` | `NETWORK_EVENT_MIN_MODULES` | 3 | cascade confidence threshold |
| `analysis.py:94` | `ranked_causes_giorgio` (inline) | **7** | ranked root causes with test + source |
| `workup.py:167` | `blind_spots` (inline) | 3 + 1 conditional | what logs cannot answer + which tool closes it |
| `encoding.py:24` / `:35` / `:40` | `_BOMS` / `_FALLBACKS` / `_ALLOWED_CONTROL` | 5 / 3 / 3 | charset ladder |
| `catalog.py:36` / `:38` | `SETTLE_SECONDS` / `_KIND_LABEL` | 3.0 / 2 | index hygiene |

### 5.2 Module registry (`modules.py`) — 126 modules

Record schema (`ModuleInfo`, `modules.py:74-100`), 9 fields: `code, name, description, domain, tier, giorgio, aliases, source, note`.

- **By domain:** body 21, safety 19, chassis 18, powertrain 17, infotainment 15, electrification 14, climate 11, lighting 5, pseudo 4 (MES procedure pages, not ECUs), network 2.
- **By tier:** informational 52, important 49, critical 25.
- **By provenance (`source`):** `mes-lang` 83, `corpus` 28 (observed in this shop's own logs), `confirmed` 15 (vendor doc).
- **By Giorgio presence:** yes 35, no 29, likely 23, unknown 39.
- Alias resolution handles compound forms (`TCM/NCA/NCR` -> `TCM`) at `modules.py:555`, Italian node names (`NBC` -> BCM, `NFR` -> ABS), and one hard-coded collision fix at `modules.py:587-597` — `CTM` in MES group "climate control" becomes a synthetic `CTM-HEATER` record, disambiguated from the telematics CTM.

**Critically: the registry contains no transport-layer data.** No CAN IDs, no diagnostic/ECU addresses, no ISO-TP addressing, no bus assignment, no capability flags (`INFO|DTC|DTC EX|PRM|ACT|ADJ`), no bus speeds. Bus names appear only as free prose inside `description` (e.g. "B-CAN to C-CAN gateway" at `modules.py:336`). The `iso_code` field seen on DTC/scan objects (`dtc.py:371`, `scan.py:89`) is **MES's printed ECU part identifier read out of log text at parse time**, not an address. Everything the spec's "Module map" and `CONNECTIVITY_AND_SGW.md:188` (FCA body-module CAN ID table) need is genuinely absent.

### 5.3 DTC / failure-type knowledge (`dtc.py`) — 99-entry FTB table

- Structure: `(byte, meaning, source, confidence)`.
- **By source:** `mes-table` 89, `corpus` 10 (printed by a real ECU in this shop's logs — ground truth).
- **By confidence:** `likely` 69, `confirmed` 21, `offset` 9 (sits in a run with one unlocated gap, so may be off by one — flagged rather than asserted).
- **By nibble group:** 0x0N 6 (`:151`), 0x1N 15 (`:157`), 0x2N 14 (`:173`), 0x3N 12 (`:188`), 0x4N 13 (`:201`), 0x5N 4 (`:215`), 0x6N 8 (`:220`), 0x7N 10 (`:229`), 0x8N 9 (`:240`), 0x9N 8 (`:252`).
- Unknown bytes return an **explicitly marked-unknown** `FailureType`, never a guess (`dtc.py:274-305`); >= `0xA0` is declared manufacturer-specific.
- **Prefix math** (`code_authority`, `dtc.py:317-339`) and it is asymmetric: for `P`, 2nd char 0 or 2 = generic, 1 = manufacturer, 3 = jointly defined; for `B`/`C`/`U`, 0 = generic, 1 or 2 = manufacturer.
- **There is no DTC -> description catalog.** Descriptions are echoed verbatim from MES's own output. The only code-keyed knowledge is the 16 codes in `BULLETINS` and the 5 in `TREES`.

Note the duplication risk with `obd2-mcp/server.py:181` `_decode_dtcs`, which implements its own (correct, but separate) ISO 15031-6 two-byte -> Pxxxx decoding. Two decoders, no shared module.

### 5.4 Fault trees (`faulttree.py`) — 2 trees, EVAP only

`Step` (9 fields: `id, title, test, tools, expect, if_abnormal, cost, source, caution`, `faulttree.py:30-53`); `Tree` (7 fields: `key, title, codes, framing, steps, verification, do_not`, `:56-77`).

| Tree | Lines | Codes | Steps | Verification | do_not |
|---|---|---|---|---|---|
| `evap-leak` | 80-219 | P0440, P0441, P0455, P0456 | 7 (E1-E7) | 2 (V1, V2) | 5 |
| `p1cea-boost-purge` | 222-301 | P1CEA | 5 (F1-F5) | 1 (V1) | 2 |

EVAP_LEAK steps: E1 (`:96`) recirculation-line quick-connect; E2 (`:106`) canister filter restriction; E3 (`:117`) KOEO purge/vent actuator tests; E4 (`:133`) refuelling-behaviour interview; E5 (`:145`) purge hose routing; E6 (`:153`) canister flooded with fuel; E7 (`:166`) smoke test. Verification V1 (`:183`) "do not road-test as proof"; V2 (`:192`) SLVT / Mode $06 / readiness + permanent DTC.
P1CEA_FLOW steps: F1 (`:235`) PCM calibration level; F2 (`:244`) EVAP quick-connects at air-cleaner cover; F3 (`:253`) ejector-tee orientation + directional blow test; F4 (`:265`) CAC-duct / air-cleaner port flash; F5 (`:273`) FTP sensor circuits then purge solenoid. Verification V1 (`:285`) confirm under boost via CSV recording.

Two hard-coded VIN-evidence annotation rules in `evaluate()` (`faulttree.py:313-381`): counts COMPLETED "evaporation" actuator runs and attaches the finding to step E3 (`:341-363`); flags `P2422` in the history against step E4 (`:370-378`). Ordering note when both trees match: leak codes fixed and verified before P1CEA.

**Coverage is EVAP-only** — nothing for transmission, chassis, body, network or ADAS, despite the bulletin table and the 7-entry network cause list carrying knowledge in those areas.

### 5.5 Bulletins (`knowledge.py`) — 17 entries

`Bulletin` dataclass, 8 fields: `number, date, title, action, dtcs, applies, caution, superseded_by` (`knowledge.py:32-60`). Entries begin at lines 65, 73, 79, 86, 92, 98, 104, 112, 123, 134, 141, 150, 159, 168, 174, 182, 190.

Numbers: S2125000002, S2125000003, 9100471, 9100469, 9100468, 9100325 Rev 1, 18-048-23, 18-030-17 REV. B, S2621000003 REV. A, S1821000001 REV. A, S2008000078 REV. A, S2008000032, S1808000005, S1708000262 REV. A, S1408000384 REV. J, S2018000004, S2308000004. Grouped EVAP (8) / transmission-AWD (3) / electrical-network (6).

8 of 17 carry DTC lists, covering **16 distinct codes**: P0440, P0441, P0455, P0456, P0716, P0733, P07E4, P1B13, P1B14, P1CEA, P1D90, P1DB2, P1DB7, U0102, U04B1, U113E. Provenance stamped into every `to_dict()`: `docs/reference/TSB_CATALOGUE.md` (NHTSA set, 2026-08-27).

Two family rules in `match_codes` (`knowledge.py:207-249`): >= 2 EVAP-family codes -> one system fault with an ordered clinical sequence (`:222-235`); >= 3 distinct U base codes -> one power/bus event ordered supply -> connectors/grounds -> terminals (`:236-247`).

### 5.6 Analysis heuristics (`analysis.py`)

- **`is_communication_dtc`** (`:39-55`) — `U` always qualifies; `B`/`C` only if the FTB is in `COMMUNICATION_FTBS` **and** the text contains one of 7 hint words. The docstring names the counter-example it protects: `B1176-97` (window riser obstructed) is a genuine component fault on a body module.
- **`detect_network_event`** (`:205-228`) — a module joins the cascade only if **every** code it holds is a communication code; one genuine component fault excludes that module entirely. Returns None below 2 modules; `confidence: high` at >= 3.
- **`ranked_causes_giorgio`** (`:94-193`) — **7 causes**, each with `cause` / `confidence` / `why` / `test`, ordered documented-first: (1) BCM power feed F82 / A901 (FCA STAR S1808000005), (2) inline connector XY201 + grounds G003A/G003B (S2008000032), (3) spread terminals (S1708000262 REV. A), (4) **the diagnostic session itself** — an extended UDS session suppresses broadcasts, (5) BCM water intrusion (recall 18V205000 / U36, all 12,595 MY2018 Stelvio), (6) corroded ground strap — explicitly ranked *below* the documented causes with a negative-evidence note (a sweep of 287 FCA bulletins found none describing a ground strap as a failing part; 13 NHTSA complaints only; test target < 0.1 V drop), (7) failing 12 V battery / IBS (S1408000384 REV. J; "DO NOT BLIND CHARGE"). Plus a `first_test` rule (`:87-93`) — read extended DTC data *before* clearing — and a `caution` (`:194-201`) that a missing-message code names the module that went quiet, not the faulty one.
- **`DtcRecord.chronic`** (`:264-269`) — odometer span >= 1000 km **or** `session_count >= 3`. `session_count` counts distinct **files**, not mentions (`:254-255`).
- **`ClearAssessment`** (`:358-403`) — 4 mutually exclusive verdicts in priority order: `returned` ("fault is live ... strongest evidence short of a scope"), `uncleared` ("on FCA transmissions usually a calibration/self-learn must complete first — the code is a state flag, not a failure"), `cleared + re-read` ("NOT proof of repair" + a drive-cycle `next_step`), `cleared without re-read` ("nothing is known").
- `module_report` (`:420`) groups DTCs by module, enriches via `modules.describe`, flags `all_communication_faults`, sorts by `(Tier.rank, module_code)`.

### 5.7 The evidence gate (`verdict.py`) — four criteria

1. **`demonstrated`** (`:247-278`) — passes on `returned_after_clear`, `chronic`, or `session_count >= 2`. Explicitly fails "seen once then cleared".
2. **`mechanism`** (`:280-290`) — >= 5 words. A part name alone is rejected.
3. **`measurement`** (`:292-306`) — at least one citation reaching `verified` or `attested`. **A `type: "dtc"` cite is hard-rejected** (`:99-103`): "codes select the tree, they do not convict the part."
4. **`disconfirmation`** (`:308-318`) — >= 5 words describing the test that would have exonerated the part.

`_verify_measurement` (`:94-223`) dispatches 6 branches: `dtc` rejected; `manual` attested; `actuator` searched in FES logs for outcome; `freeze_frame` searched by base code; `parameter` substring-matched, returns `ParamSeries.stats()` and **adds a caution when `static` is true** (`:161-193`); `recording_event` via `csvlog.crossings()`, verified only when count > 0. `_next_tree_test` (`:226-231`) names the first step of the first matching tree as the concrete next action.

`_COMPONENT_WARNINGS` (`:49-65`) — 4 platform do-not-condemn rules: purge solenoid / valve (`:50`), gas / fuel / filler cap (`:54`), vent valve (`:57`), canister vs ESIM per TSB 9100469 (`:61`).

### 5.8 Workup (`workup.py`) — 9 assembly rules, no constants

Anchor-VIN inheritance (`:50-55`); **look-behind past the empty post-clear re-read** (`:82-108`, walks backwards to the newest session that actually held DTCs, so post-clear silence never reads as a healthy car); clear assessment; network-event collapse on the latest SCAN; 3-bucket history classification (chronic / returned_after_clear / seen_once); TSB cross-reference over the union of history and open codes; an "already attempted" actuator list; **`blind_spots`** — 3 static + 1 conditional (`:167-185`): readiness since clear -> `obd2.read_readiness`; permanent Mode $0A -> `obd2.read_permanent_dtcs`; on-board leak measurement -> "Mode $06 tool not yet built"; and conditionally, EVAP monitor drive conditions (fuel 15-85 %, cold-start natural-vacuum window).

### 5.9 Parameters and encoding

`params.py`: `_UNIT_CANON` 27 entries (`:54-82`), `_TRUE_STATES` 14 (`:42`), `_FALSE_STATES` 15 (`:46`), `DEGREE` / `OHM` (`:28`, `:29`). Unknown units **pass through untouched** — no guessing (`canonical_unit`, `:85-89`). `ParamValue` preserves MES's exact printed literal in `number_text` so an odometer of 140572.6 never renders as 140573. `ParamSeries.stats()` (`:205-237`) emits min / max / mean / first / last / span / **`static`** / distinct.

`encoding.py`: `_BOMS` 5 entries longest-first (`:24`), `_FALLBACKS` = strict utf-8 -> cp1252 -> latin-1 (`:35`), `_ALLOWED_CONTROL` = tab / LF / CR (`:40`). Control-byte stripping is kept deliberately separate from decoding, with the count reported; multi-byte-safe truncation trims a trailing replacement character rather than emitting it (`:126-144`).

### 5.10 What is genuinely NOT in `mes/` — safe to build without duplication

1. **No CAN IDs, ECU/diagnostic addresses, ISO-TP addressing, bus assignments, protocol IDs, or baud rates.** Verified by grep for `0x7xx`, `18DA`, `isotp`, `arbitration`, `tester`, 11-bit, 29-bit — zero hits.
2. **No DTC -> description catalog.** Only 16 codes have bulletin entries and 5 have fault trees.
3. **No OBD-II PID table and no Mode $01/$06 mapping.** OBD-II appears only as prose referrals to the `obd2` MCP server (`workup.py:169,171,174,177`; `faulttree.py:195,197,199`).
4. **No parameter-name canonicalisation or synonym table.** Only unit canonicalisation (27 entries) plus case-insensitive / substring lookup in two places (`dtc.py:399`, `verdict.py:177`).
5. **No known-good / expected-range data** for any parameter.
6. **No module capability flags, licence gating, or bus reachability** — the spec's module map and `MES_INTEGRATION_SURFACE.md`'s capability-matrix ingestion both need this and neither exists.
7. **No SGW model, no VIN build-date decode, no UDS NRC decoder.**
8. **No persistence layer** — no database, no `Recording` / `Event` / `Procedure` tables.

---

## Three things to put at the top of the design document

1. **The cheapest big win is a log tailer + MES process/registry poller.** `FES_LOG_FORMAT.md:271` establishes that MES flushes an operation banner *before* the operation and the outcome *after*, and `HKLM\SOFTWARE\Multiecuscan\Last Selection` / `Recent Vehicles` are live session state that is already world-readable. Together those give a genuine ~1-3 s view into a running MES session with no new hardware, no elevation, and no risk of touching the car — and the existing `Catalog` already handles mid-write files (`catalog.py:180`). Nothing in the repo does this today.
2. **`obd2-mcp/server.py` needs a security pass before it is extended, not after.** The carriage-return command-injection bypass (4.1) and the ST-command hole (4.2) both defeat the write gate entirely; three of four DTC-read tools can report "(none)" on a bus error (4.3); the port-lifetime model is the opposite of the designed interlock (4.5). Any UDS / ISO-TP / Mode-$06 work builds directly on top of all four.
3. **The correlation seam already exists and is one enum away.** `verdict._VERIFIABLE` (`verdict.py:44`) accepts four corpus-backed citation types. Adding `live_readiness`, `live_permanent` and `mode06` as verifiable types — with a persisted observation record so they can be cited later — turns the evidence gate from a log-only instrument into the join point between MES history and live car state, which is the thing every other proposal in `COMPANION_APP_SPEC.md` ultimately needs.
