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
- Modifications layer: paddle-shift NA↔EU catalogue, per-car ledger, MES handoff cards, capability matrix; separated from diagnostics (2026-10-14).
- Connect to car: adapter → bus → VIN → guided full scan inline (2026-10-14).
- Review 5/6 fixes: mechanic wording, diff labels, dedup, mobile UX, cable pictogram; typography audit foundation pass (2026-10-14).

## Next (2026-10-14)

1. First guided scan with cables in hand: run `/coverage` wizard + full scan on the real Stelvio (not temp-state), now that live link works and owner's rules are set.
2. Test A (hand vacuum on ESIM while watching switch PID) + ESIM commanded test (post-mode 06 0.090" FAIL measurement, 404 ms vs 3965 ms min). Do not clear codes.
3. wiTECH flash check and baseline comparison (TSB 18-030-17 Rev. B, ECM software P235QB39/52170619).
4. Firewall rule + pre-push hook install (owner approval required; Windows Firewall TCP 5000 rule documented in session 2026-10-13).
5. TechAuthority DID definitions: module sweep (ECM/TCM/BCM/IPC/RFHUB) found 25 decoded PIDs, several still raw/UNKNOWN; get real values from TechAuthority rather than guessing.
6. Native app: owner has Apple developer account and Xcode; `/m/{vin}` and `docs/mobile/API_CONTRACT.md` are the reference implementation and contract (Location Services, pump shortcut, push belong to native app, not web).
7. Fill known gaps: EVAP purge/vapour-pressure limits, peak boost, tyre placard pressures, P052E/P04DB, UNKNOWN torques; Grecale and Levante experience links and parts; part images for 15 remaining parts.
8. Timeline: media and inspections lane; replay recording on gauges.
9. Labels: confirm Avery 6576/6578 margins from print; mark verified.
10. Port to Maserati and Ferrari: module maps/DID catalogues per platform, VIN decode ZN6/ZN7, spec/experience/parts tables per marque. Keep Stelvio as template.
11. Hygiene: fix `electrical_inspections.latest()`, clipped "..." button at 400 px, keep agent tests to 4-5 checks each.
12. Owner's responsibilities (unchanged from 2026-10-13): readiness read in 15-85% fuel window (repeat for any re-test), recalls, service ledger entries (odometer, oil, filter, technician).

## Mobile companion (decided 2026-10-13)

The phone surface "Tell CUORE" (/m/{vin}) records what the car cannot tell us (fluids, fuel and octane, battery and electrical work, tyres, parts fitted elsewhere, exposure, incidents, driving pattern) as attested records, and carries messages between owner, mechanic and CUORE. Standard: the same prestige as the main app (dark, one statement per screen, pictograms, red for the one action), opening reveal on every open, a fill-up recordable in three taps, a photo of the odometer, oil bottle or pump proposing the fields for the human to confirm (pluggable vision provider, off by default because CUORE runs offline; the Claude provider is an explicit opt-in that sends the photo to Anthropic).

Native app path (owner has an Apple developer account and Xcode): the web page is the reference implementation and the JSON API under /api/owner, /api/vision, /api/media is the contract a Flutter or Swift app talks to. Features that need the phone itself (Location Services for the station, background capture, a "pull up to the pump" shortcut, push for messages) belong to the native app; nothing in the web surface should block that, so all logic stays server-side behind the API and the page keeps no state of its own.
