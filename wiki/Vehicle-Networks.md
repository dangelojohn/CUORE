# Vehicle Networks

The reference car has three CAN buses. The OBD port reaches one of them directly; the other two need a bypass cable ([[Hardware and Cables|Hardware-and-Cables]]). The tables here are transcribed from `cuore/live/buses.py` and `cuore/live/addressing.py`, whose source of truth is the [Giorgio module map](https://github.com/dangelojohn/CUORE/blob/main/docs/reference/GIORGIO_MODULE_MAP.md). Where the map says "unknown", the code stores `None`; confidence is never upgraded.

## The three buses

| Bus | Role | Pins | Bit rate | Cable | Modules seen answering |
|---|---|---|---|---|---|
| **CAN-C** | Diagnostic / powertrain | 6 / 14 | 500 kbit/s (confirmed) | none | ECM, IPC, TCM, DTCM, ESM, BCM, RFHUB, DASM |
| **CAN-IHS** | Body / comfort / infotainment | 3 / 11 | 125 kbit/s (confirmed) | blue A5 | none yet (bus alive, no module has answered UDS) |
| **CAN-CH** | Chassis / ADAS / safety | 12 / 13 | 500 kbit/s (confirmed) | grey A6 | ABS (once); EPS, ORC, AFLS, PAM, HALF known from MES scans |

This partition was observed in every no-cable MES scan of the car: always the same eight modules on CAN-C, and a disjoint six on the second group. The body control module (BCM) is the gateway between CAN-IHS and CAN-C, and it is reached diagnostically on CAN-C.

**Rule: open a bus only at its confirmed rate.** See [[Safety Rules|Safety-Rules]].

## Routes: how CUORE reaches each bus

A *route* is an adapter protocol preset plus, where needed, a bit-rate override.

| Bus | Cable | STN preset | Header width | Status |
|---|---|---|---|---|
| CAN-C | none | 34 | 29-bit | Confirmed. UDS and the 29-bit legislated functional address. |
| CAN-C | none | 33 | 11-bit | Legislated 7E0/7E8 pair and 7DF functional request. |
| CAN-IHS | blue A5 | 34 + bit rate 125000 | 29-bit | Untested for UDS. Never use presets 53/54 with the cable fitted. |
| CAN-IHS | blue A5 | 33 + bit rate 125000 | 11-bit | **Confirmed** for listening (2026-10-15, car awake). |
| CAN-IHS | none | 54 | 11-bit | Cable-less medium-speed route; untested. |
| CAN-CH | grey A6 | 34 | 29-bit | Confirmed at 500 kbit/s. UDS route. |
| CAN-CH | grey A6 | 33 | 11-bit | **Confirmed** for listening. |

## 11-bit versus 29-bit

- **Broadcast traffic** on the Giorgio buses is largely **11-bit**. A monitor opened 29-bit-only can report zero frames on a healthy bus. The first listening attempts on 2026-10-14 reported three "silent" buses; the fault was the monitor, not the car. CUORE now listens with all frames passed unfiltered (`ATCAF0` + `STMA`) on the 11-bit route.
- **Diagnostic (UDS) requests** use 29-bit physical addresses: request `18DA<target>F1`, response `18DAF1<target>`. The tester address is `F1`. The functional (broadcast) request is `18DB33F1`.
- **Legislated OBD** (Modes 01, 03, 06, 07, 09, 0A) can be answered on either the 29-bit functional pair or the 11-bit `7DF` / `7E8` pair. Which one answers has varied between days on the reference car. CUORE tries the route proven by its active probe first and retries once on the other, recording the route that answered (`route_fallback`).
- **Reserved targets:** `F1` (tester), `33` (functional) and `BA` (squatted by a third-party project's hardware; never use `18DABAF1`).
- Sweeps are **not reliable negatives** unless the python-side wait matches the adapter's own reply wait: after `ATSTFF` the adapter waits about 1.02 s, and a shorter wait turned 29-bit and 11-bit sweeps into false "no answer" results (fixed 2026-10-15).

## Keep-alive (network management) ids

Periodic frames of the form `1E34xxxx` and `1E36xxxx` are heard on the 29-bit route of both bypass-cable buses, whether the car is awake or not.

| Bus | Ids heard |
|---|---|
| CAN-IHS (blue A5, 125k) | 1E340000, 1E340003, 1E34000A, 1E340024, 1E340030, 1E340033, 1E340034, 1E340045, 1E340067 |
| CAN-CH (grey A6, 500k) | 1E340000, 1E340006, 1E360002, 1E360006, 1E360018, 1E36001A, 1E36001D, 1E36001E |

*Hypothesis, untested:* the low byte of a `1E34xxxx` id may be the sending node's diagnostic address (the AUTOSAR network-management convention). It is not used as fact anywhere.

## Awake and asleep signatures

Observed on the car on 2026-10-15, read-only:

| Bus | Route | Awake | Asleep |
|---|---|---|---|
| CAN-IHS, blue A5, switch on HS | 11-bit, preset 33 + rate 125000 | **317 frames in 2 s over 54 ids** (3E2, 3E4, 3E6, 3E8, 2F0, 3DC, 3DE, 3E0 ...) | not recorded |
| CAN-IHS | 29-bit, preset 34 | only the keep-alive ids, about 9 frames per second | same |
| CAN-CH, grey A6 | 11-bit, preset 33 | about 400 frames per second over about 30 ids (0DE, 0EE, 0FC, 106, 10E, 116, 11C, 122 ...); earlier listens: 818 frames in 2 s, 438 frames in 2 s | **silent** about 25 minutes after ignition on with the engine off; the ABS also stops answering UDS |
| CAN-CH | 29-bit, preset 34 | about 12 frames per second of keep-alive ids | same: **cannot tell awake from asleep** |

So the 29-bit route cannot distinguish awake from asleep on the chassis bus; only the 11-bit route can.

## Module address table

Targets are the single byte in `18DA<target>F1`. Confidence is the project's own grade for the **address**: `confirmed` (the module answered an identity read matching this car, or a primary source), `unverified` (one weak or self-declared source), `inferred`, or `unknown` (stored as none).

### Present on this car (appeared in the car's own scans)

| Code | Module | Bus | Target | Address confidence |
|---|---|---|---|---|
| ECM | Engine control, Magneti Marelli IAW 10JA | CAN-C | 0x10 | confirmed |
| TCM | Transmission, ZF 8HP | CAN-C | 0x18 | confirmed |
| BCM | Body computer, Marelli 949 (gateway) | CAN-C | 0x40 | confirmed |
| IPC | Instrument panel, Continental | CAN-C | 0x60 | confirmed |
| RFHUB | Radio frequency hub, Continental | CAN-C | 0xC7 | confirmed |
| DTCM | Transfer case, Magna Q4 | CAN-C | 0x29 | unverified |
| ESM | Electronic shift module, ZF | CAN-C | none | unknown |
| DASM | Driver-assistance radar, Bosch | CAN-C | none | unknown |
| **ABS** | Anti-lock brakes, Continental MK C1 | CAN-CH | **0x2A** | **confirmed** (identity read matched the car's VIN, 2026-10-15) |
| EPS | Electric steering, ZF | CAN-CH | none | unknown |
| ORC | Airbag / occupant restraint | CAN-CH | 0x50 | unverified |
| AFLS | Adaptive headlights | CAN-CH | none | unknown |
| PAM | Parking control, Bosch | CAN-CH | none | unknown |
| HALF | Lane-feedback camera, Bosch | CAN-CH | none | unknown |

An earlier table put the ABS at a different address and gave 0x2A to the steering module. The 2026-10-15 discovery corrected this: 0x2A answered an identity read with this car's VIN and ABS part numbers, so ABS 0x2A is confirmed and the steering address is unknown. A forum-sourced address is a hypothesis until an identity read plus a VIN match promotes it.

### Listed by MES for this car but never answered

| Code | Module | Bus (inferred) | Target |
|---|---|---|---|
| HVAC | Climate control | CAN-IHS | 0x68 (unverified) |
| ETM | Radio / navigation head unit | CAN-IHS | 0x6F (unverified) |
| AMP, ESEM, CSWM, CRSM, LBSS, RBSS, PLGM | Amplifier, engine sound, seat/wheel comfort, rear seat, blind-spot sensors, power liftgate | CAN-IHS | unknown |
| TVM, ESL | Torque vectoring, steering lock | CAN-CH | unknown (did not answer on the grey-cable scan) |

The security gateway itself is not enumerated by MES; its presence on the reference car is unverified.

### Identity read

Identity uses ISO 14229 data identifiers (`22 F190` VIN, `F187` part number, `F188` software number, `F191` hardware, `F192` supplier hardware, `F194` supplier software, `F18C` serial). A module counts as a confirmed address only when the reply matches the car.

Related: [[Guided Full Scan|Guided-Full-Scan]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].
