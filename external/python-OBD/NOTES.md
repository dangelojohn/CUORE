# python-OBD (NOTES ONLY, nothing copied)

- URL: https://github.com/brendan-w/python-OBD (last push 2025-04-07 per the 2026-10-20 review)
- Licence: GPL-2.0 (copyleft). Not copied: CUORE must stay free to be distributed under its own terms. Nothing from this repo, including its data tables, is stored here.
- Source of these notes: our own 2026-10-20 review (docs/research/GITHUB_REVIEW_TOOLING.md), pages read via a summarising fetch; paraphrase-grade, not byte-verified.

## Facts and techniques (all leads, unverified on our car)

- Mode 06 reply layout on CAN: after the 0x46 service byte, repeating 9-byte blocks of OBDMID, TID, UASID, value (2 bytes), minimum (2), maximum (2). This is the J1979 layout; CUORE's `mode06.decode_mode06_records` already uses it.
- The package maps each UASID to a (signed?, scale, unit, offset) tuple; signed ids are 0x81 and up, unsigned 0x01-0x41. The numeric scalings are SAE J1979 facts, so CUORE should re-derive them from the standard itself and use this package only as an after-the-fact cross-check (compare numbers by reading, never paste).
- Its manufacturer-test coverage is only the O2 sensor and misfire test ids; it has no EVAP test ids and labels Mode 06 as experimental.
- EVAP monitor ids it uses: 0x39 (cap off / gross), 0x3A (0.090 in), 0x3B (0.040 in), 0x3C (0.020 in), 0x3D (purge flow). CUORE already lists the same ids.
- ELM init order: reset (ATZ, then about 1 s wait), echo off, headers on, linefeeds off; protocol auto then a 0100 probe; fallback loop over protocol numbers. The only failure text it checks is UNABLE TO CONNECT.

## Why not copied

GPL-2.0 terms would attach to anything derived from the code or its tables. The useful part (the standard's unit table) is available from the standard itself.
