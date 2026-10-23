# Safety Rules

CUORE touches a car's networks. The rules below are enforced in code (`cuore/live/safety.py`, `transport.py`, `buses.py`) and recorded in the README and the handbook. They are short on purpose.

## Read-only by design

- The generic read path may send only these UDS services: `10 01` (default session), `19` (read DTC information), `22` (read data by identifier) and `3E` (tester present).
- Configuration and coding services (`27` security access, `2E` write data, `31` routine control, `34`, `36`, `37` transfer, `85`) are **refused on every module with no override**.
- Commands are validated: one command, printable ASCII, no batch separator, and classified as read, adapter state, vehicle write or blocked against allowlists of AT and ST commands.
- **The web app cannot write to the car.** There is no write route in the HTTP API.
- The writes that exist are MCP-only, behind typed consent phrases: clearing a module's codes (`CLEAR <MODULE>`) and replaying an actuator test learned from a passive capture. Both refuse modules with a safety function (brakes, steering, airbag, transmission, transfer case, driver assistance and similar) and anything on CAN-CH. The clear captures every code, snapshot and counter first, refuses while the car is moving, and reads back afterwards.
- **Modifications are separate from diagnostics.** Coding and configuration are done in MES or the dealer tool from a handoff card and are then recorded in CUORE with who, when, from and to values, backup and verification. CUORE does not perform them.

## Never clear without consent

A clear erases evidence (status bytes, snapshots, counters, the record of which tests ran) and proves nothing: after a clear the monitors have not yet run. Clearing is not fixing. In the reference case the codes returned after every one of eleven clears. The standing rule is: do not clear until the decisive test has been done and recorded.

## CAN-CH needs confirmation

Brakes, airbag squibs and steering assist live on the chassis bus. Passive listening comes first. Any transmission on CAN-CH requires explicit confirmation; fitting the grey cable in the guided scan counts as the confirmation for that segment. CAN-CH is never probed actively.

## Open a bus only at its confirmed rate

Each bus has a single recorded bit rate: CAN-C 500k, CAN-IHS 125k, CAN-CH 500k. A bus is never opened at another rate, even receive-only.

### The 2026-10-14 incident, told plainly

On the night of 2026-10-14, a one-off script was run directly on the adapter's serial port, outside CUORE's session, audit and safety layer. It listened on the chassis bus at 250k and 125k as well as 500k, three receive-only windows of about two seconds each. The adapter reported CAN errors, and the car showed a chime, the airbag lamp and other warning lamps to the owner.

What was changed as a result:

- Never open a bus at any rate but its confirmed one.
- All adapter contact goes through CUORE sessions, so the lock, cable declaration, bus verification and audit log apply.
- An earlier route note ("if silent try another preset and 125k") was withdrawn.
- Any lost-communication codes dated in that window are recorded as tool artefacts, not faults, with notes on the vehicle record.

The lesson recorded: raw serial access to the adapter, even receive-only, is not harmless.

### The 2026-10-23 incident (00:50:02 and 00:50:08), told plainly

The owner pulled the blue A5 cable while a CAN-IHS session was active. The adapter was then on CAN-C at 500k, but CUORE still believed it was on CAN-IHS at 125k. `verify_bus()` for CAN-IHS listened at 125k, heard nothing, and then, by design, transmitted a functional `3E 00` (`18DB33F1`) at 125k onto the 500k diagnostic bus, twice. Both returned CAN ERROR; there was no reply. This is the same class as 2026-10-14: a transmit at the wrong bit rate. A check of bystander U-codes is pending.

What was changed as a result:

- **Transmit interlock.** On any cable route (blue A5, grey A6) and on any bus not at the adapter's default HS 500k, nothing is transmitted (probe, discovery, UDS read, tester present) unless the passive listen in the same call heard at least 5 frames at the declared rate within the last 10 s. Otherwise `verified` is false with the reason "no traffic heard at <rate>; refusing to transmit (cable fitted? ignition on?)".
- **Silence never triggers a send on a cable route.** The "silence, then send one `3E 00`" fallback was removed. Only CAN-C at 500k with cable `none` keeps its single legislated `0100` probe.
- **Cable-removal detection.** If the declared cable's rate hears nothing but a passive 500k listen hears CAN-C traffic, the cable is auto-declared `none`, every bus verification is cleared, a WARNING is logged and `/api/live/status` shows `cable_mismatch`. Passive listens only.
- **Every transmit decision is logged** (bus, rate, frames heard, allowed or refused) at INFO in `server.log`.

## No adapter scripts outside CUORE

Adapter access goes through `cuore/live` so that the lock, the cable declaration and the audit log apply. The audit log records header and raw reply for every UDS request, so an unexplained silence can be investigated afterwards.

## One program holds the port

CUORE checks MES's state and a lock file before opening the adapter; every operation opens the port, does its work and releases it. See [[Hardware and Cables|Hardware-and-Cables]].

## Never transmit on an id the car broadcasts

An 11-bit discovery sweep sends a request frame on each candidate id. Some candidate ids are used by the car for **periodic messages other modules listen to**. Since 2026-10-20 the sweep skips, and lists with the reason, any request id, and any reply id it would expect, that is **defined in the Giorgio CAN database** (`fca_giorgio.dbc`) or **heard in the most recent passive capture on that bus**. The sweep range holds two such ids (`0x73E`, a body-computer message, and `0x749`), and the alternative reply rule can land replies on three more (`0x4AA`, `0x4AE`, `0x547`). The check is enforced in code and tested against scripted streams: the default sweep never transmits on `0x73E` or `0x749`. Details on [[Vehicle Networks|Vehicle-Networks]]; the database on [[Passive Chassis Decoding|Passive-Chassis-Decoding]]. The sweep also needs explicit confirmation on the chassis bus, uses only the read-only services `22` and `3E 00`, and never uses the legislated ids (`7DF`, `7E0` to `7EF`).

## Leave the adapter as found: flow control

Addressing a physical module sets the adapter's flow-control header, data and mode. Leaving a physical target (`untarget`) used to restate the functional header but not the flow control, so the last module's pair stayed in force for functional multi-frame replies. Now every return to functional addressing **restores the default flow control** (default mode, the functional header and the ISO default data `30 00 00`). An optional, **opt-in** adapter hard reset (`CUORE_RESET_BEFORE_LEGISLATED=1`) re-initialises the adapter once per session on the first physical-to-functional switch, checks the banner, and re-states the route and its confirmed bit rate; it never changes a bit rate. Both are bench-tested only ([[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]]).

## Other protections

- **Bus must be verified** before any transmit, under the current cable declaration; the proof lasts 600 s by default. A silent bus refuses the session and sends nothing. On cable routes and non-500k buses the proof must also be fresh: at least 5 frames heard at the declared rate within 10 s of the transmit.
- **No programming-voltage commands.** The adapter has a feature, meant for other brands, that can drive pin 13 (CAN-CH minus on this platform). Never used.
- **Pins 1 and 9** must not be shorted by a cable; continuity-check cables before fitting.
- **Reserved addresses** are never targeted (tester, functional, and one squatted by third-party hardware).
- **Offline by rule.** CUORE runs on the local network with no cloud dependency. The photo-reading provider is off by default (`CUORE_VISION_PROVIDER=none`); the one provider that leaves the network sends a photo to an outside service and is an explicit, informed opt-in by the owner, never turned on by another feature.
- **Access token.** Set `CUORE_TOKEN` before exposing the app beyond a trusted network; the MES corpus contains vehicle identifiers.
- **Evidence handling.** Replay, demo and test data are labelled and excluded from measurement; attested input is never a measurement.
- **Stale replies are audited.** The adapter's input is drained before each request, and a discarded complete reply for the current target is logged as `stale_input`.
- **Outside material stays outside.** Public projects' ids, identifiers and timings are leads and are filed under licence rules ([[External References and Licences|External-References-and-Licences]]); the chassis decoder only listens ([[Passive Chassis Decoding|Passive-Chassis-Decoding]]).
- **Passive learning only.** Bus capture, signal learning and MES-learn never transmit; MES-learn refuses to start unless the port is a different adapter from MES's own.

Related: [[Evidence Model|Evidence-Model]], [[MCP Servers and Claude|MCP-Servers-and-Claude]].
