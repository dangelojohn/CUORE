# Radio software and UI options: 2018 Stelvio Alfa Connect radio (ETM)

Reference car: VIN ZASFAKPN5J7B88115. Web research written 2026-10-23. Nothing was read from or written to the car, adapter or any server.

**Summary**
1. Latest known radio software for the 2018 Stelvio 2.5 radio is MV 090.000.061, delivered by USB stick from Settings > Software Update on the radio (TSB 08-065-20, 24 Jun 2020, replaces 08-081-19 and its MV 085.000.046); it is not a wiTECH flash.
2. The update files sit in the dealer-only DealerCONNECT portal. No official owner download was found; unofficial copies on forums are unverified.
3. CarPlay/Android Auto is enabled through PROXI byte edits plus a dealer wiTECH offline-activation step (forum sources; a wrong order can lock the radio).
4. No hidden or engineering menu, boot-logo change, or firmware hacking is documented; update files are signed, and the 2020+ touch UI cannot be had by software.
5. The bulletins' post-flash step "Clear all DTCs" (and wiTECH's offer to clear after any flash) conflicts with the EVAP proof rule: log DTCs, freeze frame and readiness first and clear nothing until the proof run.
6. Open: this VIN's build date, radio sales code and current MV number; no text of TSB 08-029-20 was found (only a Stelvioforum thread title calls it a Stelvio 2.0-radio update to MV 002.010.041); North American map download page and price were not confirmed.

---

## Full note: 2018 Alfa Romeo Stelvio 8.8" / 6.5" Alfa Connect radio (ETM): software options

Research date: 2026-10-23. Web research only. Nothing on the car, adapter or repos was touched.

## Source labels and access limits

- [OFFICIAL-DOC] = FCA US dealer service bulletin (TSB), public NHTSA-hosted copy. I downloaded these and read the full text.
- [VENDOR] = manufacturer or seller statement, or a product listing.
- [FORUM] = owner or enthusiast post.
- [SEARCH-SUMMARY] = page not opened by me. Content comes from the web-search tool's summary of it. The XenForo forums (giuliaforums, alfaowner, stelvioforum) redirect bots to a paywall (tollbit) and ClubAlfa, MHH, go-parts and the Mopar map site returned 403, so I could not read them directly. Treat those items as leads to verify.
- Not found is stated as not found. Nothing is inferred beyond that.

The radio is called the ETM (Entertainment Telematics Module) in the FCA bulletins.

Maker: Magneti Marelli says it developed the multimedia system and Connect 3D Nav (8.8" TFT) for the Giulia (Marelli 2015 Frankfurt press release, [VENDOR]). Press coverage and TomTom's page say the same for Giulia and Stelvio. TomTom supplies the navigation maps. No FCA bulletin names the manufacturer, so "Marelli" is a supplier claim, not confirmed from a service document. [FORUM, SEARCH-SUMMARY]: board is i.MX6QP, Linux/GENIVI based.

---

## 1. Software release history and delivery

### Key finding: delivery is USB stick, not a wiTECH flash

For the 2017-2019 Giulia/Stelvio 2.0/2.5 radios, the ETM update is a USB-stick update started from the radio's own menu:
SETTINGS > SYSTEM > SOFTWARE UPDATE. wiTECH is used for diagnosis, for the other modules, and for clearing DTCs afterwards. [OFFICIAL-DOC 08-065-20, 08-081-19]

The update files are downloaded by the dealer from DealerCONNECT > Service > UCONNECT Command Center > Uconnect > Dealer software downloads. That is a dealer-only portal. [OFFICIAL-DOC]

### Version path for the Stelvio (North America)

ETM version is shown at SETTINGS > SYSTEM > SOFTWARE UPDATE > CURRENT SOFTWARE.

| Version | Bulletin | Date | Applies to | What the bulletin says |
|---|---|---|---|---|
| MV-072.001.002 to MV-080.000.047 | (start points, build-dependent) | - | 2.5 radios in Stelvio from build 30 Oct 2017 | Needs ETM update AND map update first, then the ETM. |
| MV 081.000.004 | 08-081-19 | 2 Aug 2019 | same | Update ETM only. |
| MV 085.000.046 | 08-081-19 | 2 Aug 2019 | 2018-2019 GA/GU, built to 6 Mar 2019 (Stelvio from 30 Oct 2017) | Fixes radio rebooting while driving, radio stays on if you leave the car during a phone call, radio comes on at old volume after remote start. Phones must be re-paired. |
| **MV 090.000.061** | **08-065-20** (supersedes 08-081-19) | 24 Jun 2020 | 2017-2019 GA, 2018-2019 GU, built to 12 Jul 2019 (Stelvio from 30 Oct 2017), radio codes RAN, RAP, RAG, RSD | Same three symptoms as above. "ETM has the latest available software" at 090.000.061. Revision added 2017 MY to GA, a new software level, revised build dates and labor ops. |

Radio sales codes (from 08-065-20):
- RAN = 8.8" with Nav
- RAP = 8.8" without Nav
- RSD = with/without SiriusXM
- RAG = standard 6.5"

Neither bulletin says what 085 or 090 changed beyond the three symptoms. No screen-layout or CarPlay/Android Auto change is claimed in either bulletin.

**Latest known version for a 2018 Stelvio with the second-generation radio: MV 090.000.061.** Source: 08-065-20 [OFFICIAL-DOC]. I found no later official bulletin for these units. A forum post quoting Alfa Romeo Cares said 090 is the most current for this hardware [FORUM, SEARCH-SUMMARY]. Versions numbered above 090 (130.000.002, later 131/132, and a claimed 145) appear only for the 3rd-generation MY2020+ hardware [FORUM, SEARCH-SUMMARY].

### Other bulletins checked (and why they do not apply)

- **08-064-20** (20 Jun 2020), RAN/RAP, target MV-119.001.009. Covers 2020 GA/GU only, built to 6 Mar 2020. Not the 2018 car. Symptoms: reboot, wrong maintenance mileage. Same USB method, same 4GB NTFS stick. [OFFICIAL-DOC]
- **08-025-20** (3 Mar 2020, supersedes 08-013-19), target MV-002.010.041. Covers 2017-2018 **Giulia only** (GA), built to 5 Dec 2017, first-generation 2.0 radios. It states "if the radio has been replaced with an updated 2.5 radio, this software will not work". It lists many fixes and UI changes (see the next heading). [OFFICIAL-DOC]
- **08-041-17 Rev B** (18 Jul 2017). 2017 Giulia only, built to 20 Apr 2017. Same fix list as 08-025-20. Uses wiTECH 2 "restore configuration". [OFFICIAL-DOC]
- **08-029-20: bulletin text not found.** Searches on the number returned no document. A Stelvioforum thread title quoted in `INFOTAINMENT_CAMERA_UPGRADE_OPTIONS.md` (not opened) describes it as "Stelvio Infotainment Update 2.0 Radio -> 002.010.041", which would be the first-generation radio, not the 2.5 radio of a Stelvio built from 2017-10-30. The dealer can look it up by VIN. The nearest matches are 08-025-20, 08-064-20 and 08-065-20.
- **08-082-19, 08-016-19, 08-112-19** and similar numbers are Jeep/Ram Uconnect 4C bulletins, not Alfa. Their "Dealer Mode" screen and 28.x/22.x versions do not apply to this radio.

### What the older (2.0 radio) releases added

From 08-041-17 and 08-025-20, for first-generation radios only:
- Navigation recovery after signal loss
- Android Bluetooth fixes
- Black-screen and logo-freeze fixes
- Seven-preset bar
- Frequency shown without kHz/MHz
- Three alternative routes
- Simplified POI categories
- Map zoom without changing menus
- Larger dial numbers
- "Apps" icon changed to a car icon
- Maps update

Stelvios built from 30 Oct 2017 already have the 2.5 radio, so the 2.0 releases do not apply.

A radio showing MV-002.009.059 or lower is an "early 2.0 radio". 08-081-19 says that software will not download to it and points to other bulletins.

### Hardware generations [FORUM, SEARCH-SUMMARY]

- Version numbers starting 001/002 = first-generation hardware.
- 051 and above = second generation (2.5).
- Third generation = MY2020+ touch unit.
- Different processors; firmware is not interchangeable.
- A German forum post says CarPlay/Android Auto needs at least 056.

### CarPlay and Android Auto

- Official bulletins do not describe CarPlay or Android Auto being added by an ETM update.
- Forum accounts [FORUM, SEARCH-SUMMARY]: early MY2018 cars were "pre-wired" with the feature switched off, and cars built from about 11 Dec 2017 have the predisposition.
- Enabling needs three things:
  - a compatible USB hub part
  - PROXI byte changes
  - a dealer wiTECH "offline activation" in the ETM
- Details are in section 3.
- Stelvios built about Dec 2017 or later may already have it working. Check by plugging in a phone.

### Other modules that must follow the ETM update (cars built on or before 12 Apr 2018)

08-065-20 warns that after the ETM goes to 085/090, these modules MUST also be updated on **GU built 30 Oct 2017 to 12 Apr 2018**: BCM, amplifier, ABS, IPC, park assist module, left/right blind-spot sensors. "Failure to update all of these modules may result in vehicle malfunctions." These are wiTECH flashes under their own bulletins.

**Action: read the build date (MDH) from the VIN/door label.** This VIN (ZASFAKPN5J7B88115) is a 2018 Stelvio, but I did not look up its build date.

### Is any USB update file legitimately available to an owner today?

- **Official owner download: none found.** The bulletins send the dealer to DealerCONNECT. I found no owner-facing Alfa Romeo or Mopar download for ETM firmware.
- A ClubAlfa post (2020) says dealers only do the updates Alfa flags as essential, and that Alfa no longer makes some files available [FORUM, SEARCH-SUMMARY]. This is opinion, not a policy document.
- Unofficial copies of the dealer files circulate on forums and file hosts. Versions mentioned: 002.009.055, 002.010.041, 056.000.007, 072, 085.000.046, 090.000.061 [FORUM, SEARCH-SUMMARY]. I did not download any. Their integrity is unverified.
- **VIN lock for the update file:** not stated in any bulletin. Forums describe files being shared freely and used on other cars, which suggests no VIN lock on the file [inference from FORUM, not confirmed]. A forum commenter says the ETM verifies signatures on each segment before flashing [FORUM, SEARCH-SUMMARY]. A German thread says a **replacement ETM** is locked to the chassis number (and asks for a security code on another car) [FORUM]. That is the head unit hardware, not the update file.
- **Sales code:** the bulletins scope by radio sales code (RAN/RAP/RAG/RSD) and build dates. I found no evidence the radio checks a sales code at install time.
- **Procedure requirements** (from the bulletins [OFFICIAL-DOC]):
  - USB stick formatted **NTFS**. 08-065-20 says at least 16 GB for ETM+map; 08-064-20 says 4 GB for the ETM file.
  - Stick must be blank. Copy the **contents** of the downloaded folder, not the folder itself.
  - One stick per update. Nothing else in either USB port.
  - Engine running for the whole update. Do not remove the stick.
  - Radio reboots afterwards. Presets and settings may reset. Phones must be re-paired.
  - Map update (RAN only) is a second stick, plugged in the port under the centre-console armrest, only after the ETM update.
- The labor ops (about 0.2-0.3 h inspect, 0.8-1.8 h update/map, per 08-025-20 and 08-065-20) show dealers treat it as a short job. Warranty reimbursement under the bulletin applies only while within warranty terms. Cost for a 2018 car out of warranty in Canada: not found. A Seattle owner was quoted $215 for 1 to 1.5 hours of infotainment and map update work [FORUM, SEARCH-SUMMARY].

---

## 2. Can the 2020+ touch UI (or newer) run on the 2018 unit?

**No. Confirmed by sources: not by software.**

- The 2020 refresh (3rd-generation ETM) brought a touchscreen-capable 8.8" and a new UI layout [Fleet News / Car Magazine coverage, SEARCH-SUMMARY]. The 2017-2019 units are rotary-only, with different hardware and firmware. Forum accounts say the generations differ in processor architecture [FORUM].
- A parts seller says touch and non-touch units are not compatible, with different wiring, modules and software architecture [VENDOR go-parts, SEARCH-SUMMARY].
- Correction to the question: the **10.25" screen is the Tonale/Dodge Hornet Uconnect 5** (bulletin 08-002-25 lists 10.25" Uconnect 5 for the Tonale). The 2023 Giulia/Stelvio facelift kept the 8.8" screen and added a 12.3" digital cluster [Parkers / Autocar, SEARCH-SUMMARY]. There is no 10.25" Giulia/Stelvio unit.
- Signing: a forum member says update segments are signed and verified before flashing, so a modified firmware cannot be loaded [FORUM, SEARCH-SUMMARY].

### Hardware retrofit in 3 lines [FORUM / LISTING, SEARCH-SUMMARY]

1. **Parts:** 2020+ touch ETM (and the screen with its matching motherboard), a knob/controller with the touch function and its USB cable, the AA/CP-capable USB hub; posters also mention the IPC, HVAC module and other modules needing updated software.
2. **Programming:** dealer-grade wiTECH for the unit's VIN activation or "unlock", a PROXI alignment for the whole car, a few hand-edited PROXI bytes. A replacement ETM is chassis-locked. Never run "restore vehicle configuration" after custom PROXI changes (resets to factory).
3. **Price (rough, user-reported):**
   - Used 2020 8.8" screen only, old motherboard kept, no touch: about EUR 400 vs about EUR 1,350 new (Giulia owner).
   - Used ETM swap: unlock service fee about EUR 400 on top of the unit, total about EUR 700-900 (seller estimate).
   - Used 2020 screens: US$300-$323 on eBay.
   - Other posters call the full touch retrofit "too expensive" and "not worth it". ENG-Custom is said to have fitted a Gen 3 head unit to a 2017 and a 2019 Giulia. I found no dealer quote.

A touch retrofit is not a software update; I would treat it as an unproven, multi-module project.

---

## 3. Customisation of the existing unit

### Known PROXI / configuration items that affect the radio

| Item | What it does | Source and status |
|---|---|---|
| CarPlay / Android Auto enable | PROXI option change, then dealer wiTECH "Android Auto/CarPlay offline activation" in the ETM Miscellaneous tab; car must then fully sleep so the ETM reboots | [FORUM] giuliaforums (AA/CP update thread), stelvioforum, alfa-romeo-portal. Describes a dealer-first path. Posters disagree on byte count (3, 4 or 5). Bytes named: 115, 157, 161, 163, 174 (e.g. byte 115 = 15 enables a USB type). Option codes mentioned: 0KA ("USB host flip", CarPlay predisposition), 8EW (full CarPlay). **The activation step must come last. Doing it before the PROXI change can lock the radio permanently.** |
| USB hub swap | Needs an AA/CP-capable hub part (one poster names 156138299) | [FORUM, alfaholicy] |
| Minimum ETM version | At least 056 (090 preferred on second generation) | [FORUM, alfa-romeo-portal, giuliaforums] |
| Proxi length | Some proxies need extra bytes; AlfaOBD "Proxy tools" or MES padding to about 193 | [FORUM, SEARCH-SUMMARY] |
| AlfaOBD vehicle configuration | An Italian poster says the Giulia body-computer configuration lists many options, including disabling Start&Stop and enabling Android Auto | [FORUM, SEARCH-SUMMARY, early AlfaOBD version limited to the body computer] |
| MES | MES is used to edit PROXI. One German poster says "MES can do nothing in that direction", another says it can edit proxi so the wiTECH option appears | [FORUM], disputed |

**Not found:**
- Hidden / engineering / dealer menu for this radio. The "Dealer Mode" in Jeep bulletin 08-082-19 is a different Uconnect 4C radio.
- Boot-logo change.
- Language change by coding. Language and "Reset Setting" are normal radio settings (SETTINGS > SYSTEM).
- Any list of radio PROXI bytes for the **Stelvio** specifically. One poster says nobody has figured out the Stelvio proxi keys (older post).

### Warnings

- **SGW.** The 2018+ models have a Security Gateway. AlfaOBD's own site says it has no software workaround and needs a hardware SGW bypass supporting the second high-speed CAN on OBD pins 12/13 [alfaobd.com, via SEARCH-SUMMARY]. Giulia/Stelvio are named. A GiuliaForums thread title warns about permanently bypassing it ("Think twice...") [FORUM, SEARCH-SUMMARY].
- **PROXI alignment** is the dealer procedure that pushes the BCM's configuration to all modules. A mismatch can cause: blank or dead screen, flashing odometer, ABS "proxy alignment" errors after reverting edits [FORUM, SEARCH-SUMMARY].
- **B10AA-4A** (BCM "Check Configuration Failed / incorrect component installed") is the code type to expect from bad configuration. The STAR/TSB handling I found is for another vehicle (2014 Fiat 500L, NHTSA MC-10139661). The Giulia/Stelvio detail came via a search summary mentioning a STAR entry, which I did not open. The usual dealer approach in those bulletins is: wiTECH restore vehicle configuration, then PROXI alignment, ignition cycle so codes go from Active to Stored, then clear. **Restore vehicle configuration resets PROXI to factory, which undoes custom edits.**
- Used-ETM and failed-activation cases are reported as permanently locked ("lock radio forever in AA/ACP activation") [FORUM, SEARCH-SUMMARY].
- Nothing here has a rollback guarantee. Back up the BCM configuration first.

### Community firmware or hacking of the unit

**No mature community firmware exists. I found none.** What the sources describe [FORUM, SEARCH-SUMMARY, GiuliaForums "Hacking Giulia"]:
- i.MX6QP-based, GENIVI Linux.
- Serial/JTAG pads found, but the JTAG fuse is blown.
- A USB-token mechanism that would open a firewall and Ethernet driver exists, but the token is asymmetrically signed and the key is held by FCA.
- Update files are signed.
- No Wi-Fi in the ETM (Bluetooth only).
- "Rooting" is mentioned as an aspiration by posters. There are no published results.
- A GiuliaForums thread on an "Android Auto widescreen UI update" concluded it is far from simple because of signing.

### Aftermarket option class (stated neutrally; not a recommendation)

Plug-in CarPlay/Android Auto interfaces exist for the 6.5"/8.8" rotary units, e.g. Integrated Automotive IMI-1000 [VENDOR page, opened], ENG-Custom, Kplay, wireless-capable modules [VENDOR listings]. The IMI-1000 install page describes unplugging the head unit's 48-pin connector and display cable and switching with a MENU long-press. Prices in sources run about US$600+ for hardware plus US$400-800 for install [SEARCH-SUMMARY, generic estimate]. These leave the factory ETM firmware untouched.

---

## 4. Map updates

Superseding note: the official NA v1176 package route (portal, files, in-car steps, dealer DTC-clearing conflict) is now researched in [`NAV_MAP_UPDATE_2018_STELVIO.md`](NAV_MAP_UPDATE_2018_STELVIO.md); the portal was not loadable in this note, so prefer that file.

- **Provider:** TomTom (TomTom's Connect 3D Nav page, [VENDOR]), delivered by USB.
- **Official path in the bulletins:** map update is the second USB stick, RAN radios only, after the ETM update. Disable GPS clock sync and set time/date by hand first, run with engine on, re-enable GPS sync afterwards. If the ETM was already at 081.000.004 the map update is not needed [OFFICIAL-DOC 08-065-20].
- **Owner route (forum):** [FORUM, SEARCH-SUMMARY]
  - Download from the Stellantis/FCA "navshop" downloads page (URLs quoted: fca.navshop.com/downloads, stellantis.navshop.com/downloads). **I could not load either; both returned 404 for me, so I could not confirm the page, the region or the pricing.**
  - Choose "3D CONNECT NAV" for 2018 cars and "3D CONNECT NAV MY20" for 2020+.
  - Files named like MAP10631.bin plus a license/.meta file; one poster used a USA/Canada/Mexico .meta.dct. Put them in the stick's root, nothing else on it.
  - Stick: NTFS, 16 GB or more (one 2023 map is 21 GB).
  - Install takes about 40 minutes with the engine running and Start/Stop off. Navigation is unavailable during the update.
  - One thread reported the US link serving EU maps at one time. The file MAP50167.bin was named as the EU one. A later reply says it was fixed. Check the region before installing.
- **Cost:**
  - Europe: Mopar Map Care portal (maps.mopar.eu, [VENDOR] via TomTom page). Free for 3 years after registration, then about EUR 150 for 3 years [FORUM].
  - UK dealer: about GBP 125 for the update [FORUM].
  - A Canadian 2018 owner had a dealer install a USA/Canada/Mexico map for free [FORUM, SEARCH-SUMMARY].
  - US/Canada current official price: **not found.**
- Forum posts disagree on whether North American map downloads are free. Ask the dealer for a written price against the VIN.

---

## 5. Risks specific to this car, and the EVAP proof rule

1. **Bus.** I found no source stating which CAN network the ETM is on (CAN-IHS vs CAN-C). Treat that as unverified. What is sourced: the SGW sits between OBD and the module networks on 2018+ cars, and third-party tools need a hardware bypass with the second high-speed CAN on pins 12/13 [alfaobd.com via SEARCH-SUMMARY].
2. **Flash tool.** The ETM update itself needs no wiTECH. The bulletin still uses wiTECH for: pre-checks, the co-required module flashes on cars built to 12 Apr 2018, and clearing DTCs afterwards. PROXI/CarPlay activation does need wiTECH (dealer).
3. **Battery and power.** No bulletin step disconnects the battery. 08-065-20, 08-081-19, 08-064-20 and 08-025-20 all say: start the engine and leave it running in a ventilated place for the update; do not remove the stick; do not turn off the ignition. How long the ETM-only run takes is not stated. The map install is about 40 minutes per forum posts.
4. **DTC clearing.** Step 15 of 08-065-20 and 08-081-19 (it sits at the end of the MAP UPDATES block) says: "Clear all DTCs that may have been set in any module due to reprogramming. The wiTECH application will automatically present all DTCs after the flash and allow them to be cleared." Routing detail from the opened text: after the ETM update, step 14 sends cars that were on MV-072.001.002 to MV-080.000.047 into the map update (which ends in step 15), and every other starting version straight to step 16 (module checks), skipping step 15. Either way, wiTECH offers to clear all DTCs after a flash. A "clear all" would erase stored EVAP codes and freeze frame and reset the readiness monitors. **For the proof rule:** log the ECM's DTCs, freeze frame, and readiness state **before** any radio, map or module flash; clear only the codes the flash itself set; or finish the radio work before the EVAP proof drive cycle starts. Re-read after the flash to prove nothing else was lost or added.
5. **Other resets.** 08-025-20 (Giulia only) has a power-down sequence after the update: car off, lock, wait 20 minutes with the key fob far away, and an optional "Reset Setting" and wiTECH "restore configuration". The Stelvio bulletins 08-065-20/08-081-19 do not include it. "Restore vehicle configuration" resets PROXI and would undo any custom edits.
6. **After the update:** presets and phone pairings are lost, and so can be user settings. Photograph settings first.
7. **Other-module dependency.** The 12 Apr 2018 cut-off in section 1 matters. If the car is on the old side of it and the radio is moved to 085/090 without the matching BCM, amp, ABS, IPC, PAM and blind-spot software, 08-065-20 warns of "vehicle malfunctions". That includes ABS, so confirm module versions first.
8. **PCM.** Separate Alfa campaign W05 (NHTSA MC-10175111, March 2020) covers PCM reprogramming for 2.0L GMET-4 (EC2) cars, and says Giulia 2017-2018 include a PROXI alignment. Not a radio item, but it is another reflash event that also interacts with the EVAP/DTC history. Do not count it as radio-related.
9. **Never** do an ETM update on a weak battery or with the engine off. The bulletins require the engine running.

---

## Open items to verify (not found)

- Build date (MDH) of this VIN and the car's radio sales code (RAN/RAP/RSD/RAG) and its current ETM version. These decide which row in the section 1 table applies.
- Whether bulletin 08-029-20 (2.0-radio update per a forum thread title) applies to this car (dealer lookup by VIN).
- Official North American map download page and price.
- Which bus the ETM sits on (CAN-IHS claim not sourced).
- The XenForo forum threads I could only see through search summaries (alfaowner "How to: Infotainment updates", giuliaforums AA/CP thread, "Hacking Giulia", "How to fit 8.8 touchscreen display to pre 2020 year models", stelvioforum map threads).

---

## Sources

**Official documents (FCA bulletins hosted by NHTSA, read in full)**
- 08-065-20, 24 Jun 2020: https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf
- 08-081-19, 2 Aug 2019: https://static.nhtsa.gov/odi/tsbs/2019/MC-10166576-9999.pdf
- 08-064-20, 20 Jun 2020: https://static.nhtsa.gov/odi/tsbs/2020/MC-10223593-9999.pdf
- 08-025-20, 3 Mar 2020: https://static.nhtsa.gov/odi/tsbs/2020/MC-10175117-9999.pdf
- 08-041-17 Rev B, 18 Jul 2017: https://static.nhtsa.gov/odi/tsbs/2017/MC-10223731-9999.pdf
- W05 PCM campaign, Mar 2020: https://static.nhtsa.gov/odi/tsbs/2020/MC-10175111-9999.pdf
- 08-082-19 (Jeep, not applicable): https://static.nhtsa.gov/odi/tsbs/2019/MC-10166583-9999.pdf
- 08-002-25 (Tonale 10.25" Uconnect 5): https://static.nhtsa.gov/odi/tsbs/2025/MC-11012822-0001.pdf
- 08-142-22 (TBM FOTA, telematics box only): https://static.nhtsa.gov/odi/tsbs/2022/MC-10230338-9999.pdf

**Vendor / maker**
- Marelli, 2015 Frankfurt release (Giulia QV infotainment): https://marelli.com/content/dam/marelli/news/documents/archive-press-room/2015/2015%20Frankfurt%20Motor%20Show%20Magneti%20Marelli%20for%20the%20Alfa%20Romeo%20Giulia%20Quadrifoglio.pdf
- TomTom Connect 3D Nav: https://www.tomtom.com/en_us/in-dash-navigation/connect-3d-nav
- AlfaOBD (SGW/bypass notes): https://www.alfaobd.com
- Integrated Automotive IMI-1000 install guide (opened): https://integratedautomotive.co.uk/user-intstallation-guide-retrofit-carplay-and-android-auto-into-alfa-romeo-giulia-stelvio-2016-2019/
- Mopar Map Care (EU; not opened, 403): https://maps.mopar.eu/en/home
- go-parts garage articles (seller content, not opened): https://www.go-parts.com/garage/audio-system-alfa-romeo-giulia-alfa-romeo-stelvio-2017-2026

**Forum (opened by me)**
- alfa-romeo-portal.com, ETM update thread (2019): https://www.alfa-romeo-portal.com/forum/thread/3597-giulia-stelvio-etm-infotainment-entertainment-einheit-update/
- alfa-romeo-portal.com, CarPlay/AA retrofit thread: https://www.alfa-romeo-portal.com/forum/thread/4984-apple-car-play-android-auto-nachr%C3%BCsten-giulia-und-stelvio/
- alfaholicy, update 2017 ETM to 2018 AA/CP ETM: https://www.forum.alfaholicy.org/giulia_stelvio/173295-_langtitle_update_2017_giulia_etm_2018_aa_cp_etm_langtitle_.html?language=en

**Forum / other (search summary only, pages not opened)**
- alfaowner, How to: Infotainment updates: https://www.alfaowner.com/threads/how-to-infotainment-updates.1185573/
- giuliaforums, Updating 2017 models to Android Auto/Apple CarPlay: https://www.giuliaforums.com/threads/updating-2017-models-to-android-auto-apple-carplay.46071/
- giuliaforums, New ETM update to 090.000.061: https://www.giuliaforums.com/threads/new-etm-update-to-090-000-061.52048/
- giuliaforums, 3rd Gen ETM Update 130.000.002: https://www.giuliaforums.com/threads/3rd-gen-etm-update-available-130-000-002.55179/
- giuliaforums, Hacking Giulia: https://www.giuliaforums.com/threads/hacking-giulia-some-more-hardcore-reverse-engineering.56834/
- giuliaforums, 2022 headunit in 2018 car: https://www.giuliaforums.com/threads/2022-headunit-in-2018-car.56796/
- giuliaforums, How to fit 8.8 touchscreen display to pre-2020 models: https://www.giuliaforums.com/threads/how-to-fit-8-8-touchscreen-display-to-pre-2020-year-models.64528/
- stelvioforum, North America Navigation Update Available: https://www.stelvioforum.com/threads/north-america-navigation-update-available.13132/
- stelvioforum, Map update. USB?: https://www.stelvioforum.com/threads/map-update-usb.17581/
- ClubAlfa, Giulia/Stelvio useful links: https://forum.clubalfa.it/goto/post?id=1768635
- ClubAlfa, new software for old infotainment: https://forum.clubalfa.it/goto/post?id=1724867
- ClubAlfa, MultiEcuScan what can be activated: https://forum.clubalfa.it/threads/multiecuscan-cosa-si-puo-fare-attivare.123843/
- MHH Auto, custom proxy mod for CarPlay Stelvio: https://mhhauto.com/Thread-Custom-proxy-mod-for-Carplay-Alfa-Stelvio
- Multiecuscan forum, 2018 Giulia proxi alignment issue: https://multiecuscan.net/forum/viewtopic.php?p=23217
- Android Police, Android Auto on Alfa (Nov 2017): https://www.androidpolice.com/2017/11/16/android-auto-now-available-alfa-romeo-models-well-one-fiat-two-head-unit-manufacturers/
- Fleet News, 2020 refresh: https://www.fleetnews.co.uk/news/manufacturer-news/2019/11/20/alfa-romeo-giulia-and-stelvio-get-updated-interior-and-infotainment
