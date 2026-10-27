# How other tools reset Stelvio/Giulia service-due and oil-change counters (research, 2026-10-26)

Scope: 2017-2020 Giulia/Stelvio 2.0T (Giorgio), Continental cluster, IAW 10JA ECM.
No git, no COM3, no subagents. Web only. Findings below are what was actually found.

## Headline
No public source gives a UDS byte sequence (service, DID or routine ID, target module, security
behaviour) for any service-reset on this platform. None was found in AlfaOBD docs, MES
docs, GitHub, forums, or Mopar bulletins. Nothing here is invented. The only CONFIRMED
reset mechanism is a non-diagnostic driver pedal procedure from an FCA bulletin.

Blocked/skipped (respected): giuliaforums.com and stelvioforum.com redirect WebFetch to a
"tollbit." host (bot gate) - I did not follow it. alfaclubvic.org.au redirected to an
unrelated domain (myccodev.com) - not followed. Forum content below is therefore only from
search-engine summaries of those threads (SINGLE_SOURCE-grade, not read first-hand).
rockauto/alfissimo not visited. multiecuscan.net thread p=24442 returned 404 on fetch.

## Three different things (do not conflate)
1. Cluster "Oil Change Required" startup message / oil-life monitor (OLM) - what the FCA TSB resets.
2. Infotainment (Uconnect) maintenance tracker: "next service" mileage/date and the
   service "coupon" number. Separate store from item 1.
3. ECM oil quality/degradation adaptation (UniAir oil-quality model). Separate again.
A tool or pedal sequence that clears item 1 does NOT necessarily clear 2 or 3.

## Findings

### F1. FCA TSB 01-001-21 / 01-001-20 (official) - CONFIRMED (procedure), module not stated
- URL: https://static.nhtsa.gov/odi/tsbs/2021/MC-10188822-9999.pdf (also 2020/MC-10175722-9999.pdf,
  dated April 8, 2020). Read first-hand by decompressing the PDF.
- Scope: 2018-2021 (GU) Stelvio / (GA) Giulia, North America, 2.0L 280HP I4 turbo (EC2).
  Subject "Oil Change Monitor Displaying Prematurely". Quote: "involves resetting the oil life monitor".
- Driver/no-tool procedure, quoted: "Without pushing the brake pedal, push the ENGINE START/STOP button and
  cycle the ignition to ON/RUN position (do not start the engine)"; "Fully depress the accelerator pedal,
  slowly, five times within 10 seconds"; "push the ENGINE START/STOP button once to return the ignition to the
  OFF/LOCK position".
- Fallback quoted: "If the above process fails to complete, use the scan tool to complete the reset process."
  The bulletin does not say which module, menu, or UDS request the scan tool uses.
- Labor op 09-55-01-94 "Oil Life Monitor System - Reset Only" (0.2 h). Later bulletin TSB 01-001-26 (2026-05-16,
  per search summary, not opened) covers 2018-2026 - SINGLE_SOURCE on that part.
- Interpretation: this is a pedal-triggered reset, so the pedal signal is read over CAN by whichever module owns
  the OLM (probably ECM or BCM; UNKNOWN). Confidence the OLM pedal reset works on a 2018 2.0T in NA: CONFIRMED (FCA doc).
  It clears only the cluster OLM message (see F5).

### F2. Owner manual - UNVERIFIED
Searches found no owner's-manual text for the driver reset. A guide stated the info is not in the Owner's Manual,
Uconnect manual or User Guide (via search summary of a third-party page, SINGLE_SOURCE). I did not retrieve the
manual itself. Status: UNKNOWN whether the manual documents a cluster-menu reset. The TSB (F1) is the official
driver-level source. Cluster menu reset: no evidence found.

### F3. carwiki.de Stelvio (Typ 949) - SINGLE_SOURCE, partly contradicted
- URL: https://carwiki.de/alfa-romeo-stelvio-inspektion-zuruecksetzen (fetched 2026-10-26)
- Steps: ignition on, accelerator "six times in a row", then AUTO menu > AUTO STATUS, cycle ignition.
- Reader report 2024-01-30: "funktioniert überhaupt nicht"; editors say 3 presses sometimes enough and that a
  diagnostic device "funktioniert der Reset selbstverständlich immer". Differs from TSB (five in 10 s).

### F4. GiuliaForums / StelvioForum threads - SINGLE_SOURCE each (search summaries only; pages gated)
- giuliaforums.com/threads/service-interval-reset-mystery.56399/ ; stelvioforum.com/threads/oil-change-interval-reset.11605/ ;
  giuliaforums.com/threads/how-to-reset-service-light.59696/
- Summarised claims: AlfaOBD car configuration has "Service Coupon Number" settable 0-15; one poster changed 10 to
  11 and MES showed the new value. Infotainment next-service reset "needs MES or Alfa OBD software, plus a secure
  gateway bypass for vehicles built after 2018". Pedal method "ONLY turns off" the cluster Oil Change Warning.
  Pedal counts vary (3 vs 5 vs 6).
- These are the best leads for item 2 (infotainment/coupon). Names the AlfaOBD item but gives no module or bytes.
  Dates and posters not verified.

### F5. Multiecuscan forum (via search summary) - SINGLE_SOURCE
- URL (404 on direct fetch): https://multiecuscan.net/forum/viewtopic.php?p=24442
- 2018 Giulia owner: "NEXT SERVICE KM RESET" in MES fails with "FAILED TO EXECUTE", no detail. Indicates MES has a
  function of that name for the platform and it can fail (likely the gateway/security issue in F4). No trace.

### F6. Klavkarr (commercial scanner) - SINGLE_SOURCE, coverage only
- https://www.klavkarr.com/blog/service-reset/6-reset-oil-service-light-alfa-romeo
- Says its tool reaches an "ECU Maintenance Interval" menu with "Reset Maintenance Information" on Alfa models.
  Vendor marketing; no module/bytes; Giulia/Stelvio model-year specificity not verified.

### F7. Forum remark on oil-quality adaptation - SINGLE_SOURCE
Search summary: a reply said resetting the interval is separate from resetting "adaptive parameters of the UniAir
module oil quality monitoring system", needing diagnostics. Not independently verified. Item 3 mechanism: UNKNOWN.

### F8. wiTECH / Mopar - UNKNOWN
No public description of an IPC "Misc Functions Maintenance Reset" for this car was found. Related bulletins show
wiTECH ECM/ECM2 "Misc. Functions" tabs exist (oil level sensor routine on ECM2, per search summary, SINGLE_SOURCE),
which suggests FCA exposes OLM-type routines under ECM/BCM Misc Functions, but this is inference, not evidence.

### F9. GitHub / opendbc / RE projects - none found
Searches ("Giorgio UDS", FCA service interval 0x31, AlfaOBD sniff, CAN trace 2E/31) returned no repository,
trace, or post with a Giulia/Stelvio service-reset request. Alfa Romeo ALSO not covered in the generic UDS pages.

## (a) Table

| Tool | Module | Mechanism | Security needed? | Confidence |
|---|---|---|---|---|
| FCA pedal procedure (TSB 01-001-21) | Unknown (OLM owner, likely ECM/BCM) | Ignition ON, accelerator x5 in 10 s, ignition OFF; no diagnostic request | No (no tool) | CONFIRMED (that it works/clears OLM msg) |
| FCA "scan tool" fallback (wiTECH) | Not stated | Not stated | UNKNOWN | UNKNOWN |
| AlfaOBD | Not stated publicly | "Service Coupon Number" 0-15 config item; reset functions exist | UNKNOWN (forums claim SGW bypass for post-2018 infotainment reset) | SINGLE_SOURCE |
| MultiECUScan | Not stated | "NEXT SERVICE KM RESET" function; user saw FAILED TO EXECUTE | UNKNOWN | SINGLE_SOURCE |
| Klavkarr / EOBD Facile | Not stated | "ECU Maintenance Interval" menu | UNKNOWN | SINGLE_SOURCE (vendor) |
| Launch/Autel/Foxwell/iCarsoft/Carly/Car Scanner | Not found | Coverage not verified for 2018 Giulia/Stelvio | UNKNOWN | UNKNOWN |
| OEM owner manual / cluster menu | - | No evidence of cluster-menu reset | - | UNKNOWN |

## (b) Best candidate sequences
1. Pedal sequence (F1): the only documented, official reset. Known: exact steps and pedal count (5 in 10 s), applies
   to the 2.0T, clears the cluster OLM message. NOT known: which module acts on it; whether it also resets the
   infotainment tracker/coupon (forums say no); whether it fires in the same ignition cycle on all calibrations.
   It requires no diagnostic traffic, so there is nothing for CUORE to send.
2. UDS-level reset: NO candidate. No service ID/DID/routine is public. Do not guess one. Generic UDS (0x2E WriteDataByIdentifier,
   0x31 RoutineControl) appears in standards pages only; routine/DID meanings are OEM-specific.
3. Candidate target modules, for planning only: cluster (IPC) for the displayed message, BCM/ECM for counters, Uconnect head unit for the coupon store.
   All inference.

## (c) Recommendation
A documented UDS sequence does NOT exist in public sources, so there is nothing strong enough to dry-run against
CUORE's gate (no 0x27, allowed services). A capture is still needed. Best route: sniff what AlfaOBD or MES sends for
"NEXT SERVICE KM RESET" / "Service Coupon Number" (passive CAN capture, or MES's own log with the simulation-log
caveat) and check whether it includes 0x27. Meanwhile, if the user only needs the cluster message gone, the FCA pedal
procedure (F1) is the zero-risk documented path; it will not clear the infotainment tracker. Also note the forum claim that
post-2018 builds need the secure gateway handled for infotainment resets - verify against the car's own gateway behaviour.
