# Learning wiTECH's DIDs by passive listening

Written 2026-09-26. Covers `cuore/live/learn.py` (reassembly, pairing,
correlation) and `cuore/live/learned.py` (persistence of accepted mappings).
Companion to `docs/reference/GIORGIO_MODULE_MAP.md` (addressing) and the
`cuore/live/` capture/UDS stack (`capture.py`, `framing.py`, `uds.py`).

## Why this exists

`addressing.py`'s `DIDS` table only has the handful of DIDs `danardi78` and
other sources already published, mostly for the ECM and TCM. wiTECH's own
live "data display" reads many more — module-specific, undocumented
identifiers the dealer tool knows and this project does not. wiTECH will not
tell a passive listener what a DID *means*; it only sends the raw UDS
requests and the modules answer with raw bytes. The technician watching the
wiTECH screen is the only source of meaning. This workflow pairs the two: the
byte-level traffic cuore captures, and the human-readable values the
technician saw at specific moments.

## The workflow

1. **Splitter cable.** Put an OBD-II splitter on the DLC so wiTECH's cable and
   cuore's adapter are both listening at once. cuore does not need its own
   port on the car — it needs to see the same bus wiTECH is already driving.
2. **Start a cuore capture** for the length of the wiTECH session (`cuore/live/
   capture.py` `listen()` via `ops.capture(bus=..., seconds=..., filters=...)`).
   Use a filter on `18DAxxxx` if the capture would otherwise be dominated by
   unrelated broadcast traffic — anything narrower risks dropping wiTECH's
   own requests, so when unsure, capture unfiltered and let `learn.py` sort
   it out afterward.
3. **Open wiTECH's data display** and watch whatever parameter you care
   about (a switch, a percentage, a state). Note the **wall-clock or
   capture-relative time** and the value shown, every time it changes:
   `{"t": 12.4, "label": "EVAP pressure switch", "value": "Closed"}`,
   `{"t": 31.0, "label": "EVAP pressure switch", "value": "Open"}`. A numeric
   gauge works the same way: `{"t": 45.0, "label": "Fuel level", "value": 42.5}`.
   More marks, and marks spanning more distinct values, make the next step
   more reliable — two Closed/Open flips is a bare minimum; several is
   better, and for a numeric gauge at least three well-separated readings are
   needed for the linear fit to mean anything.
4. **Run the pipeline** against the capture and the marks:
   - `learn.isotp_reassemble(frames)` → ISO-TP messages per CAN ID.
   - `learn.uds_transactions(frames)` → request/response pairs, DIDs decoded
     for `0x22`/`0x2E`.
   - `learn.did_series(transactions)` → per-`(target, did)` time series of
     response payloads.
   - `learn.correlate(series, marks)` → ranked `(target, did, field)`
     candidates with evidence.
5. **Review the ranked candidates.** The evidence list shows exactly which
   raw byte(s) were read back at each mark's time and what the technician
   said the screen showed then — enough to judge by eye whether a score-1.0
   candidate is the real field or a coincidence (a byte that happens to
   change at the same rate as something unrelated, e.g. once per ignition
   cycle).
6. **Accept or reject.** `learned.accept(vin, module_code, did, name, field,
   scale=None, offset=None, unit=None, evidence=...)` persists a mapping;
   `learned.reject(vin, module_code, did, field, reason=...)` records that a
   candidate was looked at and turned down, so it is not re-litigated on the
   next capture. `learned.learned(vin=None)` reads them back. Every entry is
   stamped `"confidence": "learned from wiTECH capture"` — a distinct,
   weaker provenance than the `CONFIRMED`/`INFERRED`/`UNVERIFIED` scale
   `addressing.py` uses for sourced DIDs, and it is never silently upgraded.

## API summary

```
learn.isotp_reassemble(frames) -> {"messages": [{"t","id","data"}], "dropped": int}
learn.uds_transactions(frames) -> [{"t_req","t_resp","target","tester","service",
                                     "request","response","nrc","did","data",
                                     "dids","multi_did_raw"}]
learn.did_series(transactions) -> {(target, did): [{"t","bytes"}]}
learn.correlate(series, marks)  -> [{"target","did","label","kind","field",
                                      "score", ("scale","offset","r2" if numeric),
                                      "evidence"}]  # sorted best first

learned.accept(vin, module_code, did, name, field, scale=None, offset=None,
               unit=None, evidence=None) -> entry
learned.reject(vin, module_code, did, field=None, reason="") -> entry
learned.learned(vin=None) -> {vin: [entries]} or the whole store
```

`target`/`tester` are hex byte strings (`"10"`, `"F1"` — never assumed to be
`F1`: the tester byte is read back out of whichever `18DA<TA><SA>` /
`18DA<SA><TA>` pair actually appears, so wiTECH using a different tester
address works the same way). `field` is `{"offset": N, "bit": B}` for a
single bit, `{"offset": N, "width": "byte"}` for a whole byte, or
`{"offset": N, "width": "u16"}` for a big-endian 16-bit field.

## Safety basis

- The capture is **receive-only**: `capture.listen()` opens the session
  `passive=True`, which sets `STCMM 0` on the STN adapter — no CAN
  acknowledgement, nothing transmitted. The car cannot tell cuore is
  connected at all, and it cannot be affected by this workflow. This is the
  same posture `docs/design/CUORE_LIVE_LINK_PLAN.md` establishes for every
  other capture use.
- **Do not run cuore requests while wiTECH is connected.** This workflow is
  listen-only by design specifically so it never needs to. If a targeted
  cuore read is wanted afterward (to confirm a learned mapping outside a
  wiTECH session), disconnect wiTECH first — two testers issuing UDS
  requests to the same module at once is a wiTECH problem to avoid, not a
  cuore one to manage.
- **Confirm STCMM 0 before trusting the capture as passive.** `capture.py`
  sets it on every `listen()` call for STN adapters; if a non-STN adapter or
  a manually-configured session is used instead, verify the equivalent
  monitor mode is active before treating the session as safe to run
  alongside wiTECH.

## Limits

- **Bus load.** A CAN-C bus with wiTECH's data display running and normal
  vehicle traffic can produce more frames per second than the adapter's
  serial link to the host can drain in real time (`capture.py`'s own read
  loop deadline; see `STFAC`/`STFPA` filter handling for how it copes).
  Heavy display refresh rates (fast-updating gauges, multiple parameters at
  once) can starve the serial buffer before `max_frames`/`seconds` are hit;
  a `"BUFFER FULL"` or dropped-frame condition in the capture result means
  the reassembly saw less than wiTECH actually sent, not that wiTECH sent
  less.
- **Capture buffer.** `capture.listen(seconds=..., max_frames=...)` bounds
  both wall time and frame count; a wiTECH session longer than the capture
  window, or with more distinct parameters than `max_frames` can hold, needs
  multiple back-to-back captures stitched together by timestamp, or a
  narrower `18DAxxxx` filter.
- **Incomplete ISO-TP messages are dropped, not guessed at.**
  `isotp_reassemble` counts and discards any first-frame that never gets its
  consecutive frames (capture ended mid-transfer, or a frame was lost to
  buffer overrun) rather than returning a truncated payload as if it were
  complete — a truncated multi-frame DID reply would otherwise look like a
  shorter, different value.
- **Multi-DID `0x22` requests are not always splittable.** When a single
  `0x22` request bundles several DIDs, the response concatenates each DID's
  echo with its data, but nothing in the UDS frame says how long each DID's
  data field is. `_split_multi_did` finds every way of cutting the response
  so each DID lands where expected; if more than one cut works (or none
  does), the ambiguity is real and the transaction is kept as a raw,
  unsplit response (`multi_did_raw: true`) rather than guessed.
- **Correlation is only as good as the marks.** Two marks per label is the
  floor for a binary state and can still produce a false positive by
  coincidence (a byte that happens to change once between two widely-spaced
  timestamps for an unrelated reason); more marks, spanning more distinct
  values and more time, sharpen the ranking. A numeric fit needs at least
  three well-separated readings to mean anything as an R² — two points
  always fit a line perfectly.
- **11-bit vs 29-bit.** This whole pipeline assumes 29-bit physical
  addressing (`18DA<TA><SA>`), which is what this car's UDS uses
  (`addressing.py`). A capture that also contains 11-bit legislated OBD
  traffic (`7DF`/`7E8`-style headers) will simply not match `uds_transactions`'s
  `18DA` pattern and is silently excluded — it is not reassembled as UDS,
  and it is not an error.
