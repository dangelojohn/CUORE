# External implementation review: what to build from the saved GitHub material

Date: 2026-10-20. Inputs: docs/research/GITHUB_REVIEW_GIORGIO.md, docs/research/GITHUB_REVIEW_TOOLING.md, the saved copies under `external/` (see `external/README.md` for licence status per project), and a read of `cuore/live/transport.py`, `capture.py`, `uds.py`, `mode06.py`, `dtc_detail.py`, `buses.py`, `channels.py`, `discover11.py`, `dbc.py`, `chassis_decode.py`.

Project rule applied throughout: facts from external sources are leads. Every conclusion about this car must cite CUORE's own readings. Nothing under `external/` is imported.

## Read this first: the tree was changing while this was written

When I read `transport.py` the first time it had no stale-input drain and no hard reset. A few minutes later (files stamped 08:20 to 08:22 on 2026-10-20) the tree contained `Session._drain_stale`, `Session.hard_reset` plus the `CUORE_RESET_BEFORE_LEGISLATED` flag, `cuore/live/dbc.py`, `cuore/live/chassis_decode.py`, a `chassis_passive` call in `services/liveboard_bridge.py`, `cuore/data/dbc/fca_giorgio.dbc` (same 9471 bytes as `external/opendbc/fca_giorgio.dbc`), and a `rx_mode` ("plus8", "minus280", "both") in `discover11.py`. Someone else's work is landing the first versions of items 1, 2, 3 and 4. Each item below therefore says "status in tree" (what I saw at that time) and then lists what is still open. There is no git here, so I cannot say what is committed. Re-read before acting.

Problem labels: P1 legislated route silent after UDS; P2 module answers once; P3 Mode 06 / freeze-frame decoding; P4 ESIM / EVAP; P5 unknown CAN-CH / CAN-IHS module addresses; P6 passive chassis decoding.

---

## 1. Passive CAN-CH decoder from `fca_giorgio.dbc` on the live board

- **What:** decode the CAN-CH broadcast frames with the opendbc Giorgio DBC and show them as live channels. Signals: EPS_1 0x0DE (steering angle, rate), EPS_2 0x106 (driver torque, LKA status/fault), EPS_3 0x122 (EPS torque), ABS_1 0x0EE (four wheel speeds), ABS_3 0x0FA (brake switch), ABS_5 0x116 (wheel impulses), ABS_7 0x10E (raw accel/yaw), ENGINE_1 0x0FC (RPM, pedal %), NEW_MSG_11C 0x11C (vehicle speed, scale marked estimated upstream).
- **Status in tree:** parser (`cuore/live/dbc.py`, Motorola and Intel, VAL_ tables), `chassis_decode.decode_capture()` over the `capture.listen` frame list (2 s snapshot, `INTEREST` map covers exactly the nine ids above), `liveboard_bridge.chassis_passive`, and a check file `cuore/tests/check_chassis_decode.py`. `did_catalog.BROADCAST_SIGNALS` already carries 20-odd hand-transcribed signals from the same DBC and feeds only the capture-preset listing in `channels.bus_capture_preset` (`chassis_a6`).
- **Where:** `cuore/live/capture.py` `listen()` (proven route: STP 33, ATCAF0, STMA on grey A6); `cuore/live/channels.py` (`BUS_CAPTURE_PRESETS["chassis_a6"]`, `Channel(kind=...)`); `cuore/live/buses.py` `CAN_CH` route 2.
- **Uses:** `external/opendbc/fca_giorgio.dbc` (MIT, commit 48c7f06). Provenance column: "commaai/opendbc fca_giorgio.dbc, MIT".
- **Problem:** P6 (and a side benefit for P5: ids in the DBC that are periodic must never be used as request ids, see item 4).
- **Still open:**
  1. Make it a continuous channel set on the board (a held passive session, not a 2 s snapshot), with confidence "lead, unverified on our car" until validated.
  2. Replace the hand-copied `BROADCAST_SIGNALS` rows with the parsed DBC (one source), keeping the existing `source`/`confidence` fields. Two copies of the same table will drift.
  3. Validate on our car: engine-off ignition-on: ENGINE_RPM 0; ABS_3 brake switch bit follows the pedal; EPS_1 angle follows the wheel turned by hand; ABS_1 wheel speeds near 0, then compare 0x11C and ABS_6 0x101 speed with Mode 01 PID 0D (CAN-C) on a short drive. Record the comparison; only then upgrade a signal to "confirmed on this car".
  4. Counter and checksum fields are in the DBC (4-bit counter, 8-bit checksum). The checksum algorithm is not given upstream; do not claim validity from it. Use the counter only to detect dropped frames.
  5. Unknown-scale signals (0x11C speed, ABS_2) must show raw plus "scale estimated upstream".
- **Risk:** passive, STCMM 0, no transmit, the already-proven listen route. Never a different bitrate (the 2026-10-14 airbag-lamp event came from 250k/125k windows). Bus impact: none beyond the existing listen.
- **Test:** bench first with the recorded frames (`check_chassis_decode.py` pattern) plus Motorola test vectors that come from OUR captures, not from the DBC itself. Then one on-car passive read as in point 3.
- **Effort / priority:** M / High for the validation step (decoder already exists), Medium for the continuous channel.

## 2. Drain and flush the input before every request

- **What:** guarantee a late reply or late 0x78 from request N is never read as the answer to N+1, and make stale arrivals visible.
- **Status in tree:** `Session.cmd` already did `reset_input_buffer()` before each write, and now also `_drain_stale()` (reads and discards up to 100 ms, audits `stale_input` when a full frame for the current target was thrown away). `_interrupt_and_drain()` follows a python-side timeout.
- **Where:** `cuore/live/transport.py` `Session.cmd`, `_drain_stale`, `_interrupt_and_drain`, `Session.query`.
- **Uses:** `external/opendbc/excerpts/uds_isotp_message.py` (`IsoTpMessage.send` starts with `recv(drain=True)`) and `uds_canclient_drain.py`; `external/python-udsoncan/excerpts/client_timing_send_request.py` (`conn.empty_rxqueue()` before send); `external/ELMduino/excerpts/sendCommand_flush_before_send.cpp`; `external/ObdMetrics/excerpts/DefaultCommandGroup.java` (`RECOVERY_AFTER_STOPPED`).
- **Problem:** P2 mainly, P1 secondarily.
- **Still open:**
  1. The drain happens before the write, but a late reply that arrives after the write is indistinguishable from the answer. Add a short quiet-period read after each UDS query returns its prompt (tens of ms, counted and audited), not only before the next one.
  2. `_interrupt_and_drain()` sends a bare CR after a timeout. On ELM327-family firmware an idle prompt followed by a lone CR repeats the previous command. If the prompt arrives in the instant between the deadline and the CR, that CR re-sends the last UDS request. This is a hypothesis, unverified on the STN1170 (the ELM327 command set documents repeat-on-CR; ObdMetrics also sends a bare CR in its recovery group). Test it before relying on it; if confirmed, interrupt with a different byte or check `in_waiting` for a prompt first.
  3. Look at the `stale_input` audit records from the first on-car runs before adding anything else: they say whether P2 is stale input at all.
- **Risk:** read-only, adapter side only, no bus impact.
- **Test:** bench with the stateful fake of item 8 (replies that arrive late, 7F xx 78 then final reply after the prompt). Then one on-car sequence: `22 F190` to one module, immediate repeat, repeat after 2 s; read the audit log.
- **Effort / priority:** S-M / High.

## 3. P1: reset and restore sequence after a physical session, with explicit filter clears

- **What:** when `untarget()` returns to functional addressing, restore every piece of adapter state the physical session changed, and prove it by reading it back. Concrete additions, in this order:
  1. `ATFCSM0` (default flow-control mode). `target_raw()` sets `ATFCSH<phys>`, `ATFCSD300000`, `ATFCSM1` and nothing in `untarget()` undoes them, so the user-defined flow-control header of the last physical module stays in force while talking to 7DF / 18DB33F1. This is the one concrete leftover I found by reading the code; it may or may not matter for single-frame replies, it certainly matters for multi-frame ones (VIN, Mode 09).
  2. Explicit clears, each checked for a bare `OK` (anything else is logged, not retried blindly): `STFCP`, `STFCB`, `STFCFC` (names from OBD.NET's command class), `STCFCPC` (already used), `ATCRA` (already used).
  3. Re-select the protocol (`STP <n>`, plus `STPBR` only when the route has an override), because the 2026-10-13 bench finding is that clearing filters also removes the firmware's default pass filters and only a protocol re-select restores them. Never issue a clear without the re-select.
  4. Restate `ATCP18`/`ATSHDB33F1`/`ATSTFF` or `ATSH7DF`.
  5. Read back: `STPBRR` must still read the route's bitrate (500000 on CAN-C and CAN-CH); `ATDPN`/`STPRS` equals the route. A mismatch aborts the session before any request, never "fixes" the rate.
  6. Optional hard reset with the ObdMetrics timing: 200 ms, `ATWS`, 500 ms, and check the reply contains the ELM327 banner (stn1170-tools' own success test) so the log says whether the adapter really reset.
- **Status in tree:** `Session.hard_reset()` (200 ms, `ATWS`, banner check, 500 ms, re-init, `STCFCPC`, `STP`) exists and is opt-in via `CUORE_RESET_BEFORE_LEGISLATED=1`. Items 1, 2 (STFCP/STFCB/STFCFC), 4 and 5 above are not there.
- **Where:** `cuore/live/transport.py` `Session.untarget` and `Session.target_raw` (the ATFCS* lines), `Session.hard_reset`, `AdapterLink._probe_pass_filter` (probe pattern to copy for each new command), `capture._add_filters` (already clears with STFAC and re-selects via the next session's STP).
- **Uses:** `external/ObdMetrics/excerpts/DefaultCommandGroup.java` (`CAN_ERROR_RESET`, `RECOVERY_AFTER_STOPPED`); notes in `external/OBD.NET/NOTES.md` (filter-clear names), `external/stn1170-tools/NOTES.md` (banner check, `?` resync), `external/STN1110/excerpts/reset_and_timeout_abort.nut` (ATZ+ATE0, 0x04 abort, unverified).
- **Problem:** P1 (the legislated route silent after UDS; CAN-C).
- **Risk:** adapter commands only, no new frames on the car except the legislated request that follows. The danger is wrong state, not bus load: a clear without a re-select leaves the adapter deaf (seen on the bench), so make the re-select part of the same function and fail closed. Never touch bitrate, which is why step 5 only reads.
- **Test:** (a) stateful fake from item 8 that models header, CRA, FC mode, filters; assert the exact command sequence and that the functional request then gets its reply. (b) One on-car A/B on CAN-C only, ignition on, no cable change: physical `22 F190` to ECM, then `0100` with each variant of `untarget()` in turn (current; +ATFCSM0; +explicit clears; +ATWS), one variant per session, every command and reply in the audit log. Stop at the first variant that restores the reply and keep that one.
- **Effort / priority:** M / High (first on the list).

## 4. FCA 11-bit RX offset (request - 0x280) and F132 / F194 identity probe as an alternative addressing pass

- **What:** an alternative discovery pass for EPS, ORC, HALF, PAM and AFLS. Our 29-bit F190 sweep found ABS (0x2A) but EPS was silent. CAN-CH broadcast traffic is 11-bit, and opendbc's Chrysler/FCA firmware queries answer on request id minus 0x280 for ABS, EPS, SRS, radar and cluster (`external/opendbc/excerpts/chrysler_fw_query_rx_offset.py`: DID F132 for those, F194 for engine and transmission). So: for each candidate 11-bit request id, send read-only `22 F194` and `22 F132` (single frame), accept a reply on request - 0x280 (and request + 8 as the control), and name the module by matching the returned part/software numbers to Table A.
- **Status in tree:** `discover11.discover_11bit(rx_mode="minus280"|"both")` already sweeps 0x700-0x7FF with `3E 00` then reads `IDENTITY_DIDS` (F187, F188, F191, F192, F194, F18C), through `ops.discover_11bit` with `confirm`. Missing: F132, safe candidate list, and F190 is not asked at all there.
- **Where:** `cuore/live/discover11.py` (`DEFAULT_CANDIDATES`, `discover_11bit`), `cuore/live/identify.py` (`IDENTITY_DIDS`), `cuore/live/uds.py` `discover` for the 29-bit twin (add F194 and `3E 00` as second probes there too; a module that does not implement F190 and never answers is invisible today).
- **Uses:** `external/opendbc/excerpts/chrysler_fw_query_rx_offset.py`, `uds_request_pending_loop.py` (`get_rx_addr_for_tx_addr(rx_offset)`), `isotp_parallel_query.py` (send once, listen on many addresses); `external/opendbc/fca_giorgio.dbc` for the id exclusion list.
- **Problem:** P5, and P2 (identity DID other than F190).
- **Safety finding to fix before any on-car use of this sweep:** `DEFAULT_CANDIDATES` is 0x700-0x7FF minus 0x7DF and 0x7E0-0x7EF. The Giorgio DBC lists two periodic CAN-CH messages inside that range: **0x73E (BCM_1, turn-stalk bits)** and **0x749 (NEW_MSG_749)**. A sweep transmits a frame with request id 0x73E, which is the id of a message other nodes consume. Exclude every id present in the DBC and every id heard in the passive capture of the same session. Also, with minus280 the reply id lands on 0x4AA (CAM_UNKNOWN_2), 0x4AE (LKA_HUD_1) and 0x547 (LKA_HUD_2) for requests 0x72A, 0x72E and 0x7C7: periodic frames the adapter would show as false replies; skip those requests too. Cap retries at one per id and keep the existing per-target wait (0.25 s or adapter wait + 0.2 s).
- **Evidence caveat:** the -0x280 rule comes from Chrysler Pacifica/Ram/Cherokee firmware queries, and the excerpt does not contain their request ids. Nothing says our modules use it. Treat a hit as a lead; a miss is not proof of absence.
- **Risk:** transmit on CAN-CH, so it needs the explicit human confirmation the code already requires. Read-only services only (`22`, `3E 00`). Bitrate untouched (route 2 STP 33, 500k, proven).
- **Test:** bench with the stateful fake (a module answering on request - 0x280; broadcast frames injected at 0x73E; assert 0x73E and 0x749 are never used as request ids). On car: passive capture first (item 1), build the exclusion set from it, then one sweep with confirmation.
- **Effort / priority:** S for the exclusion list and F132 (do this now), M for the 29-bit twin changes / High for the exclusion list, Medium for the rest.

## 5. P2 / P2* timing alignment and 0x78 handling

- **What:** make the adapter wait, the Python wait and the module's response-pending behaviour agree.
  1. Do not re-send on 0x78. `Session.uds()` currently re-issues the request after `0.3 * attempts` seconds (up to 3 times) when it sees `7F xx 78` with no positive reply. Upstream clients keep reading for the final reply with a longer timeout instead (opendbc: 1 s, then `response_pending_timeout` 10 s, no resend; udsoncan: P2 1 s default, then P2* 5 s default, no resend). A re-sent request while the module is still working may be answered once, then ignored or queued, which fits "answers once". Unverified: needs the audit log of a real 78 episode.
  2. Set the adapter wait deliberately: physical UDS reads use `ATST` at least P2 (our `adapter_wait` assumes ATSTFF, 1.02 s), and a pending episode reads on until P2* before declaring a timeout. `Session.query` already keeps Python's deadline at or above `adapter_wait + 0.2`; extend that to a second phase.
  3. TesterPresent: `3E 80` at about 0.5 s only while a non-default session is deliberately held (none today: `READ_ONLY_UDS` allows only `10 01`), and never leave it running into a functional request. Today `uds.tester_present` exists but nothing needs a keepalive.
  4. Log P2 and P2* actually observed per module (time from request to first byte, to final byte) so the values come from our car, not from the defaults of two Python libraries.
- **Where:** `cuore/live/transport.py` `Session.uds` (the `retries_on_pending` loop), `Session.query`, `Session._track_adapter_wait`, `untarget` (`ATSTFF`); `cuore/live/uds.py` `discover` (`per_target_timeout`), `read_dtcs`.
- **Uses:** `external/python-udsoncan/excerpts/configs_timing_defaults.py` and `client_timing_send_request.py`; `external/opendbc/excerpts/uds_request_pending_loop.py`; `external/python-can-isotp/excerpts/protocol_params_and_flowcontrol.py` (1000 ms flow-control and consecutive-frame timers); `external/python-OBD/NOTES.md` (1 s after ATZ).
- **Problem:** P2, P1, and P3 (multi-frame `19 04` snapshots are the long ones).
- **Risk:** read-only. Longer waits mean longer sessions, not more traffic. If the STN returns to its prompt after the first reply (as the current comment assumes), the second read has to be a read without a new request; check on the bench whether the adapter holds the prompt through 0x78 before writing code.
- **Test:** fake that returns `7F 22 78`, then the answer 1.5 s later; assert exactly one request frame is sent and the answer is returned. On car: one module known to be slow (ECM `19 02`), audit log shows one request, one pending, one final.
- **Effort / priority:** M / High.

## 6. Mode 06: UASID table re-derived from J1979, not copied

- **What:** replace the 4-entry `_UASID_TABLE` (0x01, 0x0A, 0x10, 0x24) with the real unit-and-scaling table, built from the standard. The current code keeps unknown ids raw, which is correct; the goal is to widen coverage without guessing.
- **Method that keeps it evidence-led:** (a) read supported MIDs and the EVAP MIDs 0x39-0x3D on the car with `read_mode06` and log which UASIDs the ECM actually returns; (b) derive only those UASIDs, then the rest, from the SAE J1979 / ISO 15031-5 text (sold by SAE and ISO; no recommendation implied; the J1979 digital annex is the table in spreadsheet form); (c) cross-check each derived row against python-OBD's table by reading both, comparing, and recording agreement or disagreement, never pasting. Signed ids (0x81 and up) are two's complement of the same row; `decode_uasid` already does this.
- **Where:** `cuore/live/mode06.py` (`_UASID_TABLE`, `UNCERTAIN_UASIDS`, `decode_uasid`, `decode_mode06_records`, `evap_summary`, `read_mode06`). The 9-byte record layout there matches what python-OBD parses (OBDMID, TID, UASID, value, min, max), so the layout is not in question; the scaling is.
- **Uses:** `external/python-OBD/NOTES.md` (layout and cross-check role only; GPL-2.0, nothing copied).
- **Problem:** P3 and P4 (EVAP MIDs 0x39-0x3D; manufacturer TIDs >= 0x80 stay raw plus UASID scaling; there is no open table for FCA EVAP TIDs).
- **Risk:** read-only (Mode 06 on the legislated route). Wrong scale would produce a wrong PASS/FAIL, so `passed` must stay computed on raw integers until the row is marked derived, and `evap_summary` should say "scaling unknown" instead of a verdict for unknown rows.
- **Test:** pure unit tests from hand-built 9-byte records with values worked out from the standard text (write the expected numbers from the standard, not from python-OBD); then one on-car `read_mode06(mids=None)` on CAN-C, ignition on, engine off or idle; save the raw replies in the case folder.
- **Effort / priority:** M (S for step (a)) / High for (a), Medium for the full table.

## 7. Cross-check BACCAble's ABS 0x28 against our proven 0x2A

- **What:** BACCAble code (and the older `stelvio_scan` source already in `addressing.py` as "ABS 0x28, self-declared unsourced") puts ABS at 18DA28F1 / 18DAF128. Our own discovery on 2026-10-15 got this car's VIN and matching F192/F194 from 0x2A. Settle it with our evidence: look in the audit log and `store.confirmed_targets` for any earlier reply from 0x28; if none, one read-only `22 F190`, `22 F194` and `3E 00` to 18DA28F1 on CAN-CH, with confirmation, and record the result (answer, NRC, or silence) as a CUORE reading.
- **Where:** `cuore/live/addressing.py` ABS entry (confirmed 0x2A) and the EPS note; `cuore/live/uds.py` `discover(candidates=[0x28])`; the audit log.
- **Uses:** `external/BACCAble/NOTES.md` (lead only; no code copied).
- **Problem:** P5 (and removes a standing contradiction in the registry).
- **Risk:** one read-only frame set on CAN-CH needing confirmation. 0x28 is not in `RESERVED_TARGETS`, so the earlier all-address sweep may already have tested it; check first.
- **Test:** bench with the fake (a silent address and an answering one); on car only after the audit check.
- **Effort / priority:** S / Medium.

## 8. A stateful fake STN adapter for the bench

- **What:** a test stream that models what the real adapter remembers: header (ATSH/ATCP), receive address (ATCRA), flow-control mode and header (ATFCS*), filters (STFAP/STFCP/STFAC), protocol and the STP-restores-defaults behaviour found on 2026-10-13, ATST wait, ATWS banner, late replies, and `7F xx 78` followed by a delayed final frame. udsoncan's `FakeConnection`/`QueueConnection` pattern is the model; Ircama's emulator is explicitly not used (non-commercial, and it does not model STN state).
- **Where:** `cuore/tests/` next to the existing `ScriptedStream` classes (`check_live.py`, `check_dtc_detail.py`, `check_active_probe.py`); consumed by `transport.Session` through the `Stream` interface in `cuore/live/stream.py`.
- **Uses:** `external/python-udsoncan/SOURCE.md` (connection classes referenced, not copied); `external/ELM327-emulator-Ircama/NOTES.md` (what not to rely on).
- **Problem:** P1 and P2 (cannot be reproduced without state), and the only way to test items 2, 3, 4, 5 before the car.
- **Risk:** none (tests only). The danger is a fake that agrees with our assumptions; every modelled behaviour must carry the source: bench finding, datasheet, or "assumed".
- **Test:** the fake is validated by replaying a recorded real session from the audit log, not by itself.
- **Effort / priority:** M / High (enables 2, 3, 4, 5).

## 9. P5: use the keep-alive id low bytes as ordered candidates, and the DBC's camera sender

- **What:** put the low bytes of the keep-alive ids already recorded in `buses.py` at the front of the 29-bit CAN-CH sweep, ahead of the blind 0x00-0xFF order: CAN-CH 1E36xxxx low bytes 0x1E, 0x18, 0x1A, 0x02, 0x06, 0x1D and 1E34xxxx 0x00, 0x06; CAN-IHS 1E34xxxx 0x00, 0x03, 0x0A, 0x24, 0x30, 0x33, 0x34, 0x45, 0x67. opendbc lists `0x1E36001E` as sent by the camera, so 0x1E is the first candidate for HALF (lane-feedback camera). The existing CAN-IHS sweep already tried several of these low bytes with `22 F190` and got no reply (note in `buses.py`), so use `3E 00` and `22 F194` as the second and third probe (item 4's reasoning applies: a module without F190 is invisible to an F190-only sweep).
- **Where:** `cuore/live/addressing.py` `sweep_candidates` (it only front-loads INFERRED/UNVERIFIED registry targets today), `cuore/live/buses.py` `nm_ids_seen`, `cuore/live/uds.py` `discover`.
- **Uses:** `external/opendbc/fca_giorgio.dbc` (CAM_UNKNOWN_6 sender); the hypothesis itself is already in `buses.py` (AUTOSAR NM style), not an external fact.
- **Problem:** P5.
- **Risk:** same as the existing discovery (CAN-CH: confirmation, read-only, `RESERVED_TARGETS` respected: 0xF1, 0x33, 0xBA). A handful of targets, not 256. CAN-IHS needs the blue A5 cable and route `33` for listen only; 29-bit UDS stays on route `34` at 125k.
- **Test:** bench for ordering; on car one confirmed sweep of about 15 targets, three probes each.
- **Effort / priority:** S / Medium.

## 10. P4 (ESIM / EVAP): what external material can and cannot do

- **What:** nothing external covers ESIM or FCA EVAP monitor internals (both reviews searched; only generic background and paid-access data were found). The usable path is our own: read EVAP MIDs 0x39-0x3D (item 6), read `19 04`/`19 06` records for the EVAP DTCs and keep them raw where the layout is unknown (`dtc_detail` already refuses to guess), and capture before/after each smoke test. No import is possible; this item exists so nobody waits on one.
- **Where:** `cuore/live/mode06.py` `evap_summary`, `cuore/live/dtc_detail.py` (`_ECM_SNAPSHOT`, `decode_snapshot_record`, `decode_extended_data`), `cuore/live/channels.py` `esim_status` placeholder (stays unpollable: ESIM is a `0x31` routine and `0x31` is refused).
- **Uses:** none (`external/python-OBD/NOTES.md` only for the EVAP MID list, which `mode06.py` already has).
- **Problem:** P4, P3.
- **Risk:** read-only. Do not add a RoutineControl path for ESIM.
- **Test:** scripted `19 04` reply from a recorded record; on car as part of the regular EVAP case, not a separate job.
- **Effort / priority:** S / Low (no code to write beyond item 6).

---

## Recommended order (first three)

1. **Item 3 (P1 restore sequence, with item 8's fake as its test).** It is the cheapest experiment that can unblock the legislated route after UDS, it is adapter-state only, and the ATFCSM1 leftover is a concrete finding from reading the code. One CAN-C A/B, one variant per session, audit log on.
2. **Item 5 (stop resending on 0x78, P2/P2* alignment), reading item 2's `stale_input` audit records first.** If the first on-car runs show stale replies, item 2 is the answer to P2; if they do not, the resend-on-0x78 loop is the next suspect. Either way the same on-car sequence tells us.
3. **Item 4's safety fix (exclude 0x73E, 0x749 and every heard broadcast id from the 11-bit sweep; skip the three minus-280 collision requests), then item 6 step (a) (read the EVAP MIDs and log which UASIDs come back).** The first is a few lines and removes a transmit-under-a-broadcast-id risk before anyone runs the sweep; the second is read-only and starts the EVAP evidence for P3/P4.

Item 1's on-car validation is passive and can ride along with any of the above, and it is the lowest-risk way to produce CUORE's own readings for P6.
