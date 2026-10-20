# TSB Layer and Cross-Reference

"TSB" means technical service bulletin. CUORE keeps a catalogue of bulletins, recalls, customer-satisfaction notices, campaigns and field reports, checks them off per car, and relates each one by explicit rules to what the car and the job actually contain. The aim is to suggest what to check, never to prove a fault.

## The catalogue

`cuore/data/tsb_catalogue.json`, last updated 2026-10-15, holds **141 rows**: 99 for the reference model and 42 sibling-engine analogues. A readable version is [docs/reference/TSB_CATALOGUE.md](https://github.com/dangelojohn/CUORE/blob/main/docs/reference/TSB_CATALOGUE.md). Sources include a public flat file of service bulletins received by the US safety regulator, the regulator's recall pages and the Canadian recall site.

Each row has (schema is documented inside the file):

| Field | Meaning |
|---|---|
| `id` | stable row id; the per-car checklist status is keyed by it |
| `kind` | `tsb`, `recall`, `csn`, `campaign`, `extended_warranty`, `emissions`, or `field_report` (a forum or retailer claim, never verified) |
| `number`, `nhtsa_id`, `title`, `date`, `summary`, `condition`, `remedy` | the bulletin itself |
| `systems`, `dtcs`, `components`, `symptoms` | what it touches; cross-reference fields are empty when research is silent, never invented |
| `repair_implied` | `flash`, `replace:<part>`, `procedure:<name>`, `inspect`, `software_update` or `none` |
| `depends_on_systems` | system keys that must be healthy |
| `applies` | `yes`, `no`, or `vin_check` (only a VIN lookup settles it) |
| `verified` | true only when the source document itself was read; false when only indexed or inferred |
| `vehicle_scope` | `this_model` (default) or `sibling_engine` (an analogue) |
| `transferability`, `stelvio_equivalent` | for analogues: why it may or may not carry over, and the row it parallels |

The catalogue records its own corrections. For example, the bulletin first cited for an engine-computer flash turned out, when the source document was opened, to cover the 2017 Giulia only, so its applicability is `vin_check`; the directly applicable 2018 Stelvio flash bulletin lists other codes than the three EVAP ones. See [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]].

## The cross-reference engine

`cuore/services/tsb_xref_bridge.py` (`/api/tsb/xref`) relates each row to four things:

1. **Codes** the car has or had (`code_match`).
2. **Repairs, parts and inspections** already on the job (`repair_interaction`).
3. **Open hypotheses** on the job (`hypothesis_interaction`).
4. **The systems dependency layer**: the fault's own system and systems one hop upstream or downstream.

Every relation carries a **reason string** that a mechanic can check against the catalogue row, the code history, the job ledger or the systems graph. The engine writes nothing; suggested evidence is only offered through a form.

### Relations that matter

| Relation | Meaning |
|---|---|
| `explains` | the bulletin lists a code the car has |
| `same_system` / `dependent_system` | system tag matches, or one hop away. A same-system match is **not** evidence |
| `candidate` | the bulletin's implied repair targets a part on the job |
| `already_applied` + `did_not_resolve` | this remedy was done and the fault came back, so it is evidence the remedy is not the fix |
| `ruled_out_by_inspection` | an inspection already excluded the bulletin's cause |
| `supports` / `weakens` | interaction with a named hypothesis |
| `model_year_doubt` / `other_model_doubt` | scope does not clearly cover this car |
| `analogue`, `field_report` | sibling-engine rows (below) |

### Scoring

Each relation type is counted once per bulletin. Small integers, floor 0:

| Component | Points |
|---|---|
| explains | 3 |
| same system | 2 |
| already applied and did not resolve | 2 |
| dependent system | 1 |
| candidate | 1 |
| hypothesis supports | 1 |
| applicability doubt (other model or model year) | -2 |
| ruled out by inspection | -2 |

A bulletin with `applies: no` keeps every relation but scores 0 and is flagged not applicable.

## Sibling-engine analogues

Rows with `vehicle_scope: sibling_engine` come from other models that share the same engine family (for example the same 2.0 L turbo engine in other Stellantis vehicles, or a sister brand's EVAP software fix). They are **never Stelvio evidence**:

- they get the relation `analogue` (linked to the Stelvio row they parallel when one exists), with the reason "analogue: same engine family, written for <model>; not a bulletin for this car";
- their score is **halved** (rounded down; a code match keeps at least 1);
- `field_report` rows never score above 1;
- they sort after every Stelvio row, stay out of the per-code, per-hypothesis and per-system lists, and are listed separately.

The practical use: an analogue says "this exact code was fixed by a flash on a sister engine", which keeps the calibration question open; it does not say the flash applies here.

## The SLVT replica

Bulletin 18-048-23 states that the manufacturer dealer tool's **small leak verification test** (SLVT) must be run first to confirm a leak, and again after any repair, component replacement or software update, and that a road test cannot confirm an EVAP small-leak repair. The bulletin gives no fuel range, temperature, soak time or pass limit; those live in a service procedure not in the repository, and CUORE does not invent them.

`/slvt` (`slvt_bridge.py`) is a **read-only replica**. The dealer tool commands the engine computer to run the test through an unpublished routine service that CUORE never sends. The replica instead:

1. waits for the computer's own EVAP monitor to run;
2. reads the outcome through three existing read-only operations: readiness (Mode 01 PID 01/41), the EVAP Mode 06 results with limits, and the UDS status bits of P0456, P0455 and P0440;
3. grades the result with a pure function, records one `slvt_replica` observation and one `test` action on the open job.

Each precondition shown carries its source. It stands in for the dealer test until that is available; it does not replace it.

Related: [[Evidence Model|Evidence-Model]], [[Jobs, Hypotheses and Mechanic Steps|Jobs-Hypotheses-and-Mechanic-Steps]].
