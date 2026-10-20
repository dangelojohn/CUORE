# ESIM Bench Test

A two-page test sheet for a new, untested **ESIM** (evaporative system integrity module) held in the hand, out of the car. It finds the **correct mounting orientation** (small white cap up or down) and proves the part works. The sheet is [docs/handbook/esim/ESIM_Bench_Test_Stelvio.pdf](https://github.com/dangelojohn/CUORE/blob/main/docs/handbook/esim/ESIM_Bench_Test_Stelvio.pdf); this page reproduces its flowchart as text. The generator scripts are in [docs/handbook/esim/](https://github.com/dangelojohn/CUORE/tree/main/docs/handbook/esim).

Why this test exists: see [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]. The new ESIM's fitment and orientation were never recorded, and outside sources say orientation matters. The sheet's own sources note that the flow directions in the mouth test are **inferred from the design**, and that none of the outside sources is a reading from this car.

## Rules

- **Blow gently** through a short clean hose; **never suck** (fuel vapour). "Gentle" means enough to make a candle flicker, not go out.
- **No battery and no 12 V.** The ESIM has no solenoid.
- Put a multimeter on the two switch pins, set to **ohms**.
- **Hold the ESIM perfectly still.** After every change of position, wait **5 seconds** before blowing.

## The flow

**A. Prepare.** Tape-label the two holes "1" and "2". Mark the small white cap end "W". The meter should read **OPEN**.

**B. Position 1: upright, W up.** Hold still 5 s. Blow gently into hole 1, then hole 2.
- **Both pass easily**: go to D.
- **One hole passes easily, the other is blocked**: go to C.
- **Both blocked even when blown harder**: **FAULTY** (valves stuck shut).

**C. Switch test**, same position, held still. Blow gently into the **blocked** hole.
- Meter **closes** (about 0.5 to 2 ohm) while you blow and **opens** when you stop: **PASS in this position.** Blowing a little harder makes air suddenly pass (the vacuum relief valve opening). Go to E.
- Meter stays **open**: **FAULTY** (switch).

**D. Position 2: upright, W down.** Hold still 5 s. Repeat B.
- A pattern appears (one easy hole, one blocked): go back to C in this position.
- **Both still pass easily**: try lying flat, with the connector at 12, 3, 6 and 9 o'clock, 5 s each. A pattern in one of them: note the position and go to C.
- **No position gives a pattern**: **FAULTY** (weights not sealing).

**E. Record the correct orientation.** Write down: W up or W down (or the flat position), and which hole is the tank side.

**F. Fit and prove.** Mount on the car in the recorded orientation, vertical, tank-side hole toward the canister. Ignition on, back-probe the ESIM signal wire: about **5 V** at rest and about **0 V** when gentle vacuum closes the switch. **Do not clear codes.** Drive until the EVAP monitor completes, then read in CUORE. If the monitor completes with P0440, P0455 and P0456 showing no fail bits: **FIXED.**

**G. Faulty.** Do not fit. Return it or replace it with the VIN-correct ESIM, and run this same test on the replacement before fitting.

### Notes on the sheet

- The **easy hole is the tank/canister side**; the **blocked hole is the fresh-air side** (inferred from the design).
- Check the other upright position once: if it also seals, orientation is not critical for this part; if it leaks, orientation **is** critical, so mount exactly as found.

## Page 2: extra checks and sources

- **White cap check** (optional, if visible): hold still in the working position and blow gently into the easy hole. The cap should lift and drop back freely when you stop. Stays up or sticks: **faulty**. The cap's identity is not documented (most likely the large weighted pressure valve), so rely on the blow and switch results, not on the cap alone. A rattle or click when shaken is **not** a valid test.
- **What this test cannot prove**: breath is not measured, so the exact switch point (about 1 inch of water vacuum) is not confirmed. For that use a hand vacuum pump with a gauge in inches of water and stay between 1 and 2 inches; above about 2.2 inches the vacuum relief valve opens by design and mimics a leak.
- **Sources** (outside literature, none a reading from this car): a trade-magazine article on Chrysler ESIM design and thresholds (pressure valve about 0.5 inch of water, vacuum valve about 2.2, switch about 1, about 0.5 to 2 ohm closed); a parts-maker tech tip on vertical mounting, no solenoid and a 5 V reference; and a repair-database tip on wrong orientation causing P0440, P0441 and P0456 on a truck, fixed by re-orienting.

## The sourced facts behind the sheet

Every number below is **outside literature**: trade articles and tech tips about Chrysler and Jeep ESIMs. None is a reading from this car and none is a Stellantis document for the Stelvio. CUORE keeps them as one record (the part's design block in the parts catalogue, `mes.parts.ESIM_DESIGN`), with the sources named, and shows them as a card on the leak-detection system's page ([[Features]]).

| Fact | Value | Source (kind) |
|---|---|---|
| Design | Passive: housing, vacuum contact switch, diaphragm, a small weighted vacuum valve and a large weighted pressure valve. **No solenoid** | Trade article "Chrysler ESIM"; a parts-maker description |
| Small vacuum valve opens | about **2.2** inches of water of vacuum | Trade article |
| Large pressure valve opens | about **0.5** inch of water of pressure | Trade article |
| Switch closes | about **1** inch of water of vacuum | Trade article; a second trade article on EVAP performance codes |
| Switch resistance when closed | about **0.5 to 2** ohm (unplugged, meter on the two switch pins) | Trade article |
| Electrical | The engine computer supplies a **5 V reference** and a ground; back-probed signal about **5 V** at rest and about **0 V** while the switch is closed by about 1 inch of vacuum | Parts-maker signal description; trade article |
| Orientation | Gravity dependent: mount **vertically**, in the position the service drawing shows; an adaptor is used where the canister is angled | Parts-maker tech tip |
| Wrong orientation | A repair-database tip for a **Ram** truck: the module fits **four ways, only one correct**; the wrong way gave P0440, P0441 and P0456 with the switch never closing (signal never 0 V), fixed by re-orienting | Repair-database tip (one vehicle, not Alfa) |
| Warning | **Never apply 12 V** across the switch: it can damage it | Design block |

What the sources do **not** say, kept on the card so nobody assumes it: the identity of the small white cap at one end (probably the large weight, not documented); that a rattle when shaken is *not* a valid test; and that the mouth-blow flow directions on this sheet are **inferred** from the design, not documented. A positive-pressure smoke test does not load the vacuum seat, because the small valve opens on vacuum and the large one on pressure [I from the article].

**Why this sheet matters:** the part is gravity dependent, the fitted unit's orientation and port seating were never recorded, and the engine computer tracks no code for the switch circuit or the vent circuit ([[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]). The same checks appear in the fault tree as step **E9** (orientation against the drawing) and **E10** (back-probe, about 5 V falling to about 0 V under about 1 inch of vacuum), and as mechanic steps on any EVAP hypothesis that names the ESIM ([[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]]).

## Safety

Fuel vapour: no sparks, ventilated space, hand vacuum only, **never shop air** through the part. The part is read and tested; CUORE does not command it. See [[Safety Rules|Safety-Rules]].
