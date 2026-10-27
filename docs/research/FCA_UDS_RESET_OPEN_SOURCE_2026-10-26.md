# FCA UDS service-reset: open-source / openly published evidence (2026-10-26)

Scope: Alfa Giulia/Stelvio (Giorgio), FCA 2015+ UDS. Method: web search + a few page fetches only. No COM3, no binaries, no MES database, no keys collected.
Headline: NO open-source repo or published trace was found that shows the UDS bytes (service, DID or routine ID, session, security level) of a cluster service-interval reset or an ECM oil-life reset on any FCA/Alfa vehicle. Everything below is either adjacent tooling or procedure-level (menu names), not byte-level.

Search limits (be honest about coverage):
- WebSearch is a summarising engine; GitHub code search was not available, so absence of hits is NOT proof of absence on GitHub.
- Forum pages (stelvioforum, giuliaforums, pacificaforums) 307-redirect to a "tollbit." bot-gateway host. I treated that as a bot check and did not follow it. So forum thread bodies were NOT read; only search-engine snippets of them are quoted, and are labelled as such.
- multiecuscan.net forum URL returned 404 on direct fetch (snippet only).
- NHTSA TSB PDF came back as compressed binary to the fetcher; its content below is from a search summary only (second-hand).

## Findings

### F1. yorch/pacifica-obd (GitHub)
- URL: https://github.com/yorch/pacifica-obd  | date: not shown on page (project is about a 2021 Pacifica; repo has ~50 commits)
- What: Python OBD/UDS toolkit for 2021 Chrysler Pacifica via vLinker FS. Code.
- Shows: read-only. Mode 22 reads (example 22 F190 VIN, F187 at module 7E0), a `10 03` request at 7E0 (page does not label it), module discovery on CAN-C and CAN-IHS, DTC clear. No 0x2E, no 0x31, no 0x27 implemented. States BCM/ABS/airbag/HVAC/TPMS/coding are NOT covered and need a manufacturer-aware tool. Mentions a Security Gateway doc (docs/chrysler-sgw.md, contents not read).
- Applicability: same parent company, but a 2021 Pacifica (different platform, 11-bit 7Ex addressing shown, SGW). Not Giorgio. Low direct value; useful only as a pattern for safe read-only discovery.
- Licence: MIT; states no third-party OEM or GPL code.
- Confidence: CONFIRMED for "read-only, no reset"; UNKNOWN for anything about Stelvio.

### F2. References cited by pacifica-obd (not opened; names only)
- grantUser/fca-ecu-diagnostics ("FCA/Stellantis ECU/CAN map, Mode-22 PIDs, DTC text") and grantUser/seedkey-fca-stellantis (0x27 seed->key generators). Both are marked "currently unavailable" by the citing README. I did NOT look for or fetch them. The second is a key-generator repo: out of scope for CUORE (never collect keys); its existence only SUGGESTS FCA has gated (0x27) functions.
- ludwig-v/psa-seedkey-algorithm: GPL-3.0, PSA not FCA. Method reference only. Do not reuse code (GPL, wrong brand).
- Confidence: SINGLE_SOURCE (as cited by F1).

### F3. Stellantis service bulletin (NHTSA TSB MC-10247449-9999), via search summary only
- URL: https://static.nhtsa.gov/odi/tsbs/2023/MC-10247449-9999.pdf (2023 folder; vehicles not verified by me)
- What: official service procedure text. Per the search summary: with the scan tool, go to the IPC > "Miscellaneous Functions" > "Reset Service Information" routine; or PCM > "Miscellaneous Functions" > "Reset oil change indicator".
- Shows: that the vendor tool exposes TWO distinct functions: one on the cluster (IPC) and one on the engine controller (PCM). Names are the tool's menu names, not UDS bytes. Whether they are 0x31 routines or 0x2E writes is NOT stated (the word "routine" is the tool's wording).
- Applicability: FCA US family (Stellantis). Supports the two-module split CUORE assumed. Not Alfa-specific.
- Confidence: SINGLE_SOURCE, second-hand. Re-read the PDF text directly before relying on it.

### F4. Alfa forum snippets (search-engine summaries only; thread bodies not read)
- https://www.stelvioforum.com/threads/alfaobd-service-reset.25281/
- https://www.stelvioforum.com/threads/can-someone-with-mes-alfaobd-check-their-ecu-oil-life-remaining-parameters-please.22901/
- https://www.stelvioforum.com/threads/scheduled-maintenance-reset.24621/
- https://www.giuliaforums.com/threads/service-interval-reset-mystery.56399/
- Per snippets: AlfaOBD exposes a "Service Coupon Number" configuration value (0-15) said to live in the BCM; factory value reportedly 10; a PROXI alignment reportedly restores coupons; infotainment reset may not clear the cluster indicator and an ECU-side oil reset may also be needed; pedal sequences are reported as unreliable on Stelvio; MES worked where the pedal method did not.
- Shows: user-level reports of a multi-module (BCM coupons + cluster + ECM) state. No bytes.
- Confidence: SINGLE_SOURCE each, anecdotal, unverified.
- Related: MES forum "Giulia SERVICE KM RESET failure to execute" (2018 Giulia, "FAILED TO EXECUTE", no cause): https://multiecuscan.net/forum/viewtopic.php?p=24442 (snippet only). Shows MES has a "service km reset" function on Giulia and that it can fail; failure cause UNKNOWN.

### F5. Klavkarr guide (commercial tool, procedure only)
- https://www.klavkarr.com/blog/service-reset/6-reset-oil-service-light-alfa-romeo
- Menu path "ECU Maintenance Interval" > "Reset Maintenance Information" for Giulia/Stelvio. Commercial tool; no bytes. Do not treat as recommendation.
- Confidence: SINGLE_SOURCE.

### F6. Generic UDS libraries and background (reuse candidates, not FCA-specific)
- pylessard/python-udsoncan, MIT: session change, unlock_security_access, write DID, routine control. https://pypi.org/project/udsoncan/ (docs show the generic flow only).
- CaringCaribou uds.md (dump_dids etc.), GPL-3.0; rejected for CUORE earlier. Read-only findings: DID-range scanning exists; nothing FCA-specific found.
- UDS background: 0x22 read DID, 0x2E write DID, 0x31 routine control (e.g. "reset odometer"-type functions), 0x27 security access. Generic, CONFIRMED as standard but says nothing about which one FCA uses.
- VAG analogy (vis4vag.com diagnostics pages): VAG UDS clusters do oil/service resets as adaptation/routine-type functions, and may lock out after a failed attempt (retry after ignition off). Different manufacturer; weak analogy only.

### Searched, found nothing
- opendbc/openpilot FCA: only CAN signal DBCs for Chrysler/Jeep (ACC/LKAS); no Giorgio, no 18DA diagnostic content found. UNKNOWN whether any diagnostic code exists.
- SavvyCAN/candump traces of an FCA service reset: none found.
- HackADay/blog write-ups of FCA cluster or ECM service-reset traces: none found.
- AlfaOBD logs/sniffs with bytes: none found (AlfaOBD is closed; no public log located).
- FCA 0x31 oil-life routine IDs, FCA cluster maintenance DIDs: none found.

## (a) Shortlist (3 most relevant)
1. Stellantis service bulletin MC-10247449-9999 (F3): only authoritative statement of the two-function structure (IPC "Reset Service Information", PCM "Reset oil change indicator"). Verify directly.
2. yorch/pacifica-obd (F1): only open FCA UDS code found; MIT; read-only discovery pattern and the explicit note that gated/coding modules need vendor-aware tools.
3. Stelvio/Giulia forum threads on AlfaOBD/MES service reset (F4): the only Alfa-specific evidence of module split (BCM coupons, cluster, ECM); anecdotal and not directly read.

## (b) Candidate mechanisms for the Stelvio service reset (all UNVERIFIED as to bytes)
- M1. Cluster (IPC) function "Reset Service Information", executed as a diagnostic routine (0x31) or a DID write (0x2E). Evidence: F3 wording ("routine" in tool menu); SINGLE_SOURCE; routine vs write NOT established.
- M2. ECM/PCM function "Reset oil change indicator", same ambiguity. Evidence: F3; SINGLE_SOURCE. Likely extended or programming session; NOT established.
- M3. BCM "Service Coupon Number" (0-15) configuration/adaptation value, likely a plain DID write or PROXI-aligned setting. Evidence: F4 snippets only; SINGLE_SOURCE, anecdotal.
- Security: F3 describes the reset as an ordinary scan-tool menu item and no source says it needs 0x27, but nothing confirms the absence of a lock either. The existence of FCA seed-key repos (F2) shows some FCA functions are gated; which ones is UNKNOWN.
- Is the Continental cluster maintenance value a plain DID (0x22/0x2E) or a routine (0x31), and in which session? UNKNOWN. No public source found.

## (c) Still unknown
- Actual service ID (0x2E vs 0x31), DID or routine ID, sub-function, payload, session (01/03/extended/programming) and security level for IPC, ECM and BCM resets on Giorgio.
- Whether the Stelvio cluster accepts the reset only with a prior coupon/BCM state, or after oil-life is reset on the ECM first.
- Why MES "service km reset" fails on some Giulias (F4).
- Whether grantUser repos or any AlfaOBD/MES-adjacent public log exist (not searched in depth; keys deliberately not pursued).
- Read-only path forward that stays within CUORE rules: through CUORE sessions only, a 0x22 DID sweep of the cluster/ECM/BCM before and after a user-performed reset (menu/Uconnect/MES) and diff; the changed DIDs identify the plain-DID candidates. Not performed here.

## (d) Licence notes
- pacifica-obd: MIT (reusable with notice); it is read-only and mostly adds nothing CUORE lacks.
- python-udsoncan: MIT (reusable as a library).
- CaringCaribou: GPL-3.0; CUORE rejected it; do not copy code. Reading its docs for ideas is fine.
- psa-seedkey-algorithm: GPL-3.0; wrong brand; do not use.
- grantUser seed-key repo: not examined; CUORE must not collect or ship keys or algorithms.
- NHTSA TSB text: public government document; cite, do not republish wholesale.
- Forum content: copyright of posters; cite links only.
