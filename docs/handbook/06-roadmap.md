# Roadmap

## Just built (2026-10-07), to settle in

Systems layer (25 systems), Electrical and all-systems physical layout with inspections, Job workflow with hypothesis ledger, MES-style Modules view, Tools page, Timeline, Media (incl. audio), Parts, Feedback and Inbox, printable report and PDFs, others' experience links.

## Next

1. Use it on the Stelvio: open a Job, record the wiTECH flash check and Test A results, tick the EVAP checklist, attach photos and sounds, answer the Inbox.
2. Fill known gaps with sources: EVAP purge and vapour-pressure limits, peak boost, tyre placard pressures, P052E/P04DB, UNKNOWN torques; Grecale and Levante experience links and parts; part images for the remaining 15 parts.
3. Timeline: a media and inspections lane; replay of a recording on the gauges from the timeline.
4. Live: Mode $06 EVAP test values; MIL state from live reads into the timeline; verify-repair flow end to end on the car.
5. Labels: confirm Avery 6576/6578 margins from a print, then mark them verified.
6. Port to Maserati and Ferrari: module maps and DID catalogues keyed by platform, VIN decoding for ZN6/ZN7, spec tables per model, brand accent as a theme variable, experience and parts tables per marque. Keep the Stelvio data as the template.
7. Hygiene: fix `electrical_inspections.latest()` (newest record), the clipped "..." strip button at 400 px, and keep agent tests to 4-5 checks each.

## Mobile companion (decided 2026-10-13)

The phone surface "Tell CUORE" (/m/{vin}) records what the car cannot tell us (fluids, fuel and octane, battery and electrical work, tyres, parts fitted elsewhere, exposure, incidents, driving pattern) as attested records, and carries messages between owner, mechanic and CUORE. Standard: the same prestige as the main app (dark, one statement per screen, pictograms, red for the one action), opening reveal on every open, a fill-up recordable in three taps, a photo of the odometer, oil bottle or pump proposing the fields for the human to confirm (pluggable vision provider, off by default because CUORE runs offline; the Claude provider is an explicit opt-in that sends the photo to Anthropic).

Native app path (owner has an Apple developer account and Xcode): the web page is the reference implementation and the JSON API under /api/owner, /api/vision, /api/media is the contract a Flutter or Swift app talks to. Features that need the phone itself (Location Services for the station, background capture, a "pull up to the pump" shortcut, push for messages) belong to the native app; nothing in the web surface should block that, so all logic stays server-side behind the API and the page keeps no state of its own.
