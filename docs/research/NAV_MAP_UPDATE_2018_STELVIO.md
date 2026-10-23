# Nav map update, 2018 Stelvio (summary)

1. Official portal: https://stellantis.navshop.com (Stelvio > 3D CONNECT NAV 8.8" > North America v1176, 10.1 GB; files MAP21331.bin + USA_Canada_and_Mexico-105003.meta.dct on download-cde.tomtom.com). No price is shown in the portal data; no VIN tie found.
2. Prerequisite radio software: MV 081.000.004 or later (check Settings > System > Software Update > Current Software). The TSB wording around 081.000.004 is ambiguous; confirm on the unit.
3. In-car steps per TSB 08-065-20: GPS clock sync off, engine running, MENU > Settings > System > Software Update, stick in the port below the armrest, OK, remove stick, sync back on.
4. USB stick 16 GB or larger, NTFS per the research (TSB and stelvioforum). Source conflict: one owner reported success with exFAT on 32 GB, and Mac formats were reported to fail; FAT32 is not named by any source. [INFERENCE] FAT32 cannot hold the single 10.1 GB MAP21331.bin file (4 GB per-file limit), so use NTFS.
5. The dealer map branch of the TSB includes "Clear all DTCs" (step 15). That conflicts with the EVAP proof rule (no clearing while the proof is pending). [INFERENCE, not sourced] An owner USB map update does not clear codes: the map files are NDS data, not module firmware, and no wiTECH flash is involved. Verify by reading the codes before and after.
6. Download 2026-10-23: fetched by the project into Downloads\StelvioMap_NA_v1176 (size 10,868,879,360 bytes; SHA-256 c30186319a45e9152530ae8ea6b2302c8dc91c51cfeee0802a3ac69be3cefa85 (verified 2026-10-23 01:58, size matches server); licence file SHA-256 bf8fc26fad8281bb90a4c3a62c65adb40e3123b0696b0d11c00903cebe9539c7). Not verified by this note.

Planned owner job: "Nav map update to NA v1176 by USB (owner)" (see the job store; no code clearing, record before/after map version).

---

# Map update options: 2018 Alfa Romeo Stelvio 2.0T, Canada, Alfa Connect 8.8 (3D Connect NAV, TomTom maps)

Researched 2026-10-23, web only. Labels: [OFFICIAL] = Stellantis/FCA/TomTom/NHTSA-hosted FCA document; [PORTAL-DATA] = read from the official portal's own public JavaScript, not from a documentation page; [FORUM]; [LISTING]. Anything not found is marked NOT FOUND.

## 1. Official DIY route (North America)

**Portal.** Stellantis NavShop, https://stellantis.navshop.com/#/downloads [PORTAL-DATA + FORUM]. Owner posts on stelvioforum.com / giuliaforums.com name this URL (older posts name fca.navshop.com/downloads). The Europe portal (maps.mopar.eu, "Mopar Map Care") is separate and does not list the US/Canada. The HERE-operated chryslergroup.navigation.com portal (reachable in CAD) lists only Chrysler, Dodge, Fiat, Jeep and Ram. It has no Alfa Romeo entry and its only product is Uconnect 8.4A activation, so it is NOT the portal for this car.

**What the portal's own data says (fetched https://stellantis.navshop.com/chunk-GNEX7KHT.js).** The vehicle tree has Alfa Romeo > Stelvio with three navigation systems: "CONNECT NAV" (6.5"), "3D CONNECT NAV" (8.8") and "3D CONNECT NAV MY20". Mapping:
- 3D CONNECT NAV (8.8", this car) maps to package "NORTH AMERICA" **v1176, 10.1 GB**.
  - Map file: https://download-cde.tomtom.com/cs/giorgio/cdp/g2/high/ttc/1176/MAP21331.bin (HTTP HEAD: 10,868,879,360 bytes, Last-Modified 2026-07-30).
  - License file: https://download-cde.tomtom.com/cs/giorgio/cdp/g2/high/ttc/1176/USA_Canada_and_Mexico-105003.meta.dct (132 bytes, Last-Modified 2026-07-30).
- CONNECT NAV (6.5") maps to NORTH AMERICA v1176, 9.0 GB (mid/MAP21411.bin) with its own .dct. Do not mix with the 8.8 files.
- 3D CONNECT NAV MY20 maps to NORTH AMERICA v2026.06, 17.1 GB (cs/my20/maps/nds/2026.06/MAP50471.bin). That is the newer-generation unit, not a 2018 car.
- Current NA release for the 2018 8.8 unit: **v1176** (file MAP21331). It is the portal's own number; I found no release-date label beyond the file timestamp.

**Price.** The portal data has no price field and no cart or checkout strings, and the two files are served by direct HTTPS links on the TomTom CDN (HEAD returned 200 without login). The owner states the maps are free. I did not find an official page that states the price in CAD or USD, so "free" is supported by the owner's statement and the absence of a price in the portal data, not by a written offer. The portal page itself is a JavaScript app and I could not render it to see on-screen text.
- Forum claim, unverified: updates are free for 3 years from registration in Europe (clubalfa.it). No NA statement found.
- For Uconnect 5 and newer, driveuconnect.com says OTA map updates need a trial or paid Navigation Package. That is not this unit. [OFFICIAL] https://www.driveuconnect.com/support/software-update.html

**Delivery / ties.** Download to your own USB (no mailed stick found). The license .dct is a generic file named USA_Canada_and_Mexico-105003, with no VIN in its name. One forum post (via search snippet) says the license comes from the portal and maps will not install without the correct license file. VIN or radio-serial tie: NOT FOUND (the portal data shows no VIN field; I did not use the live portal UI).

**Download attempted?** Not completed. I tried to fetch the two files into scratchpad\map_download\ (empty folder created) but the shell permission layer refused the download commands, so nothing was downloaded and no SHA-256 exists. The owner or coordinator can approve it or fetch the two URLs above.

**In-car steps** (Alfa dealer bulletin, [OFFICIAL] NHTSA-hosted FCA TSB 08-065-20 "RAN RAP RAG and RSD 2.5 Radio Software Enhancements", dated 2020-06-24, https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf; map section applies only to RAN, the 3D-map radio):
1. Settings > Time and Date > GPS Synchronization > OFF, then set time and date manually (the TSB does this first, then turns it back ON afterward).
2. Start the engine and leave it running for the whole update (the TSB says "safely").
3. Nothing else in the USB ports. MENU > Settings > System > Software Update.
4. Insert the stick "in the port below the center console armrest" (TSB wording). Select OK. No operator action is needed. A confirmation message shows when done. Remove the stick.
5. Settings > Time and Date > GPS Synchronization > ON.
- Stick prep per the same TSB (dealer software, not NavShop): blank stick, at least 16 GB, NTFS, copy the folder contents, not the folder itself. The NavShop map is 10.1 GB, so 16 GB or more fits; a Stellantis bulletin for another unit says 32 GB minimum and NTFS (https://static.nhtsa.gov/odi/tsbs/2024/MC-10251848-9999.pdf, search snippet only).
- Duration: no official figure for this map. Forum: 38 minutes (v1086 on an 18 Stelvio), about 1:15 (another 18 Stelvio), roughly 40 minutes, 30 to 70 minutes in a European guide. [FORUM]

**Minimum software first (relation to MV 090.000.061).** TSB 08-065-20 reads the current version at Settings > System > Software Update > Current Software:
- MV-002.009.059 or lower: early 2.0 radio; this bulletin's software will not load; use other bulletins.
- MV-072.001.002 through 085.000.046: update the ETM and the map.
- MV 085.000.046: update ETM only.
- MV 090.000.061: latest, no action.
- "The map update procedure must be performed after updating the ETM software." If ETM was at MV 081.000.004 the map update does not have to be performed (TSB wording).
- Forum (Club Alfa, March 2020, Europe): firmware 001.xxx.xxx is not suited for user map updates and updating it deletes the installed maps; 002.xxx+ supports it. https://forum.clubalfa.it/threads/aggiornamento-navigatore.123975/page-41
- After ETM goes to MV 090.000.06x on cars built 2017-06-30/2017-10-30 to 2018-04-12, the TSB says BCM, AMP, ABS, IPC, PAM and blind-spot sensors MUST also be updated.

## 2. Dealer route

- Bulletin: TSB 08-065-20 (supersedes 08-081-19). Applies to 2018-2019 (GU) Stelvio, North America, built 2017-10-30 through 2019-07-12 with radio RAN or RAP (also RAG, RSD). [OFFICIAL]
- Labor operations (as printed; the amounts column came out of the PDF in a different order than the descriptions, so which hours go with which op cannot be matched with certainty): 18-60-02-9B "Check Software Level and Perform Software Update (ETM Only)"; 18-60-02-9A "Check Software Level and Perform Software Update (ETM and Map)"; 18-60-02-9C "Radio, Software - Create USB Jump Drive for ETM"; 18-60-02-Y3 "Create USB Jump Drive for 3D Map" (the two "Create USB" ops are one time only per dealer). Hour values printed in the table: 0.2, 0.3, 0.6, 0.8. Failure code CC; the symptom must match (radio reboot while driving, stays on after exit during a call, remote start volume).
- Price a Canadian dealer would charge: NOT FOUND in any source. The bulletin is a warranty-style procedure tied to the symptoms, not a customer map-update price list.
- DTC clearing, quoted from the map branch, step 15: "Clear all DTCs that may have been set in any module due to reprogramming. The wiTECH application will automatically present all DTCs after the flash and allow them to be cleared." Confirmed. The bulletin also tells the dealer to re-pair phones afterward and to re-set radio presets.
- Dealer download source: DealerCONNECT > Service > UCONNECT Command Center > Uconnect > Dealer software downloads, "MAC" selection for 3D Navigation maps (dealer-only, security access).

## 3. Does a map update change the UI/features; known failures

- UI/features change: NOT FOUND in an official source. The files are NDS map data (v1176), not unit firmware, so no UI change is expected; this is an inference. No source mentions new POIs, speed limits or lane guidance for NA v1176.
- Failure cases: all [FORUM] via search-result summaries, because the forum sites redirect to a pay-per-crawl wall (HTTP 402) and could not be opened. Treat as unconfirmed.
  - Car will not read the drive; pressing OK returns to the Map Update page (stelvioforum.com/threads/map-update-usb.17581/).
  - "USB has no valid map updates", even with NTFS (giuliaforums.com/threads/nav-maps-update-in-usa.41462/).
  - Corrupt portal file: a dealer reportedly said a version "never worked" and v1086 worked where v1081 did not (stelvioforum.com/threads/north-america-navigation-update-available.13132/).
  - Black navigation screen after load that reset after more than 72 hours parked (stelvioforum.com).
  - Stick format: sources say NTFS (TSB, stelvioforum), one owner reported success with exFAT on 32 GB, Mac formats reported to fail on newer units; stick size at most 64 GB advised by one owner. Extract any zip contents; do not copy the zip onto the stick.
  - USB port: front port, not the rear (the rear is power only, per Club Alfa guide); TSB says the port below the center armrest. One owner could not use the port under the HVAC controls.
- Official, relevant: NHTSA TSB lists "radio navigation continues to reboot after a Map Update" for 2017-2019 Giulia / 2018-2019 Stelvio in a later bulletin (https://static.nhtsa.gov/odi/tsbs/2024/MC-10251848-9999.pdf, snippet only, not read in full).

## 4. Reading the current version on the unit

- Software (ETM) version: MENU > Settings > System > Software Update > Current Software [OFFICIAL, TSB 08-065-20 inspection procedure]. A format such as MV-090.000.061.
- Map version: no official menu path found. The portal's FAQ-style pages ("About your map") were not reachable. Forum mentions of the version label are unconfirmed (the Club Alfa guide uses the same Settings > System > Software update > current version for firmware). For CUORE: record the ETM version from the TSB path and the map package number the owner types in from the unit if it appears there.

## 5. Download outcome

- Portal identified: https://stellantis.navshop.com/#/downloads (Alfa Romeo > Stelvio > 3D CONNECT NAV > North America v1176).
- No purchase, login, account or checkout was encountered; the files are on a public TomTom CDN URL and returned 200 to HEAD. Free status rests on the owner's statement; no price shown in portal data.
- Files NOT downloaded: the shell permission layer denied both download commands (license, then the 10.87 GB map). Empty folder exists: C:\Users\User\AppData\Local\Temp\claude\C--Users-User\b392762d-d462-4aec-a062-100f3568b08f\scratchpad\map_download\
- Nothing to verify: no file name/size/SHA-256 beyond the HEAD headers above (MAP21331.bin 10,868,879,360 bytes; .dct 132 bytes; ETag for the map c6f32512c796e767247d3ae21b665386:1785406118.203674).
- Owner next step if downloading by hand: open the portal, select Alfa Romeo > Stelvio > 3D CONNECT NAV (not MY20, not the 6.5" CONNECT NAV), download both files, confirm the .bin size is about 10.1 GB, format a 16 GB or larger stick as NTFS (32 GB is fine), copy both files to the root, then do the in-car steps with the engine running.

## Subagent note
The user's mid-task message asked for subagents; the two I tried to launch were denied by the permission layer, so all research was done directly.

## Sources
- TSB 08-065-20: https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf [OFFICIAL]
- NavShop: https://stellantis.navshop.com/ (assets read: main.js, chunk-GNEX7KHT.js) [PORTAL-DATA]
- TomTom CDN files above [PORTAL-DATA]
- HERE portal (not applicable): https://chryslergroup.navigation.com/home/en_US/ChryslerNA/CAD [OFFICIAL]
- Uconnect software update FAQ: https://www.driveuconnect.com/support/software-update.html [OFFICIAL]
- Club Alfa guide: https://forum.clubalfa.it/threads/aggiornamento-navigatore.123975/page-41 [FORUM, Europe, 2020]
- stelvioforum / giuliaforums / alfaowner threads cited above [FORUM, search snippets only]
- Europe Mopar Map Care: https://maps.mopar.eu/en/home [OFFICIAL, Europe only]

## 6. Side question: CUORE on the car screen via CarPlay / Android Auto (web research only, no build)

- The 8.8" Stelvio supports CarPlay and Android Auto (Carvana lists both as standard on 2018 Stelvio; Android Police 2017 and hdmotori.it Dec 2017 tie it to the 8.8" Alfa Connect 3D NAV update). Which software level enables it on this car: NOT confirmed; check on the unit.
- Neither platform has a diagnostics/OBD app category. Apple's CarPlay categories (9to5Mac, citing Apple's Feb 2026 developer guide): audio, communication, driving task, EV charging, fueling, navigation, parking, public safety, quick food ordering, voice-based conversational. Android Auto: media, navigation, IoT, point-of-interest (plus weather, browser, video announced). A web-app like CUORE cannot simply be loaded on either screen.
- Some commercial OBD apps claim CarPlay gauges (OnTrack, OpenOBD, DriveHub listings), unverified how Apple approved them. Torque Pro: no CarPlay/Auto evidence found.
- Practical neutral options for CUORE: (a) phone/tablet beside the dash running the CUORE web UI over the ELM327 link, (b) a separate small display, (c) a CarPlay/Android Auto-approved category wrapper (driving-task) needs an app built and approved by Apple/Google, which is a development project, not an install.
- Sources: https://www.thedrive.com/news/this-nifty-mobile-obd2-scanner-app-is-carplay-compatible.md ; https://www.carvana.com/buy/2018-alfa-romeo-stelvio/ ; https://www.androidpolice.com/2017/11/16/android-auto-now-available-alfa-romeo-models-well-one-fiat-two-head-unit-manufacturers/ ; https://developer.android.com/docs/quality-guidelines/car-app-quality
