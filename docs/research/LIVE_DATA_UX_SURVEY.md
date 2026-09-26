# Live Data UX Survey — OBD-II / Diagnostic Apps

Feature survey only — no purchase recommendations. Goal: inform cuore's live-data
dashboard (FastAPI server, server-rendered pages, values streamed to the browser,
no CDN at runtime, tablets in the shop, later an in-car node).

## Per-app notes

**Torque Pro / Torque Lite** (Android; [Play Store](https://play.google.com/store/apps/details?id=org.prowl.torque), [forum](https://torque-bhp.com/)) — the de-facto reference UX. Dashboard is a free-form canvas: long-press to "Add Display", pick a gauge type (analog dial, digital, bar/linear, min/max needle) bound to any PID, then "Display Configuration" sets size, position, min/max, high/low warning bands ([OneGauge setup guide](https://www.theonegauge.com/knowledge-base/torque-pro-setup/)). Multiple dashboard pages, swipe between them; **HUD mode** mirrors big digits for windshield reflection at night. Custom PIDs use a compact algebra: raw bytes are named **A, B, C…** in request order (`A`=first byte 0–255, `A*256+B` for two-byte values), then an equation like `(A*256+B)/4` or `(A*(-0.415))+56.2` for AFR ([Torque custom PID guide](https://torqueproapk.org/torque-pro-custom-pid-list/), [forum example](https://www.insightcentral.net/threads/pid-and-formula-for-air-fuel-ratio-for-torque-pro.102937/)). Logging writes CSV/KML with GPS timestamp, optional "log only while connected" and log-rotation; a companion plugin ("Realtime Charts for Torque") adds up to 100 saved multi-trace charts, 8 PIDs each ([plugin page](https://apprecs.com/android/com.pjt.realtimecharts_v1/realtime-charts-for-torque-pro)). Includes GPS 0-60/quarter-mile timers, dyno (HP/torque vs time), fuel-cost/MPG. Torque Lite is free/ad-supported with basic gauges and code read/clear only — no custom PIDs, no advanced logging, effectively unmaintained since 2018 ([comparison](https://medium.com/@torqueproapk1/torque-lite-vs-torque-pro-torque-pro-app-obd2-2021-review-7c74394f7790)).

**Car Scanner ELM OBD2** ([Play Store](https://play.google.com/store/apps/details/car_scanner_elm_obd2?id=com.ovz.carscanner)) — similarly free-form dashboard with gauges + line charts side by side, plus extended/manufacturer PID support with a formula editor. Its own docs give the clearest *performance* guidance of any app surveyed: reading fewer PIDs at once is the single biggest speed factor; a "request optimization" setting for CAN 11-bit/29-bit vehicles batches multiple PID requests into fewer bus transactions ("up to 6x" faster); ELM327 `ATST` timeout tuning trades speed for reliability; and querying one ECU at a time avoids per-request module-reselection overhead ([Optimizing connection speed](https://www.carscanner.info/optimizing-connection-speed/)).

**OBD Fusion** ([site](https://www.obdsoftware.net/software/obdfusion), [OBDLink write-up](https://obdlink.nl/en/obd-apps/obd-fusion)) — multiple dashboard *screens*, gauge styles (dial, digital, bar), per-gauge size/color/needle-depth styling, built-in and user-saved gauge templates, and a desktop companion to design dashboards and transfer them to the phone (an early "shareable layout" pattern). Explicitly documents a UX tradeoff: minimal lag up to ~4 gauges per screen; refresh rate degrades past that. Data logging to CSV with playback in the same dashboard/grid views.

**DashCommand** ([manual PDF](https://www.palmerperformance.com/download/docs/DashCommand_User_Manual.pdf), [product page](https://www.palmerperformance.com/products/dashcommand/)) — organizes gauge layouts into "Skin Sets" (swappable full-screen dashboards), plus specialty screens: G-force skidpad with min/max hold, GPS race-track map overlaying accel/braking, and an inclinometer (pitch/roll) for off-road use. Data logging records straight from the dashboard or a spreadsheet-like grid view, with the same view used for played-back logs — one UI serves both live and replay.

**Infocar** ([Play Store](https://play.google.com/store/apps/details?id=mureung.obdproject)) — large PID catalog (vendor claims 800+ generic, 2,000+ manufacturer-specific) graphed live; HUD mode for speed/RPM/trip; a driving-record/scorecard layer (harsh accel/braking, speeding) overlaid on a map — live data feeding into a *behavior* summary rather than only instantaneous gauges.

**OBDLink app** ([support docs](https://support.obdlink.com/support/solutions/folders/43000596169), [gauge editing](https://support.obdlink.com/support/solutions/articles/43000678883-add-and-edit-dashboard-gauges)) — reorderable multiple dashboards (e.g., per vehicle), press-and-hold "Edit Display" for size/location, and a "Logs" view that graphs up to 4 live parameters at once — an explicit UI ceiling on simultaneous trace count for readability.

**OBD Auto Doctor** ([Features](https://www.obdautodoctor.com/features/), [graph blog](https://www.obdautodoctor.com/blog/obd2-data-presented-as-graph/)) — a "Sensor Graph"/oscilloscope view is the headline live-data feature, explicitly framed for catching *fast transients* a numeric readout would miss; shows current/min/avg/max simultaneously; exports to CSV for Excel/Sheets and can save graph images to share with a mechanic — a "send a picture of the fault" workflow distinct from raw log-file sharing. ~126 PIDs supported.

**Carista** (live-data-relevant only; [site](https://carista.com/en-us)) — narrower PID set curated per make/model rather than a generic OBD-II sweep, and doubles as a CarPlay/Android Auto live-data screen for glanceable readouts while driving ([CarPlay blog](https://carista.com/en-us/blogs/news/how-to-use-carista-on-carplay-android-auto)) — relevant to cuore's "driving use" accessibility goal even without dashboard customization depth.

**RealDash** ([FAQ](https://realdash.net/faq.php), [gallery](https://realdash.net/gallery.php)) — the outlier: fully skinnable "Pixel Perfect" dashboards (community gallery of downloadable skins/gizmos), CAN-bus raw-frame decoding via an XML "CAN description file" defining byte offsets/scaling per signal (a config-driven channel model, not app-hardcoded PIDs), and a **Trigger → Action** system (condition on any channel → visual effect, alarm, or external action) generalizing "alarms" into arbitrary rules ([CAN description format](https://github.com/janimm/RealDash-extras/blob/master/RealDash-CAN/realdash-can-description-file.md)).

**MultiEcuScan** (installed locally; workflow already used by cuore's toolchain) — Parameters tab selects channels; Graph tab plots them live and drives CSV recording; up to 4 graphs × 10 parameters, per-graph sample rate; a "Monitor DTCs" toggle polls and stamps DTC transitions into the CSV `TAG` column during a recording, and min/max are tracked live alongside the recording ([forum: graphing](https://www.multiecuscan.net/forum/viewtopic.php?t=4071), [forum: DTC monitoring](https://www.multiecuscan.net/forum/viewtopic.php?t=8907)). This CSV shape is the one `docs/format/CSV_LOG_FORMAT.md` documents and cuore should stay wire-compatible with.

**AlfaOBD** ([help PDF](https://www.alfaobd.com/AlfaOBD_Help.pdf)) — per-ECU "dynamic" parameter lists (engine/gearbox/ABS/climate) shown as live plots; parameters are toggled on/off individually by click/double-click rather than laid out on a fixed dashboard — a lighter-weight list-driven live view, closer to a diagnostic tool than a dashboard product.

## Cross-cutting patterns

- **Widgets**: analog dial, digital numeric, linear/bar gauge, single and multi-trace line graphs, oscilloscope-style fast graph (Auto Doctor), G-force/scatter (DashCommand), GPS map overlay (DashCommand, Infocar), tables/grids (DashCommand, MES Parameters tab), HUD mirrored digits (Torque, Infocar).
- **Layout**: free-form/drag-and-drop placement is standard (Torque, Car Scanner, OBDLink); OBD Fusion and DashCommand use discrete named "screens/skins" instead of one infinite canvas; RealDash pushes furthest into fully custom, shareable skins.
- **Custom channels**: Torque's `A/B/C` byte-algebra is the most copied convention; RealDash's XML CAN description file is the most structured (per-signal byte offset, length, scale, offset, unit).
- **Rate/priority**: no app exposes true per-PID priority scheduling to the user — the common mitigation is simply *fewer simultaneous PIDs*, request batching for CAN (Car Scanner), and hard UI caps on simultaneous graph traces (OBDLink: 4).
- **Alarms**: threshold-based high/low bands tied to gauge color zones (Torque, OBD Fusion); RealDash generalizes to a trigger→action rule engine.
- **Logging**: CSV is the universal export format; GPS-stamped CSV/KML (Torque), CSV with DTC-tagging (MES), CSV replay in the same view used live (DashCommand, Auto Doctor).
- **Computed values**: fuel economy (Torque, Infocar), boost-from-MAP-minus-baro and HP/torque dyno curves and 0-60/quarter-mile timers (Torque).
- **Freeze-frame/snapshot**: min/max/avg alongside live value (Auto Doctor, MES); shareable graph screenshots (Auto Doctor).
- **Glanceability for driving**: CarPlay/Android Auto live tiles (Carista), HUD mirrored large digits (Torque, Infocar) — both are about reading values without looking down.

## What cuore should implement

cuore already streams live values server-side (`cuore/live/stream.py`) to server-rendered pages with no CDN dependency, so widgets must be vanilla SVG/Canvas + JS. The recording format should stay a superset of the existing MES CSV convention (`docs/format/CSV_LOG_FORMAT.md`: row 1 = names, row 2 = units, col 1 = `Time` seconds, last col = `TAG`) so `mes-log-mcp`'s `read_recording`/`recording_series`/`recording_events` tools work unmodified against cuore's own logs.

### MVP
- Widgets: digital readout, linear/bar gauge, analog dial (SVG), single-trace line graph. Grid-based layout (CSS grid, not free drag) with per-widget size (1×1/2×1/2×2 cells).
- One dashboard page per "job" (see presets below), tab strip to switch pages.
- Channel types: standard PID, UDS DID with a formula string (reuse Torque's `A/B/C` byte-name convention — simplest to implement and to explain to a mechanic who already knows Torque).
- Warn/alarm zones drawn as colored arcs/bands on gauges (green/yellow/red), no sound yet.
- CSV recording in the MES-compatible shape (UTF-8, tab-separated is fine — the existing parser already sniffs delimiter/encoding), with an optional "monitor DTCs" toggle that writes DTC transitions into `TAG`, matching MultiEcuScan's convention.
- Fixed refresh scheduling: one poll loop, round-robin all active channels — acceptable for ≤6 channels per page (matches the OBDLink 4-trace / OBD Fusion 4-gauge lag thresholds found in this survey).

### Next
- Multi-trace graphs (2–4 series/graph, MES's own "4 graphs × 10 params" ceiling as inspiration for how many to allow).
- Priority tiers for scheduling: "fast" (RPM, boost, MAP — target ~5–10 Hz) vs "slow" (coolant temp, fuel level — 1 Hz), so a page with 8 channels doesn't average down to Car Scanner's single-shared-rate problem; batch same-ECU requests per Car Scanner's guidance.
- Audible/visual alarms using the browser's native `Audio`/Web Audio (a synthesized beep, no CDN asset needed) and `SpeechSynthesisUtterance` (built into the browser, no CDN) for a spoken "boost over target" — safe to use since both are native browser APIs, not external services.
- Computed channels: boost = MAP − baro, fuel trim deltas, simple fuel economy from MAF/speed.
- Freeze-frame/snapshot button that captures current values of every widget on the active page into one row, independent of a running recording (mirrors Auto Doctor's min/avg/max-alongside-live).
- Portrait/landscape-aware grid reflow for tablets.
- Layout export/import as JSON so a dashboard built on one tablet can be copied to another (RealDash's shareable-skin idea, without needing a gallery/server).

### Later
- Drag-and-drop free-form layout as an alternative to the grid, with per-widget color/theme overrides.
- Scatter/XY plot (e.g., MAP vs RPM) and GPS/map overlay widget for the in-car node.
- HUD mode: large-digit mirrored view for a windshield-mounted tablet.
- CAN-description-style config file (RealDash-inspired) so a new DID/PID can be added to a preset by editing JSON, not code.
- Replay mode that re-plays a CSV recording through the same widgets used live (DashCommand/Auto Doctor pattern), reusing `mes-log-mcp`'s `recording_series`/`recording_snapshot`.
- Trigger → action rules generalizing alarms (RealDash) — e.g., auto-start a recording when a DTC sets.

### Layout schema sketch

```json
{
  "pages": [
    {
      "id": "boost_turbo",
      "title": "Boost / Turbo",
      "layout": "grid",
      "widgets": [
        {
          "id": "w1",
          "channel": "map_kpa",
          "type": "dial",
          "unit": "kPa",
          "min": 0, "max": 250,
          "warn": [180, 210],
          "alarm": [210, 250],
          "size": [2, 2]
        },
        {
          "id": "w2",
          "channel": "boost_computed",
          "type": "bar",
          "unit": "psi",
          "min": -10, "max": 25,
          "warn": [20, 22],
          "alarm": [22, 25],
          "size": [1, 2]
        }
      ]
    }
  ]
}
```

### Channel model

```json
{
  "id": "trans_temp",
  "source": "uds_did",
  "module": "TCM",
  "did": "04FE",
  "formula": "A - 40",
  "unit": "°C"
}
```
Three source kinds: `obd_pid` (standard mode 01), `uds_did` (module + DID + `A/B/C…` formula string), and `computed` (expression over other channel ids, e.g. `map_kpa - baro_kpa`).

### 2018 Stelvio 2.0T built-in presets
- **Engine basics**: RPM, speed, coolant temp, throttle position, engine load.
- **Boost/turbo**: MAP, barometric pressure, computed boost (MAP − baro), intake air temp.
- **EVAP job** (per `docs/reference/EVAP_STELVIO.md`): purge duty PID `2E`, fuel level PID `2F`, EVAP vapor pressure PID `32`/`53`.
- **Transmission**: TCM DID `04FE` (trans fluid temp).
- **TPMS**: RFHUB DIDs `40B1`–`40B4`, one dial per wheel plus a simple 4-tile layout.

## 200-word summary

Reviewed Play Store/App Store listings, official docs, and forums for Torque Pro/Lite, Car Scanner ELM OBD2, OBD Fusion, DashCommand, Infocar, the OBDLink app, OBD Auto Doctor, Carista, RealDash, MultiEcuScan, and AlfaOBD. Common ground: free-form or grid dashboards with dial/digital/bar/graph widgets, per-widget min/max and warning-color zones, CSV logging/export, and a custom-PID formula layer — Torque's byte-named `A/B/C` algebra is the most widely copied convention; RealDash instead uses a structured CAN-description file. No app does real per-channel rate prioritization; the shared mitigation is simply capping simultaneous PIDs/graphs (OBDLink caps live graphs at 4) and, for CAN vehicles, batching requests (Car Scanner). MultiEcuScan's Parameters/Graph/CSV/"Monitor DTCs" workflow is the direct model for cuore, whose recordings should stay wire-compatible with the existing `CSV_LOG_FORMAT.md` so `mes-log-mcp` tools keep working. Recommended cuore build order: MVP (grid layout, four core widgets, PID/DID/computed channels, alarm zones, MES-compatible CSV); next (multi-trace graphs, tiered refresh scheduling, native-browser alarms/speech, computed boost/economy, freeze-frame, JSON layout export); later (free drag-drop, scatter/GPS widgets, HUD mode, replay, trigger→action rules) — plus five built-in Stelvio 2.0T presets covering engine, boost, EVAP, transmission, and TPMS.
