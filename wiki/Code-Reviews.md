# Code Reviews

On 2026-10-20 every fault code on the reference car that is **not** an EVAP code was reviewed against the car's own logs and against outside literature. This page is the summary, by system. It keeps three kinds of statement visibly apart, as the rest of the wiki does ([[Evidence Model|Evidence-Model]]):

| Tag | Meaning |
|---|---|
| **Reading** [E] | Taken from a log or from CUORE's observation store (file and date named in the source documents). |
| **Inference** [I] | Reasoning from readings. It can be wrong. |
| **Outside** [O] | A bulletin, recall, article or forum thread about other cars or model years. It never counts as a reading of this car. |

The same findings are shown in the app on every code page as the panel **"What we found out about this code"** (`mes/code_findings.py`, shown through `_code_findings.html`). The panel carries the meaning, the readings, any owner statement (marked attested, not read), the classification, the implications, a resolution ladder, the proof of fix and the outside literature. Nothing in it is invented: a field with no sourced finding is left empty. The EVAP codes are told on [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]; the network pattern behind many of these codes is on [[Network and Brake Findings|Network-and-Brake-Findings]].

The full working documents are in the repository: [NON_EVAP_CODES](https://github.com/dangelojohn/CUORE/blob/main/docs/research/NON_EVAP_CODES_2026-10-20.md), [CODES_ADAS_CAMERA](https://github.com/dangelojohn/CUORE/blob/main/docs/research/CODES_ADAS_CAMERA_2026-10-20.md), [CODES_BODY_INFOTAINMENT](https://github.com/dangelojohn/CUORE/blob/main/docs/research/CODES_BODY_INFOTAINMENT_2026-10-20.md), [NETWORK_PATTERN_READINGS](https://github.com/dangelojohn/CUORE/blob/main/docs/research/NETWORK_PATTERN_READINGS_2026-10-20.md) and [NETWORK_PATTERN_LITERATURE](https://github.com/dangelojohn/CUORE/blob/main/docs/research/NETWORK_PATTERN_LITERATURE_2026-10-20.md).

## What was reviewed

- **Reading** [E]: 18 genuine MES scan reports of the car (2026-06-07 to 2026-10-19; one more was an aborted attempt with the adapter not connected), 23 real live-session logs, and CUORE's own reads (engine, transmission, body, cluster and keyless modules on 10-13, 10-14 and 10-19, plus one silent attempt on the brakes on 10-15).
- **Excluded:** every log marked simulation, and a small set of scan and session logs that carry a different car's identifier ([[MES Integration|MES-Integration]]).
- A scan report carries no simulation marker, so its provenance is "unverifiable" by design.
- Modules CUORE has never read (driver-assistance radar, transfer case, steering, airbag, adaptive lights, parking, camera) are known only through MES scans, so for them there is **no status byte and no freeze frame** at all.

## How each code is classified

| Class | Meaning |
|---|---|
| **Real** | A genuine condition on the car is the likely reading (still unconfirmed until its proof is met). |
| **Service-induced** | Set by work done on the car (owner statement), not yet confirmed by a reading. |
| **Probable tool artefact** | First seen in a window that held tool activity; not proven. |
| **Possible bystander** | Appeared in or near tool sessions or alongside other codes; a receiver-side message. |
| **Core of, or downstream of, the BCM network cluster** | Part of the pattern described on [[Network and Brake Findings|Network-and-Brake-Findings]]. Downstream codes are not fixed on their own. |
| **Readiness flag only** | Not a fault (status byte `0x40`, see below). |

## The resolution ladder and the proof of fix

Every code has a **ladder**: steps in order, cheapest first, read-only first, none of them clearing a code. A clear erases the status bytes and freeze frames and proves nothing; on this car the engine codes returned after 10 of 11 clears. Every code also has a **proof of fix**: the reading that would settle it. The common rule is that a code is "fixed" only when it is **absent on reads spread over longer than its longest observed gap**, with status bytes read before any clear. A read within hours of a clear does not count; one such read (seven minutes after a clear, 2026-09-04) was clean and meant nothing.

## Brakes

| Code | Readings [E] | Class and implication |
|---|---|---|
| **C104B-92** ABS "leaks in hydraulic group" | One occurrence in an ABS live session on 2026-09-04 20:01, cleared in the same session. Freeze frame: standstill, engine off, 12.1 V, brake pedal pressed, hydraulic circuit 11.1 bar, pedal pressure 3.6 bar. Every ABS code read that ever succeeded falls within eight minutes that evening (later reads clean). CUORE's one attempt on 10-15 got **no reply**: silence, not "no codes". | **Service-induced, per the owner**: the owner states that it was caused by their own brake-pad inspection that evening (pedal pressed during pad and caliper work) and that it is fixed. That fits the standstill, pedal-pressed freeze frame. It is attested, not read, so the code stays on the **safety list** until an ABS read confirms it is gone. |
| **U1700-87** ABS "body computer missing message" | One occurrence, same session: battery **10.6 V**, hydraulic circuit 2.6 bar, pedal off. | Core of the BCM cluster (the ABS side of the BCM's complaints); a supply-side observation, not a brake one. |

**Ladder for C104B-92:** (1) a read-only ABS code read with the grey cable, saved with freeze frames before any clear; (2) optionally, fluid level and colour against MIN and MAX and a look for wetness at calipers, hoses and the ABS block; (3) if C104B-92 is listed active, the fluid is low or wet, or the pedal sinks under steady pressure, stop driving and have it inspected. **Proof of fix:** an ABS code read with the grey cable shows no C104B-92. In the job ledger the brake hypothesis carries `safety` and `attested_resolved`: the page shows "owner-attested resolved, confirm with ABS read" rather than hiding it ([[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]).

**Outside** [O]: no document was found for "C104B-92" (search, 2026-10-20). The catalogue holds recall 17V823 (contaminated brake fluid, 2018 Giulia and Stelvio, VIN check) and bulletin 08-044-19 (ABS flash for pedal feel); neither names this code. Recall 21V309 (a 2019 to 2021 ABS part) came up and is not this model year ([[Recalls and Campaigns|Recalls-and-Campaigns]]).

## Network cluster (body computer)

| Code | Readings [E] | Class |
|---|---|---|
| **U1713-2F** engine control signal erratic (BCM) | 10 of 18 eight-module scans; **failing now** (status `0x0F`) on 10-13 and twice on 10-19; present at 14.0 to 14.5 V. Returned after most clears, within 2.6 to over 8.9 days. | Core of the cluster. The suffix 2F is "erratic"; an earlier code text called it "lost communication" and was corrected. |
| **U1711-2F, U1712-2F** brake system signal erratic (BCM) | Six scans, 06-07 to 09-25, always together, never without U1713; absent in every later BCM read. | Core of the cluster. Looks like it stopped, not like it was cleared away. No action. |
| U1716-2F, B1029-64, B102E-64, C1403-86, C1431-86 | One burst of 14 codes in five modules on 08-27, the first read after 81 days; never again. | Single burst; no action; watch. |
| U1701-86 (DASM) | Once, 06-07, nine minutes after a clean read, during sessions on other modules. | Possible bystander; no action. |
| U0100-87 (transfer case) | 7 scans. The repository's own drivetrain table calls it a bystander of whole-vehicle serial sweeps. | No action unless transfer-case symptoms appear. |
| **U0422-86** (transfer case) | First seen 2026-10-19; between the previous clear and that read no one read the module, and the window holds the 10-14 night incident ([[Safety Rules|Safety-Rules]]). | **Probable tool artefact**; the link to the chassis bus is itself an inference. |

**Ladder (group):** ask the owner about battery work, jump starts, aftermarket electrical devices and engine-bay washing; multimeter checks of the battery at rest, cranking and running; supply and ground voltage drop at the BCM, fuse F82 and the stand-alone BCM fuse; look at the BCM and A-pillar connector for moisture; then one read-only "mirror" snapshot of all the modules in one session while U1713 is active. **Proof:** none of these codes on three reads over at least 21 days (longer than the longest clear-to-return of 14 days), including one read under the conditions that showed them.

## Driver assistance, radar and camera

The radar module (DASM) stores most of these codes; the camera (HALF) was read once.

| Code | Readings [E] | Class |
|---|---|---|
| **C141B-97** camera blinded, obstructed or blocked (DASM) | 8 of 18 DASM reads, first 09-02, most recently 10-19. Absent on several reads that were not just after a clear (09-15, 09-29, 10-04), so intermittent. Present with the BCM clean on 10-08, so **independent** of the BCM cluster. No status byte or freeze frame; no dash message or windscreen work is on record. | **Real** (possibly), the one DASM code with a cheap physical test. |
| **C141C-86** private link between camera and radar | 7 of 18 reads; present in 6 of 6 scans where U1711/U1712 were present. The 09-04 clear **failed** and it was still there 11 days later. | **Downstream** of the BCM cluster; do not fix separately. |
| C1408-86 ESP signal invalid, C1403-86 steering signal, C1431-86 yaw signal, U0418-86 (camera: ABS signal), U1960-83 (steering), U0428-86 (adaptive lights) | Receivers reporting an ESP, yaw, steering or ABS signal as invalid. C1408 left on its own once (gone by 09-15 with no successful clear). The last three were read only once, on 09-04. | **Downstream** of the BCM cluster; they say nothing about hydraulics, sensors or the steering rack. |
| **U1702-87** steering missing message (stored in the DASM, not the steering) | One sighting, 10-19; first seen inside an interval that holds the 10-14 night incident. | **Probable tool artefact**; not proven. |

**What the features might do** [I; none of it shown by a reading]: lane keeping, forward collision warning and adaptive cruise depend on the camera and radar; treat them as unavailable while these codes are live. No dashboard message is on record.

**Ladder for C141B-97:** ask about windscreen replacement, tint, a dashcam or device in the camera's view; **clean the windscreen first**, outside and inside, in the patch behind the mirror ([O] a Stellantis bulletin, S2308000020, for a camera-blinded code says to verify the view is clear and, once verified, not to repair, calibrate or replace anything; its code number is C14A5, not C141B, and it does not name the vehicle, so it is the closest statement of the mechanism, not proof for this code); re-read the radar and the camera after a daylight drive in dry weather; only if it persists on clean glass or after windscreen work, calibration with the dealer tool or an ADAS platform. MultiEcuScan cannot calibrate either module ([[MES Integration|MES-Integration]]). **Proof:** absent on at least two reads on separate days over at least 21 days including a daylight drive.

**C141C-86 and the 2020 bulletin** [O]: bulletin 08-045-20 lists the same code with a forward-collision message for **2020** cars and fixes it with a body-computer configuration restore and alignment. It names model year 2020, not this 2018 car; it is context, not a documented fix here.

## Window

**B1176-97** rear left window riser obstructed or blocked (BCM). [E] First seen 08-27 (not in either 06-07 scan, correcting an earlier brief), then 9 of 18 scans and status `0x08` on 10-13; absent since the 10-14 clear. It came back within 1 to 14 days after each clear and was absent for at least 9 days once. No freeze frame, no window symptom on record. **Real, intermittent, local** [I]: it is a single-component code and is not downstream of U1713 (present with it absent and absent with it present). Ladder: ask what the window does; hold the switch and listen for binding; check the glass run and seals; a window initialisation (hands clear, anti-pinch is off during it; third-party procedure, check the handbook) and then re-read; regulator and motor only if it returns. **Proof:** absent for longer than 14 days counted from the later of the clear and the initialisation, window used daily, one-touch confirmed by the owner. Four days of absence proves nothing.

## Radio and infotainment

**U1736-86 / U1736-87** (the radio and telematics head unit, seen by the cluster and the body computer) and **B10AA-4A** (configuration "incorrect component installed"). [E] One episode: first seen between 10-08 and 10-13, stored by two receivers, status `0x0C` and `0x08`, cleared 10-14, not back through 10-19. The head unit itself has never been read. [I] Two receivers losing the same sender points at the head unit or its bus segment, and a radio reboot would produce this pattern; it predates the night incident. **Possible bystander.** [O] Bulletins 08-065-20 and 08-029-20 describe radio reboots on 2018 and 2019 Stelvios within build-date and radio-code ranges, with software levels; the car's build date is not in any log, so which applies is unknown. Ladder: ask about radio reboots or head-unit, amplifier and USB work; read the radio software level from the menu and the label in the door jamb; re-read without clearing. **Proof:** only once a cause is found; a convincing outcome is software below the bulletin level, updated, no reboot symptoms and no U1736 for 60 days. **No action** if the radio is current and the codes stay absent.

## Keyless: RFHUB

**B1040-64** (RFHUB: communication with the body computer plausibility; 6 of 18 scans, first 06-07) and **U2054-87**, with the body computer's **U1765-86** (lost communication with the RF hub; 09-15 and 10-13/14). [E] Always stored-not-failing when read. B1040 and U1765 set together only on 10-13 and 10-14; each also occurs without the other. [I] Two ends of one link that do not always set together; **possible bystander**, not caused by the night incident (recorded before it, absent after it). No key or start symptom is on record (no record is not a negative test). [O] A tech tip for a 2015 to 2016 hub says a stored U1765-87 on a power cycle needs no repair; a bulletin on intermittent keyless start failures points at aftermarket LED bulbs and wireless devices. Ladder: ask about keyless symptoms and the spare key and fob battery; re-read without clearing; BCM supply and ground, F82, connectors. **Proof:** both absent for longer than 9 days 21 hours (the longest B1040 gap) with no keyless symptom. **No action** if there is no symptom and they stay absent.

## Powertrain codes that are not EVAP

Four engine sensor codes (P1189, P00F5, P0098, P105E) were stored once, on 2025-09-24, all with a freeze frame at the session's own clock, engine off, 12.1 V. They were never seen again in 13 months. [I] The pattern of codes stored at connection or key-on. **Possible bystander; no action.**

## Readiness flags need no action

The transmission module's list entries P1DAD-00, P1DB7-00 and P1DCE-00, and 2,337 of the 2,368 entries in CUORE's module code lists, have a status of exactly `0x40`: "test not completed this operation cycle" (ISO 14229 bit 6). **Reading** [E]: every failure bit is clear on every one of them in every read. It is a readiness flag, not a fault. The meaning of P1DB7 (torque converter clutch performance) is from the repository's transmission reference; P1DAD's name is not confirmed for this transmission; P1DCE has no description. **No action**; escalate only if one ever shows a failure bit. Counts differ between reads (the engine module's list swung from 72 to 278 entries) and nothing should be inferred from that.

## Needs no action now

B1029-64, B102E-64, U1716-2F, C1403-86, C1431-86 (one burst on 08-27); U1701-86; U1711-2F and U1712-2F (stopped after 09-25); the four 2025 engine sensor codes; U0100-87; B1040-64 and U2054-87 (watch only). They still count in the proof of their group: a read in three weeks should list none, and any that returns on a quiet read moves up.

## Gaps this review could not close

- No ABS code read since 2026-09-04; no airbag module read since the airbag lamp lit on 10-14; no steering, camera or adaptive-light read since 09-04.
- No status byte or freeze frame for any radar, transfer-case, steering, camera or adaptive-light code. The body computer's snapshot beyond operating time and startup count is undecoded.
- No battery voltage at rest, during cranking or while charging; no brake fluid level; no window, camera or keyless symptom record; the owner questions on the network codes are unanswered.
- Whether MES's report after a clear lists returned codes or the pre-clear list is not established by the files.
- The one read that would separate "stored by the car" from "stored by the session" is a quiet read after at least three tool-free days, engine running, with status bytes captured before any clear.

Related: [[Network and Brake Findings|Network-and-Brake-Findings]], [[Recalls and Campaigns|Recalls-and-Campaigns]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].
