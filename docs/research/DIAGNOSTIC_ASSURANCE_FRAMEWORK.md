# Diagnostic Assurance Framework — what a solo mechanic needs before wrenching

**Captured:** 2026-08-31. Design question: an Alfa specialist with very little
time, no assistance beyond MultiEcuScan + this toolchain — what must exist so
work is correctly diagnosed *before* it begins?

**Honest framing:** 100% certainty does not exist and aviation does not claim
it. What aviation maintenance has is a system where **you cannot proceed on a
guess**: every diagnosis is evidence-backed, checked against reference data,
follows a written fault-isolation procedure, and is not signed off until a
verification test passes. That system is mostly software, and mostly buildable
over what this toolchain already parses.

---

## The six pillars, ranked by where a time-poor mechanic bleeds hours

| # | Pillar | Aviation analogue | Status |
|---|---|---|---|
| 1 | **One-command workup** — the pre-work dossier | Squawk + history review | ✅ **Built 2026-08-31** — `workup(vin)` |
| 2 | **Known-good reference data** — limits per parameter | AMM limits tables | ❌ Biggest gap. Part research, part software |
| 3 | **Fault-isolation trees** — per-DTC guided sequences | The FIM | ✅ **Built 2026-08-31** — `fault_tree`: EVAP leak family + P1CEA boost-purge |
| 4 | **Evidence gate** — refuse "confirmed" without the proof | RTS sign-off criteria | ✅ **Built 2026-08-31** — `diagnosis_verdict` |
| 5 | **Repair verification** — measured pass, not absent light | Post-maintenance operational check | 🟡 readiness + Mode $0A built; **Mode $06 pending** |
| 6 | **The recorder habit** — CSV recording on every road test | FDR | ✅ pipeline built 2026-08-31; MES config ritual remains |

### 1. Workup — BUILT

`workup(vin)` in `mes-log-mcp` assembles in one call: identity + odometer
span; current picture — including **the newest session that actually held
findings** when the latest is an empty post-clear re-read (the silence after
a clear must never read as a healthy car); chronic vs returned-after-clear vs
seen-once classification; freeze frames; network-cascade detection; **TSB
cross-references** (`mes/knowledge.py`); everything already attempted; and an
explicit **blind-spots** section naming what the logs structurally cannot
answer and which live tool closes each one (readiness, Mode $0A, Mode $06,
EVAP fuel-level window).

`mes/knowledge.py` carries the curated bulletin table — every entry
transcribed with source from `docs/reference/TSB_CATALOGUE.md`, scope caveats
kept. Family rules encode the two costliest misreadings: several EVAP codes
= **one** fault; a spread of U-codes = **one** power/bus event, supply side
first (S1808000005) before grounds (S2008000032) before terminals
(S1708000262).

### 2. Known-good reference data — THE GAP

A live value without a limit is noise. Needed: per-parameter spec table for
the IAW 10JA / GME-T4 — nominal range, condition (idle / cruise / KOEO),
source, confidence — from published FCA data, `ZF8HP_SERVICE_DATA.md`, and
this car's own healthy sessions as self-baseline. Then `recording_series` /
`snapshot` / `parameter_series` flag in/out-of-range automatically.

### 3. Fault-isolation trees — BUILT

`fault_tree(codes, vin)` in `mes-log-mcp` (`mes/faulttree.py`). Two trees:

- **evap-leak** (P0440/P0441/P0455/P0456): E1 quick-connect (S2125000002)
  → E2 canister filter (9100468) → E3 KOEO purge/vent actuator tests →
  E4 refuelling interview (early click-off ≈ blocked canister) → E5 hose
  routing (9100325) → E6 flooded-canister/FDM check (9100471) → E7 smoke
  (low pressure). Verification: road test explicitly refused (18-048-23);
  SLVT or Mode $06 + readiness + Mode $0A. Five do-not guards (purge
  solenoid alone, gas cap, standalone vent valve, post-clear scan as proof,
  canister-for-ESIM swap).
- **p1cea-boost-purge**: PCM software level (18-023-23 REV. B) → air-cleaner
  quick-connects (25-002-23 technique) → ejector-tee directional blow test →
  CAC/air-cleaner port flash → FTP circuits → solenoid last, per FCA's own
  cause list. Framing: P1CEA is a flow monitor, not a leak monitor.

With a VIN, steps are annotated from the corpus — on this Stelvio, E3 is
flagged: the purge valve already COMPLETED 6 actuations while P0456 was
stored, so weight the vent/canister side. Leak codes order before P1CEA
automatically when both are present.

Build order note: the build went 1 → 3 (workup then trees) because the tree
consumes what the workup surfaces; the evidence gate (4) is next.

### 4. Evidence gate — BUILT

`diagnosis_verdict(vin, codes, component, mechanism, measurements,
disconfirming_test)` in `mes-log-mcp` (`mes/verdict.py`). Four criteria:

1. **Demonstrated** — chronic / returned-after-clear / standing, judged from
   the corpus automatically. Seen-once-then-cleared explicitly fails.
2. **Mechanism** — a causal sentence; a part name is rejected.
3. **Measurement** — cited evidence is *verified against the logs*:
   actuator outcomes, freeze frames, live parameters (with a static-value
   caution), CSV recording events. A DTC offered as a measurement is
   rejected outright; a fabricated citation comes back `not_found`. Manual
   tests (smoke) are accepted as operator-attested and labelled as such.
4. **Disconfirmation** — the test that would have exonerated the part,
   described with its result.

NOT CONFIRMED always names the missing criteria and pulls the next test
from the fault tree ("evap-leak step E1 ..."). The condemned component is
checked against the platform do-not list even when the gate passes — the
canister/ESIM 9100469 caution shows on a confirmed canister diagnosis.

### 5. Repair verification

Done: `read_readiness` (monitor ran?), `read_permanent_dtcs` (Mode $0A
standing?). Pending: **Mode $06** — the measured leak value against the ECM's
own threshold; the only non-dealer equivalent of the wiTECH SLVT that
18-048-23 requires for small-leak verification.

### 6. Recorder habit

CSV pipeline built (see `CSV_LOG_FORMAT.md`). Ritual: Graph tab → params →
Monitor DTCs → CSV Start on **every** road test. Costs nothing; catches the
intermittent that a parked scan never will.

---

## Interfaces (2026-08-31)

The six pillars above were built as MCP tool functions, callable only from
inside a Claude Code conversation. That's fine for building and reasoning
through a diagnosis, but not for standing at a fender with a phone. Three
usable interfaces now exist:

1. **`web-ui/` Flask app** — phone/tablet pages over `workup`, `fault_tree`
   and `diagnosis_verdict`, importing `mes` directly so every page is live
   against the current corpus. Run `python web-ui/app.py`, open
   `http://<LAN IP>:5000`. The evidence-gate page builds the
   `diagnosis_verdict` measurement JSON from a form instead of requiring
   hand-typed JSON.
2. **Claude Code itself** — the original interface; still the right choice
   for talking through reasoning rather than clicking forms, from the
   terminal or Claude Code's mobile/desktop app.
3. **Static Artifact checklist** — a point-in-time HTML job card for one
   vehicle's current diagnosis, good for printing or texting. Explicitly
   NOT live-connected; regenerate after new codes are pulled. First one:
   the Stelvio EVAP job card, https://claude.ai/code/artifact/13b57a29-701e-4ff5-8290-c5613bb484dd

---

## Build order (car not needed except where marked)

1. ✅ Workup (done)
2. ✅ EVAP fault-isolation tree (done)
3. ✅ Evidence gate (done)
4. Known-good tables — seeded from docs, grown per verified spec
5. Mode $06 tool — **needs the car** for the MID probe
6. Remaining from `MES_CAPABILITY_GAPS.md`: capability-matrix ingestion,
   `English.dat` decode tables, simulation-mode enumeration, A5/A6 cables,
   high-rate voltage logging
