# CUORE interactive procedures: design for bi-directional features

**Date:** 2026-10-26. **Status:** design for owner review - nothing here sends a command to
the car until the owner approves it and each procedure passes the safety gate.
**Scope:** every feature where CUORE changes something on the Stelvio: actuator tests
(ESIM vent, purge valve...), resets (service interval, oil), code clears. PROXI alignment,
battery registration and coding stay in MES (`CUORE_ADJUSTMENTS_PLAN.md`).
**Evidence behind it:** `docs/design/CUORE_WRITE_CAPABILITY_PLAN.md`,
`CUORE_ADJUSTMENTS_PLAN.md`, `MES_LEARN_FIRST_SESSION.md`, the MES interface/procedure
research (MES strings, real FES logs, CUORE's actuate/clear/safety code) and the
2026-10-14 airbag-lamp lesson (note 82b3090e1a85).

---

## 1. The idea in one paragraph

MES is a **remote control**: pick a module, pick a function, press Execute, read one result
word. CUORE should be a **co-pilot**: it already knows *why* the test matters (the job),
it can *see* whether the car is ready (live readings), it can *watch* the test happen (the
readings that prove it), and it can *remember* what happened (evidence on the job). The
mechanic's hands do one thing - a deliberate press - and their eyes stay on the car.

## 2. Design principles (my own, in priority order)

1. **The car answers, not the mechanic.** Every precondition CUORE can read, it reads
   (ignition, engine state, RPM, speed, gear, battery voltage, cable, MES holding the
   adapter, fuel level). The mechanic is only asked what CUORE truly cannot see
   ("Is anyone under the car?", "Hood open, hands clear of the fan?").
2. **One deliberate action, no typing.** Greasy hands and a noisy bay: a **press-and-hold
   button (2 s, with a filling ring and a buzz)** replaces typing a consent phrase. The
   typed phrase becomes a server-side, one-time **token** that the hold releases - the
   safety stays, the friction goes.
3. **STOP is always the biggest thing on screen** from the moment a command is sent until
   control is confirmed returned. It works without JavaScript (plain form POST), and a
   lost connection, a closed tab or a reload also stops the procedure (server-side).
4. **Show the proof while it happens.** Every procedure declares the readings that prove it
   worked (ESIM vent: EVAP vapour pressure moves; purge: commanded purge + MAP/trim
   response). They are shown live, large, with the expected direction.
5. **The car is watched for anything wrong.** If a guard condition changes mid-run (engine
   starts or stalls, speed > 0, voltage drops, a new DTC, a lamp the mechanic reports), CUORE
   stops automatically and says why in one line.
6. **Read before, save, change, read back.** For resets: the "before" values are read and
   saved to the job automatically; the result shows before -> after side by side (the way
   the real 10-23 service reset changed 10268 -> 16000 km and 324 -> 365 days).
7. **One result word, then evidence.** WORKED / DIDN'T / UNCLEAR, with the one line that
   explains it, then the evidence card already attached to the job and the hypothesis.
   MES prints COMPLETED even when nothing visibly changed; CUORE distinguishes "the module
   accepted it" from "the car did it".
8. **Never a dead end.** Every blocked state names the unblock step and links to it
   ("MES is holding the adapter - close MES", "Fit the blue A5 cable - Verify").
9. **Familiar navigation.** Mechanics know MES's shape: module -> tabs. CUORE keeps that
   shape (below) so nothing feels foreign, and adds the "why" layer on top.
10. **Same template for every procedure.** Learn it once, use it for all.

## 3. Where procedures live (borrowing MES's shape)

- **From the job (main path):** the Job page's "Next test -> Do it now" opens the
  procedure already filled in for that hypothesis. This is the path a mechanic uses 90 % of
  the time.
- **From the module (MES-style path):** Modules -> a module -> tabs **Info / Faults /
  Live / Tests / Resets / History**, mirroring MES's Info / Errors / Parameters /
  Actuators / Adjustments / Log. The Tests and Resets tabs list that module's procedures,
  each with a status chip: **Ready** (learned + gated), **MES only** (with the MES menu
  path, as a handoff card), **Needs owner decision** (e.g. an interlock conflict),
  **Not learned yet**.
- **From the call:** a page's call can link straight to a procedure ("Run the ESIM vent
  test now").

## 4. The procedure screen (one template)

```
+---------------------------------------------------------------+
| ESIM vent test                       Engine ECM | CAN-C        |
| WHY: proves the EVAP vent path for job 76d3... (P0440/P0456)   |
+---------------------------------------------------------------+
| 1 READY?  (CUORE checks these itself)                          |
|   [ok] Ignition on        [ok] Engine running, idle            |
|   [ok] Stationary, in P   [ok] Battery 13.9 V                  |
|   [!!] MES holding adapter -> Close MES             [Re-check] |
|   Ask: Hood open, hands clear of the fan?   [Yes]              |
+---------------------------------------------------------------+
| 2 BEFORE (saved to the job): EVAP vapour pressure 0.05 kPa ... |
+---------------------------------------------------------------+
| 3          ((  HOLD 2 s TO START  ))                           |
+---------------------------------------------------------------+
```

While running:

```
+---------------------------------------------------------------+
|  RUNNING 0:07 / 0:30          [        S T O P        ]       |
|  EVAP vapour pressure   0.05 -> -0.42 kPa   expected: falls   |
|  RPM 780 (guard)   Speed 0 (guard)   Voltage 13.8 V (guard)    |
+---------------------------------------------------------------+
```

After:

```
+---------------------------------------------------------------+
|  WORKED  - vapour pressure fell 0.47 kPa while venting         |
|  Before -> After table | Audit (requests/replies) | New codes: none |
|  Saved to job 76d3... as evidence FOR "vent path OK"           |
|  [Run again]   [Back to the job]                               |
+---------------------------------------------------------------+
```

States and words are always label + colour (never colour alone); 44 px targets, 16 px
minimum, high contrast in light and dark; usable at arm's length on the bay tablet.

## 5. Safety built into the interaction

- **Only gated procedures get a Start button.** A procedure must have been learned from
  MES and passed `procedure_capture.gate()` (no 0x27, allowed services only, confirmed
  module and bitrate, explicit stop step, recorded conditions). Everything else shows the
  MES handoff card.
- **Interlocks are visible, not hidden.** The engine-off interlock of `run_actuator` and a
  procedure's MES conditions are shown together; a conflict (ESIM vent needs engine
  running) is a clear "Needs owner decision" state, never a silent refusal - and never
  loosened without the owner's written decision.
- **Server owns the stop.** The server sends the stop/return-control step on STOP, on
  timeout (max 30 s), on any guard breach, and when the client disconnects. If return of
  control cannot be confirmed: one line, "Switch the ignition off now".
- **Cable and bus discipline.** CAN-C only at first; a procedure on CAN-CH/CAN-IHS shows a
  cable step with Verify, and a warning that a lamp or chime may follow (airbag lesson);
  any code set during the session is tagged as a possible tool artefact.
- **One controller.** Only one screen may run a procedure at a time; a second device sees
  "Running on another screen" with view-only live readings and a STOP.
- **Nothing automatic is ever retried.** A negative response stops; the mechanic decides.
- **Web vs MCP.** Today writes are MCP-only. This design moves gated procedures into the
  web UI, which is a rule change: it needs the owner's explicit approval, a local-only
  bind (no LAN exposure without a token), and the server-side one-time token per run.

## 6. Technology (from the GitHub survey, 2026-10-26)

- **htmx** (vendored in /static, no CDN; CUORE runs offline) for step cards that swap in
  place; **sse-starlette** for live readings and step events during a run (server-sent
  events; the server stops the actuator when the stream drops).
- **Hold-to-confirm and STOP: built in-house** (~40 lines of pointer-event JS + CSS);
  STOP is a plain form POST so it works even if scripts fail.
- **Playwright for Python** (dev only) to test the flows end-to-end against the existing
  fakes, including hold-to-confirm, STOP, disconnect-stops and 44 px / 16 px measurement;
  **axe-core** (dev only) for contrast and labels in both themes.
- Diagnostic side stays CUORE's own (ISO-TP/UDS over the ELM/STN adapter);
  **udsoncan** only as an offline test oracle for timing/0x78 handling.

## 7. Delivery plan (each step shown to the owner before the next)

1. **Prototype with no car** - the procedure screen running against CUORE's fake live
   layer and a simulated ESIM/coil procedure; Playwright tests; owner reviews on the tablet.
2. **Read-only half on the real car** - the READY checks and BEFORE reads only (no command
   sent), so the checklist is proven against real readings.
3. **First real procedure** - only after the second adapter, a learned MES capture, a gate
   pass, the owner's decision on the interlock, and the owner's approval of web-UI writes.
   Start with an engine-off actuator if the ESIM vent stays blocked by the interlock.
4. **Resets** - service interval first (its before/after values are already known from
   the 10-23 log), only if its capture shows no 0x27.

## 8. Decisions for the owner

1. Allow gated procedures in the web UI (with hold-to-start, one-time token, local-only)?
   Today they are MCP-only.
2. ESIM vent test needs the engine running; CUORE's actuator interlock requires engine
   off. Keep the interlock (ESIM stays MES-only) or approve a running-engine class of
   tests with stricter guards (stationary, P, hood-open prompt, 30 s max)?
3. Second adapter + Y-splitter (needed to learn any procedure). No product recommended.
