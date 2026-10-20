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

## No adapter scripts outside CUORE

Adapter access goes through `cuore/live` so that the lock, the cable declaration and the audit log apply. The audit log records header and raw reply for every UDS request, so an unexplained silence can be investigated afterwards.

## One program holds the port

CUORE checks MES's state and a lock file before opening the adapter; every operation opens the port, does its work and releases it. See [[Hardware and Cables|Hardware-and-Cables]].

## Other protections

- **Bus must be verified** before any transmit, under the current cable declaration; the proof lasts 600 s by default. A silent bus refuses the session and sends nothing.
- **No programming-voltage commands.** The adapter has a feature, meant for other brands, that can drive pin 13 (CAN-CH minus on this platform). Never used.
- **Pins 1 and 9** must not be shorted by a cable; continuity-check cables before fitting.
- **Reserved addresses** are never targeted (tester, functional, and one squatted by third-party hardware).
- **Offline by rule.** CUORE runs on the local network with no cloud dependency. The photo-reading provider is off by default (`CUORE_VISION_PROVIDER=none`); the one provider that leaves the network sends a photo to an outside service and is an explicit, informed opt-in by the owner, never turned on by another feature.
- **Access token.** Set `CUORE_TOKEN` before exposing the app beyond a trusted network; the MES corpus contains vehicle identifiers.
- **Evidence handling.** Replay, demo and test data are labelled and excluded from measurement; attested input is never a measurement.
- **Passive learning only.** Bus capture, signal learning and MES-learn never transmit; MES-learn refuses to start unless the port is a different adapter from MES's own.

Related: [[Evidence Model|Evidence-Model]], [[MCP Servers and Claude|MCP-Servers-and-Claude]].
