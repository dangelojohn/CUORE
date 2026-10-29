# AlfaOBD gap study for CUORE

Date: 2026-10-29. Research only. Outside facts carry a URL. INFERENCE marks my reading where sources are thin. CUORE facts come from docs/FEATURES.md, docs/project/MES_PARITY_PLAN.md, docs/project/CORPORATE_ACCEPTANCE_2026-10-29.md and the three gap notes (c9c9dd720c01 writes, dcb76d25442b reads, fc047a665508 features).

Rules held throughout: CUORE never learns a write by capturing AlfaOBD or MES; every write comes from a documented, authoritative source (now the manufacturer); no third-party purchases; paid tools are described neutrally.

## 0. What the sources do and do not give us

AlfaOBD publishes a general feature summary and a vehicle list, not a per-model function list. Its Windows help manual (https://www.alfaobd.com/AlfaOBD_Help.pdf, 19 pages, read as text) is generic: connection, adapters, live data, procedures. It names no Giulia, Stelvio, PROXI or paddle function. The vehicle list (http://www.alfaobd.com/supported_cars.html) lists the Giulia (2015+) and Stelvio (2016+) with a recommended adapter only. So the Giulia/Stelvio function detail below is owner-forum evidence, graded as such. The giuliaforums.com and stelvioforum.com threads now sit behind a paywall gateway, so some were seen only as search summaries.

## 1. AlfaOBD feature inventory (Giulia 952, Stelvio 949)

Source for the general list: https://www.alfaobd.com/. "2.0T?" means whether it applies to the 2018 Stelvio 2.0T (ECM Marelli, ZF 8HP, petrol). Tag: V = vendor statement, F = owner-forum report, M = a MES-sourced setting that AlfaOBD may also offer (INFERENCE, not shown for AlfaOBD).

**(a) Diagnostics**
1. ECU identification and system status read (V). 2.0T: yes.
2. Fault code read with probable causes, plus freeze-frame data (V). Yes.
3. Fault code clear and monitoring for new faults (V). Yes.
4. Live data across engine, transmission, body, dash, ABS and climate, with plots (V). Yes.
5. Active diagnostics (actuator-style tests) (V, generic wording; which tests exist for 949 is not published). Yes in principle.

The vendor does not list modules per car. INFERENCE: coverage is close to the MES 12-module reach, since both use the same CAN buses.

**(b) Adjustments and resets**
6. Service light reset (V). Yes.
7. Oil change reset (V). Yes.
8. ABS bleed (V). Yes.
9. Transmission calibration (V, generic; 8HP-specific scope unknown). Unclear.
10. DPF regeneration (V). No, petrol.
11. Air suspension maintenance (V). No.
12. Battery type setting, a body configuration byte (F: an owner changed it to AGM H8 in AlfaOBD then aligned in MES, https://www.giuliaforums.com/threads/what-are-proxi-parameters-for-agm-battery-on-giulia-2-2.65519/; byte layout from https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80). Yes.
13. TPMS reference pressures (M, RFHub adjustments, same giuliatech page). Likely yes.

Not found in any source I could open: injector coding, steering angle calibration, throttle relearn for 949. Treat as unknown, not as absent.

**(c) Configuration and coding**
14. Body computer "Car Configuration Change" tool, used to search settings by name (F: https://www.giuliaforums.com/threads/diy-add-paddle-shifters.44122/ and search summaries). Yes.
15. PROXI alignment (V names "Proxy alignment"; F: worked on Android with a vLinker and grey adapter, https://www.giuliaforums.com/threads/alfaobd-for-proxi-alignment.58085/; another owner reports AlfaOBD failing partway on some modules, same search). Yes, with caveats.
16. Paddle shifter Euro or North American behaviour (F, see section 3). Yes.
17. Cornering lights present (M, byte 149, one user saw no effect). Trim dependent.
18. Race mode / DNA selector behaviour (M, byte 88). Unclear.
19. ACC+ adaptive cruise (M). Hardware dependent.
20. Window comfort open/close (M). Likely.
21. After-wipe (M, byte 126 bit 5). Likely.
22. Seat belt chime off (M, cluster adjustments). Likely.
23. Compass display (F, named in https://www.giuliaforums.com/threads/alfaobd-and-multiscanecu-some-alfaobd-settings-i-was-surprised-by.55899/, seen as a search summary only). Unclear.

DRL, auto door lock, Start&Stop memory, mirror fold: no source I opened lists these for the 949 or 952. One forum summary says disabling Start&Stop is not possible by coding (older cars, may be out of date). Do not promise them.

**(d) Key and immobiliser**
24. Electronic key and RF remote programming "on some models" (V). The vendor does not say Giulia or Stelvio. A parts listing shows key programming on Giulia 2018+ and Stelvio 2019 to 2023 needs the gateway bypassed (https://shop.imlss.com/item_view/item/601163). Unconfirmed for AlfaOBD.

**(e) Adapters and Secure Gateway**
25. Adapters: OBDLink MX+, EX, LX, CX; ELM327 1.3 or later; OBDKey; Kiwi 3 on Android; J2534 on Windows (V, https://www.alfaobd.com/). Giulia and Stelvio need the "grey" adapter for the second high-speed CAN bus; some interfaces (OBDLink MX+/EX, Vgate vLinker MS) do not need the blue adapter (V).
26. Secure Gateway: the vendor says 2018 and later cars need a hardware bypass, carrying pins 12 and 13 on Giulia/Stelvio (V, same page). On this car: not gating (local evidence). MES wrote to the ECM with no bypass or authentication (docs/research/CONNECTIVITY_AND_SGW.md section 2), so the vendor banner is range-wide, not a finding for this VIN. The A5 and A6 cables are bus-access cables.

**(f) Platforms and price.** Windows 7 to 11, Android, and Mac via Windows virtualisation; not iOS. One-time paid licence per platform with a limited free demo, no VIN lock (V, https://www.alfaobd.com/download.html).

**Count: 26 items inventoried** (5 diagnostics, 8 adjustments, 10 configuration, 1 key, 2 adapter/gateway; platforms and price not counted). Of these, 14 are vendor statements, 6 have Giulia or Stelvio owner evidence (12, 14, 15, 16, 25, 26), and 2 do not apply to the 2.0T (10, 11).

## 2. Gap table

CUORE today (from FEATURES.md and the gap notes): reads and diagnosis are strong; nothing on the write side executes. 0x27 and 0x2E are refused by design. Usable modules: ECM, TCM, BCM, IPC, RFHUB (ABS identity only). The Mods page holds a "do it in MES" handoff card and records that it was done.

| AlfaOBD | MES | CUORE today | What closes it |
|---|---|---|---|
| ECU ID and status (1) | 12 modules reached | 5 modules; identity DIDs only | Manufacturer: module addresses and DID lists; car session to confirm responders |
| Fault read, freeze frame (2) | Decoded, all reached modules | Full for ECM/BCM snapshots; others raw bytes; ABS codes never read | Manufacturer: 19 04 snapshot layouts, DTC text; car session on grey cable |
| Clear and new-fault watch (3) | Clear plus Monitor DTCs | Clear is MCP only with consent, no web button; live new-code alert built | Owner decision on a web clear button |
| Live data and plots (4) | 133 ECM names | About 31 ECM DIDs, 1 confirmed scale; gauges, graphs, tags built | Manufacturer: DID scaling |
| Active tests (5) | EVAP, EGR, wastegate, vacuum valve done | Replay engine, zero procedures | Manufacturer: routine identifiers and conditions |
| Service reset (6) | Done on the car 4 times | Definition file, empty steps | Manufacturer procedure, then dry run, gate, consent, read-back |
| Oil reset (7) | Done, engine running | Same; interlock needs engine off | Manufacturer procedure (states the engine condition) |
| ABS bleed (8), transmission calibration (9) | ABS reached | Not present | Manufacturer procedure; ABS reads first |
| Battery type (12) | PROXI byte 63, stays in MES | Cannot read byte 63; handoff card only | Manufacturer configuration data; owner decision made 2026-10-29 to move it in |
| TPMS pressures (13) | RFHub adjustment | Absent | Manufacturer data |
| Config change tool (14) | Adjustments screen (F7) | Adjustments screen absent | Build once data arrives |
| PROXI alignment (15) | CAN Setup procedure | Stays in MES; no roster for this car | Manufacturer procedure and node roster; owner decision made 2026-10-29 |
| Paddle EU/NA (16) | Byte 156 bits 4-5, single-source | No DID, no read; handoff card | Section 3 |
| Other options (17 to 23) | Present as bytes | Absent | Manufacturer option list, per market |
| Key and remote learning (24) | Security code entry | Absent; 0x27 refused | Manufacturer security access and procedure; owner decision made 2026-10-29 |
| Adapters (25), SGW (26) | A5 and A6 cables | Same cables; scan answered 5 of 25 rows; SGW not gating this car (local evidence) | Manufacturer: supported interface list |
| Windows, Android (f) | Windows | Web app, phone-first | Already done |

**Five biggest gaps for AlfaOBD parity:** (1) PROXI read, alignment and a verified read-back; (2) service and oil resets; (3) the coding option set with market presets (paddle, battery, cluster and body options); (4) key and remote learning with security access; (5) module reach and actuator tests, which depend on gateway access and routine identifiers.

## 3. Paddle shifter usage, Euro vs North American

**What changes.** Per the giuliatech compilation (https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80, repeating a giuliaforums.com post of 2024-04-05 by FizzGiGG), the setting is in the Body computer, CAN Setup, byte 156, bits 4 and 5. Euro value is `xx00xxxx`, North American is `xx01xxxx`. Euro behaviour: [+] shifts P or R into D, and [-] with [+] shifts to N. A PROXI alignment is required afterwards. AlfaOBD route, per one owner on a 2017 QV (search summary of https://www.giuliaforums.com/threads/diy-add-paddle-shifters.44122/): Android, Body computer, Car Configuration Change, search "paddle". Another post says a logic 0 enables EU control (https://www.giuliaforums.com/threads/alfaobd-and-multiscanecu-some-alfaobd-settings-i-was-surprised-by.55899/). A Stelvio thread says it works as on the Giulia (https://www.stelvioforum.com/threads/neutral-with-the-paddles.18171/; gateway-blocked, summary only).

**Module.** Body computer (BCM), not TCM or ESM; our own research agrees (docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md, graded SINGLE-SOURCE).

**Risks.** The same author warns that neighbouring bits control other settings. A PROXI mismatch is the larger risk: the BCM holds the configuration and downstream modules compare to it; our repo notes a TCM P1500 limp-in on mismatch (docs/design/CUORE_ADJUSTMENTS_PLAN.md, Part 2) and an alignment failure on a wrong or silent module (same document). Owners also report alignment timing out on a Bluetooth adapter (https://www.multiecuscan.net/forum/viewtopic.php?p=29086, one user). INFERENCE: byte 156 is a vendor-tool index, not a published DID, so it may differ by build year and trim.

**What CUORE needs from the manufacturer to do it properly.**
1. The documented configuration (PROXI) data map for the 952 and 949: the identifier or block, option names, allowed values, and which bits are paddle behaviour per market and model year.
2. A read method for the current value, so a before and after can be proven.
3. The alignment procedure: preconditions (battery support, engine off), module roster rules, failure handling, and the restore path for a backed-up configuration.
4. Which trims carry paddles, and the market codes that decide the default.
5. Written authority for CUORE to write it, then the existing path: dry run, gate, typed consent, read-back, audit.
Until then the Mods handoff card stays.

## 4. What CUORE offers that AlfaOBD and MES do not

Already built (FEATURES.md): the job and hypothesis workflow with verdict gate and proof of repair; a fault board with a one-tap Fixed flow; the TSB cross-reference with a stated reason per link; systems dependency map and electrical paths; the parts catalogue (Mopar data kept out of git); dealer integration through AlfaCore bundles; a feedback store where mechanics correct CUORE; multi-marque theming driven by data; scan health grading and diffs; the symptom timeline with media. MES has none of the workflow layer (note fc047a665508). AlfaOBD's published material shows no such layer (INFERENCE).

Further offerings that follow from manufacturer backing:
1. **Official DTC text and procedures with citations.** Each code shows the manufacturer's description and repair procedure with its document and date. This replaces inferred text.
2. **Fleet learning across cars of one model.** Confirmed decodings and repair outcomes carry to the next same-model car, with the source car recorded. Needs consent terms between shop and dealer.
3. **Customer-to-dealership technical interaction.** The owner page feeds the technician's picture of the complaint and carries questions back. This matches the owner's stated purpose.
4. **Warranty audit trail.** Every read, procedure, consent and read-back is dated and signed to a technician, ready for a claim. The audit log exists; the claim format needs the manufacturer.
5. **Market-correct configuration presets.** The Euro or North American option set is offered only where the manufacturer allows it for that VIN and market, with the documented value and restore.
6. **Pre-wiTECH hand-off pack.** One document with evidence, ranked hypotheses and open questions, so the wiTECH session covers only what needs it. This is the owner's positioning.
7. **Official bulletin and recall status per VIN.** Checklists use manufacturer data, not a hand-built catalogue.
8. **Procedure currency.** When the manufacturer revises a procedure, CUORE flags jobs that used the old one.

## 5. Adoption: what mechanics said

From the repo's own mechanic reviews (docs/research/MECHANIC_REVIEW_2026-10-08.md and MECHANIC_REVIEW_7_2026-10-14.md, plus the 2026-10-29 dealer demo in the corporate acceptance record):
1. **Never crash.** One tab click broke every page and the tester "would not use it today". Stability gates adoption.
2. **Say what to do next.** The review wanted the next action in zero taps and zero scrolls, with a verdict that names the next test.
3. **Never contradict itself.** Hero, step 3 and step 4 disagreed on the same screen. One state, one answer.
4. **Glove-friendly and short.** Big tappable chips, now-by-default dates, no retyping the odometer, collapsed lists, minimal repeated chrome.
5. **Show where it is.** Juniors praised "open in layout" and seniors "Electrical path for:" (corporate acceptance record). The dealer's mechanics "loved" the demo.

For AlfaOBD users specifically (INFERENCE): they come for resets and coding, so the first adoption test is whether a service reset and a PROXI check work end to end, with read-back, on a real car.
