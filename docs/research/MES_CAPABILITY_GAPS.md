# What MultiEcuScan Cannot Do on the Giorgio Stelvio — Gap Analysis

**Captured:** 2026-08-27. Method: vendor capability matrix, read-only inspection of the local MES 5.4.0.0 install, its complete UI string table `Lang\English.txt` (534 entries — the authoritative feature inventory, since the exe is packed and the ECU DB encrypted), and 79 FES logs / 9 SCAN reports from VIN ZASFAKPN5J7B88115.

---

## ⚠️ A correction to an earlier brief in this project

**MES *does* have live graphing, min/max and timestamped CSV.** An earlier note in this repo said it did not; that was true only of the `.txt` session log.

String IDs 5001-5041 are a full graph subsystem: `Graph`, `Min`, `Max`, `Graphs` (up to 4, 10 parameters each), `Rate` (*"sampling rate of the parameter values"*), `Scale`, `Tags`, CSV `Start`/`Stop`/`Export`/`Import`, and an X-axis selector that plots against Δt **or against any other parameter** (5041 — i.e. X-Y plots against RPM). `Monitor DTCs` (4010) writes DTCs into the CSV during recording.

**So this is a workflow gap, not a capability gap.** The CSV path exists and has never been used here.

---

## The headline

> **MES implements no generic OBD-II mode at all.**

Its entire UI is seven tabs — `Info`, `Errors`, `Parameters`, `Graph`, `Actuators`, `Adjustments`, `Log` — mapping exactly onto the `INFO|DTC|DTC EX|PRM|ACT|ADJ` capability flags. The strings `Readiness`, `Monitor` (other than "Monitor DTCs"), `EOBD`, `OBD-II`, `Permanent` and `Freeze` appear **zero times** in the 534-entry table. The single occurrence of "Generic OBD" (1061) names an *interface type*, not a mode.

**Consequence:** MES cannot tell you whether a monitor has run, cannot show a measured on-board test result, and cannot show a permanent code. For an EVAP job that is the difference between confirming a repair and hoping.

---

## Gap table

| # | Capability | MES on Giorgio | Remedy class | Safety |
|---|---|---|---|---|
| 1 | Readiness monitors (Mode 01 PID 01/41) | **ABSENT** `CONFIRMED` | **(b)** — now built | read-only |
| 2 | Mode $06 on-board test results | **ABSENT** `CONFIRMED` | **(b)** | read-only |
| 3 | Permanent DTCs (Mode $0A) | **ABSENT** `CONFIRMED` | **(d)** — already built | read-only |
| 4 | Graph / log / min-max | **mostly PRESENT**; no trigger | **(d)** | read-only |
| 5 | Guided diagnostics, wiring, pinouts | **ABSENT** `CONFIRMED` | (a)/(d) | read-only |
| 6 | Bi-directional beyond the fixed list | fixed list only `CONFIRMED` | (b)/(c) | **WRITES** |
| 7 | VIN-keyed service history | **ABSENT** `CONFIRMED` | **(d)** | read-only |
| 8 | Battery / charging / IBS registration | partial `CONFIRMED` | (a)/(d) | mixed |
| 9 | ADAS calibration (DASM, HALF) | **IMPOSSIBLE** `CONFIRMED` | **(a)** | **WRITES** |
| 10 | Key / immobiliser on Giorgio | `UNCERTAIN` | (a) | **WRITES** |
| 11 | Module flashing | **ABSENT** `CONFIRMED` | (a)/(c) | **WRITES** |

*(a) impossible without dealer tools · (b) ELM327/STN + open protocols · (c) J2534 passthru · (d) software over existing output*

---

## 1. Readiness monitors — **the sharpest operational failure**

MES will happily show "No fault codes" on a car whose EVAP monitor **has never executed since the last clear**. It offers no way to tell the difference.

**Closed.** `read_readiness()` in `obd2-mcp` decodes Mode 01 PID 01 (since clear) and PID 41 (this drive cycle), reports per-monitor supported/complete status, and returns an explicit EVAP verdict. It also pulls the two companion counters — warmups and distance since clear — which are the context that makes readiness interpretable.

## 2. Mode $06 on-board monitoring test results — the highest-value remaining read

`CONFIRMED` absent from MES.

TSB 18-089-19 says a road test cannot confirm an EVAP small-leak repair and only wiTECH SLVT can. Mode $06 does not replace SLVT, but it is **the only non-dealer route to the actual measured leak value and the ECM's own pass/fail threshold** rather than a binary code. It turns *"no code yet"* into *"test ran, measured X against limit Y."*

Reachable today through `send_raw`. A proper tool would iterate MIDs and apply ISO 15031-5 UAS scaling. `LIKELY` the IAW 10JA exposes EVAP MIDs; `UNCERTAIN` which ones — a ten-minute check on the car, not a research question.

## 3. Permanent DTCs — already solved

`read_permanent_dtcs()` already exists in `obd2-mcp`. A `P0456` that persists in `$0A` after a clear proves to an inspector the repair is unverified; its **disappearance** is the cheapest available proof the monitor ran and passed.

## 4. ⚠️ DTC EX values need a sanity check — but read this carefully

The gap analysis flagged this sample as evidence that MES's extended DTC data can render unset fields as data:

```
  ERROR DETAILS:
  Operating time: 24959 min
  Battery voltage: 4.750 V
  Vehicle speed: 3240 km/h
```

**Caution on that conclusion.** `Vehicle speed: 3240 km/h` is one of the documented **simulation-mode fingerprints** recorded in `CORPUS_BASELINE.md`, alongside `VIN code: 5188214` and `ECU ISO code: 7C 86 4F FF FF`. That block is far more likely to be MES *simulation* data than real DTC EX output.

**So treat "DTC EX is unreliable" as unproven.** Sanity-check values regardless — good practice on any tool — but do not discard genuine extended data on the strength of a sample that appears to come from a fake session.

Generic Mode 02 freeze frame (`read_freeze_frame`, already implemented) is an independent cross-check.

## 6. Bi-directional control — what this car actually accepts

From **real, non-simulated** logs only (25 of 79):

```
10  Clutch self-calibration enable     2  Wastegate solenoid valve
 6  Evaporation control valve          2  Turbo vacuum valve
 3  Electronic thermostat              1  Replacement of turbocharger
 1  EGR solenoid valve                 1  Overboost counter reset
 1  Fan 1st speed (FAILED)             1  NEXT SERVICE KM RESET
```

Bi-directional control demonstrably works here. The one failure was a precondition refusal (UDS `0x22 conditionsNotCorrect`), not a gateway block.

Arbitrary UDS `0x31`/`0x2F` over `send_raw` is technically reachable and is **the most dangerous item in this document** — `0x2E`/`0x34`/`0x36`/`0x37` can brick a module, and blind routine IDs on a safety ECU are not worth guessing at. **Ranked low despite being feasible.**

## 7. VIN-keyed service history — best value-to-effort ratio

MES writes flat files into its own install directory with **no VIN in the filename**, and the filename timestamp is the file *close* time, not the session time. No cross-visit record exists.

Yet every SCAN report carries the VIN on every module block, and `mes-log-mcp` already parses it. Indexing by VIN + true session time yields trend queries MES structurally cannot answer: did `U0100` on the transfer case recur, is `B1176` intermittent, what was the odometer at each visit. **The raw material is already on disk and already parsed.**

## 8. Battery and charging

**Has:** `IBS Battery charge status` as a live parameter (observed 40/47/62/63/64/100 % across logs), `Battery voltage`, and the ECM routine `Replacement of intelligent alternator (IAM)`.

⚠️ **Caveat:** the log showing that routine `COMPLETED` is a **simulation** log. Per simulation semantics that confirms the routine is *offered* for this ECM — it is **not** evidence it has ever run on this car.

**Lacks:** any battery-*replacement* registration routine, state-of-health test, load test, or ripple analysis. No scan tool of any brand does the latter three — they need a conductance tester, not an OBD port.

`LIKELY` that on Giorgio no explicit registration transaction exists in the VAG/BMW sense; PROXI byte 63 holds battery *type* and the IBS learns state adaptively after a reset.

**Worth doing:** high-rate voltage logging. Per the platform research, a ground-strap or battery fault shows as **sag or noise that a handheld meter averages away**. MES's few-Hz parameter loop is the wrong instrument; PID 42 or the ~100 Hz signal on `0x0F1` from the Giorgio DBC is the right one.

## 9. ADAS calibration — the cleanest negative here

From the vendor capability matrix for the Stelvio 2.0T:

- **HALF forward camera (Bosch MFK2)** — `INFO|DTC|DTC EX|PRM` on `ELMA6`. **No ACT. No ADJ.**
- **DASM radar** — `INFO|DTC|DTC EX|PRM|ACT` on `ELM`. **No ADJ.**
- **Airbag** — `INFO|DTC|DTC EX|PRM`. **No ACT, no ADJ** either — so no crash-data reset and no squib tests, on top of needing the A6 cable to see it at all.

Calibration is an `ADJ`-class routine. Neither ADAS module exposes one. **No cable, adapter or software wrapper changes this** — the routine does not exist in the product.

**After windscreen or front-bumper work this needs wiTECH plus FCA static targets, or a dedicated ADAS platform** (Autel IA900/MA600, Hunter, Bosch, Texa) with correct Alfa target boards, a level floor and measured setback. There is no cheap path. **Realistic advice: subcontract it or decline the job — an uncalibrated forward camera is a liability, not an inconvenience.**

## 10. Key programming — resolve it in five minutes, don't research it

MES clearly has key machinery in its string table: security-code entry, the BCM's 30-minute lockout after 3 failed attempts, transponder learning, RF remote learning, and **FOBIK** learning (6085-6093), with destructive warnings like *"ALL KEYS MUST BE LEARNED! The keys not inserted... will be disabled and unusable anymore"*.

**But the string table is a global vocabulary shared across 532 vehicles** — its presence proves nothing about the Giorgio BCM 949, and no key routine appears in any of this car's 79 logs.

> **Verification is free:** connect to `Body Computer Marelli (949)` and `RFHUB Continental` in **simulation mode (CTRL+F10)** and read the offered adjustment list. That is the authoritative per-ECU enumerator.

## 11. Module flashing — don't build toward this

`Flash` = zero hits. The only programming MES does is **PROXI/EOL configuration** — writing configuration bytes, not firmware. MES supports neither J2534 nor DoIP.

This matters because several Giorgio "faults" are software fixes (recalls 18V636000, 19V551000; TSB 18-023-23 REV. B on P1CEA). The **Drew Technologies Mongoose-Plus Chrysler2 J2534 driver is already installed on this machine** — but a passthru is a *transport*, not an authorisation. FCA reflashing needs a wiTECH 2.0 subscription (~$2,800 first year, ~$1,600/yr renewal) plus AutoAuth for SGW cars, and the calibration files are not distributable.

**Commercially the right answer: recall work is free at the dealer.**

---

## Ranked bolt-ons

Everything in the top five is **read-only**.

| # | Opportunity | Value | Feasibility | Safety |
|---|---|---|---|---|
| **1** | **Readiness monitors + Mode $0A** — "is the repair verified?" | Very high | **Done** | read-only |
| **2** | **VIN-keyed history over existing logs** | Very high | Trivial — data on disk, parser exists | read-only |
| **3** | **Mode $06 EVAP test values and thresholds** | Very high | Easy; availability `UNCERTAIN` until tested | read-only |
| **4** | **CSV pipeline + post-hoc trigger analysis** | High | **Software done** (`csvlog.py` + 5 tools, 2026-08-31); awaiting first real recording — see `docs/format/CSV_LOG_FORMAT.md` | read-only |
| **5** | **Local knowledge base** (pinouts, TSBs, known-good) | High | Moderate, ongoing | read-only |
| **6** | **Buy the A5 (blue) and A6 (grey) cables** | Very high | Trivial — a purchase | enables writes |
| 7 | High-rate voltage logging for ground-strap work | Medium-high | Easy | read-only |
| 8 | Confirm key learning via simulation mode | Medium | Trivial (5 min) | read-only to check |
| 9 | Arbitrary UDS bi-directional control | Medium | Easy but **hazardous** | **WRITES** |
| 10 | ADAS calibration | High when needed | Not viable in-house | **WRITES** |
| 11 | Module flashing | Low (free at dealer) | Not worth it | **WRITES** |

> **Item 6 deserves emphasis even though it is hardware:** the A5 and A6 cables take addressable modules from **~10 to 29**, including ABS, airbag, electric steering, HALF camera and torque vectoring. No software substitutes for it, and it is the cheapest large capability increase available.
> ⚠️ **Verify any cable does NOT short pins 1 and 9** — the vendor warns explicitly that this drops the bus on Giulia/Stelvio.

---

## The blunt summary

MES on Giorgio is a competent **manufacturer-protocol** scanner with a real graphing engine and working bi-directional control on the powertrain. What it is not, at all, is an **OBD-II** tool.

Everything in that first category is recoverable for near-zero cost with the ELM327 already on hand. Everything in the second — ADAS calibration, flashing, and probably keys — is not recoverable at any price short of wiTECH, and pretending otherwise is how people damage cars.
