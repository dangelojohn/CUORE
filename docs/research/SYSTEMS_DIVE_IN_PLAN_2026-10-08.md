# Systems map: dive-in plan (2026-10-08)

Owner's brief: the Systems map is excellent for diving into each cell and seeing the relationships between systems and their technical details. Make the dive deeper, let it lead the mechanic into new areas of CUORE, and let him add, discover and interact with real-time errors.

Today each cell is an anchor on one long page: label, components, dependencies (why / confidence / source), co-occurrence from this car's history, a live-channel band. Electrical layout, fault trees, tests, parts, others' experience and the hypothesis ledger exist but are not reachable from the cell. The change: the cell becomes the hub of everything CUORE knows about that system, on this car, right now. All of it is joins on existing data (25 system ids are already the taxonomy for hypotheses, codes, tests, electrical elements).

## Phase 1: a real system page, /v/{vin}/systems/{key} (in progress)
1. Status strip: codes mapped to the system with state (active / cleared-unverified / stale), monitor readiness, latest live values with the Live board colour grade, active blocker, "Last evidence from the car: <time>".
2. Relationship ring: one-hop upstream and downstream dependencies with why, confidence, source; electrical-supply vs functional edges; hot edges where both systems fired in the same session on this car, carrying the lift value, worded "seen together on this car", never "depends on".
3. Components, placed: component list merged with the placed electrical elements (location, harness, connector, ground, conditions), part link and image, wiring path per open code, latest inspection record.
4. How it fails here: fault-tree branches for the open codes, next unresolved test highlighted, "Do it now ->" into the Tests surface row.
5. Hypotheses touching this system, with evidence counts; "+ Add hypothesis" pre-filled with system and codes.
6. What this car has taught: timeline filtered to the system (codes, clears, repairs, parts, tests, notes, media) and case memory ("on the last Stelvio with these codes in this system", never "proven").
7. Others' experience for the system, ranked by importance.
8. "What else should I look at?": top 3 neighbours ranked by dependency confidence x co-occurrence lift x unverified items, each with a one-line why.
Every block keeps the feedback affordance (correct / ask / confirm); every UNKNOWN is an open marker ("use the service manual, TechAuthority").

## Phase 2: the map says something about this car
- Cells coloured by state (red active, amber cleared-unverified, grey stale, dim no data, green verified clean) with an open-code count badge.
- Hot edges drawn thick with the lift value (the network/EVAP 6-of-18 finding becomes visible).
- Session time slider under the map: drag through the sessions and watch which cells light together (the 28 Sep chassis-bus event, quiet on 29 Sep).

## Phase 3: discovery and adding
- Unknown markers on every page: UNKNOWN spec, unverified image, missing source; filling one records an attested input with date and author, never a car measurement.
- Inspection from the cell: tap a placed element to record condition, photo, note.
- Learned DIDs: module DIDs that correlate with the system's channels (obd2 learn_capture / learn_correlate), "watch on Live board" to grow the channel set per system.

## Phase 4: real-time errors
- Live overlay toggle: cells pulse the colour grade of their worst live channel; Snapshot captures the map state as freeze-frame evidence.
- A DTC from the live poller lands on its cell within one poll: chip, red cell, suggested hypothesis card, next test updated, Bench next-action regenerated so the three surfaces agree.
- Freeze frame shown on the system page with the system's channels highlighted.

## Correctness points
- Distinguish electrical-supply edges from functional edges: different diagnostic moves.
- Every edge keeps source and confidence; co-occurrence-only edges are "seen together on this car".
