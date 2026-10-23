# Digital rear-view mirror install: plan and cautions

2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115. Written 2026-10-22 from an owner request made the same day ("We also require a digital rear view mirror installed"). Status: **planned. Product not chosen, date not set.** Research only: nothing was read from or written to the car, the adapter or any server.

## Evidence labels

- **[E]** a CUORE reading or a CUORE record on this car.
- **[O]** outside source, with its URL in the Sources section. Never proof about this car.
- **[I]** inference by the writer, stated as such.
- **NOT FOUND** means searched for and not located. It is not the same as "does not exist".

## 1. Scope

In scope: choosing, powering, routing and testing one of three product types, and what CUORE records afterwards.

1. A **full-display mirror** that replaces the OEM interior mirror.
2. A **strap-on (clip-on) mirror cam**: a display that straps over the OEM mirror.
3. A **dashcam-mirror with a rear camera**: a clip-on or replacement mirror body with a front camera and a separate rear camera on a cable.

Out of scope: any coding, PROXI change or module configuration; any work on airbag, ADAS, CAN or LIN wiring; permanent power from the OBD port. Products are not ranked or recommended here; the owner has not named one.

## 2. Product types and choice criteria

| Criterion | Full-display mirror (replaces OEM) | Strap-on mirror cam | Dashcam-mirror with rear camera |
|---|---|---|---|
| Touches the OEM mirror mount | Yes: the OEM mirror comes off its mount [I] | No | Depends: clip-on = no, replacement body = yes |
| Sits in the windshield area near the ADAS camera | Yes | Yes, with a bigger body | Yes, plus a front camera lens |
| Loses OEM features | Possibly auto-dimming and any garage-door transmitter in the OEM mirror (see below) | Keeps the OEM mirror underneath | As the matching mount type |
| Power | 12 V lead, plan in section 4 | 12 V lead | 12 V lead for the mirror and the rear camera |
| Rear camera cable | Needed | Needed | Needed |
| Reverse trigger | Often an optional wire | Often an optional wire | Often an optional wire |
| Reversibility | Lowest | Highest | Medium |

Choice criteria, in order:

1. **Does it leave the forward ADAS camera and the sensor window clear?** Nothing may sit in front of, or shade, the camera area. See 3.1.
2. **Reversibility.** A strap-on needs no mount work. It is the lowest-risk starting point [I].
3. **Key-off draw.** Prefer a unit that runs from a switched (ACC) supply with no parking mode. See section 4.
4. **Cable path.** Prefer a rear camera that mounts inside the glass or at the plate area without drilling, with a cable long enough for the liftgate slack.
5. **Reverse trigger.** Prefer a unit that does not need a reverse signal wire, because the usual tap point is the tail-lamp harness in the liftgate (see 3.4). Many units can show the rear image on a button or all the time [O general, product-dependent].
6. **No CAN or LIN connection.** A product that needs one is rejected.

What the factory car may already have (VIN or build-sheet check needed):

- **ParkView rear camera with rear park sensors**: reported as standard on the entry US 2018 Stelvio in one launch-pricing report; one dealer listing uses the name "ParkView Rear Back-Up Camera" [O, weak: listings describe single cars]. **Whether this car has it is not established.** If it does, the existing screen already shows a reverse image and the digital mirror is a second display.
- **Auto-dimming interior mirror and a garage-door transmitter**: appear on some dealer listings of 2018 Stelvios [O, weak]. NOT FOUND for this VIN.

## 3. Safety: airbags, the ADAS camera, battery drain

### 3.1 The forward ADAS camera behind the mirror

- [O] I-CAR lists the **2018 Giulia** forward-facing camera as "Camera Near Rearview Mirror" (OEM name "Forward Facing Camera Module"). Recalibration is required "if camera is removed/installed or replaced", "if DTC indicates", or "if windshield is removed/installed or replaced". The rear (liftgate) camera has no calibration requirement listed. This is for the Giulia; the Stelvio shares the platform, so it is **[I] likely the same, and NOT FOUND for the Stelvio itself**.
- [O] Shop sources say a scan tool and special tools are needed to calibrate, and that the Stellantis/FCA secure gateway needs registration before special functions can run (Hunter video, via Brake and Front End, seen as a search summary).
- [E] This car has a Bosch **DASM radar** and a Bosch **HALF camera** (`docs/research/CODES_ADAS_CAMERA_2026-10-20.md`). The DASM has stored **C141B-97 "camera blinded/obstructed/blocked"** repeatedly: present on 8 of 18 DASM reads between 2026-09-02 and 2026-10-19, absent on 10, returning 2 to 10 days after clears. CUORE has never read a freeze frame or status for it. No windscreen, tint or dashcam work is on record; that is an absence of a record, not evidence of absence.
- Consequences for this install:
  1. **Do not remove, loosen or touch the camera, its bracket or the cover behind the mirror.** A mirror removal that disturbs the bracket could move the camera [I]. No Stelvio procedure for the mirror button or the module cover was found.
  2. **Mount nothing in the camera's view or over the sensor window.** A mirror body, a front dashcam lens, a sunshade strip or a decal can shade it [I].
  3. **Baseline first.** C141B-97 is already intermittent. Hardware next to the camera changes what a recurrence means, so keep the pre-install history (it is in the CUORE record) and note any driver-assist message after the install. The owner has not yet been asked whether such a message was ever seen [E, from the ADAS note].
  4. **Do not clear DASM or HALF codes** after the install. CUORE refuses clears on safety modules and a clear hides the evidence.
  5. A windshield replacement later needs camera recalibration [O, Giulia]; avoid adhesive fittings on the glass that would have to be removed.

### 3.2 Airbags

- Curtain airbags sit in the roof rails and pillars [general vehicle design; the Stelvio layout was NOT FOUND]. A cable **must not cross the airbag deployment path or interfere with its mounting hardware** [O, Black Box My Car].
- Owner rule for this job: route **behind** the airbag (body side, outside the zone the airbag opens into) and **never in front of it** (cabin side, in the path of deployment). If the trim layout is not clear, do not guess; use the headliner edge and door seal only, or hand the job to a professional.
- **No zip ties on the airbag harness**, and no tape or clips on airbag connectors. Do not probe, splice, cut or move airbag wiring (yellow connectors and harness are the usual marking [O general]; unverified for this car).
- Do not remove a pillar trim that the service information says needs a procedure. FCA service information for this VIN was **NOT FOUND**.
- [E] On 2026-10-14 three short receive-only windows at the wrong bit rate on the chassis bus lit the **airbag lamp with a chime** (Safety Rules). The airbag system on this car has already reacted to bus disturbance. All hands stay off ORC wiring and any CAN-CH wire.

### 3.3 Battery drain and low voltage

- [E] The one low-voltage reading in the whole corpus is the ABS freeze frame of **U1700-87: 10.6 V** on 2026-09-04, speed 0, one startup count before the engine computer stored its first EVAP code (Network and Brake Findings). The network codes centre on the **BCM**. A low-voltage moment can plausibly set body and brake communication codes [I]. The BCM supply reads 14.4 to 14.5 V with the engine running [E], so a low supply is not needed for the codes to be present.
- [I] Any new load that draws current with the car off adds to that risk. A weak battery is one plausible reason for the 10.6 V moment; that is not established. A new parked load is a variable to avoid while the network cluster is being diagnosed.
- [O] This platform was researched as using a single 12 V battery for the loads and for Start/Stop (AGM, Mopar BBH8A001AA, single source). The battery sensor is called IBS in some tool material, while the owner's manual uses "IBS" for the Integrated Brake System (`docs/reference/STELVIO_20T_MAINTENANCE_SPECS.md`, `GIORGIO_MODULE_MAP.md`). Start/Stop depends on battery state, so a sagging battery can disable Start/Stop or cause a hard start [I].
- **Rule: ACC-only power with no parking mode; or, if parking mode is ever wanted, a low-voltage cutoff and a measured quiescent current.** See section 4.

### 3.4 Other cautions from the CUORE record

- **Do not disconnect the battery.** The EVAP proof run is still pending (job 76d3454bce75) and a battery disconnect can reset the readiness monitors [I, general practice]. Use the fuse, not the terminal.
- Dates already planned: rear pads 2026-10-23, dealer visit 2026-10-28 for recall 93C (25V586, fuel pump), accessory belt date unknown. Do the mirror on a separate day, and tell the dealer there is aftermarket wiring in the car.
- **Recall 18V203 (liftgate wiring and switch water intrusion, 2018-03)**: catalogue row `recall-18v203` in `cuore/data/tsb_catalogue.json` (`verified: false`, applies `vin_check`); listed on the Recalls and Campaigns page; no VIN check is on record. The remedy is added sealing on the liftgate wiring connectors and switches [O, Transport Canada 2018150]. A new cable through the liftgate boot must not break that sealing, and an unsealed liftgate harness is a reason not to add anything there until the recall status is known.
- **Recall 18V205 (water corrodes the BCM or its A-pillar connector)** is also on the checklist, and the BCM is the centre of the network cluster. The A-pillar and the passenger kick panel are exactly where the cable and fuse-box work happen. **Do not disturb the A-pillar sealing or the BCM connectors.** Photograph the area (stains, silt line, green or white corrosion) before and after, and do not clean or reseal it.

## 4. Power plan options, with the recommendation

Fuse and circuit facts found (third-party diagram, **not an FCA document**; verify against the diagram in the owner's manual or on the fuse box cover):

- The interior fuse box ("passenger side control unit") is in the cabin, passenger side, in the footwell under the glove compartment area; unclip the acoustic lower trim panel to reach it [O, autouserguide, seen as a search summary]. Third-party 2018 Stelvio diagram: F33, F34 (front windows), **F36 15 A** (infotainment, climate control, alarm, door mirror folding, **EOBD system**, USB port), F38 (central locking), F43 (washer pump), F47, F48 (rear windows), F94 (rear window heater) [O, autogenius].
- The luggage-compartment unit lists **F22 20 A "KL15/a 12 V power socket in the luggage compartment"**, F21 10 A (USB/AUX), F08 30 A (Hi-Fi), F01 40 A [O, autogenius].
- No **cabin ignition-switched (ACC) fuse** for a mirror or camera was identified, and no mirror, camera or rain-sensor fuse is named on that diagram. NOT FOUND.
- [O, search-result summary of Giulia owner posts; the forum pages were behind a paywall and not read] on the Giulia, one owner reports the top row of the footwell fuse box is ignition-switched and the bottom row is always live. Different car, unverified claim.
- [E] The Network page lists BCM feeds including fuse **F82 in the rear power distribution** (bulletin S1808000005) and a stand-alone BCM fuse. **Do not use, borrow from or move either.**

### Option A: the OEM mirror harness

Feed from the OEM mirror connector. Pinout and supply: **NOT FOUND**. Whether the mirror is on LIN, CAN or plain power: **NOT FOUND**. [I] An auto-dimming mirror normally needs only switched 12 V and ground, but on Alfa it may also carry a garage-door transmitter. A Giulia owner post (search summary only) says the mirror harness has an ACC wire and no constant wire. Tapping a wire in that connector without a verified pinout could land on a signal shared with the camera or the rain/light sensor. **Not recommended unless a meter first verifies the pinout and the circuit is shown to be plain power.** Only a plug-in adapter that does not cut or pierce the wire is acceptable.

### Option B: add-a-fuse (fuse tap) in the interior box

The usual hardwire route. Rules from the installer guidance read [O]: follow the adapter's own diagram for orientation; use the fuse rating the adapter specifies; never upsize a fuse to stop it blowing; identify supply with a voltmeter or test light (a continuity beep does not prove a live supply); key-off does not make every fuse position dead. Use a small fuse for the tap's own branch, sized to the product's stated draw and within the tap's rating [I].

- **Choose the circuit by what it is, not by convenience**: not a safety circuit (airbag, stability, horn); not **F36** (it carries EOBD, the head unit and climate control, and the OBD port must stay healthy for CUORE); not the BCM feeds above.
- **ACC (ignition-switched) slot only**, so the unit powers down with the key. Confirm with a meter on both sides of the slot (dead key-off, live key-on) before fitting.
- Record the circuit, its number and rating, and the tap fuse rating (section 8). Name the circuit from the owner's manual or the box cover, not from this document.

### Option C: OBD-port power cable

**Rejected.** CUORE needs the OBD port, the port sits on the diagnostic circuit (F36 carries EOBD, per the diagram above), and a permanent load there risks the adapter session. Never for permanent power.

### Option D: constant feed with parking mode

Needed only for parking-mode recording. [O] Hardwired parking-mode draw is quoted at 50 to 300 mA (two Nexar pages disagree: 100 to 300 mA and 50 to 200 mA). Cutoff suggestions run from 11.6 V (Nextbase kit) to 12.0 to 12.2 V (Nexar, for AGM and Start/Stop) and 11.8 V (a Viofo forum post). One forum poster measured about 14 mA still flowing after a kit had cut off, and another reported a kit that did not stop the drain at its set voltage [O, DashCamTalk, anecdotes]. Nexar's arithmetic: 0.2 A for 8 hours is 1.6 Ah, roughly 3 to 4 percent of a 45 Ah battery. Small on a healthy battery, but unwelcome on a car with a 10.6 V event on record. **Not recommended now.** Revisit only after the network cluster is understood and a measured key-off current is recorded.

### Recommendation

1. **Preferred: Option B, ACC-only, no parking mode.** A fuse tap on a verified switched, non-safety, non-F36, non-BCM circuit in the passenger footwell box; a low-amp fuse in the tap; the rear camera powered from the mirror (not from a second tap); ground to a clean body bolt; no battery disconnect.
2. **If a low-voltage-cutoff product is used (Option D), set the cutoff at or above 12.2 V** [I, from the AGM and Start/Stop figures above] and record the key-off current. Do not change from ACC to constant without recording the new quiescent current.
3. **Never** use the OBD port for power, never splice CAN or LIN, never cut a factory harness (use a plug-in or crimped fuse-tap adapter), never fuse an accessory above what the wire and product need.
4. **Record the quiescent current** (section 8) after the install: key off, doors closed, car asleep, meter in series on the added feed. For an ACC-only fit the expected reading is zero or the product's own standby draw. How long the car takes to sleep is **NOT FOUND**; record the wait actually used.

## 5. Install outline

One day with no other work on the car. No battery disconnect. No adapter on the port during the work.

1. **Before**: photograph the mirror, the cover behind it, the windshield area, the passenger kick panel and the fuse box cover. Record the odometer. Copy the C141B-97 history from the CUORE record. Check the VIN build sheet for the factory ParkView camera.
2. **Choose the product** and check section 2: ADAS clearance, no CAN or LIN connection, ACC power, stated standby draw.
3. **Dry-fit** the mirror (or strap-on) over the OEM mirror without removing the cover behind it. Keep the camera and sensor window clear, and look from the driver seat. If the OEM mirror must come off its mount, stop: the removal procedure and mount type are NOT FOUND for the Stelvio; get the service information or a professional.
4. **Fuse box**: open the lower acoustic panel, identify the ACC slot with a meter (dead key-off, live key-on), fit the fuse tap per its diagram, fit the small tap fuse last.
5. **Front cable route** (power to the mirror): along the door-opening seal, then behind the A-pillar trim edge, then the headliner edge to the mirror, staying out of the airbag zone (3.2). Do not remove the A-pillar trim unless the clip layout is known. No zip ties on any factory harness.
6. **Rear camera route** (if any): from the mirror along the headliner edge, down the C or D pillar side, outside the airbag zone. Hold the cable with supplied clips on trim edges only. At the liftgate use the existing flexible boot or a route that drills nothing; do not cut the boot, force the plug through a connector or puncture a seal [O]. Leave a slack loop so the gate opens fully and closes without tension; open and close slowly and watch for pinching.
7. **Reverse signal** (only if the product needs one): prefer a unit that does not. If one must be used, do not pierce the tail-lamp or liftgate harness (the area covered by 18V203); agree the method before fitting.
8. **Ground** to an existing clean body bolt; no new holes.
9. **Fit the tap fuse**, power the unit with the key on, check function, key off, check it powers down.
10. **After**: photograph the finished route and the fuse tap, and fill in section 8.

## 6. Testing

1. **Bench**: power the unit from a protected bench supply first; check image, brightness, reverse-trigger behaviour (if any) and boot time.
2. **Key-on**: the unit powers up; the dashboard shows no new warning; none appears on cranking.
3. **Key-off**: the unit powers down with the key. Measure the quiescent current in series on the added feed and record it. If the owner agrees, leave the car overnight and re-check for a flat-battery sign.
4. **Liftgate**: open and close it ten times at normal and slow speed; check the cable, boot, water seal and the gate's own motion (power liftgate on listed cars [O weak]).
5. **Airbag and ADAS**: the airbag lamp is normal on key-on; no driver-assist message on the cluster; on a straight road with lane markings, lane and forward-collision functions behave as before [I]. If a message appears, move the product out of the camera area first, then investigate.
6. **Diagnostics**: a CUORE scan (the owner's decision, through CUORE sessions only, no raw adapter scripts) before and after. A new code in the BCM, DASM, HALF or ORC after the install is a reason to undo the install before diagnosing; do not clear anything on a safety module.
7. **Battery**: watch the next cold start and the running voltage; report any slow crank or Start/Stop dropout on the job.

## 7. Diagnostics effects

- **Tapping CAN or LIN wires is not acceptable.** A tap adds a stub and load to a differential bus and can corrupt frames; on this car a disturbance of the chassis bus has already lit the airbag lamp [E]. CAN-CH is never probed. The same holds for LIN.
- **Fusing must be correct**: a fuse in the added feed at the tap; rating no more than the wire and the product need; never a higher fuse to stop a blow.
- **The OBD port stays clear** for CUORE. No cable, tie or plug on or near it.
- An aftermarket device on a switched feed can add supply noise [I, general]. If network codes change after the install, the device is the first thing to remove.

## 8. What to record in CUORE after the install

Record each on the job:

| Field | Value to record |
|---|---|
| Product | Brand, model, type (full-display / strap-on / dashcam-mirror), firmware |
| Part and serial | Part number and serial number of the mirror and the rear camera |
| Fuse used | Fuse box, slot number, host circuit name, tap fuse rating, host fuse rating |
| Supply type | ACC or constant, and how it was verified (dead key-off, live key-on) |
| Current draw key-off | mA, meter and position, wait time before the reading, date and time |
| Ground point | Bolt location |
| Cable route | Front and rear routes, liftgate boot used or not, photographs |
| Reverse signal | Used or not; where taken |
| Airbag check | Cable outside the airbag zone, no ties to any harness, airbag lamp normal on key-on |
| ADAS check | Camera area clear; driver-assist message present or not; C141B-97 history compared |
| Codes before and after | A CUORE scan before and after; anything new |
| Date and installer | Date and name; owner or professional |
| VIN checks | 18V203 and 18V205 answered or not (dealer or regulator pages) |

## 9. Job

A CUORE job was recorded 2026-10-22: status planned, product TBD, date TBD. It holds the owner request, the key cautions and a link to this document. Job id **98a6aad68d72**, in the CUORE state (`C:\ProgramData\cuore\jobs.jsonl`, copied to `data/captures/stelvio-2018/cuore_state/jobs.jsonl`).

## 10. Not found (searched, not located)

- The OEM mirror connector pinout and its supply (plain power, LIN or CAN). Inference only.
- The Stelvio interior mirror removal procedure, the mount type and the module cover behind it.
- The Stelvio forward-camera and rain/light sensor layout in any FCA document (Giulia only, I-CAR).
- The ignition-switched (ACC) cabin fuse for a mirror or camera on the 2018 Stelvio; the FCA fuse diagram.
- A Stelvio-specific digital rear-view mirror install on any forum. Giulia dashcam threads exist but were not readable (paywall); only search-result summaries were seen.
- Whether this VIN has the factory ParkView camera, the auto-dimming mirror or a garage-door transmitter.
- The liftgate grommet layout and the reverse-signal wire on the Stelvio.
- How long the car takes to sleep, and the car's own key-off current (never measured).
- A VIN check for 18V203 and 18V205.

## 11. Sources

Fetched and read (2026-10-22):

- I-CAR, 2018 Giulia forward-facing camera, "Camera Near Rearview Mirror": https://rts.i-car.com/oem-calibration-requirements-search/calv-2719.html
- Transport Canada recall 2018150 (18V203): https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018150
- Third-party 2018 Stelvio fuse diagram (autogenius): https://www.autogenius.info/?p=15692
- Black Box My Car, rear camera on an SUV or hatchback: https://www.blackboxmycar.com/pages/how-to-install-a-rear-camera-on-a-suvhatchback
- Black Box My Car, add-a-fuse facts: https://www.blackboxmycar.com/pages/fuse-facts-the-right-way-to-use-an-add-a-fuse
- Black Box My Car, hardwire a dash cam: https://www.blackboxmycar.com/pages/how-to-hardwire-a-dash-cam
- AutoGuru, Stelvio reversing camera install: https://www.autoguru.com.au/repairs/reversing-camera-install/alfa-romeo/stelvio
- CarExpert, 2018 Stelvio safety (Australian market): https://www.carexpert.com.au/alfa-romeo/stelvio/2018/base/safety-and-security
- Cars.com, 2020 to 2025 Stelvio rearview-camera recall (not this model year): https://cars.com/articles/nearly-63000-alfa-romeo-giulias-stelvios-recalled-for-rearview-camera-issue-517261
- European Auto Glass (general calibration claims; marketing page): https://europeanautoglass.com/alfa-romeo-windshield-replacement-repair-in-paradise-valley/

Seen only as search-result summaries, or blocked:

- Stelvio fuse box location (fetch returned 403): https://www.autouserguide.com/faqs/7455422/Where-are-the-fuse-boxes-located-on-a-2017-2026-Alfa-Romeo-Stelvio
- GiuliaForums threads (HTTP 402 paywall, not read): https://www.giuliaforums.com/threads/dashcam-rear-view-mirror-wiring-diagram.41670/ , https://www.giuliaforums.com/threads/front-and-rear-hardwire-dashcam-install.42608/ , https://www.giuliaforums.com/threads/hard-wiring-a-dashcam.49022/
- AlfaOwner threads (not read): https://www.alfaowner.com/threads/dashcam-installation.1194433/ , https://alfaowner.com/Forum/alfa-giulia/1061377-dash-cam.html
- Brake and Front End, FCA/Stellantis forward camera calibration (fetch returned 403): https://www.brakeandfrontend.com/adas-calibration-fca-stellantis-forward-facing-camera-calibration/
- NHTSA 18V203 owner notice PDF (unreadable by the fetch tool): https://static.nhtsa.gov/odi/rcl/2018/RCONL-18V203-8210.pdf
- Nexar, parking mode: https://www.getnexar.com/blogs/blog/how-to-set-up-dash-cam-parking-mode ; hardwire: https://www.getnexar.com/blogs/blog/how-to-hardwire-dash-cam-step-by-step
- Nextbase, will a dash cam drain the battery: https://support.nextbase.com/hc/en-gb/articles/360006862138-Will-my-Dash-Cam-drain-my-car-battery
- DashCamTalk, parking guard residual draw: https://dashcamtalk.com/forum/threads/veckle-0906-parking-guard-not-working.30915/post-458070
- 2018 Stelvio dealer listing (weak, one car): https://www.mercedesbenzofdelray.com/used/Alfa-Romeo/2018-Alfa-Romeo-Stelvio-79e93c4eac18184b0a44cf946a3106d6.htm
- Alfa Club Victoria, Stelvio electronic tailgate failure (not read): https://www.alfaclubvic.org.au/forum/index.php/topic,23667.0.html

CUORE records used: `cuore/data/tsb_catalogue.json` (recall-18v203), `wiki/Recalls-and-Campaigns.md`, `wiki/Network-and-Brake-Findings.md`, `docs/research/CODES_ADAS_CAMERA_2026-10-20.md`, `docs/reference/STELVIO_20T_MAINTENANCE_SPECS.md`, `docs/reference/GIORGIO_MODULE_MAP.md`, `wiki/Safety-Rules.md`.
