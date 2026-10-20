# ADAS / camera code group, Stelvio the reference car (2026-10-20)

DASM C141B-97, C141C-86, C1408-86, C1431-86, C1403-86 and HALF U0418-86. Research only: nothing was read from or written to the car, no clearing, no serial, no jobs.

Two evidence classes, kept apart.

- **READINGS [E]**: only `data/captures/stelvio-2018/mes_logs/` (19 SCAN, 23 FESLog) and `data/captures/stelvio-2018/cuore_state/observations.jsonl`, parsed with `mes-log-mcp/mes` and re-checked line by line against the SCAN text. Scan id = filename stamp YYMMDDHHMM (a save/start stamp, not an exact scan time). Intervals are computed from those stamps.
- **OUTSIDE LITERATURE [O]**: public web or NHTSA PDFs, each with a URL; `cuore/data/tsb_catalogue.json` row ids where a row exists. Search budget used: 6 standard WebSearch plus WebFetch. [I] marks inference.

## 0. Who is who

- [E] SCAN prints the DASM as "Driver assistant system module (DASM) radar Bosch", ISO 00 39 70 7E 15, HW MRR1evo14F v00, SW 52081920 v0500 (identical in every scan). The HALF is "Haptical lane feedback (HALF) camera Bosch", ISO 00 1E 50 72 14, HW 0203500279 v01, SW 1037601726 v1001 (SCAN_2609042008, the only HALF read).
- [E] Every code in this note except U0418-86 is stored in the **DASM** (the radar). C141B-97 "camera blinded" is therefore the radar module reporting a fault about the camera, not a code read out of the camera itself. The HALF has been read once.
- [E] CUORE never read the DASM or HALF: `observations.jsonl` 2026-10-13 20:24:25 lists `{"ecu": "DASM", "skipped": "no confirmed address"}`. So there is **no status byte, no freeze frame, no occurrence counter and no extended data for any code in this note** from CUORE. SCAN logs contain no freeze data either (grep of all 19 files). FES (live) logs never touched DASM or HALF.
- [E] A different code with the same number appears in CUORE: BCM **U0418-96**, status 0x40 (test not completed this cycle only, not failing), 2026-10-14 19:02:07 and 2026-10-19 00:23:42 / 00:30:25. It is a different module and a different FTB from HALF U0418-86. Do not count it as a sighting.
- [E] DASM was read in 18 of 19 SCANs (SCAN_2609042008 read ABS, EPS, NAB/ORC, AFLS, PAM, HALF instead).

## 1. READINGS

### 1.1 DASM clear history (from the CLEARING blocks)

| scan | DASM clear | note |
|---|---|---|
| 2606070954 | SUCCESS x2 | first re-listing still showed C141C-86; second clear done |
| 2606071003 | SUCCESS | DASM then held only U1701-86 (not in this group) |
| 2608271131 | SUCCESS | re-read 2608271136: DASM clean |
| 2609041953 | **FAILED** | post-clear list: C1408-86, C141C-86 (C141B-97 not listed) |
| 2609152048 | SUCCESS | |
| 2609252027 | SUCCESS | |
| 2609281159 | SUCCESS | |
| 2609291046 | not cleared (ECM, BCM only) | |
| 2610080920 | SUCCESS (second pass; first pass cleared ECM only and C141B-97 stayed) | 2610080926: DASM clean |
| 2610140859 | SUCCESS | |
| 2610190039 | SUCCESS | no re-read in the file, so removal unverified |

[E] "SUCCESS" is MES's clear result; it is not a proof the code stays gone. Clears were written by MES, not by CUORE.

### 1.2 C141B-97 "Camera blinded/obstructed/blocked" (DASM)

Present in 8 of 18 DASM reads. Absent in 10 (all before 09-02, plus 09-15, 09-29, 10-04 x2, and 10-08 09:26 straight after a clear).

| scan | date time | result | context |
|---|---|---|---|
| 2609021445 | 2026-09-02 14:45 | **first sighting**, alone in DASM | last absent read: 2608271141 (08-27 11:41, 6 d 3 h before) |
| 2609041953 | 09-04 19:53 | present (with C1408-86, C141C-86) | clear FAILED; C141B not in the post-clear list |
| 2609152048 | 09-15 20:48 | absent | 11 d 1 h after 09-04 |
| 2609251956 | 09-25 19:56 | present (listed twice in the file) | 9 d 23 h after the 09-15 clear |
| 2609252027 | 09-25 20:27 | present, then cleared | |
| 2609281159 | 09-28 11:59 | present, then cleared | back within 2 d 15 h of the 09-25 clear |
| 2609291046 | 09-29 10:46 | absent | 22 h 47 min after the 09-28 clear |
| 2610041113 / 2610041115 | 10-04 11:13 / 11:15 | absent x2 | 5 d 23 h after the 09-28 clear |
| 2610080920 | 10-08 09:20 | present; stayed after a first clear that did not include DASM; then cleared | back within 9 d 21 h of the 09-28 clear |
| 2610080926 | 10-08 09:26 | absent | verified removal, same session |
| 2610140859 | 10-14 08:59 | present (listed twice), cleared | back within 5 d 23 h of the 10-08 clear |
| 2610190039 | 10-19 00:39 | present (listed twice), cleared | back within 4 d 15 h 40 min of the 10-14 clear |

- [E] Return after a verified or probable clear: 22 h absent, 5 d 23 h absent, then present at 9 d 21 h; present at 2 d 15 h, 4 d 15 h, 5 d 23 h. The code is **intermittent, not constant**: it is absent on three reads that were not immediately post-clear (09-15, 09-29, 10-04).
- [E] Independent of the BCM network cluster: present with the BCM pair (09-04, 09-25 x2), with U1713 alone (09-28, 10-14, 10-19), and alone with the BCM clean (10-08 09:20).
- [E] No dashboard message about forward collision, lane or cruise is recorded anywhere in the captured state (no symptom, note or feedback row mentions one; `symptoms.jsonl` holds one row, fuel smell, 10-08). The owner has not been asked (see section 4).
- [E] No record of windscreen replacement, tint, dashcam or camera work in `shop_visits.jsonl`, `notes.jsonl`, `symptoms.jsonl`, `jobs.jsonl`. Absence of a record is not evidence of absence; the question is open.
- [E] Time of day or weather for any reading: not recorded.

### 1.3 C141C-86 "Private CAN between HALF and DASM, signal invalid" (DASM)

Present in 7 of 18 DASM reads: 06-07 09:54, 08-27 11:31, 09-04 19:53, 09-15 20:48, 09-25 19:56, 09-25 20:27, 10-19 00:39.

- [E] Clears: 06-07 first clear did not hold in the re-listing, second did (06-07 10:03 clean of C141C); 08-27 11:31 removed (11:36 clean); **09-04 clear FAILED and C141C was still present 11 d 1 h later on 09-15 20:48** (then cleared SUCCESS); 09-25 cleared (09-28 absent, 2 d 15 h); 10-14 DASM list had no C141C; it was present again 10-19.
- [E] Tracks the BCM U1711/U1712 pair: present in 6 of 6 scans where the pair was present, and in 1 of 12 scans without it (10-19, when BCM U1713-2F was failing). Details and the shared-clear confound are in `docs/research/NETWORK_PATTERN_READINGS_2026-10-20.md` section 3g.
- [E] Not read in the HALF end of the link (HALF read once, 09-04 20:08, no C141C-type code there).

### 1.4 C1408-86 "ESP control", C1431-86 "Lateral acceleration/YAW sensors", C1403-86 "EPS electric steering (NGE)" (DASM, all FTB 86)

| code | scans present | detail |
|---|---|---|
| C1408-86 | 08-27 11:31, 09-04 19:53, 10-19 00:39 | 09-04: stayed after the FAILED clear; **gone by 09-15 20:48 with no successful clear in between**. 10-19: first seen again after 09-15, within 4 d 15 h of the 10-14 DASM clear |
| C1431-86 | 08-27 11:31 only | together with C1403-86 and C1408-86 and C141C-86, with the BCM U1711/12/13 trio and U1716-2F (BCM) |
| C1403-86 | 08-27 11:31 only | as above |

- [E] Only one scan (08-27 11:31) shows all three, and then all five DASM codes except C141B/U1702. Cleared 11:31, re-read 11:36 clean, 11:41 clean.
- [E] 10-19 also added U1702-87 "EPS (NGE) missing message" (DASM), new that day. The 10-14 23:58 to 00:00 wrong-bitrate listen window lies between the 10-14 DASM read (C141B only) and 10-19; no read of any module exists in the window (`NETWORK_PATTERN_READINGS` 3e). The 10-19 DASM codes cannot be attributed to it or cleared of it; C1408-86 and C141C-86 existed before it.
- [E] No ABS read after 09-04 except one unanswered `can_ch` read on 10-15 00:12:43 (all identity fields null, [I] not a clean result). ABS FES 09-04 20:01 held C104B-92 and U1700-87 (cleared); 20:08 no faults x14 reads. No EPS freeze frame; EPS read once (U1960-83, 09-04 20:08).
- [E] BCM U1716-2F "Electric steering erratic" appeared on 08-27 11:31 only, in the same scan as C1403-86.

### 1.5 HALF U0418-86 "Error in communication with ABS module, signal/message invalid"

- [E] One sighting: SCAN_2609042008 (2026-09-04 20:08). That scan read ABS, EPS, NAB/ORC, AFLS, PAM, HALF. HALF held only U0418-86. EPS held U1960-83, AFLS U0428-86.
- [E] DASM was read 15 min earlier (19:53) with C141B-97, C1408-86 and C141C-86 and its clear failed; the HALF was not cleared (no CLEARING block in the file); it has not been read again, so the code's current state is unknown.
- [E] ABS FES at 20:01 and 20:08 (14 reads) showed no faults after the 20:01 clear; the ABS had a stored U1700-87 at 10.6 V at 20:01:10 (startups 14280).
- [I] Because the HALF and the DASM were each read once at that time, U0418-86 cannot be called intermittent or chronic.

### 1.6 What the readings do and do not show about features

- [E] Shown: the DASM stored a camera-obstructed code on 8 reads and a HALF-to-DASM link-invalid code on 7 reads; the DASM complained about ESP, yaw/lateral-acceleration and EPS signals on 3 reads (once all three); the HALF complained about an ABS signal once.
- [E] **Not shown**: any dashboard message, lamp, feature-off state or live-data value for lane keeping, forward collision warning/AEB, adaptive cruise or traffic sign recognition. No parameter (PRM) read of DASM or HALF exists. The readings give no basis to say a given feature is off.
- [E] The car's fitted ADAS content (is it ACC, FCW-Plus, LDW/LKA, sign recognition) is not recorded in the captured files. DASM exists on the car (radar), so it has at least a radar function.

## 2. MEANING

- [E] FTB as MES prints it: -97 "Component or system operation obstructed or blocked"; -86 "Signal/message invalid".
- [O] FTB -97 = component or system operation obstructed or blocked; -86 = signal invalid (message arrives but content fails a check; a lost message is -87). Source for the FTB list: https://oficinabrasil.com.br/noticia/tecnicas/quais-os-tipos-de-falha-sao-descritas-em-um-dtc-diagnostic-trouble-codes (trade article, not checked against paid SAE J2012-DA https://saemobilus.sae.org/content/J2012DA_201812); -86 versus -87 on a Fiat page https://www.tat.net.au/scandata/codes/code-view.php?id=8470 (as collected in `docs/research/NETWORK_PATTERN_LITERATURE_2026-10-20.md`).
- [O] FCA's own wording for the neighbours: "C141C-86 Video Camera Private Can Communication Failure - Signal Invalid", "B1006-49 Camera - Internal Electronic Failure", "C1999-86 Dataset Failure - Signal Invalid" (NHTSA 08-045-20, https://static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf, text read). FCA wording of C141B-97 itself: not found in any document opened.
- [I] C141B-97: the DASM (which fuses the camera) reports that the camera's view/operation is obstructed. Its text is about the camera's view, not a network fault.
- [I] C141C-86: the camera-radar private link delivered invalid content. GIORGIO_PLATFORM.md section 2 describes the link as point-to-point, outside the vehicle network; if so, it is not carried by the BCM gateway (source for the layout is the repo doc, which is itself outside literature).
- [I] C1408/C1431/C1403/U1702-87 (DASM) and U0418-86 (HALF): receivers reporting an ESP, yaw, EPS or ABS signal as invalid or missing; they say nothing about the hydraulics, sensors or rack. They sit on the chassis CAN with ABS, EPS and the radar/camera (per GIORGIO_PLATFORM.md bus-C layout).

## 3. IMPLICATIONS FOR THE CAR

READINGS show none of these; every line below is inference or literature.

| feature | what the readings show | inference / literature |
|---|---|---|
| Lane keeping / lane departure | nothing | [I] camera-dependent. [O] a camera-blocked state is "temporary unavailability" of the camera systems per Stellantis STAR S2308000020 (below) |
| Forward collision warning / AEB | nothing | [O] FCA's 08-045-20 symptom for a camera-link fault on a 2020 car is "Forward Collision Warning Limited Functionality Front Camera Service Required"; the 2018 behaviour of this car is not documented in anything found. [I] FCW is camera-plus-radar, so it is the most likely feature to be limited |
| Adaptive cruise | nothing | [O] STAR S2308000020 title: "ACC/FCW Limited Functionality Clean Windshield" (ACC and FCW together). [I] only if the car has ACC; not recorded |
| Traffic sign recognition | nothing | [I] camera-dependent where fitted. No source found that ties it to C141B. Fitment not recorded |
| Radar / bumper-side function | nothing | [I] DASM itself answers, with a normal identity, so the radar module is alive |

[O] Safety note from the sources: a mis-calibrated forward camera can cause AEB to act late and lane keeping errors (UK AA warning, via https://www.businessday.co.za/motoring/2026-10-12-aa-warns-motorists-to-recalibrate-adas-cameras-after-windscreen-replacement/). Treat the camera features as unavailable or untrusted while any of these codes is live, and do not rely on them.

## 4. OUTSIDE LITERATURE

### 4.1 Causes of a camera-blocked/blinded code

- **[O] Stellantis STAR S2308000020, February 2023 (text read)**: https://static.nhtsa.gov/odi/tsbs/2023/MC-10234434-9999.pdf. "ACC/FCW Limited Functionality Clean Windshield Message Displayed In The IPC. FCW Warning Light ON, DTC C14A5-68, C14A5-97" (stored "Camera Blinded" / "Camera Blocked"). Cause stated: "temporary blinding/obstruction of the camera on the windshield ... commonly caused by grazing sun, rain, fog, snow, glare, misting or dirt in area of the FFCM/HALF." It says the light goes out and the system resets once conditions clear; "Verify the DTC are stored and the FFCM view out of the windshield is clear. Once verified DO NOT carry out any repair, calibration or component replacement"; if the light is permanent and DTCs persist after cleaning the windscreen with no blinding conditions, "proceed with standard diagnostics by performing the DTC flow charts." Limits: the code number is C14A5, not C141B, the document does not name the vehicle (it uses the term HALF, which is Alfa/Maserati wording), and it is not in `tsb_catalogue.json`. Treat as the closest FCA statement of the mechanism, not proof for this code.
- **[O] Windscreen replacement without calibration.** I-CAR OEM calibration search, 2018 Alfa Romeo Giulia (the 2018 Stelvio page was not found, Giulia is the sister model): forward-facing camera module near the mirror needs calibration "If camera is removed/installed or replaced", "If DTC indicates", "If windshield is removed/installed or replaced"; scan tool and special tools required; module programming (PROXI alignment) required if the camera is replaced with a new one. https://rts.i-car.com/oem-calibration-requirements-search/calv-2719.html (2018 Giulia, read). 2020 Giulia, same triggers: https://rts.i-car.com/calv-3787.html. Same I-CAR page for the radar behind the bumper: calibration if a DTC indicates, if bumper parts requiring sensor removal are removed, if the bracket is removed or replaced, if rear axle adjustments are made, if rims are changed.
- **[O] Why it gets missed.** I-CAR notes that FCA windscreen procedures say to remove the camera and may not mention calibration; the requirement is in a linked procedure (https://rts.i-car.com/collision-repair-news/fiat-chrysler-automobiles-fca-adas-repair-planning-do-you-have-all-the-information.html, Jeep example, not Alfa). Pilkington/AA say a camera left plugged in can still need calibration after a new windscreen (https://thecalibrationpeople.pilkington.com/en/FAQ, https://www.businessday.co.za/motoring/2026-10-12-aa-warns-motorists-to-recalibrate-adas-cameras-after-windscreen-replacement/; summary-grade).
- **[O] Camera bracket, tint, dashcam, stickers in the field of view**: no Alfa/FCA source found that names them for C141B. General statements (clean glass, nothing in the camera's view) are in other makers' manuals (Kia, Volvo, found in search) and in the Hunter video summary for FCA pre-checks (clean windscreen, nothing obstructing the camera, tyres correct, vehicle unloaded; summary only). [I] these are plausible but unsourced for this car.
- **[O] Not found for C141B-97**: any NHTSA bulletin, recall or forum thread (three searches, DASM/Giulia/Stelvio). Catalogue rows touching the modules: `recall-19v148` (BSM software, ACC cannot be disabled after wheel slip, 2018-2019 Stelvio, remedy BSM software update, row unverified), `tsb-s2223000047` (C1452-86 DASM engine torque, ACC/start-stop, 2022, PDF not opened), `tsb-31-004-19` (use Authentic Mopar glass, 2019, discussion only, PDF not opened), `tsb-s2008000093` (blind-spot/park-assist false warnings, 2020). None lists C141B, C1408, C1431, C1403 or U0418 for a 2018 car.

### 4.2 Bulletins checked

| bulletin | scope | codes | bearing on this car |
|---|---|---|---|
| NHTSA 08-045-20 (https://static.nhtsa.gov/odi/tsbs/2020/MC-10175724-9999.pdf; REV A https://static.nhtsa.gov/odi/tsbs/2020/MC-10180265-9999.pdf), no catalogue row | 2020 GA built on or before 2019-12-31, 2020 GU built on or before 2019-12-20, North America | B1006-49, C141C-86, C1999-86 plus FCW limited-functionality message | **2020 builds only; not this 2018 car.** Fix: wiTECH 2 Restore Vehicle Configuration, PROXI alignment, ignition cycle, clear, remove Micro Pod, sleep 10-15 min with fobs away, re-check. Only evidence that C141C-86 can be a configuration problem |
| STAR S2308000020 (above), no catalogue row | vehicle not stated | C14A5-68 / C14A5-97 | closest mechanism statement for temporary camera blindness |
| `recall-19v148` | 2018-2019 Stelvio | none | BSM software; VIN check on NHTSA/Transport Canada before assuming it is closed |
| 08-020-21 (https://static.nhtsa.gov/odi/tsbs/2021/MC-10188796-9999.pdf, wording only) | 2021 | C141C / U1700-87 wording | no 2018 scope |

[O] Nothing in the catalogue or the web results ties the C1408/C1431/C1403/U1702/U0418 group to a bulletin for 2017-2019 Giulia/Stelvio. FCA lookups by VIN are gated (`campaign-lookup` row); a VIN check at Mopar/dealer for open campaigns on the reference car has not been done.

### 4.3 Calibration after windscreen work

- [O] Required when the windscreen or camera is replaced, or when a DTC indicates it (I-CAR, above). I-CAR does not state static versus dynamic for the Giulia entries. The FCA-wide process is described elsewhere as a dynamic drive on a flat, straight road and, for some cases, static targets; both need the scan tool with the Security Gateway registered (summary of a Hunter Engineering video via search; not Alfa-specific; two Brake & Front End and Shop Owner pages returned HTTP 403, so the detail was not read).
- [O] Exact Alfa Giulia/Stelvio target distances, speed, lane-marking and minutes for a dynamic drive: **not found**. They are in FCA wiTECH service information (VIN-gated). A 2022 STAR note about a front camera "not calibrating with wiTECH, DTC B2286-00" was returned; vehicle scope unknown, not opened.
- [O/E] Repo doc `docs/research/MES_CAPABILITY_GAPS.md` section 9: HALF camera in MultiEcuScan is `INFO|DTC|DTC EX|PRM` (no ACT, no ADJ); DASM radar `INFO|DTC|DTC EX|PRM|ACT` (no ADJ). Calibration is an ADJ-class routine, so **MultiEcuScan cannot calibrate either module**. That doc's conclusion: after windscreen or front-bumper work this needs wiTECH plus FCA static targets, or an ADAS platform (Autel, Hunter, Bosch, Texa) with Alfa targets. Consistent with the above; the vendor matrix is from the repo, not independently verified here.
- [O] Paid options exist (dealer wiTECH, independent ADAS shops, glass companies' calibration services). This note does not recommend any of them; they are listed because the work cannot be done with MES.

## 5. RESOLUTION, per code

General rule: no clearing as a fix. A code that returns after a clear is information, not a result. "Fixed" means the code is absent on a re-read after the conditions that set it have been met, not that a clear succeeded.

### C141B-97 (DASM, camera blocked)

Tasks, cheapest first:
1. Ask and record: any windscreen replacement or chip repair (when, where, was calibration done and documented), tint or film, dashcam, toll tag, sticker or mirror-mounted device in the camera's view, parking-sensor or bumper work, a recent alignment or suspension work (rims, ride height). Free. Tells whether the dealer-calibration branch is in play.
2. Inspect and clean the outside and inside glass in the camera's patch behind the mirror (inside film, haze from off-gassing, wiper smear, sap, ice). Check wiper sweep covers the patch. Remove any device in the view.
3. Look at the camera housing, mirror base and bracket for movement, a loose cover or a cracked windscreen near it.
4. Re-read with MES (DASM, and HALF with the grey A6 cable) after a daylight drive in dry weather; note time, weather and which dash messages show. Record a **freeze frame/status** if a future tool exposes one (none exists now).
5. Dynamic calibration drive and/or dealer static calibration, only if step 1 shows windscreen or camera work or if the code stays on clean glass (STAR S2308000020 wording: persistent code on a clean windscreen means proceed to the DTC flow charts). Requires wiTECH or an ADAS platform; not possible with MES.

Reading that proves it fixed: C141B-97 absent on DASM reads after a daylight drive in conditions the camera would normally handle, on at least two reads on separate days over a longer span than the longest observed absence. Longest absence on record: 09-15 to 09-25 (about 10 days, 09-15 20:48 to 09-25 19:56), and 09-29 to 10-08 including a clean 10-04. A clean read on the day after a clear (22 h on 09-29) is **not** proof. The earlier project criterion (`docs/research/NON_EVAP_CODES_2026-10-20.md`: absent on two scans over at least 21 days including a daylight drive) is stricter and consistent.

### C141C-86 (DASM, HALF-DASM private CAN)

- Downstream of the BCM cluster for now: tracks the BCM U1711/U1712 pair in 6 of 6 cases; **do not fix separately** while the pair is being worked. Resolve through the BCM network cluster (supply and ground, connectors, gateway, configuration), then re-read.
- If it persists after the pair stays absent over several scans: check the HALF and DASM connectors and the windscreen-header to bumper harness (the private-CAN route per GIORGIO_PLATFORM.md), look for windscreen or bumper work, and read the HALF as well as the DASM. The 08-045-20 BCM Restore Vehicle Configuration plus PROXI alignment is a dealer-tool step with a 2020-only bulletin; it is a candidate, not a documented fix for 2018.
- Fixed = absent on DASM re-reads on separate days after BCM U1711/U1712 have also stayed absent; remember C141C returned within 4 d 15 h of a clear on 10-19 while the pair was absent, so a single clean read does not count.

### C1408-86, C1431-86, C1403-86 (DASM, ESP / yaw / EPS signals invalid)

- Downstream of the ABS, EPS and the BCM/gateway cluster. The DASM is the receiver. Do not chase the DASM, the yaw sensor or the steering rack; the first useful action is a fresh ABS and EPS read (last ABS DTC read 09-04, one unanswered can_ch read 10-15), then the BCM cluster work.
- Tasks: read ABS, EPS, DASM and HALF in one session; compare against the BCM state in the same session; log voltage; only then consider wiring or module work. C1408-86 has already left on its own once (gone by 09-15 without a successful clear), which argues for a network or timing cause.
- Fixed = absent on DASM re-reads on separate days, ABS/EPS/DASM read in the same session, BCM U1713/U1711/U1712 not failing at the same time.

### U1702-87 (DASM, EPS missing message)

Same group; first seen 10-19 and in the same window as the wrong-bitrate listen. Treat as downstream and as "unproven whether tool-caused".

### U0418-86 (HALF, ABS invalid)

- Read once. Task 1: read the HALF again (grey A6 cable). If absent, record as a single event. If present, it belongs to the same ABS/EPS/BCM cluster work; do not clear it as a fix.
- Fixed = absent on at least two HALF reads on separate days, after the ABS side is read in the same session.

### Which are downstream of the BCM network cluster (do not fix separately)

- C141C-86: tracks U1711/U1712 [E, 6 of 6].
- C1408-86, C1431-86, C1403-86, U1702-87, U0418-86: receivers of ABS/EPS signals on a chassis bus; co-timed in part with the BCM trio on 08-27 [E]; order of cause not proven [I].
- **C141B-97: independent** [E: present with the BCM clean on 10-08]. It is the one code in this group that has a cheap physical test (the glass).

## 6. Open items

1. Owner questions in 5, step 1 (windscreen, tint, device in view, dash messages seen). One answer decides whether the calibration branch matters.
2. HALF read and a same-session ABS/EPS/DASM read have not been done since 09-04.
3. VIN-based campaign lookup (FCA/Mopar, Transport Canada) for the reference car has not been done.
4. The 2018 Stelvio I-CAR page, a static-versus-dynamic statement for this model, and a dynamic-drive procedure were not found; they need wiTECH service information.
