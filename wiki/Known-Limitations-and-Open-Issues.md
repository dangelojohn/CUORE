# Known Limitations and Open Issues

What CUORE cannot do or has not yet proven, as the repository records it. "Unknown" is shown as unknown. The dossier page also carries a collapsible *Known limitations* section for each car.

## Reading the car

| Limitation | Detail |
|---|---|
| **Legislated OBD route goes silent after UDS sessions** | On 2026-10-19 Modes 01, 03, 06, 07, 09, 0A and readiness all returned NO DATA while UDS reads to the same engine computer worked (engine running, port at 14.4 V). The same computer answered all of them on 10-13 and 10-14. The cause is not known. Which route answers has varied between days (29-bit functional or 11-bit 7DF/7E8); CUORE retries on the other and records the route that answered. The scan requirements report such a read as `silent`, a tool fault. |
| **The ABS answered only once** | The ABS answered an identity read at 29-bit address 0x2A once (2026-10-15 00:08) and never again, including after an ignition cycle and an adapter warm start. Cause unknown. A per-request audit now records header and raw reply so the next occurrence is diagnosable. Part of the cause was a timing bug (the software waited less than the adapter's own reply wait); that was fixed. |
| **IHS and CH module addresses unknown** | Only the ABS (0x2A) is confirmed on the chassis bus. The steering, airbag, adaptive lights, parking and camera modules are silent to the 29-bit sweep (hypothesis: they use 11-bit physical ids; an 11-bit discovery routine exists and had not yet been run). No body-bus module on CAN-IHS has a confirmed address: a sweep of 13 candidate targets and a functional TesterPresent got no reply, though the bus is alive. MES reads these modules through the same cables, so the request and receive path is suspected, not the modules. |
| **A silent bus is a claim about the listener** | The first "silent" results were the monitor mode, not the car. A negative on one addressing scheme (29-bit) says nothing about the other (11-bit). |
| **Unpublished manufacturer routine identifiers** | The dealer tool starts tests such as the small-leak test through a routine service whose identifiers are unpublished. CUORE never sends routine control (`31`); its replica waits for the computer's own monitor. The ESIM function is a routine and has no readable data identifier, so the **ESIM switch state cannot be read** by CUORE or MES. |
| **Engine hours not available over OBD** | Measured 2026-10-14/15: the engine-hours PID is not supported (the supported-PID bitmap advertises only a few in that group), and the run-time PID counts time since start only. Real engine hours are not readable on this car over OBD. MES's header "operating time" and a freeze-frame operating-minutes field are the nearest values. Recorded in the per-car **capability register** (`cuore/live/capabilities.py`) so the next session does not ask again. |
| **Other measured capability facts** | The exhaust-gas temperature PID returned an impossible value (about 2699 C at warm idle) and is not to be trusted or plotted. Two battery-sensor data identifiers answered plausibly (one read 14.4 V against 14.3 to 14.5 V at the adapter) but their formulas are unverified. Whether an external EGR valve exists is unverified (no source found). |
| **Security Gateway** | Behind the gateway CUORE is limited to what it answers for modules it knows. Bypass and authenticated routes are out of scope. Presence on the reference car is unverified. |
| **Mode 06 test meanings** | What test IDs `3A`/`87` and `3C`/`90` measure on this computer is not published. |
| **Status bits** | Bits b4 and b5 are not implemented by the reference engine computer, so "ran since the clear" cannot be read from the status byte. |
| **Freeze-frame scaling** | Medium confidence. Purge duty, ambient and barometric values were not established in the raw bytes. |

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

See [[Case Study: Stelvio EVAP|Case-Study-Stelvio-EVAP]]: the decisive tests (the ESIM hand-vacuum test, the flash check, an ESIM wiring and bench test) have not been done, and no component is yet proven faulty by a reading.

## Open items by area

| Area | Open item |
|---|---|
| Hardware | Run the 11-bit discovery on the chassis bus; blue-cable retry for CAN-IHS; ABS DTC re-read with the new audit; passive capture of an MES session on the chassis bus to read the ids MES uses |
| Connectivity | Test a second adapter, a Bluetooth or Wi-Fi adapter, and a native CAN interface for passive capture |
| Evidence | Decode more freeze-frame fields; obtain the manufacturer's test definitions; read the ECM's external temperature parameter again |
| UI | Timeline media and inspection lane; replay recording on the gauges; a clipped button at 400 px; a fix for the latest electrical-inspection helper |
| Mobile | A native app (the web page and the mobile API contract are the reference) |

Related: [[Roadmap]], [[Vehicle Networks|Vehicle-Networks]], [[Evidence Model|Evidence-Model]].
