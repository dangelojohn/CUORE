# CUORE adjustments plan: graphs/CSV, service and oil resets, PROXI alignment, battery registration

**Date:** 2026-10-26. **Car:** 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115 (owner reports no security gateway).
**Closes:** point 5 ("missing features") of `docs/design/CUORE_WRITE_CAPABILITY_PLAN.md`.
**Method:** two research passes (subagents) that verified against CUORE's own evidence first (MES capability notes,
MES UI strings, the owner's real MES session logs, CUORE notes/jobs) and only then outside sources, cited and labelled.
Labels: **CONFIRMED** (local evidence) / **OUTSIDE** (cited, not proof) / **UNKNOWN**. No car contact; MES's encrypted
database never opened.

## Summary

| Feature | Verdict | Do now (Stage A) | Next (Stage B) | Later (Stage C) |
|---|---|---|---|---|
| Graph / CSV recording | Being built in CUORE (uses only the existing live session; per-sample timestamps, which MES's FES logs lack) | Record drives (EVAP proof, shudder test), compare two drives, export CSV | - | - |
| Service interval reset | MES does it today (ran 2026-06-07, 10-23, 10-24 on this car, all COMPLETED) | Checklist step after every oil change; verify by MES-log before/after values | Learn MES's write passively; find the 8 service DIDs; record whether 0x27 appears | CUORE may perform it only if no 0x27, read-save-write-readback, consent |
| ECM oil-change reset | MES does it (ran 2026-09-15 twice); which value it writes is UNKNOWN | Checklist step; unofficial pedal method labelled OUTSIDE (6 presses, some say 3) | Learn passively; identify the ECM value | Same gate as above |
| PROXI alignment | Stays in MES (Stage 3) - confirmed right by the evidence | MES-only card; read the CAN configuration first; never align if MES says "not needed" | Learn the roster read passively (expected 0x27/config writes: gate refuses) | Read-back "PROXI compare" only |
| Battery registration (PROXI byte 63) | Stays in MES (Stage 3) | MES-only card; only when the battery TYPE/capacity changes | Find a byte 63 read path | Only with a verified read DID, byte-exact capture, a non-MES key source, backup + tested restore |

**Key verified facts for this car**
- The owner's real Service Interval Reset (FESLog_2610230114) changed: distance-till-next 10268 -> 16000 km,
  days-till-next 324 -> 365, distance-after-last-service 142475 -> 148207 km (= odometer), last service date -> 10/23/2026.
  Interval (16000 km) and period (365 days) unchanged. CONFIRMED.
- The BCM already stores **B10AA-4A "PROXI configuration incorrect component installed"** and the PROXI write counter
  reads 1 (MES module reads 2026-10-23). CONFIRMED. Worth raising with the dealer on 2026-10-28.
- CUORE has **no DID** yet for any of the 8 service parameters, no read path for PROXI byte 63, and the IBS DIDs are unverified.
- The only real attempt to read this car's CAN configuration (FESLog_2610230124) ended "Failed to connect to Body
  Computer (BCM)", so this car's node roster is not yet held.

## Open owner questions
1. Was an ECM "Oil change" reset run on 2026-10-24 (no log found)? What does the cluster show now?
2. Which battery is fitted (type, Ah, CCA from its label), and was it ever replaced?
3. Pedal method: 6 or 3 presses? CUORE job 6d55b2e32b2a says 3; forum service-manual text says 6.

---

## Part 1 - Plan: oil-change reset (ECM) and service-interval reset (2018 Stelvio 2.0T)
Date 2026-10-26. Research only. No car contact, MES database untouched.
Labels: CONFIRMED (local evidence), OUTSIDE (cited), UNKNOWN.

### 1. What each reset changes, and when it is needed

### (a) Oil-change reset, ECM (Magneti Marelli IAW 10JA)
- CONFIRMED: MES runs it as an adjustment on the ECM. Real logs FESLog_2609152049 and FESLog_2609152050 (2026-09-15 20:48 and 20:49) read "EXECUTING ADJUSTMENT... Oil change ... COMPLETED", with "Engine running" noted. They have no Old/New value lines and no parameter block. Each shows only the ECM identity block (VIN, operating time 292558, startups 14415).
- CONFIRMED: menu path and sources are in `mes-log-mcp/mes/mes_functions.py` row oil_change_reset_ecm (~lines 209-221) and in `docs/research/MES_VS_CUORE_CAPABILITY_2026-10-14.md` line 57 ("Engine -> Magneti Marelli IAW 10JA ... Adjustments tab -> Oil Change", CORROBORATED). Those sources are forum threads, so the confidence is forum-level.
- UNKNOWN: which ECM value is written. CUORE has no catalogued DID for it. MES shows no value.
- OUTSIDE (forum, not Alfa documentation): this is the engine-side oil-life/degradation counter. A forum member also says the same tool resets the UniAir adaptive parameters (https://www.stelvioforum.com/threads/oil-change-interval-reset.11605/ and page-3). Treat the UniAir claim as unverified.

### (b) Service Interval Reset (MES "Service" module, ISO code 00 03 50 8B 14)
- CONFIRMED: this is a separate module from the ECM. Its identity block shows ISO code only, with no part numbers.
- CONFIRMED by FESLog_2610230114 (2026-10-23 01:13, 710 lines, not a simulation: 0 "SIMULATION" lines). It reads 8 parameters, each shown as "Name: value unit":
  1. Odometer 148207.0 km
  2. Distance after last service 142475 km
  3. Last service date 09/12/2026 (MES date format; ambiguous whether this is 12 Sep or 9 Dec, but see the 2026-09-15 oil reset)
  4. Number of services 0
  5. Service interval 16000 km
  6. Service period 365 days
  7. Distance till next service 10268.0 km
  8. Days till next service 324 days
- CONFIRMED adjustment block (line 636): "EXECUTING ADJUSTMENT... NEXT SERVICE KM RESET ... COMPLETED". There is no Old/New wording. The change is visible only by re-reading the parameters. After the reset:
  - Distance after last service 142475 -> 148207 km (equal to the odometer)
  - Distance till next service 10268.0 -> 16000.0 km
  - Days till next service 324 -> 365 days
  - Last service date 09/12/2026 -> 10/23/2026
  - Unchanged: Number of services 0, Service interval 16000 km, Service period 365 days. The counter-style rows refreshed, not the interval settings.
- CONFIRMED: the same adjustment ran on 2026-06-07 (FESLog_2606070950: adjustment block only, COMPLETED) and on 2026-10-24 12:59 (FESLog_2610241300: two "EXECUTING ADJUSTMENT" lines, one headed "Last service date", then NEXT SERVICE KM RESET COMPLETED). The 10-24 log has no readable values. The 10-20 log is simulation and is ignored.
- CONFIRMED CUORE record: the oil and filter change was 2026-10-24, 5.2 L Pennzoil Platinum Euro LX 0W-30, at 148,226 km (notes.jsonl entries c8e0e0bc85ea and c52c5c2b5002). The 10-24 12:59 service reset fits that visit. The 10-23 01:13 reset was done before the oil change. The owner may have re-run it afterwards to set the date.
- UNKNOWN: the owner's own statement about whether an ECM "Oil change" adjustment was run on 2026-10-24. No ECM oil-reset log for that date appears in the grep results. CUORE job 6d55b2e32b2a holds an open question on this.
- Interval limits, CONFIRMED in `mes-log-mcp/mes/service_specs.py` lines 157-177: the owner's manual caps the interval at 1 year or 10,000 mi (16,000 km), which matches the 16000 km / 365 days that MES reads. OUTSIDE source: 2018 Stelvio manual P124461 (https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf).
- When a mechanic needs them: after every oil and filter change, so the cluster reminder and the service counters restart. Without a reset the "oil change required" message can persist.
- OUTSIDE (forum): the two resets are not coordinated. The dash/ECM oil message and the infotainment service counter ("coupons") are separate, and both may need a reset (https://www.stelvioforum.com/threads/oil-change-interval-reset.11605/, https://www.stelvioforum.com/threads/multiecuscan-help.19957/, https://www.stelvioforum.com/threads/scheduled-maintenance-reset.24621/).
- The MES function table notes "SGW bypass may be required on later cars". This does not apply here, since the owner reports no gateway, and MES completed the write on this car three times.

### 2. Can it be done without a tool?
- OUTSIDE (forum-quoted service-manual text, not from the owner's manual PDF, which I did not open): oil-change indicator reset by accelerator pedal.
  - Ignition ON, engine off, brake NOT pressed.
  - Fully and slowly press the accelerator 6 times within 10 seconds.
  - Ignition OFF, then restart. If the message returns, the reset failed.
  - One quote says 3 presses. Owners report mixed results, and some say it does not work on the 2018 TI Sport.
  - Sources: https://www.stelvioforum.com/threads/2018-stelvio-how-to-reset-oil-change-reminder.17261/, https://www.stelvioforum.com/threads/reset-oil-service-indicator.14049/, https://www.alfabb.com/threads/oil-change-required-message.689787/
- CUORE already carries this method in job 6d55b2e32b2a (note 59c69c60: "unofficial accelerator-pedal method ... 3 times"; the 3 versus 6 discrepancy is real, so the mechanic should try 6 first and then 3). Dealer wiTECH "IPC, Misc Functions, Maintenance Reset" is the other path listed there.
- UNKNOWN: whether the pedal method also clears the infotainment/BCM service counter. Forum owners say it does not.
- UNKNOWN: the cluster-menu reset. One independent site describes a steering-wheel menu path. It is unverified, so do not offer it.
- Answer: yes for the dash oil message, outside the owner's manual. CUORE can direct the mechanic to it today, labelled as an unofficial procedure. The service-interval counter has no known tool-free method.

### 3. What CUORE can verify read-only
- CONFIRMED: CUORE has no DID for any of the 8 service-module parameters. grep of `cuore/live/did_catalog.py`, `addressing.py` and `channels.py` finds only: ECM 0x2001 Odometer (unverified, danardi78 source), ECM 0x2003 programming events, ECM 0x3A41 oil level (read 5.31 L on 2026-10-24), and Engine oil temperature and pressure channels. `owner_events.py` records the oil change itself.
- UNKNOWN: the DID or module for each MES service parameter. The identity of the "Service" module (ISO 00 03 50 8B 14) in CUORE addressing is not established. Candidates are IPC 0x60 and BCM 0x40, but nothing in the evidence supports either.

| MES parameter | CUORE DID today | Verify route |
|---|---|---|
| Odometer | ECM 0x2001 (unverified) | read, compare with the cluster |
| Distance after last service | none | needs capture |
| Last service date | none | needs capture |
| Number of services | none | needs capture |
| Service interval (km) | none | needs capture |
| Service period (days) | none | needs capture |
| Distance till next service | none | needs capture |
| Days till next service | none | needs capture |

- Soon, with no car contact: read MES logs after a reset. `mes-log-mcp/mes/service.py` and `check_service.py` already parse the service block. This verifies a reset by its before/after values, as the 10-23 log shows (142475 to 148207, 10268 to 16000, 324 to 365).
- Soon, with consent: use the existing DID-discovery tools (`discover_module_dids`, `learned_dids`) on the IPC/BCM with read-only service 0x22, guarded by CUORE's own safety layer. Then correlate any discovered value against the MES parameters in the capture above (e.g. 16000, 365, 148207). That correlation is the proof; nothing else is.

### 4. What a learned MES capture must show before CUORE performs it
- A passive capture (second adapter and Y-splitter, per the write plan) of one MES oil-change reset and one MES service-interval reset, each with a before and after read.
- For each, record: target module and address; the diagnostic session service (0x10) and sub-function; whether 0x27 SecurityAccess appears (UNKNOWN until captured); the write service (0x2E data identifier, 0x31 RoutineControl or 0x2F IO control) and the exact payload; the response; and the read-back values that changed.
- Pass test: payload identical across two runs apart from the date/odometer-bearing fields. If a seed/key exchange (0x27) is seen, CUORE does NOT perform it. The standing rule forbids 0x27, and MES's encrypted database stays closed.
- CUORE `safety.WRITE_SERVICES` already refuses RoutineControl (0x31, `channels.py` ~line 199). That gate must stay closed for any unlearned operation.

### 5. Staged plan

### Stage A (now: direct and verify read-only)
- Add both procedures as checklist steps after an oil change: (1) the pedal method, labelled unofficial and OUTSIDE; (2) MES ECM Oil Change; (3) MES Service Interval Reset.
- Record the owner-reported reset outcome in the oil-change ledger (a job action naming which reset, when, and the odometer).
- Verify by MES log read-back: the new Distance till next service should be the interval (16000 km) and Days till next service the service period (365 days). The last-service date should be the work date.
- Acceptance: the job holds a log filename and parsed before/after values, and each claim is labelled CONFIRMED, OUTSIDE or UNKNOWN. The 3 versus 6 press discrepancy is flagged.
- Open owner questions: was an ECM oil reset run on 2026-10-24, and what does the cluster show now?

### Stage B (learn, then gate)
- Passive capture sessions for both resets (consent, no CUORE traffic during MES use). Run `mes_learn_*` to extract the DIDs and the write exchange.
- Acceptance: both write sequences are documented with response bytes; 0x27 present or absent is recorded per procedure; the service-parameter DIDs are catalogued with "learned" confidence and checked against the 8 MES values.
- Gate: if 0x27 is present, mark the procedure MES-only. Otherwise draft a read-then-write-then-read design.

### Stage C (perform with consent, only if B shows no 0x27)
- Read and save the full before state (all 8 values plus ECM oil DIDs) to the vehicle record. Show the exact frame and the expected change. Require explicit consent and the oil-change ledger entry first.
- Write once, read back, and compare. Stop on any negative response and never retry.
- Acceptance: the read-back equals the Stage B expected values, the audit log shows the single write, no DTCs were added (cluster and airbag lamps unchanged), and a later MES read agrees.
- Any step that cannot be proven this way stays with MES.

### Sources
Local:
- `docs/research/MES_VS_CUORE_CAPABILITY_2026-10-14.md` lines 57-58
- `mes-log-mcp/mes/mes_functions.py` ~209-237
- `mes-log-mcp/mes/service_specs.py` 157-177
- `cuore/live/did_catalog.py` (0x2001, 0x2003, 0x3A41)
- C:\Program Files (x86)\Multiecuscan\FESLog_2610230114, 2610241300, 2606070950, 2609152049, 2609152050 (the Lang\English.txt search found no oil or interval strings beyond "Service" at 1108 and "days" at 334)
- C:\ProgramData\cuore\notes.jsonl (c8e0e0bc85ea, c52c5c2b5002, a6974988f1b3) and jobs.jsonl (job 6d55b2e32b2a: actions 59c69c60, 7cba31df, 12dcd7aa)

Outside (forums and search summaries; the owner's manual PDF was not opened):
- https://www.stelvioforum.com/threads/2018-stelvio-how-to-reset-oil-change-reminder.17261/
- https://www.stelvioforum.com/threads/reset-oil-service-indicator.14049/
- https://www.stelvioforum.com/threads/oil-change-interval-reset.11605/
- https://www.stelvioforum.com/threads/multiecuscan-help.19957/
- https://www.stelvioforum.com/threads/scheduled-maintenance-reset.24621/
- https://www.alfabb.com/threads/oil-change-required-message.689787/
- https://vehicleinfo.mopar.com/assets/publications/en-us/Alfa_Romeo/2018/Stelvio/P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf

---

## Part 2 - PROXI alignment (952) and battery type registration: stay in MES? (research only, no car contact)

Labels: CONFIRMED (local) / OUTSIDE (cited) / UNKNOWN. Paths are under C:\Users\User\mcp-servers unless stated.

### 1. What each procedure does, modules, when needed

**PROXI alignment**
- CONFIRMED (local): MES menu "CAN Setup / PROXI ALIGNMENT PROCEDURE (952)", Adjustment tab; cable switching per MES prompts; battery support advised (mes-log-mcp/mes/mes_functions.py row proxi_alignment_952, lines 191-203).
- CONFIRMED (local): MES decides by reading the CAN configuration and comparing the node roster. Its own strings: 1084 "Reading CAN configuration data ...", 1083 "This vehicle is properly configured. PROXI Alignment is not needed!", 1081/1082 "Too many new/removed modules detected!", 6225 "WRITING PROXI DATA" (C:\Program Files (x86)\MultiEcuScan\Lang\English.txt, read-only grep).
- CONFIRMED (local): the roster uses per-node status Ok / EOL Ok / EOL Failed / Added / Removed (docs/format/FES_LOG_FORMAT.md section 2.3, lines 120-140). Alignment reconciles Added/Removed/EOL Failed nodes with the BCM's PROXI.
- CONFIRMED (local): PROXI is a BCM data area, not a separate node; the stelvio_scan 0x6D PROXI address is UNVERIFIED and likely wrong (docs/reference/GIORGIO_MODULE_MAP.md lines 55-58).
- CONFIRMED (local): downstream modules compare their stored config to the BCM's; a mismatch sets P1500 in the TCM with limp-in and no positive-torque requests (docs/reference/ZF8HP_SERVICE_DATA.md line 232; STELVIO_20T_DRIVETRAIN_SPECS.md line 77).
- CONFIRMED (local): FCA bulletin S2108000163 covers PROXI sequencing when several modules are replaced (docs/reference/TSB_CATALOGUE.md line 231). Flash recall docs for this car say "perform PROXI Alignment" after PCM reprogramming (docs/vehicles/ZASFAKPN5J7B88115/pdf-sources/make_flash_pdf.py lines 81, 139).
- OUTSIDE: needed after module replacement, module software update, dead battery or Restore Vehicle Configuration; a flashing odometer / DTC B2204 on Jeep WL/WS is the symptom. NHTSA TSB MC-10212320 summary [1][2].

**Battery type registration (byte 63, bits 0-3)**
- CONFIRMED (local): MES path CAN Setup -> Adjustments -> PROXI byte 63 bits 0-3, patterns 80Ah/680A, 95Ah/800A, H7/H8 flooded/AGM; classed "coding", prerequisite is the proxi_alignment_952 access path; "static configuration, not a live-learn routine" (mes_functions.py lines 239-250).
- OUTSIDE (forums, unofficial): xxxx0001 = 80Ah 680A EU default; xxxx0010 = 95Ah 800A US default; H8 AGM = xxxx1011 (0x8B) [3][4].
- OUTSIDE (forums): the setting tells the IBS/charging logic which battery it is charging; one owner says an AGM or lead-acid battery is not charged properly unless the type is changed; another says effect on charging strategy is not confirmed/tested; others fitted AGM with no change and no adverse effect [3][4][5].
- Needed (OUTSIDE, inference from forums): only when the new battery differs in type/capacity from what byte 63 holds. Same-type swap: no registration reported; CUORE's own note records "after a new battery the IBS needs 1 crank plus 2-4 h sleep to relearn (TSB S1408000384); no registration step found" (C:\ProgramData\cuore\notes.jsonl, 2026-10-24 research note, vehicle target). That TSB text is OUTSIDE research stored locally.
- CONFIRMED (local): TSB S1408000384 carries "DO NOT BLIND CHARGE" and the U113E lost-communication-with-battery-sensor test (TSB_CATALOGUE.md lines 100, 225).
- UNKNOWN: which battery is fitted to this car and whether byte 63 matches. Local research lists Mopar AGM as single-source for the platform (docs/maintenance/DIGITAL_REAR_VIEW_MIRROR_INSTALL.md line 74). No battery-replacement record found in notes.jsonl or jobs.jsonl.

### 2. Risks if it fails or is done wrong
- CONFIRMED (local): the project's own reason for Stage 3 is "risk of a module that will not start or not communicate" (CUORE_WRITE_CAPABILITY_PLAN.md line 65).
- CONFIRMED (local): a failed or partial config leaves the TCM P1500 limp-in condition (see above); BCM already stores B10AA-4A "PROXI configuration control - Incorrect component installed" on this car (MES_MODULE_READS_2026-10-23.md line 136), and the car's PROXI write counter reads 1 (lines 43, 100, 124).
- OUTSIDE: failed alignment points to an unresponsive module, wrong-VIN used module or wiring fault; the scan tool names the module [2][6][7]. Anecdotal (Ram forum): B10AA "Check Configuration Failed" [6].
- OUTSIDE: battery disconnect/low voltage during FCA programming is itself a known hazard (diag.net thread title "Caution on FCA Vehicles - Disconnecting the Battery") [8]; content not read, UNKNOWN details.
- Wrong battery byte: OUTSIDE/unconfirmed: possible poor charging or Start/Stop behaviour; no cited source quantifies it.
- UNKNOWN: MES write backup/rollback behaviour for PROXI. No local evidence of a restore path.

### 3. What CUORE can verify read-only, and what it holds

Holds now (CONFIRMED local):
- IBS composite read: DID 1005 on 18DA40F1 (SoC %, temp, voltage, current) and 19BD SoC; both UNVERIFIED on the 2.0T (docs/reference/GIORGIO_MODULE_MAP.md lines 141, 158; STELVIO_READABLE_ITEMS.md lines 82, 108). The MES log format carries "IBS Battery charge status" in % (FES_LOG_FORMAT.md line 227). MES capability row ibs_battery_sensor_read says "no CUORE DID for IBS" (SINGLE-SOURCE) - this conflicts with the GIORGIO row; treat IBS read as unverified until a live read.
- Voltage: ATRV reading; MES log 2026-10-23 showed Battery voltage 11.7 V (engine off); CUORE port read 14.4 V (engine running) on 2026-10-25 (notes.jsonl a915407487b5).
- PROXI configuration write counter = 1 and BCM code B10AA-4A, from MES logs (MES_MODULE_READS_2026-10-23.md).
- Node roster for THIS car: NOT held. The only real non-simulation Stelvio 2.0 log that opens with "Reading CAN configuration data ..." is FESLog_2610230124 and it ends with "Failed to connect to Body Computer (BCM)" (2 lines, no roster). The other Stelvio 2.0 logs have no EOL/Node lines. Roster parsing (fes.py NODE_RE, line 77) has only seen other cars. EOL status for this car: UNKNOWN.
- Battery in parts catalogue: C:\ProgramData\cuore\parts_catalog\stelvio-2018-2.0l\catalog.json has a "Battery, Battery Tray and Cables" section; no Ah/CCA option set extracted in my check (UNKNOWN beyond the section name). Not used further.

Could verify read-only (not done, no car contact):
- Before/after snapshot: BCM DTC list (B10AA), TCM P1500 absence, IBS SoC/voltage, key-on voltage. These are all standard reads CUORE already does.
- Byte 63 read: UNKNOWN whether a read DID exists; MES reads PROXI through its encrypted DB (not opened, standing rule). CUORE cannot read byte 63 today. Candidate route: MES screenshot/export of the PROXI byte dialog (Ctrl+Alt+C), recorded by hand.

### 4. Is Stage 3 (stay in MES) right?
Yes, for now. Evidence:
1. CONFIRMED (local): CUORE has no PROXI/configuration write path and no 0x27 key material; MES holds those in its encrypted DB, which is off limits (CUORE_WRITE_CAPABILITY_PLAN.md; MES_VS_CUORE row cuore_today).
2. CONFIRMED (local): PROXI is spread across BCM and downstream modules, cable switching is manual (A5/A6), and a failure has a documented limp-in outcome (P1500).
3. OUTSIDE: even FCA's own routine (wiTECH) fails on non-responsive modules; failure diagnosis needs expertise [2][7].
4. No CUORE readback exists for byte 63, so CUORE could not prove a write.
What would have to be true to move either to CUORE:
- Battery registration (lower risk, one byte): a verified read DID for byte 63 (or the PROXI block), a byte-exact capture of MES's write on this car, the module's security level and key derivation obtained from a source that is not MES's database, read-back match, and a stored original-PROXI backup with a tested restore. Only then.
- PROXI alignment: all of the above plus roster-diff logic validated on several cars, a power-supply guard (stable battery), and restore proven on a bench BCM. Not realistic on the owner's only car.

### 5. Staged plan

**Stage A (now)**
- Add a "MES only" card to the job page for both procedures: when needed (module replaced/flashed, roster shows Added/Removed/EOL Failed, MES says "not needed" otherwise; battery type changed), exact MES menu paths from section 1, battery support on, no door/key cycling, cable change per MES prompt, record who/when/why.
- Before (read-only via CUORE sessions): BCM and TCM DTCs (note B10AA, P1500), battery voltage, IBS SoC/voltage if the DID answers; owner states battery type/Ah from the plate (UNKNOWN today). In MES: run only the "Reading CAN configuration data" step first; save its log (this captures the roster that CUORE lacks).
- After: same reads; MES log with the byte 63 pattern; PROXI write counter should rise by 1 if a write happened (counter is currently 1). Acceptance: no new codes, B10AA state recorded, IBS charge status plausible after 2-4 h sleep (OUTSIDE TSB note above).
- Service-interval reset stays "MES only"; the read-back path is now the read-only service-value discovery on the MES-parameters page (/v/{vin}/mes-parameters, UDS 0x22 only; candidates unconfirmed until a value changes after a real reset).
- Gate: do NOT run alignment if MES prints "PROXI Alignment is not needed!". Do not blind charge.

**Stage B (learn passively, only with owner consent and MES doing the work)**
- With the existing MES-learn feature, record the bus while MES runs the roster read; expected to include 0x27 SecurityAccess and configuration writes, which the CUORE gate refuses and must never replay. Keep only: DIDs read, addressing, timing, counter values. Do not store seeds/keys.
- Acceptance: a documented byte 63 read path (DID or block) and the full roster for this car stored in CUORE; no write sent by CUORE.

**Stage C (only if evidence ever allows)**
- Preconditions in section 4. Start with a read-back-only "PROXI compare" tool (current vs MES-logged bytes), never a writer. Any writer needs: written owner consent, full PROXI backup, stable-voltage check, MCP-only with consent, one byte at a time, immediate read-back, rollback test on spare hardware. Acceptance: matched read-back on three consecutive cycles and zero new DTCs.

### Sources
- [1] NHTSA TSB MC-10212320 (Jeep WL/WS flashing odometer / B2204 / Proxi routine): https://static.nhtsa.gov/odi/tsbs/2022/MC-10212320-9999.pdf (via search summary only, PDF not read)
- [2] go-parts B2204 Cherokee: https://www.go-parts.com/garage/obd-b2204-jeep-cherokee-2014-2020 (summary only)
- [3] Giulia Tech MES compilation: https://giuliatech.com/t/multiecuscan-mes-popular-settings-compilation/80
- [4] Giulia Forums AGM PROXI thread: https://www.giuliaforums.com/threads/what-are-proxi-parameters-for-agm-battery-on-giulia-2-2.65519/page-3
- [5] Alfa Owner battery replacement: https://www.alfaowner.com/threads/battery-replacement.1190455/ (summary only)
- [6] Jeep Cherokee Club failed proxy alignment: https://www.jeepcherokeeclub.com/threads/help-with-failed-proxy-alignment.246956/ (summary only)
- [7] appcar-diagfca PROXI alignment guide: https://appcar-diagfca.com/en/diy/proxi-configuration-alignment/ (vendor, summary only)
- [8] diag.net, "Caution on FCA Vehicles - Disconnecting the Battery": https://diag.net/msg/m4oauyn8nfysjhbmb8rpygoywe (title only)
- Forum byte values are community compilations, not Alfa documentation; the search tool returned snippets and I did not open the pages (time/token limits), so quotes are second-hand.
- Local: files cited inline above; MES ECU database never opened.

---

## Status 2026-10-26 (later the same day)

Checked against the code. Nothing above is rewritten.

**Decisions**
- **PROXI alignment and battery registration stay in MES permanently for this car.** Reasons:
  they need UDS SecurityAccess (0x27) whose keys sit only in MES's database; a failed or
  partial alignment leaves the TCM in P1500 limp-in; and there is no spare BCM to recover
  with. Part 2's Stage B and C for these two are withdrawn; the MES-only card (Stage A)
  stands.
- **The service-interval reset is the first write target** (Part 1). The oil-change (ECM)
  reset follows only after the service one is proven.

**What now exists for Part 1, Section 3 ("what CUORE can verify read-only")**
- `cuore/live/service_dids.py`: 0x22-only sweep of the IPC and ECM on CAN-C (max 576
  requests, about 144 s), matched against the values in the 10-23 log (16000 km, 365 days,
  odometer, last service date) under many decodings (1-4 byte, both endians, x10, BCD and
  binary dates). Tools `service_dids_plan` / `service_dids_discover` / `service_dids_results`
  and a section on `/v/{vin}/mes-parameters`.
- Every hit is labelled "candidate - unconfirmed until it changes after a reset". The same
  value can match two quantities (16000 is both the interval and the countdown after a
  reset); the matcher says so in a warning. The proof remains: re-run after the next MES
  reset and see which DID moved off 16000.
- It has not been run on the car. The 8-row table in Section 3 is unchanged: still no
  confirmed DID.
- The sweep needs MES closed, no live poll, plain cable on CAN-C, ignition on, engine off.

**What now exists for Stage B/C**
- `procedure_dry_run` replays a capture through the real gate and replay logic on a fake
  session and prints the exact would-send bytes. This is the "dry run" step of the plan.
- `actuate` tightening: a stop step counts only if accepted; target-byte check; bounded
  adapter-lock wait.
- Consent phrases: `CLEAR ALL EMISSIONS CODES` (clear), `SEND RAW <SS> TO <MODULE>` (raw
  write).

**Revised order for the service reset**
1. Next car connection: discovery (after the cold RFHUB read and the EVAP reads); record
   candidates.
2. Capture one MES service reset: second adapter plus Y-splitter, or the PC-side serial
   mirror (design in preparation: `docs/design/SERIAL_MIRROR_CAPTURE.md`).
3. Dry-run, then gate.
4. First real write with consent and read-back, compared with the before/after pattern
   from FESLog_2610230114.

**Caveat from the code.** The service module is the IPC. The raw-send path refuses IPC, and
refuses 0x2E and 0x31 on every module. `actuate` allows 0x31 and 0x2F, not 0x2E. Whether the
reset is a 0x2E write or a 0x31 routine is UNKNOWN until captured; if 0x2E, CUORE cannot
send it under today's rules and the owner would have to decide whether to change them.
