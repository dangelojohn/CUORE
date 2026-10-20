# Glossary

The project's own glossary is [docs/project/GLOSSARY.md](https://github.com/dangelojohn/CUORE/blob/main/docs/project/GLOSSARY.md). This page covers the terms used across the wiki.

## Car, buses and modules

| Term | Meaning |
|---|---|
| **Giorgio** | The rear-drive Alfa Romeo platform under the Giulia and Stelvio; the Maserati Grecale shares it. |
| **GME T4** | The 2.0 L turbocharged four-cylinder engine family. |
| **OBD port** | The diagnostic connector (SAE J1962), 16 pins. |
| **CAN** | Controller Area Network, the vehicle bus. |
| **CAN-C** | Diagnostic/powertrain bus, pins 6/14, 500 kbit/s. Reached with no cable. |
| **CAN-IHS** | Body/comfort/infotainment bus, pins 3/11, 125 kbit/s. Blue A5 cable. |
| **CAN-CH** | Chassis/ADAS/safety bus, pins 12/13, 500 kbit/s. Grey A6 cable. |
| **A5, A6** | The MES bypass cables, blue and grey. |
| **SGW** | Security Gateway module between the OBD port and the vehicle networks on newer cars. |
| **11-bit / 29-bit** | CAN identifier widths. Giorgio broadcast traffic is mostly 11-bit; diagnostic requests use 29-bit addresses. |
| **ECM** | Engine control module. |
| **TCM** | Transmission control module (ZF 8HP). |
| **BCM** | Body control module (a Marelli 949 that is also the gateway between buses). |
| **IPC** | Instrument panel cluster. |
| **RFHUB** | Radio frequency hub (keys and tyre pressure). |
| **DTCM** | Transfer case module (Q4 all-wheel drive). |
| **ESM** | Electronic shift module. |
| **DASM** | Driver-assistance (radar) module. |
| **ABS, EPS, ORC** | Anti-lock brakes, electric power steering, airbag/occupant restraint. |
| **AFLS, PAM, HALF** | Adaptive headlights, parking assist, lane-feedback camera. |
| **ESIM** | Evaporative system integrity module: a part in the EVAP vent path containing a vacuum-operated switch and two weighted valves. |
| **EVAP** | Evaporative emissions: the fuel-vapour control system. |
| **Purge valve** | The engine-side valve that draws vapour from the canister into the intake. |
| **Canister** | The charcoal vapour storage unit. |
| **P0440, P0455, P0456** | General EVAP fault, large leak, small leak. |

## Protocols

| Term | Meaning |
|---|---|
| **UDS** | Unified Diagnostic Services (ISO 14229). Services used read-only here: `10 01`, `19`, `22`, `3E`. |
| **DID** | Data identifier read with service `22` (for example `F190` = VIN). |
| **DTC** | Diagnostic trouble code. A UDS DTC carries a failure-type suffix, for example `U1713-2F`. |
| **Status byte** | The eight bits ISO 14229 attaches to each DTC; see [[Evidence Model|Evidence-Model]]. |
| **Freeze frame** | A snapshot of conditions when a code set (UDS `19 04`). |
| **ISO-TP** | Multi-frame transport over CAN. |
| **Mode 01/03/06/07/09/0A** | Legislated OBD modes: live PIDs, stored codes, on-board test results, pending codes, vehicle information, permanent codes. |
| **PID** | Parameter identifier in Mode 01. |
| **Readiness** | Whether each emissions monitor has completed since the last clear (Mode 01 PID 01) and this drive cycle (PID 41). |
| **Mode 06** | The computer's own measured test results with limits. |
| **OBDMID, TID, UASID** | Monitor id, test id, unit-and-scaling id in a Mode 06 record. |
| **STN / ELM327** | Adapter command sets. STN adds hardware filters and monitoring. |
| **STP / STPBR / STMA / ATCAF** | STN protocol select, bit rate, monitor-all, CAN auto-formatting. |
| **Keep-alive id** | A periodic network-management frame (`1E34xxxx`, `1E36xxxx`). |

## Codes and the 2026-10-20 review

| Term | Meaning |
|---|---|
| **FTB (failure type byte)** | The two-character suffix of a UDS code, for example `-87` in `U1700-87`. As used in this project's sources: `86` signal invalid, `87` missing message, `2F` erratic, `64` plausibility, `97` operation obstructed or blocked. The meanings are from a trade article and a page for another car in the group, not the paid SAE list ([[Network and Brake Findings|Network-and-Brake-Findings]]). |
| **NCM, NFR, NGE, NBC** | Legacy node labels printed in code texts: engine computer, brake module, electric steering, body computer. Their use on this platform is inferred; the scan tool's printed label is the only definition for this car. |
| **Code finding** | The stored review of one code: meaning, readings, owner statement, classification, ladder, proof, literature ([[Code Reviews|Code-Reviews]]). |
| **Resolution ladder** | Ordered steps to settle a code, cheapest and read-only first, never a clear. |
| **Proof of fix** | The reading that would settle a code: absent on reads spread over longer than its longest observed gap, with status bytes read before any clear. |
| **Real / service-induced / probable artefact / possible bystander / downstream / readiness flag** | The classes a code is given. Downstream means a receiver of another module's bad signal, so it is not fixed on its own. |
| **Tool artefact** | A code set by the tool's own activity (for example the 2026-10-14 night incident), not by the car. |
| **BCM cluster** | The group of codes in which the body computer is on one side of every complaint ([[Network and Brake Findings|Network-and-Brake-Findings]]). |
| **Readiness flag (`0x40`)** | A status byte with only bit 6 set: the test has not completed this cycle. Not a fault. |
| **Mirror snapshot** | One session reading every module that reports on the body computer, with full status bytes, while a cluster code is active. |
| **SAFETY flag; attested resolved** | Marks on a hypothesis: it concerns a safety system; the owner states it is resolved, which is attested, not read. |
| **`event_date`** | The date an action actually happened, as opposed to when it was recorded ([[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]). |
| **ETM** | The radio, navigation and telematics head unit. |
| **PROXI** | The vehicle configuration record in the body computer; a mismatch code says a component does not match it. |
| **MDH** | A build-date code on the car's label that decides which bulletin applies. Not recorded for the reference car. |
| **Recall number / CSN** | Safety recall (for example `18V205`) and customer-satisfaction notification; both settled per car only by a VIN lookup ([[Recalls and Campaigns|Recalls-and-Campaigns]]). |

## Passive decoding, addressing and the adapter

| Term | Meaning |
|---|---|
| **DBC** | A CAN database file naming messages and their signals (start bit, length, scale, unit). |
| **opendbc** | A public project whose MIT-licensed `fca_giorgio.dbc` CUORE keeps a copy of ([[External References and Licences|External-References-and-Licences]]). |
| **Passive chassis decode** | Listen-only decoding of chassis-bus broadcasts through that database ([[Passive Chassis Decoding|Passive-Chassis-Decoding]]). |
| **Lead** | An outside fact, unverified on this car; never proof. |
| **`rx_mode`** | Reply-id convention for the 11-bit discovery sweep: request plus 8, request minus `0x280`, or both. |
| **`probe_dids`** | The identifiers the 29-bit discovery sweep asks per target (default `F190`; `F132` and `F194` optional). |
| **Broadcast id** | A periodic message the car sends itself; CUORE never transmits a request on one. |
| **Flow control** | The multi-frame handshake settings of the adapter (header, data, mode) that must be restored when leaving a physical target. |
| **`stale_input`** | An audit event: a complete reply was found in the input before a new request, and discarded. |
| **Hard reset** | An opt-in adapter warm start (`ATWS`) with re-initialisation, once per session. |

## Tools and software

| Term | Meaning |
|---|---|
| **MES** | MultiEcuScan, a Windows diagnostic tool for Fiat-group cars. |
| **FES log** | An MES engineering-session log. |
| **SCAN log** | An MES full-scan report. |
| **wiTECH** | The manufacturer's dealer diagnostic tool. |
| **SLVT** | Small leak verification test, a dealer-tool procedure (bulletin 18-048-23). |
| **TSB** | Technical service bulletin. Also recalls, customer-satisfaction notices (CSN), campaigns. |
| **MCP** | Model Context Protocol, the way an assistant calls tools. |
| **Bridge** | A `cuore/services/*_bridge.py` module producing the view model for a page and its API route. |

## CUORE concepts

| Term | Meaning |
|---|---|
| **Observation** | One stored read from the car with time, bus, cable and stream. |
| **Attested input** | A human-entered record (symptom, note, feedback, photo, owner event). Never a measurement. |
| **Evidence gate** | The rule that refuses a confirmed verdict until the fault is demonstrated from captured data. |
| **Verdict** | ACTIVE FAULTS, UNVERIFIED REPAIR, VERIFIED CLEAN or NO DATA, computed, never hand-written. |
| **Job** | One visit's record: complaint, hypotheses, actions, verification. |
| **Case** | A closed job kept as memory for the next car. |
| **Analogue** | A sibling-engine bulletin, labelled as not a bulletin for this car. |
| **Declared cable** | The bypass cable the operator says is fitted: `none`, `blue_a5` or `grey_a6`. |
| **Coverage / not reachable** | Which modules answered, and which were on a bus never read. |
| **Handoff card** | The step-by-step for a task done in MES (module, menu path, prerequisites), recorded in CUORE afterwards. |
| **Tell CUORE** | The phone page for attested owner input. |
| **[E] / [I] / [N]** | Evidence, inference, not known. |
| **CONFIRMED / CORROBORATED / SINGLE-SOURCE / UNKNOWN** | Confidence grades for table rows. |
