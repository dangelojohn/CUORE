# Deep-dive: control & comms options for Stelvio 2.0T (Giorgio, 2018+, SGW) diagnostics

**Hardware correction applied.** The COM3 adapter is a **Vgate vLinker FS (USB)** — `STI` → `STN1170 v4.3.2`, `STDI` → `vLinker FS r2`, `STMFR` → `Vgate.com.cn`, `ATI` → `ELM327 v2.3`, FTDI FT-X bridge, 115200 default. This is **better** than an OBDLink SX for this car: the STN1170 is the tri-transceiver chip (HS-CAN / MS-CAN / SW-CAN / K-line), whereas the SX's STN1110 is HS-CAN-only. That single fact unlocks the most interesting finding in this report (§3.3).

Confidence labels used throughout: **[C]** = confirmed by primary source, **[I]** = inference, **[U]** = unverified/blocked.

---

## 1. MultiEcuScan automation surface

### 1.1 No documented API — but the binary does read argv

**[C]** There is no command-line, scripting, plugin, COM/DDE, or remote-control feature documented anywhere. The official User Guide covers the full feature set and contains nothing of the kind ([User Guide PDF](https://multiecuscan.de/wp-content/uploads/2018/02/Multiecuscan20User20Guide.pdf)); the official usage page likewise documents only GUI operation ([multiecuscan.net/HowToUse](https://www.multiecuscan.net/HowToUse.aspx)). MES is a .NET application ([dicorse.com](https://www.dicorse.com/shop/multiecuscan-software-and-hardware-options/)).

**[I]** From direct inspection of `C:\Program Files (x86)\Multiecuscan\Multiecuscan.exe` (4.3 MB, dated 2025-08-12, MES 5.4): the assembly references `Environment.GetCommandLineArgs`, so it *does* parse arguments — but only **70 UTF-16 string literals** survive in the file (no `.ini`, `.csv`, `COM`, `ELM`, `OBDLink`, `Simulation` literals present), meaning the assembly is packed/obfuscated and its string table is decrypted at runtime. Runtime target string is `v2.0.50727` (.NET 2.0 CLR). **Conclusion: undocumented argument handling exists but cannot be enumerated without decompiling — which the EULA almost certainly forbids.** Treat MES CLI automation as a dead end.

### 1.2 Automation levers that actually exist (verified on this machine)

These are real, file-based, and writable by an MCP server:

| Artifact | Path | Format | Notes |
|---|---|---|---|
| `FES_Templates.ini` | install dir | `0=1989,1802,1872,1804` … slots 0–9 | 10 parameter-template slots, each a CSV list of MES-internal parameter IDs. **Writable → you can pre-program which PIDs MES will graph/record, then the operator just presses a number key.** |
| `FES_Tags.ini` | install dir | `0= ` … `9= ` (UTF-16) | Tag text bound to keys 0–9, injected inline into recordings. Writable → pre-load semantic event labels. |
| `SCAN_YYMMDDHHMM.txt` | install dir | plain text | Full-vehicle scan report: module name, ECU family, ISO code, VIN, HW/SW part numbers, DTCs with `Uxxxx-yy` + description. |
| `FESLog_YYMMDDHHMM_<vehicle>.txt` | install dir | plain text | Per-session log: `(Multiecuscan 5.4)`, timestamp, vehicle, ECU identity block, then `EXECUTING ADJUSTMENT…` / `EXECUTING ACTUATOR…` / `COMPLETED` records. |
| `Report1.pdf` + `report_head.png` | install dir | PDF via `PdfSharp.dll` | PDF report generation is built in. |
| CSV recordings | user-set folder | CSV, user-set separator | See §7. |

**[C] Simulation mode**: `CTRL+Connect` or `CTRL+F10` starts a fake session with no hardware — all modules/functions explorable, random values ([User Guide](https://multiecuscan.de/wp-content/uploads/2018/02/Multiecuscan20User20Guide.pdf), p.~14). **This is the ideal harness for developing/testing an MES-facing MCP server without the car.**

### 1.3 Adapters MES supports — and J2534

**[C]** User Guide (v1.x): MES recognises **5 interface types** — `K-Line/VagCom`, `ELM 327 1.3+`, `OBDKey`, `OBDLink`, `CANtieCAR`. Current site adds ELM Scan 5 and Vgate vLinker, and BLE devices on Windows 11 ([HowToUse](https://www.multiecuscan.net/HowToUse.aspx)). Current MES 5.x interface list per the vendor's own app listing: *CANtieCAR v4.x WiFi, CANtieCAR v5.x BLE/WiFi, ELM327 WiFi, OBDLink MX WiFi, OBDLink MX+ BT, Vgate vLinker WiFi, Vgate vLinker BLE, **Vgate vLinker FS/MS*** ([App Store listing](https://apps.apple.com/us/app/multiecuscan/id1436939705)).

**[C] MES does not support J2534 pass-thru.** J2534 appears in no MES interface list, guide, or page. (Contrast FORScan, which added experimental J2534 in v2.2 — [forscan.org t=867](https://forum.forscan.org/viewtopic.php?t=867).) Every MES connection is **ELM327/ST AT-command text over a serial COM port**, which has a hard consequence: **MES holds COM3 exclusively while connected. No MCP server can share the port concurrently.**

**[C]** ELS27 is not listed by MES (it is a FORScan-oriented STN1170 device); it would likely enumerate as a generic ELM327 but is unsupported.

**[C] CANtieCAR** is the "MULTIPLEXED" option: it multiplexes the vehicle's buses in hardware so **no coloured adapter cables are needed**, and the licence binds to the interface rather than the PC ([stelvioforum](https://www.stelvioforum.com/threads/mes-multiecuscan-multiplexed-vs-registered-difference.22086/), [multiecuscan.net/OrderMultiplexedPP.aspx](https://www.multiecuscan.net/OrderMultiplexedPP.aspx)).

**[C]** MES 5.4 released **2025-08-15**; release notes cover added ISO codes for 2012–2025 vehicles, Tonale 1.6 MJT, E6F engine updates, Ducato 290MCA modules — nothing about automation, and the 500e 2nd-gen remains **read-only because of the Security Gateway** ([MES forum t=10818](https://www.multiecuscan.net/forum/viewtopic.php?t=10818)). Recent versions fixed *PROXI alignment problems with DSCM and TBM modules on Giulia/Stelvio*.

---

## 2. Security Gateway (SGW) on 2018+ Giulia/Stelvio

### 2.1 What is blocked vs. allowed

**[C]** With SGW locked, MES is **read-only**: you can read DTCs and live data, but **cannot clear DTCs, run actuators, run procedures, or write/align PROXI**. The SGW "blocks any diagnostic tool from executing commands on the vehicle like actuators, procedures and even clearing of DTCs" ([giuliaforums SGW bypass thread](https://www.giuliaforums.com/threads/multiecuscan-sgw-by-pass-lite-module-sblocco-proxy-2018-fca.42962/)).

**[C]** FCA's own framing: the SGW restricts **intrusive/bi-directional** diagnostics — clearing DTCs, calibrations, relearns, actuations, adjustments — and is *not* intended to restrict read access to diagnostic data ([ALLDATA](https://www.alldata.com/us/en/support/diagnostics/article/fca-secure-gateway), [Repairer Driven News](https://www.repairerdrivennews.com/2020/01/20/cic-emerging-tech-head-explains-fca-sgw-says-other-oem-firewalls-coming/), [youcanic](https://www.youcanic.com/fca-security-gateway-module-explained-obd2-sgm-sgw/)).

**[C]** MES **cannot** unlock the SGW itself; only the factory tool can ([giuliaforums](https://www.giuliaforums.com/threads/multiecuscan-sgw-by-pass-lite-module-sblocco-proxy-2018-fca.42962/)). Appcar DiagFCA states plainly for the Stelvio: *"2018+ … is equipped with a Security Gateway Module (SGW). For active diagnostics and coding it is necessary to use an additional SGW Bypass Cable"* ([appcar-diagfca.com](https://appcar-diagfca.com/en/supported-vehicles/alfa-romeo-stelvio/)).

### 2.2 The three unlock paths

1. **SGW bypass plug (module replacement).** Unplug the SGW, insert a bypass block in its place; the OBD port then has full access. **Stelvio SGW location: behind the instrument cluster, near the windscreen under the dash** (Giulia: right of the steering column, under the wheel) ([EUROCOMPULSION](https://shopeurocompulsion.net/blogs/installation-database/fca-sgw-module-bypass-installation-info), [alfissimo](https://shop.alfissimo.com/inicio/3132-alfissimo-sgw-bypass-security-gateway-bypass-alfa-romeo-giuliastelvio-.html)). Proven on 2018–2019 Giulia/Stelvio.
2. **12+8 universal bypass adapter.** Unplug the SGW 12-pin and 8-pin connectors and bridge them through the adapter. Covers FCA 2018+; **not** for 2021+ where the SGW is folded into the BCM ([obdii365](https://www.obdii365.com/wholesale/obdstar-fcs-12-8-universal-adapter.html), [felkodslasare install guide](https://www.felkodslasare.se/en-en/collections/fca-group-sgw-bypass-adapter-12-8-pin-inkopplingsguide-steg-for-steg)).
3. **AutoAuth.** Stellantis credential service for **OE-approved** aftermarket tools; $50/yr per shop (6 users, +$2/user). The tool itself must be AutoAuth-registered — **MES is not**, so this is not a path for MES ([auteldealer](https://www.auteldealer.com/blogs/products-tutorial/fca-autoauth-what-it-is-how-to-use-it-with-your-autel-scanner), [tirereview](https://www.tirereview.com/autel-autoauth/), [Bosch](https://boschdiagnostics.com/ads-software/secure-gateway)).

**Risk note [C]:** dealers may object if the SGW is absent during warranty work; the community advice is to refit the original module before service visits ([giuliaforums](https://www.giuliaforums.com/threads/sgw-bypass-installation.56787/page-2), [klavkarr](https://www.klavkarr.com/blog/security-gateway-alfa-romeo)). A permanently installed bypass also removes the vehicle intended CAN firewall.

---

## 3. STN1170 / ST command set — the real capability layer

All citations below: **OBDLink Family Reference and Programming Manual, revision F** — https://www.scantool.net/scantool/downloads/682/obdlink_frpm_f.pdf (78 pp; I extracted and read the full text). Older preliminary revision: https://els27.ru/files/stn1100-frpm.pdf

### 3.1 `STP` protocol presets — the multi-bus map (§8.6, p.34)

> "OBDLink ICs support a maximum of three physical CAN channels… Internally, the OBDLink has **only one CAN peripheral that can be mapped to different IC pins under software control. This means that only one CAN channel can be active at a time.**"

**High Speed CAN — "dual-wire transceiver connected to OBD port pins 6 and 14"**

| `p` | Protocol |
|----|----|
| 31 | ISO 11898, 11-bit Tx, 500 kbps, var DLC (raw CAN) |
| 32 | ISO 11898, 29-bit Tx, 500 kbps, var DLC (raw CAN) |
| 33 | ISO 15765, 11-bit Tx, 500 kbps, DLC=8 |
| **34** | **ISO 15765, 29-bit Tx, 500 kbps, DLC=8** ← the Giorgio UDS preset |
| 35/36 | ISO 15765, 11/29-bit, 250 kbps |
| 41/42 | J1939 11/29-bit |

**Medium Speed CAN — "typically connected to pins 3 and 11 of the OBD port"**

| `p` | Protocol |
|----|----|
| 51 | ISO 11898, 11-bit Tx, 125 kbps, var DLC |
| 52 | ISO 11898, 29-bit Tx, 125 kbps, var DLC |
| 53 | ISO 15765, 11-bit Tx, 125 kbps, DLC=8 |
| 54 | ISO 15765, 29-bit Tx, 125 kbps, DLC=8 |

**Correction to the brief:** the MS-CAN range is **51–54, not 51–56**.

**Single Wire CAN ("GMLAN") — "single-wire transceiver connected to OBD port pin 1"**: 61–64 at 33.3 kbps, transceiver mode via `STCSWM`. Not used on Giorgio.

Baud rate and DLC are changeable per preset via `STPBR <bps>` / `STPBRR`; the protocol family and Tx ID size are hard-set per preset. **All CAN presets receive both 11-bit and 29-bit messages.**

### 3.2 Giorgio three OBD-accessible CAN buses

**[C]** Verified pinout (Alfa Romeo Portal, from factory wiring docs — https://www.alfa-romeo-portal.com/forum/thread/3284-obd-port-pinbelegung-giulia-stelvio/ ):

| Bus | OBD pins | Wire colours | Speed | Modules |
|---|---|---|---|---|
| **CAN-C** (diagnostic C) | **6 (+) / 14 (−)** | green / brown | **500 kbps** | ECM, TCM, main powertrain — reachable with any plain ELM327 |
| **CAN-IHS** (a.k.a. CAN-BH) | **3 (+) / 11 (−)** | blue-white / white | **125 kbps** | BCM, IPC, HVAC, ETM/uConnect, AMP, blind-spot sensors, CSWM, TTM |
| **CAN-CH** (chassis) | **12 (+) / 13 (−)** | green-white / brown-white | 500 kbps *[I]* | ESC/ABS, CDCM (suspension), damper control |

CAN-IHS at **125 kbps** confirmed independently ([alfaowner LIN/CAN speeds thread](https://www.alfaowner.com/threads/lin-bus-connection-speeds.1210388/)); CAN-IHS module list from [appcar-diagfca](https://appcar-diagfca.com/en/supported-vehicles/alfa-romeo-stelvio/) / community. The **M001 Body Computer acts as the central gateway** between them.

**[C]** MES coloured cables are **passive re-pinning harnesses**: "The main system is on pin 6 and 14 and can be reached directly with any ELM327 interface. The adapter cables redirect to pins 12-13 and 3-11 to reach the other 2 CAN busses" ([squadra-tuning](https://squadra-tuning.com/obd-tools/multiecuscan/) via [giuliaforums](https://www.giuliaforums.com/threads/multiecuscan-cables-question.66547/)). Part codes: **A5 = blue, A6 = grey**, both for Giulia and Stelvio 2.0L/2.9L ([alfissimo](https://shop.alfissimo.com/diagnostic-softwarehardware-multiecuscanalfaobd/3019-diagnostic-adapters-multiecuscanalfa-obd.html)). Mapping from [giuliatech MES settings compilation](https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80): **Body / CAN Setup / PROXI ALIGNMENT → blue**; **ABS / Continental ABS MK C1 → grey**. Since BCM is on CAN-IHS (3/11) and ABS is on CAN-CH (12/13): **blue = pins 3/11, grey = pins 12/13** *[I, high confidence]*.

### 3.3 The standout finding: your adapter can reach CAN-IHS with no cable

**[I — high value, medium-high confidence, cheap to verify]**
The STN1170 MS-CAN transceiver sits on **OBD pins 3/11** at a **125 kbps** default — which is *exactly* Giorgio CAN-IHS. Therefore:

```
STP 54          # ISO 15765, 29-bit, 125 kbps, MS-CAN transceiver (pins 3/11)
STPBRR          # confirm 125000
STPO            # open
ATSH 18DA40F1   # e.g. BCM
2210xx
```

should reach the **BCM / IPC / HVAC / uConnect** stack **without the blue A5 cable**. Conversely, **CAN-CH on pins 12/13 has no STN transceiver mapping at all — the grey A6 cable remains mandatory** for ABS/ESC/CDCM.

Caveats to test: (a) whether Vgate wired the MS-CAN transceiver to 3/11 per the Ford/FORScan convention (near-certain, since the device is sold as a FORScan MS-CAN adapter — [Amazon listing](https://www.amazon.com/Vgate-vLinker-Adapter-FORScan-MS-CAN/dp/B094Z7PBLS)); (b) whether the vLinker "auto switch" firmware overrides manual `STP` selection. Vgate markets **electronic auto-switching between HS-CAN and MS-CAN** with no physical toggle ([vgatemall vLinker FS USB](https://vgatemall.com/products-detail/i-19/), [obdii365 FORScan config](https://www.obdii365.com/service/configure-forscan-for-vgate-vlinker-fs-interface.html)) — whether that is a firmware layer above `STP` or simply *is* `STP` is **[U]**; probe `STPR`/`STPRS` before and after an `STP 54` to find out.

**[C] Does MES use this?** No. MES supported-interface abstraction is the generic `OBDLink`/`ELM327` type plus a COM port, and MES own Giorgio workflow instructs the user to swap coloured cables — it prompts "use the appropriate cable" when a module is on another bus ([giuliaforums](https://www.giuliaforums.com/threads/multiecuscan-cables-question.66547/)). MES does **not** drive MS-CAN transceiver switching on this adapter. That means **your MCP server can reach a bus MES cannot reach without hardware you may not own.**

### 3.4 Command reference (rev F, §8, verified verbatim)

**Transmit arbitrary frames — `STPX param1[,…,paramN]`** (§8.6, p.35)

| Param | Meaning |
|---|---|
| `h:` | header / CAN ID (overrides `ATSH`) |
| `d:` | data (hex) |
| `l:` | data length → device replies `DATA>` prompt, then you send bytes (for messages longer than the UART RX buffer) |
| `t:` | response timeout, overrides `STPTO` |
| `r:` | expected response count, overrides `ATR` |
| `x:` | ISO 15765 extended address / ISO 9141 expected length |
| `f:` | flags (auto-checksum control) |

Examples from the manual: `STPX h:686AF1, d:0100, t:50, r:1` and `STPX h:123456, d:`
"This command will turn on segmentation but will revert segmentation back to its previous state after sending." Also: **`STPX` opens the protocol but does not close it when it finishes.**

**Device limits (p.35 table):** OBDLink SX / **STN1110 / STN1170** → max message **2 k**, **max recommended UART baud 2 Mbps with `ATE0`** (1 Mbps with echo on). OBDLink MX+ / EX → 4 k. The vLinker FS vendor claims an **8192-byte serial buffer and OBD requests up to 4,128 bytes** ([vgatemall](https://vgatemall.com/products-detail/i-19/)) — richer than the reference STN1170, **[U]**, worth probing.

**Monitoring (§8.9, p.40)**
- `STM [n]` — monitor using current filters. For CAN, **treats frames as raw CAN** (no ISO-15765 reassembly).
- `STMA [n]` — monitor all; **for CAN protocols all messages are treated as ISO 15765**.
- `n` = 1…32767 responses then auto-exit; omit for indefinite. Stop by sending any single character; wait for `STOPPED`.
- **`STCMM mode`** — CAN monitoring mode, and this one matters for safety:
  - `0` = **receive only, no CAN ACKs** ← truly passive; the vehicle never sees you
  - `1` = normal node, with CAN ACKs *(default)*
  - `2` = receive all frames including errored frames, no ACKs
- **Caution (§8.14):** "Exiting a monitoring session will close the protocol."

**Filtering (§8.10, pp.41–42)** — note the **modern names** in rev F:

| Command | Function |
|---|---|
| `STFPA [pattern],[mask]` | **add pass filter** (older firmware: `STFAP`) |
| `STFBA [pattern],[mask]` | add block filter |
| `STFFCA [pattern],[mask]` | add flow-control filter |
| `STFPGA pgn[,tgt]` | add SAE J1939 PGN filter |
| `STFPC` / `STFBC` / `STFFCC` / `STFPGC` | clear pass / block / FC / PGN filters |
| `STFA` / `STFAC` | enable automatic filtering / clear all filters |

Syntax: pattern and mask 0–5 bytes (0–10 ASCII chars), equal length, matched MSB-first. `STFPA 7E8,7FF` is the same as `STFPA 07E8,07FF`. For 29-bit CAN the first four bytes are the CAN ID; for 11-bit, the first two. Example: `STFPA 102ABCDE, 1FFFFFFF`.
**Every "add filter" command dynamically allocates RAM** and can return `OUT OF MEMORY`, which then also breaks OBD requests — *"make sure that your code anticipates and gracefully handles OUT OF MEMORY errors."*
**[U]** On firmware v4.3.2 verify whether `STFPA` or the legacy `STFAP` spelling is accepted — the 2010 preliminary manual used `STFAP`. Probe both at startup and cache which one works.

**CAN-specific (§8.8, pp.38–39)**

| Command | Function |
|---|---|
| `STCAF format[,tt]` | addressing format: `0` Normal, `1` Extended w/ target address, `2` Mixed w/ TA extension. Default `0`. |
| **`STCFCPA txadd[ext],rxadd[ext]`** | add flow-control address pair. **Manual own examples include `STCFCPA 18DA10F1, 18DAF110` and `STCFCPA 7E0, 7E8`** — i.e. exactly the Giorgio pattern |
| `STCFCPC` | clear all FC address pairs |
| `STCSEGR 0/1` | **CAN Rx segmentation** — strips multi-frame PCI bytes and reassembles into one message. **Default 0 (off).** |
| `STCSEGT 0/1` | CAN Tx segmentation. Default 0. **Works for raw CAN (ISO 11898) too, not just ISO 15765-2** |
| `STCSTM ms` | STmin offset (max 127 ms, 3-dp precision). Legislated CAN: added to ECU-supplied STmin. Raw CAN: sets inter-frame delay (default 1 ms) |
| `STCTOR fcTimeout,cfTimeout` | FC/CF receive timeouts. **Defaults 75 ms / 150 ms** |
| `STCTR hhhhhh` / `STCTRR` | write/read raw CAN timing registers (custom bit timing) |
| `STCSWM mode` | SW-CAN transceiver mode (0 Sleep, 3 Normal default, 2 High-Voltage Wakeup, …) |

**Protocol / timing (§8.6)**: `STP p`, `STPO` (open), `STPC` (close), `STPR` (number), `STPRS` (string), `STPBR`/`STPBRR`, `STPTO ms` (request timeout), `STPTOT ms`, `STPTRQ ms` (min gap between last response and next request), `STPCB 0/1`.

**UART (§8.3)**: `STBR baud` (software-friendly switch), `STBRT ms`, `STSBR baud` (terminal-friendly), `STUFC 0/1` (flow control), `STWBR` (persist to NVM). Manual own example ramps to `STSBR 921600`.

**Identity (§8.4)**: `STDI`, `STDIX`, `STI`, `STIX`, `STMFR`, `STSN`, `STDICPO`, `STDICES`, `STDITPO`.

**Batched Commands (§8.15, p.51–52) — biggest latency win available**
```
STBC 1                                  # enable batching (volatile; lost on reset/power cycle)
STBCOF 2                                # 0=verbose, 1=suppress OKs, 2=coalesce contiguous OKs
STP 33|ATAT 0|ATH 1|ATSH 7E0|0100 1     # one round trip, pipe separated
```
Collapses a 5-round-trip setup sequence into one — worth roughly 5x on session setup over a 115200 link.

**Periodic Messaging (§8.14, p.50)** — `STPPMA` adds background auto-sent messages. **This is your TesterPresent (`3E 00`) keepalive** for extended diagnostic sessions, handled by the adapter rather than your event loop. Caveats: protocol must be open; `STCMM` mode governs whether periodic messages are sent while monitoring; `OUT OF MEMORY` risk as with filters; you must account for periodic-message replies when parsing responses to manual requests.

**PowerSave (§8.11)**: `STSLCS` prints the active config summary; `STSLEEP`, `STSLLT`, `STSLU`, `STSLUIT`, `STSLUWP`, `STSLPA…`. Relevant if the dongle is left plugged in.

---

## 4. UDS / ISO-TP on Giorgio

### 4.1 Addressing — confirmed

**[C]** Giorgio uses **29-bit ISO-15765-2 normal-fixed** addressing on CAN-C at **500 kbps**:
- Physical request `0x18DA<TA>F1` → response `0x18DAF1<TA>`
- Functional request `0x18DB33F1`
- Tester source address `0xF1`

Confirmed by [ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia](https://github.com/ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia) (2019 Giulia 2.0L petrol, `TWAI_SPEED_500KBPS`, RX filter `0x18000000`–`0x18FFFFFF`) and [danardi78/Alfaromeo-Giulia-Stelvio-PIDs](https://github.com/danardi78/Alfaromeo-Giulia-Stelvio-PIDs/). Matches ISO-15765-2 normal-fixed as documented by [python-can-isotp addressing docs](https://can-isotp.readthedocs.io/en/latest/isotp/addressing.html) (`0x18DA<TA><SA>` physical, `0x18DB<TA><SA>` functional).

### 4.2 Target-address map (community-derived, **[I]** medium-high confidence)

| TA | Request ID | Response ID | Module |
|---|---|---|---|
| `10` | `18DA10F1` | `18DAF110` | **ECM / engine** |
| `18` | `18DA18F1` | `18DAF118` | **TCM / transmission (ZF 8HP)** |
| `40` | `18DA40F1` | `18DAF140` | BCM / battery management |
| `60` | `18DA60F1` | `18DAF160` | IPC / instrument cluster |
| `2A` | `18DA2AF1` | `18DAF12A` | Steering angle |
| `C7` | `18DAC7F1` | `18DAF1C7` | TPMS / RFHub — WARNING: danardi repo notes this header **can trigger the immobiliser if a BACCAble board is installed** |
| `BA` | `18DABAF1` | — | unused; claimed by the BACCAble project |
| `33` | `18DB33F1` | — | functional broadcast (legislated OBD-II) |

### 4.3 Services and DIDs

**[C]** Service **`0x22` ReadDataByIdentifier** with 2-byte DIDs; positive response `0x62` (service + 0x40). Sample DIDs observed in the wild:

| DID | Parameter | Header |
|---|---|---|
| `1000` | Engine RPM | `DA10F1` |
| `1302` | Engine oil temperature | `DA10F1` |
| `195A` | Boost pressure | `DA10F1` |
| `1955` | Battery voltage | `DA10F1` |
| `1004` | Battery | `DA10F1` |
| `192D` | Gear | `DA10F1` |
| `18DE` | DPF temperature | `DA10F1` |
| `1018` | Torque | `DA18F1` (TCM) |

Formulas in danardi `custompids.csv` use CarScanner syntax (A, B, C = response bytes). Files provided: `custompids.csp` (CarScanner native), `custompids.csv` (human-readable: description, header, PID, formula, units, min/max), `dashboardv2.json`, `backup.cbz`. Caveat: derived from a **2.2 MJTD diesel Giulia MY2016**; the author warns 2.0/2.9 petrol variants differ.

### 4.4 ECU identification correction

The brief assumed **Bosch MED17.3.x**. **[C] The actual ECU on this vehicle** — read from `FESLog_2510142149_....txt` in the MES install directory on this machine — is:

```
Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir
Magneti Marelli IAW 10JA CF6/EOBD Injection (2.0)
ECU ISO code: 00 01 50 40 18
Hardware number: MM10JAHW232   Software number: P235QB39
Homologation: FIBA00           FIAT drawing number: 52055320
VIN lock status: Locked by odometer
PROXI configuration write counter: 1
```

So: **Magneti Marelli IAW 10JA, not Bosch MED17**. MED17.3.5 is associated with Giulia/Stelvio by tuning vendors ([Alientech/Alt Tune](https://alttune.com/upgrade-3-54-from-alientech)) but applies to other variants (2.9 QV / diesel). Any DID map sourced from MED17 documentation will not transfer. **Transmission: ZF 8HP50** on the 2.0T AWD ([go-parts](https://www.go-parts.com/garage/transmission-assembly-alfa-romeo-giulia-alfa-romeo-stelvio-2017-2025)).

Also note from that same log: MES exposes **`Functioning time (EEPROM)`, `Startups counter`, `VIN lock status`, `PROXI configuration write counter`** — all high-value fields for a diagnostic MCP server to surface.

### 4.5 Python stack

| Library | Fit | Notes |
|---|---|---|
| **[udsoncan](https://udsoncan.readthedocs.io/)** | strong | Full ISO-14229 client. `PythonIsoTpConnection` couples to `can-isotp` + `python-can` and works on Windows ([Q&A](https://udsoncan.readthedocs.io/en/latest/udsoncan/questions_answers.html)) |
| **[python-can-isotp](https://can-isotp.readthedocs.io/)** | **key enabler** | Pure-Python ISO-TP in userspace, "may or may not be coupled with python-can", accepts a **user-provided `rxfn`/`txfn`**. So you can run real ISO-TP over the STN raw-CAN mode (`STP 32`/`STM` for RX, `STPX` for TX) without any SocketCAN. Supports `NormalFixed_29bits` natively |
| **python-can** | partial | **No ELM327/STN interface exists.** Supported: socketcan, slcan, serial, Vector, PCAN, Kvaser, neoVI, IXXAT, candleLight/GS-USB, etc. ([interfaces docs](https://python-can.readthedocs.io/en/stable/interfaces.html)). "python-can-stn" does not exist |
| **python-OBD** | basic | ELM327 only, legislated PIDs. **Known STN bug: commands must terminate with CR only, not CRLF** — CRLF breaks STN11xx chipsets ([PR #122](https://github.com/brendan-w/python-OBD/pull/122)). Fix this in your own serial layer too |
| **[can327](https://docs.kernel.org/networking/device_drivers/can/can327.html)** / [elmcan](https://github.com/norly/elmcan) | reference only | Mainline Linux kernel ELM327-to-SocketCAN line discipline (ELM327 1.4b+). Linux-only, so useless on this Windows laptop — but it is THE reference implementation for "make an ELM327 behave like a CAN interface", worth reading before writing your own |
| **[ELM327-emulator](https://github.com/Ircama/ELM327-emulator)** | dev/test | Multi-ECU simulator; supports many AT commands **plus some OBDLink AT/ST commands**, stateful UDS with ISO-TP flow control, over serial/TCP/BT, cross-platform. **Your CI harness — no car needed** |

---

## 5. Alternative / complementary tools

**AlfaOBD** — **[C]** "Gauges data recording" writes CSV to `/sdcard/Android/data/com.android.AlfaOBD/files/logs/Gauges_Data.log`; one line per measurement cycle (timestamp + values); **appended across sessions**, so the file grows and contains many "chapters". Configurable "Decimal separator" and "CSV separator" ([AlfaOBD Android Help PDF](https://www.alfaobd.com/AlfaOBD_Android_Help.pdf)). **Advantage over MES: append-during-session, so genuinely tailable.** No API/CLI. Also works with the vLinker FS ([obdii365](https://www.obdii365.com/wholesale/vgate-vlinker-fs-elm327-for-ford-forscan.html)).

**OBDwiz / OBDLink app** — **[C]** OBDwiz records to log or CSV for offline analysis ([scantool.net/obdwiz](https://www.scantool.net/obdwiz/)); the OBDLink app auto-creates a new CSV per connection, plain text, standard column-aligned format ([OBD Solutions support](https://support.obdsol.com/support/solutions/articles/43000709894-get-started-with-logs)). Legislated PIDs only — no Giorgio manufacturer DIDs.

**Open-source Giorgio projects**

| Project | Value |
|---|---|
| [commaai/opendbc PR #1251](https://github.com/commaai/opendbc/pull/1251) + PR #1250 | FCA Giorgio Stelvio/Giulia DBC + panda safety. Draft; UDS/VIN fingerprinting, gear position, driver gas, cruise buttons, checksums/counters still open. **Best available Giorgio DBC starting point** |
| [gaucho1978/BACCAble](https://github.com/gaucho1978/BACCAble) | Giulia/Stelvio CAN tool: sniffer, start&stop disable, ESC+TC selector, dashboard params. Custom board with **3 ST chips, one per CAN bus**; alternatives: CANable/MKS, Fysect uCAN, candlelight STM32F072. Explicitly "educational and research purposes" |
| [danardi78/Alfaromeo-Giulia-Stelvio-PIDs](https://github.com/danardi78/Alfaromeo-Giulia-Stelvio-PIDs/) | Header + DID + formula table (see §4.3) |
| [ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia](https://github.com/ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia) | Minimal ESP32-C3 + SN65HVD230 reference; explicitly warns you need an SGW bypass first |
| [beaups/giulia_ESCape](https://github.com/beaups/giulia_ESCape) | TC/ESC enable-disable, 2018 Giulia QV |
| [CSS-Electronics/can-bus-reverse-engineering-skills](https://github.com/CSS-Electronics/can-bus-reverse-engineering-skills) | **Claude Code skills for reverse-engineering CAN signals into DBC files** — directly reusable methodology |
| [iDoka/awesome-canbus](https://github.com/iDoka/awesome-canbus) | Index of CAN tooling |

**SavvyCAN** — **[C]** has a **JavaScript scripting interface** with `host` (`setTickInterval`, `log`, `addParameter`), `can` (`setFilter`, `sendFrame`), **`isotp` (`sendISOTP` with automatic flow control)** and **`uds` (`sendUDS(bus, id, service, sublen, subfunc, length, data)`)** objects ([savvycan.com/docs/scriptingwindow.html](https://www.savvycan.com/docs/scriptingwindow.html)). Connects via GVRET devices, network, and Qt CANbus. **No command-line / headless automation — GUI-only script loading** ([README](https://github.com/collin80/SavvyCAN)). Log formats: crtd, cs11, gvret-a/b, lawicel, pcap, raw.

**wiTECH 2 / Mopar Diagnostic Pod (reference only)** — MicroPod II covers pre-2024; **MDP+** is required for 2021–2025+ with CAN-FD / DoIP ([kb.fcawitech.com](https://kb.fcawitech.com/article/mopar-diagnostic-pod-overview-983.html), [Maverick Diagnostics](https://www.maverickdiagnostics.com/shop/oem-tools/diagnostic-pod/)). Subscription-gated; not a practical integration target.

---

## 6. Existing MCP servers for automotive diagnostics

| Server | Tools / shape | Hardware | Transport | Licence | Verdict |
|---|---|---|---|---|---|
| **[farzadnadiri/mcp-can](https://github.com/farzadnadiri/mcp-can)** | **13 tools**: read frames, decode signals, OBD-II requests, **UDS diagnostic requests**, fault injection, J1939 PGN/DM1 | Built-in **virtual CAN bus + ECU simulator** (no hardware needed); optional SocketCAN/vCAN on Linux | SSE (default), streamable-HTTP, stdio | MIT | **Best reference.** DBC decode via `cantools`. Tool taxonomy is close to what you want. Note "Educational/prototyping use only" |
| **[ayhammouda/obd-mcp-server](https://github.com/ayhammouda/obd-mcp-server)** | 7 read-only tools: `obd_list_vehicles`, `obd_get_vehicle_status`, `obd_read_standard_pids`, `obd_read_dtcs`, `obd_read_ecu_snapshot`, `obd_open_issue`, `obd_get_issue_timeline` | Deterministic simulator; optional ELM327 via `py-obdii` | stdio, or **loopback-only** HTTP (rejects remote) | Apache-2.0 / MIT | **Best safety model to copy.** Strictly read-only, no raw commands, allowlisted operations, **VINs never fully exposed — only pseudonymous fingerprints** |
| [petrpatek/obd2-mcp-server](https://github.com/petrpatek/obd2-mcp-server) | 7 OBD tools, fault codes + live data + plain-language explanation | BLE ELM327 | stdio | — | Hobby-scale; good UX ideas |
| [castlebbs/Vehicle-Diagnostic-Assistant](https://github.com/castlebbs/Vehicle-Diagnostic-Assistant) | LangGraph agent with diagnostic MCP server on-device, plus VIN decoder | ELM327 | — | — | Architecture reference for on-dongle deployment |

**[C]** Nothing automotive exists in the first-party Claude connector registry (searched "OBD, CAN bus, automotive, vehicle diagnostics, car" — zero relevant hits). No J2534 or SavvyCAN MCP server found. **There is a genuine gap here.**

---

## 7. MES recording & live data — exact behaviour

All **[C]**, from the official [User Guide](https://multiecuscan.de/wp-content/uploads/2018/02/Multiecuscan20User20Guide.pdf) (Settings items 9–11, Graph screen items 3–13) plus on-disk verification:

**Settings screen**
- **item 9** — "Select the separator character for the CSV files generated by Multiecuscan."
- **item 10** — "This is the folder on your hard drive where Multiecuscan will automatically save the generated **CSV** files. **The folder must exist!**" e.g. `C:\Multiecuscan_CSV`
- **item 11** — same for **LOG** files, e.g. `C:\Multiecuscan_LOGS`
- **item 5** — graph redraw speed Fast/Slow: "does not affect the recorded data in any way, it only affects the graph drawing quality on screen" (set Slow if you get disconnects)

**Graph / recording screen**
- **item 3** — F10 toggles recording. "Each time you start a new recording Multiecuscan will create new CSV file. **When you stop the recording Multiecuscan will automatically write the CSV file.**"
- **item 5** — selectable record rate; **item 6** — horizontal scale; **item 4** — 1–4 graphs
- **items 7/13** — tags on keys 0–9, inserted inline during recording (backed by `FES_Tags.ini`)
- **items 8/9/10** — multiple CSVs held in memory; `E` exports the selected one, `I` imports one
- **item 13** — **PARAMETER RECORDING PRIORITY 1–5**: priority 5 refreshes 5x slower than priority 1, freeing bandwidth for the parameters you care about. Directly tunable for a high-rate MCP capture plan

### The answer to "can we live-tail?"

**No — for CSV.** Confirmed twice over:
- The User Guide: the CSV is written **on stop**, not streamed.
- MES forum: "the registered version of Multiecuscan autosaves the log file, but **only at the end of logging when you press stop**, not continuously during recording" ([MES forum t=2316](https://www.multiecuscan.net/forum/viewtopic.php?t=2316)).

**Yes — for session logs, partially.** `FESLog_*.txt` and `SCAN_*.txt` land in the **install directory** (`C:\Program Files (x86)\Multiecuscan\`, not the configured LOG folder — verified on this machine) and are written as events occur. A filesystem watcher on that directory gives you near-real-time visibility of **module identity blocks, adjustments executed, and actuators fired** — which is exactly the workflow-provenance data an MCP diagnosis tool wants, even though it is not live parameter data. WARNING: because they are under `Program Files`, writes may require elevation — check whether MES runs elevated or whether UAC virtualisation is redirecting these to `VirtualStore`.

---

## Ranked integration options

### 1. Native ISO-TP/UDS client over the vLinker FS, in Python — the core engine
**Enables:** arbitrary UDS on any Giorgio module — `0x22` DID reads (incl. undocumented DIDs via sweep), `0x19` DTC reads w/ status masks, `0x03/0x07/0x0A` legacy, freeze frames, session control `0x10`, `0x3E` TesterPresent, `0x27` SecurityAccess probing. Everything MES reads, plus everything MES database does not know about.
**Prereqs:** `STP 34` + `ATSH 18DA10F1` + `STCFCPA 18DA10F1,18DAF110` + `STCSEGR 1`/`STCSEGT 1`, or raw-CAN mode (`STP 32` + `STM` + `STPX`) feeding python-can-isotp custom `rxfn`/`txfn` under `udsoncan`. Set `ATE0` then `STBR 921600`+. MES must be closed (exclusive COM3).
**Difficulty:** Medium. **Risk:** Low with read-only services; **high if you enable writes** — gate `0x2E`/`0x31`/`0x2F`/`0x14`/`0x11` behind explicit confirmation.

### 2. MS-CAN reach to CAN-IHS with no blue cable (`STP 53/54`)
**Enables:** BCM, IPC, HVAC, uConnect/ETM, blind-spot, amp, TPMS — **a bus MES cannot touch without the A5 cable**. Highest capability-per-effort ratio in this report.
**Prereqs:** vLinker FS (have it), 5 minutes of probing: `STP 54` then `STPBRR` then `STPO` then `STPR`/`STPRS`.
**Difficulty:** Low. **Risk:** Low — start with `STCMM 0` (no ACK) + `STM` to listen before transmitting. **Verify before building on it.**

### 3. Passive raw-CAN sniffer/recorder (`STCMM 0` + `STM`/`STMA` + `STFPA`)
**Enables:** full bus capture for reverse engineering, opendbc/DBC decode via `cantools`, signal discovery for parameters no tool exposes. Works **with the SGW fully locked** — the SGW blocks writes, not the wire.
**Prereqs:** `ATE0`, `STBR 2000000` (cap per FRPM: 2 Mbps for STN1110/1170 class with echo off), aggressive `STFPA` filters, robust `OUT OF MEMORY` handling.
**Difficulty:** Low–Medium. **Risk:** Very low with `STCMM 0` — the adapter does not even ACK. **The safest thing in this list.**

### 4. MES artefact ingestion MCP server (extend the existing `mes-log` server)
**Enables:** structured history from `SCAN_*.txt` (module inventory, ISO codes, HW/SW part numbers, VIN, DTC + description), `FESLog_*.txt` (actuator/adjustment provenance, `Startups counter`, `Functioning time`, `VIN lock status`, `PROXI write counter`), and post-hoc CSV recordings. Directory watch on the install folder gives near-real-time event visibility.
**Prereqs:** none — pure file parsing. Handle UTF-16 and the configurable CSV separator.
**Difficulty:** Low. **Risk:** None. **Do this first; it is free.**

### 5. MES pre-configuration via `FES_Templates.ini` / `FES_Tags.ini`
**Enables:** an MCP tool that writes a recording plan ("capture boost, RPM, oil temp, wastegate duty at priority 1") into template slot 0, and pre-loads tag strings — the human then presses `0` and `F10`. Closes the loop between the agent and MES without any API.
**Prereqs:** map MES-internal parameter IDs to names (reverse from `Files/data0*.dat` or by GUI round-trip: set a template in the GUI, diff the INI).
**Difficulty:** Medium (the ID mapping is the work). **Risk:** Low; back up both INIs. Write only while MES is closed.

### 6. Port-arbitration / handoff layer
**Enables:** MES and your MCP server coexisting on one operator laptop. MES holds COM3 exclusively; you need a supervisor that detects `Multiecuscan.exe`, releases the port, and reports "MES has the bus" instead of throwing serial errors.
**Prereqs:** process watch + `SerialPort` open/close discipline; optionally a second adapter on a second COM port (the car OBD port is single, so this means a Y-splitter — electrically fine on CAN, but two ACKing nodes; set the passive one to `STCMM 0`).
**Difficulty:** Low–Medium. **Risk:** Low. Unglamorous but it is the difference between a demo and a tool.

### 7. Fork `mcp-can` / `obd-mcp-server` for tool shape and safety model
**Enables:** a proven 13-tool taxonomy (frames, decode, OBD, UDS, J1939, fault injection) and a proven safety posture (read-only, allowlisted ops, loopback-only HTTP, VIN pseudonymisation) without designing from scratch. `cantools` DBC decode drops straight in alongside opendbc Giorgio DBC.
**Prereqs:** MIT / Apache-2.0 — both permissive. Neither has an ELM327/STN backend; you supply that from option 1.
**Difficulty:** Low. **Risk:** Low. Honour mcp-can "educational use" caveat in your own docs.

### 8. SGW bypass to unlock bi-directional control
**Enables:** clear DTCs, run actuator tests, execute procedures, PROXI alignment — i.e. MES and your server entire write surface. Nothing else unlocks this (AutoAuth requires an OE-approved tool; MES is not one).
**Prereqs:** bypass plug or 12+8 adapter; **Stelvio SGW is behind the instrument cluster near the windscreen** — a genuinely awkward install compared to the Giulia steering-column location.
**Difficulty:** Medium (physical). **Risk:** **Highest in this list.** Removes the vehicle CAN firewall; dealers may object during warranty work (refit before service); write operations on BCM/PROXI can immobilise the car; legality varies by jurisdiction. Gate every write tool behind explicit human confirmation and log to FESLog-style provenance.

### 9. ELM327-emulator + MES simulation mode as a CI harness
**Enables:** develop and regression-test the whole stack with no car. `ELM327-emulator` does stateful UDS with ISO-TP flow control and multi-ECU, over serial/TCP; MES `CTRL+F10` exercises the MES side.
**Prereqs:** `pip install ELM327-emulator`; a com0com-style virtual serial pair on Windows.
**Difficulty:** Low. **Risk:** None. **Build this alongside option 1, not after.**

### 10. CANtieCAR upgrade (MES MULTIPLEXED)
**Enables:** all three Giorgio buses with no cable swapping, licence bound to the interface rather than the PC, and MES only "professional multi-protocol multiplexing" tier.
**Prereqs:** purchase; MES MULTIPLEXED licence.
**Difficulty:** Low (money). **Risk:** Low. **Only worth it if option 2 fails** — if `STP 54` reaches CAN-IHS, you already have two of three buses and only need the grey A6 cable (about 20 EUR) for CAN-CH.

---

## Coverage gaps & things to verify on the car

- **[U] `multiecuscan.net/forum` requires login** for automated fetch — I could not read threads t=10818 (5.4 notes), t=8582 (adapters), t=7240 ("SGW Module Detected"), t=10514 (vLinker FS USB connection issue), t=2316 (autosave). Search-engine snippets were used instead; a logged-in human should confirm the SGW and vLinker threads directly.
- **[U] giuliaforums / alfaowner / fiat500owners** are behind a Tollbit 402 paywall for automated fetching. Reachable in a browser.
- **[U]** Whether `STP 54` actually reaches CAN-IHS on this vehicle (option 2) — the single highest-value 5-minute test.
- **[U]** Whether the vLinker FS firmware "auto-switch" overrides manual `STP`.
- **[U]** `STFPA` vs legacy `STFAP` spelling on firmware v4.3.2 — probe both, cache the winner.
- **[U]** Whether the vLinker advertised 8 kB buffer / 4128-byte OBD request exceeds the reference STN1170 2 k limit.
- **[U]** CAN-CH (pins 12/13) bitrate — 500 kbps inferred from "high speed", not confirmed.
- **[U]** MES undocumented command-line arguments (would require decompiling an obfuscated assembly — EULA risk, not recommended).

**One correction worth propagating upstream:** the engine ECU is **Magneti Marelli IAW 10JA CF6/EOBD**, not Bosch MED17 — any MED17-derived DID map will not apply.

---

## Sources

**MultiEcuScan (primary)**
- https://www.multiecuscan.net/HowToUse.aspx
- https://multiecuscan.de/wp-content/uploads/2018/02/Multiecuscan20User20Guide.pdf
- https://www.multiecuscan.net/MultiecuscanUserGuide.pdf
- https://www.multiecuscan.net/forum/viewtopic.php?t=10818 (5.4 release notes)
- https://www.multiecuscan.net/forum/viewtopic.php?t=2316 (autosave on stop)
- https://www.multiecuscan.net/forum/viewtopic.php?t=8582 (interfaces and adapters)
- https://www.multiecuscan.net/forum/viewtopic.php?t=7240 (SGW Module Detected)
- https://www.multiecuscan.net/forum/viewtopic.php?t=10514 (vLinker FS USB)
- https://www.multiecuscan.net/forum/viewtopic.php?t=4071 (graphing CSV recordings)
- https://www.multiecuscan.net/forum/viewtopic.php?t=8907 (parameter refresh rates)
- https://www.multiecuscan.net/forum/viewtopic.php?t=1493 (faulty ELM327 interfaces)
- https://www.multiecuscan.net/OrderMultiplexedPP.aspx
- https://www.multiecuscan.net/OrderMultiecuscanMS.aspx
- https://apps.apple.com/us/app/multiecuscan/id1436939705 (current supported-interface list)
- https://www.dicorse.com/shop/multiecuscan-software-and-hardware-options/ (.NET requirement)
- https://squadra-tuning.com/obd-tools/multiecuscan/
- https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80
- https://giuliatech.com/t/multiecuscan-mes-setup-and-connection-timeout-troubleshooting/114
- https://www.stelvioforum.com/threads/mes-multiecuscan-multiplexed-vs-registered-difference.22086/
- https://www.fiatforum.com/guides/multiecuscan-and-alfaobd-pids-for-x290-ducato.891/page/multiecuscan-template-examples.861/
- Local install inspected: C:\Program Files (x86)\Multiecuscan\ (MES 5.4, Multiecuscan.exe 2025-08-12, FES_Templates.ini, FES_Tags.ini, SCAN_*.txt, FESLog_*.txt, Files/data0*.dat, PdfSharp.dll, EULA.rtf)

**OBDLink / STN chip documentation (primary)**
- https://www.scantool.net/scantool/downloads/682/obdlink_frpm_f.pdf (FRPM rev F — main reference)
- https://www.scantool.net/scantool/downloads/678/obdlink_frpm_e.pdf (rev E)
- https://els27.ru/files/stn1100-frpm.pdf (STN1100 FRPM preliminary, 2010 — legacy STFAP naming)
- https://www.scantool.net/scantool/downloads/234/stn1100-frpm-preliminary.pdf
- https://www.obdsol.com/solutions/chips/stn1170/
- https://www.obdsol.com/solutions/chips/stn1110/
- https://cdn.sparkfun.com/datasheets/Widgets/stn1110-ds.pdf
- https://www.obdsol.com/downloads/stn1110_vs_elm327.pdf
- https://support.obdsol.com/support/solutions/articles/43000709894-get-started-with-logs
- https://www.scantool.net/obdwiz/
- https://www.obdlink.com/obd-apps/obdwiz-app/

**Vgate vLinker FS**
- https://vgatemall.com/products-detail/i-19/
- https://www.amazon.com/Vgate-vLinker-Adapter-FORScan-MS-CAN/dp/B094Z7PBLS
- https://www.obdii365.com/service/configure-forscan-for-vgate-vlinker-fs-interface.html
- https://www.obdii365.com/wholesale/vgate-vlinker-fs-elm327-for-ford-forscan.html
- https://forum.forscan.org/viewtopic.php?t=867 (FORScan J2534 support)
- https://forscan.org/forum/viewtopic.php?t=8510 (HS/MS-CAN relay mod)

**Security Gateway**
- https://www.alldata.com/us/en/support/diagnostics/article/fca-secure-gateway
- https://www.repairerdrivennews.com/2020/01/20/cic-emerging-tech-head-explains-fca-sgw-says-other-oem-firewalls-coming/
- https://www.youcanic.com/fca-security-gateway-module-explained-obd2-sgm-sgw/
- https://boschdiagnostics.com/ads-software/secure-gateway
- https://www.auteldealer.com/blogs/products-tutorial/fca-autoauth-what-it-is-how-to-use-it-with-your-autel-scanner
- https://www.tirereview.com/autel-autoauth/
- https://pro.repairsolutions.com/chrysler-secure-gateway
- https://shopeurocompulsion.net/blogs/installation-database/fca-sgw-module-bypass-installation-info
- https://shop.alfissimo.com/inicio/3132-alfissimo-sgw-bypass-security-gateway-bypass-alfa-romeo-giuliastelvio-.html
- https://www.giuliaforums.com/threads/multiecuscan-sgw-by-pass-lite-module-sblocco-proxy-2018-fca.42962/
- https://www.giuliaforums.com/threads/sgw-bypass-installation.56787/page-2
- https://www.klavkarr.com/blog/security-gateway-alfa-romeo
- https://www.obdii365.com/wholesale/obdstar-fcs-12-8-universal-adapter.html
- https://www.felkodslasare.se/en-en/collections/fca-group-sgw-bypass-adapter-12-8-pin-inkopplingsguide-steg-for-steg
- https://appcar-diagfca.com/en/diy/security-gateway-sgw-bypass/

**Giorgio platform: buses, pinout, cables, ECUs**
- https://www.alfa-romeo-portal.com/forum/thread/3284-obd-port-pinbelegung-giulia-stelvio/ (OBD pinout, CAN-C / CAN-IHS / CAN-CH)
- https://www.alfaowner.com/threads/lin-bus-connection-speeds.1210388/ (CAN-IHS 125 kbps)
- https://appcar-diagfca.com/en/supported-vehicles/alfa-romeo-stelvio/
- https://www.giuliaforums.com/threads/multiecuscan-cables-question.66547/
- https://shop.alfissimo.com/diagnostic-softwarehardware-multiecuscanalfaobd/3019-diagnostic-adapters-multiecuscanalfa-obd.html
- https://www.stelvioforum.com/threads/how-do-i-know-which-color-cable-adapter-to-use-with-the-multiecuscan-the-grey-and-or-the-blue-one.19445/
- https://alttune.com/upgrade-3-54-from-alientech (MED17.3.5 OBD protocol)
- https://www.go-parts.com/garage/transmission-assembly-alfa-romeo-giulia-alfa-romeo-stelvio-2017-2025 (ZF 8HP50)
- https://www.racelogic.co.uk/_downloads/vbox/Vehicles/Other/Docs/Alfa%20Romeo-Stelvio.pdf

**Open-source Giorgio / CAN projects**
- https://github.com/commaai/opendbc/pull/1251 (FCA Giorgio Stelvio)
- https://github.com/gaucho1978/BACCAble and https://www.tr3ma.com/baccable
- https://github.com/danardi78/Alfaromeo-Giulia-Stelvio-PIDs/
- https://github.com/ClaudeMarais/Simple_OBD2_for_AlfaRomeoGiulia
- https://github.com/beaups/giulia_ESCape
- https://github.com/CSS-Electronics/can-bus-reverse-engineering-skills
- https://github.com/iDoka/awesome-canbus
- https://github.com/collin80/SavvyCAN and https://www.savvycan.com/docs/scriptingwindow.html and https://www.savvycan.com/docs/connectionwindow.html

**Python / protocol libraries**
- https://udsoncan.readthedocs.io/en/latest/udsoncan/questions_answers.html
- https://udsoncan.readthedocs.io/en/latest/udsoncan/examples.html
- https://can-isotp.readthedocs.io/en/latest/
- https://can-isotp.readthedocs.io/en/latest/isotp/addressing.html
- https://python-can.readthedocs.io/en/stable/interfaces.html
- https://python-can.readthedocs.io/en/stable/interfaces/socketcan.html
- https://github.com/brendan-w/python-OBD/pull/122 (STN CR termination bug)
- https://python-obd.readthedocs.io/
- https://docs.kernel.org/networking/device_drivers/can/can327.html
- https://github.com/norly/elmcan
- https://github.com/Ircama/ELM327-emulator and https://pypi.org/project/ELM327-emulator/

**MCP servers**
- https://github.com/farzadnadiri/mcp-can and https://pypi.org/project/mcp-can/
- https://github.com/ayhammouda/obd-mcp-server and https://glama.ai/mcp/servers/ayhammouda/obd-mcp-server
- https://github.com/petrpatek/obd2-mcp-server
- https://github.com/castlebbs/Vehicle-Diagnostic-Assistant
- https://modelcontextprotocol.io/specification/2026-07-28

**AlfaOBD / OEM tools**
- https://www.alfaobd.com/AlfaOBD_Android_Help.pdf
- https://kb.fcawitech.com/article/mopar-diagnostic-pod-overview-983.html
- https://www.maverickdiagnostics.com/shop/oem-tools/diagnostic-pod/
