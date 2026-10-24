# Interface box deployment plan: 2018 Stelvio 2.0T

Car: 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115, Canada, about 148,207 km. Written 2026-10-24. **Status: plan only. No product chosen, nothing bought, nothing installed.** Nothing was read from or written to the car, the adapter or any server for this document.

This document does not recommend any product. Paid products are listed with their listed prices and compared on objective criteria. The owner chooses.

## Evidence labels

- **[official]**: manual, TSB, NHTSA or wiTECH document.
- **[listing]**: vendor or retailer page. A sales claim, not verified.
- **[forum]**: owner post. Anecdote. Most forum pages could not be opened and came from search excerpts.
- **[inference]**: reasoning, not stated by any source.
- **[CUORE record]**: a reading or rule already held for this car.

"Not stated" means the source is silent. "Ask vendor" means we must get the answer in writing. Prices are as listed, in the currency shown. Duty, shipping and tax are extra.

---

## 1. Goal and scope

**What this route gives**

- Apple CarPlay and Android Auto on the factory screen, if the box has them (most do; the Ampire RL4-C3D does not) [listing, official].
- Optional front and rear camera inputs shown on the factory screen [listing].
- The factory screen, radio, rotary knob and steering keys stay in place [listing]. The knob is a known weak point on 2018 cars (section 8) [forum].

**What it does not give**

- No touchscreen. The factory screen stays non-touch [forum].
- No 360 view that anyone has shown working. 360 through a box is a vendor claim only [listing]. No owner report was found [inference from the research note].
- No change to the radio's own software. A box does not update the ETM.
- Not a fix for any open code. It is a new variable on the radio's connectors, so it makes diagnosis harder, not easier [inference].

**Scope of this plan**

- Route B only (interface box). Routes A, C and D are out of scope (see INFOTAINMENT_CAMERA_UPGRADE_OPTIONS.md).
- The digital rear-view mirror is a separate job (98a6aad68d72). Do not combine them on the same day [inference].

**Why the radio bus matters**

- The radio (ETM) is on CAN-C, the main powertrain bus. HVAC is on CAN-IHS [CUORE record, owner MES 2026-10-23].
- A box that sits in series with the radio's connectors therefore touches CAN-C, not the quieter interior bus [inference]. The earlier risk matrix was raised one notch for this reason (Medium-high became High) [inference, Correction 2026-10-23].
- The radio's CAN-C address is unverified (likely 0x6F) [CUORE record].
- None of the boxes below is known to be CAN-passive [inference]. No source tested any box on this car.

**Hard rules for this car**

- The 2026-10-14 incident: a raw wrong-bitrate CAN listen lit the airbag lamp. All diagnostic bus contact goes only through CUORE sessions at confirmed bitrates [CUORE record].
- Never clear codes during the open EVAP proof (job 76d3454bce75) [CUORE record].
- Do no install work before the EVAP proof run and the 2026-10-28 dealer visit [CUORE record].

---

## 2. Pre-install checks (owner tasks)

Do these before buying anything. All are read-only.

| # | Check | How | Why it matters | Record |
|---|---|---|---|---|
| 1 | **Build date** | Read the manufacture date (MDH) on the door-jamb label | TSB 08-029-20 targets MV-002.010.041 for 2.0 radios on Stelvios built on or before 2018-01-11 [official]. The build date is not yet read. | Date, photo of label |
| 2 | **Factory AUX / USB** | Look in the centre console and armrest area for an AUX jack and USB ports | Abt says the vehicle "MUST be equipped with factory AUX input" [listing]. APPplay says AUX is required for USB or Mirrorlink [listing]. Whether a 2018 North American Stelvio has an AUX jack is UNVERIFIED. AU/NZ listings show one [listing]. | Yes / no, photo |
| 3 | **Radio software** | Read from the radio menu after any TSB 08-029-20 update | Owner read MV-002.009.043 / TV-002.009.043, map 971.7832 (meaning unconfirmed) [CUORE record, 2026-10-23]. | Exact strings |
| 4 | **Screen size and type** | Confirm 8.8 inch, non-touch | Several boxes are keyed to size (dip switches, harness). Size is not recorded in the repository [inference]. | Size, touch yes/no |
| 5 | **Connector check** | At install time, with the radio out: confirm the Quadlock (48-pin) and the screen cable (LVDS) match the box harness | The IMI-1000 guide says a MOST fibre line may sit in the Quadlock and must be moved if present [listing]. Harman Kardon amp presence is also unknown [inference]. | Photo of both connectors |
| 6 | **Battery health** | Measure rest voltage after the car has sat 12 hours or more, with a load test if a shop offers one | The 10.6 V freeze frame on ABS U1700-87 and the airbag lamp event show the car is sensitive to low voltage [CUORE record]. | Rest voltage, date, time |
| 7 | **Charger plan** | Have a charger that holds voltage (maintainer mode) ready for the work day | Protects the car while the radio is out and the ignition is cycled [inference]. | Charger model |
| 8 | **BASELINE CUORE scan** | Full scan of all modules and all DTCs with status bytes. Read-only. Through CUORE sessions only. | Needed to prove later that the box added nothing [inference]. | Save the scan file name |

**Baseline scan rules**

- Use a CUORE session at confirmed bitrates only. Never a raw adapter script [CUORE record].
- Do not clear anything. Not before, not after [CUORE record].
- Save the scan before any work and note the date, odometer and battery voltage.
- Include the radio (ETM) identity if CUORE can read it. The radio has never been read [CUORE record].

**Radio update interaction**

- The planned radio update comes BEFORE any box [CUORE record].
- TSBs 08-081-19 and 08-065-20 say MV-002.009.059 or lower is an "early 2.0 radio" that cannot take their 2.5-radio software (085/090) and point to other bulletins [official]. TSB 08-029-20 is that other bulletin: its Step 8 lists "MV-002.008.041, MV-002.009.043, MV-002.009.053, MV-002.009.055 or MV-002.009.059" as "update the ETM", and "MV-002.010.041 ETM has the latest available software" [official, NHTSA PDF read 2026-10-24]. So MV-002.009.043 has a defined path to MV-002.010.041, provided the build date fits.
- TSB 08-029-20 (2020-03-05, supersedes 08-012-19) was read in full on 2026-10-24; copy in the CUORE repo at docs/vehicles/ZASFAKPN5J7B88115/radio/TSB_08-029-20_MV-002.010.041.pdf [official]. It says the 2.0 software will not work on a radio replaced with a 2.5 unit.

---

## 3. Product selection criteria

All rows are [listing] unless marked. "Not stated" means the page is silent.

| Criterion | Ampire RL4-C3D | NAVconnect APPplay CP-ALF-G1PV | Abt ZZ-2 | IMI-1000 | ENG-Custom piggyback | NAViKS NK-3800-CP | kSmart | thecarplayer | Carlinklife | INTEAR1719 | ATD CIK-27411 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Fitment stated for Stelvio 8.8 non-touch | Yes, 8.8 Connect 3D, Stelvio 949 "since 01/2017 til about 2020" [official] | Yes, 6.5 and 8.8 non-touch | Stelvio "2014-2018" (model launched 2017) | Yes, 949, 2016-2019, 6.5 or 8.8 non-touch | Yes, 6.5 and 8.8 | Stelvio 2018-2022 title; BMW text in kit | Three inconsistent year ranges | 2017-2020, "6.5 or 8" | Stelvio 2014-2019 | Factory 6.8/8.8 non-touch, 2017-2019 | Giulia/Stelvio with Uconnect |
| CarPlay / AA | None | Wireless | Wireless and wired | Wireless | Wired and wireless | Wired and wireless | Wireless | Wireless | Wireless CarPlay, wired AA | Wireless | Not stated |
| Knob support | Not stated | Yes, "controls CarPlay/AA" | "Integrated with factory console knob" | Yes; hold MENU to toggle | Not mentioned | Not stated | Not stated | Not stated | "Factory knobs and steering controls" | Not stated | Not stated |
| Camera inputs and signal | 4 CVBS (rear, front, 2 AV), NTSC only [official] | Front and rear, CVBS NTSC per datasheet summary; AHD not stated | Front and rear, dynamic lines; signal not stated | Page says compatible with front, rear and 360; wiring not stated | Front and rear, NTSC; side via turn signal (forum) | 1 front, 1 rear, guide lines; signal not stated | "Rear/Front/360 option"; signal not stated | "Can be used" with backup or front camera | None mentioned | Front and rear, dynamic lines; signal not stated | Front and rear; count not stated |
| Audio path | Video only. Audio via factory AUX or FM modulator [official] | AUX required | Factory AUX required | Not stated | Via AUX; no radio and CarPlay audio at once | Not stated | Via car AUX | Not stated | Not stated | Not stated | Not stated |
| CAN involvement | Reads CAN through the Quadlock pass-through [official] | Reverse by lamp plus CAN on automatics; head unit not opened | Not stated | Not stated; module sits between 48-pin plug and display cable | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated |
| Standby current | 8 mA standby, 330 mA active [official] | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated | Not stated |
| Warranty | Not stated; one year of updates only if box is sent in at owner's cost [official] | 2 years | 3 years parts and labor | 1 year | 2 years | Not stated | Not stated | 2 years | 1 year | Not stated | Not stated |
| Price, as listed | Not stated | "Contact us for price" | $850 | GBP 465 + GBP 10 UK delivery | EUR 370 incl. tax | $575 (was $875) | $289 | $569 (was $625) | $699.99 | About $1,399 (search summary; page returned 404) | GBP 399.99 |
| Canadian availability | Not stated | Not stated (Netherlands) | Ships from US; Canada not stated | UK; "ships worldwide" | Italy | US | China | Not stated | China | Australia listing; Canada not stated | UK |
| Loses factory function | Parking-guide overlay "not available for all vehicles" [official] | Parking-sensor display not supported; no PiP with OEM PDC overlay | Not stated | Not stated | No radio and CarPlay audio together | Not stated | Not stated | Not stated | Not stated | Works with factory parking display (search summary) | Not stated |

**Notes on the table**

- A Stelvioforum owner says several of these are the same Chinese-made module under different names [forum]. Support may be limited to relabelled firmware [inference].
- NAViKS and APPplay pages contain BMW wording (harness, iDrive). Confirm Alfa fitment in writing [inference].
- The Krando CarPlay interface box on Alibaba was not read. Not compared.
- The Ampire manual warns that vehicle software updates "can cause malfunctions of the interface" [official]. Treat that as a possible issue for any box [inference].

### Questions to ask each vendor in writing

Keep the replies. Ask all vendors the same list.

1. Does the box need a minimum radio firmware? Does it work with MV-002.009.043 as it is now? Does it work with MV-002.010.041? Does it work after the radio is later updated?
2. Does the box transmit on CAN-C, only listen, or only pass messages through? What is the bus load? Is there a CAN-passive mode?
3. Is the harness for North America or Europe? Is it confirmed on a 2018 North American Stelvio with a 2.0 radio (ETM, not 2.5)?
4. Standby current in mA with the car asleep. Active current. Does it sleep when the bus sleeps? Does it wake the car?
5. Does it need the factory AUX input? If the car has none, what is the audio path (Bluetooth, FM modulator, other)?
6. Does the rotary knob work on 2018 cars? Are there reports of the knob failing?
7. Camera inputs: how many, CVBS or AHD, NTSC or PAL, resolution. Can it take a 360 box output? Does the factory rear camera keep working?
8. Reverse trigger on an automatic Stelvio: CAN only, or is a reverse-lamp wire needed? (Ampire says a lamp tap may need a relay [official].)
9. Are the parking-sensor display and the climate/volume overlays kept?
10. Return policy, who pays return shipping, warranty length, what voids it, and how firmware updates are delivered.
11. Is the install manual available before purchase? Is there a Canadian reseller or installer?
12. Will they support a dealer reflash of the radio, and what does the owner do then?

---

## 4. Parts and tools list

Generic. Replace with the chosen box's own list.

| Item | Detail |
|---|---|
| The box and harness | Model, harness variant: not stated until vendor answers |
| Microphone | Many boxes keep the original microphone; if an extra mic is supplied, its type is not stated |
| GPS antenna | Only if the box has its own; not stated |
| Cameras (if chosen) | Count, type and cable length: not stated. Do not mix NTSC and PAL |
| AUX cable or FM modulator | Only if the vendor says so |
| Fused ACC feed | Only if the box needs one. Circuit and fuse size: not stated. Choose a switched, non-safety circuit; not F36, which carries EOBD, the head unit and climate [CUORE record, per mirror install document]. Name the circuit from the owner's manual, not from a third-party diagram |
| Trim tools | Plastic pry set; Torx and socket sizes for the radio and cubby: not stated (physically tight under footwell trim per owner reports [forum]) |
| Multimeter | For rest voltage and in-series standby current |
| Battery charger | Maintainer type, kept on during the work |
| Labels and tape | For marking each connector (section 5) |
| Phone camera | Photograph every connector before disconnecting |
| Zip ties | Only on the new cables. None on factory harnesses [CUORE record] |
| Service information | FCA service information for this VIN was not found [CUORE record]. Radio removal steps: not stated |

---

## 5. Install procedure outline

**This is generic. Replace it with the chosen box's manual.** The manual wins wherever they differ.

1. **Prepare.** All pre-install checks done. Baseline scan saved. Charger on. Date of work is after 2026-10-28 and after the radio update (section 9).
2. **Battery handling.** Follow the box's manual. The Ampire manual says to disconnect the battery and, if needed, put the car in sleep mode before installing [official]. Other manuals: not stated. This conflicts with the EVAP rule of no disconnect until the proof run ends [CUORE record]. After the proof run, decide with a written note. If the manual requires it, disconnect the negative terminal with the charger plan in place. Record the time.
3. **Access the radio and screen.** Remove the trim needed to reach the radio and the screen. The exact sequence for the Stelvio is not stated. One owner described it as physically hard: footwell trim, cubby box, unbolting the head unit [forum]. Stop if a step needs a procedure we do not have.
4. **Photograph and label.** Photograph every connector before disconnecting. Label the radio side and the screen side of each cable.
5. **LVDS (screen cable).** The purple screen cable is unplugged at the head unit and re-routed through the box ("HU IN" and "TO LCD") [official, Ampire]. The Ampire manual warns that swapping the two "may cause dysfunction or even damage" [official]. Mark the box ends and the cable ends. Check twice before power.
6. **Quadlock.** The 48-pin connector comes off the radio and passes through the box's power/CAN cable [official, Ampire; IMI-1000 similar per listing]. If a MOST fibre line is present, move it as the guide says [listing]. Seat each connector fully. A mis-seated pin gave a dark screen on one car [forum].
7. **Dip switches / settings.** Set exactly as the manual says. Ampire dip switches 7 and 8 select the monitor timing by trial [official]. A wrong switch setting was reported to cause blind-spot and tailgate errors [forum]. A cheap box's "CAN type" menu setting broke navigation when changed [forum]. Do not change settings that are not in the manual.
8. **Routing and keep-out.** Keep new cables away from airbag and ADAS harnesses [CUORE record, mirror document]. Route behind airbag zones, never in the deployment path. No zip ties, tape or clips on yellow airbag connectors or their harness. Do not probe, splice or cut factory wires. Do not remove a pillar trim without a known procedure. Secure the box so it cannot rattle or touch warm parts. One user reported overheating under the steering wheel on long summer drives [forum].
9. **Microphone.** Keep the original unless the box says otherwise. If a new mic is used, place it away from airbag covers.
10. **Cameras (if chosen).** Route from the camera to the box with trim-edge clips only. At the liftgate use the existing flexible boot; do not cut it or force connectors; leave a slack loop [CUORE record, mirror document]. Do not tap the tail-lamp harness unless the vendor requires a reverse relay and the owner agrees. A front camera mount and wiring were not researched [CUORE record].
11. **Power.** Use the box's own harness. Add a fused ACC feed only if the manual says so, with a small fuse sized to the stated draw and not upsized.
12. **Do not re-assemble yet.** Go to section 6 first.

---

## 6. Test plan with pass/fail

### 6.1 Before re-assembly (trim off, radio in place)

| # | Test | Pass | Fail action |
|---|---|---|---|
| 1 | Power on, no warning lamps, no chime | Radio and screen start normally | Disconnect box (section 7) |
| 2 | Factory video | Factory menus show, no flicker or black screen | Reseat connectors; if still bad, roll back |
| 3 | CarPlay / AA (if fitted) | Connects, shows full screen, audio plays | Check audio path and settings per manual |
| 4 | Rotary knob | Moves, selects, backs out in factory and phone modes | Note failure; knob is a known weak point [forum] |
| 5 | Steering keys | Volume, track, phone, voice work as before | Note which keys fail |
| 6 | Audio | Radio, Bluetooth and phone audio work; amp not muted | Check AUX or audio path |
| 7 | Reverse camera | Image appears in reverse, guide lines as expected | Check trigger source |
| 8 | Factory functions | Parking sensors, factory rear camera, climate overlay, volume overlay, DNA display, navigation | Any loss is a fail unless the vendor stated it |
| 9 | Front camera (if fitted) | Shows after reverse for the stated time | Note timing |

### 6.2 After re-assembly: CUORE scan against the baseline

- Run a full read-only scan through a CUORE session. Same method as the baseline.
- **Any new U-code on CAN-C = fail.** A radio communication code (such as U1736-86 or U1736-87, seen before on 2026-10-14) is a fail if it is new or its status has changed [CUORE record].
- A code already in the baseline is not caused by the install [inference].
- **Do not clear. Record.** Keep the pre-install history [CUORE record].
- Include B10AA-4A in the comparison: it was stored 2026-10-14 [CUORE record].

### 6.3 Standby current test

- Measure after the car has gone to sleep. The Stelvio's sleep time is not found; record the wait actually used (the forum guideline is 20 to 30 minutes) [CUORE record, forum].
- Meter in series on the added feed (or on the battery lead per a safe method).
- Compare to the box's stated figure. For Ampire: 8 mA standby [official]. For other boxes: not stated, so the vendor answer from section 3 is the reference.
- Forum guideline: about 20 mA asleep is fine; over about 50 mA is a problem [forum].
- **Pass:** at or below the stated figure and under 50 mA. **Fail:** above 50 mA, or above the vendor figure by a clear margin.

### 6.4 Three-day battery rest-voltage check

- Measure rest voltage at the same time each morning for three days, before starting the car, with no charger connected.
- Compare to the pre-install reading from section 2.
- **Pass:** no downward trend and no start-up weakness. **Fail:** a falling trend. Unplug the box and retest (section 7).

### 6.5 Road test

- 30 minutes or more, mixed driving, with a phone connected.
- Check: no warning lamps; radio stays up; CarPlay or AA stays connected; knob and steering keys; reverse camera on a real reversing manoeuvre; parking sensors; navigation position.
- Repeat the scan afterwards if any lamp, message or reboot occurred.

---

## 7. Rollback plan

1. Park the car, ignition off. Put the charger on.
2. Follow the box's battery-handling step in reverse.
3. Remove the box from the chain. Restore the original screen cable and original Quadlock directly to the radio, using the labelled photos.
4. Remove any ACC tap and fuse. Remove new cables from trim. Leave nothing live and unterminated.
5. Re-assemble. Power on. Confirm the factory system works as in the baseline.
6. Run a CUORE read-only scan. Compare to the baseline and to the post-install scan.
7. Do not clear any code. Record findings in the job notes [CUORE record].
8. If a new code remains after rollback, treat it as an open diagnosis, not a closed one. Tell the dealer about the aftermarket work before further dealer work [inference].
9. Contact the vendor about returns using the policy saved from section 3.

---

## 8. Risks and mitigations specific to this car

| Risk | Why it applies here | Mitigation |
|---|---|---|
| **CAN-C disturbance** | Radio is on CAN-C [CUORE record]. A faulty box may make the radio drop off the bus [inference]. Ampire reads CAN through the Quadlock [official]. One ENG-Custom owner reported body-module errors and a black screen [forum]. | Ask vendors about CAN behaviour. Baseline and post-install scans. Any new U-code on CAN-C is a fail. No raw bus contact; CUORE sessions only. |
| **Battery drain / low voltage** | ABS freeze frame 10.6 V; airbag lamp reacted to a bus disturbance on 2026-10-14 [CUORE record]. A wireless dongle may drain the battery [forum]. | Rest voltage before; charger on during work; standby test; 3-day check; ACC-only power if possible. |
| **Airbag and ADAS harness** | Airbag system already reacted to bus disturbance. A DASM C141B-97 "camera blinded" is intermittent [CUORE record]. | Keep-out rules in section 5. No contact with yellow connectors. No tape or ties on factory harness. Stop and ask a professional if a trim needs a procedure. |
| **Dealer warranty and blame** | One forum thread has a dealer blaming add-ons for a drain [forum]. Another dealer said a unit was made for the European version [forum]. | Tell the dealer about the box before further dealer work. Keep photos, scans and vendor emails. Keep original connectors ready for a quick rollback. |
| **Knob reliability** | Some 2018 owners report the knob is unreliable with these boxes [forum]. Sigma said the knob did not work for some 2018 customers (that is a head unit, not a box) [listing]. | Ask the vendor in writing. Check the return policy first. Test the knob before re-assembly. |
| **Radio update interaction** | Radio at MV-002.009.043 [CUORE record]. Ampire warns software updates can cause interface malfunctions [official]. A dealer flash with a box on the radio is undocumented [inference]. | Update radio first. Ask vendors about firmware compatibility. Be ready to unplug the box before any later dealer flash. Note radio version and box firmware. |
| **EVAP proof contamination** | Proof run is open (job 76d3454bce75) and forbids clears and unplanned battery disconnects [CUORE record]. A new fault or reset during the proof would confuse results [inference]. | No install work until the proof closes. No code clearing at all. |
| **Wrong cable swap** | Ampire warns swapping HU IN and TO LCD may cause damage [official]. | Label every connector. Photograph before disconnecting. Check twice before power. |
| **Audio path missing** | Factory AUX is unverified on this car [CUORE record]. Some boxes need it [listing]. | Check AUX in section 2 before buying. Ask the vendor for an alternative. |
| **PDC display lost** | APPplay does not support the parking-sensor display [official]. | Test parking sensors in section 6.1. Ask each vendor. |
| **PROXI / B10AA-4A** | B10AA-4A stored 2026-10-14 [CUORE record]. ENG-Custom says no coding needed [listing]. Others: not stated. | Ask vendors whether any PROXI or coding step is needed. Do not change PROXI. |
| **Overheating** | A long-term user reported heat under the steering wheel in summer [forum]. | Fix the box where air can move around it. Check temperature after a long drive. |

---

## 9. Sequencing

1. **EVAP proof run** completes (job 76d3454bce75). No clears during it [CUORE record].
2. **Dealer visit 2026-10-28** (recall 93C, NHTSA 25V586). Ask the dealer for: the radio software level, the build date, the radio sales code, a written price for any radio or map update, and whether a security gateway is present [CUORE record, options document].
3. **Radio update to MV-002.010.041** if the build date fits TSB 08-029-20 (built on or before 2018-01-11) [official]. MV-002.009.043 is listed in TSB 08-029-20 Step 8 as a level to update [official]. The dealer has told the owner the radio update can be downloaded by anyone as well as through wiTECH [CUORE record, owner-attested 2026-10-24]. Bulletins say run the engine during the update and do not turn off the ignition [official, per RADIO document].
4. **Map update** after the radio update (second USB stick; the Canadian map path and any price: ask the dealer) [official, per RADIO document].
5. **Rescan and set a new baseline** after the radio and map updates, because they change the radio.
6. **Interface box** install, one change at a time, on a day with no other work [inference]. Not the same day as the digital mirror job.

---

## 10. Open questions and sources

### Open questions

1. **Build date.** Not yet read. Decides whether TSB 08-029-20 applies.
2. **Factory AUX jack.** Does this 2018 North American Stelvio have one? Unverified. It decides which boxes can work.
3. **Radio update path.** TSB 08-029-20 covers MV-002.009.043 -> MV-002.010.041 for cars built on or before 2018-01-11 [official]. Open: whether this car's build date fits, and where the owner download is.
4. **Minimum radio firmware.** Which boxes work on MV-002.010.041? No vendor has been asked yet.
5. **CAN behaviour.** Does any box transmit on CAN-C or add bus load? Not stated by any vendor except Ampire (reads CAN).
6. **Standby current.** Stated only for Ampire (8 mA).
7. **Canadian availability and returns.** No Canadian reseller found for the CarPlay boxes. Ask.
8. **Screen size and touch.** 8.8 inch non-touch is assumed; not recorded.
9. **Harman Kardon / MOST fibre.** Not known for this car. It affects the Quadlock move step.
10. **Radio CAN-C address.** Likely 0x6F; unverified.
11. **Does the car have a security gateway?** Not established.
12. **Camera choices.** Which positions, which signal type, and whether 360 is wanted at all.
13. **Who installs.** Owner or professional. One pro install was quoted at "150" [forum].

### Sources (URLs only as found in the research notes)

**Local documents**
- C:\Users\User\mcp-servers\docs\research\INFOTAINMENT_CAMERA_UPGRADE_OPTIONS.md
- C:\Users\User\mcp-servers\docs\research\RADIO_SOFTWARE_AND_UI_OPTIONS.md
- C:\Users\User\mcp-servers\docs\maintenance\DIGITAL_REAR_VIEW_MIRROR_INSTALL.md

**[official]**
- Ampire RL4-C3D manual: https://pdf.ampire.de/caraudiosystems/RL4-C3D/ins_eng_RL4-C3D%20.pdf
- NAVconnect APPplay page and datasheet: https://navinc.nl/appplay-carplay-android-auto-set-alfa-romeo-infotainment-6-5-rgb ; https://www.navinc.nl/pdfviewer/datasheet/index/product_id/2050
- FCA wiTECH SGW knowledge base: https://kb.fcawitech.com/print-903.html
- FCA bulletin on 2020 radios (via search summary): https://static.nhtsa.gov/odi/tsbs/2020/MC-10223593-9999.pdf
- TSB 08-029-20: https://static.nhtsa.gov/odi/tsbs/2020/MC-10174204-9999.pdf (read 2026-10-24; repo copy docs/vehicles/ZASFAKPN5J7B88115/radio/TSB_08-029-20_MV-002.010.041.pdf)

**[listing]**
- IMI-1000: https://integratedautomotive.co.uk/product/alfa-romeo-2016-2019-giulia-stelvio-carplay-and-android-auto-retrofit-kit/ ; guide: https://integratedautomotive.co.uk/user-intstallation-guide-retrofit-carplay-and-android-auto-into-alfa-romeo-giulia-stelvio-2016-2019/
- ENG-Custom: https://shop.eng-custom.com/en/module-android-auto-apple-carplay/61-automotive-eng-custom-alfa-romeo-giulia-stelvio-carplay-android-auto-mirror-link-imperium.html
- NAViKS: https://naviks.com/i-24078110-2018-2022-alfa-romeo-stelvio-apple-carplay-wired-wireless-android-auto-wired-wireless-front-rear-view-camera-interface.html
- Abt: https://www.abt.com/ZZ-2-Wireless-CarPlay-and-Android-Auto-Interface-For-Select-Alfa-Romeo-Giulia-and-Stelvio-Vehicles-ITZALFAA/p/196901.html
- kSmart: https://www.kremersino.com/product-kSmart-auto-alfa-romeo-CarPlay.html
- thecarplayer: https://thecarplayer.com/products/apple-carplay-alfa-romeo-giulia-stelvio-quadrifoglio-2017-2020
- Carlinklife: https://carlinklife.com/products/wireless-apple-carplay-android-auto-for-alfa-romeo-stelvio-giulia-giulietta-2014-2019-carplay-retrofit-module
- ATD: https://audiotechdirect.com/atd-cik-27411-front-reverse-camera-interface-for-alfa-giulia-stelvio-with-uconnect/
- INTEAR1719 (404 when fetched): https://frankiesautoelectrics.com.au/products/car-audio-connect-intear1719-app-connect-interface-module-for-alfa-romeo-giulia-stelvio-2017-2019-factory-6-8-8-8

**[forum]** (search excerpts; open each thread before relying on it)
- https://www.stelvioforum.com/threads/aftermarket-radio-for-stelvio.13305/
- https://www.stelvioforum.com/threads/carplay-android-auto-piggyback.12873/
- https://www.stelvioforum.com/threads/carplay-on-stelvio-2017.17088/
- https://www.stelvioforum.com/threads/tracing-parasitic-loss-battery-drain-thread.20544/
- https://www.giuliaforums.com/threads/carplay-boxes-eng-limcet-aliexpress-factory-menu-questions.66161/
- https://www.giuliaforums.com/threads/great-experience-with-install-of-aftermarket-carplay.59850/
- https://www.alfaowner.com/threads/apple-carplay-android-auto-add-on-box.1180627/
- https://www.alfaowner.com/threads/best-wireless-android-auto.1214538/

Labels follow the source notes. Anything marked [inference] is reasoning, not a source statement. Nothing here was measured on the car.
