# Digital Rear-View Mirror

A planned accessory on the reference car, a **2018 Alfa Romeo Stelvio 2.0T** (VIN ZASFAKPN5J7B88115). The owner asked on 2026-10-22: "We also require a digital rear view mirror installed". **Status: planned. Product not named, date not set.** This page is research and a plan; nothing was done to the car, the adapter or any server.

Full document: [`docs/maintenance/DIGITAL_REAR_VIEW_MIRROR_INSTALL.md`](https://github.com/dangelojohn/CUORE/blob/main/docs/maintenance/DIGITAL_REAR_VIEW_MIRROR_INSTALL.md). CUORE job **98a6aad68d72** holds the request and the cautions.

**External reference and inference, not CUORE readings.** The sources are web pages and owner posts gathered on 2026-10-22; none was measured on the car. Where a fact was not found it says so.

## Three product types

| Type | What it is | Main point |
|---|---|---|
| Full-display mirror | Replaces the OEM interior mirror | Lowest reversibility; the OEM mirror comes off its mount |
| Strap-on mirror cam | A display that straps over the OEM mirror | Highest reversibility; no mount work |
| Dashcam-mirror with rear camera | A mirror body with a front camera and a rear camera on a cable | Adds a front lens near the ADAS camera |

Choice criteria, in order: keeps the forward camera and sensor window clear; reversible; ACC-only power with no parking mode; a cable path that drills nothing; no reverse-signal tap in the liftgate; no CAN or LIN connection.

## The key cautions

- **The forward ADAS camera sits near the mirror.** I-CAR lists the 2018 Giulia camera as "Camera Near Rearview Mirror" and requires recalibration if the camera or the windshield is removed or replaced; the Stelvio shares the platform, so this is likely the same but was not found for the Stelvio itself. Do not touch the camera, its bracket or its cover, and put nothing in its view. This car's radar module already holds an intermittent **C141B-97 "camera blinded"** (8 of 18 reads, 2026-09-02 to 10-19), so keep a before and after record and never clear DASM or HALF codes ([[Code Reviews|Code-Reviews]]).
- **Power: ACC-only, no parking mode.** The network codes centre on the BCM and the ABS U1700-87 freeze frame holds **10.6 V** ([[Network and Brake Findings|Network-and-Brake-Findings]]). A parked load adds risk to the battery and to Start/Stop. Use an add-a-fuse in the passenger-footwell fuse box on a circuit verified by meter (dead key-off, live key-on), not F36 (it carries EOBD, the head unit and climate control) and not the BCM feeds. If a low-voltage cutoff is ever used, set it at or above 12.2 V and record the key-off current.
- **Never the OBD port for power.** CUORE needs the port ([[Hardware and Cables|Hardware-and-Cables]]). **Never tap or splice CAN or LIN**; a bus disturbance already lit the airbag lamp once on this car ([[Safety Rules|Safety-Rules]]).
- **Airbags.** Route behind, never in front of, the curtain airbag; no zip ties on the airbag harness; do not probe or move airbag wiring. If the trim layout is unclear, use a professional installer.
- **Liftgate.** Recall **18V203** (liftgate wiring and switch water intrusion) is in the catalogue and has no VIN check on record; the remedy is added sealing, so a new cable must not break it. Recall 18V205 (water at the BCM A-pillar connector) is also on the checklist, so do not disturb the A-pillar sealing or the BCM connectors ([[Recalls and Campaigns|Recalls-and-Campaigns]]).
- **No battery disconnect.** The EVAP proof run is pending ([[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]); use the fuse, not the terminal.

## Not found

The OEM mirror connector pinout and whether it is on LIN, CAN or plain power; the Stelvio mirror removal procedure; an FCA fuse diagram naming a cabin ACC fuse (only a third-party diagram was found); a Stelvio-specific digital-mirror install (GiuliaForums dashcam threads exist but were behind a paywall and not read); whether this VIN has the factory ParkView camera or the auto-dimming mirror; the car's key-off sleep time and current.

## What CUORE records afterwards

Product and part number; fuse box, slot and circuit; tap fuse rating; ACC or constant and how it was verified; current draw key-off with how and when it was measured; ground point; cable routes; reverse signal used or not; airbag and ADAS checks; a CUORE scan before and after; date and installer; the 18V203 and 18V205 VIN-check answers.

Related: [[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]], [[Recalls and Campaigns|Recalls-and-Campaigns]], [[Network and Brake Findings|Network-and-Brake-Findings]].

Wider evaluation: the owner also asked about front, side and 360 cameras and a head-unit or interface-box upgrade. Four routes are compared in [[Infotainment and Camera Upgrades|Infotainment-and-Camera-Upgrades]] (job c70f2f3e6932, cross-linked with this job); standalone mirror systems are route A there. Do the mirror and any infotainment work on separate days.
