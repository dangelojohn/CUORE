# Case Study: Stelvio EVAP

The reference car is a 2018 Alfa Romeo Stelvio 2.0T Q4 (about 142,000 km at the time of the first dossier). It has a chronic fuel-vapour (EVAP) fault: three codes that keep returning on a system that smoke tests show to be sealed. This page tells the diagnostic story as the repository records it, up to 2026-10-20, and keeps three kinds of statement visibly apart.

| Tag | Meaning |
|---|---|
| **Reading** [E] | A stored read from the car, a log line, or a recorded job entry. The source is named in the working document. |
| **Inference** [I] | Reasoning from readings. May be wrong. |
| **Outside** [O] | Service bulletins, articles, forum posts, parts guides. Not a measurement of this car; it may suggest what to check but proves nothing. Where the repository could not read the source itself, it says so. |

Where the repository has nothing, this page says **not known** [N]. The full working document is [CEL_2026-10-19_DIAGNOSIS.md](https://github.com/dangelojohn/CUORE/blob/main/docs/research/CEL_2026-10-19_DIAGNOSIS.md); related files are [EVAP_STELVIO.md](https://github.com/dangelojohn/CUORE/blob/main/docs/research/EVAP_STELVIO.md), [EVAP_SMOKE_TEST.md](https://github.com/dangelojohn/CUORE/blob/main/docs/research/EVAP_SMOKE_TEST.md) and the handbook summary [04-stelvio-case.md](https://github.com/dangelojohn/CUORE/blob/main/docs/handbook/04-stelvio-case.md).

## The codes

| Code | Meaning (SAE generic; the manufacturer's own definition for this car was not obtained) | Lamp |
|---|---|---|
| P0440 | General EVAP fault. The scan tool names it "evaporation control valve"; one outside article defines it, for a related model, as the vapour switch failing to close in the test. | The only one of the three that has ever requested the lamp |
| P0455 | Large leak (0.040 in or greater by SAE convention) | no |
| P0456 | Small leak (0.020 in or greater by SAE convention) | no |

A fourth, unrelated code on the body computer, **U1713-2F** ("engine control signal/message erratic"), is often listed in the same scans. It is a network code; whether it relates to the EVAP monitor is not known.

## Timeline

Times are local. "Cleared" means MES ran its clear function with success on the engine computer, unless stated.

| Date | What happened |
|---|---|
| 2025-08 | New fuel cap and new EVAP canister. First smoke test: no leak. Codes persisted (owner-confirmed, never logged by a tool). |
| 2025-09-24 | First MES log of this car. P0456 stored. Purge-valve actuator test ran five times, completed. |
| 2026-08-27 | P0455, P0440, P0456 all logged with freeze frames. Cleared. |
| 2026-08-31 | P0440 back after 4.3 days. Cleared. |
| 2026-09-02 | P0456 and P0440 back after 1.9 days. Cleared. Same day new: canister air filter, fuel cap and seal, a valve at the canister, **ESIM** (the evaporative system integrity module), part 04861961AD. |
| 2026-09-04 | P0440 after 2.2 days. Cleared. |
| 2026-09-15 | P0440 only, after 11.0 days. Cleared. Purge valve actuator test 12 times, completed. |
| 2026-09-16 | Smoke test 2: no leak; quick-connect and purge routing OK. |
| 2026-09-02 to 09-25 | Engine-side purge valve replaced (date not recorded). |
| 2026-09-25 | All three codes back after 10.0 days. Cleared. |
| 2026-09-26 | Filter clear; no fuel in the canister; quick-connect latched; owner reports no hard fill, no hiss, no early click-off. Smoke test 3: all sections sealed. |
| 2026-09-28, 09-29 | P0440 back after 2.6 days and then 0.95 day. Cleared both times. |
| 2026-10-04 | Two scans and a session: no codes, 5.0 days after the clear. No evidence the monitors had run. |
| 2026-10-08 | P0456 and P0455 after 8.9 days. Cleared. |
| 2026-10-13 | **First live read by CUORE**, 5.4 days after the last clear. The engine computer requested the lamp. Mode 06: two leak tests failing. |
| 2026-10-14 08:59 | P0455 and P0440 present. Cleared. 10 hours later P0440 already back. |
| 2026-10-14 night | A tool-caused incident on the chassis bus (a wrong-rate listen). Not EVAP, not evidence. See [[Safety Rules|Safety-Rules]]. |
| 2026-10-19 00:23 to 00:34 | CUORE UDS reads, engine running: P0440 `0xCD`, P0455 `0x4D`, P0456 `0x4D`, BCM U1713-2F `0x0F`. The legislated OBD side returned no data. |
| 2026-10-19 00:39 | MES scan, then cleared again: the **eleventh engine-computer clear in 53 days**. The only copies of that night's freeze frames are in CUORE's observation store. |

**Reading:** The fault came back after every clear whose later reads exist (10 of 11), within 0.4 to 11 days. Clearing changes nothing. The 10-04 read was clean at 5.0 days but there is no evidence the monitors had run.

## Repairs as recorded, and what each ruled out

| Item | Ruled out | Strength |
|---|---|---|
| Fuel cap, new twice | A leaking cap | Strong |
| Canister, new (2025-08, part number not recorded) | Original saturated or failed canister | Moderate |
| Canister air filter, new and inspected clear | Dirty filter | Strong |
| "Valve at the canister" | A valve there (the entry does not say which valve) | Weak |
| ESIM 04861961AD, new (2026-09-02) | An old or failed unit | Moderate. Fitment never verified by VIN (an alternative number exists); mounting orientation and port seating were not recorded |
| Engine-side purge valve 68337662AC, new | A leaking or stuck purge valve | Strong, plus 18 actuator runs completed and a passing purge-flow Mode 06 on 2026-10-13. Actuating is not sealing |
| Three smoke tests | A physical leak at smoke-test pressure | Strong for leaks. **Blind to a blockage or a sense-port fault**; no flow readings or smoke-arrival points were recorded |
| No liquid fuel at the canister; normal refuelling | Flooded canister | Strong at the canister; the recirculation line was not reported |
| Eleven clears | Clearing as a remedy | Fault returns every time |

**Not yet done** (none recorded): the dealer tool's hand-vacuum test on the ESIM, the dealer tool's ECM flash check, an ESIM wiring test, an ESIM bench test, and VIN checks for the recalls that could have reflashed the computer.

## What the status bytes say

**Reading:** The engine computer's status bytes for the three codes, every stored read:

| Read | P0440 | P0455 | P0456 |
|---|---|---|---|
| 2026-09-25 | `0x4D` | `0x4D` | `0x4D` |
| 2026-10-13 | `0xCD` | `0x4D` | `0x40` |
| 2026-10-14 (10 h after a clear) | `0x4D` | `0x40` | `0x40` |
| 2026-10-19 (two reads) | `0xCD` | `0x4D` | `0x4D` |

How to read them: see [[Evidence Model|Evidence-Model]]. The failed state is carried from an earlier cycle; the lamp request is attached to P0440 only (why is not known). The triplet `0xCD` / `0x4D` / `0x0F` (body computer) is identical on 10-13 and 10-19, about 5 days after a clear each time: reproducible, not random. The lamp interval is **not** a rule: two clears were followed by a lamp request after 5 days, two others were not (one at 10 days, one at 10 hours). A caution recorded in the working notes: the 10-13 "lamp on" was the computer's request flag; the owner had not seen the dash lamp.

**Reading:** On 2026-10-14 the other EVAP-related codes (P0441, P0451, P0457, P0458, P0459, P0461, P1CEA, P2422) read `0x40` throughout, which is *not completed this cycle*, **not** "passed". No code for the ESIM switch circuit (P0450, P0452, P0453) or the vent circuit (P0446 to P0449) is tracked by this computer at all, so silent circuit codes are not a pass.

## Freeze frames, 2026-10-19

**Reading** (decoded from UDS `19 04`; scaling medium confidence):

| Field | P0455 | P0456 | P0440 |
|---|---|---|---|
| Startups counter | 14603 | 14608 | 14612 |
| Fuel level | 91.8 % | 62.7 % | 55.7 % |
| Engine speed | 764 rpm | 0 | 921 rpm |
| Vehicle speed | 0 | 0 | 12.1 km/h |
| Coolant temperature | 69 C | 17 C | 51 C |
| Battery voltage | 14.2 V | 12.3 V | 14.3 V |

**Inference:** three different regimes (idle just after a refuel, engine off after a cold soak, driving in third gear), the same outcome. Older frames: P0456 was set at cold-start idle in all four MES frames across twelve months. A caution: two of the 09-25 frames and tonight's P0455 frame had fuel above 85 %, which is above the usual EVAP test window; the working note says this may be a logging versus test-start difference, or a scaling issue, and that it is unknown which.

## Mode 06 decode

**Reading** (raw frames stored from 2026-10-13, record layout in [[Evidence Model|Evidence-Model]]):

| Test (CUORE label) | Value | Limits | Unit | Result |
|---|---|---|---|---|
| `3A` "0.090 in" | **404** | min 3965, no maximum | ms | **fail** (3561 below the minimum) |
| `3C` "0.020 in", TID `90` | **6096** | 0 to 6000 | ms | **fail** (96 over the maximum) |
| `3D` purge flow, TID `A1` | 168 | 57 to 328 | | pass |
| `39` gross leak | 0 | 0 to 0 | | not a result (zero-limit record) |

**Reading:** after the 2026-10-14 clear every record reset: limits wiped on `3A`, and `3C` TID `90` read 6000 against a maximum of 6000, a reset artefact.

**What the numbers mean is not known [N]**: no source found states what these two test IDs measure on this manufacturer's computer. The limits point in opposite directions (one needs a high value, the other a low one), so one quantity is unlikely to be behind both.

**Inference** table from the working notes, by candidate meaning of the millisecond value:

| Candidate | 404 vs min 3965 | 6096 vs max 6000 |
|---|---|---|
| Time from vacuum applied to switch closing | closure at 0.4 s; limit shape contradicts | closure 96 ms late; shape fits |
| Time the switch stayed closed, or decay time | closed but reopened after 0.4 s against 4.0 s needed; shape fits | held 6.1 s; shape contradicts |
| Counts, as another maker uses for the same ID | contradicts the declared unit | same |

The honest summary recorded: **the stored Mode 06 data does not show that the ESIM switch never closed**, and does not exclude it. It can be read as "closed but did not hold", and also as "late". It cannot separate the ESIM from blockages upstream of it.

**The timers in detail.** The two failing records are raw frames from 2026-10-13 20:03:54: for `3A` / TID `87` the value bytes are `0x0194` (404) with minimum `0x0F7D` (3965) and maximum `0xFFFF` (no upper limit); for `3C` / TID `90` the value is `0x17D0` (6096) with limits 0 and `0x1770` (6000). The unit byte `0x10` is read as milliseconds, one per count (the project table plus a manufacturer reference seen through a search summary; the paid SAE table was not read). The maker could in principle reuse the unit byte for something else; nothing found says so. The same `3C` reply also holds TID `85` and TID `86` records that are all zeros.

- **Limit shapes disagree.** `3A` passes at *higher* values and `3C` at *lower* ones, so the two test IDs probably measure different things [I].
- **Time scale.** Outside articles [O] say a key-off small-leak closure takes minutes to hours, so 0.4 s or 6.1 s is not the whole key-off closure; it could be an engine-running purge-vacuum timing or a sub-interval such as a decay timer. They name "time to switch closure" and "vacuum decay time" as measured quantities but give no numeric limits and no mapping to a test ID. A Saab table lists the same OBDMIDs as "leak factor" counts: the same ID can carry a different quantity per maker.
- **Never-closed reading.** Under either time reading, a non-zero value needs at least one closure event; only an undocumented "value stored when the switch never closes" would let either number mean "never closed". The reset value 6000 differs from the stored 6096, so the 10-13 value was written by a test.
- **What would settle it:** the manufacturer's test-ID description (dealer tool); a second read on the next P0440 `0xCD` (a measured quantity varies, a fixed sentinel repeats); and a read before and after one hand-vacuum pump cycle at the ESIM.
- **Standing caveat:** the gross-leak record (`39`) is byte-identical whether the monitor ran or not, so its "pass" carries no information ([[Evidence Model|Evidence-Model]]).

## ECM sub-test map

A per-sub-system verdict from status bits, across all five full reads (summary):

| Sub-system | Code | Verdict |
|---|---|---|
| General EVAP fault | P0440 | failed, lamp, every read |
| Large leak | P0455 | failed in four of five reads |
| Small leak | P0456 | failed in three of five reads |
| Purge circuit and flow | P0458, P0459, P0441 | passed on 2026-10-13 only (list absence plus the Mode 06 flow pass); never failed |
| Pressure / switch range | P0451 | never completed |
| Vent stuck closed | P2422 | never completed |
| Fuel level input | P0461 | never completed |
| Fuel cap | P0457 | never completed |
| ESIM switch circuit, vent circuit, ambient input | P0450-P0453, P0446-P0449, P0070-P0074 | not tracked by this computer |

A fuller version of the map gives a verdict per sub-system and per read, using this rule: a code **absent** from a full list went `0x40` to `0x00` (its test completed this cycle with no failure; an inference), a code at `0x40` has not completed this cycle, and a code **never returned** is "not tracked" (the earlier 278-code list holds 278 of the 282 codes ever seen, so absence from it makes non-existence the likelier case).

| Sub-system | Codes | 09-25 | 10-13 | 10-14 (10 h after clear) | 10-19 (two reads) |
|---|---|---|---|---|---|
| ESIM switch circuit; vent circuit | P0450, P0452, P0453; P0446 to P0449 | not tracked | not tracked | not tracked | not tracked |
| Pressure / switch range | P0451 | not run | not run | not run | not run |
| Vent valve stuck closed | P2422 | not run | not run | not run | not run |
| Purge circuit and flow | P0458, P0459, P0441 | not run | passed this cycle | not run | not run |
| Small leak (0.020 in) | P0456 | **failed** | not run | not run | **failed** |
| Large leak (0.090 in) | P0455 | **failed** | **failed** | not run | **failed** |
| General fault | P0440 | **failed** | **failed, lamp** | **failed** | **failed, lamp** |
| Fuel level; fuel cap | P0461; P0457 | not run | not run | not run | not run |
| Ambient input; 0.040 in leak | P0070 to P0074; P0442 | not tracked | not tracked | not tracked | not tracked |

The mapping of 0.020 to P0456 and 0.090 to P0455 is by SAE convention and CUORE's labels. The engine computer's own supply-voltage and processor monitors completed clean in every cycle read since 10-13. **Reading:** since the 2026-10-14 clear, nothing on the EVAP side has been verified clean.

## Bulletin research and its corrections

**Outside** (service bulletins, with the repository's own corrections):

| Item | What it is | Relation |
|---|---|---|
| 18-048-23 (supersedes 18-089-19) | Dealer-tool small-leak test; a road test cannot confirm a small-leak repair | Proof-of-fix tool, not a cause. Not yet run. |
| 9100471 | Hard to fill / flooded canister | Canister and ESIM remedy already applied; flooding excluded; its kinked-hose checks were not recorded |
| 9100469 | Replace only the ESIM if only it is at fault | Applied 2026-09-02, did not resolve |
| 9100468 | Canister filter | Excluded by inspection |
| 18-026-20 | 2018 Stelvio 2.0 ECM flash (opened and read) | Applies; lists other codes, **not** P0440/P0455/P0456 |
| 18-030-17 | ECM flash listing the three codes | **The opened copy covers the 2017 Giulia only (built on or before 2017-06-29); the Stelvio is not listed.** Weakens the calibration branch; applicability is a VIN check |
| Recalls 18V636, campaign W05, 19V551, 18V205, 25V586 | Engine software, body-computer fuel-level, water intrusion, fuel pump | Pending VIN checks |
| Sibling-engine bulletins on other models | Flashes listing P0456 on the same engine family; a sister-brand EVAP false-detection software fix | **Analogues, not Stelvio evidence** |

Corrections the case made to its own earlier statements (each is recorded in the working notes):

- "Two clean smoke tests" was actually **three**.
- The bulletin cited as the basis for the calibration verdict is Giulia-only.
- "The ESIM switch never closes" was **retracted as unsupported**: it rested on the codes, not on Mode 06.
- An idea that the ESIM contains a solenoid the computer drives was **retracted** after outside literature said the part has none (it is a passive vacuum-operated switch with two weighted valves). The old text stays on the job, marked retracted. The correction was carried into the parts catalogue on 2026-10-20: the part's older "pump" wording now carries a note, and a **design block** (outside literature, with its sources) records the passive design, the thresholds, the orientation rule, the 5 V reference and the tests. It also records what the engine computer can and cannot check: it tracks no code for the switch or vent circuit, so a fault there shows only as the leak codes themselves.
- "0x40 means passed" is false on this computer; "absent from the list means passed" is an inference.
- The Mode 06 gross-leak "pass" is a zero-limit record, carrying no information.
- The lamp does not return "about 5 days after each clear".

## Outside cross-check (literature only)

Eight web searches plus page fetches, all about Chrysler, Jeep or Dodge parts; **none describes the Stelvio ESIM itself**. Where a source could not be opened (a refused request or unreadable file) the notes say so, and claims resting on search snippets are marked.

- The ESIM is a vacuum-operated contact switch with a diaphragm and two weighted valves held shut by gravity; the switch closes at about 1 inch of water of vacuum; the large valve vents at about 0.5 inch of positive pressure, the small valve admits air at about 2.2 inch negative. Because of this, **a positive-pressure smoke test does not load the vacuum seat** [I from O].
- Orientation: the part must mount upright, and a sealing ring can degrade [O, weak]. A parts-tip source describes wrong orientation causing the same three codes on a pickup truck, fixed by re-orienting [O].
- Test conditions: fuel roughly 12 to 88 % (15 to 85 % elsewhere), ambient 4 to 37 C (4 to 43 C for small leak), coolant near ambient for the intrusive test. These are gates: the test does not run. No source says bad inputs make a test fail.
- Lamp: a large-leak code is a two-trip code; a small-leak failure stores a pending code first. Why only P0440 carries the lamp: not found.
- A search summary of a 2022 Challenger bulletin lists P0455, P0456, P0440 and P0441 together, fixed by a computer reprogram; the exact PDF was not isolated.

## Readings-only ledger and certainty

A separate pass used only the 222 observation lines in the store (two fake-stream lines excluded). Result, in the working notes' own words:

**What the readings prove [E]:** the computer held P0440, P0455 and P0456 as failed, pending and confirmed on several dates; only P0440 ever requested the lamp; a reset happened between 2026-10-13 and 10-14 (that it was a clear is inference: the store holds no clear command); P0455 and P0456 failed again between 10-14 and 10-19; the purge side passed on 10-13 only; the two leak records failed on 10-13; the engine-computer software identity never changed; no read ever caught a test failing in the *current* cycle.

**Certainty table:**

| Statement | Grade |
|---|---|
| The three codes are failed, pending, confirmed | Proven |
| The ECM never saw the ESIM switch close in any regime | **Not proven and not provable from the store**: no reading carries switch state; no ESIM word appears in the store at all |
| 0x40 means passed | False |
| Purge circuit and flow are healthy now | No: the only pass is before the 10-14 reset |
| Freeze frames show failures in three regimes | Inference on medium-confidence scaling |
| Mode 06 gross-leak passed | No information |
| Absent from a list means passed | Inference only: list length swings from 72 to 278 codes and no status of `0x00` was ever seen |
| Status bytes are a full history | No: P0456 is in the permanent list while the module list shows `0x40` |
| The engine computer's software is the right one | Not shown: its identity never changed (no reflash), which says nothing about whether it is current |
| A physical leak (cap, hoses, canister, tank) is excluded | No: no reading can rank it against the sense and vent path |
| **A component the readings prove must be replaced** | **None.** No circuit code, commanded test, measured output or stimulus-and-response pair exists |
| The component to test first | The leak-detection chain: the ESIM sense and vent assembly and its signal path. This is a premise the brief supplied; the store never names the ESIM |

**Readings that would prove a replacement** (none taken): the pressure signal and the purge command, fuel level and air temperature logged together through a stimulus applied at the sense port and checked on an independent gauge, with the connector supply, ground and signal in specification (a flat signal alone is not proof, because the store does not say which sensor feeds it); the switch state, if a tool exposes it; a commanded vent close followed by a pressure hold; the failing codes read with failed-this-cycle set, plus snapshot and extended data in the same cycle, before any clear; Mode 06 in two complete cycles with no reset between; and the sense, vent and purge codes dropping out of the list while the leak codes still fail, which would exonerate them. Replacing the engine computer cannot be proven from legislated readings alone.

## Ranked candidates (inference, after the outside cross-check)

1. **ESIM seal, orientation or part**: fitted 2026-09-02, never VIN-verified, orientation not recorded; positive-pressure smoke does not load the vacuum seat. Against: the same codes were present with the original unit.
2. **ESIM switch circuit** (connector in the rear wheel-well area, ground, wiring): the computer cannot self-check it; nothing measured either way.
3. **Engine-computer calibration**: software number unchanged through 2026; no Stelvio bulletin lists the three codes; a VIN check settles whether it is current.
4. **Vacuum supply** (purge valve and hoses): replaced, actuator-tested, flow passed on 10-13.
5. **Canister internal**: new, no liquid fuel; low.
6. **Invalid inputs over the network** (fuel level, ambient): weakest. One log from June read "external temperature" as -61 C in all 61 samples while air temperature read 30 C; this was read once and has not been read since. Outside sources treat these as test gates, not failure causes.

## The ESIM orientation lead

Outside sources say the part must mount upright and that an incorrect orientation can set exactly these codes. The repository recorded that the new ESIM's mounting orientation and port seating were **never logged**. That makes orientation a cheap, specific lead: find out which way up the original unit sat, how the new one is mounted, and bench-test it. The bench procedure is on [[ESIM Bench Test|ESIM-Bench-Test]].

**Its sources, all outside literature, none a reading of this car and none a Stellantis document for the Stelvio:** a trade-magazine article on the Chrysler ESIM (design and thresholds); a parts-maker tech tip (vertical mounting, an adaptor for an angled canister); a repair-database tip about a Ram truck (the module fits four ways and only one is correct; the wrong way gave P0440, P0441 and P0456 with the switch never closing, fixed by re-orienting); and a parts-maker description of the 5 V reference signal. The Stelvio part's own mounting rule was not found, so the service drawing for this VIN decides. In the fault tree the check is **step E9** (free, about ten minutes), followed by **E10** (back-probe the signal: about 5 V at rest, about 0 V under about 1 inch of water of hand vacuum, never 12 V; see [[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]). A replacement fitted the wrong way would reproduce the same codes.

## Next tests, in order

Standing rule: **do not clear again.** When P0440 next reports `0xCD`, read Mode 06 first (all test IDs, raw frames stored) before anything else.

1. VIN checks, no tools: recalls and notices that would have reflashed the computer.
2. Dealer tool, ECM flash tab: record the current calibration number and the latest available. Outdated: flash, then run the small-leak test. Current: calibration stays an unproven suspect.
3. ESIM first: part number against the VIN, mounting orientation, port seating, bench test out of the car.
4. Hand vacuum at the ESIM port with the switch back-probed (outside source: about 4.5 to 5 V open, near 0 V and 0.5 to 2 ohm closed). Hand vacuum only; never shop air; no sparks.
5. Low-pressure air through each hose leg to look for blockage, which smoke cannot show; next smoke test to record flow at every step and where smoke arrives.
6. One live read of the ECM's external temperature, air temperature and fuel level against the dash and a thermometer.
7. Drive until the EVAP monitor completes (cold start, fuel one quarter to three quarters, 20 or more minutes of steady cruise, a long soak), then read status bytes and Mode 06 in CUORE.
8. Record each result on the job with date, values and meaning before the next.

Proof of any fix: the dealer small-leak test (or CUORE's read-only replica until then) plus a completed EVAP monitor with the three codes not returning. A road test alone does not confirm it.

## What the case teaches

- Eleven clears produced eleven restarts of the evidence. CUORE now captures freeze frames and status bytes **before** anything can clear them.
- A smoke test answers "is there a leak", not "is there continuity".
- The legislated route can fall silent (NO DATA) while manufacturer reads work; that is a tool fault, and the scan requirements now say so.
- A part is condemned by a stimulus and a response, not by a code.

Related: [[TSB Layer and Cross-Reference|TSB-Layer-and-Cross-Reference]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].


## ESIM replaced, 2026-10-22 (owner-attested)

- New ESIM fitted with a **new gasket**. The previous ESIM (fitted 2026-09-02) had reused the **original gasket**.
- Orientation changed: the previous ESIM was mounted **white cylinder down**; the new one is mounted **white cylinder up**.
- Recorded on the EVAP job as owner-attested actions and linked as evidence for the ESIM seal/orientation/part hypothesis, now **supported, not confirmed**.
- Proof of fix (readings only, no clearing): drive until the EVAP monitor completes, then read Mode 06 (0.090 in test TID 0x87 must reach at least 3965 ms, against 404 ms before; 0.020 in test TID 0x90 within its limit; it read 6096 ms against a maximum of 6000 earlier) and the P0440/P0455/P0456 status bytes with no fail bits.
- Caveat: orientation and gasket changed together, so a fix will not show which one was the cause. No source states which way up is correct for this part; the monitor result decides.
- **2026-10-23 read (scan SCAN_2610230010, no clearing): EVAP proof INCOMPLETE.** EVAP readiness incomplete; P0440, P0455 and P0456 pending, P0440 and P0456 permanent (status 0x4D); Mode 06 0x3A/0x87 read 496 ms against a minimum of 3707 (404 ms before), 0x3C/0x90 read 6096 against a maximum of 6000 (identical to 10-13). Whether the failing result came before or after the ESIM change cannot be read from the ECM; the P0455 freeze frame (82.7 % fuel, tank now 46 %) suggests before (inference, medium confidence).
- Hypothesis 02c3c411 (ESIM) stays supported; 8c659dfc (EVAP inputs invalid) is weakened, since ambient 8 C and fuel 46 % are plausible and inside the monitor's enable window. Readings, verdict and raw capture: `docs/research/SCAN_2026-10-23_POST_ESIM.md`.
- Next conditions for the proof run: fuel between 15 and 85 % (do not fill above 85 %), a cold soak (the reviewer asks at least 8 h), then a cold start and a drive, repeated over several days; read again without clearing before the 2026-10-28 dealer visit.
