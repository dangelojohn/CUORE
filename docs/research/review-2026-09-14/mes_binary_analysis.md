# MultiEcuScan 5.4.0.0: automation and integration surface analysis

Read-only investigation performed 2026-09-14 on this machine. Nothing was clicked, closed or modified. Scripts and raw extractions are in `C:\Users\User\AppData\Local\Temp\claude\` (`mes_meta.py`, `mes_probe.py`, `mes_uia3.py`, `mes_strings.txt`, `mes_strings_heap.txt`, `mes_us_heap.txt`, `mes_guide.txt`, `mes_uia_tree.txt`).

## 1. .NET assembly facts

Obfuscated: yes, heavily.

| Fact | Value |
|---|---|
| `ImageRuntimeVersion` | `v2.0.50727` (.NET Framework 2.0/3.5 CLR) |
| Metadata streams | `#~` 71,244 B, `#Strings` 49,460 B, `#US` 1,248 B, `#GUID` 32 B, `#Blob` 24,292 B |
| PE Machine | `0x014c` (I386) |
| CLI flags | `0x1` = ILONLY only; `32BITREQUIRED` is not set |
| Strong name | Not signed (`PublicKeyToken=null`); Authenticode-signed via Sectigo |
| Assembly | `Multiecuscan, Version=5.4.0.0, ProcessorArchitecture=MSIL`, FESSoft Ltd. |

The process is 64-bit, not 32-bit: ILONLY without 32BITREQUIRED means AnyCPU, and `IsWow64Process` returned False for PID 2372. The venv's 64-bit Python 3.10 is the correct bitness.

Obfuscation markers: `ObfuscationAttribute`, `SuppressIldasmAttribute`, `AllowPartiallyTrustedCallersAttribute` in `#Strings`; 70.1 % of the 4,438 `#Strings` entries are 3 characters or shorter and 3,120 are non-ASCII; the `#US` heap holds only 21 literals for a 4.3 MB assembly, so string literals are encrypted at rest and decrypted at runtime (`RijndaelManaged`, `CryptoStream`, `AesCryptoServiceProvider`, `MD5CryptoServiceProvider` referenced). Surviving `#US` literals are the .NET Reactor fingerprint (`{11111-22222-10009-11112}` and siblings).

Reflection-based type enumeration is pointless because names are Unicode garbage. Do not attempt deobfuscation (see section 6).

### String extraction

`mes_strings.txt` (65 KB) contains only 67 unique UTF-16LE runs of 6+ characters in 4.3 MB, all certificate and manifest boilerplate. Zero hits for ELM, STN, OBDLink, J2534, KKL, Simulation, PROXI, TCP ports, FESLog, SCAN, csv, or any product URL. Only URLs are Sectigo/Comodo CRL/OCSP endpoints plus `www.multiecuscan.net` and `http://forum.multiecuscan.net` from the embedded EULA RTF resource. No update-server or licence-server URL is statically present.

The informative extraction is the `#Strings` heap, whose external references cannot be encrypted:

| Area | Every reference found |
|---|---|
| Serial | `SerialPort`, `GetPortNames`, `set_BaudRate`, `get_BytesToRead`, `get/set_ReadTimeout`, `set_WriteTimeout`, `set_RtsEnable` |
| Network | `TcpClient`, `NetworkStream`, `Socket`, `System.Net.Sockets`, `IPAddress`, `GetIPProperties`, `GatewayIPAddressInformation` |
| P/Invoke modules | `kernel32.dll` and `user32.dll` only |
| Registry | `Registry`, `RegistryKey`, `OpenSubKey`, `GetValue`, `SetValue`, `RegistryValueKind`, `LocalMachine` |
| Files | `StreamWriter/Reader`, `FileStream`, `get_StartupPath`, `get_ExecutablePath`, `GetFolderPath`, `SpecialFolder` |
| PDF | `PdfSharp.Pdf`, `PdfDocument`, `PdfPage`, `XGraphics`, `PdfFontEmbedding` |
| UI | 30 `DataGridView*` types, `SysTabControl`, `ToolStripMenuItem`, `RichTextBox`, `MenuStrip` |
| Anti-tamper | `OpenProcess`, `ReadProcessMemory`, `WriteProcessMemory`, `VirtualProtect`, `GetCurrentProcess` |

Consequences: there is no J2534, FTDI D2XX or vendor-DLL P/Invoke, so every adapter is reached as a serial COM port or a TCP socket (the user guide confirms: all interfaces have a COM port number). The anti-debug primitives mean attaching a debugger or scraping process memory risks tripping countermeasures. `GetCommandLineArgs` exists but no switches are documented anywhere and none survive as plaintext.

## 2. Settings storage

Found at `HKEY_LOCAL_MACHINE\SOFTWARE\Multiecuscan` in the native 64-bit view (not `WOW6432Node`). `HKCU\Software\Multiecuscan` holds only `installed=1`. Nothing in `%LOCALAPPDATA%`, `%APPDATA%`, `VirtualStore`, isolated storage or any `user.config`.

```
Interface 0 Type Ex : 7        Interface 0 Port : COM3   Speed : 115200
Interface 1 Type Ex : 7        Interface 1 Port : COM3   Speed : 115200
Interface 2 Type Ex : 0        Interface 2 Port : COM5   Speed : 115200
Interface 3 Type Ex : 0        Interface 3 Port : COM1   Speed : 38400
Interface 4 Type Ex : 0        Interface 4 Port : COM1   Speed : 38400
Show Available Ports Only : 1  Show Adapter Message : 1   High Latency mode : 0
KWP2000 Timings : 0            Screen Repaint Interval : 1  Show Disclaimer : 8
Convert KMs to Miles : 0       Convert C to F : 0   BAR to PSI : 0   KG to LB : 0   MM to IN : 0
UI Language : English          Data Language : English
CSV Separator : Tab
Export Folder : .              LOG Folder : .
Parameter Color 1..20, Graph colours, fonts, line thickness
Lic Number : [redacted]        Lic Number M / D : empty   Removal Key : empty
Last Selection : 10622
Recent Vehicles : (695),(757),(646),(694);(106),(101),(100),(103),(106),(102),(99),(113),(104),(104),(104),(93),(490)
```

Implications: `Export Folder` and `LOG Folder` are both `.`, resolved against the application start-up path, which is why every log lands in `C:\Program Files (x86)\Multiecuscan\`. Changing these two values to a user-writable folder is the cleanest integration lever, needs admin, and is a user action. `CSV Separator` is Tab. `Interface Type Ex = 7` on COM3 at 115200 is the vLinker FS (confirmed separately by probing the adapter). The settings key names map 1:1 onto UI labels in `Lang\English.txt` ids 8101 to 8132; id 8110 is the WiFi interface IP and port field (`192.168.0.10:35000` example), which is the `TcpClient` path, and no WiFi interface is configured.

## 3. UI Automation feasibility: blocked by UIPI

All three MES processes run at High integrity (elevated). The Claude Code session runs at Medium.

- pywinauto `backend="uia"` and the `uiautomation` package see only `Dialog 'Multiecuscan 5.4 REGISTERED'` with a `TitleBar` child. pywinauto warns that the Python process has no rights to make changes in the target GUI.
- pywinauto `backend="win32"` throws `AccessDenied` (`VirtualAllocEx` into a High-IL process).
- Raw `EnumChildWindows` plus `GetWindowTextW` does survive the boundary, read-only. The main window has 34 descendant HWNDs: 15 `WindowsForms10.Window`, 9 `STATIC`, 5 `BUTTON`, 4 `SCROLLBAR`, 1 `SysTabControl32`. Fourteen return text, including the live connection status (`Disconnected`), hidden banners (`WARNING: Invalid ISO code for selected vehicle system!`, `Loading ...`), and the top-level buttons (`Connect`, `Scan`, `Simulate`, `Settings`, `Register`, `Model/Version`, `Make`, `Control Module`, `System`).
- The live-parameter grid and DTC list are not readable by any available means: no `ValuePattern`, `TablePattern` or `GridPattern` is exposed, and `DataGridView` cells are owner-drawn with no per-cell HWND, so `WM_GETTEXT` has no target. No `SysListView32` exists.

To make UIA work at all the MCP server process would have to run elevated too. That is a user decision. Even elevated, .NET 2.0 `DataGridView` support is partial; expect `LegacyIAccessible` at best.

## 4. Data files and user guide

### `Files\data01..06.dat`

| File | Size | Entropy (head 2 MB) | Entropy (tail 200 KB) | First bytes |
|---|---|---|---|---|
| data01.dat | 37,563,930 | 7.929 | 7.728 | `65 5a d1 d8 99 4d 31 b2` |
| data02.dat | 6,758,884 | 7.058 | 6.995 | `00 22 38 3e 3e 1a 0c 80` |
| data03.dat | 34,394,310 | 7.028 | 7.081 | `01 66 79 79 66 b6 12 00` |
| data04.dat | 45,812 | 7.860 | 7.860 | `00 27 01 26 35 2b 08 2d` |
| data05.dat | 1,121,352 | 8.000 | 7.999 | `5e d7 4e d4 d1 51 59 9c` |
| data06.dat | 1,185,849 | 8.000 | 7.999 | `83 b0 f8 04 5a db 01 bb` |

No magic bytes, no ZIP/GZIP/CAB header. data05 and data06 at a flat 8.000 bits/byte are indistinguishable from random, so block-encrypted. No decryption attempted. These hold the vehicle, ECU and parameter catalogue and the interface-type enum.

`Lang\English.txt` is plain key=value (534 lines) and `English.dat` a 437 KB binary companion. Both are legal to read and already used by `mes-log-mcp`.

### `Multiecuscan User Guide.pdf` (63 pages, 2012)

- Supported interfaces: KL (VagCom 409), ELM327 1.3 or newer, OBDKey 1.40, OBDLink, ELM Scan 5, CANtieCAR. All have a COM port number. ELM327 v1.3 at 38400, OBDKey at 9600. FTDI latency timer must be set to minimum.
- Logging: settings items 9 to 11 are CSV separator, CSV folder, LOG folder; "the folder must exist". Recording: a new CSV file per recording, written automatically when recording stops. Error monitoring writes DTCs into the CSV. CSV import and export via keys `I` and `E`.
- PROXI alignment: worked example pp. 55 to 60. ELM327/OBDKey/OBDLink are "not recommended for special functions (PROXI alignment, remote control programming, IMA coding)".
- Simulation mode: Ctrl+Connect or Ctrl+F10; string id 1207 = `SIMULATION MODE!!! THE DATA IS NOT REAL!!!`. Any scraper must detect this banner.
- Command line options: none. Scripting or automation: none. Keyboard shortcuts are the only vendor-exposed control surface: F10 connect/execute/clear/record, F11 scan and disconnect, F12 scan DTC, F9 settings, F7 adjustments, Ctrl+F10 simulate, E/I export/import CSV, T tags panel.
- Telemetry: a "Send Report" button uploads the last connection's raw bus traffic to the vendor. User-initiated only.

## 5. Runtime behaviour

- No sockets: `Get-NetTCPConnection` and `Get-NetUDPEndpoint` return nothing for the three PIDs.
- No serial port held while the status label reads `Disconnected`: `SerialPort("COM3", 115200).Open()` succeeded from this session at that moment.
- No file handles on the log directory: every recent log opened with `FileShare.None`.

### Logs are written once, at disconnect

| File | Size | CreationTime | LastWriteTime | Header timestamp (session start) |
|---|---|---|---|---|
| `FESLog_2606071008_...Stelvio...` | 171.4 KB | 06/07 10:08:33 | 06/07 10:08:33 | 6/7/2026 10:03:48 |
| `FESLog_2510150207_...Stelvio...` | 119.6 KB | 10/15 02:07:11 | 10/15 02:07:11 | 10/14/2025 21:56:37 |
| `FESLog_2510271230_...Stelvio...` | 12.3 KB | 10/27 12:30:09 | 10/27 12:30:09 | 10/27/2025 10:56:06 |
| `FESLog_2509241345_...Stelvio...` | 5.6 KB | 09/24 13:45:46 | 09/24 13:45:46 | 9/24/2025 10:58:07 |

A 171 KB log covering a 4m45s session was created and last written in the same second; a 119 KB log covering 2h10m likewise. MES buffers the session and flushes once on disconnect. The filename stamp is the flush time; header line 2 is the session start. A file watcher delivers a complete session immediately after the user disconnects, never mid-session.

## 6. EULA

`EULA.rtf` (2012), verbatim clauses that bind this work:

> "Limitations on Reverse Engineering, Decompilation, and Disassembly. You may not reverse engineer, decompile, or disassemble the SOFTWARE PRODUCT, except and only to the extent that such activity is expressively permitted by applicable law notwithstanding this limitation."

> "Separation of Components. The SOFTWARE PRODUCT is licensed as a single product. Its component parts may not be separated for use on more than one computer."

Also: single-computer use, no rental, no transfer, unregistered copies freely distributable, all warranties disclaimed. There is no clause prohibiting automation, UI scripting, or reading the program's own output files. Do not deobfuscate, unpack the .NET Reactor layer, decrypt `data0*.dat`, or dump process memory. Three simultaneous instances sit awkwardly with the "run one copy" clause, and MES is elevated, so anything automated inherits admin authority over a live vehicle bus.

## Ranked integration approaches

| # | Approach | Feasibility | Risk | Verdict |
|---|---|---|---|---|
| 1 | File-watch and parse FESLog/SCAN/CSV | High, proven | Very low | Do it; complete session on disconnect |
| 2 | Read `HKLM\SOFTWARE\Multiecuscan` | High, proven | Very low (read) | Do it; auto-discover port, speed, folders, separator |
| 3 | Relocate LOG and CSV folders out of Program Files | High | Low; user does one admin edit | Recommend |
| 4 | Parse `Lang\English.txt` / `English.dat` | High | None | Already used; keep |
| 5 | Win32 window-text polling of the 34 HWNDs | Medium, shallow | Low | Liveness and state signal only |
| 6 | Independent adapter use on COM3 while MES is disconnected | High | Medium, mutually exclusive with MES | Gate on the status label from 5 |
| 7 | UIA scripting of the grids | Low, blocked | Medium | Requires elevated server; still partial |
| 8 | Window-message or keystroke driving | Very low | High | Rejected |
| 9 | Screen capture plus OCR | Medium | Medium-high | Last resort; must detect the simulation banner |
| 10 | Command line, IPC, plugin API | Zero | n/a | Does not exist |
| 11 | Deobfuscation, data-file decryption, memory scraping | n/a | Prohibited | EULA and anti-debug |
