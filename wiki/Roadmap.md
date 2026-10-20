# Roadmap

The product direction is **Alfa Romeo first**, then **Maserati and Ferrari**, with all marque specifics kept in data and configuration. The planning documents are [docs/project/ROADMAP.md](https://github.com/dangelojohn/CUORE/blob/main/docs/project/ROADMAP.md) and the handbook's [06-roadmap.md](https://github.com/dangelojohn/CUORE/blob/main/docs/handbook/06-roadmap.md); this page summarises both.

## Vision

CUORE is for a mechanic who specialises in cars that are loved, not merely driven: the Alfa Romeo Stelvio and Giulia today, the Maserati Levante and Grecale and the Ferrari Purosangue next. The mechanic decides; CUORE remembers.

## Done

- Systems layer (25 systems), electrical and physical layout with inspections, job workflow with hypothesis ledger, MES-style modules view, tools page, timeline, media (including audio), parts, feedback and inbox, printable report and PDF, experience links.
- Tests catalogue; systems dive-in; systems map overlay with live state.
- Case memory: closing a job records a case, and new jobs are pre-filled from the closest past case.
- **Marque port groundwork:** the page theme (`data-marque`) is computed per request from the VIN; model-specific wording moved into the knowledge tables; a Maserati fixture test exists.
- "Tell CUORE" mobile page rebuilt: dark, one statement per screen, a fill-up recordable in three taps, a camera on every form; a mobile API contract is documented for a future native app.
- **Live link:** first real reads from the car (gateway-silent bus, 29-bit route, filter-reset fix), the guided full scan, the scan log with diff and export, scan health report, live-board freeze-frame panel, and a read-only SLVT replica.
- Modifications layer (catalogue, per-car ledger, MES handoff cards, capability matrix), kept separate from diagnostics.
- Connect to car: adapter, bus, VIN, guided scan inline.
- Chassis-bus work: 11-bit listen routes, ABS address confirmed, out-of-order cables.
- Data snapshot and a state archive, with a pre-push backup hook available.

## Next (open items)

1. **First guided scan with both cables** on the real car under the new rules, then the decisive EVAP tests: ESIM hand-vacuum test (watching the switch parameter), ESIM bench test and orientation check, the dealer tool's ECM flash check and the small-leak test. **Do not clear codes** until these are done.
2. **VIN checks** for the recalls and notices that could have reflashed the engine computer.
3. **Fix the legislated-route silence** and confirm which route answers; read Mode 06 first whenever P0440 reports the lamp bit again.
4. **Chassis-bus discovery:** 11-bit discovery, ABS re-read, passive capture of MES on the chassis bus; find IHS and CH module addresses.
5. **Manufacturer data identifiers:** replace unverified catalogue entries with real definitions from service information.
6. Fill known gaps: EVAP purge and vapour-pressure limits, peak boost, tyre placard pressures, unknown torques; Grecale and Levante experience links and parts; 15 part images.
7. **Native app:** the owner has the means to build one; the web page and the JSON contract are the reference. Location-based and background features belong to the native app, not the web.
8. **Hardware options:** second adapter, Bluetooth or Wi-Fi adapter, a native CAN interface for passive capture.
9. Firewall rule and the pre-push hook install (owner action).
10. Timeline and gauge improvements; label margin confirmation.

## Port to Maserati and Ferrari

The port is a data task more than a code task, with the Stelvio as the template:

| Item | Status |
|---|---|
| Marque theme from VIN | done (WMI prefixes for Maserati SUVs return unknown rather than guessing Levante or Grecale) |
| Platform relationships | recorded: Grecale shares the Giorgio platform and engine family (corroborated); Levante differs (component-level overlap only) |
| Bus, pin, bit-rate and module data per platform | **unknown for all three sibling cars**; a research pass found nothing that met the evidence bar, so the table is empty on purpose. It must be learned on a car, not inferred from the Giorgio pinout |
| Module maps and data-identifier catalogues per platform | to do, per car |
| VIN decode for the Maserati prefixes | to do |
| Specification, experience and parts tables per marque | to do |
| Brand typefaces and palette | design rule: marque typefaces and true-black text are constant across light and dark themes |

An audit on 2026-10-13 grepped templates, styles, services and the live layer for hard-coded model names, platform names and colours, classified each hit (data to move, sample case to keep, theme already keyed off the marque) and fixed the data hits.

## Principles that gate the roadmap

Every feature is checked against the core directive: does it serve diagnosing, proving, or learning for the next car? If not, it is not built. No boards, throughput metrics, blocking gates or inventory management. CUORE advises and records; it never blocks, manages or replaces the mechanic or his other tools.

Related: [[Project History|Project-History]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].
