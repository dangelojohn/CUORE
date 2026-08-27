# Connectivity, Protocol and Security Gateway — 2018 Stelvio

**Captured:** 2026-08-27. Local findings marked `CONFIRMED (local)`; web findings carry their source.
No primary FCA service document was obtainable (all behind Stellantis IOP paywall).

---

## 1. THE HEADLINE: why only 8 modules appear in a scan

**It is not SGW, and it is not an MES coverage gap. It is physical bus access.**

> "The Giulia and Stelvio uses **3 separate CAN systems**… The main system is on **pin 6 and 14** and can be reached directly with any ELM327 interface… To reach the other 2 CAN busses **adaptor cables are needed**. These adaptor cables redirect to **pin 12-13 and 3-11**. … In case of the Giulia and Stelvio you need the **grey and the blue** cable."
> — [squadra-tuning.com](https://squadra-tuning.com/obd-tools/multiecuscan/)

AlfaOBD concurs: Giulia/Stelvio "require the 'grey' adapter … to access the second high-speed CAN bus … connected to the **pins 12 and 13**", with an exception for OBDKey multipin and **Vgate vLinker MS**, which switch pins internally.
— [alfaobd.com](http://www.alfaobd.com/index.html)

| OBD-II pins | Bus | Reachable with a plain ELM327? |
|---|---|---|
| **6 / 14** | main CAN-C | **yes** |
| **12 / 13** | second HS-CAN | no — needs the **grey** adapter |
| **3 / 11** | third bus | no — needs the **blue** adapter |

MES *does* list ABS MK C1, Bosch Airbag, ZF Electric Steering, TRW climate and the AlfaConnect radio for Stelvio. Their absence from the scan is purely that a plain ELM327 on pins 6/14 sees only CAN-C modules.

> **This is a hard ceiling on any software tool. No amount of code reaches those modules without an adapter cable or a multiplexing interface.**

### Consequence for the communication-fault cascade

The pervasive U/C lost-communication DTCs — BCM `U1711/U1712/U1713/U1716`, IPC `B1029`, DTCM `U0100`, DASM `C1403/C1408/C1431/C141C` — **name exactly the modules on the unreachable buses**. `DTCM U0100` reappearing immediately after a successful clear suggests a **key-on-engine-off scanning artifact**.

> **Recommendation: do not chase these as faults without a key-on-engine-RUNNING rescan.**

This refines rather than contradicts the "one network event, not five faults" rule in `CORPUS_BASELINE.md` — it supplies the likely mechanism.

---

## 2. Security Gateway — resolved

### A premise that needed correcting

Inferring "SGW is not gating this car" from clears succeeding on BCM/IPC/DTCM/RFHUB/DASM does **not** hold on its own: **MES only attempts a clear on modules that actually had stored faults.** ECM, TCM and ESM were clean, so no clear was attempted there. Those SCAN logs say nothing about powertrain writes.

### The decisive local evidence

`FESLog_2608271119_...Stelvio...txt` — no simulation marker, VIN `ZASFAKPN5J7B88115`, module = **Magneti Marelli IAW 10JA, the Engine ECM**: DTCs read, `CLEARING STORED FAULT CODES...`, re-read `No fault codes`, then an actuator command.

Across other real sessions on the ECM: `Evaporation control valve → COMPLETED` (x3), `Wastegate solenoid valve → COMPLETED`, `Turbo vacuum valve → COMPLETED`, `Replacement of turbocharger → COMPLETED`, `Overboost counter reset → COMPLETED`; on the IPC `NEXT SERVICE KM RESET → COMPLETED`.

> **`CONFIRMED (local)`: MES performs full bidirectional writes to the powertrain ECU on this car — DTC clearing, physical actuator commands, adaptation routines — over an ELM327-class adapter, with no bypass cable and no authentication step anywhere in the logs.**

The one failure rules out a security explanation: `Fan 1st speed → FAILED TO EXECUTE / Engine running` is the ECU refusing on a **precondition** (UDS NRC `0x22 conditionsNotCorrect`), not a gateway refusing on authorization. A gateway block would not be engine-state-dependent and would not pass the neighbouring wastegate and EVAP commands.

### Why the vendor flag says otherwise

MES's page carries a **single global banner over the whole 2018-2025 range**, not a per-VIN determination:

> "…**It is not possible to unlock the SGW module with Multiecuscan.** … The 2018+ models with confirmed presence of SGW are: 500X/Renegade, 500L MCA, Doblo, **Giulia/Stelvio**."
> — [multiecuscan.net/SupportedVehiclesList.aspx](https://www.multiecuscan.net/SupportedVehiclesList.aspx)

**The actual fitment cutoff is a production date, not a model year** (`CONFIRMED`, from bypass-maker fitment data, Stuff4Car P/N `SGB0001.B01`):

> "Giulia, Stelvio (NAFTA: **2.2018+** / EMEA **4.2018+** production including MY2020-26)"

MY2018 Stelvio production began in **2017**, so a "2018 Stelvio" straddles the cutoff.

A direct trade source examining a **2018 Stelvio** (`CONFIRMED`, professional publication): *"This particular model does not have a Secure Gateway Module (SGW)."* — the technician used **MES + OBDLink MX+** to reset the service interval through the IPC, no bypass, no AutoAuth.
— [automotivetechinfo.com, March 2022](https://automotivetechinfo.com/2022/03/how-to-scan-a-2018-alfa-romeo-stelvio/)

**Verdict:** NAFTA Giulia/Stelvio got SGW from **Feb-2018 production**. This car is either a pre-02/2018 build, or its SGW was removed/disabled.

### Cheapest read-only checks if certainty is wanted
1. **Driver's door-jamb build date** — before 02/2018 predicts no SGW.
2. **Look for the module** — lower dash, right of/below the steering column (2018-2019); 12-pin + 8-pin connectors.
3. **Read the PROXI/BCM configuration** in MES for an SGW flag.

### Reference details
- Bypass part numbers: Stuff4Car `SGB0001` / `SGB0001.B01`; Centerline `FI504` (~$59.95); GaleMotorsport `GMSQIUSTESGWBP` (~EUR 49). Passive block linking the two harness plugs. **Not compatible with 2021+** where SGW is integrated into the BCM.
- **AutoAuth covers Alfa Romeo MY2017+.** Standard **$5/month billed annually**; open to shops and individual technicians. **MES cannot use AutoAuth** — its only sanctioned routes are a hardware bypass or tapping CAN behind the gateway.
- *What NRC an SGW returns when blocking is* **UNRESOLVED** *— no source gave UDS-level detail. Behaviourally, generic OBD Modes 01/03 keep working and clearing is the specific thing blocked.*

---

## 3. The DTC suffix proves UDS, and it matters

MES DTCs carry a two-hex-digit suffix: `P0455-00`, `U0100-87`, `C141C-86`, `U1713-2F`, `B1029-64`, `B1176-97`. These are **UDS DTC failure-type bytes** (ISO 14229-1). Note `C141C` — a **five-character** code, inexpressible in the legacy 2-byte OBD DTC format.

> **Manufacturer-level diagnostics use UDS 3-byte DTCs read via service `0x19`, not legacy Mode 03.** A Mode 03/07/0A path can only ever see the emissions subset on the ECM and is **structurally incapable** of reading the body/chassis DTCs MES surfaces.

### UDS services, read/write classified

| Service | Purpose | Effect |
|---|---|---|
| `0x10` DiagnosticSessionControl | session selection | **state change** |
| `0x3E` TesterPresent (`3E 80`) | keep-alive, S3 ~5 s | benign, sustains session |
| `0x14` ClearDiagnosticInformation | per-module DTC clear | **WRITE** |
| `0x19` ReadDTCInformation (`01`/`02`/`04`/`06`/`0A`) | counts, lists, snapshots, extended data | **READ-ONLY** |
| `0x22` ReadDataByIdentifier (`F190` VIN, `F187` part, `F195` SW) | identity/data | **READ-ONLY** |
| `0x2F` InputOutputControlByIdentifier | actuator tests | **WRITE — moves physical hardware** |
| `0x31` RoutineControl | EVAP tests, adaptations | **WRITE** |
| `0x27` SecurityAccess | seed/key, lockout on failures | gate |
| `0x2E`, `0x34`/`0x36`/`0x37` | writes, reflashing | **WRITE — can brick a module** |

NRCs worth handling: `0x11`, `0x12`, `0x13`, **`0x22` conditionsNotCorrect**, `0x31`, `0x33`, `0x35`, and **`0x78` responsePending** (must be awaited, not treated as failure — a common client bug).

**FCA body-module CAN IDs remain `UNCERTAIN`.** MES logs a per-module "ISO Code" (ECM `00 01 50 40 18`, BCM `00 00 70 7C 15`, DASM `00 39 70 7E 15`) and byte 2 plausibly encodes an address, but no source confirms it. **Derive empirically; do not guess.**

---

## 4. Adapter hardware on this machine

| Port | Device | Status |
|---|---|---|
| **COM3** | `VID_0403+PID_6015` — **FTDI FT231X**, descriptor `"vLinker FS"` | **Present, OK, CM_PROB_NONE** |

- **The counterfeit-chip risk does not apply here.** No Prolific or CH340 device exists on this machine. The FTDI part binds FTDI's current signed driver (`FTSER2K` v2.12.36.20, 2024-10-27) — the practical authenticity test, since FTDI's driver actively non-functions counterfeits.
- **Also installed:** Drew Technologies **Mongoose-Plus Chrysler2 J2534 driver** (hardware NOT connected — the official FCA cable for wiTECH 2.0); **StnFirmwareUpdater 2.4.1.0** and **OBDwiz 4.35.0** (both ship with **STN-chipset OBDLink** adapters, so one is likely on hand); J2534Toolbox 3.
- `.venv` has **pyserial 3.5 only** — no python-OBD, python-can, udsoncan, can-isotp, cantools, or J2534 binding.

### The vLinker FS is the wrong variant for this vehicle

MES's supported list names **"Vgate vLinker"**, and singles out the **vLinker MS** as "the only supported Bluetooth interface that can reliably perform PROXI alignment and other special procedures."

But the **FS is Vgate's Ford/Mazda/Lincoln/Mercury product** — headline features are Ford MS-CAN and FEPS 18 V on pin 13; its named partners are FORScan and ELMConfig, not MES.

| | **FS** (yours) | **MS** (MES-endorsed) |
|---|---|---|
| Target | Ford / Mazda / Lincoln | **FCA / Fiat / Alfa** |
| CAN channels | HS-CAN + Ford MS-CAN | **five: HS, MS, SW, CH, LS-CAN** |
| MES status | not named | named for PROXI alignment |

One nuance worth testing: the FS's Ford MS-CAN switching targets **pins 3/11**, which *is* one of Giorgio's extra buses, so it may reach that bus even though it cannot reach 12/13 (`UNCERTAIN`).

**Troubleshooting note** (`CONFIRMED`, FORScan admin announcement): the vLinker FS USB was removed from FORScan's recommended list over stability issues traced to **USB 3.0 hubs lacking full USB 2.0 backwards compatibility**; workaround was a **USB 2.0 hub**. Reinstated 30 May 2025. If COM3 goes flaky, try a USB 2.0 hub before blaming software.

### Adapter tiers

- **ELM Electronics ceased operations in 2022** — every new "ELM327" is a reimplementation, and the advertised version string is the least reliable datum about it. Typical clone defects: no-op `ATCRA`/`ATFCSH`/`ATFCSD`/`ATFCSM` (ISO-TP breaks), ~256-512 B buffers, `ATSH` accepted but ignored, broken 29-bit addressing.
- **STN (STN1110/1170/2100/2120)** — ELM327-command-compatible, 16-bit core, UART to 10 Mbps, large buffer, field-reflashable; **STN2120 adds SW-CAN and MS-CAN**. The ST command set adds hardware pass/block filters, filtered monitoring, single-shot extended transmit (`STPX`), and `STDI` real device identification. **This is the tier at which multi-ECU work stops being flaky.**
- **J2534 PassThru** — an API, not a serial protocol. Multiple concurrent channels, message-layer arbitration, module reprogramming.
- **MES supports neither J2534 nor DoIP** (`CONFIRMED` by omission). AlfaOBD does support J2534, CAN-only.

---

## 5. Two apps cannot share COM3 — confirmed twice

Microsoft's `CreateFileA` docs: for communications resources "the *dwShareMode* parameter must be **zero (exclusive access)**". pyserial hard-codes exactly that (`serialwin32.py:54-60`, comment `# exclusive access`). The second opener gets `ERROR_ACCESS_DENIED` (Win32 5).

**Splitters (com0com, Eltima) do not help.** The failure is at the protocol layer: ELM327 is a strict half-duplex, stateful, single-master REPL. Commands interleave and produce `?`; responses broadcast to both clients and get silently misattributed; and `ATSP`/`ATSH`/`ATCRA`/`ATFC*`/`ATH`/`ATAT`/`ATST` are **device-global**, so one client silently destroys the other's session setup. On a device that can command actuators, misattributed responses are a **safety** problem. Splitters are for one master plus one passive sniffer.

**No consumer adapter exposes two independent masters** — behind any transport there is one interpreter core, one protocol state machine, one header register, one filter set.

### Correct handoff pattern

1. **Let the current operation finish** — never interrupt mid-actuator-test; that can leave an ECU with control overridden.
2. **Fully exit MultiEcuScan.**
3. **Pause 1-2 s** — a crashed Python process holds COM3 until it dies.
4. **Wait out the vehicle-side session.** If MES left a module in an extended session with TesterPresent, that persists on the **ECU** with S3 ~5 s. Wait >5 s, or send `10 01` before disconnecting. Otherwise the next tool gets "wrong session" NRCs it cannot explain.
5. **Reset the interpreter; never inherit state.** `ATWS`, then re-issue the entire init.
6. **No background TesterPresent loop** while MES is active.
7. **Structural fix:** open the port lazily per operation and close immediately, rather than holding COM3 for the server's life.

---

## 6. ELM327 reliability engineering

- **Pin the protocol.** `ATSP0` re-searches every connect. `ATDPN` once, then `ATSP6`.
- **Adaptive timing.** `ATAT0` off / `ATAT1` adaptive (default) / `ATAT2` aggressive. Pair `ATAT0` with explicit `ATST hh` (x4 ms) for deterministic manufacturer queries.
- **`ATH1` is mandatory** for multi-ECU work — it prepends the responding CAN ID.
- **Flow control** for multi-frame to non-OBD modules: `ATFCSH`/`ATFCSD`/`ATFCSM1` plus `ATCFC0/1`.
- **Receive filters** `ATCRA`/`ATCF`/`ATCM` — essential on a busy bus; where STN's multiple hardware filters beat ELM327's single mask.
- **`ATS0` vs `ATS1` changes tokenization** — see the parser bug in `OBD_SERVER_AUDIT.md`.
- **Never swallow:** `BUFFER FULL`, `CAN ERROR`, `BUS BUSY`, `STOPPED`, `NO DATA`, `UNABLE TO CONNECT`, `?`, `<DATA ERROR`.
- **Prefer `ATWS` over `ATZ`** on reconnect — faster, and on some clones `ATZ` resets the UART to 38400 and you lose the port at a non-default rate.

### Do NOT lower the FTDI latency timer

MES's own documentation says latency and buffer settings should be changed **only** for KKL interfaces — "For ALL other types of interface these should **NOT** be changed!" ([multiecuscan.net/HowToUse.aspx](https://www.multiecuscan.net/HowToUse.aspx)). FORScan recommends the opposite. The setting is **per-device and global** — it cannot be scoped to one tool.

Since MES does the consequential work on this car and the cost of 16 ms is bounded (~0.16-0.8 s across a 10-50 request burst), **leave `LatencyTimer` at 16.** USB selective suspend for COM3 is separate and safe to disable.

---

## 7. Open items

1. **Whether this car has an SGW** — provenance only; capability is settled. Door-jamb build date is the cheapest check.
2. **UDS-level SGW behaviour** (`0x33` vs silent drop) — no source found; moot here.
3. **FCA body-module CAN ID table** — blocks per-module UDS work. Derive empirically.
4. **STN Family Reference & Programming Manual** — all PDF paths 403/404. Needed before coding to specific ST commands.
5. **MES forum sticky "FAULTY ELM 327 INTERFACES DE-MYSTIFIED"** (`forum.multiecuscan.net/viewtopic.php?f=5&t=1493`) — login-gated; the user has a licence.
6. **Whether MES holds COM3 for its whole session** — 30-second empirical test.
7. **Whether the FS's Ford MS-CAN switching reaches Giorgio's pins 3/11 bus** — testable, would partially offset the wrong-variant problem.

**Source-quality flags:** stelvioforum.com and giuliaforums.com sit behind a Tollbit paywall (HTTP 402) and were readable only through a text-extraction proxy — those details are second-hand. Bypass-vendor fitment dates are commercially motivated but consistent across independent sellers. vgatemall.com performance claims are unverified marketing.
