# Roadmap

## Done

- Systems layer (25 systems), Electrical and all-systems physical layout with inspections, Job workflow with hypothesis ledger, MES-style Modules view, Tools page, Timeline, Media (incl. audio), Parts, Feedback and Inbox, printable report and PDFs, others' experience links (2026-10-07).
- Tests surface (platform-wide mechanic test catalogue, sourced pass criteria) and Systems dive-in phase 1 (`/v/{vin}/systems/{key}`: status, relationship ring, fault tree, this car's history) (2026-10-08).
- Systems map overlay phases 2-4: colour state, hot edges, session time slider, live overlay (`/api/systems/{vin}/state`, `/live`) (2026-10-08/13).
- Case memory: closing a Job records a Case; `cases.match`/`cases.prefill` rank real cases above the seed data and feed Job prefill (2026-10-13).
- Marque port: `data-marque` computed per-request from the VIN (`marque_for_vin`), model-specific wording in the knowledge tables, Maserati fixture test (2026-10-13).
- Tell CUORE mobile (`/m/{vin}`) rebuilt to the Ferrari benchmark: dark, intro reveal every open, 4 quick actions, 3-tap fill-up, camera + Snap & fill on every form; mobile API contract documented for a future native app (2026-10-13).
- Live link: first real reads from the car -- active-probe fix for the gateway-silent bus, the 29-bit legislated route, the STFAC filter-reset fix (see 05-methods-and-gotchas.md); full-scan orchestrator, Scans log area with diff/export, scan health report generator, Live board freeze-frame panel, Test A in the Tests catalogue (2026-10-13).
- Perf: workup/flow-state results shared across Report/Job/Tests/Timeline via one cache key (Report 30 s -> 5 s, Job 3.2 s -> 0.3 s) (2026-10-13).

## Next

1. First guided scan with the cables in hand: run the `/coverage` wizard (and a full scan) on the real Stelvio, not a temp-state server, now that the live link actually works on this car.
2. Test A (hand vacuum on the ESIM while watching the switch PID), now that Mode $06 has shown the first direct measurement behind the chronic P0440/P0455 (0.090" leak test FAILED, 404 ms vs a 3965 ms minimum) -- then the wiTECH flash comparison. Do not clear codes first.
3. UDS DID definitions from TechAuthority: the module sweep found live codes and module identities but several DIDs are still read raw/UNKNOWN (no decoder in the registry); get real TechAuthority values in rather than guessing.
4. Native app: the owner has an Apple developer account and Xcode; `/m/{vin}` and `docs/mobile/API_CONTRACT.md` are the reference implementation and contract -- Location Services, a pump shortcut and push belong to the native app, not the web page.
5. Fill known gaps with sources: EVAP purge and vapour-pressure limits, peak boost, tyre placard pressures, P052E/P04DB, UNKNOWN torques; Grecale and Levante experience links and parts; part images for the remaining 15 parts.
6. Timeline: a media and inspections lane; replay of a recording on the gauges from the timeline.
7. Labels: confirm Avery 6576/6578 margins from a print, then mark them verified.
8. Port to Maserati and Ferrari: module maps and DID catalogues keyed by platform, VIN decoding for ZN6/ZN7, spec tables per model, experience and parts tables per marque (the theme variable and VIN-based marque detection are now built; data population is what's left). Keep the Stelvio data as the template.
9. Hygiene: fix `electrical_inspections.latest()` (newest record), the clipped "..." strip button at 400 px, and keep agent tests to 4-5 checks each.
10. Still on the owner (unchanged from the 2026-10-13 session record): readiness read in the 15-85% fuel window (now done once, repeat for any re-test), wiTECH flash check, recalls, service ledger entries (odometer, oil, filter, technician).

## Mobile companion (decided 2026-10-13)

The phone surface "Tell CUORE" (/m/{vin}) records what the car cannot tell us (fluids, fuel and octane, battery and electrical work, tyres, parts fitted elsewhere, exposure, incidents, driving pattern) as attested records, and carries messages between owner, mechanic and CUORE. Standard: the same prestige as the main app (dark, one statement per screen, pictograms, red for the one action), opening reveal on every open, a fill-up recordable in three taps, a photo of the odometer, oil bottle or pump proposing the fields for the human to confirm (pluggable vision provider, off by default because CUORE runs offline; the Claude provider is an explicit opt-in that sends the photo to Anthropic).

Native app path (owner has an Apple developer account and Xcode): the web page is the reference implementation and the JSON API under /api/owner, /api/vision, /api/media is the contract a Flutter or Swift app talks to. Features that need the phone itself (Location Services for the station, background capture, a "pull up to the pump" shortcut, push for messages) belong to the native app; nothing in the web surface should block that, so all logic stays server-side behind the API and the page keeps no state of its own.
