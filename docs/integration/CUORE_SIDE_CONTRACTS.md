# CUORE side contracts for AlfaCore

Status: draft 1, 2026-10-22. Derived by reading the code in this repo; nothing here is a promise that an export or sync feature exists. CUORE has **no AlfaCore integration code today** (no export job, no outbound queue, no station identity, no TLS). Where this document says "proposed" it describes what must be added; everything else describes what is in the code now.

Companion file: `ALFACORE_MODEL_MAP.md` (the AlfaCore side of the mapping, written separately).

Conventions used below:

- "State dir" is `%PROGRAMDATA%\cuore` (override `CUORE_STATE_DIR`; fallbacks `%LOCALAPPDATA%\cuore`, then `~/.cuore`). Same resolution in `cuore/live/config.py` and `mes-log-mcp/mes/jobs.py`.
- Every store is append-only JSON Lines unless noted. Nothing is rewritten in place except small JSON state files (`addresses.json`, `fullscan_guided.json`, `fullscan_last.json`, `checklists.json`, `mes_clear_watch.json`, `learned_dids.json`).
- Timestamps are `datetime.now().isoformat(timespec="seconds")`: **naive local time, no UTC offset**. See 1.2 and 2.4.
- `<VIN>` stands for a 17-character VIN. No real VINs appear in this file.

---

## Part 1. Data contracts

### 1.1 What lives where (state dir)

| File | Writer | Content |
|---|---|---|
| `observations.jsonl` | `cuore/live/store.py` | Every read from the car (and tests/replays, tagged by `stream`). Section 1.3 to 1.5. |
| `jobs.jsonl` | `mes-log-mcp/mes/jobs.py` | Job ledger as `op` records (section 1.8). Folded on read. |
| `fullscan_guided.json` | `cuore/live/fullscan.py` | The one open (or last closed) guided scan session (1.6). |
| `fullscan_last.json` | same | Last `scan_coverage` result (also rewritten at every guided segment). |
| `addresses.json` | `store.confirm_target` | `{<VIN>: {<module>: {target:"XX", source, at}}}` confirmed module addresses. |
| `attested.jsonl` | `cuore/live/attested.py` | Mechanic-typed measurement/source/photo facts (owner-attested class). |
| `owner_events.jsonl` | `cuore/live/owner_events.py` | "Tell CUORE" owner/driver/mechanic reports (owner-attested class). |
| `audit.jsonl` | `cuore/live/audit.py` | Adapter command audit (every send, clears, actuations). |
| `notes.jsonl`, `symptoms.jsonl`, `feedback.jsonl`, `cases.jsonl`, `shop_visits.jsonl`, `experience_inputs.jsonl`, `live_snapshots.jsonl` | various | Supporting per-vehicle records. |
| `media/`, `recordings/`, `logs/`, `clears/`, `scans/<VIN>/`, `bench/` | various | Files: photos, CSV recordings, server logs, pre-clear evidence JSON, MES-style scan exports. |

The first two rows are the ones AlfaCore needs for diagnosis data; the rest is context.

### 1.2 Identity and keys

| Entity | Key today | Shape | Uniqueness caveat |
|---|---|---|---|
| Vehicle | `vin` | 17 chars, upper case | Some observations carry `vin: ""` (Mode 03/06/0A reads do not know the VIN). `scanlog` borrows the VIN from neighbours in the same cluster; the xref and scan-requirements bridges assume a single-car store and keep untagged rows. A multi-car sync must resolve this on the CUORE side before upload. |
| Scan (full or guided) | `scan_id` | `SCAN_YYMMDDHHMM`, minute resolution (`fullscan.run`, `run_guided`, `scanlog.ID_FMT`) | Not unique across stations and not unique for two scans of one car in the same minute. Proposed upload key: `(station_id, vin, scan_id)`. |
| Observation | none | Envelope has no id | Proposed key: `station_id + at + kind + sha256(canonical json of data)[:16]`. Do not use the file line number: the file has been hand-edited before (`.bak-` copies exist). |
| Job | `id` | `uuid4().hex[:12]` (48 random bits) | Unique in practice. Prefix with `station_id` anyway. |
| Hypothesis, action | `id` | `uuid4().hex[:8]` | Unique **within a job only**. Key as `(job_id, hyp_id)` and `(job_id, action_id)`. |
| Attested row | `id` | `uuid4().hex` | Unique. |
| Owner event | `id` | see `owner_events.py` | Unique. |
| Bulletin | `id` (catalogue row id, e.g. `tsb-18-030-17-rev-b`) and `number` (as printed) | strings | `id` is the stable key; xref and jobs cross-link on `id` (evidence ref kind `bulletin`). |

Observations do **not** carry a scan id. A scan's observations are identified by time window: start = the scan id's timestamp, end = the newest `scan_coverage` observation bearing that `scan_id` (or a 15-minute gap rule if none). `scan_requirements_bridge._build_ctx` and `scanlog._clusters` both implement this. An exporter must either replicate that window rule or (proposed) stamp `scan_id` into each observation at write time.

### 1.3 Observation envelope

One JSON object per line in `observations.jsonl`:

```json
{ "at": "2026-10-22T14:05:31", "kind": "module_dtcs", "vin": "<VIN>",
  "bus": "can_c", "cable": "none", "stream": "serial COM3@115200", "data": { } }
```

| Field | Meaning |
|---|---|
| `at` | Naive local time, seconds. |
| `kind` | Observation kind (1.4). |
| `vin` | May be `""`. |
| `bus` | `can_c` (500 kbps, OBD pins 6/14, no cable), `can_ihs` (125 kbps, blue A5 cable), `can_ch` (500 kbps, grey A6 cable; brakes, airbags, steering) or `""` for whole-scan records. |
| `cable` | `none`, `blue_a5`, `grey_a6` as declared by the operator. |
| `stream` | What produced it: `serial COM3@115200` (real adapter), `recording(serial ...)` (replay of a real capture), `scripted`, `playback ...` (tests/replays). |

**Only streams starting with `serial` or `recording(serial` are evidence about a car** (`store.is_from_car`). AlfaCore must carry `stream` (or a derived `from_car` boolean) and must never present a non-car observation as a reading. The scan-requirements result reports `non_car_observations` for this reason.

`data` is the result dict of the adapter call, stamped with `bus` and `cable`. Failures are data, not exceptions: `error` (string, "ADAPTER/BUS ERROR ... NOT 'no codes'"), `nrc` (negative response text), `warning` ("no answer from the module"), `note`. An empty DTC list with `error` set means **the read did not complete**, not that the car is clean. The exporter must preserve those fields.

### 1.4 Observation kinds and data shapes

Kinds written by the full-scan and guided-scan path (`cuore/live/fullscan.py`) first, then kinds written elsewhere. Shapes are what the code writes; fields marked (opt) are not always present.

| Kind | Written by | `data` shape |
|---|---|---|
| `scan_coverage` | `fullscan.run`, `_record_guided_coverage` | `{scan_id, vin, cable, buses_attempted:[bus], duration_s, sessions_opened, steps:[{step, ok, error?}], coverage:[{bus, module, category, why, active, history, not_run, did?}], counts:{active, history, not_run}, guided?:true, guided_status?}`. `category` is `answered`, `silent` (module did not reply) or `not_reachable` (no cable, no confirmed address, NRC, adapter error, skipped). `did` (opt) is `{did, name, source}` or an `UNKNOWN: ...` string. **Rewritten (appended anew) after every guided segment**; the latest record per `scan_id` is the truth, earlier ones are partial. |
| `module_dtcs` | `fullscan._sweep_bus_modules`, `ops.module_dtcs` | Sweep form: `{ecu, bus, dtcs:[{code, status, flags}]}`. Direct-read form (`ops.module_dtcs`) is the full UDS result: `{ecu, bus, mask, error, nrc, dtcs:[{code, raw, status, flags}], codes, availability_mask, warning?, note?}`. `code` is `P0456-00` (5-char DTC, dash, failure-type byte). `status` is the UDS status byte as an int; `flags` is its decode (1.7). |
| `obd_dtcs` | `fullscan._obd_readout`, `ops.obd_dtcs` | `{dtc_kind:"stored"\|"pending"\|"permanent", kind, raw, dtcs:[code], by_ecu:{<header>:[code]}, error?, warning?, note?, bus, cable}`. Legislated Mode 03/07/0A. Codes here have no failure-type byte. |
| `freeze_frame` | `fullscan._obd_readout` | One record per stored code: `{code, ecu, frame:{<pid hex>:{name, value, unit}}}`. (Mode 02.) |
| `freeze_frame_set` | `ops.obd_freeze_frames` | `{by_ecu:{<header>:{<pid>:{name, value, unit, ...}}}}`. |
| `readiness` | `fullscan`, `ops.obd_readiness` | `{since_clear:{mil_on, stored_dtc_count, ignition:"spark"\|"compression", monitors:[{monitor, supported, complete}], all_complete, ecu}, this_drive_cycle:{same}, evap_verdict:"...", drive_cycle_counters?:{warmups_since_clear, distance_since_clear}}`. A sub-record may be `{error, raw, why?}`. |
| `mode06` | `fullscan`, `ops.obd_mode06` | `{raw, supported:{<hdr>:[mid]}, results:{<mid>:{by_ecu:{<hdr>:[{mid, mid_name, tid, uasid, unit, value, min, max, passed, raw:{value, min, max, scaling}}]}, error?, negative?, retried?}}, evap_summary:[sentence]}`. `passed` = `min <= value <= max`. Scaling for an unknown UASID is `"unknown"` and raw values are kept. EVAP MIDs are 39 to 3D (3C is the 0.020 in small-leak test). |
| `pids_snapshot` | `fullscan`, `ops.obd_pids_snapshot` | `{by_ecu:{<header>:{<pid hex>:{name, value, unit}}}, requests_sent, multi_pid_used}`. |
| `pid` | `liveboard_bridge` | One Mode 01 PID reading. |
| `mode09` | `fullscan._obd_readout` | `{vin?, ..., mode09:{raw, results:{<pid>:...}}, gaps:[...], gap_reason}`. PIDs 04 (calibration IDs), 06 (CVNs), 08 (IUPR / in-use counters), 0A (ECU names). `gaps` lists PIDs the ECM did not answer: an honest gap, never filled in. |
| `adapter_identity` | `fullscan` | `{probe:{...adapter id...}, verify_can_c?, verify_can_ihs?, verify_can_ch?}`. `verify_*` carries `awake` (false when only network-management frames were heard) and `awake_note`. |
| `module_identity` | `fullscan._sweep_bus_modules` (sweep), `ops.module_identity` (kind `identity`) | `{ecu, bus, fields:{<DID hex>:{name, ascii, bytes, nrc}}}` over F190 (VIN), F187, F188, F189, F18C, F191, F192, F194, F195 (ISO 14229 Annex C). `error` set means the walk stopped early. |
| `did` | `fullscan`, `ops.module_did` | `{ecu, bus, did, name, error, nrc, formula?, unit?, confidence?, bytes?:[hex], ascii?, warning?}`. `formula` and `confidence` come from the project's DID table; unverified scales are flagged there. |
| `did_discovery` | `fullscan` (TCM), `ops.module_did_sweep` | Fullscan form: `{module:"TCM", tried, answered}`. Answers go to `learned_dids.json` as raw bytes with `scale:"unknown"`. |
| `evap_bundle` | `fullscan._evap_bundle` | Only when the ECM holds an **active** P044x/P045x/P046x. `{scan_id, codes:[{code, status, flags, snapshot_decoded, extended, error?}], mode06:{...}, readiness:{...}}`. `snapshot_decoded` and `extended` are the decoded 19 04 / 19 06 records of 1.7. Inner failures land as `{error}` in their own slot. |
| `dtc_detail` | `ops.module_dtc_detail` | `{ecu, dtc, status?, flags?, status_source:"19 02"\|"19 04 status byte"\|"19 06 status byte", snapshot:{...}, extended:{...}}` (1.7). |
| `capability` | `cuore/live/capabilities.py` | `{key, value, status:"measured"\|"unverified", evidence}`. Per-VIN facts ("PID 7F not supported", "PID 6B returned junk"). Later record for the same `key` wins. Seed facts also exist in code; `capabilities(vin)` returns the merge with `source:"builtin"\|"recorded"`. |
| `slvt_replica` | `slvt_bridge.run` | Read-only replica of the wiTECH Small Leak Verification Test: `{verdict:"PASS"\|"FAIL"\|"INCONCLUSIVE", summary, ran, at, preconditions:{confirmed:[id], missing:[id]}, job_id, ...per-signal evaluation from readiness + Mode 06 3C + ECM 19 02 status bits of P0456/P0455/P0440}`. PASS requires the EVAP monitor complete this cycle AND Mode 06 3C within limits AND `testFailedThisOperationCycle` clear on all three codes; INCONCLUSIVE when the monitor has not run. Also writes one `test` action on the VIN's open job. Bulletin 18-048-23. |
| `live_dtc_change`, `live_alarm` | `poller.py` | `{added, removed, stored, pending}` and `{channel, level, value}`; `vin` may be empty. |
| `clear_evidence` | `clear.py` | `{ecu, active:[code], tracked, file}`; `file` is the pre-clear evidence JSON under `clears/`. |
| `actuator_test` | `actuate.py` | `{ecu, name, steps:[...], control_returned, session_restored}`. |
| `bus_capture` | `buscapture.py` | `{bus, cable, recording, path, frame_count, distinct_ids, ids}`. Path is local; the CSV itself is not in the store. |
| `scan` | `ops.scan_modules` | UDS bus sweep result (older path). |

Reference counts from this PC's store (2026-10-22): `obd_dtcs`, `module_dtcs`, `module_identity`, `did`, `readiness`, `scan_coverage`, `adapter_identity`, `mode06`, `identity`, `dtc_detail`, `did_discovery`, `mode09`, `pids_snapshot`, `actuator_test`, `scan` are present. `evap_bundle`, `capability`, `slvt_replica`, `freeze_frame` are implemented but have not yet been written on this machine; treat their shapes as code-derived, not corpus-verified.

### 1.5 Scan regrouping (`cuore/live/scanlog.py`)

CUORE already regroups observations into scans on read (consecutive from-car observations within a gap are one scan; cache keyed on the file mtime). This is the nearest thing to a ready-made export shape: `GET /api/scans/{vin}` and `GET /api/scans/{vin}/{scan_id}`:

`{id, vin, started, ended, source, ecus:[...], dtcs:{stored, pending, permanent, ...}, readiness, mil, freeze_frames, mode06:[...], pids, coverage:{line, buses_attempted, counts, guided}, status:"complete"|"partial"|"attempt", partial:bool, counts:{observations, stored, pending, permanent, mode06_fail}}`

`status` semantics (honesty rule): `complete` = a `scan_coverage` exists, CAN-C was attempted and at least one CAN-C module answered; `attempt` = coverage exists but no module answered anywhere; `partial` = anything else (including manual single reads with no coverage). Only `complete` counts toward the "scan n of 10" plan. AlfaCore should store `status` and not count `partial`/`attempt` scans as completed scans. `GET /api/scans/{vin}/{scan_id}/export?fmt=json` returns one scan as an attachment.

### 1.6 Guided-scan state (`fullscan_guided.json`)

A single JSON object (one open session at a time; `run_guided` refuses while one is `paused`). Written after every segment, skip and abandon. Public view (`_guided_view`) adds `segment_done`, `next`, `counts`.

```json
{
  "scan_id": "SCAN_2610221405",
  "vin": "<VIN>",
  "started": "2026-10-22T14:05:00",
  "stream": "serial COM3@115200",
  "cable": "blue_a5",
  "status": "paused",
  "pending_index": 2,
  "segments": [
    {"n": 1, "cable": "none",    "bus": "can_c",   "status": "done",    "why": null},
    {"n": 2, "cable": "blue_a5", "bus": "can_ihs", "status": "done",    "why": null},
    {"n": 3, "cable": "grey_a6", "bus": "can_ch",  "status": "pending", "why": null},
    {"n": 4, "cable": "none",    "bus": "can_c",   "status": "pending", "why": null}
  ],
  "steps": [{"step": "verify_bus can_c", "ok": true}, {"step": "obd_mode06", "ok": false, "error": "..."}],
  "coverage": [{"bus": "can_c", "module": "ECM", "category": "answered", "why": null,
                "active": 3, "history": 12, "not_run": 20, "did": {"did": "XXXX", "name": "...", "source": "catalog"}}],
  "session_opens": 14,
  "segment_done": ["can_c", "can_ihs"],
  "next": {"cable": "grey_a6", "bus": "can_ch", "modules": [{"code": "ABS", "name": "..."}], "instruction": "Fit the GREY A6 cable (CAN-CH), then press Continue"},
  "counts": {"active": 3, "history": 12, "not_run": 20}
}
```

| Field | Values |
|---|---|
| `status` (session) | `paused`, `done`, `abandoned`. |
| `segments[].status` | `pending`, `done`, `failed` (bus silent, modules asleep, or nothing answered; retryable), `skipped`. Segment 4 is the closing "remove the cable and re-verify CAN-C" step (no sweep). |
| `pending_index` | Next segment to do; null when not paused. Segments may complete out of order (the mechanic may have fitted grey before blue); the pause returns to the lowest open one. |
| `coverage[].category` | `answered`, `silent`, `not_reachable`. A skipped bus is recorded as `not_reachable` with `why: "not reachable: skipped, needs <cable>"`, never dropped. |

The session is the unit AlfaCore should treat as "one visit scan": one `scan_id`, several segments, one rolling `scan_coverage` observation. Upload only when `status` is `done` or `abandoned`, or upload on every segment and let the latest win.

### 1.7 UDS DTC status bits and decoded records (`cuore/live/obd.py`, `coverage.py`, `dtc_detail.py`)

Status byte (ISO 14229-1 D.2), `flags` = `{name: bool}` for each bit:

| Bit | Mask | Name |
|---|---|---|
| 0 | 0x01 | `testFailed` |
| 1 | 0x02 | `testFailedThisOperationCycle` |
| 2 | 0x04 | `pendingDTC` |
| 3 | 0x08 | `confirmedDTC` |
| 4 | 0x10 | `testNotCompletedSinceLastClear` |
| 5 | 0x20 | `testFailedSinceLastClear` |
| 6 | 0x40 | `testNotCompletedThisOperationCycle` |
| 7 | 0x80 | `warningIndicatorRequested` |

Classification used everywhere (`coverage.classify_records`): **active** = `status & 0x0D` (0x01 testFailed, 0x04 pending, 0x08 confirmed); **history** = not active but `status & 0x20`; `not_run_since_clear` counts `status & 0x10`. A UDS 19 02 reply lists every code the module *tracks* (the ECM tracks hundreds); "present in the reply" is not "fault on the car". A code with only bit 0x40 set is a readiness flag, not a fault (`code_findings` class `readiness_only`). AlfaCore must store the raw `status` int and compute active/history itself or take CUORE's lists, but must not treat tracked codes as faults.

Decoded freeze-frame style records (`cuore/live/dtc_detail.py`, UDS 19 04 snapshot and 19 06 extended data; read-only, service 0x19 is on the read-only allowlist):

Snapshot (`decode_snapshot_record`):
```json
{ "dtc": "P0456-00", "status": 47, "flags": {"testFailed": true, "...": false},
  "records": [ { "record_number": 1,
      "identifiers": [ { "did": "1000", "name": "Engine RPM", "bytes": ["00","00"],
                         "value": 0, "unit": "rpm", "confidence": "medium", "basis": "..." } ] } ],
  "undecoded_from": "DID XXXX (length unknown); N raw byte(s) remain from here: [...]" }
```
- `confidence` is `high` (value anchored to a MultiEcuScan decode), `medium` (physically consistent plus a source), `low` (identity or scale plausible only) or `unknown`. `basis` says why. `name` and `value` are `null` where not earned; `bytes` is always the raw value.
- A DID whose length is not known stops the walk; everything after it is returned raw under `undecoded_from`. Empirical snapshot layouts exist for two modules only (ECM Marelli 10JA, BCM Marelli 949), derived on one car. Do not assume they hold for other ECUs.

Extended data (`decode_extended_data`): `{dtc, status, flags, records:[{record_number, bytes, meaning_guess, confidence:"unverified for FCA"}], undecoded_from?}`. Record numbers 1/2/3 are labelled occurrence / aging / aged counters by an AUTOSAR convention that is **not confirmed for FCA/Stellantis**. Carry `confidence` through; never present `meaning_guess` as fact.

Other 19-service decoders: `decode_dtc_count` (`19 01`: `availability_mask, format_id, count`), `decode_snapshot_identification` (`19 03`: `[{dtc, record_number}]`).

### 1.8 Jobs, hypotheses, actions, evidence (`mes-log-mcp/mes/jobs.py`)

`jobs.jsonl` is an event log of `op` records; `load(vin)` / `get(job_id)` fold them. An integration can either ship the folded job or ship the ops. Folded shape:

```json
{ "id": "a1b2c3d4e5f6", "vin": "<VIN>", "opened_at": "2026-10-08T09:12:00", "closed_at": null,
  "technician": "", "complaint": "", "status": "open", "outcome": null,
  "hypotheses": [ ... ], "actions": [ ... ],
  "verification": {"readiness_at": null, "codes_returned": [], "verdict": null},
  "links": {"symptom_ids": [], "note_ids": [], "media_ids": [], "feedback_ids": [],
            "service_record_ids": [], "inspection_ids": []} }
```

- Job `status`: enum is `open | verifying | closed`, but the fold only ever sets `open` and `closed`; `verifying` is declared and unused. `outcome` (required to close): `fixed | not_fixed | deferred`. More than one job may be open per VIN; the UI shows the newest (`current(vin)`), preferring jobs with an unresolved safety hypothesis.
- Ops: `open`, `hypothesis_add`, `hypothesis_set` (status/next_test), `hypothesis_edit` (text, system, codes, likelihood, next_test, `safety`, `attested_resolved`), `hypothesis_delete` / `hypothesis_undelete` (soft), `action_add`, `action_event_date`, `attach`, `evidence_remove`, `evidence_resolve`, `close`.

Hypothesis:
```json
{ "id": "ab12cd34", "text": "...", "system": "evap", "system_text": "EVAP",
  "status": "open", "evidence_for": [ref], "evidence_against": [ref],
  "next_test": "", "codes": ["P0456"], "likelihood": "low|med|high|null",
  "safety": false, "attested_resolved": false, "updated_at": "...", "deleted": false,
  "confirmed_by": null, "confirmed_at": null,
  "audit": [{"at": "...", "by": null, "action": "created|status|edited|deleted|evidence_removed|evidence_resolved|evidence_unresolved", "detail": "..."}] }
```
`system` is `mes.systems.normalize_system(system_text)` resolved on every read (so an alias-table improvement re-labels old records without rewriting the log).

**Status machine** (`_validate_status_transition`; violations raise `RuleViolation`, HTTP 409 with `reason` and `next_test`):

```
open -> supported -> confirmed
any state -> refuted
```
- `open -> confirmed` directly is refused.
- `supported` only from `open`. Nothing returns to `open`. `confirmed -> supported` is refused. Same-status is a no-op.
- `confirmed` needs at least one `evidence_for` ref with `kind:"test"` and `result` in `pass|fail` **and** zero `evidence_against` refs that are not `resolved`. (Note the gate checks that a test was *recorded*, pass or fail; it does not check which way it went. The meaning of the result is the mechanic's judgment.)
- `confirmed_by` / `confirmed_at` are set by the `hypothesis_set` record. Status is changed only through `hypothesis_set`; `hypothesis_edit` cannot change status or evidence, so the gate cannot be bypassed by editing. A server-side mirror in AlfaCore must re-implement or call this rule; a plain field write in AlfaCore would bypass it.

`safety` (bool): marks a hypothesis as safety-relevant (brakes, airbags, steering, anything that makes the car unsafe to release). `attested_resolved` (bool): the owner/mechanic attests the safety item is resolved; it is an attestation, not a reading. `has_safety(job)` is true when any non-resolved safety hypothesis exists, and such jobs sort first. Release gating (`shop_bridge`) advises and records; it does not block.

Evidence ref: `{kind, id, label, result?, resolved?}`. `kind` is one of `code, freeze_frame, actuator, live, inspection, symptom, note, media, dealer, bulletin, feedback, test, observation, measurement`. `result` (for `test`) is `pass | fail | inconclusive | not_possible`. `resolved` applies to `evidence_against` only. Bare job-level links accept only kinds that map to a link list (`symptom, note, media, feedback, dealer, inspection`).

Action:
```json
{ "id": "ef56ab78", "at": "2026-10-08T10:00:00", "kind": "test|inspection|repair|part|clear|note|understand",
  "text": "...", "ref": null, "event_date": "2026-09-14" | null,
  "effective_date": "...", "effective_date_source": "event_date|text|at", "date_uncertain": false }
```
`at` is when it was **recorded**; `event_date` (ISO date or datetime, set explicitly, or later via `action_event_date`) is when the thing **happened**. `effective_date` resolves: `event_date`, else a date parsed from the text ("REPAIR HISTORY, <date>", a leading ISO date, "between A and B" taking the later one and setting `date_uncertain`), else `at`. AlfaCore should store all three and order history by `effective_date`, not `at`; bulk entry of past repairs makes `at` misleading.

Case folding: `POST /api/jobs/{job_id}/close-as-case` folds a closed job into a portable Case for the next car of the same model (`cases.jsonl`); `GET /api/vehicles/{vin}/cases/match` ranks prior cases.

### 1.9 Mechanic plan (`cuore/services/mechanic_plan_bridge.py`)

Derived, read-only; regenerated on demand, not stored (except when the mechanic presses "save as next test", which writes text into the hypothesis `next_test` through `jobs_bridge.edit_hypothesis`). Endpoint: `GET /api/jobs/{job_id}/hypotheses/{hyp_id}/plan`.

```json
{ "vin": "<VIN>", "job_id": "...", "hypothesis_id": "...", "generated_at": "...",
  "rationale": "newline-separated notes, including bulletins excluded and why",
  "steps": [ { "n": 0, "title": "...", "detail": "...",
               "kind": "precondition|vin_check|read|flash|test|drive_cycle|decide|inspect|record",
               "source": "what put this step here",
               "done": false, "done_ref": "job action that satisfied it, or empty",
               "bulletins": ["18-048-23"], "tools": ["service drawing"] } ] }
```
Order is deterministic: preconditions, VIN checks, module currency, ESIM inspection, proof, flash, test, drive cycle, read, decide, inspect, record; steps already evidenced by job actions are marked `done` and sorted last. The first step always includes "never clear codes; no CAN-CH transmit without consent". Every step's `source` cites a bulletin number, a fragment of the hypothesis's CONFIRM / REFUTE / NEXT TESTS text, a job action, or a systems-graph dependency path. Steps that rest on outside literature carry the prefix `OUTSIDE LITERATURE, not a reading from this car:` in `source`. Steps are tied to a hypothesis via `hypothesis_id`; AlfaCore should keep `steps[].n` as order, not as identity (they renumber when a step becomes done).

### 1.10 Scan requirements (`cuore/services/scan_requirements_bridge.py`, `cuore/data/scan_requirements.json`)

A data file lists what each scan must capture for the open diagnosis. Row: `{id, label, why, source, evidence_kind:{kind, check, step?, window?, field?, ...}, not_capturable_reason?}`; `source` is `legislated | uds | did | bundle | mes_sync | mechanic_input`. Marque and car specifics are in the file (platform key, default VIN, open job note), not in code. Current ids: `readiness, mode06_evap, pids_enabling, obd_dtcs, mode09_cal, ecm_dtcs, evap_bundle, ecm_identity, ibs_dids, bcm_dtcs, mes_clear_sync` plus mechanic-input rows `esim_switch_state, esim_wire_voltage, esim_fit, slvt_result`.

`check(scan_id, vin)` output (read-only, no car traffic):

```json
{ "scan_id": "SCAN_...", "vin": "<VIN>",
  "met": [ {"id","label","source", ...} ],
  "gaps": [ {"id","label","source","reason"} ],
  "needs_mechanic": [ {"id","label","source","why","reason","status":"needs mechanic"} ],
  "not_applicable": [ {"id","label","source","reason"} ],
  "captured": 8, "required": 10,
  "window": {"start": "...", "end": "..."}, "non_car_observations": 0,
  "summary": "Captured 8 of 10 required; gaps: ..." }
```
Semantics to preserve: `needs_mechanic` rows are never failures (CUORE cannot read them: they need a meter, a visual check or wiTECH). A legislated read that was attempted but returned nothing decodable is a `gap` with the file's `silent_reason` (the adapter route failing), which is different from the car having nothing to report. `not_applicable` e.g. the EVAP bundle when no EVAP code is active. With no `scan_id`, `view(vin)` returns `{has_scan:false, to_capture:[...], needs_mechanic:[...]}`, the list of what the next scan must capture.

### 1.11 Code findings (`mes-log-mcp/mes/code_findings.py`)

In-code store (`FINDINGS`, as of 2026-10-20), keyed by full code `CODE-FTB` and module, looked up with `lookup(code, module?)` (full code = exact, base code = every FTB variant). Not exposed over HTTP; shown in templates via the `code_findings` Jinja global. Record:

`{code, module, meaning, meaning_source, readings:[str], classification, classification_label, classification_note, safety:bool, safety_note, implications, ladder:[step], proof, owner:[str], literature:[{text, url}]}`

`classification`: `real`, `service_induced` (owner-attested, not yet confirmed by a reading), `probable_artefact`, `possible_bystander`, `downstream_bcm`, `bcm_cluster`, `readiness_only`. The three evidence arrays are deliberately separate: `readings` (this car's logs), `literature` (outside; other cars/years; never a reading), `owner` (statements by the owner; attested). A field with no sourced finding is left empty, never filled. `proof` states what would count as proof of a fix (for example "absent from reads over N days, status bytes read before any clear").

### 1.12 TSB catalogue and cross-reference

**Catalogue** `cuore/data/tsb_catalogue.json`: `{_schema, vehicle:{make, model, year, engine, market, vin}, updated, sources:[...], items:[...]}` (141 rows at 2026-10-15). Row (only `id` is required; extras tolerated):

| Field | Meaning |
|---|---|
| `id` | Stable row id. |
| `kind` | `tsb`, `recall`, `csn`, `campaign`, `extended_warranty`, `emissions`, `field_report` (forum/retailer claim, never verified; sibling-engine only). |
| `number`, `nhtsa_id`, `title`, `date`, `summary`, `condition`, `remedy`, `systems[]`, `dtcs[]`, `links[{label,url}]\|null` | As printed. |
| `applies` | `yes \| no \| vin_check` (does it apply to this car; `vin_check` = unconfirmed, check by VIN/dealer). |
| `source`, `verified` | Where the facts came from; `verified:true` only when the source document itself was read. |
| `components[]`, `symptoms[]`, `repair_implied` (`flash \| replace:<part> \| procedure:<name> \| inspect \| software_update \| none`), `depends_on_systems[]` (systems-graph keys) | Optional matching fields. |
| `vehicle_scope` | `this_model` (default) or `sibling_engine` (analogue from another model with the same engine family; never Stelvio evidence). Sibling rows add `sibling_vehicle`, `transferability` ("inference: ..."), `stelvio_equivalent`. |
| other optional | `supersedes`, `family`, `applies_to`, `also_applies_to`, `transport_canada_id`, `nhtsa_ids`, `cuore_relevance`, `cross_references`. |

Carry `applies`, `verified` and `vehicle_scope` to AlfaCore: they decide how much weight a bulletin may have.

**Cross-reference** `tsb_xref_bridge.xref(vin)` (`GET /api/tsb/xref?vin=`): every catalogue row related, by explicit rules with a human-checkable `reason`, to the car's codes, the job's actions, the open job's hypotheses and the systems-dependency graph.

```json
{ "vin": "<VIN>", "job_id": "open job id or null", "weights": {"explains":3, "same_system":2, "dependent_system":1, "candidate":1, "not_the_fix":2, "supports":1, "applicability_doubt":-2, "ruled_out_by_inspection":-2},
  "bulletins": [ { "id","number","kind","title","applies","systems":[key],"vehicle_scope","verified",
                   "relations": [ {"type","reason", "relation"?, ...} ],
                   "flags": ["not_applicable"|"other_model"|"year_doubt"],
                   "score": 5, "score_parts": ["..."], "analogues": [{id,number,title,sibling_vehicle,score,kind,reason}], "href": "/tsb?vin=..." } ],
  "by_code": {}, "by_repair": [], "by_hypothesis": {}, "by_system": {},
  "analogues": [], "analogues_by": {"by_code":{}, "by_hypothesis":{}, "by_system":{}},
  "hypotheses": {"<hyp_id>": "first 140 chars of text"} }
```

Relation `type` and `relation` values:

| `type` | `relation` values | Extra fields |
|---|---|---|
| `applicability` | `app_rel` (catalogue `applies`), `other_model_doubt`, `model_year_doubt` | `applies` |
| `analogue` | `analogue`, `field_report` | `stelvio_equivalent?` |
| `identity_match` | none | `value` (a module part number the bulletin names that the car's identity reports) |
| `code_match` | `explains` (code active), `historical` | `code`, links to the code's history |
| `system_match` | `same_system`, `dependent_system` | `system` |
| `hypothesis_interaction` | `supports`, `weakens`, `neutral` | `hyp_id`, `job_id`, `hyp_text`, `suggestion?:{side, kind:"bulletin", ref_id, label, action}` |
| `repair_interaction` | `already_applied`, `did_not_resolve`, `ruled_out_by_inspection`, `candidate` | `at`, `event_date`, `code?`, `repair_kind?`, `parts?` |

Scoring rules (each relation type counted once per bulletin): `already_applied` + `did_not_resolve` scores 2 as "evidence that this remedy is not the fix"; `applies == "no"` zeroes the score and flags `not_applicable`; analogue scores are halved (`ANALOGUE_FACTOR = 0.5`, a code match keeps at least 1) and `field_report` rows cap at 1; analogues sort after every Stelvio row and are excluded from `by_*` and `top`. `suggestion` is offered, never applied: evidence is attached only by an explicit user action on the job. An `already_applied` flash requires a flash word AND the same module named in the action (or the bulletin cited), and the action's `event_date` is used for ordering.

### 1.13 Evidence labels

CUORE keeps four classes apart and AlfaCore must too. There is **no single stored `evidence_class` field**; the class is implied by where the record lives or by a prose prefix. Proposed mapping to an enum on the AlfaCore side:

| Label | Meaning | Where it shows up in CUORE | Mapping rule |
|---|---|---|---|
| `reading` | What this car said, on a real adapter. | Observations with `stream` starting `serial` / `recording(serial` (`is_from_car`); `code_findings.readings`; MES logs in the corpus. | `from_car == true`. Replays and scripted streams are not readings. |
| `inference` | A conclusion drawn from readings or from the hypothesis text. Not itself a measurement. | Hypothesis text and `status`; `code_findings.classification_note`, `implications`; xref `reason`, `score`; plan `rationale`; the verdict gate's mechanism sentence. | Anything derived. A DTC alone is explicitly **not** a measurement: codes select the fault tree, they do not convict a part. |
| `outside_literature` | From bulletins, web pages, forums, other cars or years. Never a reading of this car. | Catalogue rows (especially `field_report`, `vehicle_scope:"sibling_engine"`, `verified:false`); `code_findings.literature`; plan step `source` prefix `OUTSIDE LITERATURE, not a reading from this car:`; the "experience links" tables. | Carry `verified` and `vehicle_scope`. |
| `owner_attested` | A person said it. | `owner_events.jsonl` (`confidence:"reported"`); `attested.jsonl` (`confidence:"SINGLE-SOURCE (mechanic)"`); hypothesis `attested_resolved`; `code_findings.owner`; the `service_induced` class; job `symptom`/`note`/`inspection` refs. | These never enter the evidence gate as car measurements (`mes.verdict`: "the evidence gate" counts verified measurement types `actuator, freeze_frame, parameter, recording_event, live, dealer` and treats `manual` and `note` as attested). |

Rule for any AlfaCore view or any LLM that reads these: a conclusion that rests only on `outside_literature`, `inference` or `owner_attested` must say so. Only `reading` supports "the car showed X". The evidence gate (`POST /api/vehicle/{vin}/verdict`) returns CONFIRMED only when four criteria hold: the fault is demonstrated (chronic, returned after a clear, or standing now), a causal mechanism is stated, at least one cited measurement implicates the component, and a disconfirmation test was attempted.

### 1.14 HTTP API and authentication

All 269 JSON endpoints (plus the two web-router helpers noted below) are in Appendix A (method, path, purpose). Prefix `/api`; interactive docs at `/api/docs`, schema at `/api/openapi.json`. Roughly 150 further routes are server-rendered HTML pages and HTML form posts (`/v/{vin}/...`, `/tsb`, `/slvt`); they are a UI, not a contract. Two JSON helpers live on the web router outside `/api` routers: `GET /api/jobs/{job_id}/hypotheses/{hyp_id}/plan` and `GET /api/tsb/xref`.

Endpoints an AlfaCore integration would use first:

| Need | Method and path |
|---|---|
| Liveness, profile | `GET /api/health`, `GET /api/capabilities`, `GET /api/status` |
| Raw observations | `GET /api/live/observations?n=&vin=&kind=` (n up to 1000, newest last) |
| Scans for a car | `GET /api/scans/{vin}`, `GET /api/scans/{vin}/{scan_id}`, `.../export?fmt=json`, `.../health`, `GET /api/scans/{vin}/diff` |
| Last / guided scan | `GET /api/live/fullscan/last`, `GET /api/live/fullscan/guided/state` |
| Jobs | `GET /api/vehicles/{vin}/job`, `GET /api/vehicles/{vin}/job/{job_id}` |
| Jobs (write, rule-enforced) | `POST /api/jobs/{job_id}/hypotheses/{hyp_id}/status` (409 on rule violation), `.../evidence`, `POST /api/jobs/{job_id}/actions`, `POST /api/jobs/{job_id}/close` |
| Plan and bulletins | the two web-router JSON helpers above |
| Owner / attested | `GET/POST /api/owner/{vin}/events`, `GET /api/attested/{vin}/{system}` |
| Evidence gate | `POST /api/vehicle/{vin}/verdict` |

Write endpoints that move the car (not for AlfaCore): `POST /api/live/probe`, `/verify`, `/capture`, `/cable`, `/discover`, `/fullscan*`, `/session/*`, `/coverage/*`, `/connect/start`, `/module/{code}/discover-dids`. These talk to the adapter. There is **no HTTP route that clears codes, writes DIDs, or runs actuators**: `/api/live/actuators` is list-only and states "replay never over HTTP". Clearing is a separate local procedure with a typed consent phrase (section 2.5).

**Authentication, as it is today.** CUORE has an optional single shared token (`CUORE_TOKEN` / `--token`), checked by `require_token` on every `/api` router and every HTML router, sent as header `X-Cuore-Token` or query `?token=`, compared with `hmac.compare_digest`. It is **off by default** (empty token = no check), the `/static` mount is outside it, and both `start-cuore.ps1` and `cuore-keepalive.ps1` start the server with `--host 0.0.0.0` and no token. In that default launch there is effectively **no authentication on the LAN**, and the log corpus and job ledger contain customer VINs. There are no user accounts, no roles, no per-client tokens, no JWT, no TLS, and no request audit beyond the uvicorn access log. The server warns at startup when bound beyond loopback without a token.

---

## Part 2. Deployment on the shop LAN

### 2.1 AlfaCore side, from the QNAP install note

Roles only (no addresses, names or secrets are reproduced here):

| Role | Detail from the install note |
|---|---|
| Host | QNAP TS-851 (8-bay, dual-core Celeron, 8 GB RAM maximum, QTS, two 1 GbE). Viable for pilot and about 3 to 5 concurrent users; the note itself flags the CPU and RAM ceiling. |
| Runtime | Container Station (Docker), one private Docker network for the stack. |
| Application | Odoo 19 Community in a container: 2 workers plus 1 cron thread, reverse-proxy mode on, custom AlfaCore modules bind-mounted as an addons directory. |
| Database | PostgreSQL 16 in a container, data on an SSD-backed volume. |
| Edge | Caddy reverse proxy terminating HTTPS on the LAN with its internal (self-signed) certificate authority; a real certificate only if the service is ever exposed publicly (not planned; the note starts LAN-only). |
| Storage | SSD pool for Postgres, filestore, addons, config; HDD pool for long-term backups. |
| Hardening | Default admin disabled, 2-step verification on the new admin, unneeded NAS services off, SSH brute-force blocking, NTP enabled (the note says audit trails depend on it). |
| Backups | Nightly Postgres dump (custom format) plus filestore archive, rotated daily/weekly/monthly to the HDD pool, with a restore test on a throwaway database. |
| Memory budget | Postgres capped about 2 GB, Odoo about 4 GB, Caddy about 256 MB, leaving about 1.5 GB for QTS. |

**Qdrant and Ollama are not in the install note.** On this hardware there is no spare RAM for an embedding model or a vector store alongside Odoo and Postgres. If AlfaCore needs either, plan them on a separate host (or accept a very small model); do not assume they share the QNAP.

### 2.2 CUORE side, as it runs today

- Windows PC in a bay; Python venv; `python -m cuore --profile bench --host 0.0.0.0 --port 5000` started by `start-cuore.ps1` (opens the browser) and kept alive by `cuore-keepalive.ps1` (a scheduled task at logon, rechecked every 5 minutes; restarts if nothing listens or `/api/health` fails 3 times). Output goes to `<state>\logs\server.log`.
- Port 5000 is hard-coded in the scripts. The `cuore/config.py` default bind is loopback; the launcher widens it.
- The adapter is a USB-serial STN-based OBD interface on a COM port. Port and speed resolve from `CUORE_OBD_PORT` / `CUORE_OBD_BAUD`, then `OBD_PORT` / `OBD_BAUD`, then MultiEcuScan's registry (`Interface 0 Port`), then a 38400 baud fallback with no port. `CUORE_OBD_CABLE` declares the cable.
- One program per port: a process lock plus an advisory lock file in the state dir, and an MES interlock (the process list and the text of MultiEcuScan's status label). CUORE refuses full scans and guided scans while MES shows `Connected`. A live poller session also holds the adapter and blocks scans.
- State is in `%PROGRAMDATA%\cuore` per PC (section 1.1). Each bay PC therefore has its **own, separate** observations, jobs, attested and owner-event files. The same VIN can appear in two bays with unrelated job ids.
- The JSON API is the same process as the pages; the MCP servers (`obd2`, `mes-log`) are separate local processes that share the state dir and the lock.
- No outbound network use by default (CUORE "runs offline by rule"). The only optional outbound call is the photo-reading provider, off by default.

### 2.3 Target topology

```
  Bay 1 PC                    Bay N PC                       QNAP TS-851 (LAN only)
 +----------------+         +----------------+            +---------------------------------+
 | CUORE :5000    |         | CUORE :5000    |            | Caddy (HTTPS, LAN CA)           |
 |  state dir     |         |  state dir     |  HTTPS     |   -> Odoo 19 (AlfaCore addons)  |
 |  outbox  (new) | ------> |  outbox  (new) | ---------> |   -> Postgres 16                |
 |  USB-serial    |         |  USB-serial    |  token     | nightly dump + snapshots        |
 |  STN adapter   |         |  STN adapter   |            +---------------------------------+
 +-------+--------+         +-------+--------+                  ^
         | OBD port                 | OBD port                  | browser (LAN) from any
       car in bay 1             car in bay N                    workstation
```

- One CUORE per bay, one adapter per CUORE, one program per port. Nothing from AlfaCore talks to an adapter, and nothing from AlfaCore may reach the adapter through CUORE.
- Direction of data: **bay to NAS**, pushed by CUORE (outbound HTTPS from the bay PC). AlfaCore does not call into the bay PC to scan. If AlfaCore wants to show "start a scan" it should only ever open the CUORE UI on that bay PC (a link), not drive it.
- AlfaCore is a **mirror and workspace** for readings, jobs and findings; CUORE remains the source of truth for readings. Edits made in AlfaCore that change a hypothesis status or evidence must be sent back through CUORE's job endpoints (which enforce the status machine, 1.8) or AlfaCore must implement the same rule server-side. Decide this before building (see 2.6).

### 2.4 What CUORE must add

None of the following exists today.

| # | Addition | Why | Proposal |
|---|---|---|---|
| 1 | **Station identity** | Nothing identifies which bay produced a record; scan ids collide across PCs at minute resolution. | `CUORE_STATION_ID` in settings, stamped into every upload and into the idempotency key (1.2). Optionally stamp it into the observation envelope at write time. |
| 2 | **Auth to AlfaCore's app API** | Outbound calls need an identity the NAS can revoke. | A per-station API token (or a short-lived JWT the NAS issues from a station credential), held in a Windows-protected store, not in `.env` in the repo. Sent as a bearer token. AlfaCore validates, maps to a station, and rate-limits. One revocable credential per bay PC. |
| 3 | **Outbound sync queue** | The NAS will be offline for updates, backups and power events. A bay must keep scanning. | An on-disk outbox beside the state dir (append-only, one entry per record or batch, with a sent marker or a separate cursor file). A background worker retries with backoff and jitter. Never blocks a scan or a job write: the existing stores stay the write path, the outbox is a reader of them (tail `observations.jsonl` and `jobs.jsonl` by byte offset, persisted cursor). Survive restart. Cap size and report age of the oldest unsent entry in `/api/health`. |
| 4 | **Idempotent upload** | Retries and a re-sent backlog must not duplicate. | Upload key per 1.2: `(station_id, vin, scan_id)` for scans, `(station_id, job_id)` for jobs with `(job_id, hyp_id)` / `(job_id, action_id)` children, and a content-hash key for observations. AlfaCore upserts on the key and ignores exact repeats. Jobs and hypotheses are event-sourced, so the safest payload is the ordered `op` records, replayed on the NAS; the folded job is derived there. |
| 5 | **Payload contract and versioning** | The shapes in Part 1 evolve (`kind` set grows, fields get added). | Envelope `{schema_version, station_id, sent_at, items:[...]}`; AlfaCore stores unknown kinds raw rather than rejecting. Preserve `error`, `nrc`, `warning`, `note`, `confidence`, `basis` and `stream` verbatim. |
| 6 | **Time sync and time zone** | All CUORE timestamps are naive local time with no offset; ordering across bays and against Odoo/Postgres (UTC) needs a defined meaning. `event_date` vs `at` ordering (1.8) is meaningful only if clocks agree. | NTP on every bay PC (Windows Time pointed at the NAS or a common source, same source as the NAS). Add `CUORE_TZ` (an IANA zone) to settings and send `sent_at` as UTC with the station zone so AlfaCore can convert naive `at` values; do not rewrite stored values. Alert if the PC clock differs from the NAS by more than a few seconds at sync time. |
| 7 | **TLS on the LAN** | Customer VINs and job data cross the LAN. Caddy already terminates HTTPS with an internal CA. | CUORE uploads over HTTPS only and validates the NAS certificate against the LAN CA (installed on each bay PC), never with verification disabled. For CUORE's own port 5000: either bind to loopback and put a local TLS proxy in front, or add a certificate to uvicorn; at minimum stop serving plain HTTP to the whole LAN (next row). |
| 8 | **Firewall and exposure** | CUORE must not be reachable beyond the LAN, and ideally not by other LAN hosts. | Windows Firewall inbound rule on each bay PC: port 5000 allowed only from the bay's own workstation (or loopback) and denied otherwise; outbound allowed only to the NAS HTTPS port. No router port forwarding or UPnP for CUORE; no inbound path from the internet; the NAS reverse proxy is LAN-only (as the install note starts). Set `CUORE_TOKEN` whenever the bind is wider than loopback (change `start-cuore.ps1` and `cuore-keepalive.ps1` so they do not launch `0.0.0.0` without one). Separate the adapter's PC from guest Wi-Fi. |
| 9 | **Authentication for CUORE's own API** | Today anyone on the LAN can read VINs and POST to jobs. | At minimum a mandatory token for any non-loopback bind; better per-client tokens so AlfaCore's pull calls (if any) and bay workstations are distinguishable. |
| 10 | **Backups** | The bay state dir is the only copy of readings until the outbox drains. | Nightly copy of the state dir (observations, jobs, attested, owner events, `addresses.json`, `learned_dids.json`, `media/`, `clears/`, `recordings/`) to a NAS share with versioned retention; QNAP snapshots on that share (and on the Odoo volumes); restore tested. Back up the outbox cursor with them. Never back up or sync `audit.jsonl` contents elsewhere without a retention decision (it logs every adapter command). |
| 11 | **Health and observability** | An unattended sync needs to be visible. | `/api/health` gains `outbox:{pending, oldest_age_s, last_success_at, last_error}`; a visible banner in CUORE when the NAS has been unreachable for N minutes; server log line per batch. |
| 12 | **Data minimisation and retention** | The store holds customer VINs and photos. | Decide what is sent: structured records, not `media/` by default; photos on an explicit action. Honour deletions (soft-delete flags travel as records). |

### 2.5 Safety invariants that must survive

These are enforced in CUORE's code today. Any integration must leave them intact, and must not offer a path around them.

1. **No clearing without consent.** Clearing (UDS 0x14) is the only vehicle write CUORE performs. It is a local procedure (`cuore/live/clear.py`): the operator must type the exact phrase `CLEAR <MODULE>`; the car must be stationary; on CAN-CH a per-call confirmation is required; all evidence (19 02, snapshot, extended data) is captured to `clears/` and to a `clear_evidence` observation **before** the clear, and codes that return are reported after. There is no HTTP route for it, and AlfaCore must not add one. AlfaCore must never send, queue or schedule a clear, a flash, a write or an actuation. Mechanic plan step 1 repeats: never clear codes during diagnosis.
2. **Read-only by construction.** `safety.py` classifies every adapter command: UDS services 0x10, 0x11, 0x14, 0x27, 0x28, 0x2C, 0x2E, 0x2F, 0x31, 0x34 to 0x37, 0x3D, 0x85, 0x87 are write-class and blocked on the read path; AT and ST commands are allowlisted reads only; one command per call (no CR, LF or `|` batching). Service 0x19 (all sub-functions) is read-only. The coverage checklist forbids any FEPS or programming-voltage command (the vLinker class of adapter can put 18 V on OBD pin 13, which is CAN-CH(-) on this car).
3. **Confirmed bitrates only.** Each bus has a fixed bitrate with a `bitrate_confidence` (`confirmed` or `inferred`; all three buses are `confirmed` in `buses.py`): CAN-C 500 kbps, CAN-IHS 125 kbps, CAN-CH 500 kbps. The cable protocol is enforced before any request leaves the adapter (`assert_transmit_allowed`): the declared cable must reach the bus, the bus must have been verified by a passive listen under that cable declaration, and a 500 kbps preset must never be put on a 125 kbps bus. Module addresses carry the same distinction (`bus_confidence` `confirmed` / `inferred`; only addresses confirmed by discovery, kept in `addresses.json`, are used). AlfaCore must not carry a bitrate or address setting that CUORE could be told to apply.
4. **CAN-CH confirmation.** CAN-CH carries brakes, airbags and steering. Every request there needs explicit confirmation (`transmit_needs_confirmation`). In the guided scan the confirmation is physical: the mechanic fits the grey A6 cable and declares it on the same call; the sweep is read-only UDS (0x19, 0x22). Actuator-test replay refuses brakes, airbag, steering and every other CAN-CH module outright. Scans must not be triggered unattended from AlfaCore.
5. **Readings-only conclusions.** Only a `reading` (from-car observation) supports "the car showed X". A DTC is not a measurement. A hypothesis cannot be `confirmed` without a recorded pass/fail test and with unresolved evidence against it (1.8). Absence of a code carries no information when the monitor has not run (`evap_verdict`). Outside literature, inference and owner-attested statements are labelled and kept apart (1.13). AlfaCore must preserve the label, show it, and never promote an attested or literature item to a reading.
6. **Failures are not "clean".** An adapter/bus error, NRC or silence is never recorded or displayed as "no codes". Coverage rows say `silent` or `not_reachable` with a reason. Skipped segments stay in the record.
7. **Bystander discipline.** Re-plugging cables and serial UDS sweeps can manufacture bystander codes (-87 / -2F). The coverage session reads CAN-C first, last, and diffs; an active code that appears between is reported as likely bystander, not a fault. AlfaCore must display the diff, not just the final list.
8. **One program per adapter.** No MES and CUORE (or two CUOREs) on the same port at once; scans refuse while MES is connected or the live poller holds the adapter. Keep sync a pure file/HTTP activity that never opens the serial port.
9. **Sync must never block or alter a scan.** The outbox is a downstream reader. A full disk, an offline NAS or a rejected payload must not fail a read or lose an observation (`record_observation` never raises today; keep that property).
10. **Safety jobs.** A hypothesis flagged `safety` and not `attested_resolved` keeps its job at the top and is surfaced at release. AlfaCore should preserve both flags and the attested wording.

### 2.6 Open questions for the AlfaCore side

1. Which side owns hypothesis status changes after sync: CUORE only (AlfaCore read-only plus links back), or AlfaCore with an equivalent server-side state machine?
2. Is a pull path needed (AlfaCore asks a bay for its latest scan), or is push-only enough? Push-only avoids any inbound firewall opening on the bay PCs.
3. VIN resolution for untagged observations: resolve on the CUORE side before upload, or accept `vin: ""` and let AlfaCore attach by station and time?
4. Shape of upload: raw ops and observations (replayable, larger) or regrouped scans and folded jobs (smaller, loses ordering information).
5. Where Qdrant/Ollama (if wanted) will run, given the NAS memory budget.
6. Retention: how long AlfaCore keeps raw observations, and whether `media/` photos sync.
7. Time zone and clock policy for the bay PCs (section 2.4, row 6).

---

## Appendix A. CUORE HTTP API (JSON), as of 2026-10-22

All paths are under the `/api` prefix. Every router carries the optional `X-Cuore-Token` dependency (off unless `CUORE_TOKEN` is set). Generated from `@router` decorators in `cuore/api/*.py` and the `api_router` objects in `cuore/web/{dashboard,service,drivetrain,labels}_routes.py`, plus two JSON routes on the web router. For parameters and response models use `/api/openapi.json` on a running server.

#### Attested mechanic input (2)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/attested/{vin}` | File one attested mechanic input |
| GET | `/api/attested/{vin}/{system}` | Attested inputs on file for one system |

#### Bus capture (12)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/buscapture/cable` | Declared cable, reachable buses, unlocked presets |
| POST | `/api/buscapture/cable` | Declare the fitted cable; lists what it enables |
| POST | `/api/buscapture/{bus}/start` | Start a passive bus capture |
| GET | `/api/buscapture/{bus}/status` | Live frame rate and distinct-ID counts |
| POST | `/api/buscapture/{bus}/stop` | Stop a running bus capture |
| POST | `/api/buscapture/{bus}/save` | Save a stopped capture as a tagged CSV recording + observation |
| POST | `/api/buscapture/{bus}/learn/start` | Start a learn capture for one action |
| GET | `/api/buscapture/{bus}/learn/status` | Poll a running learn capture |
| POST | `/api/buscapture/{bus}/learn/stop` | Stop a learn capture; returns ranked (id, byte) candidates |
| POST | `/api/buscapture/{bus}/learn/accept` | Name a ranked candidate and save it as a learned broadcast signal |
| GET | `/api/buscapture/presets/{name}` | One bus-capture preset's items, catalogue/learned only |
| POST | `/api/buscapture/presets/{name}/start` | Start a capture scoped to one preset's bus; refuses without its cable |

#### Cases (2)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/cases/match` | Prior cases for this model, ranked by overlap |
| GET | `/api/vehicles/{vin}/cases/prefill` | Suggested starting point from the best prior case |

#### Checklists (3)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/checklist` | Checklist state for this vehicle |
| POST | `/api/vehicles/{vin}/checklist` | Tick (or untick) one checklist step, with an outcome |
| POST | `/api/vehicles/{vin}/checklist/{step_id}/result` | Record a test result on one checklist row (step 6 result sheet) |

#### Dossier (1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/view` | The redesigned dossier's computed view |

#### Electrical (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/electrical/elements` | Every electrical element known |
| GET | `/api/electrical/elements/{element_id}` | One electrical element by id |
| GET | `/api/electrical/path/{code}` | Electrical path for a DTC |
| GET | `/api/vehicles/{vin}/electrical/inspections` | Electrical inspection history for this vehicle |
| POST | `/api/vehicles/{vin}/electrical/inspections` | Record an electrical inspection finding |

#### Others' experience links (10)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/experience` | Others' experience: videos, threads, teardowns |
| GET | `/api/experience/{vin}/inputs` | Driver/mechanic-added links for this vehicle |
| POST | `/api/experience/{vin}/inputs` | Add one driver/mechanic-found link |
| PATCH | `/api/experience/{vin}/inputs/{id}` | Edit a driver/mechanic-added link |
| POST | `/api/experience/{vin}/inputs/{id}/verify` | Run the deferred link check and record its result |
| DELETE | `/api/experience/{vin}/inputs/{id}` | Soft-delete a driver/mechanic-added link |
| POST | `/api/experience/{vin}/inputs/{id}/restore` | Undo a soft-delete |
| POST | `/api/experience/links/{link_id}/flag` | Flag a link (curated or added) as wrong/outdated |
| POST | `/api/experience/links/{link_id}/worked` | "Worked on this car?" tick |
| GET | `/api/experience/{vin}/inputs/export` | Export user-added links for curation review |

#### Feedback (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/feedback` | Mechanic feedback for this vehicle |
| POST | `/api/vehicles/{vin}/feedback` | Record mechanic feedback |
| GET | `/api/vehicles/{vin}/feedback/counts` | Per-target feedback tallies |
| POST | `/api/feedback/{id}/answer` | Answer one feedback row |
| POST | `/api/feedback/{id}/status` | Set one feedback row's status |

#### Mechanic flow (1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/flow` | The 12-step mechanic flow for this VIN |

#### Jobs (cases, hypotheses, evidence, actions) (17)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/job` | The current (or most recent) job for this vehicle |
| GET | `/api/vehicles/{vin}/job/{job_id}` | One job by id |
| POST | `/api/vehicles/{vin}/job` | Open a new job (case) for this vehicle |
| POST | `/api/jobs/{job_id}/close` | Close a job -- outcome required |
| POST | `/api/jobs/{job_id}/close-as-case` | Fold this job into a portable Case for the next car of this model |
| GET | `/api/jobs/{job_id}/case` | The case already on file for this job, if any |
| POST | `/api/jobs/{job_id}/hypotheses` | Add a hypothesis to a job's ledger |
| GET | `/api/jobs/{job_id}/hypotheses/similar` | The most similar existing hypothesis to a proposed one (merge prompt) |
| POST | `/api/jobs/{job_id}/hypotheses/{hyp_id}/status` | Change a hypothesis's status -- 409 on a rule violation |
| POST | `/api/jobs/{job_id}/hypotheses/{hyp_id}` | Edit a hypothesis's own fields |
| DELETE | `/api/jobs/{job_id}/hypotheses/{hyp_id}` | Soft-delete a hypothesis |
| POST | `/api/jobs/{job_id}/hypotheses/{hyp_id}/undelete` | Undo a soft-delete |
| POST | `/api/jobs/{job_id}/hypotheses/{hyp_id}/evidence` | Add, remove, or resolve one evidence ref on a hypothesis |
| GET | `/api/jobs/steps` | The flow's step registry (n/key/title) for cross-references |
| POST | `/api/jobs/{job_id}/actions` | Record one action against a job |
| POST | `/api/jobs/{job_id}/attach` | Attach a real record as hypothesis evidence or a job link |
| POST | `/api/jobs/migrate-systems` | Backfill system_text on old-shape hypothesis records (idempotent) |

#### Known-good bands (1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/live/known-good` | Known-good bands for live-dashboard channels, optionally with this VIN's own observed ranges |

#### Live adapter link, scans, coverage, polling (56)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/live/status` | Port, speed, MES state, lock, cable and bus verification |
| GET | `/api/live/ports` | Serial ports, with MES's configured port marked |
| GET | `/api/live/mes` | MultiEcuScan's own settings from the registry |
| GET | `/api/live/buses` | The three buses and their reachability under the declared cable |
| GET | `/api/live/modules` | The module table with addresses and confidence |
| POST | `/api/live/cable` | Declare which adapter cable is fitted |
| POST | `/api/live/probe` | Reset the adapter and read its identity; holds nothing |
| POST | `/api/live/verify` | Passive listen on a bus; marks it verified if traffic is seen |
| POST | `/api/live/capture` | Passive frame capture on a bus (receive only, no ACK) |
| GET | `/api/live/obd/dtcs` | Stored, pending or permanent codes (Mode 03/07/0A) |
| GET | `/api/live/obd/pid/{pid}` | One Mode 01 PID, decoded |
| GET | `/api/live/obd/voltage` | Battery voltage at the OBD port |
| GET | `/api/live/obd/supported` | Mode 01 PID support bitmaps per ECU |
| GET | `/api/live/obd/freeze` | Mode 02 freeze frame |
| GET | `/api/live/obd/vin` | Mode 09 VIN |
| GET | `/api/live/obd/readiness` | Readiness monitors with the EVAP verdict |
| GET | `/api/live/module/{code}/dtcs` | UDS 0x19 02 on one module |
| GET | `/api/live/module/{code}/identity` | ISO 14229 Annex C identity of one module |
| GET | `/api/live/module/{code}/did/{did}` | UDS 0x22 on one module |
| GET | `/api/live/module/{code}/repair` | Repair verification: has each test re-run since the clear, and passed? |
| GET | `/api/live/obd/mode06` | OBD Mode $06 on-board test results (EVAP summarised) |
| GET | `/api/live/module/{code}/dtc/{dtc}` | One code's status, snapshots and counters |
| GET | `/api/live/module/{code}/all` | Identity plus every catalogued identifier, decoded |
| POST | `/api/live/module/{code}/discover-dids` | Read-only sweep for unknown identifiers |
| POST | `/api/live/learn/capture` | Passive capture while a dealer tool reads (learning) |
| POST | `/api/live/learn/correlate` | Rank identifiers against values seen in wiTECH |
| POST | `/api/live/learn/accept` | Save a learned identifier mapping (cuore state only) |
| GET | `/api/live/learned` | Identifier mappings learned from dealer-tool captures |
| GET | `/api/live/scan` | UDS DTC sweep over every confirmed module on a bus |
| POST | `/api/live/discover` | Address discovery: 22 F190 at each candidate target |
| GET | `/api/live/coverage` | Whole-vehicle coverage session: passes, next step, report |
| POST | `/api/live/coverage/start` | Start a coverage session for one VIN |
| POST | `/api/live/coverage/run` | Run one pass: verify, discover, read codes |
| POST | `/api/live/coverage/skip` | Skip a pass (not the baseline) |
| GET | `/api/live/coverage/report` | Merged whole-car report with bystander diff |
| POST | `/api/live/coverage/reset` | Discard the coverage session |
| GET | `/api/live/observations` | What the car said, for the evidence gate to cite |
| GET | `/api/live/audit` | Recent audit-log entries |
| GET | `/api/live/actuators` | Learned actuator-test procedures (list only; replay never over HTTP) |
| POST | `/api/live/fullscan` | One read-only full-vehicle scan; every reading recorded as an observation |
| GET | `/api/live/fullscan/last` | The most recent full scan's result |
| POST | `/api/live/fullscan/guided/start` | Start a guided scan: CAN-C in full, then pause for the blue A5 cable |
| GET | `/api/live/fullscan/guided/state` | The open (or most recently closed) guided scan |
| POST | `/api/live/fullscan/guided/continue` | Declare the cable just fitted, sweep its bus, and pause for the next step |
| POST | `/api/live/fullscan/guided/skip` | Skip the guided scan's currently paused-on cable segment |
| POST | `/api/live/fullscan/guided/abandon` | Close an open guided scan honestly |
| GET | `/api/live/channels` | Channel registry (PID/DID/computed/battery) and presets |
| POST | `/api/live/session/start` | Start the live-data poll session; read-only but holds the adapter |
| POST | `/api/live/session/stop` | Stop the live-data poll session, release the adapter |
| GET | `/api/live/session` | Live-data session status: channels, achieved rates, alarms |
| GET | `/api/live/snapshot` | Latest value of every channel in the running session |
| POST | `/api/live/record/start` | Start mirroring the live session to an MES-format CSV |
| POST | `/api/live/record/stop` | Stop the live-session CSV recording |
| POST | `/api/live/alarms` | Set a warn/alarm threshold on one live channel |
| POST | `/api/live/connect/start` | Adapter probe, bus verify, VIN match, then start (or resume) the guided scan |
| GET | `/api/live/stream` | Server-sent events: live channel samples and alarms |

#### Live dashboard layouts, recordings, snapshots (17)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/live/layouts` | Every layout (built-in and user), name and page count |
| POST | `/api/live/layouts/import` | Import a layout; assigns a free id if taken |
| GET | `/api/live/layouts/{layout_id}` | One layout, full definition |
| PUT | `/api/live/layouts/{layout_id}` | Save a user layout (400 if the id is built-in) |
| DELETE | `/api/live/layouts/{layout_id}` | Delete a user layout (400 if built-in) |
| GET | `/api/live/layouts/{layout_id}/export` | Download one layout as JSON |
| GET | `/api/live/recordings` | Every replayable recording: cuore's own plus MES CSVs |
| GET | `/api/live/replay/{recording_id}/channels` | One recording's columns as {slug: {name, unit}} |
| GET | `/api/live/replay/{recording_id}/stream` | Replay a recording as SSE, same shape as /live/stream, plus replay:true |
| GET | `/api/live/custom-channels` | User-defined DID/computed channels |
| PUT | `/api/live/custom-channels` | Replace the whole custom-channel set |
| POST | `/api/live/snapshots` | Save a freeze-frame of the current widget values |
| GET | `/api/live/snapshots` | Recent snapshots, newest first |
| GET | `/api/live/snapshots/{snapshot_id}` | One saved snapshot |
| GET | `/api/live/snapshots/{snapshot_id}/csv` | One snapshot as a one-row MES-format CSV |
| GET | `/api/live/triggers` | Stored trigger rules (evaluated in the browser, not here) |
| PUT | `/api/live/triggers` | Replace the whole trigger rule set |

#### Liveboard and freeze-frame capture (9)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/live/chassis/passive` | CAN-CH passive panel: a 2 s receive-only listen decoded through the Giorgio DBC (grey A6 cable only) |
| GET | `/api/liveboard/{vin}` | Live channels grouped by system, rated and graded against known-good |
| POST | `/api/liveboard/evaluate` | Grade a set of live values; recommendations, excessive first |
| POST | `/api/liveboard/{vin}/snapshot-to-job` | Score a saved liveboard snapshot against the current job's hypotheses |
| POST | `/api/liveboard/{vin}/freeze/capture` | Start a freeze-frame capture: stored codes, then every supported PID's freeze frame + a Mode 01 snapshot, plus readiness -- read-only, held unsaved for 30 minutes |
| GET | `/api/liveboard/{vin}/freeze/status` | Poll a freeze-frame capture's progress |
| POST | `/api/liveboard/{vin}/freeze/stop` | Stop a running freeze-frame capture; data already read is kept and the capture ends partial |
| POST | `/api/liveboard/{vin}/freeze/save` | Save a finished freeze-frame capture into the CUORE log as from-car observations; returns the scan id it lands under |
| POST | `/api/liveboard/{vin}/freeze/discard` | Discard an unsaved freeze-frame capture |

#### MES log corpus (3)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/logs` | The log index, newest first |
| GET | `/api/log/{name}` | One log, verbatim |
| GET | `/api/search` | Regex search across logs |

#### Media (7)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/vehicles/{vin}/media` | Upload one or more media files |
| GET | `/api/vehicles/{vin}/media` | Search this vehicle's media |
| GET | `/api/vehicles/{vin}/media/export.zip` | Export every file plus the index, for recovery |
| GET | `/api/media/{id}/file` | The original media file |
| GET | `/api/media/{id}/thumb` | 320px thumbnail (or first frame, for video) |
| POST | `/api/media/{id}` | Edit caption, tags, target, symptom tags, or feels_like |
| POST | `/api/media/{id}/hide` | Hide a media item (soft delete) |

#### MES learn (6)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/mes-learn/start` | Start the passive listener on a second adapter |
| GET | `/api/mes-learn/status` | Poll the running (or just-stopped) listener |
| POST | `/api/mes-learn/stop` | Stop the listener and align its capture against an MES CSV recording |
| GET | `/api/mes-learn/candidates` | Fit candidates from the last alignment |
| POST | `/api/mes-learn/candidates/{candidate_id}/accept` | Accept a candidate: saved as a learned, scaled channel |
| POST | `/api/mes-learn/candidates/{candidate_id}/reject` | Reject a candidate: kept observed-but-unscaled |

#### Modifications (9)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/mods/catalog` | Every known modification (paddle shift first) |
| GET | `/api/mods/catalog/{mod_id}` | One catalogue modification by id |
| GET | `/api/mods/catalog/{mod_id}/handoff` | The 'Do it in MES' handoff card, if one exists |
| GET | `/api/mods/{vin}` | This car's modification status and ledger |
| GET | `/api/mods/{vin}/non-stock` | Chips for other surfaces: this car's non-stock configuration |
| POST | `/api/mods/{vin}/record` | Record one modification done to this car |
| PATCH | `/api/mods/{vin}/{entry_id}` | Edit one ledger entry |
| DELETE | `/api/mods/{vin}/{entry_id}` | Soft-delete one ledger entry |
| POST | `/api/mods/{vin}/{entry_id}/restore` | Undo a soft-delete |

#### Owner events (Tell CUORE) (8)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/owner/{vin}/taxonomy` | Category/kind table for the Tell CUORE form |
| GET | `/api/owner/{vin}/events` | This VIN's owner-reported events |
| POST | `/api/owner/{vin}/events` | Record one owner-reported event |
| DELETE | `/api/owner/{vin}/events/{id}` | Soft-delete one owner event |
| PATCH | `/api/owner/{vin}/events/{id}` | Edit one owner-reported event |
| GET | `/api/owner/{vin}/messages` | Questions for the owner, CUORE's and the mechanic's |
| POST | `/api/owner/{vin}/messages/{id}/reply` | Owner's (or mechanic's) reply to one message |
| GET | `/api/owner/{vin}/correlations` | Owner events near each code's first/returned occurrence |

#### Parts (4)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/parts` | Every part known, with resolved torques |
| GET | `/api/parts/for-code/{code}` | Parts related to a DTC |
| GET | `/api/parts/for-job/{job}` | Parts related to a service/maintenance job |
| GET | `/api/parts/{key}` | One part by key |

#### Recordings (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/recordings` | Every recording, newest first |
| GET | `/api/recording/{name}` | Columns, timing and events |
| GET | `/api/recording/{name}/series` | One channel as a timed series |
| GET | `/api/recording/{name}/events` | Markers, dropouts, excursions |
| GET | `/api/recording/{name}/snapshot` | Post-hoc freeze frame |

#### Module reference (3)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/modules` | The module registry, grouped by domain |
| GET | `/api/modules/{abbrev}` | One module by any name MES prints |
| GET | `/api/failure-type/{byte}` | Decode a UDS failure-type byte |

#### Scan health report (3)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/scans/{vin}/{scan_id}/health` | The scan health report, as JSON |
| GET | `/api/scans/{vin}/{scan_id}/health.md` | The scan health report, as markdown |
| POST | `/api/scans/{vin}/{scan_id}/health/save` | Write the report to disk (never over a hand-written file) |

#### Scan log (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/scans/search` | Regex search across every CUORE log, newest first |
| GET | `/api/scans/{vin}` | Scan summaries for one vehicle, newest first |
| GET | `/api/scans/{vin}/diff` | Diff two scans |
| GET | `/api/scans/{vin}/{scan_id}` | One scan in full |
| GET | `/api/scans/{vin}/{scan_id}/export` | Export one scan as JSON or an MES-style log |

#### Shop visits (8)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/shop/board` | The day board: cars currently in, plus today's throughput |
| POST | `/api/shop/intake` | Take a car in: register the visit and open a linked Job |
| GET | `/api/shop/visits/{visit_id}` | One visit by id |
| POST | `/api/shop/visits/{visit_id}/status` | Move a visit to a new status |
| POST | `/api/shop/visits/{visit_id}/steps/start` | Start timing a job step (1-7) |
| POST | `/api/shop/visits/{visit_id}/steps/end` | End timing a job step (1-7) |
| GET | `/api/shop/visits/{visit_id}/release` | The release gate view for one visit |
| POST | `/api/shop/visits/{visit_id}/release` | Release the car -- advises and records, never blocks |

#### System (4)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/capabilities` | What this host can do |
| GET | `/api/health` | Liveness |
| GET | `/api/status` | Corpus inventory in full |
| GET | `/api/roots` | Configured log and CSV directories |

#### Systems graph (3)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/systems` | Every vehicle system in the graph |
| GET | `/api/systems/for-code/{code}` | Which system(s) a DTC implicates |
| GET | `/api/vehicles/{vin}/systems` | DTC-system correlation for one vehicle |

#### Systems map (2)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/systems/{vin}/state` | Live per-system map state, hot edges and session timeline |
| GET | `/api/systems/{vin}/live` | Live overlay: per-system worst live grade, scanner status, new DTCs |

#### Mechanic tests (8)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tests/catalog` | The full mechanic-test catalogue, no per-VIN state |
| GET | `/api/tests/{vin}` | The Tests view for this vehicle: catalogue, latest results, relevance ranking, counts |
| POST | `/api/tests/{vin}/{test_id}/result` | Record a test result; auto-attaches evidence on pass/fail when a hypothesis is named |
| GET | `/api/tests/mes-handoff/candidates` | Every catalogued MES function, trimmed for client-side matching against a test/step name |
| GET | `/api/tests/mes-handoff/by-test/{test_id}` | Handoff card for a mechanic-test catalogue id, or handoff: null |
| GET | `/api/tests/mes-handoff/by-text` | Handoff card matching a free-text job-step label, or handoff: null |
| POST | `/api/tests/{vin}/mes-import` | Import an MES SCAN/FES log already on a configured MES root: records it as a Scans-timeline entry (source MES) with the same health verdict a live scan gets |
| GET | `/api/tests/{vin}/mes-scans` | MES-imported scans on file for this vehicle (source MES), newest first |

#### Timeline and symptoms (5)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/timeline` | Codes vs. what the driver noticed |
| GET | `/api/vehicles/{vin}/symptoms` | Symptom reports for this vehicle |
| POST | `/api/vehicles/{vin}/symptoms` | Record a symptom report |
| POST | `/api/vehicles/{vin}/symptoms/{id}/hide` | Hide a symptom report (soft delete) |
| GET | `/api/vehicles/{vin}/code/{code}/feel` | What would the driver feel? |

#### Tools catalogue (4)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tools/catalogue` | The full mechanic-facing tools catalogue |
| GET | `/api/tools/suggest` | Next sensible tools given the current state |
| GET | `/api/tools/workflows` | Semi-automatic read-only workflows |
| POST | `/api/tools/shape` | Shape one tool's raw payload for display |

#### Tools knowledge base (6)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tools-kb/recommend/{step}` | Recommended tools for a job/step |
| GET | `/api/tools-kb/learn/{step}` | Aggregated tool-usage learning for a job/step |
| GET | `/api/vehicles/{vin}/tool-usage` | Tool-usage reviews recorded for this vehicle |
| POST | `/api/vehicles/{vin}/tool-usage` | Record a tool-usage review |
| GET | `/api/tools-kb/inventory` | The garage's owned/not-owned tool list |
| POST | `/api/tools-kb/inventory` | Record whether the shop has a tool |

#### Vehicles, corpus, dealer results, notes, verdict (20)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles` | Every vehicle in the corpus |
| GET | `/api/vehicle/{vin}` | The pre-work dossier |
| GET | `/api/vehicle/{vin}/report` | Identity and chronic faults |
| GET | `/api/vehicle/{vin}/dtcs` | Every DTC with its full history |
| GET | `/api/vehicle/{vin}/dtc/{code}` | One code's complete life |
| GET | `/api/vehicle/{vin}/freeze` | Freeze frames |
| GET | `/api/vehicle/{vin}/actuators` | What has already been tried |
| GET | `/api/vehicle/{vin}/tree` | Fault-tree isolation sequences |
| GET | `/api/vehicle/{vin}/session` | One FES engineering session |
| GET | `/api/vehicle/{vin}/scan` | One all-systems SCAN |
| GET | `/api/vehicle/{vin}/parameters` | Live parameters in a session |
| GET | `/api/vehicle/{vin}/parameter/{parameter}` | One parameter series |
| GET | `/api/vehicles/{vin}/live-vs-log` | Live UDS reads vs the newest MES log |
| POST | `/api/vehicle/{vin}/verdict` | The evidence gate |
| GET | `/api/vehicles/{vin}/dealer-results` | Dealer (wiTECH) results |
| POST | `/api/vehicles/{vin}/dealer-results` | Record a dealer (wiTECH) result |
| GET | `/api/vehicles/{vin}/notes` | Technician notes for this vehicle |
| POST | `/api/vehicles/{vin}/notes` | Record a technician note |
| POST | `/api/vehicles/{vin}/notes/{id}/edit` | Amend a note's text |
| POST | `/api/vehicles/{vin}/notes/{id}/hide` | Hide a note (soft delete) |

#### Photo reading (2)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vision/status` | Which photo-reading provider is configured |
| POST | `/api/vision/{vin}/read` | Read one photo (odometer, fuel pump, oil bottle, part label, or receipt) |

#### Dashboard (1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/dashboard` | Per-vehicle dashboard |

#### Service and maintenance (8)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/service-records` | Service records for this vehicle |
| POST | `/api/vehicles/{vin}/service-records` | Record a service event |
| GET | `/api/vehicles/{vin}/oil-change/next` | Next oil change due |
| GET | `/api/vehicles/{vin}/brakes-tires/checklist` | Brakes and tyres checklist |
| GET | `/api/vehicles/{vin}/maintenance` | Maintenance schedule state |
| POST | `/api/vehicles/{vin}/maintenance` | Record a maintenance item done |
| GET | `/api/vehicles/{vin}/maintenance/due` | Maintenance items due |
| GET | `/api/vehicles/{vin}/torque` | Torque specs for this vehicle |

#### Drivetrain (3)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/service-hub` | Drivetrain service hub view |
| GET | `/api/vehicles/{vin}/drivetrain/{section}` | One drivetrain section (read) |
| POST | `/api/vehicles/{vin}/drivetrain/{section}` | Record a drivetrain section entry |

#### Labels (1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/vehicles/{vin}/labels/templates` | Label templates for this vehicle |

#### Jobs (JSON helpers on the web router) (1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/jobs/{job_id}/hypotheses/{hyp_id}/plan` | Mechanic plan for one hypothesis (JSON) |

#### Bulletins (1)

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/tsb/xref` | Bulletin cross-reference for a VIN (JSON; vin query parameter) |

