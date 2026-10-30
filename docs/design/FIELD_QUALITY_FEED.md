# Field-quality feed (prototype)

Purpose: pooled across shops, with consent, show engineering patterns ("the 949 is starting to show this code with these readings; fixed by X in 8 of 10 cases") before a bulletin exists. Today CUORE holds one car, so this is the pipeline only; one car is not a pattern.

Endpoint: `GET /field-quality.json` (same token rule as every page). Page: `/field-quality`. Export only: CUORE never sends anything.

## Consent
`<state_dir>/field_quality.json`: `{"sharing": false, "min_cohort": 3, "changed": "YYYY-MM-DD"}`. Default OFF. Toggled on the page (form POST). Off: the feed returns `"sharing": "off"`, `"message": "sharing is off"`, `"rows": []`. The page still shows local rows.

## Schema `cuore.field_quality/1`
Top level: `schema`, `generated` (date), `min_cohort`, `sharing` ("on"/"off"), `message`, `rows`.

Row: `platform` (e.g. 949), `model_year`, `market` (currently "unknown"), `dtc` (base code), `failure_type` (suffix after the dash), `readings_signature` ("N out of band, M in band" or "no readings categorised"), `cars`, `cases`, `proven_fixes`, `comebacks_30d` {yes,no,unknown}, `fixes` [{`fix`, `cases`, `proven`}].

- Proven = outcome fixed and verified clean at release (proof of repair passed).
- Comeback = a later case on the same car with the same base code opened within 30 days of close; "unknown" while the 30 days have not passed.
- `fix` = fitted part number(s) matching a part-number pattern, else "fixed, part not recorded" or "not fixed / unresolved".

## Minimum cohort
A row is a pattern only when `cars >= min_cohort` (default 3, configurable, floor 2). The page shows smaller rows as "single case, not a pattern yet"; the feed never includes them.

## Never included
VIN or any hash of it, customer, plate, names, technician, complaint, notes, hypothesis or action text, raw reading values, visit dates, shop identity. VINs are used in memory only to count distinct cars.

## Known gaps
Market is not captured yet. The readings signature counts categorised test results rather than naming key parameters (needs a sourced parameter list). The receiving side does not exist.
