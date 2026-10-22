# AlfaCore model map (for a CUORE connector)

Source: public GitHub repo `dangelojohn/alfacore` (Odoo 19 CE, LGPL-3.0-only), read at HEAD on 2026-10-22.
Files read: `README.md`, `CLAUDE.md`, `docs/SPRINT-IMPLEMENTATION-STATUS.md`, `docs/CLAUDE-CODE-HANDOFF-2026-05-12.md`,
`docs/api/README.md`, `docs/api/alfacore-v1-openapi.yaml`, `docs/architecture/*` (Decision Log in full; Service Plan sections 5-10;
Blueprint sections 4.1 and 8.1), `docker-compose.dev.yml`, `deploy/README.md`, and the `models/`, `controllers/`, `security/`
(and a few `data/`, `tests/`) files of: alfa_core (base only, for `inference_zde`/PIPEDA), alfa_fleet, alfa_service, alfa_parts,
alfa_core_scanner, alfa_core_diagnosis, alfa_core_inspection, alfa_tsb, alfa_core_campaign, alfa_core_app_api,
alfa_core_multi_loc, alfa_core_portal.

Rules for this file: only what was read is stated. Where the architecture docs and the code disagree, both are given and the
disagreement is flagged. No credentials, hostnames or IPs are recorded. Items marked "(not seen)" mean the code I read does
not contain it, not that it is absent from the whole repo.

---

## 1. Project shape

- AlfaCore = "Luxury automotive service platform for Italian-platform vehicles (Alfa Romeo in v1; Fiat / Maserati in v1.1+)".
  "Paired OBD-II BLE scanner + companion PWA + AI diagnosis backed by Odoo 19 CE." (README)
- 13-14 Odoo modules (README says 13, CLAUDE.md says fourteen; the handoff doc lists 14 incl. `alfa_core` and `alfa_core_multi_loc`;
  `alfa_core_loaner` and `alfa_core_configurator` exist but are out of scope here).
- Twelve Patterns doctrine (README/CLAUDE.md). Those that matter to a connector: 4 per-record isolation (VIN-scoped),
  5 idempotent/immutable intermediates, 6 config-as-data, 10 honest boundaries (stub methods document hand-off boundaries),
  11 per-record privacy disposition (`inference_zde`), 12 versioned content.
- Custodianship rule (CLAUDE.md): "if a model is defined in module X, only module X writes its schema. Module Y may extend
  module X's model via inheritance - never via parallel definition." This is the rule a CUORE connector module should follow.
- Decision Log v1.0 (24 locked decisions per README/CLAUDE.md; the log file's own table lists 12). Decisions relevant here:
  #3 recommendation engine "Rule-based only" at v1 (LLM polish opt-in post-pilot); #9 scanner hardware "Vgate iCar Pro BLE 4.0
  baseline; OBDLink MX+ included with Pro tier"; #10 "Alfa-only at v1; Fiat / Maserati added in v1.1"; #12 Twilio SMS.
  "ZDE preserved at v1 ... customer scan data does not leave the AlfaCore host during inference at pilot."
- Out of scope per CLAUDE.md: "Hardware engineering - Vgate iCar Pro BLE 4.0 baseline; OBDLink MX+ for Pro; no PCB, no firmware",
  "DTC content corpus", "Triage rule corpus" (rules authored over time; "engine architecture is what we build"),
  "Stellantis dealer-only integrations - eAuthority, SDMS, Mopar TechAuthority", "Predictive maintenance ML".
- Status doc (v2.9.0, 2026-05-11): all sprints "Full" (models + security + views + demo + tests). Handoff doc (2026-05-12):
  all 14 modules installed on the live container deployment; `alfacore_smoke` suite "partial" (one unexplained Traceback);
  the architecture corpus "is binding but not always reflected in code yet" (handoff section 8.6) and "Manifests track what
  code uses, not what corpus describes" (section 5.3).

### Deployment shape (only)
- `docker-compose.dev.yml`: four services - Postgres 15, Odoo 19 CE image (repo bind-mounted read-only as extra-addons, custom
  odoo.conf), Qdrant (for alfa_tsb RAG), Ollama (for diagnosis LLM and `bge-large-en-v1.5` embeddings). Ports exposed for Odoo
  web and longpolling, Postgres, Qdrant REST/gRPC, Ollama.
- `deploy/`: Kustomize base + dev/prod overlays + Argo CD Application manifests; production image is stock Odoo 19 with an
  init-container (`addon-loader`) that fetches a Cosign-signed module tarball and refuses to start on signature mismatch;
  `dbfilter = ^alfacore.*`; filestore on a PVC. The handoff doc states the live deployment on a NAS-hosted container host
  "doesn't use the k8s manifests"; prod overlay is single-replica/Recreate because the filestore PVC is RWO.
- Odoo is the only system of record; the PWA talks to it over the `/api/v1/*` REST API (section 9).

### Groups / ACL vocabulary (alfa_core `security.xml`)
`alfa_core.group_user` (implies `base.group_user`) < `group_advisor` < `group_manager`; separate `group_pipeda_officer`
(implies `group_user`). Portal customers are `base.group_portal`. CSV ACLs are explicit per model (listed per model below as
R/W/C/U = read/write/create/unlink).

---

## 2. alfa_core (privacy / customer base, read only for context)

| Model / field | Detail |
|---|---|
| `res.partner` extension | `alfa_core_customer` Boolean; `alfa_core_signup_date` Datetime (auto-stamped); `alfa_core_preferred_channel` Selection email/sms/whatsapp/portal (default email; "WhatsApp deferred to v1.1"); `alfa_core_customer_tier` (computed, stored) bronze/silver/gold/platinum; `alfa_core_lifetime_spend` (sum of posted out_invoices); `alfa_core_subscription_ids`; `alfa_core_active_subscription_id` |
| PIPEDA fields | `alfa_core_pipeda_consent_version` Char and `alfa_core_pipeda_consent_date` Datetime, both field-level restricted to `alfa_core.group_pipeda_officer`. Config param `alfa_core.pipeda_consent_version` = `2026-05` (seed data) |
| `alfa_core.subscription` | `name` (sequence), `partner_id` (req), `plan_id` (req), `start_date` (req), `end_date`, `state` trial/active/past_due/cancelled/expired (default trial), `sale_order_id`, `inference_zde` Boolean (default True; "Per-record privacy disposition (Pattern 11). True = Ollama-local only; False = cloud LLM polish allowed."), `active`. On create `inference_zde` is taken from `plan.inference_zde_default` unless given. State methods `action_activate` (trial/past_due -> active), `action_mark_past_due` (active only), `action_cancel`, `action_expire`; each posts chatter. Constraint: end_date >= start_date |
| `alfa_core.subscription.plan` | `code` is "Stable identifier (basic, premium, pro). Used in API and integrations."; `inference_zde_default` Boolean default True ("Basic/Premium default to Ollama-local inference; Pro tier customers may opt into cloud LLM polish with explicit consent") |

`alfa_fleet` adds `alfa_core.subscription.vehicle_ids` (M2M to vehicles).

---

## 3. alfa_fleet

Depends on `alfa_core`; external python dep `requests`. Seed data: 4 platforms, 4 engines, 4 trims.

### `alfa_fleet.vehicle` (VIN-keyed master; `mail.thread` + activity)
| Field | Type | Req | Notes |
|---|---|---|---|
| `vin` | Char(17) | yes | indexed, tracked, `copy=False`; UNIQUE(vin) |
| `year` | Integer | yes | constrained 1980..2100 |
| `make` | Char | yes | default "Alfa Romeo" |
| `model` | Char | yes | e.g. 'Stelvio', 'Giulia', '4C', 'Tonale' |
| `license_plate`, `color`, `color_interior` | Char | no | |
| `platform_id`, `engine_id`, `trim_id` | M2O | no | to `alfa_fleet.platform/engine/trim` |
| `last_mileage_km` | Integer | no | must be >= 0; writing it auto-sets `last_mileage_date` |
| `state` | Selection | yes | active (default) / in_service / sold / totalled |
| `ownership_ids` | O2M | | `alfa_fleet.vehicle.ownership` |
| `primary_owner_id` | M2O res.partner | computed, stored | active ownership row with role `primary_driver` |
| `preference_ids` | O2M | | `alfa_fleet.vehicle.preference` |

Constraints / rules (quoted from code):
- `VIN_PATTERN = ^[A-HJ-NPR-Z0-9]{17}$  # ISO 3779 - no I, O, Q`, checked on `vin.upper()` by `_check_vin_format`; error text "VIN must be 17 alphanumeric characters (no I, O, Q)".
- `create()`/`write()` normalise `vin` with `.upper().strip()`.
- `action_decode_vin` is a STUB: posts a chatter message "NHTSA vPIC integration ships in Sprint 11"; no vPIC call was found in the app_api controller (boundary, not implemented).
- No field for ECU calibration ID / CVN / software version exists on the vehicle (not seen).

### `alfa_fleet.vehicle.ownership` (through-model)
`vehicle_id` (req, cascade), `partner_id` (req), `role` Selection primary_driver (default) / secondary_driver / account_holder / authorized_caller, `start_date`, `end_date`, `active`, `notes`. Constraint `EXCLUDE (vehicle_id WITH =) WHERE (active AND role = 'primary_driver')` - one active primary driver per vehicle; end_date >= start_date.

### `alfa_fleet.vehicle.preference`
`vehicle_id`, `category` (oil, brake_fluid, coolant, transmission_fluid, transfer_case, differential, washer_fluid, tire, alignment, battery, other), `name` (req), `spec`, `brand_preference`, `set_by_id`, `set_date`, `active`, `notes`.

### Taxonomy
- `alfa_fleet.platform`: `name`, `code` (UNIQUE), `description`, `engine_ids`. Seeds: giorgio, 4c, stellantis_compact, premium_159.
- `alfa_fleet.engine`: `name`, `code` (UNIQUE), `platform_id` (req), `displacement`, `configuration`, `horsepower_kw`, `torque_nm`, `fuel_type` (gasoline/diesel/hybrid/phev/ev), `oil_capacity_l`, `default_oil_spec`. Seeds: GME_2_0T, F154_29_V6, 1750_TBi, 15_T4_MHEV.
- `alfa_fleet.trim`: `name`, `code` (UNIQUE), `is_performance`. Seeds: sprint, ti, veloce, quadrifoglio.

ACL: platform/engine/trim: user R, manager RWCU. vehicle: user R, advisor RWC, manager RWCU, portal R. ownership: advisor RWC, manager RWCU, portal R. preference: advisor RWC, manager RWCU, portal RWC (portal can write preferences).

---

## 4. alfa_parts

### `alfa_parts.part`
`part_number` (req), `canon_part_number` (computed, stored, UNIQUE), `name` (req), `manufacturer` (default MOPAR), `category` (engine, brake, suspension, electrical, body, interior, fluid, filter, tire, other; req), `product_id` -> product.product, `fits_platform_ids`, `fits_engine_ids`, `alternative_ids`, `vendor_ids`, `active`. `find_by_part_number(value)` looks up by canonical form.
`canonicalize_part_number`: docstring claims 7 passes; the implemented function does NFC normalise, strip + strip quotes, upper, remove whitespace/`-`/`_`/`.` only ("minimal viable normalization. Expand per real OEM patterns").

### `alfa_parts.part.alternative`
`oem_part_id` (req), `name` (req), `part_number`, `manufacturer` (req), `grade` Selection **safe / interim / not_recommended** (req; "Pattern 10 - honest grading"), `rationale` (req, "Source-cited evaluation"), `source_reference` ("Diagnosis ID, TSB reference, or technician evaluation note"), `price_savings_pct`.

### `alfa_parts.part.kit` / `.kit.line`
Kit: `name`, `code` (UNIQUE), `line_ids`, `fits_platform_ids`, `fits_engine_ids`, `estimated_labor_hours` - "service quote templates", not POS combos. Line: `part_id`, `quantity`, `required`, `notes`.

### `alfa_parts.part.vendor`
`vendor_type` oem_dealer / aftermarket (default) / mopar_direct / specialty, plus contact fields, `delivery_days_typical`.

ACL: part user R / advisor RWC / manager RWCU / portal R; alternative user R / advisor RWC; kit advisor RWC; vendor advisor R.

---

## 5. alfa_service

Extends `sale.order` (not a separate `alfa_service.order` model, although Blueprint 4.1/8.1 names `alfa_service.order`).

### `sale.order` extension
`alfa_vehicle_id` -> alfa_fleet.vehicle; `alfa_service_state` Selection (15 states, default draft, indexed, `copy=False`); `alfa_bay_id`; `alfa_technician_id` -> hr.employee; `alfa_quality_check_ids`; `alfa_quality_check_pending` (stored; true if any QC in draft/pending).

**15-state machine (`SERVICE_STATES`)**: draft, sent (Quotation Sent), confirmed, parts_ordered, parts_ready, scheduled, in_progress, inspection_pending, findings_review (Findings - Customer Review), quality_check, ready_for_pickup, picked_up, awaiting_review (Awaiting Customer Review), closed, cancelled.
Blueprint 8.1 diagram edges (not enforced in code): draft->sent->confirmed->parts_ordered->parts_ready->scheduled->in_progress->inspection_pending->findings_review->in_progress (approve or decline); in_progress->quality_check->(fail)in_progress / (pass)ready_for_pickup->picked_up->awaiting_review->closed; sent/confirmed->cancelled.
Code reality: `action_advance_service_state(new_state)` just assigns the new state and posts chatter "Service state: old -> new"; it validates nothing (no transition table).

### `alfa_service.bay`
`name`, `code` (UNIQUE), `location_id`, `bay_type` general/alignment/diagnostic/track_prep/body, `capacity_vehicles`, `lift_type` two_post/four_post/scissor/ground, `current_order_id` (computed: the in_progress SO in that bay).

### `alfa_service.quality.check`
Custom (explicitly not Odoo Quality): `sale_order_id`, `name`, `description`, `state` draft / pending / passed / failed / waived, `checked_by_id` (hr.employee), `checked_at`, `pass_threshold_note` ("What constitutes a pass"), `failure_reason`. `action_pass()`; `action_fail(reason)` raises UserError "Failure reason required." if none.

ACL: bay user R / advisor RW / manager RWCU; qc advisor RWC / manager RWCU / portal R.

---

## 6. alfa_core_scanner (OBD ingestion)

Depends `alfa_fleet`, `alfa_core`. Manifest summary: "OBD-II BLE scanner ingestion: paired devices, scan sessions, DTC + PID capture, offline heartbeat".

### `alfa_core_scanner.device` (`mail.thread`)
| Field | Type | Req | Notes |
|---|---|---|---|
| `serial_number` | Char | yes | UNIQUE(serial_number) |
| `model_name` | Selection | yes | `vgate_icar_pro` "Vgate iCar Pro BLE 4.0" (default) / `obdlink_mx_plus` "OBDLink MX+" / `other` "Other" |
| `firmware_version` | Char | no | |
| `partner_id` | M2O res.partner | no | Owner |
| `vehicle_id` | M2O alfa_fleet.vehicle | no | "Vehicle this scanner is currently paired with. Null when in transit." |
| `paired_date`, `last_seen` | Datetime | no | `last_seen` readonly |
| `state` | Selection | yes | **shipped (default) -> paired -> active**; also offline, returned, decommissioned |

Docstring: "the scanner is the moat. Customer-owned hardware that ships with onboarding. Bluetooth pairing happens in the PWA."
State lifecycle is assigned by `write()` in tests (shipped -> paired -> active); no transition methods or guards were found.
No `pairing_token` fields (Service Plan 5.1 lists them; implementation lacks them).

### `alfa_core_scanner.scan_session` (`mail.thread`)
| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | Char | yes | sequence `AC-SCAN-%(year)s-` + 6-digit padding |
| `vehicle_id` | M2O | yes | "Every session has exactly one vehicle" |
| `device_id` | M2O | yes | a device record is mandatory |
| `started_at` | Datetime | yes | default now |
| `ended_at` | Datetime | no | `duration_seconds` computed, stored |
| `mileage_at_scan` | Integer | no | km |
| `battery_voltage` | Float | no | V (single value) |
| `modules_scanned` | Char | no | "Comma-separated module list: ECM, TCM, ABS, AFLS, BCM, etc." |
| `dtc_ids`, `pid_ids` | O2M | | `dtc_count` computed, stored |
| `state` | Selection | yes | **running (default) / complete / aborted / uploaded ("Uploaded to Backend")** |
| `inference_zde` | Boolean | | default True; help: "Inherits from subscription. ZDE=True keeps this session local only." (no code found that copies it from the subscription) |
| `diagnosis_report_id` | M2O | | added by `alfa_core_diagnosis` via `_inherit` (readonly) to avoid a dependency cycle |

Lifecycle seen: API upload creates the session directly in state `uploaded`. Tests create `running`, `complete`, `uploaded`. No transition methods exist.
Immutability: README/status claim "Sprint 5 `scan_session` immutable once committed" (Pattern 5), but the model file contains no `write`/`unlink` guard (not seen). Treat immutability as a convention, not an enforced constraint.

### `alfa_core_scanner.scan_dtc`
`scan_session_id` (req, cascade), `dtc_code` Char (req, indexed; "e.g. P0301, P0507, C0561"), `dtc_status` Selection **active ("Active / Current") / pending / history / permanent** (default active, req), `module_source` Char ("ECM, TCM, ABS, AFLS, BCM, etc."), `freeze_frame_data` Text, `raw_payload` Text ("Hex bytes as received from the scanner."), `sequence`.
`dtc_code` is a free Char, not a Many2one to the DTC library (Service Plan 5.4 shows `dtc_id` + `occurrence_count` + `first_seen`; not implemented).

### `alfa_core_scanner.scan_pid`
`scan_session_id`, `pid_id` Char (req; "OBD-II PID identifier, e.g. '010C' (RPM), '0105' (Coolant temp)"), `pid_name`, `value` **Float**, `units`, `raw_payload`.

### `alfa_core_scanner.heartbeat`
`device_id`, `received_at`, `rssi` ("Signal strength when last seen."), `battery_voltage` ("Vehicle Battery (V)"), `firmware_version`, `notes`.

ACL: device advisor RWC / manager RWCU / portal RW; session advisor RWC / manager RWCU / portal RWC; scan_dtc advisor RWC / manager RWCU / portal R; scan_pid advisor RWC / manager RWCU (no portal); heartbeat advisor R / manager RWCU.

### Hardware assumptions in the scanner module and docs
- Device vocabulary is BLE dongles only (Vgate iCar Pro BLE 4.0, OBDLink MX+, "other"). Heartbeat carries `rssi`. Pairing "happens in the PWA".
- Service Plan 6.1: "the scanner does the absolute minimum: it's a passive OBD-II to Bluetooth Low Energy bridge. All protocol intelligence lives in the companion app."
  7.1: PWA on iOS Safari / Android Chrome via Web Bluetooth ("SPP-over-BLE"); native wrapper (Capacitor) only if background BLE needed.
- Service Plan 6.2 protocols (docs only, no `protocol` field in the model): ISO 15765 CAN primary, KWP2000, ISO 9141-2, J1850.
- Service Plan 6.3 standard scan reads Mode 01, 02, 03, 07, 09 (VIN, calibration ID, CVN), 0A, plus "FCA proprietary (Premium)". No Mode 06 appears anywhere I read. No UDS (ISO 14229) service is mentioned.
- Service Plan 6.4 stated limits: the app does not clear DTCs, write to ECU memory, "Run actuator tests" ("technician-only"), or "Bypass safety interlocks".
- Where a wired / bypass-cable adapter does NOT fit:
  1. `model_name` has no wired/ELM/J2534 value (use `other`; there is no transport, cable, or adapter-type field).
  2. `heartbeat.rssi` and PWA-pairing assume wireless; a cabled adapter has no RSSI and no BLE pairing step.
  3. The API upload path requires a device with `partner_id` AND `vehicle_id` matching the caller and the VIN, so a bench/bypass rig must be registered as a "paired" device first.
  4. Nothing models which bus segment or connector the data came from (OBD-II pin 6/14 CAN vs gateway-bypassed segment); `module_source` is a free-text ECU label only.
  5. The docs' "thin dongle, intelligence in the PWA" design means the server only receives already-parsed rows (`code`, `status`, `module`, `freeze_frame`, `raw`); anything produced by a desktop tool must be flattened into those strings.
  6. Stated boundary 6.4 (no writes / actuator tests / interlock bypass in the app) is a product position that a bypass-cable workflow would sit outside of.

---

## 7. alfa_core_diagnosis

Depends `alfa_core_scanner`, `alfa_parts` (the corpus says it should also use `alfa_tsb`; code does not - handoff 5.3). Sequence for reports: `AC-DX-%(year)s-` + 6 digits.

### `alfa_core_diagnosis.report` (`mail.thread`, `mail.activity.mixin`)
| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | Char | yes | sequence |
| `scan_session_id` | M2O | yes | `ondelete=restrict` |
| `vehicle_id` | related, stored | | from session |
| `partner_id` | related, stored | | from `vehicle.primary_owner_id` (active `primary_driver` only) |
| `state` | Selection | yes | **draft (default) -> ai_generated -> pending_review -> reviewed -> delivered**; plus disputed |
| `confidence` | Float | | default 0.0, "Aggregate confidence 0.0-1.0." (no code computes it; tests set it manually, e.g. 0.72, 0.92) |
| `severity` | Selection | | info / warn (default) / severe / safety_critical |
| `inference_zde` | Boolean | | default True ("Pattern 11 ... derives from the scan_session and ultimately from the subscription" - docstring; no copy logic seen) |
| `summary` | Text (translate) | | "Customer-facing plain-English summary." |
| `technical_summary` | Text | | "Internal technician-facing." |
| `recommendation_ids` | O2M | | |
| `reviewed_by_id` | M2O res.users | | Pro reviewer (res.users, not hr.employee - handoff 5.5) |
| `reviewed_at`, `review_notes` | | | |

State machine is a plain Selection; the workflow test advances it with `write()`: draft -> ai_generated (confidence 0.72) -> pending_review -> reviewed (+reviewed_by_id). No `action_*` methods, no guards (not seen). Service Plan 8.1 describes four layers (parser, rule engine, LLM polish, Pro technician review: "Pro tier customers have every diagnosis routed through John's review queue"). Only the data layer exists; the engine/LLM orchestration is explicitly listed as hand-off in the status doc ("needs the running scanner firmware and Ollama endpoint").

Plan-vs-code gap in the report: Service Plan 5.6 lists `triage_outcome`, `summary_source` (`rule_only`/`rule_plus_llm`/`llm_with_review`), `generation_engine`, `technician_review_state`, `customer_acknowledged`. None exist in the implemented model.

### `alfa_core_diagnosis.recommendation`
`report_id` (req), `name` (req), `description`, `action_type` Selection (req) **inspect / replace_part / service / test_drive / recall_check / monitor / do_not_drive**, `related_part_id` -> alfa_parts.part, `related_kit_id` -> alfa_parts.part.kit, `confidence` Float (default 0.0), `sequence`.
(Service Plan 5.7 uses a different action_type set - book_service, order_parts, diy_guide, monitor, clear_codes, escalate_to_technician - and `priority`, cost range; not implemented.)

### `alfa_core_diagnosis.dtc` (library; not mail.thread)
`code` (req, UNIQUE, indexed), `name` (req; "Description"), `description_long` ("Customer-facing plain-English explanation"), `category` powertrain/body/chassis/network (req), `severity` info / warn / severe / safety_critical (req, default warn; "Safety-critical codes block save-for-later in the customer PWA."), `typical_causes`, `fits_platform_ids`, `is_safety_critical` (stored compute; the method has no `@api.depends` in the file as read), `active`.
Seed: P0301, P0507, C0561, C1095, P200A, P0234 (6 entries; the 5000+1500 corpus is a separate curation deliverable per CLAUDE.md).
Docstring: "Seeded from SAE J2012 and OEM-specific Stellantis codes." No revision/versioning fields (Service Plan 8.3 promises `revision`, `revised_by_id`, `revised_at`; not seen).

### `alfa_core_diagnosis.triage_rule` (Pattern 6 config-as-data)
`name`, `code` ("Stable identifier"), `sequence`, `priority` (default 50), `dtc_pattern` Char ("DTC code or pattern (e.g. 'P030[0-9]' for any misfire)"), `pid_condition` Char ("e.g. 'coolant_temp > 110'. Evaluated by the diagnosis engine." - engine not in repo files read), `recommended_action` Text (req), `confidence_base` Float default 0.7 ("Adjusted by signal corroboration in the engine"), `severity` (req), `fits_platform_ids`, `fits_engine_ids`, `active`.

ACL: dtc user R / advisor RW / manager RWCU; triage_rule advisor RW / manager RWCU; report advisor RWC / manager RWCU / portal R; recommendation same.

---

## 8. alfa_core_inspection

Depends alfa_core, alfa_fleet, alfa_service, alfa_parts, hr. Seeds: Spring-Readiness 18-point and Track-Prep QV templates (status doc).

### `alfa_core_inspection.template` and `.template_item`
Template: `name`, `code` (req), `version` Integer (default 1; help "Published templates are immutable; amendments create a new version" - no enforcing code seen), `item_ids`, `fits_platform_ids`, `estimated_duration_minutes`, `requires_lift`, `state` draft / published / retired; UNIQUE(code, version); `action_publish` (draft only; raises "Cannot publish template with no items."), `action_retire`.
Item: `name`, `description` ("Inspection criteria - what to look for, threshold values"), `category` (brakes, suspension, steering, drivetrain, tires, fluids, electrical, body, interior, safety, other), `measurement_type` pass_fail (default) / measurement / photo / text, `measurement_units`, `threshold_pass` ("value at or above which item passes"), `threshold_warn` ("at or above which item warns. Below = fail."), `is_safety_critical`.

### `alfa_core_inspection.inspection`
`name` (sequence), `template_id` (req; domain published only), `template_version` (snapshot at create), `vehicle_id` (req), `sale_order_id`, `technician_id` (hr.employee), `bay_id`, `started_at`, `completed_at`, `customer_reviewed_at`, finding counters (pass/warn/fail), `safety_critical_fail`, `estimated_remediation_total`, `approved_remediation_total`, `currency_id`, `inference_zde` (default True; "If True, photos and notes stay on local infra only."), `state`.
**State machine**: draft -> (`action_start`) in_progress -> (`action_submit_for_review`; blocked if any finding `not_checked`) pending_review -> (`action_send_to_customer`; all-pass auto-sets approved, else) customer_review -> (`action_record_customer_decision`; blocked while any warn/fail finding is still `pending`) approved / partially_approved / declined -> (`action_apply_to_so`; creates one sale.order.line per approved finding) applied; `action_cancel` -> cancelled. Each transition posts chatter. On create, one finding per template item is instantiated (state `not_checked`).

### `alfa_core_inspection.finding`
`inspection_id`, `template_item_id`, `name`, `category`, `measurement_type`, `measurement_value` Float, `measurement_units`, `photo` Image (max 1920x1080), `note`, `state` not_checked / pass / warn / fail / not_applicable, `is_safety_critical`, `remediation_recommended`, `remediation_cost`, `remediation_part_id`, `remediation_kit_id`, `remediation_urgency` immediate / soon / scheduled / monitor, `customer_decision` pending / approved / declined / defer, `customer_decision_at`, `customer_decision_note`. Actions: `action_mark_pass` (also sets customer_decision approved), `action_mark_warn`, `action_mark_fail`, `action_customer_approve`, `action_customer_decline`.

`sale.order` extension: `inspection_ids`, `inspection_count`, `action_view_inspections`.
ACL: template user/advisor R, manager RWCU; inspection advisor RWC, portal R; finding advisor RWC, portal RW.

---

## 9. alfa_core_app_api (companion PWA REST API)

Depends alfa_core, alfa_fleet, alfa_core_scanner, alfa_core_diagnosis; external python dep `pyjwt`. (README of the module lists `alfa_core_portal, sms`; manifest does not.)

### Endpoints (controller `controllers/api_v1.py`; spec `docs/api/alfacore-v1-openapi.yaml`)

| # | Method + path | Route type / auth | Rate limits |
|---|---|---|---|
| 1 | `POST /api/v1/auth` | `type="jsonrpc"`, `auth="public"`, csrf off | `auth` profile per client IP |
| 2 | `POST /api/v1/scans` | `type="jsonrpc"`, public + `_require_token` | `api_ip` then `api_read` |
| 3 | `GET /api/v1/diagnoses/<int:report_id>` | `type="http"`, `_require_token` | same |
| 4 | `GET /api/v1/vehicles/<vin>/preferences` | `type="http"`, `_require_token` | same |
| 5 | `GET /api/v1/vehicles/<vin>/recalls` | `type="http"`, `_require_token` | same |

**1. POST /api/v1/auth** - request `{login, password}` (portal user credentials checked via Odoo `res.users.authenticate`). Success response:
`{"token": "<JWT>", "expires_at": "<ISO datetime>", "partner": {"id": <int>, "name": "<str>"}}`.
Errors (returned as `{"error": ...}`): `rate_limit_exceeded` (+ `retry_after_seconds`), `missing_credentials`, `pyjwt_not_installed`, `invalid_credentials`, `jwt_secret_not_configured`.
JWT: HS256; claims `sub` (partner id as string), `jti`, `scope` ("pwa"), `iat`, `exp` (= token record `expires_at`). Token record created by `issue_for_partner(partner_id, scope="pwa", ttl_days=30)`. No refresh endpoint ("there is no refresh endpoint in v1"). Service Plan 7.4 had planned `/auth/login`, `/auth/refresh`, 24h expiry, plus `/device/pair`, `/device/heartbeat`, `/vehicle/list`, `/scan/<id>/status` etc.; those were NOT implemented (only the 5 above).

**2. POST /api/v1/scans** - Bearer token required. Request body (kwargs):
```
{ "vehicle_vin": "<17-char VIN, required>",
  "started_at": "<datetime>", "ended_at": "<datetime>",
  "modules_scanned": "ECM,TCM,ABS",
  "battery_voltage": 12.6, "mileage_at_scan": 89247,
  "dtcs": [ {"code": "P0301", "status": "active|pending|history|permanent",
             "module": "ECM", "freeze_frame": "<text>", "raw": "<text>"} ],
  "pids": [ {"pid": "010C", "name": "Engine RPM", "value": 847, "units": "rpm"} ] }
```
Server steps: look up vehicle by `vin.upper()`; caller's partner must be among the vehicle's active ownership partners (any role); find a device with `partner_id = caller` AND `vehicle_id = vehicle` (else `no_paired_device_for_vehicle`); create a `scan_session` with `state="uploaded"`; create one `scan_dtc` per entry (`status` default "active"), one `scan_pid` per entry.
Success: `{"session_id": <int>, "name": "AC-SCAN-YYYY-NNNNNN", "dtc_count": <int>}`.
Errors: `vehicle_vin_required`, `vehicle_not_found` (+ `vin`), `not_authorized_for_this_vehicle`, `no_paired_device_for_vehicle`, plus the token errors below.
Not idempotent: README: "server creates a new session per request. Track scan UUIDs client-side and avoid resending." (Service Plan 5.3 planned `session_uuid` for idempotency; absent from the model.) No DTC-code format validation in the controller (the OpenAPI schema declares pattern `^[PBCU][0-9A-F]{4}$`). OpenAPI types `pids[].value` as string, while the model field is Float.
The response does not return a diagnosis id; README notes the id is only reachable via `scan_session.diagnosis_report_id` and "needs a dedicated lookup endpoint or webhook".

**3. GET /api/v1/diagnoses/{report_id}** - 404 `{"error":"not_found"}`; 403 `{"error":"not_authorized"}` unless `report.partner_id` (the vehicle's active primary driver) equals the caller. Response:
`{"id","name","vehicle_vin","state","confidence","severity","summary","recommendations":[{"id","name","description","action_type","confidence"}]}`.
It does not filter on state (the portal pages only list reviewed/delivered), and omits `technical_summary`, `reviewed_by`, `related_part/kit`.

**4. GET /api/v1/vehicles/{vin}/preferences** - 404 `vehicle_not_found`; 403 `not_authorized` (non-owner). Response `{"vin", "preferences":[{"category","name","spec","brand_preference"}]}` (active rows only).

**5. GET /api/v1/vehicles/{vin}/recalls** - same ownership checks. Targets in states identified / notified / acknowledged / scheduled only. Response:
`{"vin","open_recall_count","do_not_drive": <true if any open campaign severity == safety_critical>, "recalls":[{"campaign_id","campaign_name","source","source_id","source_url","severity","campaign_type","affected_components","risk_summary","remedy_summary","estimated_remedy_hours","issued_date","target_state","last_notified_at","notification_attempts","scheduled_so"}]}`.

**Auth decorator `_require_token`** (applies to 2-5), in order: `Authorization: Bearer <token>` else 401 `missing_bearer_token`; `jwt_secret_manager.verify_token`; 401 `token_expired` / `invalid_token`; `alfa_core_app_api.token` row with matching `jti` and `state=active` else 401 `token_revoked_or_unknown`; IP limit; token limit; then updates `last_used_at` and `last_used_ip` on the token row. Client IP = first `X-Forwarded-For` entry when present, else remote address.
Status-code note: errors on the two `jsonrpc` routes are returned as `{"error": ...}` dicts by the controller; the OpenAPI document shows 400/401/412 for them. The README curl examples send plain JSON bodies; whether Odoo 19 `type="jsonrpc"` accepts that vs a JSON-RPC envelope was not verifiable from the files I read. (Handoff 3.10 recorded that the routes were being migrated from deprecated `type='json'` to `jsonrpc`.)

### `alfa_core_app_api.token`
`jti` (req, UNIQUE, indexed), `partner_id` (req, cascade), `issued_at`, `expires_at` (req), `last_used_at`, `last_used_ip`, `scope` (default "pwa"; comment mentions 'admin' advisor tools), `state` active (default) / revoked / expired. `action_revoke()`; cron `expire_stale()` hourly. ACL: manager RWCU, PIPEDA officer R only.

### JWT secret rotation (`alfa_core_app_api.jwt_secret_manager`, abstract)
- Two `ir.config_parameter` slots: current secret and previous secret, plus a `rotated_at` timestamp. Seed data ships a placeholder current value that must be replaced; `action_rotate_secret()` treats a missing / placeholder / `dev-`-prefixed current value as first-time initialisation ("status: initialized"), otherwise moves current -> previous and generates a new current with `secrets.token_urlsafe(32)` ("status: rotated", returns `grace_until`).
- `verify_token()` tries current; on `InvalidSignatureError` falls back to previous (logs the jti), else re-raises. New tokens are always signed with current.
- Grace window `GRACE_DAYS = 30`; `cron_clear_stale_previous()` (daily) clears the previous slot when `rotated_at` is older than 30 days; manual `action_clear_previous_secret()`. If the timestamp is missing the cron refuses to clear and logs a warning.

### Rate limiter (`models/rate_limiter.py`, token bucket, in-memory)
| Profile | Burst (capacity) | Sustained | Key |
|---|---|---|---|
| `auth` | 5 | 10/min | client IP |
| `api_read` | 30 | 120/min | caller partner id |
| `api_ip` | 100 | 600/min | client IP |
Unknown profile fails open. LRU-evicted at `MAX_BUCKETS = 5000`; thread-safe via a lock; per-worker process state. Documented boundary: "For multi-worker or multi-replica production, this needs Redis-backed shared state"; `RateLimiter.check()` is the swap point.
Denial on the http routes: HTTP 429, body `{"error":"rate_limit_exceeded","retry_after_seconds":<float>}`, header `Retry-After: <int>`. On `/auth` (jsonrpc) the controller returns the same body as a plain dict without setting 429.

---

## 10. alfa_tsb (record schema for a TSB catalogue)

Depends alfa_core, alfa_fleet; external python dep `qdrant_client`. Docstring: "TSBs are the manufacturer's accumulated diagnostic wisdom... chunked, embedded into Qdrant, and retrieved during diagnosis"; the module "owns the document side; the RAG retrieval lives in the diagnosis pipeline (Sprint 6+)" (not wired - handoff 5.3).

### `alfa_tsb.tsb` (`mail.thread`)
| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | Char | yes | TSB title |
| `bulletin_number` | Char | yes | indexed, `copy=False`; help example `'07-080-21'`. UNIQUE(bulletin_number, manufacturer) |
| `manufacturer` | Char | yes | default "Alfa Romeo" |
| `issued_date` | Date | no | |
| `supersedes_id`, `superseded_by_id` | M2O self | no | supersession chain |
| `summary` | Text (translate) | no | |
| `symptoms` | Text (translate) | no | plain-language |
| `procedure` | Text (translate) | no | "Step-by-step repair / diagnostic procedure" (single free-text field) |
| `source_url` | Char | no | |
| `document_attachment_id` | M2O ir.attachment | no | Source PDF |
| `full_text` | Text | no | "Source of truth for chunking" |
| `fits_platform_ids` | M2M alfa_fleet.platform | no | |
| `fits_engine_ids` | M2M alfa_fleet.engine | no | |
| `affected_year_from`, `affected_year_to` | Integer | no | |
| `related_dtc_codes` | Char | no | "Comma-separated DTC codes this TSB addresses, e.g. 'P0234,P200A'" |
| `state` | Selection | yes | draft (default) / published / chunked / indexed ("Indexed (Qdrant)") / retired |
| `chunk_ids`, `chunk_count`, `indexed_chunk_count`, `indexed_at` | | | |

Methods: `action_chunk()` (naive paragraph splitter, max 1500 chars per chunk, clears and recreates chunks, sets `chunked`); `action_index_to_qdrant()` (calls the stub client, sets `indexed`).

### `alfa_tsb.chunk`
`tsb_id`, `chunk_index` (UNIQUE per tsb), `text` (req), `qdrant_point_id`, `qdrant_collection` (default `alfa_tsb_v1`), `embedding_model` (default `bge-large-en-v1.5`, "Cache invalidation key"), `indexed_at`.

### `alfa_tsb.qdrant_collection`
`name` (UNIQUE), `vector_size` (default 1024), `distance_metric` cosine/dot/euclid, `embedding_model`, `point_count`, `last_synced_at`, plus host/port fields (defaults not recorded here).

### `alfa_tsb.qdrant_client` (abstract) - DOCUMENTED STUB BOUNDARY
Docstring: "Qdrant client - STUB." `index_chunks` sets `qdrant_point_id = "stub-<id>"` and `indexed_at` without embedding or upserting; `search` returns `[]`; `ensure_collection` only records a row locally. Status doc: Sprint 13 "index_chunks() marks records as indexed without actually upserting. search() returns empty. Production: route to Ollama for embedding (bge-large-en-v1.5, 1024-dim), upsert to Qdrant".
Consequence: `state=indexed` and `indexed_at` do not prove real indexing today.

ACL: tsb user R / advisor RWC / manager RWCU; chunk advisor R / manager RWCU; collection manager RWCU.

---

## 11. alfa_core_campaign (recall / campaign schema)

Depends alfa_core, alfa_fleet, sale_management. Cron `AlfaCore: poll NHTSA recall feed` every 24 hours, active.

### `alfa_core_campaign.campaign` (`mail.thread` + activity)
| Field | Type | Req | Notes |
|---|---|---|---|
| `name` | Char | yes | display name |
| `campaign_type` | Selection | yes | **safety_recall (default) / emissions_recall / service_campaign / tsb / warranty_extension** |
| `source` | Selection | yes | **nhtsa (default) / transport_canada / manufacturer / other**; indexed |
| `source_id` | Char | no | e.g. "23V456000"; UNIQUE(source, source_id) |
| `source_url` | Char | no | |
| `manufacturer` | Char | no | default "Alfa Romeo" |
| `affected_components` | Char | no | "Brief component list" |
| `risk_summary`, `remedy_summary` | Text (translate) | no | |
| `estimated_remedy_hours` | Float | no | |
| `severity` | Selection | yes | **safety_critical ("do-not-drive") / high / medium (default) / low (informational)** |
| `issued_date` | Date | no | |
| `received_at` | Datetime | no | default now |
| `fits_platform_ids`, `fits_engine_ids` | M2M | no | |
| `affected_year_from`, `affected_year_to` | Integer | no | |
| `vin_pattern` | Char | no | substring match (code: `p in vin`), not regex despite the help text "substring or regex" |
| `state` | Selection | yes | draft (default) / imported / targeting / notifying / active / closed |
| `target_ids`, `target_count`, `notified_count`, `serviced_count` | | | computed stats |

`action_target_vehicles()` builds a vehicle domain from platform / engine / year range, filters by `vin_pattern`, creates missing targets (idempotent), sets `state="targeting"`. `action_close()`. Nothing in the files read advances `targeting` -> `notifying` -> `active`.

### `alfa_core_campaign.target` (`mail.thread`)
`campaign_id`, `vehicle_id` (both req, cascade), `partner_id` (computed from active primary driver), `state` **identified (default) / notified / acknowledged / scheduled / serviced / declined / unreachable**, `notification_ids`, `last_notified_at`, `notification_attempts`, `scheduled_so_id` -> sale.order, `serviced_at`. UNIQUE(campaign_id, vehicle_id).

### `alfa_core_campaign.notification` (`mail.thread`)
`target_id`, `campaign_id`/`partner_id`/`vehicle_id` (related), `channel` email / sms / portal / phone / mail (req), `sent_at`, `response` none (default) / acknowledged / scheduled / declined / bounce, `response_at`, `message_text`. `action_mark_sent()` only stamps `sent_at`, moves an `identified` target to `notified` and increments attempts - no channel dispatch code exists in these three files (manifest summary says "customer notification dispatch").

### `alfa_core_campaign.nhtsa_client` (abstract; `models/nhtsa_client.py`) - shipped, not a stub
- Source: the NHTSA `recalls/recallsByVehicle` endpoint (public, no auth), params `make`, `model`, `modelYear`; once per distinct (make, model, year) of vehicles in state active / in_service (via `read_group`).
- HTTP: connect/read timeouts 10 s / 30 s; 3 attempts with exponential backoff (2 s, 4 s, 8 s); 4xx returns `[]` without retry; 1.1 s sleep between calls (advisory 1 req/s); failures are logged and skipped ("never crash the cron").
- Response parsing accepts `results` or `Results`. Mapping of an NHTSA record to a campaign: `NHTSACampaignNumber` -> `source_id` (record skipped if missing); `Manufacturer` -> `manufacturer`; `Component` -> `affected_components` (first 255 chars); `Summary` (+ "Consequence: ..." if different) -> `risk_summary`; `Remedy` -> `remedy_summary` with prefix flags "PARK IT - do not drive until remedied" (`parkIt`), "PARK OUTSIDE - fire/explosion risk" (`parkOutSide`), "OTA remediable - may not require dealer visit" (`overTheAirUpdate`); `ReportReceivedDate` parsed as `DD/MM/YYYY` -> `issued_date`; `campaign_type="safety_recall"`; `severity = safety_critical` if `parkIt` or `parkOutSide`, else `high`; new rows get `name = "<Manufacturer>: <first component>"` (truncated to 200) and `state="imported"`.
- Upsert key: `(source='nhtsa', source_id)`; existing rows are `write()`n, new rows created, then `action_target_vehicles()` is run on all campaigns in `imported`. Returns a summary dict: `tuples_queried`, `tuples_failed`, `campaigns_imported`, `campaigns_updated`, `campaigns_targeted`.
- Only NHTSA is implemented; `transport_canada`, `manufacturer`, `other` are selection values with no poller (the user is in Canada; Transport Canada ingestion is not present).

ACL: campaign user R / advisor RWC / manager RWCU; target advisor RWC / manager RWCU / portal R; notification advisor RWC / manager RWCU.

---

## 12. alfa_core_portal

Depends alfa_core, alfa_fleet, alfa_core_diagnosis, alfa_core_inspection, alfa_core_loaner, portal, website. Extends `CustomerPortal`. All routes `auth="user"`, website=True.
Routes: `/my/vehicles` (+ paging, sort) and `/my/vehicles/<id>`; `/my/diagnoses` (only states `reviewed`, `delivered`) and `/my/diagnoses/<id>`; `/my/inspections` (states customer_review, approved, partially_approved, declined, applied) and `/my/inspections/<id>`; `POST /my/inspections/<id>/decide` (csrf on; only while state is `customer_review`; form keys `finding_<id>` = approved | declined | defer, sets `customer_decision` and `customer_decision_at`); `/my/loaners`. Home counters: vehicle_count, diagnosis_count, inspection_pending_count, loaner_count.
Row security (`ir.rule`, group `base.group_portal`): own vehicles (active ownership), own diagnoses (`partner_id = user.partner_id`), own inspections (via vehicle ownership), findings (write allowed on own), own loaner allocations. Note that the inspection decide route does not call `action_record_customer_decision`; moving the inspection out of `customer_review` is a separate advisor action.

## 13. alfa_core_multi_loc

P3 stub, depends alfa_core. `models/__init__.py` contains only a comment ("Models will be added here as the module is implemented"); the ACL CSV has a header row only. Blueprint 12 (single-operator at v1) is the design reference. Nothing to integrate.

---

## 14. Stub and hand-off boundaries (documented in code or status doc)

| Boundary | Where | State |
|---|---|---|
| Qdrant embed / index / search | `alfa_tsb.qdrant_client` | STUB (fake point ids, empty search) |
| VIN decode via NHTSA vPIC | `alfa_fleet.vehicle.action_decode_vin` | STUB (chatter message only) |
| Diagnosis engine: parse -> rules -> LLM -> report generation, `triage_rule.pid_condition` evaluation | status doc "Sprint 5/6" hand-off | not in repo files read; data model only |
| Real BLE pairing / scanner firmware | status doc | out of scope ("no PCB, no firmware") |
| Rate limiter shared state | `rate_limiter.py` | in-memory; Redis swap point is `RateLimiter.check()` |
| Customer-notification channel dispatch | `alfa_core_campaign.notification` | records only |
| Odoo Sign template variable substitution / email branding | `alfa_core_loaner` | hand-off (out of scope here) |
| Transport Canada / manufacturer campaign feeds | `campaign.source` values | no poller |
| Diagnosis id lookup after scan upload | `docs/api/README.md` | "needs a dedicated lookup endpoint or webhook" |
| Multi-location | `alfa_core_multi_loc` | empty stub |

---

## 15. Integration hooks (what a CUORE connector should write to)

Principle from CLAUDE.md: add fields by `_inherit` in a new connector module that depends on the module owning the model; do not define parallel models; models carry explicit ACLs.

### 15.1 Preconditions in AlfaCore
1. `alfa_fleet.vehicle` must exist: `vin` (ISO 3779 regex, uppercased by the model), `year`, `model` required. Optionally link `platform_id` / `engine_id` / `trim_id` (seed codes: giorgio, GME_2_0T, etc.).
2. For the REST path: an active `alfa_fleet.vehicle.ownership` row for the authenticating portal user's partner, and an `alfa_core_scanner.device` whose `partner_id` and `vehicle_id` equal that partner and vehicle. For a wired adapter use `model_name = other`, unique `serial_number`.
3. Privacy flag: set `inference_zde` consistently (True = nothing left the host). Defaults are True on scan_session, report, inspection and subscription.

### 15.2 Write targets
| Purpose | Preferred route | Target | Required / notable fields |
|---|---|---|---|
| Upload a scan (DTCs + PIDs) | `POST /api/v1/scans` (supported contract; needs portal-user bearer token; limit 120/min per token, 600/min per IP) | `alfa_core_scanner.scan_session` + `.scan_dtc` + `.scan_pid` | `vehicle_vin`; `dtcs[].code/status/module/freeze_frame/raw`; `pids[].pid/name/value/units`; creates session in `uploaded` |
| Richer scan data than the API carries | Odoo ORM/RPC as an advisor (or manager) user | same three models | session needs `vehicle_id`, `device_id`, `started_at`; dtc needs `dtc_code`; pid needs `pid_id`; advisor has RWC on all three (portal cannot create dtc/pid) |
| Diagnosis verdict | ORM/RPC | `alfa_core_diagnosis.report` (+ `.recommendation`) | `scan_session_id` required; set `state` (use `draft`/`ai_generated`/`pending_review`; portal shows only `reviewed`/`delivered`), `confidence` 0-1, `severity` (info/warn/severe/safety_critical), `summary`, `technical_summary`, `inference_zde`; recommendations: `name`, `action_type` (7 values), `related_part_id`, `confidence` |
| Parts | ORM/RPC | `alfa_parts.part` (UNIQUE canonical number), `.part.alternative` (grade safe/interim/not_recommended + required `rationale`) | use `find_by_part_number` before create |
| TSB catalogue | ORM/RPC | `alfa_tsb.tsb` | `name`, `bulletin_number` + `manufacturer` unique; `related_dtc_codes` (comma string); `symptoms`, `procedure`, `summary`; `fits_platform_ids`, `fits_engine_ids`, `affected_year_from/to`; `supersedes_id`; `source_url`; keep `state` at `draft`/`published` (do not set `indexed` - indexing is a stub) |
| Recall / campaign catalogue | ORM/RPC | `alfa_core_campaign.campaign` (`campaign_type = tsb` is also a valid value) | `name`, `source` (`manufacturer`/`other`), `source_id` (unique per source), `severity`, fitment fields, `vin_pattern` (substring); then `action_target_vehicles()` |
| Service history | ORM/RPC | `sale.order` fields `alfa_vehicle_id`, `alfa_service_state`; `alfa_core_inspection.inspection/finding` | inspection requires a published template |

CUORE catalogue -> AlfaCore mapping notes: DTC-to-TSB cross reference lives only as the Char `alfa_tsb.tsb.related_dtc_codes` (no M2M to `alfa_core_diagnosis.dtc`; Service Plan's `tsb_reference_ids` on the DTC library is not implemented); platform/engine fitment uses record references, so CUORE model/engine codes must be mapped to `alfa_fleet.platform.code` / `alfa_fleet.engine.code`.

### 15.3 Gaps: CUORE data with no AlfaCore home
| CUORE concept | Closest AlfaCore field | Gap |
|---|---|---|
| UDS DTC status bytes (ISO 14229 status mask bits: testFailed, confirmed, pending, warning indicator, etc.) | `scan_dtc.dtc_status` (4 values: active/pending/history/permanent), `raw_payload` Text | Status byte and its bits are not represented; only a 4-way label. Would need a new Char/Integer `status_byte` plus decoded flags on `scan_dtc` (proposal) |
| Decoded freeze frames | `scan_dtc.freeze_frame_data` Text (Service Plan calls it a "JSON dump"; API example uses plain text) | No structured parameter/value/unit rows; Mode 02 vs UDS snapshot/extended-data distinction not modelled |
| Mode 06 on-board test results | none (`scan_pid` is PID-shaped: one Float `value`, no TID/CID, min/max limits, pass/fail) | Entire concept missing; no mention of Mode 06 in code or docs read |
| Evidence class labels (reading / inference / outside literature) | `report.summary` vs `technical_summary`; `confidence` Floats; `alternative.grade` + `rationale` + `source_reference` | No per-statement provenance enum. Planned `summary_source` (rule_only / rule_plus_llm / llm_with_review) is not implemented and is about generation method, not claim evidence |
| Mechanic steps | `tsb.procedure` Text; inspection template `item.description`; `recommendation.description` | No ordered step model, no tools/specs/torque per step, no step completion state |
| Proof-of-fix criteria / verification | `quality.check.pass_threshold_note` and `state` (passed/failed/waived); inspection `threshold_pass/threshold_warn`; `campaign.target.state=serviced` + `serviced_at` | No link from a repair to a post-repair rescan, no "code returned within N drive cycles" criterion, no before/after comparison, no clear-codes event record |
| Bus / cable metadata (CAN line, gateway bypass, adapter type, cable) | `device.model_name` (3 BLE-oriented values), `device.firmware_version`, `scan_session.modules_scanned` (CSV), `scan_dtc.module_source` (free text) | No bus, protocol, ECU address, transport, cable or adapter fields. Service Plan lists `protocol` and `modules_queried/responded` (ECU addresses) on the session; the implemented model omits them |
| ECU calibration ID / CVN (Mode 09), software versions | none (Service Plan 6.3 says Mode 09 is read) | No storage on session or vehicle |
| Idempotent upload key | none (Service Plan planned `session_uuid`) | Re-sending creates duplicates; connector must dedupe client-side |
| DTC occurrence_count, first_seen, link to library | none (`dtc_code` is a Char; Plan 5.4 lists them) | Not implemented |
| Per-session `inference_zde` inheritance | field exists; no copy logic seen | Connector should set explicitly |

### 15.4 Cautions
- The spec/docs and code disagree in places (endpoint set, token TTL 24 h vs 30 days, state names); trust the controller code for behaviour, and the OpenAPI file only for field shapes.
- Immutability and transition rules described in docs (scan sessions, published templates, diagnosis reports, service-state edges) are conventions; the model code read does not enforce them.
- `state = indexed` on TSB rows is not evidence of real vector indexing (stub client).
- The auth endpoint takes a real portal user's password; a connector needs its own dedicated portal user and token handling. No credentials are recorded in this file.
