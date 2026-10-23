# Wiring and Ground Faults

Added 2026-10-23. This page covers three tools for finding a bad ground or a resistive supply feed, which a code reader cannot see directly. **Fact** means a CUORE reading or a cited source; **inference** means reasoned from facts and still to be confirmed with a meter.

## Why it matters on the reference car

Several of the Stelvio's modules complain together (see [[Network and Brake Findings|Network-and-Brake-Findings]]). A weak ground or a high-resistance feed is one candidate that explains a spread of modules at once. Known leads, all **fact**: ABS `U1700-87` was logged with a freeze frame of **10.6 V** (2026-09-04); BCM `B101D-15` (battery voltage circuit, short to battery or open) is set as of 2026-10-23; the cluster codes `U1711/U1712/U1713` were seen repeatedly and have not been seen since 2026-10-19.

## 1. Failure-type wiring map

`GET /api/wiring?vin=...` (and a table on the Electrical page, section "Wiring and ground faults by failure type"). It parses every real MES log for the VIN (SCAN and FES, 41 logs) plus CUORE's own scan store, and groups each code by its **failure-type byte**, the suffix in `B101D-15`:

| Class | Bytes | Meaning |
|---|---|---|
| Wiring | -11 short to ground, -12 short to battery, -13 open, -14 short to ground or open, -15 short to battery or open, -16 voltage low, -17 voltage high | something measured wrong on the wire |
| Communication | -81 to -89 (-86 invalid message, -87 missing message) | a message did not arrive; the wire may be fine |
| Performance | -92 to -99 | component fault |
| Signal / range | -18 to -1F, -2x (-1C, -29, -2F erratic) | signal not plausible |

A **read** is one session: sightings of the same module and code within 10 minutes count once. CUORE-store codes are counted only if the status byte says the code is really set (a status of `0x40` is a never-failed entry and is ignored).

The **ground-suspect score** is an **inference**: the share of a module's reads that were -11, -14 or -16 or whose freeze frame logged a low supply voltage (below 11.5 V, or below 12.8 V with the engine turning). A module with fewer than 3 reads is marked low confidence.

Result for the reference car (2026-10-23, 245 sightings):

| Module | Reads | Wiring | Comm | Perf | Signal | Other | Ground-suspect |
|---|---|---|---|---|---|---|---|
| ABS | 2 | 0 | 1 | 1 | 0 | 0 | 0.50 (low confidence, 2 reads) |
| BCM | 45 | 1 | 6 | 11 | 24 | 3 | 0.00 |
| ECM | 38 | 0 | 0 | 0 | 0 | 38 | 0.00 |
| DASM | 22 | 0 | 14 | 8 | 0 | 0 | 0.00 |
| RFHUB | 9 | 0 | 2 | 0 | 0 | 7 | 0.00 |
| IPC | 8 | 0 | 6 | 0 | 0 | 2 | 0.00 |
| DTCM | 7 | 0 | 7 | 0 | 0 | 0 | 0.00 |

What it says, honestly: **no -11, -14 or -16 code has ever been recorded on this car**. The only wiring-class code is BCM `B101D-15` (one read, 2026-10-23). The only low-voltage freeze frame is ABS `U1700-87` at 10.6 V. Most BCM trouble is signal/communication class (`U1713-2F` and relatives, `U1736-86/-87`, `U1765-86`), which is what a bus or sender problem looks like and is also what a shared supply problem can look like; the map cannot tell these apart. That is the job of the next two tools.

## 2. Load-step voltage test (read-only recording)

Preset `load_step_voltage`: adapter voltage (`ATRV`), Mode 01 PID 42 (the ECM's own supply reading) and the BCM "Battery voltage" identifier `1004`. **Yes, BCM 1004 is in the registry** (`bcm_1004`, formula A/10, confidence unverified); on 2026-10-23 it read 14.5 V while the adapter read 14.5 V. The ECM's `1955` identifier is also in the registry but answered "request out of range" that night, so it is not used.

Recorded for 3 minutes at the fastest rate the poller allows, with the engine idling and the charger off, while the owner follows an on-screen script (page `/v/{vin}/load-step`): every 20 seconds one load is switched on for 10 seconds and then off (headlights, high beam, rear defrost, blower max, heated seats, brake pedal held), then all loads together, then recovery. Each recording row is tagged with the script step.

Analysis: for each load, the voltage drop each channel saw. A module whose drop exceeds the adapter's by more than **0.3 V** has extra resistance between the supply and that module (**inference**, a lead for the multimeter test). Limits are general automotive practice: about 0.2 V on a ground side, 0.3 V on a positive side, 0.2 to 0.5 V total ([Fluke](https://www.fluke.com/en-us/learn/blog/digital-multimeters/how-to-check-starter-circuit-voltage-drop-with-a-multimeter)). API: `POST /api/live/load-step/start`, `GET .../status`, `GET .../analysis`. **Not run yet.** Full procedure: `docs/maintenance/LOAD_STEP_VOLTAGE_TEST.md`.

## 3. Multimeter voltage-drop procedure

`docs/maintenance/GROUND_VOLTAGE_DROP_TEST.md`: battery negative to engine block, block to body, body to battery negative, each with headlights and blower on, with limits and the rule for reading them. **Stelvio ground-point locations were not found** in any sourced diagram or forum post; the page says to ask the dealer for the ground-point diagram and its G-codes (the only ground names on file, G003A and G003B, come from an FCA bulletin that does not give their location). The page also records the **BCM / A-pillar connector water-intrusion recall (NHTSA 18V205, Transport Canada 2018-151)** as a known wiring weak point; whether this VIN is in scope is not known, so check by VIN.

Results go into the job as descriptive entries (what, when, values, meaning, next test) with a `measurement` reference, and physical findings (a corroded ground, water at a connector) go on the Electrical page as inspections.

## Limits

- The map only knows codes some tool read; a ground fault that never set a code is invisible to it.
- The score is meaningless on a handful of reads, and today only the BCM, ECM, DASM, RFHUB, IPC and DTCM have enough.
- PID 42 is answered by the ECM and the TCM; only the ECM's value is recorded.
- Code in this change has not been run on the car; restart the CUORE server to load it.
