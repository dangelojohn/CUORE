# Infotainment and Camera Upgrades

An evaluation for the reference car, a **2018 Alfa Romeo Stelvio 2.0T** (VIN ZASFAKPN5J7B88115). The owner asked on 2026-10-22 to upgrade, replace or enhance the infotainment so that extra cameras can be added: the rear digital-mirror camera, front, side and 360 degree views. **Status: planned / evaluation. No product chosen, nothing bought or installed.** This page is research only; nothing was done to the car, the adapter or any server.

Full document: [`docs/research/INFOTAINMENT_CAMERA_UPGRADE_OPTIONS.md`](https://github.com/dangelojohn/CUORE/blob/main/docs/research/INFOTAINMENT_CAMERA_UPGRADE_OPTIONS.md). CUORE job **c70f2f3e6932** holds the request; it is cross-linked with the digital-mirror job **98a6aad68d72** ([[Digital Rear-View Mirror|Digital-Rear-View-Mirror]]).

**Neutral framing.** Several options are paid products. No product here is labelled recommended or best. The routes are compared on objective criteria: risk to this car's diagnostics, OEM functions kept, camera capability, reversibility, documentation quality and price. The choice is the owner's.

**Confidence labels.** [official] manual or datasheet; [listing] vendor page (a sales claim); [forum] owner post, mostly from search excerpts because the forum pages were bot-gated; [inference] reasoning, not a source statement. "Not stated" and "not found" are carried as the sources left them. Every source URL is in the full document.

## Four routes

| | A. Standalone camera / mirror | B. Interface box, keeps OEM screen | C. Android head unit | D. Factory MY20+ retrofit |
|---|---|---|---|---|
| Price as listed | Mirror displays $249.99 to A$399.95; Rydeen TOMBO-360X $649; Brandmotion SurroundVUE $1,279.99 | $289 to about $1,399 (kSmart $289, ENG-Custom EUR 370, IMI-1000 GBP 465, Abt $850). Ampire RL4-C3D: not stated | US$527 to about US$1,021; Sigma CAD$1,049; MND EUR 999-1,399 | ENG-Custom MY20 kit EUR 3,000; factory CarPlay activation needs a USB hub of about EUR 100-140 plus labour |
| Cameras | Own set; SurroundVUE is a 4-camera 360 with its own 9.1 in monitor [listing] | Front + rear inputs (CVBS class); side via turn signal at ENG-Custom [forum]; 360 only a vendor claim | Generic 360 app claimed by two listings; input count not stated (Sigma: one RCA input) | None stated |
| Touches CAN / radio | No | Yes: in series with the radio's screen cable and connectors; RL4-C3D passes the Quadlock power/CAN [official] | Yes: display swap plus CAN/harness tap; ETM stays [listing] | Yes: new ETM, screen, often HVAC and cluster |
| Key risk to this car | Low: a new load and wiring path, not a network node [inference] | Medium to high: radio can drop off the bus; manual asks for a battery disconnect [official] | High: one 2018 Giulia report of cut wires and OEM software dying [forum] | Highest: PROXI rewrite on top of stored B10AA-4A [inference] |
| Reversibility | High to medium | High [inference] | Medium | Low: no return once connected [listing] |

No Giulia/Stelvio-specific 360 kit was found, and Alfa never offered 360 from the factory [forum]. A Mopar or Alfa camera, surround view or digital mirror for the 2018 Stelvio was **not found** (ask a parts counter with the VIN).

## Why diagnostics come first

The car already holds the BCM network codes **U1711 / U1712 / U1713**, a **B10AA-4A** PROXI "incorrect component installed" stored 2026-10-14 and co-timed with **U1736** (the radio, never read), an ABS freeze frame at 10.6 V, and an open EVAP proof run. Whether it has a security gateway is not established. Routes B, C and D sit on or replace the radio path already implicated by U1736; D also rewrites PROXI. Diagnostic exposure, lowest first: A, B, C, D [inference]. See [[Code Reviews|Code-Reviews]] and [[Network and Brake Findings|Network-and-Brake-Findings]].

## Sequencing (an inference)

1. No infotainment or CAN-tap work until after the **EVAP monitor proof run** and the **2026-10-28 dealer visit**, so a new code cannot be confused with an existing one.
2. Record a **CUORE baseline** before the install (module list, all U-codes with status bytes, through a CUORE session) and a key-off sleep-current log of 20-30 minutes; repeat both after and compare.
3. One change at a time; not on the same day as the mirror install. Never clear DASM, HALF, airbag or ABS codes afterwards.
4. Read the radio software level from its menu first. TSB 08-065-20 (radio reboots on 2018-2019 Stelvios; latest MV 090.000.061, USB update, not a wiTECH flash) was opened in full; the text of 08-029-20 was not found. Version history, the CarPlay/AA PROXI path, map updates and the DTC-clearing conflict with the EVAP proof rule: [`RADIO_SOFTWARE_AND_UI_OPTIONS.md`](https://github.com/dangelojohn/CUORE/blob/main/docs/research/RADIO_SOFTWARE_AND_UI_OPTIONS.md).

## Open questions for the owner

Screen size (8.8" or 6.5", touch or non-touch); factory ParkView; Harman Kardon; budget; whether 360 is wanted, and CarPlay / Android Auto as well or cameras only; which camera positions; who installs; radio symptoms, build date and software level.

## Related

[[Digital Rear-View Mirror|Digital-Rear-View-Mirror]] (route A is that job's product class), [[Safety Rules|Safety-Rules]], [[Recalls and Campaigns|Recalls-and-Campaigns]], [[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]], [[Guided Full Scan|Guided-Full-Scan]].
