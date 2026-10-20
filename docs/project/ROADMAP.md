# Roadmap

Open items as of 2026-10-20. Status notes come from the project notes and git history; "delivered" means a commit exists, not that it has been run on a car. Items needing the car are marked (car).

## 1. Brand roadmap

- Finish the Alfa Romeo version first (accent, Stelvio and Giorgio-platform data).
- Then port to Alfa Romeo, Maserati and Ferrari. Do not start the port until asked.
- Groundwork already in place: `data-marque` from the VIN, marque-neutral copy, Maserati fixture test (003d6a4); known-good bands gated by platform and marque with an honest "no band on file" for other models (05f7ae6); sibling-platform bus topology researched for Grecale, Levante and Purosangue (e8c8ff3).
- To do at port time: module maps and DID catalogues keyed by platform, spec tables keyed by vehicle, marque-specific experience-link sources (Maserati and Ferrari equivalents of the Alfa forums), marque accents and fonts via data.
- Sibling cars (Levante, Grecale) are used for parts cross-reference and experience links only after verifying what is actually shared (Grecale is Giorgio-derived; Levante is on a different platform, so overlap is component-level).
- Media: audio clips (bearing noises and similar) are a required kind alongside photos, scans and video (delivered in 7e05223; keep exercising it).

## 2. MES toolchain items

Ranked list from the toolchain notes, with current status. The authoritative ranked list is `docs/research/MES_CAPABILITY_GAPS.md`.

| # | Item | Status |
|---|---|---|
| 1 | Known-good parameter spec tables | Partly delivered: sourced ranges and bands (7ec2f48, 05f7ae6, `docs/reference/STELVIO_20T_KNOWN_GOOD_VALUES.md`); widen coverage |
| 2 | Mobile-friendly checklist page for use at the car | Delivered as the Tell CUORE mobile page (391e639, 18b3425); static artifact checklist exists as a printable snapshot |
| 3 | Mode 06 EVAP measured test values | Decoder and EVAP sub-test map documented (821e436); live values need (car) |
| 4 | Vendor capability-matrix ingestion (`mes_capabilities(vehicle, module)`) | MES vs CUORE capability matrix and handoff cards delivered (545abb8); ingestion of the vendor matrix still open |
| 5 | MES DTC description tables | Delivered at runtime from the MES install, never copied (169db2a) |
| 6 | MES simulation-mode enumeration of ECM actuators and adjustments | Open |
| 7 | Hardware: blue A5 and grey A6 cables (10 to 29 modules); second adapter for stimulus and response | Cables fitted in guided scans 2026-10-13 to 2026-10-15; second adapter and Y-splitter for "learn DIDs from MES" built in software (a6b11ab) and waiting on hardware (car) |
| 8 | High-rate voltage logging (PID 42 or a CAN frame) | Open |

Also open:
- CSV recording pipeline (`mes/csvlog.py` and five tools) was validated on synthetic fixtures; diff `docs/format/CSV_LOG_FORMAT.md` against the first real export and mark per-item confidence.
- Label printing: template geometry for the durable-ID sheets is unverified on paper; record measured margins and confidence once a printout is checked (the template offset calibration is saved per template and printer, 6ac133e).
- Transmission data capture (deferred): full scan for learned TCM DIDs, one MES recording of ZF 8HP parameters (ATF temperature, gear, slip) imported, optionally second adapter to learn DIDs from MES (car).

## 3. Open tool faults

- Legislated OBD reads (Modes 01, 03, 06, 07, 09, 0A) returned NO DATA on both routes on 2026-10-19 while UDS physical reads worked. Fix committed 2026-10-19 (4c35d27: probe always runs on CAN-C, 29-bit first, one retry on the other route); needs confirming on the car (car). Same family as the ABS answering only once.
- ABS answered identity discovery once (2026-10-15 00:08) and never again, including after an ignition cycle and an adapter warm start, while MES reads EPS and the private-CAN module through the same grey cable. Suspect the request and receive path (adapter filters after protocol setup, flow control, auto-format, 11-bit versus 29-bit diagnostics), not the modules. Per-request header and raw reply are now audited to settle it next time.
- The 29-bit (253 addresses) and 11-bit (239 addresses) sweeps of 2026-10-15 used waits shorter than the adapter's reply wait; they are not valid negatives and must be repeated (car).
- The 11-bit discovery sweep is built but has not been run on the car; the CAN-IHS 11-bit listen route is untested.
- First 19 02 request after a quiet period often returns CAN ERROR and a retry succeeds; keep the retry.
- One pre-existing failing check in the API suite ("clear assessment present") noted 2026-09-25; confirm whether still failing.
- Bench item, not car: reproduce the legislated-read silence on the bench against a fake responder.

## 4. Next on-car tests (all read-only, engine running unless stated, through CUORE)

From the 2026-10-15 chassis-bus session record:
1. Lone carriage return, then `ATI`.
2. Repeat identity read to the ABS at 0x2A with `ATST 19` and `ATAT0`.
3. `ATCRA` off with an explicit `STFAP 18DAF12A` pass filter.
4. Identity read with `ATFCSM0`.
5. Raw ISO-TP first frame with `ATCAF0`.
6. Passive MES-learn capture of a MES session on the chassis bus, to read the ids MES uses for EPS and the private-CAN module.

Diagnosis (reference car, EVAP detection path), in this order:
1. Read the ECM "external temperature" and the BCM ambient value against the real ambient. The ECM value was pinned at -61 C in a 2026-06 engineering log (all samples) and never re-read; ambient temperature and fuel level reach the ECM over CAN and feed the EVAP monitor (hypothesis "EVAP monitor inputs invalid").
2. Physical: ESIM mounting orientation against the service-manual drawing (an inverted or tilted unit holds the vent open and gives this exact signature, surviving part swaps); then vacuum at the ESIM port with a meter on the switch; then 5 V and 0 V back-probe at the ESIM; out-of-car bench test of the ESIM (flowchart in `docs/handbook/esim/`).
3. Dealer-side check of ECM calibration currency (flash check), and of the recalls that apply; the 18V636 reflash is the stronger lead than any EVAP bulletin.
4. One full EVAP monitor run without clearing (fuel level in the monitor window 15 to 85 %), then read Mode 06 EVAP test values and status bytes (SLVT replica page, bcc62f4).
5. Record each result as a descriptive job entry (RULES.md rule 8). Never clear before the monitor has run.

Scan plan: about ten complete guided scans over the whole diagnosis; track the count in the Scans log.

## 5. Process and quality items

- Re-run the full test suites after any UI or live-link change (last recorded counts 2026-10-19: scan_requirements 4, fullscan 261, api 96, active_probe 60, coverage 140, live 193).
- Keep the bulletin catalogue growing from opened documents only; every new code or job gets experience links.
- Keep the core directive check on every new feature (drift was flagged 2026-10-08).
- Refresh the handbook pages generated from code after structural changes.
