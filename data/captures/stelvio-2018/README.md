# Captured data — reference car (2018 Alfa Romeo Stelvio 2.0T)

Snapshot of what CUORE and MultiEcuScan collected from the reference car, copied 2026-10-20.

- `cuore_state/`: CUORE state directory (observations.jsonl = every reading with timestamps; audit.jsonl; jobs.jsonl = jobs, hypotheses, actions; fullscan_*.json; learned_dids.json; addresses.json; notes, symptoms, checklists). Backups and machine logs excluded.
- `mes_logs/`: MultiEcuScan scan logs (SCAN_*.txt) for this car and its real live recordings (FESLog_*.txt). MultiEcuScan simulation-mode logs ("SIMULATION MODE ... NOT REAL") are excluded.

Point-in-time copy; the live system keeps writing to the original locations. See docs/research/CEL_2026-10-19_DIAGNOSIS.md.
