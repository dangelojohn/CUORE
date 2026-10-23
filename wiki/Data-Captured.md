# Data Captured

`data/captures/` holds a snapshot of what CUORE and MultiEcuScan collected from the reference car. It exists so that the case ([[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]) can be re-read and re-analysed from the original readings. The index file is [data/captures/stelvio-2018/README.md](https://github.com/dangelojohn/CUORE/blob/main/data/captures/stelvio-2018/README.md).

It is a **point-in-time copy**, made 2026-10-20. The live system keeps writing to the original locations.

## Layout

```
data/captures/stelvio-2018/
├── README.md
├── cuore_state/     CUORE's state directory, copied (backups and machine logs excluded)
└── mes_logs/        MultiEcuScan logs for this car
```

### `cuore_state/`

| File | Content |
|---|---|
| `observations.jsonl` | Every reading with timestamps: the evidence record ([[Evidence Model|Evidence-Model]]) |
| `audit.jsonl` | Sessions, cable declarations, verification, discovery, capture |
| `jobs.jsonl` | Jobs, hypotheses and actions |
| `cases.jsonl`, `shop_visits.jsonl` | Closed-job memory and visit records |
| `fullscan_guided.json`, `fullscan_last.json` | Guided scan state and the last scan's coverage |
| `learned_dids.json` | Data identifiers learned from passive capture |
| `addresses.json` | Module addresses confirmed per car |
| `live_snapshots.jsonl` | Saved live-data snapshots |
| `mes_clear_watch.json`, `mes_imports.json` | Clear auto-sync point and imported MES scans |
| `notes.jsonl`, `symptoms.jsonl`, `feedback.jsonl`, `owner_events.jsonl`, `experience_inputs.jsonl`, `checklists.json` | Attested human input and checklist state |

### `mes_logs/`

**42 real files**: 23 live recordings and engineering sessions (`FESLog_*.txt`) and 19 scan reports (`SCAN_*.txt`) for this car, dating from 2025-09 to 2026-10. The snapshot first also held the simulation logs; **38 were removed on 2026-10-20** because they do not describe the car. **MES simulation-mode logs** (those whose banner reads "SIMULATION MODE ... NOT REAL") are **excluded**: they do not describe the car ([[MES Integration|MES-Integration]]).

The September 2026 MES backup (97 logs) was audited on 2026-10-23 and added **no new logs**: all 25 genuine Stelvio logs in it were already held byte-for-byte, and the other 72 are simulation-mode or other cars ([docs/research/MES_LOGS_2025-10_TURBO_ERA.md](https://github.com/dangelojohn/CUORE/blob/main/docs/research/MES_LOGS_2025-10_TURBO_ERA.md)).
Only three genuine logs predate 2026 (2025-09-24 and the two of 2025-10-14, all ECM only); every Stelvio session logged between 2025-10-15 and 2025-10-27 is a simulation, so P0456 is first seen 2025-09-24 and the BCM network codes only from 2026-06-07.

Module software and hardware identities read on 2026-10-23 (ECM, BCM, TCM, IPC, RFHUB; the numbers wiTECH's Flash tab is compared against) are tabulated in [docs/vehicles/ZASFAKPN5J7B88115/MODULE_SOFTWARE_LEVELS.md](https://github.com/dangelojohn/CUORE/blob/main/docs/vehicles/ZASFAKPN5J7B88115/MODULE_SOFTWARE_LEVELS.md).

## How to use it

- Point `CUORE_STATE_DIR` at a copy of `cuore_state/`, and `MES_LOG_DIR` at a copy of `mes_logs/`, to run CUORE against this data. Work on copies: the app appends to these files.
- The tests build fixtures from copies of this kind of data rather than reading the originals ([[Testing]]).
- Time-sensitive facts in the case (for example, which clears came before which reads) can be rechecked directly from `observations.jsonl` and the SCAN files.

## Notes on handling

- The files contain the car's vehicle identifier and records typed by its owner. Treat them as personal vehicle data before sharing or republishing.
- The observation store was never rotated or rewritten; the case notes record that some freeze frames exist **only** there because the car's own copies were cleared.
- The logs are stored as written by MES; filenames carry the model name and a timestamp (`FESLog_YYMMDDHHMM_...`, `SCAN_YYMMDDHHMM`).

Related: [[Architecture]] (state directory), [[Project History|Project-History]].
