# Passive Chassis Decoding

CUORE can decode the broadcast frames of the chassis bus (CAN-CH) into steering angle, wheel speeds, brake switch and similar signals, **by listening only**. Nothing is transmitted. The decoder landed on 2026-10-20 and has been tested on the bench with scripted frames; it has **not yet been validated on the car**.

## Why a decoder, and what it is not

The chassis bus carries about 400 frames per second over about 30 ids when the car is awake, almost all 11-bit broadcasts ([[Vehicle Networks|Vehicle-Networks]]). Until now CUORE only counted them. A public CAN database for this platform names most of the busiest ids, so the same listen can show *what* they carry. Two uses follow: a passenger-readable chassis panel, and a first step toward comparing brake, engine and body frames at the port when the network codes need a frame census ([[Network and Brake Findings|Network-and-Brake-Findings]]).

It is **not** a diagnostic read of the brake or steering modules. It gives no fault codes, and it decodes what another module chose to send, so it is a lead until compared with the car ([[External References and Licences|External-References-and-Licences]]).

## The database

`cuore/data/dbc/fca_giorgio.dbc` is an unmodified copy of `fca_giorgio.dbc` from the commaai/opendbc project: **MIT licence**, 37 messages, added upstream in 2024 as an initial database for the Stelvio and Giulia. The licence text (`LICENSE-opendbc`) and a `SOURCE.md` with the URL and fetch date sit beside it. The database does not say which bus it was captured on; its ids match the chassis bus, so it is probably that bus (inference). Many scales are marked "TBD" or "estimated" upstream.

## What is decoded

`cuore/live/dbc.py` is a small, dependency-free parser (message and signal lines, both byte orders, signed values, value tables); `cuore/live/chassis_decode.py` applies it to a captured frame list and reports, per message, the latest decoded signals, the count and the rate.

| Id | Message | Signals (as named upstream) |
|---|---|---|
| `0x0DE` | EPS_1 | steering angle, steering rate, counter, checksum |
| `0x0EE` | ABS_1 | four wheel speeds, counter, checksum |
| `0x0FA` | ABS_3 | brake pedal switch, brake pressure threshold |
| `0x0FC` | ENGINE_1 | engine speed, accelerator pedal percent, reverse |
| `0x106` | EPS_2 | driver torque, lane-keep status and fault |
| `0x10E` | ABS_7 | raw longitudinal and lateral acceleration, yaw rate |
| `0x116` | ABS_5 | wheel impulses, wheel active and direction bits |
| `0x11C` | (unnamed upstream) | vehicle speed (scale estimated upstream), three unknown signals |
| `0x122` | EPS_3 | steering torque |

Ids that the database lacks are tallied as unknown, not guessed; frames that do not parse are counted as bad. Counter and checksum signals are carried, but the checksum algorithm is not given upstream, so CUORE **does not claim a frame is valid** from it; the counter can only reveal dropped frames. Signals with an estimated scale show the raw value and the upstream caveat. The database lists no body-bus (CAN-IHS) ids and nothing for the gear, the keep-alive frames or the camera's `1E36001E` frame beyond a one-byte stub.

## How to use it

- **Route:** `GET /api/live/chassis/passive` (optional `seconds`, clamped to 0.5 to 5, default 2). It is served by `liveboard_bridge.chassis_passive` and requires the access token when one is set. There is no page for it yet.
- **Requirement:** the **grey A6 cable** declared. With any other cable the answer is `available: false` with the reason, not an error.
- **How it listens:** a *passive* session (adapter silent mode on), the 11-bit route (`STP 33`) at the chassis bus's single confirmed rate of 500 kbit/s, all frames passed unfiltered, `STMA`. Every guard in [[Safety Rules|Safety-Rules]] still applies: the bus is verified before the session, one program holds the port, and the audit log records it. No other rate is ever opened.
- **Result:** the frame count, the decoded messages with signals and rate, the unknown ids, the bad-frame count, and the source label "fca_giorgio.dbc (opendbc, MIT)".

## Validation still to do on the car

All passive, engine off with the ignition on, then a short drive:

1. Engine speed reads 0 with the engine off.
2. The brake-switch bit follows the pedal.
3. Steering angle follows the wheel turned by hand.
4. Wheel speeds read near 0, then compare the `0x11C` speed and the other speed message with Mode 01 vehicle speed on the powertrain bus on a short drive.

Record the comparison; only then does a signal move from "lead, unverified on our car" to "confirmed on this car". A continuous (held) channel set on the live board, and replacing the hand-copied broadcast-signal rows in the capture presets with this one parsed source, are open items so that two copies of the same table cannot drift ([[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]]).

## Safety by-product

The same database makes the 11-bit discovery sweep safer: it never transmits a request on an id the car broadcasts itself. See [[Safety Rules|Safety-Rules]].

Related: [[Live Board|Live-Board]], [[Hardware and Cables|Hardware-and-Cables]].
