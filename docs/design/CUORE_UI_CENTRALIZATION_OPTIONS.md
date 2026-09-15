# Centralizing the cuore interface

**Date:** 2026-09-15
**Status:** options for review, nothing built yet.
**Scope:** the server-rendered bench UI in `cuore/web/` (15 templates, `cuore/web/routes.py`, `cuore/web/static/cuore.css` and `cuore.js`) plus how it does and does not connect to `cuore/live/`.

## Where it stands

cuore is two apps sharing one nav bar. The corpus side reads MES's log history for a VIN: vehicle picker, dossier, code history, fault tree, the evidence gate, a static module registry, recordings, raw logs. The live side reads the car right now: adapter status, cable declaration, per-bus verification, live DTC and identity reads. Both are well built on their own terms — the same bridge discipline, the same JSON API underneath, the same "no scripting required" rule. They just don't know about each other.

| Domain | Pages | Scoped to | Data source |
|---|---|---|---|
| History | `/`, `/v/{vin}`, `/v/{vin}/codes`, `/v/{vin}/code/{code}`, `/v/{vin}/tree`, `/v/{vin}/gate`, `/modules`, `/recordings`, `/logs` | one VIN, or the whole corpus | `mes` library, over `services/mes_bridge.py` |
| Live | `/live`, `/live/module/{code}` | the adapter, not a VIN, until a live read happens to set one | `cuore.live`, over `api/live.py` and `ops.py` |

## Four gaps

**1. The evidence gate cannot cite the live link.** Phase 0 added `type: "live"` citations and an observation store specifically so a live DTC or DID read could verify a diagnosis (`mes/live_obs.py`, `mes/verdict.py`). The gate form (`gate.html`) still offers only `actuator`, `freeze_frame`, `parameter`, `recording_event` and `manual` — the one feature built for exactly this page has no way in except hand-typing JSON. This is the most valuable gap and the cheapest to close.

**2. Two module tables describe the same parts and never meet.** `/modules` is the static 126-entry registry: domain, tier, aliases, the CTM collision fix. `/live` carries its own 14-entry table: bus, 29-bit address, confidence, hazard notes. A tech looking up ABS on the reference page has no link to "read it live"; a tech reading it live has no link to its aliases or tier.

**3. Live has no vehicle.** Every history page is `/v/{vin}/...`. `/live` is VIN-less: it only learns a VIN when a live read happens to return one, and that fact goes nowhere — the dossier for that same VIN has no idea a live session is even open.

**4. Live state is invisible everywhere except `/live`.** Whether MES holds the adapter, which cable is declared, which bus is verified — these matter on the gate page (can I even go get a live citation right now?) and on the dossier, but they only render on one page in the whole app.

## Options

### Option 1 — Wire the gate to the live link
**Small. No new pages, no schema change, no architecture risk.**

- Add "live" as a fifth choice on the gate form. Given a code and a module, call `live_obs.verify_live` / `ops.observations()` directly and drop the result in as a citation, instead of asking the tech to hand-type a JSON measurement.
- Cross-link `/modules` rows to `/live/module/{code}` and back, for the 14 codes that exist in both tables.
- Add a one-line status strip — MES state, declared cable, adapter present — as a small template partial rendered from `base.html`, so it shows on every page instead of only `/live`.

Touches: `gate.html` + its route, `modules.html`, `live.html` (a small "seen in the registry" link), `base.html`, one new partial calling `live_ops.status()`.

### Option 2 — One vehicle, one context
**Medium. This is the actual centralizing move.**

- An active-vehicle concept: a cookie or a `?vin=` carried across the live routes, so a live DTC or identity read auto-tags the VIN instead of it only being known after the fact. The dossier (`/v/{vin}`) gains an embedded "Live" panel: cable and bus state, a Verify button, and the live module table filtered to modules on this platform.
- Merge the two module views into one page with a toggle between "reference" (the full registry) and "live" (bus, address, confidence) over one shared table shell, instead of two separate designs for the same subject.
- Regroup the nav into two labeled clusters instead of six flat links — **History** (Vehicles, Codes, Modules, Recordings, Logs) and **Live** (Link, Modules, Discover) — so the seam between the two apps is shown, not hidden.

Touches: `routes.py` (a small session helper), `vehicle.html`, `modules.html` + `live.html` merged, `base.html` nav markup.

### Option 3 — A bench home screen
**Larger. Worth it once Option 2's active-vehicle concept exists to feed it.**

- Replace the vehicle-picker-only `/` with a real landing page: corpus health next to adapter/cable/bus state and the most recent live observations, vehicle picker below. One page that answers "what's plugged in, what did it just say, which car" the moment cuore opens at the bench.
- Optional: a light auto-refresh on that one page only (a meta-refresh or a small polling script), still fully functional with scripting off since the page works the same on a manual reload.

Touches: `index.html`, `routes.py` `index()`, a small aggregator function next to `ops.observations()`.

## Recommendation

Do Option 1 now — it costs almost nothing and closes a real functional gap: the gate cannot use the feature that was just built for it. Do Option 2 next, once there has been a real bench session to learn from; it is the difference between "two apps" and "one app." Treat Option 3 as a later nice-to-have that Option 2 makes easy.
