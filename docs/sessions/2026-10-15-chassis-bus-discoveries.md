# Chassis bus discoveries - 2026-10-15

Durable record of what was learned on the car about the chassis buses (CAN-CH, CAN-IHS) and the CUORE listen/discovery path. Vehicle: 2018 Alfa Romeo Stelvio, VIN ZASFAKPN5J7B88115. Adapter: vLinker FS r2 / STN1170 v4.3.2 on COM3. Everything below was verified on the car unless marked untested or not yet run.

## Index
1. Passive listen was blind (fixed, c57de05)
2. Incident 2026-10-14 23:58-00:00 (tool-caused warning lamps)
3. 29-bit discovery on CAN-CH: the ABS is 0x2A
4. ABS silent to the DTC sweep (cause unknown)
5. Guided scan changes
6. Scan SCAN_2610141901 state
7. Open questions and next on-car tests

## 1. Passive listen was blind

CUORE's listen used the filtered monitor `STM` with `ATCAF1`. On CAN-CH through the grey A6 cable at 500k it heard 0 frames.

`STMA` (monitor all, ignores the filter table) with `ATCAF0` heard 818 frames in 2 s over 29 IDs (0DE, 0EE, 0FC, 106, 10E, 116, 11C, 122 ...), all 11-bit. A 29-bit protocol monitor (`STP 34`) with `STMA` heard only one id.

Conclusion: Giorgio periodic traffic is 11-bit. The three "silent" buses earlier on 2026-10-14 were the monitor, not the car.

Fix (commit c57de05):
- `cuore/live/capture.py`: `ATCAF0` + `STMA` unless the caller asked for pass filters.
- `cuore/live/buses.py`: 11-bit listen routes added. CAN-CH `STP 33` confirmed. CAN-IHS `STP 33` + `STPBR 125000` untested.

## 2. Incident 2026-10-14 23:58-00:00

A scratchpad pyserial script was run directly on COM3, outside CUORE's session, audit and safety layer. It listened at 250k and 125k as well as 500k (three receive-only windows of about 2 s each). The adapter reported CAN ERROR. The owner heard a chime and saw the airbag lamp and other warning lamps.

Rules now in `cuore/live/buses.py` and in memory:
- Never open a bus at any rate but its confirmed one.
- All adapter contact goes through CUORE sessions.
- The old CAN-CH route note "if silent try STP 36 then STPBR 125000" is withdrawn.

Any ABS/EPS/ORC/IPC/BCM lost-communication codes dated in that window are tool artefacts. Notes to that effect are on the vehicle record.

## 3. 29-bit discovery on CAN-CH

Sweep: `22 F190` at `18DAxxF1`, xx 00-FF, 0.3 s each, 253 candidates, 152.7 s. One reply, from 0x2A:

| DID | Value |
|---|---|
| F190 | VIN match |
| F187 | 50553290 |
| F191 | 52086513 |
| F192 | 28554010535 |
| F194 | XJ_RAL00165 |
| F18C | TA2922017612200 |

This is the ABS (Continental MK C1). The registry had ABS 0x28 and EPS 0x2A (forum inference). Corrected: ABS 0x2A CONFIRMED, EPS unknown. `discover()` now lets a strong identity + VIN match override a non-confirmed registry address.

EPS, ORC, HALF, PAM, AFLS, TVM and ESL were silent on 29-bit. Hypothesis: they use 11-bit physical UDS ids. A new read-only `cuore/live/discover11.py` + `ops.discover_11bit` was built (`3E 00` to 0x700-0x7FF, reply id +8, identity DIDs, nothing persisted). NOT yet run on the car.

## 4. ABS silent to the DTC sweep

The ABS answered discovery at 00:08 but was silent to the DTC sweep (`19 02 FF`, same headers) at 00:12. Cause unknown. `Session.uds` now audits header + raw reply per request, so the next occurrence will be diagnosable.

## 5. Guided scan changes

- `continue_guided` accepts cable segments out of order (75ab659).
- Fitting the grey cable is the CAN-CH confirmation (f55c665).
- A segment whose sweep reached no module is "failed" and stays open, not "done".

## 6. Scan SCAN_2610141901 state

- CAN-C: done.
- CAN-IHS (blue): failed; retry open with the new listen + `3E 00` probe.
- CAN-CH (grey): recorded with ABS silent and others unaddressed; re-openable.
- Closing step: pending.

## 7. Open questions / next on-car tests (all read-only)

1. 11-bit discovery on CAN-CH (`ops.discover_11bit`).
2. Blue A5 retry for CAN-IHS.
3. ABS DTC re-read, now with the per-request audit.
4. MES-learn passive capture of a MES session on CAN-CH, to read the ids MES uses for EPS and HALF.

## Lessons

- A silent bus is a claim about the listener until a second method agrees. Check the monitor mode before concluding anything about the car.
- Raw serial on the adapter, even receive-only, is not harmless: wrong-rate listening raised CAN errors that the car showed to the owner. One confirmed rate per bus, and only through CUORE sessions.
- A registry address from a forum is a hypothesis. Identity DIDs plus a VIN match are what promote it to CONFIRMED.
- Absence on one addressing scheme (29-bit) says nothing about the other (11-bit).
- Audit what was actually sent and received (header + raw reply), or an unexplained silence cannot be investigated afterwards.
- A segment that reached nothing is failed, not done.
- Match the python-side wait to the adapter's own reply wait: after ATSTFF the adapter waits 1.02 s, and a python wait 0.25-0.5 s shorter turned the 29-bit and 11-bit sweeps into unreliable negatives (query-timing bug, fixed 2026-10-15).

## 8. Blue A5 session 00:30-01:10 (added later)

Guided scan SCAN_2610141901, 2026-10-15 00:30-01:10 local, read-only, through CUORE.

Blue A5 cable, CAN-IHS at 125k:
- Passive listen, 29-bit route: 17 frames in 2 s, all keep-alive ids 1E340000/03/0A/24/30/33/34/45/67.
- Passive listen, 11-bit route: 317 frames in 2 s over 54 ids (3E2, 3E4, 3E6, 3E8, 2F0, 3DC, 3DE, 3E0 ...). The bus is alive.
- `22 F190` (1.5 s wait each) to 29-bit targets 45, 30, 24, 03, 0A, 33, 34, 67, 00, 68, 6F, 01, 02: no reply.
- One functional TesterPresent (`3E 00` on 18DB33F1): NO DATA.
- No body module has a confirmed address, so the guided segment reached no module.

Grey A6 cable, CAN-CH at 500k:
- Alive: 438 frames in 2 s over 33 ids.
- The ABS answered `22 F190` at 29-bit 0x2A once (00:08, VIN + identity) and never again, including after an ignition cycle and an adapter warm start.
- Timing bug: the python-side wait was 0.25-0.5 s shorter than the adapter's 1.02 s reply wait after `ATSTFF`. The 253-address 29-bit sweep and the 239-address 11-bit sweep are therefore not reliable negative results. Fixed in code tonight.

Meaning: on both bypass-cable buses listening works and transmitting gets nothing back (ABS once excepted), while MultiEcuScan reads EPS/HALF through the same grey cable. Suspect the request/receive path (adapter filters after `STCFCPC`/`STP`, flow control, `ATCAF` framing, 11-bit vs 29-bit diagnostics) rather than the modules. Neutral for the EVAP hypothesis.

Next tests (read-only, engine running, through CUORE):
1. Lone CR, then `ATI`.
2. Repeat `22 F190` to ABS 0x2A with `ATST 19` + `ATAT0`.
3. `ATCRA` off + explicit `STFAP 18DAF12A` pass filter.
4. `22 F190` with `ATFCSM0`.
5. Raw ISO-TP first frame with `ATCAF0`.
6. Passive MES-learn capture of a MultiEcuScan session on CAN-CH, to read the ids MES uses for EPS/HALF.
