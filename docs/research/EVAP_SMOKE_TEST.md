# EVAP smoke test by section — 2018 Stelvio 2.0T (GU)

Written 2026-09-26 for VIN ZASFAKPN5J7B88115 (P0455 / P0456 / P0440, chronic).
Companion to `EVAP_STELVIO.md`; this is step E7 of the `evap-leak` fault tree, expanded
so a smoke test tells you **which section** leaks, not just that something does.

**Source tags.** `[TSB …]` = transcribed from a bulletin in `EVAP_STELVIO.md` /
`TSB_CATALOGUE.md`. `[car]` = this car's own logs. `[practice]` = general EVAP smoke-test
shop practice, not from an FCA document for this platform. No FCA smoke-test procedure,
service-port location or pressure specification for the GME-T4 was obtainable
(`EVAP_STELVIO.md`, "Could not verify"), so every `[practice]` step should be checked
against the smoke machine's own instructions.

---

## 0. What this car's evidence already says

- Purge valve **actuates**: 18 KOEO actuator runs COMPLETED, including with P0456 stored `[car]`.
  Actuating is not sealing: a valve that clicks can still leak through. Section C tests that.
- P0455 and P0440 set with the tank at **93.7 %** and **91.8 %**; P0456 on a **cold-start idle**
  at 80 % `[car, FESLog_2609252002]`. High fill points at the canister/ORVR path
  (`EVAP_STELVIO.md` §4–5); the cold-start set fits the natural-vacuum test window.
- Platform base rate: canister module first, purge valve alone low-yield, standalone vent
  valve almost never `[EVAP_STELVIO.md §4, forum-grade]`.

## 1. The three sections

| Section | Contains | Codes it can explain | Access |
|---|---|---|---|
| **A. Tank side** | Tank, filler neck and cap, fuel delivery module (FDM) flange and lock ring, internal vapour line to the FDM port, tank-to-canister vapour hose, **recirculation line and its mid-point quick-connect** | P0455 (disconnected / cracked line, loose quick-connect), P0456 (seals) | Under car, filler door; FDM needs tank or access work |
| **B. Canister / vent side** | Vapour canister module, **ESIM** (separate part), clean-air hose, EVAP air filter | P0456, P0455, P2422-type blockage | Behind the **driver-side rear wheel liner** `[EVAP_STELVIO.md §4]` |
| **C. Purge side** | Canister purge port → purge line → purge valve → ejector tees → intake | P0440, P0455 (purge valve leaking through), P1CEA | Engine bay |

## 2. Before any smoke — two checks that can end the job

1. **Recirculation-line mid-point quick-connect.** Seated and latched? Reseat it.
   FCA's documented first check for these codes `[TSB S2125000002]`.
2. **Liquid fuel in the canister or recirculation line.** Disconnect the recirculation
   line and the canister's tank-side connection over a drain pan.
   **If fuel is present, stop smoke testing.** The bulletin path is: drop the tank, check
   the internal vapour line at the FDM port, and replace **both** canister and ESIM
   `[TSB 9100471]`. This VIN is in fuel-pump recall 25V586000 / Mopar 93C, which replaces
   the FDM, so check that connection on any reassembly `[EVAP_STELVIO.md §8]`.
3. **EVAP air filter** passes air freely `[TSB 9100468]`. A blocked filter can be the
   whole problem for flow/vent codes.

## 3. Setup `[practice]`

- Engine **off and cool**, ignition off, no smoking or sparks; ventilated bay.
- Use an **EVAP-rated smoke machine that pushes inert gas (nitrogen/CO2)**, never shop air,
  because the system holds fuel vapour.
- **Low pressure only.** EVAP components are damaged by over-pressure
  `[EVAP_STELVIO.md §10]`. Typical EVAP machines regulate around 0.5 psi (about 14 inH2O);
  use the machine's EVAP setting, never more.
- Fuel between about **1/4 and 3/4**. A near-full tank shrinks the vapour space and hides
  tank-side leaks; a near-empty one takes a long time to fill with smoke.
- Clamp **rubber** hoses only, with soft-jaw pinch pliers. **Never clamp nylon quick-connect
  lines**: disconnect at the quick-connect and cap instead.
- If the machine has a flow gauge, **zero it against its 0.020 in and 0.040 in reference
  orifices** first. By EPA/SAE definition, P0456 is a leak at least 0.020 in (0.5 mm) and P0455
  at least 0.040 in (1.0 mm). The gauge then tells you whether a section alone accounts
  for the code.
- **Seal the vent**: cap the EVAP air filter's fresh-air inlet. With the ignition off the
  purge valve is closed, so the system is sealed between that cap and the purge valve.

## 4. The isolation sequence

Work whole-system first, then split. At each split, the section whose flow falls to zero
is clean. Record the flow reading at every step.

**Step 1. Whole system.** Introduce smoke on the canister purge port (disconnect the purge
line at the canister, feed smoke into the canister port, cap the purge line). Note the flow
against the reference orifices. With no flow and no smoke anywhere, the leak is not present
at rest: go to section C, since a purge valve leaking only when hot or commanded fits
P0440.

**Step 2. Split A from B.** Disconnect the tank-to-canister vapour hose at the canister and
cap the canister's tank port. Smoke still in at the purge port.
- Flow **stops** → leak is on the **tank side**: go to Step 3.
- Flow **continues** → leak is in the **canister / vent section**: go to Step 4.

**Step 3. Tank side (A).** Smoke into the disconnected tank-side vapour hose, canister
still isolated. Look for smoke at, in order of cost to reach: filler neck and cap, the
**recirculation-line quick-connect** `[TSB S2125000002]`, hose unions under the car, the FDM
flange and lock ring. The platform has **no field reports** of filler neck, ORVR valve or FDM
flange leaks `[EVAP_STELVIO.md §4, "not substantiated"]`, so treat a find there as real but
unusual and confirm it with a soap test.

**Step 4. Canister versus ESIM (B).** These are separate parts, and replacing one for the
other's fault is a bulletin-warned error `[TSB 9100469]`.
- Move the vent cap from the air-filter inlet to the **canister's own vent port**, with the
  ESIM, clean-air hose and filter now outside the sealed zone. Smoke at the purge port.
  - Flow **stops** → the leak is in the **ESIM, clean-air hose or filter**. Look for smoke at
    the ESIM body and its connections, and for a kinked or split clean-air hose
    `[TSB 9100471]`. ESIM only → replace the ESIM only `[TSB 9100469]`.
  - Flow **continues** → the leak is in the **canister module**: smoke at its seams, ports or
    housing. Mopar canister P/N 68528496AA `[EVAP_STELVIO.md §4]`.
- `[practice]` The ESIM has an internal pressure relief. If smoke appears at the ESIM only
  while the vent is capped at the filter, check that the machine is not above its EVAP
  pressure before condemning the ESIM.

**Step 5. Purge side (C).** Reconnect everything on the canister. Disconnect the purge line
at the canister and feed smoke into the line toward the engine, ignition off so the purge
valve is shut.
- Smoke at hose joints or the ejector tees → hose or routing fault; check for kinked or
  mis-connected hoses `[TSB 9100325]`.
- Smoke reaching the **intake** (visible at the air box or throttle side) → the purge valve
  **is not sealing** even though it actuates. That explains P0440 and can explain P0455.
  This is the one result that would justify a purge valve.

## 5. Recording it so the evidence gate can use it

Enter each finding in cuore's evidence gate (`/v/<VIN>/gate`, or the `diagnosis_verdict`
tool) as a manual measurement, **with the flow numbers**, for example:

- measurement: `smoke test: whole-system flow above the 0.040 in reference; with tank port
  capped flow unchanged; with vent capped at canister port flow stopped; smoke seen at ESIM
  body`
- disconfirming test: `with the ESIM, hose and filter outside the sealed zone the canister
  and tank sections held with zero flow, so the canister is exonerated`

That second line is what the gate calls disconfirmation: the test that would have cleared
the part, run and failed to clear it.

## 6. After the repair

A road test cannot confirm a small-leak repair `[TSB 18-048-23]`. Clear the codes, keep fuel
between about 15 and 85 %, drive with cold starts, then use cuore's **verify_repair**
(`/api/live/module/ECM/repair?codes=P0455,P0456,P0440`). It reads each test's UDS status:
"not run since clear" means keep driving; "passed since clear" is the evidence; for EVAP,
also confirm the permanent code (Mode 0A) has gone.
