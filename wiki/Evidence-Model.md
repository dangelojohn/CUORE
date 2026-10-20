# Evidence Model

CUORE's central rule is **data-only diagnosis**: a conclusion cites readings that were captured from the car. Everything else is kept, labelled, and used to suggest what to check, never shown as proof. This page explains what counts, how the readings are decoded, and where the project is careful about what a reading does and does not say.

## Observations: the evidence record

Each live read is appended to `observations.jsonl` as one object:

```
{ "at": ISO time, "kind": ..., "vin": ..., "bus": ..., "cable": ...,
  "stream": ..., "data": { ... } }
```

`stream` names what produced the read. `is_from_car()` is true only for a real serial link (or a recording of one). Reads from a test stream or a replay are stored but are never evidence about a car.

Kinds written by the live layer: `adapter_identity`, `obd_dtcs` (stored, pending, permanent), `readiness`, `mode06`, `pid`, `pids_snapshot`, `freeze_frame`, `freeze_frame_set`, `module_identity`, `module_dtcs`, `did`, `did_discovery`, `read_all`, `dtc_detail`, `scan`, `scan_coverage`, `evap_bundle`, `clear_evidence`, `live_alarm`, `capability`, `bus_capture` and `slvt_replica`. The Scans area groups consecutive from-car observations within 15 minutes of each other into one scan; it only groups on read and writes nothing.

## Attested input versus measurements

Symptoms, notes, feedback, photos, mechanic-typed values, dealer-tool results entered by hand and Tell CUORE events are **attested records** with date and author. They are shown next to the facts they concern but are never passed to the evidence gate as measurements. Outside material (service bulletins, forum and video links) is kept and labelled as such.

## The evidence gate

`mes/verdict.py` reads the observation log through `mes/live_obs.py` (page `/v/{vin}/gate`, MCP tool `diagnosis_verdict`). It returns **CONFIRMED** only when all four hold:

1. the fault is **demonstrated** (chronic, returned after a clear, or standing now);
2. a causal **mechanism** is stated;
3. a verified **measurement implicates** the component;
4. a test that **could have cleared** the component was run (disconfirmation attempted).

A trouble code is not a measurement. The overall verdict states are computed, never hand-written: ACTIVE FAULTS, UNVERIFIED REPAIR, VERIFIED CLEAN, NO DATA; per code ACTIVE, CLEARED UNVERIFIED, STALE. A clear without proof leaves "unverified repair" until a readiness read from the car shows the monitor complete and no code back.

## Claim tags and confidence grades

Working documents tag every claim:

- **[E]** evidence: a stored read, a log line or a recorded job entry, with its source named.
- **[I]** inference: reasoning from [E] items; may be wrong.
- **[N]** not known or not in the repository; do not treat it as known.

Reference tables use grades: `CONFIRMED` (manufacturer document), `CORROBORATED` (two independent sources), `SINGLE-SOURCE`, `UNKNOWN` ("use the service manual"; stored as none, never estimated). Module addresses use `CONFIRMED`, `INFERRED`, `UNVERIFIED`.

## UDS DTC status bits

A UDS status byte (ISO 14229-1) is stored and decoded per code:

| Bit | Mask | Meaning |
|---|---|---|
| b0 | `0x01` | test failed |
| b1 | `0x02` | failed this operation cycle |
| b2 | `0x04` | pending |
| b3 | `0x08` | confirmed |
| b4 | `0x10` | test not completed since last clear |
| b5 | `0x20` | failed since last clear |
| b6 | `0x40` | test not completed this operation cycle |
| b7 | `0x80` | warning indicator (lamp) requested |

`cuore/live/repair.py` turns the byte into a per-code repair state: failing, failed since clear, not run since clear, passed since clear, or likely passed (the code is absent from a reply the module did give). The overall verdict says "not repaired", "not yet known" or "tests passed", and states that silence after a clear proves little because every test must run again.

**Caveats found on the reference car's engine computer** (all from stored reads):

- Its availability mask is `0xCF`, so b4 and b5 are not implemented. Across 745 stored status values only `0x40`, `0x4D` and `0xCD` ever occurred.
- Therefore the rule "b4 clear and failure bits clear means the test ran and passed" cannot be used here: `0x40` means only "not completed this operation cycle", which says nothing about earlier cycles.
- `0x4D` = b0 + b2 + b3 + b6: failed, pending, confirmed, not completed this cycle, with the failure carried over from an earlier cycle. `0xCD` = the same plus b7: lamp requested.
- A code that drops out of a full `19 02 FF` list went `0x40` to `0x00`: its test completed this cycle with no failure. That is an inference, and the list length swings widely between reads (72 to 278 codes).

## Freeze-frame decoding

A freeze frame is read with UDS `19 04` (snapshot) and `19 06` (extended data). `cuore/live/dtc_detail.py` decodes the engine computer's snapshot, which is 132 bytes starting at data identifier `0x1008`, and the body computer's 38 bytes. Fields decoded:

| Field | Note |
|---|---|
| Startups counter, operating minutes | rise from frame to frame, so each frame is a separate event |
| Odometer (km) | cross-checked against a live odometer data identifier and the "distance since clear" counter |
| Fuel level (%), engine speed, vehicle speed, gear | |
| Coolant temperature, battery voltage, MAP, spark advance | |

Each decoded identifier carries a **confidence** and a **basis**. "High" means anchored to numbers MultiEcuScan itself printed for a freeze frame; "medium" means physically consistent across the records plus a source; "low" means the identity or scale is plausible only; "unknown" is returned as raw bytes with no name. The decoder never guesses a length: where it cannot tell, it stops and returns the remainder as raw bytes. The snapshot identifier lengths for the engine and body computers were derived empirically, because the standard leaves lengths to the tester's database.

| Module | Identifier | Field | Confidence |
|---|---|---|---|
| Engine | `1008` | Operating time (minutes) | high |
| Engine | `200A` | Startups counter | high |
| Engine | `1000`, `1002`, `192D` | Engine speed, vehicle speed, engaged gear | medium |
| Engine | `2001` | Odometer (0.1 km units) | medium |
| Engine | `1003`, `1935`, `1302` | Coolant, intake-air, oil temperature | medium |
| Engine | `1004`, `1937`, `1001`, `19BD` | Battery voltage, manifold pressure, fuel level, battery state of charge | medium |
| Engine | `1812`, `182F`, `195A`, `1956`, `198C` | Spark advance, air flow, boost and atmospheric pressure (an interchangeable pair), UniAir mode | low |
| Engine | `1921`, `1B0D` and a number of others | flag blocks and unknowns | raw, unnamed |
| Body | `1008` (operating time), `200A` (startups) | counters | medium, high |
| Body | `1002`, `1004`, `3700`, `1921` | identifiers present, meaning not established | raw, unnamed |

The body computer's own supply identifier `1004` in the live read reads 14.4 to 14.5 V on 10-14 and 10-19 (formula unverified), which is how module voltages were compared with the port voltage ([[Network and Brake Findings|Network-and-Brake-Findings]]). A verification pass re-decoded the raw bytes by hand and confirmed the scalings, with two limits: scaling confidence is rated **medium**, and fields such as purge duty, ambient temperature, barometric pressure and time since start were not established as present in the raw bytes. The raw bytes are stored verbatim under each observation so a better decoder can re-read them later. Extended-data byte `0x60` is labelled "occurrence counter" in the decoder, but it reads the same on every code and looks constant; the label is unverified.

## Mode 06 (on-board test results)

Mode 06 returns, per monitor, the engine computer's own measured result and its pass/fail limits. CUORE decodes J1979 CAN records (`cuore/live/mode06.py`):

```
OBDMID | TID | UASID | value (2 bytes) | minimum (2) | maximum (2)
```

- **UASID 0x10** means time in **milliseconds**, 1 ms per count, unsigned 16-bit. The unit rests on the project's own table and a manufacturer reference summarised by a search result; the authoritative SAE table is paywalled and was not read.
- The mapping of a test to a code is by SAE convention and CUORE's labels (`3C` = 0.020 in leak, `3B` = 0.040 in, `3A` = 0.090 in, `39` = gross leak, `3D` = purge flow). What a given test ID measures on this manufacturer's computer is **unpublished and unknown**.
- A value of 0 inside limits 0 to 0 prints "pass" but is not a result. A record with value 0 and limits 0/0 is **byte-identical** whether the monitor ran or not; it carries no information.
- After a code clear, Mode 06 resets: some limits are wiped, and one value equals its maximum (6000). That "pass" is a reset artefact, not a result.
- A `NO DATA` reply is not "not supported". The tool once reported "not supported by this ECU" when the legislated route had simply returned nothing. Such cases are now classed `silent`: a tool fault, not a car statement.
- An older display printed the maximum limit for every test (a 404 ms value shown "against 65535 ms") and was misleading; job entries quote the correct minimum.

## The code findings layer

Beside the raw reads, CUORE keeps a **per-code findings store** (`mes/code_findings.py`) for the non-EVAP codes reviewed on 2026-10-20. Each entry is keyed by the full code (`C104B-92`) and holds the meaning and where it comes from; the **readings** from this car; any **owner statement** (attested, not read); a **classification** (real, service-induced, probable artefact, possible bystander, core of or downstream of the network cluster, readiness flag only); the implications; a **resolution ladder** (cheapest, read-only first, never a clear); the **proof of fix**; and the **outside literature**, each item with its link. The three evidence classes are labelled and shown apart on every code page, and a code with no sourced finding shows nothing. A lookup by base code (`C104B`) returns every failure-type variant. An owner statement can change the classification (the brake code is "service-induced, not yet confirmed") but never counts as a reading. The review itself is on [[Code Reviews|Code-Reviews]]. Code texts for 22 more codes were added to the description table, and U1713's text was corrected from "lost communication" to "signal erratic" (failure type 2F).

## What readings can and cannot prove

The reference case wrote a readings-only ledger that makes the point clearly: eleven code clears, three codes failing, two leak tests failing, and still **no reading that fails a part**. Status bytes give the computer's verdict, not the input that produced it; a part is condemned only by a stimulus-and-response pair that shows it failing. See [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]].

Related: [[Safety Rules|Safety-Rules]], [[Guided Full Scan|Guided-Full-Scan]], [[MES Integration|MES-Integration]].
