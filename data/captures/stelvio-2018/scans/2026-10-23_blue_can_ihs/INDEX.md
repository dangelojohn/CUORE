# Blue A5 / CAN-IHS read-only session, 2026-10-23 (Stelvio ZASFAKPN5J7B88115)

Outcome: PARTIAL. Bus verified passively; all UDS reads (steps 2-5) NOT done.

## Files
| File | Content |
|---|---|
| 00_status_before.json | /api/live/status after CUORE restart (port COM3, cable none) |
| 01_cable_declare.json | POST /api/live/cable {"cable":"blue_a5"}; can_ihs route = STP 34, 125000, status "untested" |
| 02_verify_can_ihs.json | POST /api/live/verify can_ihs 3 s: verified, passive_listen |
| 03_modules_can_ihs.json | /api/live/modules?bus=can_ihs registry |
| 04_buses.json | /api/live/buses |
| 06_verify_listen_20s.json | second passive verify, 20 s window (frame cap 200) |
| 07_cable_none.json | POST cable none (declaration only) |

## Verify
verified=true, 27 frames / 3 s on STP 34 (29-bit), 201 frames on STP 33 (11-bit). No transmit.
29-bit keep-alive ids (9): 1E340000, 1E340003, 1E34000A, 1E340024, 1E340030, 1E340033, 1E340034, 1E340045, 1E340067.
11-bit ids (54): 3E0-3E8 (even), 3DC, 3DE, 2F0, 305, 307, 258, 25A, 354-358, 4F4, 4F6, 44A, 44C, 468-46C, 5A6-5C6 range, 5E6, 5E8, plus 738, 75C, 760, 762, 764, 766, 7C0 (7xx ids look like diagnostic-range; not interpreted).

## Modules answered
None queried. Registry for can_ihs: HVAC (18DA68F1) and ETM (18DA6FF1) have addresses but confidence=unverified, usable=false; AMP, ESEM, CSWM, CRSM, LBSS, RBSS, PLGM have no address. CUORE's module endpoints refuse unverified targets, so the only way to reach HVAC/ETM is POST /api/live/discover (22 F190 at 68, 6F).
IPC (0x60), BCM (0x40), RFHUB are registered on can_c, not can_ihs; unreachable with the blue cable.

## DTCs / identity / radio / IPC odometer
Not read.

## Skipped and why
- Discover 22 F190 at 68/6F (step 2/3/4): the call was denied by the Claude Code auto-mode classifier ("Security Weaken"). Not worked around. Note it would have transmitted on CUORE's preferred blue_a5 route (STP 34, 29-bit, 125k, status "untested"), not the STP 33 route the brief described as confirmed; CUORE has no HTTP way to select STP 33 for UDS.
- IPC odometer probe (step 5): IPC is on can_c, not reachable with blue_a5; HTTP /api/live/discover does not expose probe_dids anyway.
- 11-bit decode (step 6): done only as the passive verify id list above; no decode endpoint other than capture (forbidden).
- Step 7: cable set back to none (declaration, no wire traffic).
---
## Second pass (2N_ files, 00:45-00:51) -- after the discover fix (commit f413c7b)

Stopped early: the owner removed the blue cable around 00:50; the coordinator ordered no further car contact. Steps 3 (beyond discover's identity reads), 4, and the two 30 s listens were NOT run.

| File | Content |
|---|---|
| 20_cable_declare.json | POST cable blue_a5 (after CUORE restart; declaration resets to none on restart) |
| 21_verify_can_ihs.json | verify can_ihs: verified, 18 frames STP 34 (9 ids) + 201 frames STP 33 (54 ids) |
| 22_discover_request.json / 22_discover_can_ihs.json | discover, 37 targets, 0.3 s, 16.6 s total, 2 responders: 0x62 and 0x65 |
| 23_discover_request.json / 23_discover_can_ihs_extra3.json | 3 more targets (60, 70, 71): silent. 40 targets in all |
| 24_cable_redeclare.json | cable blue_a5 declared again after the registry restart |
| 25_verify_can_ihs.json | verify FAILED: 0 frames on both routes, then CUORE's built-in functional 3E 00 probe returned CAN ERROR (cable apparently already removed). One 125k transmit may have reached CAN-C |
| 26_modules_can_ihs.json | registry for can_ihs after the edit (IHS62, IHS65 confirmed) |
| 27_verify_retry.json | verify under cable 'none' (declared by the coordinator): STP 54 passive listen, 0 frames |

Earlier-pass files 00-11 are from the first (partial) session of the same night; 06_verify_listen_20s.json is the 20 s histogram.

Disclosure (audit.jsonl): cable re-declared blue_a5 at 00:49:56; passive listens at 00:49:58 / 00:50:01 saw 0 frames; CUORE's built-in functional UDS 3E 00 probe (STP 34, 125k, 18DB33F1) was then sent twice (00:50:02 from my POST verify, 00:50:08 from my GET module/IHS62/dtcs auto-verify), both returning the adapter's CAN ERROR (no frame accepted by the bus). The cable was evidently already off the car; whether those two frames reached CAN-C is not known. The coordinator declared cable 'none' at 00:50:23.
