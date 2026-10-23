# CAN-IHS discovery, 2026-10-23 (blue A5 cable)

Car: 2018 Stelvio, VIN ZASFAKPN5J7B88115. vLinker FS on COM3, blue A5 declared,
route STP 34 (29-bit UDS) / STP 33 (11-bit listen), 125 kbit/s only. Every
statement below is a CUORE reading; raw responses are in
`data/captures/stelvio-2018/scans/2026-10-23_blue_can_ihs/` (see its `INDEX.md`).

## What was and was not done

Done: verify, one bounded discover (40 targets), identity read of the two
responders (inside discover). **Not done**, because the owner removed the blue
cable at about 00:50 and the coordinator ordered all car contact stopped:
`19 02 FF` / `19 0A` on the responders, the ETM/radio DID probe, and the two
30 s passive listens. There are therefore **no DTCs read from any CAN-IHS
module** and no radio identity.

## The discover bug and fix

`POST /api/live/discover {"bus":"can_ihs"}` with no candidates sweeps 253 targets
(`addressing.sweep_candidates`). The session assumes the adapter's ATSTFF reply
wait (1.02 s), so `discover` floored every silent target at 1.22 s. The audit log
of the first call shows `tried 253, hits 6` between 00:27:16 and 00:32:06, i.e.
290 s: not a hang, but longer than any client waits, and the six hits were lost
when the client disconnected (no hit is persisted unless it is proven to be this
car and named in the registry). The second call was cut off by a CUORE restart.
The 00:12 can_c call was fast because it was given a short candidate list.

Fix (commit f413c7b, `cuore/live/uds.py`, `ops.py`, `api/live.py`):
- `ATST` is set to `per_target_timeout` for the sweep (`untarget()` restores ATSTFF);
  silent targets now cost about 0.42 s.
- `deadline_s` (default 60 s, max 170 s): at the deadline the call returns the hits so
  far with `partial: true` and the `untried` list.
- `max_targets`, and a 6 s cap on identity reads per target.
- every target is logged to server.log (`cuore.discover`).

Check: a fake-session run stopped at 1.0 s with 16 tried / 237 untried; the live
40-target call took 16.6 s plus 1.4 s for 3 more.

## Modules found

Candidates (40): registry HVAC 0x68 and ETM 0x6F; the keep-alive low bytes heard on
the bus (00 03 0A 24 30 34 45 67, the AUTOSAR-NM hypothesis in
GIORGIO_MODULE_MAP.md); stelvio_scan constants 38 and 6D; 01 02; the 0x61-0x6E
neighbourhood; and a few others (04 05 08 09 0B 20 23 25 31 35 44 46 60 70 71).
The repo holds no "Giorgio body-bus list", so this set is evidence-derived, not
authoritative. Functional 18DB33F1 was not swept (discover only does physical pairs).

| Target | Request / response | Answer | Identity (`22`) |
|---|---|---|---|
| 0x62 | 18DA62F1 / 18DAF162 | F190 = ZASFAKPN5J7B88115 | F187 50538672, F188 (sw) 952J1SW6X01, F191 (hw) 952J1HW6X01, F192 633633000A, F194 633633800D, F18C TC4852217303980 |
| 0x65 | 18DA65F1 / 18DAF165 | F190 = ZASFAKPN5J7B88115 | same except F18C TC4852217304000 |

The two nodes carry the same part, hardware and software numbers and differ only
in serial, so they are a twin pair. The readings do not say which modules they are
(a left/right pair such as LBSS/RBSS is a guess; the numbers match nothing in
Table A). They are registered as `IHS62` and `IHS65`, confirmed addresses, with no
module claim.

Silent (no reply to `22 F190` at 0.3 s): 0x68 (HVAC), 0x6F (ETM/radio), and the
other 35 targets. HVAC and ETM remain unverified; silence at 0.3 s is not proof of
absence. The earlier full sweep found six answering targets, so four more exist
somewhere outside the 40 tried here; a further bounded sweep (60 s windows with
`untried` as the next candidates) would find them.

## DTCs

None read (see above).

## ID histograms (passive, from verify listens; the 30 s listens were not run)

Verify at 00:47:30 (3 s per route, frame cap 200):
- STP 34, 29-bit: 18 frames, 9 ids, two each: 1E340000, 1E340003, 1E34000A,
  1E340024, 1E340030, 1E340033, 1E340034, 1E340045, 1E340067.
- STP 33, 11-bit: 201 frames, 54 ids. Eight at 12: 3E2, 3E4, 3E6, 3E8, 3DC, 3DE, 3E0,
  2F0. 305 and 307 at 6. 4F6, 356, 358, 258, 25A at 5. 4F4, 354 at 4. 44A, 44C at 3.
  The rest at 1-2: 5E6 5E8 764 5AA 5B0 75C 766 46A 46C 468 7C0 5AC 5A6 5BC 5B6 5C0
  5C4 5C6 5CE 5C2 5A8 5CA 760 738 762 5BE, plus the nine 1E34xxxx ids again.
- Earlier same-night 20 s verify (`06_verify_listen_20s.json`): the nine 29-bit ids at
  20 frames each (180 frames, 9.0/s), i.e. a steady keep-alive of roughly 1 Hz each.

DBC decode: `cuore/data/dbc/fca_giorgio.dbc` (37 messages, CAN-CH) defines none of the 11-bit ids heard here
(nearest: 0x259, 0x2FA, 0x2FE against heard 258, 25A, 2F0), so nothing was decoded.
The 7xx ids heard (738, 75C, 760, 762, 764, 766, 7C0) are not interpreted.

## Hazard note

Cable removal caught the session mid-run. At 00:50:02 and 00:50:08 CUORE's built-in
functional `3E 00` probe (STP 34, 125k) ran on the no-traffic bus and both times
returned the adapter's CAN ERROR. The cable was already off at 00:49:58 (0 frames),
so those frames may have been attempted onto CAN-C at the wrong rate; none was
accepted by any bus and nothing answered. Watch for bystander U-codes.

## Correction 2026-10-23

Owner-attested via MES (not a CUORE reading): MES did not request the blue adapter for the Radio/Nav entry; with the blue A5 cable fitted the radio did NOT connect while the climate control (HVAC) did; with the adapter alone (no cable) the radio connects. The radio (ETM, Marelli AlfaConnect Radio-Nav) is therefore on CAN-C (main bus), not CAN-IHS, and HVAC on CAN-IHS is MES-confirmed. This explains why 0x6F stayed silent in the sweep above: CUORE asked on the wrong bus for it. The radio's CAN-C address is still unverified by CUORE (likely 0x6F / 18DA6FF1); to be confirmed by a CAN-C discover on a later session. Where this document says ETM is a CAN-IHS candidate, read CAN-C.
