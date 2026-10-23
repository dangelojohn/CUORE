# Hardware and Cables

CUORE talks to the car through one OBD adapter on one serial port. This page covers what the project has used and learned about the adapter, the OBD connector, the two bypass cables, the Security Gateway, and why only one program may hold the port. Products are mentioned as what the project used or what a document records; none is endorsed here.

## The adapter

- **Chip family:** STN1170 (an ELM327-compatible chip with the extra `ST` command set: hardware pass filters, filtered monitoring, device identification). The reference adapter is a **vLinker FS** (revision 2), which identified itself as STN1170 firmware 4.3.2.
- **Link:** USB serial (an FTDI chip), 115200 baud. MES's own settings on the same PC used the same speed, so CUORE is not slower than MES on the serial link. An optional, off-by-default baud raise exists and is marked unverified on the real adapter.
- **Selection of port and speed:** call arguments, then `CUORE_OBD_PORT` / `CUORE_OBD_BAUD`, then `OBD_PORT` / `OBD_BAUD`, then the Interface 0 settings in MES's registry key.
- **Why STN rather than plain ELM327:** clone ELM327 chips often ignore header and flow-control commands or break 29-bit addressing. The STN tier was chosen because multi-module work stops being flaky there. A native CAN interface (PCAN, Kvaser, SocketCAN) would give full-rate passive capture but, as the connectivity review notes, never more reach behind a gateway; it is listed as an open hardware decision in [[Roadmap]].

### The HS / MS switch

The vLinker FS has a hardware switch labelled HS and MS. CUORE decides the switch position from the **route**, not from the bus speed:

- With **either** bypass cable fitted (blue A5 or grey A6), the cable moves the car's bus pins onto the adapter's normal high-speed pins (6/14), so the switch stays on **HS**, even for the 125 kbit/s CAN-IHS bus.
- **MS** is only for the cable-less medium-speed route (STN protocol presets 53/54 on adapter pins 3/11). That route is untested on the reference car. Never use presets 53/54 with a bypass cable fitted.

A document recorded that the FS model is a variant aimed at other brands, and that MES's own supported-interface list names a different model of the same maker for certain special procedures. The reference car works with the FS for the reads described in this wiki.

## The OBD connector (SAE J1962) as used on this platform

| Pins | Use on the reference car |
|---|---|
| 6 and 14 | CAN-C, diagnostic/powertrain, 500 kbit/s. Reached with **no cable**. |
| 3 and 11 | CAN-IHS, body/comfort/infotainment, 125 kbit/s. Reached through the **blue A5** cable. |
| 12 and 13 | CAN-CH, chassis/ADAS/safety, 500 kbit/s. Reached through the **grey A6** cable. |
| 16 | Battery positive (adapter power). |
| 4 and 5 | Chassis and signal ground. |

Two hazards are recorded in the data (`cuore/live/buses.py`):

- **Pins 1 and 9.** Do not use interfaces with a short between pins 1 and 9 on Giulia or Stelvio; it drops the bus. Continuity-check any cable before fitting.
- **Pin 13 programming voltage.** The FS adapter has a feature, intended for another brand, that can drive pin 13 with a higher voltage. On this platform pin 13 is CAN-CH minus. Never issue any such command on this vehicle. Whether the adapter can be commanded to do so over serial is unverified, so it is treated as live.

## The two MES bypass cables

MultiEcuScan sells (and the project uses) two adapter cables that re-route the car's other buses onto the standard pins:

| Cable | Bus reached | Bit rate | Notes |
|---|---|---|---|
| **Blue A5** | CAN-IHS (pins 3/11) | 125 kbit/s | Open the bus only at 125 kbit/s. Listening works on the 11-bit route; UDS to body modules has not been answered yet (see [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]]). |
| **Grey A6** | CAN-CH (pins 12/13) | 500 kbit/s | Safety-relevant bus (brakes, airbag, steering assist). Any transmit needs explicit confirmation. |

The full catalogue of coloured cables (A1 to A6, the 3-pin lead and the SGW bypass), with a per-brand matrix, is on [[Adapter Cables|Adapter-Cables]]. That catalogue is an external reference, not a CUORE reading: only these two cables are driven live, and the page also repeats the wrong-bitrate and pins-1-and-9 warnings.

The cable is **declared**, not detected: you tell CUORE which cable is fitted, and changing the declaration clears every bus verification. A bus the declared cable does not reach is refused. One adapter has one CAN peripheral, so only one bus can be read at a time; the guided scan pauses for each swap ([[Guided Full Scan|Guided-Full-Scan]]). A second adapter permanently on a cable would remove the swap and is listed as an open hardware option.

## The Security Gateway

Giorgio cars from 2018 production onward can carry a Security Gateway module (SGW) between the OBD port and the vehicle networks. The project's documents record the following, with different confidence levels:

- **Observed on the reference car:** on CAN-C there is no broadcast traffic at all, in either 11-bit or 29-bit form; a passive listen hearing zero frames does not mean the bus is dead. Legislated OBD and UDS reads to known modules (engine, transmission, body, instrument cluster) work; a blind sweep of all 253 target addresses found nothing in 75.6 s. The gateway answers requests to modules it knows about and emits nothing unprompted. CUORE therefore verifies CAN-C with one active Mode 01 request instead of a listen.
- **Recorded in a document, unverified for this car:** fitment depends on production date, not model year; NAFTA Giulia/Stelvio production from February 2018 is stated to carry it. A trade source examined a 2018 Stelvio that had none. The module map lists SGW presence on the reference car as `UNVERIFIED`.
- **What exists to get past it:** third-party passive bypass modules, and the manufacturer's own authenticated service route. CUORE does not attempt either. The connectivity review decided that an SGW bypass or manufacturer-authentication equivalent is out of scope for a read-only diagnostic tool.

## One program on the port

A serial port opened by one program cannot be opened by another: the Windows serial API requires exclusive access. Port splitters do not fix this, because an ELM/STN adapter is a half-duplex, stateful, single-master device: commands interleave, replies reach both clients, and settings such as protocol and header are global.

CUORE's rules:

1. Before opening the adapter it asks the **MES interlock** whether MultiEcuScan is running and connected (process list plus the text of MES's own status label). If it is, the operation is refused unless the caller states that MES is on a different port.
2. A **lock file** keeps CUORE and the MCP server from opening the port at the same time.
3. Every operation opens the port, does its work and releases it. The one exception is the live-data poller, which holds one session for a whole run; while it runs, other live operations refuse.
4. No other script may open the adapter. See [[Safety Rules|Safety-Rules]].

The correct hand-off between tools: let the current operation finish (never interrupt a test mid-way), fully exit the other program, wait a second or two, then start the next.

Next: [[Vehicle Networks|Vehicle-Networks]].
