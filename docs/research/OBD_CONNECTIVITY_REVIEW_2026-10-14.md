# OBD connectivity review: performance, reach, and how CUORE compares

2026-10-14. Scope: `cuore/live/transport.py`, `buses.py`, `poller.py`, `uds.py`, and the
timings in tonight's audit log (`C:\ProgramData\cuore\audit.jsonl`, read-only, car on the
bench 2026-10-13 ~20:25-20:53). No COM3 access was used to write this review — every number
below is either read from the audit log or from this codebase; every new behaviour is tested
against a fake `Stream` (`cuore/tests/check_transport_perf.py`), never the real adapter.

## 1. The current path, as it exists tonight

**Adapter.** vLinker FS r2, chip identifies as STN1170 v4.3.2 (`AdapterLink._probe_identity`,
`transport.py:459`), opened over USB-serial at 115200 baud. MES's own registry
(`HKLM\SOFTWARE\Multiecuscan`, `Interface 0 Port`=`COM3`, `Interface 0 Port Speed`=`115200`,
`Interface 0 Type Ex`=`7`) is configured at the **same** 115200, read directly tonight — so
CUORE is not leaving speed on the table relative to MES's own setting; both are at the
adapter's power-on default.

**Session shape.** `AdapterLink.session()` (`transport.py:325`) opens the port, takes the
MES interlock, runs `_init()` (`ATE0`, `ATL0`, `ATS0`, `ATH1`, `ATAT1`, `ATCAF1`, then
`STP <protocol>`/`STPBR`/`STCMM`), yields a `Session`, and closes the port on the way out —
**per call**. Every `ops.py` function (`obd_pid`, `obd_dtcs`, `module_identity`, `module_did`,
`scan_modules`, `discover`, ...) opens its own session. The live-data poller
(`LivePoller._run`, `poller.py:417`) is the one existing exception: it opens **one** session
for the whole polling run and holds it until `stop()`.

**Addressing.** 29-bit legislated addressing on this car's CAN-C (`STP 34`, `header_bits=29`,
`buses.py:160`); the 11-bit 7DF/7E8 pair (`STP 33`) is the fallback route Mode 01 OBD actually
needs (`ops._obd_route`, `ops.py:289`) because this ECM answers legislated PIDs only on 11-bit,
while UDS 0x22/0x19 needs the 29-bit `18DAxxF1`/`18DAF1xx` pair.

**STFAC/filter issue.** Bench finding 2026-10-13: clearing the STN's pass filters
(`STCFCPC`) to restate the functional header also removes the firmware's *default* pass
filters, after which every reply reads `NO DATA` until the protocol select (`STP`) is
reissued (`transport.py`'s `Session.untarget`, comment above the `STCFCPC` call). This is
exactly the kind of firmware quirk `capture.py`'s `_add_filters` (`capture.py:20-44`) already
works around for the *passive-listen* path, by probing which pass-filter spelling
(`STFPA`/`STFAP`) the firmware accepts rather than assuming — the same pattern this review
now applies to `untarget()`'s heavier path (§3d).

**ISO-TP reassembly** is pure-parser work in `framing.py` (`reassemble`, `parse_frames`):
correct, and untouched here.

**Security Gateway.** Tonight's audit confirms the SGW's exact shape on this 2018+ Giorgio
car: legislated OBD (Mode 01/03/07/0A) and UDS 0x19/0x22 reached ECM, TCM, BCM and IPC on
CAN-C; a full 253-target UDS discovery sweep (`discover can_c`) got **0 hits** in 75.6s, and
ESM/DASM never got a `module_identity` call because they have no confirmed address this
session. This matches the owner's account exactly: the gateway answers requests addressed to
a module it already knows about, but emits nothing unprompted and does not let a blind sweep
find new targets — a bypass module (SGW Bypass / Alfissimo, aftermarket) is what actually
opens the gateway for third-party discovery; CUORE/MES/AlfaOBD without one are limited to the
modules already in the address registry. ([centerlinealfa.com](https://centerlinealfa.com/catalog/sgw-bypass-module-giulia-stelvio-2018), [shopeurocompulsion.net](https://shopeurocompulsion.net/blogs/installation-database/fca-sgw-module-bypass-installation-info))

### Tonight's per-call timings (audit log, last ~120 events)

| Operation | n | time |
|---|---|---|
| `read_pid` session (open+init+1 PID+close) | 38 | 0.32-1.35s, most ≈0.32s |
| `module_identity <ECU>` (9 DIDs, 1 session) | 4 | ECM 2.45s, TCM 1.33s, BCM 5.22s, IPC 5.21s |
| `scan_modules can_c` (DTCs, all modules, 1 session) | 1 | 3.36s |
| `discover can_c` (253 targets, 1 session, 0 hits) | 1 | 75.56s |
| `dtc_detail BCM U1713-2F` | 1 | 1.96s |
| `verify_bus`/`active_probe_0100` | several | 1.3-2.2s each |
| `live_session` (poller, held) | 3 | 934.8s, 577.1s, 881.3s (ended `ClearCommError`/`Access is denied`) |

**Cost centres, in order of impact:**
1. **Per-module session churn.** `fullscan._sweep_bus_modules` calls `ops.scan_modules` (1
   session for all modules), then `ops.module_identity` **and** `ops.module_did` once **per
   module**, each its own `AdapterLink.session()` open/close/`_init`. For the 4 modules that
   answered tonight that is 1 + 4 + 4 = 9 opens instead of 1.
2. **The PID snapshot** (`fullscan._obd_readout`, the `for pid in all_snapshot_pids:
   ops.obd_pid(pid)` loop) opens one session **per PID**. At ≈0.32s/open this is linear in
   PID count for no reason — Mode 01 allows up to 6 PIDs per request.
3. **Discovery's 75.6s for 0 hits** is not a session-churn cost (one session, as it should
   be) — it is 253 × a per-target timeout on a gateway that never answers an unaddressed
   target. This is inherent to blind discovery behind a SGW, not fixable from this side; see
   §4.
4. **The one `live_session` failure** (`ClearCommError`, `Access is denied`, 881s in) is a
   Windows serial-contention fault, not a protocol problem — most likely something else
   (MES, a terminal, antivirus port scanning) briefly grabbed COM3. Out of scope for this
   review's code changes, but it is the kind of fault a single long-held session is more
   exposed to than many short ones; see §4's held-session recommendation.

## 2. Comparison with MES, wiTECH/AutoAuth, AlfaOBD, and a native CAN interface

| | **CUORE (tonight)** | **MultiEcuScan** | **wiTECH 2/AutoAuth** | **AlfaOBD** | **Native CAN (PCAN/SocketCAN)** |
|---|---|---|---|---|---|
| Transport | vLinker FS r2 (STN1170), 115200 baud, port opened per op | Same adapter/port, 115200 per registry (confirmed tonight) | FCA's own VCI (e.g. microPod II) over USB/Ethernet, no ELM/STN layer | Any ELM/STN adapter, typically same ELM AT-command path as CUORE | Direct CAN controller (PCAN-USB, Kvaser, or Linux SocketCAN); no AT-command translation layer at all |
| 11/29-bit CAN | Both, per-route (`buses.py`) | Both | Both, native | Both, same ELM/STN layer as CUORE | Both, native, plus raw/undocumented IDs |
| KWP2000 | N/A — not used on this car | N/A | N/A | N/A | N/A (this is a straight CAN pipe, not a diagnostic stack) |
| Buses reached | CAN-C always; CAN-IHS (blue A5) / CAN-CH (grey A6) need a cable swap | Same OBD port, same single-bus-at-a-time limitation unless the harness is also re-pinned | All buses at once over its own gateway-side harness — no cable swap | Same OBD-port limitation as CUORE | Whatever the harness wires to it; a second interface on IHS/CH removes the swap entirely |
| SGW behaviour | Legislated OBD + UDS 19/22 pass; blind discovery = 0 hits (confirmed tonight) | Same SGW rules — MES does not bypass it either; needs the module already known or an SGW bypass fitted | **AutoAuth**: wiTECH's own cloud-issued, time-limited certificate authenticates the VCI to the gateway for full read/write session access — the sanctioned unlock, not a bypass | Same SGW rules as MES/CUORE | A raw CAN tap behind an SGW bypass box sees everything; in front of one, same silence as the others |
| Session persistence | Per-op by default; the poller is the one caller that already holds one session for a whole run | One held session for the whole scan ("Auto Scan"/"Full Scan") — this is the main structural gap this review closes with `uds.sweep_bus_full` (§3b) | One held, authenticated session per tool run | Similar per-op/per-screen pattern to CUORE, adapter-dependent | One always-open handle; "session" is a software concept on top of it, not a serial open/close |
| Mode 01 multi-PID | **Yes** in the poller already (`poller.py`'s `_poll_pids`, ≤6 PIDs/request); now also available as `Session.query_pids` (§3a) for any other caller | Yes — MES's live-data graphs already request multiple PIDs per frame | N/A (UDS-only tool, not Mode 01 PID-oriented) | Partial/adapter-dependent | N/A at this layer — multi-PID batching is a J1979 concept, irrelevant to a raw CAN pipe (the *application* on top would do it) |
| 29-bit flow control | `STCFCPA` sets the pass-filter address; STmin/BS were never stated explicitly until §3e | Handled inside MES's own closed adapter driver, not inspectable | Native UDS stack, full flow-control control | Adapter-dependent, usually relies on firmware defaults same as CUORE did before §3e | Full control — the application sets BS/STmin directly in the ISO-TP layer it owns |
| Baud raise | Off by default; `STSBR`-based raise now implemented and opt-in (§3c), **unverified on this car** | MES's registry says 115200 tonight — **not** running faster than CUORE | Its own VCI negotiates its own link speed, irrelevant comparison (different hardware class) | Typically stays at the adapter's default unless the user changes it by hand | Not applicable — PCAN/SocketCAN runs the CAN bus itself at its native 500k/125k; there is no USB-UART bottleneck to raise in the first place, which is the real structural advantage of this option |
| Raw multi-frame access | `send_raw`/`STPX` is on the `vehicle_write` classification (`safety.py:106`) — available but gated like any other write | No equivalent exposed to the user | N/A, UDS abstracts this away | No equivalent | This *is* the native mode — every frame is "raw" by construction |
| Phone / wireless | None — USB only | USB (desktop) | Dedicated VCI, Bluetooth/Wi-Fi variants exist for some FCA tools | Commonly used with Bluetooth/Wi-Fi ELM clones (`TcpStream`/Bluetooth `SerialStream` already supported by this codebase's `stream.py`, just never wired to a phone UI) | N/A — PCAN/Kvaser are desktop-tethered; a wireless CAN tap is a different product category |

**What this means concretely:**
- CUORE is not behind MES on baud (both 115200 tonight) or on bus-at-a-time reach (same
  harness limitation, same cable-swap need for IHS/CH).
- CUORE *was* behind MES on session shape — MES holds one session for its whole scan; CUORE
  opened one per micro-operation. §3b narrows this with a reusable held-session sweep
  primitive in `uds.py`.
- Nothing here can out-reach wiTECH's AutoAuth behind the SGW: that is a certificate-issued
  unlock FCA controls, not an adapter-layer trick. The honest ceiling for CUORE on a sealed
  gateway is "what the gateway answers for a known module" — exactly what tonight measured.
- The one place a *different piece of hardware* would materially outperform the current
  USB-serial-to-CAN translation is a native CAN interface (PCAN-USB / Kvaser / SocketCAN) for
  **passive capture**: no STN translation layer, no 115200 UART ceiling, full-rate 500k/125k
  capture of every frame including ones no AT-command surfaces. This only ever gives
  *listening* reach, never SGW-gated reach — it is a research/verification tool, not a
  functional upgrade to diagnostic coverage.

## 3. Implemented now — safe, additive, behaviour-preserving by default

All five are in `cuore/live/transport.py`, `stream.py`, `poller.py`, and `uds.py`; all are
unit-tested against fake streams in `cuore/tests/check_transport_perf.py` (46 checks, all
green) with zero COM3 access. **Ownership note:** `fullscan.py` and `ops.py` are outside this
review's edit scope (owned elsewhere), so the PID-snapshot loop
(`fullscan._obd_readout`, around line 339) and the per-module sweep
(`fullscan._sweep_bus_modules`) are **not** rewired to the new primitives below — that wiring
is listed as a recommendation in §4 for whoever owns those files, with the before/after
estimate it would realise.

### (a) Mode 01 multi-PID: `Session.query_pids` (`transport.py:140`)

Batches up to `MAX_MULTI_PID` (6, the J1979 cap) PIDs into one `01<pid><pid>...` request,
splits the reply per responding ECU (`_split_multi_pid`, generalised from the poller's
existing per-tick logic), and automatically retries any PID a batch left short as its own
single request — never silently drops one. This is the exact mechanism the live-data poller
already uses internally (`poller.py`'s `_poll_pids`/`_parse_multi_pid`, unchanged here); it is
now also available as a session-level primitive for any other caller holding a session.

*Tested*: full-batch success, partial-batch fallback (one ECU answers fewer PIDs than asked),
>6-PID requests split into two batches, and the single-PID no-multi path — 10 checks in
`check_transport_perf.py`.

*Before/after estimate for the PID snapshot, from tonight's numbers*: `read_pid` sessions
averaged ≈0.32-0.8s each; a snapshot of ~20 supported PIDs today costs ~20 × that ≈ 6-16s. One
held session (§3b's pattern) issuing `query_pids` in batches of 6 would cost one session open
(~0.25-0.3s) plus ⌈20/6⌉ = 4 requests at roughly the per-request round-trip only (no re-open) —
projected **≈1-2s**, a 4-10× reduction. **Projected, not measured**: this requires
`fullscan.py`'s owner to call `query_pids` from the held session instead of `ops.obd_pid` in a
loop; see §4.

### (b) Held-session module sweep: `uds.sweep_bus_full` (`uds.py:122`)

DTCs (`19 02 FF`) + identity (the Annex C DID set) + one named DID, per module, all inside the
**one** session the caller already has open — no `AdapterLink.session()` call inside it at
all. This is the held-session equivalent of what `fullscan._sweep_bus_modules` currently does
across three separate session opens per module (`scan_modules`, `module_identity`,
`module_did`).

*Tested*: one module scripted through DTC + identity + DID reads, with a structural assertion
that `ATE0` (sent exactly once per session `_init`) appears exactly once across the whole
sweep — proof of one session, not N.

*Before/after estimate*: tonight's `module_identity` alone cost 2.45/1.33/5.22/5.21s for
ECM/TCM/BCM/IPC — each paying its own port-open + `_init` on top of the 9 DID reads. Folding
DTC+identity+DID into the module loop of one already-open session removes 2 of those 3 opens
per module; at the ≈0.25-0.3s open+init overhead implied by the `read_pid` baseline, that is
roughly **0.5-0.6s saved per module**, ~2-5s for the 4 modules this gateway lets through
tonight — smaller in raw seconds than §3a, but it also removes 2×(N-1) extra MES-interlock
acquire/release and port open/close cycles, each one a chance at the kind of Windows
`ClearCommError`/"Access is denied" fault that ended tonight's last `live_session`.
**Projected, not measured**: adopting this in `fullscan._sweep_bus_modules` is a recommendation
(§4), not wired in by this review.

### (c) Optional UART baud raise: `AdapterLink.raised_baud` (`transport.py:628`)

Opt-in (`CUORE_ADAPTER_BAUD`, 0 = off, matching tonight's 115200 default exactly), self-
reverting `with` block around a held session, using the STN's **temporary** `STSBR <rate>`
(never `STWBR`, so a lost revert still clears itself at the adapter's next power cycle) plus
`STI` to confirm the switch actually took. Never sent to a transport that cannot follow:
`Stream.supports_set_baud` (new, `stream.py`) is checked *before* any `STSBR` reaches the
adapter — `SerialStream` is the only transport that sets it `True`, so a Bluetooth/TCP clone
is simply never asked rather than being told to change and then left mismatched.
`poller.py`'s `_run` wraps its hot loop in this (`poller.py:447`): the poller is the one
caller that already holds a session for long enough to amortise the raise, and the wrapper is
a true no-op (skips straight to `yield False`) whenever the env var is unset — exactly
tonight's configuration.

*Tested*: feature off (no `STSBR` sent at all), success path (confirmed by a scripted `STI`
echo, `link.baud` reflects the raise then reverts), unsupported transport (never asks the
adapter), and adapter-refuses-the-switch (link state untouched) — 4 scenarios, 11 checks.

**UNVERIFIED on the real adapter.** `STSBR`'s exact syntax and the "switch host side, then
confirm with `STI`" procedure come from scantool.net's own documentation of the STN baud-
switch commands ([scantool.net/blog](https://www.scantool.net/blog/switching-communication-baud-rate/)), not from a bench test on this vLinker FS. vLinker FS units also have
a documented firmware-version gate on baud persistence (older firmware reverts to 115200 on
restart regardless) ([forum.forscan.org](https://forum.forscan.org/viewtopic.php?t=23037)) — another reason this stays off by default pending a real test.

### (d) Probe-based pass-filter restore (`transport.py:597`, `Session.untarget`)

`AdapterLink._probe_pass_filter` tries `STFAP 1,<functional-header>,FFFFFFFF` **once per
link**, cached; `untarget()` uses the lighter restore (re-apply the functional pass filter
directly) only when that probe came back a clean `OK`, and otherwise uses the exact
`STCFCPC`+`STP`-reissue path this codebase already proved works on the bench (unchanged,
same commands, same order). **Off by default** (`CUORE_PASS_FILTER_PROBE`, unset = probe
never runs, `pass_filter_mode` is cached as `"stp_reissue"` without ever touching the wire) —
this was tightened after the first pass broke `check_coverage.py`'s exact-wire-sequence
regression test against a fake adapter that answers "OK" to any AT/ST-prefixed command
indistinguishably from real support; gating it behind an explicit opt-in was the only way to
add the capability without that false positive risk, and keeps every existing caller's
behaviour byte-for-byte unchanged.

`capture.py`'s `_add_filters` already probes between `STFPA`/`STFAP` spellings for the
*passive-listen* filter path (`capture.py:20-44`) — this is the same idea applied to
`untarget()`'s heavier restore, using the spelling `_add_filters` settles on as `STFAP`.

*Tested*: probe disabled (default) preserves the exact `STCFCPC`+`STP` sequence; probe enabled
+ adapter confirms → lighter path used, `STCFCPC` never sent; probe enabled + adapter says
`?` (unsupported) → exact fallback sequence preserved.

**UNVERIFIED on the real adapter** — the bench comment this review preserves names the
problem command "STFAC" while the code sends "STCFCPC"; that mismatch already existed before
this review and is left exactly as found (not this review's to resolve). Whether this
specific vLinker FS/STN1170 firmware answers `STFAP` with a clean `OK` is unknown without a
bench test with `CUORE_PASS_FILTER_PROBE=1`.

### (e) Explicit ISO-TP flow control for 29-bit targets (`transport.py`, `Session.target_raw`)

29-bit STN targets now also get the same `ATFCSH`/`ATFCSD300000` (BS=0, STmin=0)/`ATFCSM1`
flow-control statement the non-STN (ELM-equivalent) path already sent — additive, since
`STCFCPA` alone only routes which header gets flow control, never states STmin/BS. STN chips
are a documented ELM327 command-set superset ([scantool.net](https://www.scantool.net/stn1170/)), so the same commands already proven on the non-STN branch are a reasonable default; a
firmware that rejects `ATFCSx` under an ST protocol select just answers `?` and `STCFCPA`'s
own routing still holds — nothing is removed by this addition.

*Tested*: targeting ECM over the 29-bit route sends `ATFCSH<hdr>`, `ATFCSD300000`, `ATFCSM1`,
and still sends `STCFCPA` too (additive, not a replacement) — 4 checks.

**UNVERIFIED on the real adapter** — BS=0/STmin=0 (send consecutive frames back-to-back) is a
reasonable default, not a value read off this car's actual gateway behaviour.

## 4. Recommendations

| # | Recommendation | Cost | Benefit | Needs the car to verify? | Status |
|---|---|---|---|---|---|
| 1 | Wire `fullscan._obd_readout`'s PID-snapshot loop to one held session + `Session.query_pids` instead of `ops.obd_pid` per PID | Low — `fullscan.py`'s owner swaps the loop body; primitive already exists and is tested | ~4-10× fewer round trips for the snapshot step (§3a estimate) | No — the primitive is fake-tested; only the real-car timing improvement needs confirming | **Done (2026-10-14)** — `fullscan._obd_readout` now calls the new `ops.obd_pids_snapshot` (one held session, `Session.query_pids` batching) instead of `ops.obd_pid` once per PID; `scan_coverage["sessions_opened"]` makes the reduction measurable on the car. Freeze-frame PIDs got the same treatment via the new `ops.obd_freeze_frames` (one held session per code's full PID set). Real-car timing still unconfirmed. |
| 2 | Wire `fullscan._sweep_bus_modules` to `uds.sweep_bus_full` (one session per bus instead of 1+2N) | Low-medium — same swap, slightly more surface since 3 ops functions collapse into 1 | Fewer port open/close cycles (2-5s + reliability, §3b) | No — primitive tested; real-car timing needs confirming | **Done (2026-10-14)** — `fullscan._sweep_bus_modules` now calls the new `ops.sweep_bus_full` (one held session per bus: DTCs + identity + DID together) instead of `scan_modules`+`module_identity`+`module_did` per module. Real-car timing still unconfirmed. |
| 3 | Try `CUORE_ADAPTER_BAUD=500000` (or whatever this vLinker FS firmware actually accepts) on the bench, watching `AdapterLink.status()`'s new `last_baud_raise` field | Very low — one env var, already off by default, self-reverting | If it holds, every held-session op (poller, a future held scan) gets faster per-byte transfer, though most requests here are 1-2 CAN frames so the win is modest until traffic volume rises | **Yes** — `STSBR`'s real behaviour on this specific vLinker FS/STN1170 is unverified | Open — not attempted |
| 4 | Try `CUORE_PASS_FILTER_PROBE=1` on the bench and read `AdapterLink.status()`'s `pass_filter_mode` afterwards | Very low — one env var, off by default, proven fallback preserved | Removes the `STCFCPC`+`STP`-reissue cost (full protocol re-init) from every `untarget()` once a module-targeted read finishes, if the probe confirms | **Yes** — whether this firmware answers `STFAP` cleanly is unknown | Open — not attempted |
| 5 | Confirm the new 29-bit flow-control statement (§3e) does not change behaviour on CAN-C (it should be inert if the adapter already defaulted to BS=0/STmin=0) | None — already shipped, additive | Explicit rather than implicit timing; matters more once BS/STmin ever need to be non-zero (e.g. a slower module) | **Yes** — confirm no regression in UDS read latency/success rate | Open — not attempted |
| 6 | A second vLinker (or any STN/ELM adapter) permanently wired to the blue A5 or grey A6 cable, so IHS/CH never needs a cable swap mid-session | Medium — a second adapter, ~$30-60 | Removes the single biggest "reach" limitation this review found: one bus at a time | Partially — needs the second cable/adapter in hand, but the software side (cable declaration, `buses.py`) already supports it today | Open — hardware decision, not attempted |
| 7 | A PCAN-USB or Kvaser (or a Linux box running SocketCAN) tapped in passively alongside the vLinker, for full-rate capture independent of the STN's 115200 UART ceiling | Medium-high — ~$80-200 for a basic PCAN-USB, plus a parser for its own wire format | Full-bus-rate passive capture with zero translation-layer loss; useful for verifying what `capture.py`'s `listen()` might be missing at 115200, and for any future reverse-engineering work | No — purely additive instrumentation; does not touch the diagnostic path | Open — hardware decision, not attempted |
| 8 | A Bluetooth/Wi-Fi vLinker (or any ELM/STN Bluetooth/Wi-Fi clone) for a phone-based interface | Low-medium — the hardware exists off the shelf; `stream.py` already has `TcpStream` for a Wi-Fi bridge and `SerialStream` already works over a Bluetooth virtual COM port with no code change | Reach: a phone-based quick-check without a laptop | No — software side already supports both transports; this is a hardware/UI decision, not a protocol one | Open — hardware/UI decision, not attempted |
| 9 | Do **not** attempt an SGW bypass or AutoAuth-equivalent from this codebase | N/A | N/A | N/A — this is a hardware/certificate product (SGW Bypass module, or FCA's own AutoAuth), explicitly out of scope for a read-only diagnostic tool; discovery hitting 0 behind the gateway tonight is expected, not a bug to chase in software | Decided — out of scope, no action planned |

## Verification run (this review)

`check_transport_perf.py` (new, 46 checks), `check_live.py` (177), `check_active_probe.py`
(23), `check_fullscan.py` (222), `check_coverage.py` (126) — all green, no COM3 access. Broader
regression (`check_live_data.py`, `check_perf.py`, and the rest of `cuore/tests/check_*.py`)
also run clean against these changes.
