# Module code round (IPC, TCM, DTCM/ESM on CAN-C; ABS on CAN-CH)

Read-only. Car: 2018 Stelvio 2.0T, VIN ZASFAKPN5J7B88115. All adapter contact goes through CUORE sessions.
Call: `GET /api/live/round?bus=<bus>&modules=<A,B>&vin=<VIN>&confirm=<bool>` (`ops.module_code_round`).
Per module it does 19 02 (mask FF), then 19 04 and 19 06 for each code with a fault bit set
(testFailed, pending, confirmed, failedSinceLastClear; "not completed" only is skipped; max 40 codes),
stores every result as an observation, and returns `{codes, snapshots_decoded, snapshots_raw, candidate_fields}`.

## Address state (from `cuore/live/addressing.py`)

- IPC 0x60, TCM 0x18: CONFIRMED on CAN-C.
- DTCM 0x29 (18DA29F1): UNVERIFIED (source: Stelvio scan table). A round skips it ("no confirmed address")
  until a discovery sweep matches its identity (HW M0045027.01, SW M0099947) and stores the address per VIN.
- ESM: target None, UNKNOWN. DASM: same. Both are skipped with the reason, never guessed.
- Discovery (`POST /api/live/discover`) reads 22 F190, matches hardware/software numbers to Table A and saves
  a confirmed match in addresses.json for the VIN. Unmatched replies are stored as live nodes, not as DTCM/ESM.
- The existing GET /live/scan did 19 02 only; the round adds 19 04, 19 06, the ABS inclusion and `candidate_fields`.

## 1. CAN-C round (no cable)

1. Engine off, ignition ON. Plain adapter, HS/MS on HS. MultiEcuScan closed or disconnected.
2. Declare cable `none`. Run the coverage baseline (`c_first`) first if it is not done: later passes are judged against it.
3. Optional, to try DTCM/ESM: `POST /api/live/discover {"bus":"can_c","vin":"<VIN>"}`; check `hits` for an identity match.
4. `GET /api/live/round?bus=can_c&vin=<VIN>` (default modules IPC, TCM, ESM, DTCM).
5. Expect: IPC and TCM `read: true` with a `codes` list; ESM `skipped` (no confirmed address); DTCM `skipped`
   unless step 3 confirmed it. `snapshots_raw` counts 19 04 replies CUORE can only show as raw bytes
   (`undecoded_from`); `candidate_fields` is empty for IPC/TCM (no scaffold).

## 2. Grey-cable round for ABS

1. Finish or skip `c_first`. Cable swap checklist: pass `ch` in `cuore/live/coverage.py` (`GET /api/live/coverage`)
   and `docs/research/ADAPTER_CABLES.md`.
2. Continuity-check the grey A6 cable first (no short between pins 1 and 9). Fit it and declare `grey_a6`.
3. **Pin 13 warning: the vLinker FS can put 18 V on OBD pin 13, which is CAN-CH(-) on this car. Never issue a FEPS or
   programming-voltage command during this round.** The response repeats this under `warnings`.
4. `GET /api/live/round?bus=can_ch&modules=ABS&vin=<VIN>&confirm=true` (`confirm=true` is required on CAN-CH).
5. Expect ABS (18DA2AF1) `read: true`; `candidate_fields` lists the seven unbound names; `snapshots_raw` > 0 is normal
   (ABS DID lengths are unknown). Remove the cable and declare `none` afterwards.

## 3. Binding step (owner, with MES)

1. In MES: Alfa Romeo Stelvio 2.0 Turbo 16V MultiAir > Continental ABS MK C1 > Read error codes. This screen shows the
   same per-code environmental data (operating time, startups, brake switches, battery V, speed, hydraulic and pedal
   pressure). Reference: FESLog_2609042001 (C104B-92: 12.1 V, 11.1 bar, 3.6 bar; U1700-87: 10.6 V, 2.6 bar, 0.0 bar).
   Do not run MES and CUORE on the adapter at once.
2. Open the same code in CUORE (`GET /api/live/module/ABS/dtc/<code>?vin=<VIN>&confirm=true`). Read `proposals` and
   `unresolved_did`; match raw values to the MES numbers.
3. Bind what the numbers prove: `POST /api/live/snapshot-bind {"vin","module":"ABS","did":"<hex>","field_name":"Battery voltage","length":<n>,"unit":"V","div":10}`
   (`length` and `div` only if you know them). Saved to `C:\ProgramData\cuore\snapshot_bindings.json`, shown as
   "bound (owner)". Binding a DID with `length` lets the walk continue to the next DID; repeat until no
   `unresolved_did` remains.
