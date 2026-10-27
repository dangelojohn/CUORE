# CUORE

Cuore is Italian for heart. CUORE is a diagnostic assistant for a mechanic who specialises in cars that are loved, not merely driven: the Alfa Romeo Stelvio and Giulia today, the Maserati Levante and Grecale and the Ferrari Purosangue next.

## Maxim

**Diagnose on evidence. Prove the fix. Learn for the next car.**

The mechanic decides; CUORE remembers. It serves the owners' maxim, passion and the joy of driving, by sending the car back driving the way it should, with the repair proven and the car's story told honestly.

## What that means in the tool

- Every fact carries its date, its source and a confidence grade. Nothing is invented; unknown means "use the service manual".
- Clearing is not fixing. A repair is verified only by proof from the car.
- One car at a time, start to finish: complaint, evidence, codes, understanding, tests, hypotheses, plan, repair, verification, documentation, release, tools away, next car.
- Driver and mechanic input, photos, sounds, inspections and corrections are kept as the car's record, never mistaken for measurements.
- Every finished job becomes a case, so the next car with the same fault starts where the last one finished.
- CUORE advises and records. It never blocks, manages or replaces the mechanic or his other tools.

## Status (2026-10-26)

CUORE now reasons across a job (common cause, ranked suspects, the best next test), leads every list with what matters now, and moves each fault from Fixed to Verifying to Proven fixed on the car's own readings. Writing to the car is still MES's job; CUORE is earning it in stages, see `docs/design/CUORE_WRITE_CAPABILITY_PLAN.md`. Lists follow `docs/design/CUORE_LIST_ORGANISATION.md`.

## Where to read more

`docs/handbook/` is the place to understand everything gathered and to build on: decisions and rules, architecture, knowledge tables, the Stelvio case, methods, roadmap. `docs/vehicles/<VIN>/` holds each car's case folder.
