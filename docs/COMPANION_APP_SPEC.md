# CUORE — Companion App Specification

**A phone / tablet / watch companion to the Alfa-Stellantis diagnostic toolchain.**

**Status:** draft 1, 2026-09-01. Written against the toolchain in this repo, the ~3,100
lines of Giorgio/MES research in `docs/`, and the separate `stelvio_scan` suite at
`C:\Users\User\Documents\stelvio_scan`.

---

## 0. The one-paragraph version

MES is a bench tool: Windows-only, no API, exclusive COM port, logs written on close. It
is excellent at manufacturer-protocol work and blind to everything that happens between
visits — while you drive. CUORE is the other half: a browser-delivered app on phone,
tablet and (partially) watch that shows live vehicle data on the move, records every
drive, cross-references what it sees against this car's own 12-month log corpus, and puts
Claude in the passenger seat with all of it in context. It never fights MES for the port,
because when MES is running CUORE is reading logs, not the car.

**Name:** working title `CUORE` (Alfa's *cuore sportivo*; also "core"). Swap freely.

---

## 1. Scope and audience

Three audiences from one codebase, in this order. Each tier is a superset of the one above
and **each is independently shippable**.

| Tier | Who | What it adds | Gate to the next tier |
|---|---|---|---|
| **T1 — Personal** | The two cars in the corpus: Stelvio `ZASFAKPN5J7B88115`, 500L `ZFBCFABH1EZ020882` | Everything in §5–§9. Single user, LAN-only, API key on device | Works reliably on real drives for a month |
| **T2 — Shop** | Customer cars through the bench | Multi-vehicle switching, VIN-keyed customer records, PDF reports, immutable audit log, tech sign-off on the evidence gate | Two techs use it on real jobs without falling back to raw MES |
| **T3 — Product** | Other Giulia/Stelvio owners | Accounts, cloud sync, server-side Claude proxy (no user-held keys), generic-vehicle fallback, native shell, EULA + liability posture | Legal review of bidirectional write features |

**T1 and T2 share every line of code.** T3 changes the trust model — untrusted users, no
shared LAN, keys cannot live on the client — and is the only tier that justifies a native
app and a cloud backend. **Do not build for T3 before T1 is proven on a car.**

---

## 2. What already exists, and what CUORE reuses

Nothing below gets rewritten. The companion app is a **new front-end and a new live data
path over an existing analysis core**.

| Asset | Location | Role in CUORE |
|---|---|---|
| `mes` library — 6.2k LOC, 28 MCP tools | `mes-log-mcp/mes/` | **The brain.** `workup`, `fault_tree`, `diagnosis_verdict`, `dtc_history`, `extract_dtcs`, `actuator_history` become HTTP endpoints unchanged |
| `mes.csvlog` + 5 recording tools | `mes-log-mcp/mes/csvlog.py` | Reads MES CSV exports. CUORE's own drive recordings adopt **the same schema**, so one analyzer serves both |
| `obd2-mcp/server.py` | `obd2-mcp/` | Live OBD-II: DTCs, freeze frame, permanent codes, readiness, PIDs, `send_raw`. Becomes the **bench** transport |
| Flask web-UI | `web-ui/` | The T1 skeleton. CUORE is its successor, not a parallel app |
| `docs/research/*` (8 docs) | `docs/research/` | Ships as the **knowledge pack** Claude reads (§9) |
| `CORPUS_BASELINE.md`, `TSB_CATALOGUE.md`, `ZF8HP_SERVICE_DATA.md` | `docs/reference/` | Known-good ranges, TSB cross-refs, service data |
| `docs/format/*` | `docs/format/` | Parser contracts; the CSV format doc governs CUORE's own logger |
| `stelvio_scan` (PySide6, v0.6) | `~/Documents/stelvio_scan` | **Harvest, don't run.** Take `data/dtc_codes.yaml` (191 codes), `expected_ranges.yaml`, `uds/addresses.py`, the procedure classes. Its UDS layer is unit-tested but never hardware-validated |
| Desktop analyses | `~/Desktop/Claude/*.html` | Ground map, FTA/FMECA, Weibull tracker become **in-app reference pages** rather than loose files |
| `fca_giorgio.dbc` | opendbc, upstream | The Tier-2 telemetry decoder (§6.2) |

---

## 3. The hard constraints this design is shaped by

Established facts from the research, not assumptions. The architecture exists to satisfy them.

1. **One adapter, one master.** Windows opens COM ports exclusively, and ELM327 is a
   stateful half-duplex REPL whose `ATSP`/`ATSH`/`ATCRA`/`ATFC*` settings are device-global.
   Two clients on one adapter is not a sharing problem, it is a **safety** problem — on a
   device that can command actuators, misattributed responses move hardware.
   → *CUORE never opens the adapter MES is using. §4.3 is the interlock.*
2. **Safari has no Web Bluetooth and no raw TCP sockets.** A browser PWA on iOS cannot talk
   to any OBD adapter, BLE or Wi-Fi. → *The server moves to the car, not the client.*
3. **MES writes logs on close, not streaming.** File-watching yields per-operation
   completion events at seconds granularity. CSV export is the only streaming path.
   → *Log ingest is event-driven, but never presented as live.*
4. **A plain ELM327 on pins 6/14 reaches Bus A only** — ECM, ZF 8HP, Q4, BCM, IPC, RFHUB,
   PROXI. ABS, airbag, EPS, camera, radio need the A6 (grey) / A5 (blue) cables.
   → *The app states which bus a module is on and why it is unreachable, rather than
   silently omitting it.*
5. **⚠ Never use a cable that shorts pins 1 and 9 on Giulia/Stelvio** — it drops the bus.
   Many cheap "universal FCA" cables do exactly this. → *Hardware checklist in-app; §12.*
6. **Most of the FES corpus is simulated** (54 of 80). SCAN logs carry no marker at all.
   → *Provenance is a first-class field in every UI surface, never silently mixed.*
7. **Clearing is not fixing.** After a clear the ECU reports nothing until each monitor
   re-runs. → *The readiness / permanent-DTC verdict is the headline, not the DTC list.*

---

## 4. Architecture

### 4.1 The shape

```
        ┌──────────────────────── CLIENTS ────────────────────────┐
        │  iPhone PWA    iPad PWA    Desktop browser   Watch(§8)  │
        │      └──────────────┴─────────────┴──────────┘          │
        └──────────────────── HTTPS + WebSocket ──────────────────┘
                                    │
                    ┌───────────────┴────────────────┐
                    │                                │
        ╔═══════════▼═══════════╗        ╔═══════════▼════════════╗
        ║   BENCH HOST          ║        ║   DRIVE NODE           ║
        ║   (this Windows PC)   ║        ║   (in-car, §4.4)       ║
        ║                       ║        ║                        ║
        ║ • MES log corpus      ║        ║ • Live OBD poller      ║
        ║ • mes library (all    ║        ║ • CAN sniffer (opt)    ║
        ║   28 analyses)        ║        ║ • Drive recorder       ║
        ║ • obd2 bench session  ║        ║ • Ring buffer + GPS    ║
        ║ • MES log watcher     ║        ║ • Serves the same PWA  ║
        ╚═══════════▲═══════════╝        ╚═══════════▲════════════╝
                    │     sync on return to Wi-Fi    │
                    └────────────────────────────────┘
                                    │
                    ╔═══════════════▼════════════════╗
                    ║  Anthropic API (claude-opus-5) ║
                    ║  reached per §9                ║
                    ╚════════════════════════════════╝
```

**One Python application, two deployment profiles.** `cuore serve --profile bench` on the
PC; `cuore serve --profile drive` on the in-car node. Same FastAPI app, same PWA bundle,
different capability set advertised at `/api/capabilities`. The client renders whatever the
host it reached says it can do — that is the whole mechanism for the "both data paths"
requirement, and it means there is never a second codebase to keep in step.

### 4.2 Why the server moves instead of the client

You asked for a PWA *and* live data while driving from a phone-side adapter. On iOS those
are mutually exclusive: no Web Bluetooth, no TCP. Rather than compromise either, **the
thing that owns the adapter becomes portable.** A ~$40 in-car node runs the same server;
the phone joins its Wi-Fi and gets a genuinely live app, in a browser, anywhere.

Consequences, stated plainly:

- ✅ Real live gauges while driving, in Safari, with no App Store.
- ✅ Recording continues with the phone screen off — the node logs, not the browser.
- ✅ Identical code path bench and car; one analyzer for every recording.
- ❌ A small piece of hardware must live in the car and be powered.
- ❌ No true Apple Watch app (§8).

### 4.3 The MES interlock — non-negotiable

The bench profile must never contend for the adapter. Enforced in three layers:

1. **Process check.** Before any adapter open, poll for `Multiecuscan.exe`. If present, the
   live surface is disabled and the UI says *"MES has the port — showing logs only."*
2. **Advisory lock file.** `%PROGRAMDATA%\cuore\adapter.lock` holds pid + port + purpose.
   Both CUORE profiles respect it. (MES does not, hence layer 1.)
3. **Lazy per-operation open.** Open the port for the operation, close immediately. Never
   hold COM3 for the server's lifetime. This is the structural fix identified in
   `CONNECTIVITY_AND_SGW.md` §5 and it makes handoff a non-event.

**Handoff checklist, surfaced in the UI when switching tools:** let the current operation
finish (never interrupt an actuator test — it can leave an ECU with control overridden) →
fully exit MES → wait 1–2 s → wait out the vehicle-side session (S3 ≈ 5 s, or send `10 01`)
→ `ATWS` and re-issue the entire init, never inherit interpreter state → no background
TesterPresent loop while MES is active.

**Also resolve the standing collision:** MES is configured for COM3 and so is `obd2-mcp`.
COM8/9/10 are free. Moving MES needs elevation via its Settings dialog (HKLM ACL).

### 4.4 The drive node

| Option | Cost | Notes |
|---|---|---|
| **Raspberry Pi Zero 2 W** + USB ELM327 + AP mode | ~$25 + adapter | Baseline. Boots to Wi-Fi AP `CUORE`, serves at `http://cuore.local` |
| **Pi 4/5 + MCP2515 or comma panda** | ~$80–150 | Adds Tier-2 CAN sniffing (§6.2). The 100 Hz path |
| **GL.iNet travel router + USB adapter** | ~$40 | Better Wi-Fi, worse compute |
| **Old Android phone as node** | $0 | Termux + Python; brings BLE, GPS and a battery for free. Ugly, viable, and the right way to prove the idea before buying anything |

Requirements regardless of host: powered from a switched 12 V source, or a supercap for
clean shutdown; read-only root or journaled writes (**SD corruption is the failure mode
that kills these projects**); mDNS advertisement; an AP with no captive portal so iOS does
not fight it; and **no cellular modem** — the node is LAN-only by design (§12).

### 4.5 Sync

Drive node → bench host over home Wi-Fi, on return. Recordings are append-only files with
content-hash names; sync is rsync-shaped and idempotent. The bench host is the system of
record for anything historical. The node holds a rolling window (default 30 days or 8 GB,
whichever comes first) and **never deletes an unsynced file**.

---

## 5. The three modes

One app, three entry points, because the same person wants different things in the
driveway and on a back road.

### 5.1 DRIVER — glanceable, safe, in motion

- Big-type live cluster: coolant, oil temp, oil pressure, boost, IAT, battery voltage,
  gear, lambda where available. Zone colouring from `expected_ranges.yaml`.
- **Warm-up gate.** One honest indicator — *"not ready to be driven hard"* until oil temp
  is in range. The most useful thing a turbo Alfa app can show, and no OEM cluster shows
  oil temp meaningfully.
- **Silent watchdog.** Deterministic threshold monitoring across everything polled, not
  just what is on screen. Speaks only when it matters: knock retard, oil pressure below
  the RPM-dependent floor, voltage sag, IAT climbing under sustained boost, coolant
  deviation. **No LLM in this path** (§9.1).
- **MIL-on capture.** If a code sets while driving: freeze frame grabbed automatically,
  drive marked, notification fired. No interaction required, nothing lost.
- **Everything is locked** — no writes above 0 km/h, no exceptions (§12).

### 5.2 ENTHUSIAST — the drive is the artifact

- **Drive log.** Every trip recorded automatically: full parameter series + phone GPS
  (posted to the node while the browser is open, interpolated otherwise), route, duration,
  elevation, ambient. Written in the `csvlog` schema so `recording_series`,
  `recording_events` and `recording_snapshot` work on them **unmodified**.
- **Sessions.** Mark a stretch — a canyon run, a track session, a dyno pull. Overlay runs
  against each other on the same axes, with the X-axis against Δt *or* against any other
  channel (RPM, speed, distance) — the same X-Y capability MES's graph subsystem has.
- **0–100, 100–0, 80–120 in gear**, quarter mile — with the honest caveat that OBD-derived
  speed has latency. Wheel-speed CAN (Tier 2) is the accurate source, and the app labels
  which one produced each number rather than quietly mixing them.
- **Health trend.** Cranking voltage over time; oil temp rise rate; long-term fuel trim
  drift; boost vs. commanded. These are the numbers that show a car going wrong *before* a
  code sets — and the corpus already proves the point: `P0456` on this Stelvio spans
  114,008 → 140,572 km. A chronic fault, invisible to any tool that shows only "last seen".
- **Maintenance ledger.** Service interval, oil life by actual thermal load rather than
  distance, fluids and parts from `ZF8HP_SERVICE_DATA.md`.

### 5.3 MECHANIC — the bench, in your hand

The existing toolchain, made touchable. Straight passthrough to `mes`:

- **Vehicle dossier** = `workup`. Current picture, chronic/returned/fresh classification,
  freeze frames, TSB cross-refs, prior attempts, and — the part no other tool does — the
  blind spots the logs cannot answer.
- **Fault tree** = `fault_tree`. FIM-style isolation, cheapest-first, every step sourced,
  annotated with *this car's own* evidence.
- **Evidence gate** = `diagnosis_verdict`. Refuses CONFIRMED until the fault is
  demonstrated, a mechanism is stated, a corpus-verified measurement implicates the part,
  and disconfirmation was attempted. **This is the app's spine and its differentiator.** A
  parts-cannon scan tool it is not.
- **Repair verification** — the answer to *"is it actually fixed?"*, which MES structurally
  cannot give: readiness monitors (Mode 01 PID 01/41) + permanent DTCs (Mode $0A) + warmups
  and distance since clear, as one verdict, with drive-cycle guidance to complete the
  missing monitors. The disappearance of a code from `$0A` is the cheapest available proof
  the monitor ran and passed.
- **Mode $06** on-board test results — the measured leak value and the ECM's own pass/fail
  threshold. The only non-dealer route to *"the test ran and passed at X against limit Y."*
  Reachable today via `send_raw`; needs MID iteration and ISO 15031-5 UAS scaling. **The
  highest-value unbuilt read in the whole toolchain.**
- **Module map.** All 29 Stelvio modules with bus (A / B–A5 / C–A6), capability flags
  (`INFO|DTC|DTC EX|PRM|ACT|ADJ`), and licence gating. Unreachable modules show *why* —
  "needs A6 grey cable, pins 12/13" — instead of a silent absence.
- **Guided procedures**, each gated by §12: EVAP leak family, P1CEA boost purge, ZF 8HP
  adaptation reset, service interval reset, clutch self-calibration.
- **Known-issue register**, pre-loaded and VIN-checked where possible: ground strap
  corrosion (13 NHTSA complaints, exactly this cohort — the #1 inspection on a 140,000 km
  MY2018), BCM water intrusion recall 18V205000/U36 (all MY2018 Stelvio), fuel pump recall
  25V586000/93C, misfire/harness UA4, BCM fuel-level V84.

---

## 6. Live data: sources, rates, and honesty about both

Two tiers. **The app always labels which tier produced a number**, because their accuracy
differs by an order of magnitude and silently mixing them is how telemetry apps lie.

### 6.1 Tier 1 — OBD-II polling (ELM327/STN)

The baseline. Works on any car, any adapter, no DBC.

- Request/response over a half-duplex link. Realistic aggregate: **8–20 samples/s across
  all channels**, not per channel. Six PIDs at 2 Hz each is a realistic budget on a decent
  STN adapter; a cheap clone will do worse.
- Pin the protocol (`ATDPN` once, then `ATSP6` — never leave `ATSP0` re-searching).
  `ATH1` mandatory for multi-ECU. `ATAT0` + explicit `ATST hh` for deterministic timing.
- **Never swallow** `BUFFER FULL`, `CAN ERROR`, `BUS BUSY`, `STOPPED`, `NO DATA`,
  `UNABLE TO CONNECT`, `?`, `<DATA ERROR`. Surface them as link health, because on this
  platform a degrading link is itself a diagnostic signal.
- Adapter tiering matters: ELM Electronics ceased operations in 2022, so every new
  "ELM327" is a reimplementation and the advertised version string is the least reliable
  datum about it. **STN (OBDLink) is the tier at which multi-ECU work stops being flaky.**

### 6.2 Tier 2 — CAN sniffing with `fca_giorgio.dbc`

The real telemetry path, and the one that answers this car's actual open question.

| Addr | Signals | Rate |
|---|---|---|
| `0x0EE` ABS_1 | `WHEEL_SPEED_FL/FR/RL/RR` | **100 Hz** |
| `0x0FA` ABS_3 | `BRAKE_PEDAL_SWITCH`, brake pressure threshold | 100 Hz |
| `0x0FE` / `0x10E` ABS_2/7 | `LONG_ACCEL`, `LATERAL_ACCEL`, `YAW_RATE` — filtered **and** raw twins | — |
| `0x0DE` EPS_1 | `STEERING_ANGLE`, `STEERING_RATE` | — |
| `0x0FC` ENGINE_1 | `ENGINE_RPM`, `ACCEL_PEDAL`, `REVERSE` | — |
| `0x101` ABS_6 | `VEHICLE_SPEED`, `BRAKE_PRESSURE_1/2` | — |
| **`0x0F1`** | **`MAYBE_VOLTAGE`** (10-bit ×0.02 → 0–20.46 V) | **~100 Hz** |

**`0x0F1` is the single highest-value measurement available for this car.** Validate it
once against a DVOM, then log it at 100 Hz while cranking and cycling the ABS pump, fan and
EPS. A ground-strap or battery fault shows here as sag or noise that a handheld meter
averages away — and the ground strap is the leading root-cause candidate for this car's
whole communication cascade.

Caveats the app must carry in the UI, not bury:

- The DBC is a **2024 first pass**; ~40% of signals are still `NEW_SIGNAL_n`. Accel and yaw
  scale factors are the author's estimates — **relative comparison, not absolute calibration**.
- **Zero UDS/diagnostic content.** It decodes broadcast traffic only and will never read
  `U1711` or `U0100`. Tier 2 complements Tier 1; it does not replace it.
- No transfer case, no ZF 8HP, no IPC, no BCM body traffic.
- Requires a CAN device (comma panda, CANtact, Pi + MCP2515) at the forward-camera
  connector or Bus C — **not an ELM327**.

### 6.3 Free plausibility checks Tier 2 enables

Straight out of the platform research, and worth surfacing as one-tap in-app checks:

| Suspect | Check |
|---|---|
| Yaw / lateral accel (`C1431`) | `ABS_2` filtered vs `ABS_7` raw. Stationary, level: both ≈ 0. Divergence = sensor or supply |
| EPS (`C1403`) | `EPS_2.DRIVER_TORQUE` vs `EPS_3.EPS_TORQUE` vs `LKA_FAULT` |
| Wheel speeds | All four track within a few counts rolling slowly. Dropout with `ACTIVE` still set = wiring, not sensor |
| Brake (`U1711/U1712`) | `ABS_3.BRAKE_PEDAL_SWITCH` vs `ABS_4/6` pressure must agree |
| The cascade itself | `0x0F1` at 100 Hz under load |

---

## 7. Screens

Mobile-first, thumb-reachable, high contrast, legible in sunlight and at night. Nothing
below needs a native app.

| Screen | Contents |
|---|---|
| **Launch** | Which host am I on (bench / drive), which car, link health, what this host can do |
| **Cluster** (driver) | 4–6 large live gauges, configurable; warm-up gate; watchdog banner |
| **Drive** | Current trip: map, speed/RPM trace, session markers, one-tap "mark this" |
| **Drives** | History list → detail with overlay, X-Y plotting, exports |
| **Health** | Trend charts across drives; the "going wrong before it codes" view |
| **Dossier** (mechanic) | `workup` rendered: current, chronic, returned, fresh, blind spots |
| **Codes** | DTC list with first/last seen, session count, odometer span, freeze frames, failure-type decode |
| **Verify** | Readiness + permanent + Mode $06 → one verdict + drive-cycle guidance |
| **Tree** | `fault_tree` walkthrough, step-by-step, each step sourced and VIN-annotated |
| **Gate** | `diagnosis_verdict` form — builds the measurement citations for you |
| **Modules** | The 29-module map with bus, capability flags, reachability |
| **Procedures** | Gated write operations (§12) |
| **Reference** | Ground map, TSBs, recalls, service data, pinouts — the Desktop HTML analyses, folded in |
| **Ask** | Claude (§9) |
| **Settings** | Host, adapter, API key, units, thresholds, sync |

---

## 8. Apple Watch — what is actually possible

Being precise here, because the gap between expectation and reality is large.

**With the PWA (T1/T2), you get:**

- ✅ **Notifications on the wrist.** An installed iOS PWA (home-screen, iOS 16.4+) can use
  Web Push; iPhone notifications mirror to a paired Watch. So the watchdog *can* tap your
  wrist for knock retard, oil pressure, a MIL event.
- ❌ No Watch app, no complication, no glanceable live gauge.
- ❌ No background execution — but this does not matter, because **the node does the
  logging**, not the phone.

**A real Watch experience needs native**, and that is a T3 item: a small SwiftUI iOS app
whose only jobs are (a) a WatchConnectivity bridge and (b) a WKInterface gauge fed by the
node's WebSocket. It does not need to reimplement the app — the PWA stays the main UI.
Estimated 2–3 weeks of Swift work, and **it requires a Mac with Xcode, which this machine
is not.** Plan it as a separate, later, Mac-side project.

**Interim recommendation:** ship Web Push, tune it hard so it fires rarely and always for a
real reason, and treat the Watch as an alerting surface only. That covers the actually
useful case — *"something is wrong right now"* — which is the one you cannot get by
glancing at the phone anyway.

---

## 9. Claude integration — layered, not monolithic

Four layers. Each is independently useful; each degrades cleanly.

### 9.1 Layer 0 — no LLM in the hot path *(mandatory)*

Safety-relevant alerts are **deterministic thresholds evaluated locally**, always. Knock
retard, oil pressure floor, coolant, voltage sag, overboost — none of these wait on a
network round trip, an API key, or a token budget. Claude explains *after* the alert; it
never gates it. This is the single most important design rule in this section.

### 9.2 Layer 1 — direct from the client *(your chosen default)*

The PWA calls the Anthropic API itself.

- **Model:** `claude-opus-5` (1M context, $5/$25 per MTok). `claude-haiku-4-5` ($1/$5) is
  the right cost/latency tradeoff for short in-drive Q&A if that matters; do not downgrade
  the diagnostic path.
- **Thinking:** `thinking: {type: "adaptive"}`, with `output_config: {effort: ...}` —
  `low` for in-drive chat, `high` or `xhigh` for diagnostic reasoning. `budget_tokens` is
  removed on this model and returns 400.
- **Streaming** for anything long, via the SDK's final-message helper.
- **Prompt caching** carries the knowledge pack. Order is `tools` → `system` → `messages`,
  and any byte change in the prefix invalidates everything after it: put the frozen
  knowledge pack and vehicle dossier first, behind a `cache_control` breakpoint, and the
  volatile live snapshot *after* it. Verify with `usage.cache_read_input_tokens` — if it is
  zero across repeated calls, something is silently invalidating the prefix. This is what
  makes a large corpus economically viable to re-send.
- **Browser CORS:** calling the API directly from browser JS requires Anthropic's explicit
  direct-browser-access opt-in header. **Verify the exact header before building on it** —
  it is a documented but deliberately friction-ful path.
- ⚠ **The key lives in browser storage.** Acceptable for T1 (your device, your key,
  your car). **Not acceptable for T3** — shipping an app where each user pastes an API key
  into a web page is a support and security liability. T3 uses Layer 2 instead.

### 9.3 Layer 2 — the PC brain *(optional, highest capability)*

When the bench host is reachable, the client can route through it, and Claude gets **real
tool access to the 28 `mes` tools and the OBD tools** rather than a cached snapshot. It can
call `workup`, `dtc_history`, `parameter_series`, `read_readiness` itself and reason over
the answers. This is a different quality of assistance from Layer 1 — it is the difference
between an assistant that was told about the car and one that can go look.

Implement as a tool-use loop over the same `mes` functions the HTTP API already exposes.
Every tool is read-only except the explicitly gated write set (§12), which **Claude is
never given** — writes stay human-initiated, full stop.

### 9.4 Layer 3 — asynchronous *(cheap, high value)*

- **Post-drive analysis** via the Batch API at 50% cost: every drive gets a written
  summary — anything anomalous, anything trending, anything worth watching — waiting when
  you get home. No latency requirement, so no reason to pay interactive rates.
- **Scheduled review.** A nightly or weekly pass over new logs and drives; flags chronic
  patterns the way `workup` does, but unprompted.

### 9.5 Layer 4 — voice *(later)*

Web Speech API in, TTS out, so the driver mode is genuinely hands-free. Deferred, but
worth designing the "Ask" endpoint so voice is a front-end change only.

### 9.6 What Claude is actually given

| Context | Layer 1 (cached on device) | Layer 2 (live tools) |
|---|---|---|
| Vehicle identity, VIN, mileage | ✅ | ✅ |
| Current DTC set + history summary | ✅ | ✅ live |
| Full log corpus (89 logs) | ✗ summary only | ✅ queryable |
| `docs/research/*` knowledge pack | ✅ | ✅ |
| Live parameter snapshot | ✅ pushed | ✅ pollable |
| Drive recordings | ✗ current only | ✅ all |
| **Write/actuator capability** | **✗ never** | **✗ never** |

**System prompt posture:** the same discipline the toolchain already enforces — do not
assert a diagnosis without evidence, distinguish simulated from real logs, never let a
clean rescan after a clear read as success, and treat a `-2F`/`-86`/`-87` cascade as one
network event rather than N component faults. The evidence gate is a rule for Claude too,
not just for the UI.

---

## 10. Data model

```
Vehicle       vin, name, platform, engine, build_date, sgw_status, notes
Session       id, vehicle, kind{drive|bench|mes_import}, started, ended, provenance
Recording     session, schema_version, channels[], rate, source_tier{1|2}, file
Sample        (in file) time_s, <channel values...>, TAG
Event         session, t, kind{dtc_set|threshold|marker|note}, payload
DtcObservation vehicle, code, ftb, first_seen, last_seen, sessions, odo_span, status
Verdict       vehicle, code, state{unconfirmed|confirmed|refuted}, citations[], author, ts
Procedure     vehicle, kind, params, operator, preconditions_met, result, ts   (immutable)
```

- **Recording files use the `csvlog` schema** — UTF-16LE with BOM, row 1 names, row 2 units,
  first column `Time` in seconds, last column `TAG` — so MES exports and CUORE drives are
  interchangeable to every existing analysis tool. This is worth the mild inconvenience of
  UTF-16 for exactly that reason.
- **Provenance is not optional.** `real | simulated | unverifiable` on every session, as
  the corpus already tracks. SCAN logs remain *unverifiable*, never silently *real*.
- **The `Procedure` table is append-only** and is the T2 liability record.

---

## 11. API surface

`GET /api/capabilities` first — everything else is conditional on it.

**Read (all profiles):**
```
GET  /api/vehicles                       GET  /api/vehicle/{vin}/workup
GET  /api/vehicle/{vin}/dtcs             GET  /api/vehicle/{vin}/dtc/{code}/history
GET  /api/vehicle/{vin}/tree?code=       GET  /api/vehicle/{vin}/modules
GET  /api/recordings                     GET  /api/recording/{id}/series?ch=
GET  /api/recording/{id}/events          GET  /api/recording/{id}/snapshot?t=
POST /api/vehicle/{vin}/verdict
```

**Live (drive profile, or bench when the adapter is free):**
```
GET  /api/live/status                    WS   /api/live/stream
POST /api/live/subscribe   {channels[], rate}
POST /api/live/mark        {label}
GET  /api/live/readiness                 GET  /api/live/permanent
GET  /api/live/freeze/{pid}
```

**Gated writes (§12):**
```
POST /api/procedure/{kind}    requires: precondition token + explicit confirm + 0 km/h
```

The WebSocket carries a compact binary or JSON frame per tick: `{t, {ch: val, ...}}` plus
occasional `event` frames. Client-side ring buffer for the chart; the node's file is the
truth.

---

## 12. Safety, gating, and the write policy

The most important section. This app can move hardware.

1. **No writes in motion.** Every state-changing operation requires `speed == 0` verified
   from the vehicle, not from the phone's GPS. No override, no "advanced mode" toggle.
2. **Claude never holds a write tool.** Not in any layer. It can *describe* a procedure and
   *explain* the preconditions; a human presses the button.
3. **Two-step confirmation** on every procedure, with the specific consequence named —
   not a generic "are you sure?".
4. **Precondition checks before the command**, because UDS `0x22 conditionsNotCorrect` is
   an ECU refusing a real request, and the corpus already contains one (`Fan 1st speed →
   FAILED TO EXECUTE / Engine running`). Check first, do not fail and guess.
5. **Never interrupt an actuator test.** Aborting mid-test can leave an ECU with control
   overridden. The UI must not offer a cancel that does this.
6. **`send_raw` and arbitrary UDS stay expert-only**, behind a distinct unlock, with
   `0x2E`/`0x34`/`0x36`/`0x37` blocked outright. Blind routine IDs on a safety ECU can
   brick a module — this is the most dangerous capability in the toolchain and it is
   ranked low deliberately.
7. **`0x78 responsePending` must be awaited**, never treated as a failure. It is the
   classic client bug and it produces exactly the "it half-worked" symptom.
8. **Hardware checklist, shown before first connection to any Giulia/Stelvio:** verify the
   adapter does **not** short pins 1 and 9 — the vendor warns explicitly that this drops
   the bus on these cars.
9. **Pull `DTC EX` before any clear.** Clearing destroys the only evidence. The app should
   make this automatic, not advisory.
10. **Scan discipline, enforced by the UI:** connect once, note odometer before and after,
    and warn that a whole-vehicle serial scan can itself generate `-2F`/`-87` cascade codes
    by putting modules into extended sessions. If codes appear only after the first scan,
    the app should say so.
11. **The node is LAN-only.** No cellular, no inbound WAN, no cloud relay at T1/T2. If
    remote access is wanted later, Tailscale — not a port forward.
12. **Driving UI discipline:** no text entry, no scrolling lists, no modal dialogs above
    0 km/h. Voice or nothing.

---

## 13. Non-goals

Explicit, so they do not creep in:

- **Not a reimplementation of MES.** No manufacturer ECU database, no attempt to decrypt
  `data01-06.dat` (confirmed infeasible), no PROXI alignment.
- **Not a flashing tool.** MES supports neither J2534 nor DoIP; FCA reflashing needs wiTECH
  plus AutoAuth, and the recall work that matters is free at the dealer.
- **Not an ADAS calibration tool.** Neither DASM nor HALF exposes an `ADJ` routine — the
  capability does not exist in the product at any price. Subcontract or decline.
- **Not a tune.** Read-only on the ECM calibration side.
- **Not a replacement for a scope, a DVOM, or a conductance tester.** The app should say so
  where it matters, particularly on battery state-of-health.

---

## 14. Phasing

| Phase | Deliverable | Depends on |
|---|---|---|
| **P0** | `cuore` package skeleton, FastAPI, `/api/capabilities`, PWA shell, mobile chrome. Port the existing Flask routes | Nothing — buildable on this machine today |
| **P1** | Mechanic mode complete: dossier, codes, tree, gate, modules, reference pages. **Ships real value with no new hardware** | P0 |
| **P2** | Bench live: adapter interlock, live readiness/permanent/freeze, Mode $06 MID sweep | P1, adapter free of MES |
| **P3** | Drive node: Pi image, AP, Tier-1 poller, recorder in `csvlog` schema, WebSocket, driver cluster, watchdog | P2, ~$40 hardware |
| **P4** | Claude layers 0–1 + knowledge pack + caching; Web Push alerts to Watch | P3 |
| **P5** | Enthusiast mode: sessions, overlays, acceleration metrics, health trends | P3 |
| **P6** | Tier-2 CAN sniffing + DBC decode; the 100 Hz `0x0F1` voltage hunt | P3, CAN hardware |
| **P7** | Claude layers 2–3: PC tool-use brain, batch post-drive analysis | P4 |
| **P8** | T2 shop features: multi-vehicle, PDF reports, audit log, sign-off | P1 |
| **P9** | T3: accounts, proxy, native shell + real Watch app | Mac + legal review |

**P0→P1 is the whole first milestone** and needs nothing bought. P3 is where the app
becomes the thing you actually asked for.

---

## 15. Decisions still open

1. **Drive-node hardware.** Old Android phone (free, proves it) vs Pi Zero 2 W (clean) vs
   Pi 4 + CAN (the full thing). Recommend starting with the phone.
2. **Does a Tier-2 CAN device get bought?** Everything in §6.2 and the ground-strap hunt
   depends on it. Highest-value hardware purchase after the A5/A6 cables.
3. **A5 (blue) and A6 (grey) cables** — takes addressable modules from ~10 to 29. Cheapest
   large capability increase available, and no software substitutes for it. Verify pins 1/9.
4. **Which adapter for the node.** The vLinker FS on COM3 is the *Ford* variant, not the
   MES-endorsed MS. Its Ford MS-CAN switching targets pins 3/11, which *is* one of Giorgio's
   extra buses — untested, and worth ten minutes to find out.
5. **Does MES move off COM3?** Recommend yes; COM8/9/10 are free.
6. **Mode $06 MID availability on the IAW 10JA** — a ten-minute check on the car, not a
   research question, and it gates the most valuable unbuilt read.
7. **Verify the browser direct-API header** before building Layer 1 on it.
8. **Units, and whether the 500L gets first-class support** or stays a second vehicle.

---

## 16. Risks

| Risk | Severity | Mitigation |
|---|---|---|
| A write operation damages a module | **Critical** | §12 in full. Writes stay a small, audited, human-only set |
| SD-card corruption silently loses drives | High | Journaled writes, read-only root, sync-before-delete, integrity check on boot |
| Cheap ELM327 clone produces wrong data confidently | High | STN adapter; surface link errors instead of swallowing them; label data tier |
| Adapter contention with MES corrupts a session | High | §4.3, three layers |
| DBC scale factors are estimates → wrong absolute numbers | Medium | Label Tier-2 values as relative; validate `0x0F1` against a DVOM once |
| API key extracted from browser storage | Medium (T1) / **Critical (T3)** | T3 must use the Layer-2 proxy. Never ship T1's model to strangers |
| Claude asserts a diagnosis that is wrong | Medium | The evidence gate applies to Claude's output too; citations required |
| Driver distraction | **Critical** | §12.12. No text entry in motion; alerts are terse and rare |
| Scope creep into a MES clone | Medium | §13, revisited each phase |

---

## Appendix A — corpus at time of writing

89 logs (80 FES / 9 SCAN), 35 real / 54 simulated, 8 vehicles, 2025-09-24 → 2026-08-31,
zero parse failures. Real-data vehicles: Stelvio `ZASFAKPN5J7B88115` (17 logs, all real) and
Fiat 500L `ZFBCFABH1EZ020882` (4 real). Everything else is simulation or unattributed.

## Appendix B — the reachable Stelvio module set today

Bus A, plain ELM327, no adapter: ECM (IAW 10JA) · ZF 8HP TCM · ZF Gear Shift Module · Magna
Q4 Transfer Case · Body Computer Marelli 949 (the gateway) · PROXI Alignment · IPC · RFHUB ·
Service Interval Reset.

Everything else — ABS MK C1, Bosch Airbag, ZF Electric Steering, HALF camera, DASM, torque
vectoring, climate, radio, amplifier, ESEM, blind spot, liftgate — needs the A5 or A6 cable.
