# CUORE write-capability plan: when CUORE may change the car, and when MES stays

**Date:** 2026-10-25. **Car:** 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115.
**Question from the owner:** can CUORE begin to make changes to the Stelvio, and is
CUORE ready to replace MultiEcuScan (MES)?

**Answer:** not yet. MES stays the tool that writes to the car. CUORE earns write
ability one low-risk procedure at a time, in the stages below, starting only after
it can learn MES's exact command sequences passively. Until then: **MES makes the
changes, CUORE does the thinking.**

Sources: `docs/research/MES_VS_CUORE_CAPABILITY_2026-10-14.md` (capability matrix,
generated from `mes-log-mcp/mes/mes_functions.py`), `cuore/live/actuate.py`
(consent and replay rules), CUORE notes 82b3090e1a85 (airbag-lamp incident,
2026-10-14) and ce54db3f26e5 (ECM decoding check, 2026-10-25).

## Where CUORE already leads

- **Diagnosis:** one job per visit, evidence, hypotheses, the history of every
  code, TSB links, electrical paths, and "prove the fix" checks.
- **Directing the mechanic:** the call at the top of the Fuses & relays, Sensors,
  Wiring harnesses and Modules pages tells the mechanic what to check now and where.
- **Honest data:** every value says where it came from; unsourced items are said
  once; invalid or suspect readings are never shown as OK.

## Why CUORE cannot replace MES yet

1. **Module security access (not the security gateway).** Two different things are
   called "security" on these cars:
   - **Security gateway (SGW):** a separate gateway module that blocks diagnostic
     writes unless the tool logs in to FCA's service. The owner reports this 2018
     Stelvio has **no** SGW. CUORE's own reads are consistent with that (it talks to
     ECM, BCM, RFHUB and the other CAN-C modules directly, with no login), though
     that alone does not prove it. So no gateway stands between CUORE and the modules.
   - **UDS SecurityAccess (0x27):** a seed/key handshake inside each module,
     present with or without an SGW. A module can require it before protected
     services (coding, adaptations, some routines). MES holds the algorithms in its
     encrypted ECU database; CUORE does not, and must not obtain them by
     reverse-engineering MES (standing rule: the MES database is never touched).
     `actuate.py` already refuses to replay any procedure that contains 0x27.
   - **What is not known:** which procedures on this car actually ask for 0x27.
     "Most adjustments and coding need it" is general knowledge, not a CUORE
     reading. Passive learning (Stage 1 prerequisite) shows it per procedure; any
     that do not use 0x27 are candidates for Stages 1 and 2.
2. **Coverage.** CUORE reaches part of the car. CAN-CH modules (ABS, steering,
   airbag, lane camera) need the grey cable; several modules have no known address
   (gear shift module, steering, adaptive headlights, parking control, and the
   CAN-IHS comfort modules).
3. **Data quality is still being proven.** On 2026-10-25 two ECM channels were found
   decoded wrongly (0x195A boost, 0x1956 atmospheric; fixed) and three remain
   unconfirmed (0x195B boost voltage, 0x1925 / 0x1926 throttle). A tool that writes
   must first read correctly.
4. **Safety record.** On 2026-10-14 one wrong-bitrate passive listen on CAN-CH set
   the airbag lamp. Writing carries far more risk than listening.
5. **Missing functions.** No graph / CSV recording; none of MES's adjustment
   procedures (PROXI alignment, service resets, battery registration). Verified
   plan for each, with this car's evidence: `docs/design/CUORE_ADJUSTMENTS_PLAN.md`
   (2026-10-26). Graph / CSV recording is being built.

## The staged path

| Stage | What CUORE may change | Gate to enter the stage |
|---|---|---|
| **0 - now** | Clear codes (built; MCP-only, typed consent phrase) | Evidence saved first; never during an open proof (e.g. EVAP job 76d3454bce75) |
| **1 - next** | Actuator tests MES runs **without** SecurityAccess, e.g. ESIM vent command, purge valve | MES sequence learned passively (see Prerequisites); consent phrase; engine-state checks; scan before and after; automatic abort; one procedure at a time |
| **2 - later** | Service resets: oil change, service interval | Only if the learned sequence shows **no** 0x27; values read and saved before any write; restore path recorded |
| **3 - stays in MES** | PROXI alignment, battery registration, any coding | Not planned for CUORE: risk of a module that will not start or not communicate |
| **Never** | Reflash, immobiliser / keys, airbag / ORC, odometer | Out of scope |

## Prerequisites for Stage 1

- **Second OBD adapter + Y-splitter on CAN-C** (pins 6/14). CUORE's MES-learn
  listener (`obd2.mes_learn_start` / `mes_learn_stop`) records MES's requests while
  MES runs a procedure, never transmitting. This PC has only the one adapter on
  COM3 today. Buying hardware is the owner's decision (no product recommended).
- **Battery support** during any write session (stable voltage; CUORE reads ATRV).
- **Learned sequence review:** each learned procedure is checked by `actuate.py`'s
  replay rules (allowed services 0x10/0x3E/0x2F/0x31/0x22/0x19; no 0x27; no
  configuration, reflash or reset services) before it can become a CUORE action.
- **Dry run:** the procedure first runs against CUORE's simulator/test client.
- **Audit:** every request and reply is written to `audit.jsonl` (already done
  for reads).

## Rules that apply at every stage

- No raw adapter scripts; every COM3 contact goes through CUORE sessions, at the
  bus's confirmed bitrate only.
- Writes are MCP-only with a typed consent phrase; never over the web UI's HTTP
  routes.
- Read before write; save the value; scan before and after; any new fault code is
  a failure: record it, do not clear it.
- Conclusions cite CUORE readings; outside facts are labelled.

## First concrete step

Choose one Stage 1 candidate (recommended: the **ESIM commanded vent test**, which
also serves the EVAP job). With the second adapter fitted, run it once in MES while
CUORE listens, review the learned sequence, then decide whether CUORE may run it.
