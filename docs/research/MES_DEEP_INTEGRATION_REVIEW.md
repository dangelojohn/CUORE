# Deep review: Claude Code <-> MultiEcuScan <-> Stelvio

**Date:** 2026-09-14  
**Scope:** every existing connection between Claude Code, the two MCP servers, MultiEcuScan (MES) 5.4 and the car, plus the deeper options for control and communication that are actually available on this bench.  
**Method:** direct inspection of this machine (MES install, registry, processes, window tree, adapter probe over USB only), a line-by-line review of `mes-log-mcp`, `obd2-mcp` and `cuore`, and sourced web research. Three long-form supporting reports are in `docs/research/review-2026-09-14/`.  
**Safety posture during the review:** the adapter was never plugged into the car. Only identification and configuration-read commands were sent to it over USB, and the COM port was released afterwards.

---

## 0. Executive summary

1. **MES has no automation surface, and that is now settled by evidence, not assumption.** No command-line switches, no IPC, no sockets, no COM/DDE, no plugin model. The binary is .NET 2.0 WinForms packed with .NET Reactor; the EULA forbids decompilation. Every MES connection is ELM/ST text over one exclusive COM port.
2. **Two findings close doors the current docs left open.** MES runs **elevated (High integrity)**, so UI Automation from a normal process sees only the title bar. And MES **writes each session log once, at disconnect** (file creation time equals last-write time for a 171 KB, 4m45s session), so no file watcher can stream a session live. The best achievable latency is "complete session, seconds after the technician disconnects".
3. **The adapter is more capable than the toolchain assumes.** COM3 is a **Vgate vLinker FS r2 with an STN1170 v4.3.2** chip, not an OBDLink SX. The STN1170 has HS-CAN, MS-CAN and SW-CAN transceivers, raw-CAN monitoring, hardware filters, ISO-TP segmentation, periodic messaging and batched commands. Giorgio's CAN-IHS body bus sits on OBD pins 3/11 at 125 kbps, which is exactly the STN1170 MS-CAN mapping. That means a Claude-driven server could plausibly reach the BCM/IPC/HVAC bus that MES needs the blue A5 cable for.
4. **The existing OBD server is registered at the wrong baud and shares its port with MES and with itself.** `OBD_BAUD=38400` returns garbage from this adapter; it needs 115200, which is what MES's own registry settings use. Three separate `obd2-mcp` processes were alive at once (one per open Claude session), and COM3 became busy mid-review with MES still showing "Disconnected".
5. **The biggest leverage is not in MES at all.** It is in (a) a native UDS/ISO-TP client over the STN chip, (b) passive CAN capture that works even with the Security Gateway locked, (c) a session-completion watcher that hands Claude every MES session the moment it lands, and (d) a correlation layer that lets live car data enter the evidence gate as verifiable citations.

---

## 1. Existing connections, as they actually are

### 1.1 `mes-log` MCP server (28 tools)

- Pull-based only. Every tool call re-scans the log roots; nothing runs between calls, there is no watcher, and `watchdog` is not a dependency.
- Roots come from env vars or the hard-coded install directory. It never reads MES's registry to confirm where MES actually writes.
- Parsers are solid: 97/97 logs parse clean, path containment is enforced after `resolve()`, half-written files are flagged for 3 s and not cached.
- The CSV recording path has **never been exercised on this install**. Zero CSV recordings exist; the parser is validated against synthetic fixtures only.
- Parameter blocks in `.txt` logs carry no per-sample timestamps. Only four corpus files contain any parameter blocks at all.
- Knowledge already encoded (do not duplicate): 126-module registry with 161 aliases, 99-entry failure-type table, 17 bulletins covering 16 DTCs, two EVAP fault trees, 27 unit canonicalisations, a 7-cause Giorgio network-event ranking, the four-criterion evidence gate. It holds **no** CAN IDs, ECU addresses, bus assignments, PID formulas, expected ranges, SGW model or UDS negative-response decoder.

### 1.2 `obd2` MCP server (13 tools)

- Generic ELM327 Modes 01/02/03/04/07/09/0A plus a good readiness decoder. **No UDS, no ISO-TP, no CAN monitoring, no ST-command support, no Mode $06.**
- Init sequence is `ATH0` + `ATSP0`: headers off, auto protocol. That is the wrong baseline for anything multi-ECU and is the opposite of what `COMPANION_APP_SPEC.md` specifies.
- Holds the serial port for the life of the process. The spec calls for lazy per-operation open.
- Write gate defects found during review (details in appendix A, section 4):
  - a carriage return embedded in `send_raw` sends a second, unclassified command (`ATI\r04` clears codes);
  - `ST` commands are neither `AT` nor hex, so they fall through the gate unguarded, including `STPX` which is an arbitrary CAN transmit;
  - `adapter_error()` is not applied in `read_pending_dtcs`, `read_permanent_dtcs`, `read_pid`, `read_vin` or `send_raw`, so a bus error prints "(none)";
  - `clear_dtcs` captures no evidence first, checks no vehicle speed, and does not read back the result.
- Returns prose strings rather than JSON, unlike `mes-log`, which blocks programmatic correlation.

### 1.3 `cuore` companion service

HTTP mirror of the `mes` library. All live capabilities (`live_obd`, `live_can`, `drive_recorder`, `actuators`) report `False`. `websockets` is installed but unused. No persistence layer.

### 1.4 `stelvio_scan` (Documents folder, separate project)

A PySide6 suite with implemented UDS services 0x10/0x19/0x22/0x27/0x31, ISO-TP framing, a 29-bit Giorgio address table and session recording. It has **never touched hardware**. Its UDS and addressing code is directly reusable for the options in section 3.

### 1.5 MCP registration and process hygiene

- Both servers are registered globally in `~/.claude.json` under `mcpServers`, launched from the repo `.venv`.
- `obd2` is registered with `OBD_PORT=COM3`, `OBD_BAUD=38400`. **38400 is wrong for this adapter.**
- Twelve Python processes were running: three `obd2` servers and three `mes-log` servers (each wrapped by a venv launcher), belonging to three concurrent Claude sessions. Any one `obd2` instance can take COM3 and block the others and MES.

### 1.6 The adapter on COM3, verified over USB

| Probe | Reply |
|---|---|
| `ATI` | `ELM327 v2.3` |
| `STI` | `STN1170 v4.3.2` |
| `STDI` | `vLinker FS r2` |
| `STMFR` | `Vgate.com.cn` |
| `STSN` | serial recorded in memory |
| `ATRV` | `--.-V` (USB power only, not on the car) |
| `STPRS` | `AUTO [AT]` |
| `STSLCS` | ELM327 control mode, UART sleep after 1200 s |
| USB bridge | FTDI FT-X, VID 0403 PID 6015 |
| Working UART speed | **115200** (38400 returns framing garbage) |

MES's registry agrees: `Interface 0 Type Ex = 7`, `Port = COM3`, `Speed = 115200`.

### 1.7 MES 5.4 facts established on this machine

| Fact | Evidence |
|---|---|
| .NET 2.0 WinForms, AnyCPU, runs as 64-bit | CLI header, `IsWow64Process` false |
| Obfuscated with .NET Reactor, string literals encrypted at rest | `SuppressIldasmAttribute`, 21 literals in a 4.3 MB assembly, Reactor fingerprints |
| Imports only `kernel32` and `user32`; no J2534, no FTDI D2XX | P/Invoke names cannot be obfuscated |
| Talks to adapters only via `SerialPort` or `TcpClient` | `#Strings` heap references |
| **Runs elevated (High integrity)**, all three instances | token integrity check |
| Settings live in `HKLM\SOFTWARE\Multiecuscan` (64-bit view), not HKCU, not AppData | direct read; `BUILTIN\Users` has ReadKey only |
| `LOG Folder = .`, `Export Folder = .`, `CSV Separator = Tab` | registry |
| `Last Selection` and `Recent Vehicles` are live, world-readable session state | registry |
| No listening sockets, no serial port held while "Disconnected", no open log handles | `Get-NetTCPConnection`, `SerialPort.Open`, `FileShare.None` probes |
| **Logs are written once at disconnect** | creation time = last-write time on every large session log |
| No command line, no scripting, no API in the 63-page guide | full-text search |
| UI Automation exposes only the title bar from a Medium-integrity process | pywinauto UIA and win32 backends both blocked |
| `Files\data0*.dat` are encrypted (entropy 7.0 to 8.0 bits/byte) | measured, not decrypted |
| EULA forbids reverse engineering, decompilation and disassembly | `EULA.rtf` |

---

## 2. Hard limits: what MES will never give Claude

| Wanted | Verdict | Why |
|---|---|---|
| Live parameter stream from MES | **No** | CSV is written on stop; `.txt` is written on disconnect; grid cells are owner-drawn with no HWND and UIA is blocked by integrity level |
| Trigger MES actions (connect, scan, actuator) | **No, and should stay no** | Input injection into a High-IL window is blocked; even if elevated, autonomous writes on a live bus violate the toolchain's own safety policy |
| Command-line or IPC control | **No** | Does not exist |
| MES's vehicle database (ISO codes, parameter IDs, procedures) | **No** | Encrypted, EULA-protected. Only `Lang\English.txt` and `English.dat` are readable |
| SGW unlock through MES | **No** | MES states it cannot; AutoAuth requires an OE-approved tool |

---

## 3. The deeper options, ranked

Tier A costs nothing and is safe. Tier B is where the new capability is. Tier C needs hardware or a licence.

### Tier A: free, safe, do first

**A1. Read MES's registry instead of guessing.** Port, speed, interface type, LOG/Export folders and CSV separator are all in `HKLM\SOFTWARE\Multiecuscan` and readable without elevation. `mes-log` should derive its roots and separator from there; `obd2` should derive port and baud from there. `Last Selection` and `Recent Vehicles` give a "what is MES looking at" signal for free.

**A2. Session-completion watcher.** A `FileSystemWatcher` on the log folder fires the moment MES flushes a session. Wire it to `analyze_session` or `workup` automatically and surface the result to Claude as an MCP notification or resource change. Latency is seconds after disconnect. This is the closest thing to "Claude watching over the technician's shoulder" that is physically possible.

**A3. MES liveness probe.** Process presence plus the read-only window-text of the status label (`Disconnected` / `Connected`) survives the integrity boundary. Use it as the port interlock: the OBD server refuses to open COM3 while MES reports connected.

**A4. Port arbitration.** Lazy per-operation open and close, an advisory lock file with pid and purpose, and a single-instance guard. Three `obd2` processes were alive at once during this review; that alone explains a busy COM3.

**A5. Fix the OBD server before extending it.** Baud from registry (115200), `ATH1`, pin the protocol after detection, JSON returns, `adapter_error()` on every tool, reject embedded CR/LF in `send_raw`, classify `ST` commands (allowlist reads such as `STI`, `STDI`, `STPRS`, `STSLCS`; gate `STPX`, `STP`, `STBR`, `STWBR`, `STCMM`), and make `clear_dtcs` capture DTCs plus freeze frames plus readiness before clearing and read back after.

**A6. Move LOG and Export folders out of Program Files.** A one-time admin registry edit by the user. It removes the reason MES needs elevation for logging and makes watching robust.

**A7. Exercise the CSV path once.** One real recording validates the whole `csvlog` parser and settles the four `UNCONFIRMED` format questions. `FES_Templates.ini` (parameter-ID slots 0-9) and `FES_Tags.ini` (tag text slots 0-9) are the only writable MES config and can pre-program a recording plan for the technician.

**A8. Ship the decode tables and use simulation mode.** `Lang\English.txt` and `English.dat` (6,326 strings: data, enum, DTC) are plain and legal to read. MES's Ctrl+F10 simulation mode is a no-car harness for enumerating what each module exposes.

### Tier B: new capability through the vLinker FS

**B1. Native UDS/ISO-TP client over the STN chip.** Giorgio uses ISO 15765 29-bit normal-fixed addressing on CAN-C at 500 kbps: request `18DA<TA>F1`, response `18DAF1<TA>`, functional `18DB33F1`. On the STN1170 that is `STP 34`, `ATSH 18DA10F1`, `STCFCPA 18DA10F1,18DAF110`, `STCSEGR 1`, `STCSEGT 1`. Community target addresses: ECM `10`, TCM `18`, BCM `40`, IPC `60`, steering `2A`, RF hub `C7` (the last one is reported to trip the immobiliser on cars with a BACCAble board; avoid). Reuse `stelvio_scan`'s UDS layer, or `udsoncan` on top of `python-can-isotp` with custom `rxfn`/`txfn` bound to `STM` and `STPX`. Use `STPPMA` for TesterPresent and `STBC 1` to batch setup commands into one round trip. Read-only services first: `0x22`, `0x19`, `0x10 01`, `0x3E`. Note the engine ECU is a **Magneti Marelli IAW 10JA**, not a Bosch MED17, so MED17 DID maps do not apply.

**B2. Reach CAN-IHS without the blue cable.** `STP 54` selects ISO 15765 29-bit at 125 kbps on the MS-CAN transceiver, which the vLinker FS wires to pins 3/11. Giorgio's CAN-IHS is on pins 3/11 at 125 kbps. If this works, Claude can reach BCM, IPC, HVAC and uConnect over a bus MES cannot reach without the A5 harness. Unknowns to verify on the car: whether the vLinker's auto-switch firmware overrides manual `STP`, and whether `STFPA` or legacy `STFAP` filter spelling is accepted on firmware 4.3.2. CAN-CH on pins 12/13 has no STN transceiver mapping; the grey A6 cable stays mandatory for ABS/ESC.

**B3. Passive CAN capture.** `STCMM 0` (receive only, no ACK) plus `STM` or `STMA` with `STFPA` pass filters and `STBR` raised toward 2 Mbps. The adapter never transmits, so it works with the Security Gateway fully locked and is the safest item in this document. Feed frames through `cantools` with the opendbc Giorgio DBC (PR 1251) or the repo's own `fca_giorgio.dbc` notes; `0x0F1` is the 100 Hz voltage signal the platform research ranks as the single most valuable measurement. Budget for `OUT OF MEMORY` from filter allocation.

**B4. Mode $06.** Iterate MIDs and apply ISO 15031-5 scaling. Named across the existing docs as the highest-value unbuilt read; reachable today through `send_raw` once the gate is fixed.

**B5. Correlation layer.** Shared VIN identity, a common time base, a parameter-name synonym table mapping MES names to PIDs and DIDs, and a small persistence store. Then add `live_readiness`, `live_permanent`, `mode06` and `uds_did` as verifiable citation types in `mes/verdict.py` so a live measurement can convict a part instead of merely being attested. This is the single highest-leverage code change in the repo.

**B6. Server shape.** Either extend `obd2` or replace it with a `giorgio` server built on the tool taxonomy of `mcp-can` (frames, decode, OBD, UDS) and the safety model of `obd-mcp-server` (read-only by default, allowlisted operations, loopback-only HTTP, VIN pseudonymised). Add MCP resources for the latest session and recording, and MCP notifications from the watcher in A2. Expose `cuore` as streamable HTTP so the phone Claude app can reach the bench. Use `ELM327-emulator` plus a virtual COM pair as the no-car CI harness.

### Tier C: hardware or licence

- **C1. Grey A6 cable** for CAN-CH (ABS, ESC, dampers). Cheap and required regardless.
- **C2. CANtieCAR** multiplexed interface: all three buses without cable swaps. Only worth it if B2 fails.
- **C3. Security Gateway bypass** (module replacement, behind the instrument cluster on the Stelvio, or a 12+8 adapter). Unlocks every write path for MES and for any server. Highest-risk item here: warranty friction, removes the CAN firewall, and body/PROXI writes can immobilise the car. Not compatible with 2021+ cars where the SGW is inside the BCM.
- **C4. Second adapter on a Y-splitter** so MES and Claude can co-exist. Electrically fine on CAN; keep the Claude side in `STCMM 0` so only one node ACKs.

### Rejected after testing

| Option | Why not |
|---|---|
| UI Automation of the MES grids | Blocked by UIPI; would require running the MCP server elevated, and .NET 2.0 `DataGridView` exposes little even then |
| Sending keystrokes or window messages to MES | Blocked from Medium integrity; and autonomous Connect/Scan/Clear on a live bus is unsafe by policy |
| Screen capture plus OCR | Fragile; only fallback if the user explicitly wants live grid values and accepts the cost |
| Decompiling, unpacking, decrypting `data0*.dat`, memory scraping | EULA prohibits it; binary carries anti-debug |
| Command-line switches | None exist; discovery would require decompilation |
| python-can STN backend | Does not exist; use `can-isotp` custom rx/tx instead |

---

## 4. MCP connectivity: concrete changes

1. **`~/.claude.json`**: change the `obd2` env to `OBD_BAUD=115200`, or better, drop the env and let the server read port and speed from `HKLM\SOFTWARE\Multiecuscan`.
2. **One server instance per adapter.** Either make `obd2` single-instance via a lock file, or move the live link into `cuore` as the one process that owns the port and let every Claude session reach it over HTTP.
3. **Notifications and resources.** The watcher in A2 should publish `resources/list_changed` and a log-level notification when a session lands, so Claude does not have to poll.
4. **Tool returns as JSON everywhere.** `obd2` is the outlier.
5. **Remote reach.** `cuore` over streamable HTTP with a token lets the phone Claude Code app drive the bench from the driver's seat, which is the only way to combine a road test with Claude's analysis.
6. **Registration hygiene.** The `mes` modules `csvlog.py`, `faulttree.py`, `knowledge.py`, `verdict.py`, `workup.py` and four test files are untracked in git; a fresh clone would not run the server.

---

## 5. Verifications that need the car and the owner present

Each is a five-minute read-only test. None writes to any module.

1. `ATRV` on the car to confirm bus power, then `STP 34`, `STPO`, `ATSH 18DA10F1`, `22 F190` (VIN DID) to prove the UDS path to the ECM.
2. `STP 54`, `STPBRR`, `STPO`, `STCMM 0`, `STM 50` to see whether CAN-IHS traffic appears on pins 3/11 without the blue cable.
3. `STFPA 7E8,7FF` versus `STFAP 7E8,7FF` to learn which filter spelling firmware 4.3.2 accepts.
4. One MES CSV recording with tags, to validate `csvlog.py` and the `FES_Tags.ini` hypothesis.
5. Mode $06 MID availability on the IAW 10JA.
6. Whether the vLinker's auto-switch overrides manual `STP` selection.

---

## 6. Safety policy carried forward

- Claude never holds a write tool. Read-only services and passive monitoring only, unless the owner initiates a specific write with the car stationary and the evidence captured first.
- The OBD server must refuse to open the port while MES reports connected, and must release it after every operation.
- Anything that reaches CAN-IHS or CAN-CH is body and chassis territory. Sniff first, transmit later, and never transmit on those buses without a per-command confirmation.
- Simulation-mode output must be detected and refused as evidence.

---

## Appendices (in `docs/research/review-2026-09-14/`)

- **A. Codebase review** (`codebase_review.md`): every existing connection with file and line citations, the unbuilt roadmap, `obd2` defects, and the full inventory of knowledge already in `mes/`.
- **B. MES binary and runtime analysis** (`mes_binary_analysis.md`): assembly facts, settings storage, UIA test results, data-file entropy, log-flush timing, EULA clauses.
- **C. Web research** (`web_research.md`): MES automation and adapter support, Security Gateway, the full STN1170 command reference for this work, Giorgio addressing and DIDs, Python libraries, open-source Giorgio projects, existing automotive MCP servers, with sources.
