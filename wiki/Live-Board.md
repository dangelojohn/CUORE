# Live Board

The live board and the gauges dashboard show readings as they arrive from the car. They are the "what is it doing right now" half of CUORE; the guided scan is the "what is stored" half.

## Live board

`/v/{vin}/liveboard` is a read-only board meant for a **passenger to watch while someone else drives**. Every known channel is grouped by system and shown as a large digital readout. The colour of each readout says how far the value is outside its known-good band. Feed: `liveboard_bridge` and the known-good tables in `mes.known_good`; the bands are also available at `/api/live/known-good`.

Known-good bands follow strict rules:

- Only **one-sided** limits (too hot, too low) become warning and alarm colours. Idle-only or two-sided ranges are shown as notes, not as alarms.
- A value with no sourced band stays **unknown and blank**. Nothing is estimated to fill a gap. There are 28 channels with a band entry, and many of the bands are still marked unknown.
- Each band carries a source and a confidence grade (CONFIRMED manufacturer document, CORROBORATED, SINGLE-SOURCE, UNKNOWN).

### Freeze-frame panel

The board includes a freeze-frame panel. A freeze frame can be captured, saved or discarded, and sent to the open job as a snapshot action (`/api/liveboard/{vin}/*`). 
## Gauges dashboard

`/v/{vin}/gauges` (and `/gauges/hud`) is a customisable dashboard. You can arrange gauges into **layouts**, define **custom channels** (a formula over existing channels), set **triggers**, take **snapshots**, and **replay recordings**. Client code is under `cuore/web/static/live/`; storage is `cuore/live/ui_store.py` and `layouts.py`. The live stream is `/api/live/stream`, fed by a poller session started with `/api/live/session/*`.

Recordings keep the CSV format that MultiEcuScan itself uses, so the existing MES log tools read CUORE's recordings unchanged.

## The poller

The poller (`cuore/live/poller.py`) is the one place CUORE holds an adapter session open for a whole run. It:

- opens one session, round-robins its channels and batches **up to six Mode 01 PIDs** per request (the J1979 limit), publishing samples to subscribers;
- sends only reads (OBD Modes 01, 03, 07 and UDS `22`);
- makes every other live adapter operation refuse while it runs, and refuses to start while MES holds the port;
- can end with a serial fault if something else grabs the port; a held session is more exposed to that than many short ones.

An optional baud raise for held sessions exists (`CUORE_ADAPTER_BAUD`), off by default and unverified on the reference adapter.

## What is and is not evidence

- Readings from a real serial link are stored as observations and can enter the evidence gate.
- Replay, demo and test streams are stored and labelled, but are **never** evidence about a car (`is_from_car()` is false for them). The playback stream is how the live checks run in the test suite without hardware.
- A custom or learned channel carries its provenance. A learned data identifier is a candidate until a person accepts it, and it is then recorded as learned, not as catalogue.

## Comparing live with the logs

`/v/{vin}/live-vs-log` compares what the live link read with what MES logs say for the same car, which helps spot a scaling disagreement between the two tools. See [[MES Integration|MES-Integration]].

Related: [[Evidence Model|Evidence-Model]], [[Features]].
