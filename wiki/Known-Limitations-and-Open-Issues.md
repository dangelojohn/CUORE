# Known Limitations and Open Issues

What CUORE cannot do or has not yet proven, as the repository records it. "Unknown" is shown as unknown. The dossier page also carries a collapsible *Known limitations* section for each car.

## Reading the car

| Limitation | Detail |
|---|---|
| **Legislated OBD route goes silent after UDS sessions** | On 2026-10-19 Modes 01, 03, 06, 07, 09, 0A and readiness all returned NO DATA while UDS reads to the same engine computer worked (engine running, port at 14.4 V). The same computer answered all of them on 10-13 and 10-14. The cause is not known. Which route answers has varied between days (29-bit functional or 11-bit 7DF/7E8); CUORE retries on the other and records the route that answered. The scan requirements report such a read as `silent`, a tool fault. **Still open on 2026-10-20.** Two candidate fixes landed that day and are bench-tested only: leaving a physical session now restores default flow control (previously the last module's flow-control header and mode stayed in force), and an opt-in adapter hard reset (see below). Neither has been run on the car, so the silence is not yet known to be cured. |
| **The ABS answered only once** | The ABS answered an identity read at 29-bit address 0x2A once (2026-10-15 00:08) and never again, including after an ignition cycle and an adapter warm start. Cause unknown. A per-request audit now records header and raw reply so the next occurrence is diagnosable. Part of the cause was a timing bug (the software waited less than the adapter's own reply wait); that was fixed. **Still open:** the answer-once cause is unknown. Two candidates are in place and unverified on the car: stale input before a request (below) and the software re-sending a request when a module answers "response pending" (an upstream client library keeps waiting without re-sending; a re-send may be answered once, then ignored). |
| **Stale-reply audit** | Before every request the adapter's input is drained (at most 100 ms) so a late reply or late "pending" answer from the previous request is not read as this one's answer; a complete stale reply for the current target is written to the audit log as `stale_input`. The audit tells whether stale replies happen at all, and it is the first thing to read after the next on-car run. Limits: it drains **before** the write only, so a late reply that arrives *after* the write cannot be told from the answer; a quiet-period read after each reply is not built. |
| **Adapter hard reset is opt-in** | `CUORE_RESET_BEFORE_LEGISLATED=1` makes the first switch from a physical target to the legislated route in a session send one warm-start reset (with a banner check, re-initialisation and flow-control restore). It is **off by default** and unverified on the real adapter; it is the candidate fix for the legislated-route silence. A related hypothesis, untested: after a timeout the software sends a bare carriage return, which on this adapter family may repeat the previous command. |
| **Chassis decoder and addressing passes are unvalidated** | The listen-only chassis decoder ([[Passive Chassis Decoding|Passive-Chassis-Decoding]]) rests on a public database whose scales are partly "estimated" upstream and whose checksum rule is not given; no signal is "confirmed on this car" yet. The 11-bit reply-offset sweep and the extra identity probes ([[Vehicle Networks|Vehicle-Networks]]) have run only against scripted streams. External ids, identifiers and timings are leads ([[External References and Licences|External-References-and-Licences]]). |
| **IHS and CH module addresses unknown** | Only the ABS (0x2A) is confirmed on the chassis bus. The steering, airbag, adaptive lights, parking and camera modules are silent to the 29-bit sweep (hypothesis: they use 11-bit physical ids; an 11-bit discovery routine exists and had not yet been run). No body-bus module on CAN-IHS has a confirmed address: a sweep of 13 candidate targets and a functional TesterPresent got no reply, though the bus is alive. MES reads these modules through the same cables, so the request and receive path is suspected, not the modules. |
| **Cable declaration is manual** | Cable declaration is manual; interlock now refuses transmit without heard traffic. Cable removal is auto-detected only when the declared rate differs from 500k (blue A5); a pulled grey A6 cannot be told apart by rate. |
| **A silent bus is a claim about the listener** | The first "silent" results were the monitor mode, not the car. A negative on one addressing scheme (29-bit) says nothing about the other (11-bit). |
| **Unpublished manufacturer routine identifiers** | The dealer tool starts tests such as the small-leak test through a routine service whose identifiers are unpublished. CUORE never sends routine control (`31`); its replica waits for the computer's own monitor. The ESIM function is a routine and has no readable data identifier, so the **ESIM switch state cannot be read** by CUORE or MES. |
| **Engine hours not available over OBD** | Measured 2026-10-14/15: the engine-hours PID is not supported (the supported-PID bitmap advertises only a few in that group), and the run-time PID counts time since start only. Real engine hours are not readable on this car over OBD. MES's header "operating time" and a freeze-frame operating-minutes field are the nearest values. Recorded in the per-car **capability register** (`cuore/live/capabilities.py`) so the next session does not ask again. |
| **Other measured capability facts** | The exhaust-gas temperature PID returned an impossible value (about 2699 C at warm idle) and is not to be trusted or plotted. Two battery-sensor data identifiers answered plausibly (one read 14.4 V against 14.3 to 14.5 V at the adapter) but their formulas are unverified. Whether an external EGR valve exists is unverified (no source found). |
| **Security Gateway** | Behind the gateway CUORE is limited to what it answers for modules it knows. Bypass and authenticated routes are out of scope. Presence on the reference car is unverified. |
| **Mode 06 test meanings** | What test IDs `3A`/`87` and `3C`/`90` measure on this computer is not published. |
| **Status bits** | Bits b4 and b5 are not implemented by the reference engine computer, so "ran since the clear" cannot be read from the status byte. |
| **Freeze-frame scaling** | Medium confidence. Purge duty, ambient and barometric values were not established in the raw bytes. |
| **Adapter port fallback** | CUORE falls back to the MES registry port when `CUORE_OBD_PORT` is unset. On 2026-10-23 that produced COM1 and a 503 LinkUnavailable on every live call (the first scan attempt aborted before sending anything else). The fix is the user-level environment variable `CUORE_OBD_PORT=COM3`. |
| **Odometer not readable** | PID A6 unsupported on 2018; IPC DID unknown. Candidate for a DID probe on the blue-cable session. |

## The non-EVAP code review: what it could not close

From [[Code Reviews|Code-Reviews]]:

- The ABS has not been read for codes since 2026-09-04 (one silent attempt 10-15), so the owner-attested explanation of the brake code C104B-92 is **unconfirmed by a reading**; the steering, camera and adaptive-light modules were read once, on 09-04. The airbag module has not been read since the airbag lamp lit on 10-14.
- CUORE has never read the radar, transfer-case, steering, camera or head-unit modules, so none of their codes has a status byte or freeze frame. The body computer's snapshot beyond operating time and startups is undecoded.
- No battery voltage at rest, cranking or charging is logged; no brake fluid level; no window, camera or keyless symptom; the owner questions on the network codes are unanswered.
- Whether MES's report after a clear lists returned codes or the pre-clear list is not established.
- Public searches found no document for most of these codes on this car; VIN-gated manufacturer lookups and recall checks have not been done ([[Recalls and Campaigns|Recalls-and-Campaigns]]).

## Evidence and data

- **Gaps stay gaps.** Unsourced values (EVAP purge and vapour-pressure limits, peak boost, tyre pressures from the door placard, some codes, several torques) are stored as unknown. A module sweep found 25 decoded data identifiers, several still raw or unknown; real values should come from the manufacturer's service information, not guesses.
- **Third-party data identifier formulas** (from a catalogue) are marked unverified.
- **Label sheet margins** (a commercial label stock) are unverified until a test grid is printed.
- **Experience links.** Forums block plain HTTP checks, so links are verified through a real browser; some links are flagged as not working.
- **Part images** for 15 parts remain to be verified and linked.

## Platform coverage

- **Only the Alfa Romeo Stelvio data set exists.** The Giulia shares the platform; sibling cars (Maserati Grecale shares the Giorgio platform and engine family; Levante is a different platform with only component overlap; the Ferrari Purosangue is separate) have **no verified bus, pin, bit-rate or module data**. A research pass found nothing at CORROBORATED level, so the sibling bus table is intentionally empty rather than invented.
- VIN decoding for the Maserati SUV prefix deliberately returns "unknown" rather than guessing Levante versus Grecale.

## Application

- Only the `bench` profile is implemented; the `drive` (in-car) profile is reserved.
- No authentication beyond a shared token. Setting the bind address to all interfaces exposes the app to the whole network.
- The phone's LAN address can change on a restart; check it before handing a phone the link. The firewall rule is a one-time administrator step.
- A second adapter (or a permanently wired cable) would remove the cable swap; not yet used.
- Pre-push archive hook: a versioned script exists but is not installed automatically; the owner copies it by hand.
- Optional adapter optimisations (baud raise, pass-filter probe, explicit flow control) are implemented but **unverified on the real adapter**.

## Open issues in the reference case

See [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]: the decisive tests (the ESIM hand-vacuum test, the flash check, an ESIM wiring and bench test) have not been done, and no component is yet proven faulty by a reading. The ESIM was replaced on 2026-10-22 (owner-attested, white cylinder up); the fix is **not proven** until an EVAP monitor completes with no code clearing.

## AlfaCore integration

- The pilot (one real service order, CUORE export then AlfaCore import) has not been run. The bundle and the import module are tested, not yet used on a real order ([[AlfaCore Integration|AlfaCore-Integration]]).
- Transfer is by a carried file only; there is no online sync, by design.
- Password rotation on the shop NAS is outstanding; an optional Documents area in CUORE and the licence decision are open.

## Open items by area

| Area | Open item |
|---|---|
| Radio address | Next CAN-C session: discover 0x6F to confirm the radio's address and read its identity (software version vs MV 090.000.061) |
| Hardware | Run the 11-bit discovery on the chassis bus; blue-cable retry for CAN-IHS; ABS DTC re-read with the new audit; passive capture of an MES session on the chassis bus to read the ids MES uses |
| Connectivity | Test a second adapter, a Bluetooth or Wi-Fi adapter, and a native CAN interface for passive capture |
| Evidence | Decode more freeze-frame fields; obtain the manufacturer's test definitions; read the ECM's external temperature parameter again |
| UI | Timeline media and inspection lane; replay recording on the gauges; a clipped button at 400 px; a fix for the latest electrical-inspection helper |
| Mobile | A native app (the web page and the mobile API contract are the reference) |

Related: [[Roadmap]], [[Vehicle Networks|Vehicle-Networks]], [[Evidence Model|Evidence-Model]].
