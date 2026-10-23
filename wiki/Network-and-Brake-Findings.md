# Network and Brake Findings

Many of the non-EVAP codes on the reference car are messages about **other modules' messages**. This page explains the pattern the 2026-10-20 review found around the body control module (BCM), the one low-voltage event on the brake module, what outside literature ranks as likely causes, and the tests that would settle it. Per-code detail is on [[Code Reviews|Code-Reviews]]. Statements are tagged **[E]** reading, **[I]** inference, **[O]** outside literature, as on [[Evidence Model|Evidence-Model]]. The source documents are [NETWORK_PATTERN_READINGS](https://github.com/dangelojohn/CUORE/blob/main/docs/research/NETWORK_PATTERN_READINGS_2026-10-20.md) and [NETWORK_PATTERN_LITERATURE](https://github.com/dangelojohn/CUORE/blob/main/docs/research/NETWORK_PATTERN_LITERATURE_2026-10-20.md).

## Reading the code texts

[E] MES prints, for the BCM, "Engine control (NCM) signal erratic" (U1713-2F) and "Brake system (NFR) signal erratic" (U1711-2F, U1712-2F). The first half names the sender the BCM is watching: NCM is the engine computer, NFR the brake module (legacy labels from older cars of the same group; [O] their use on this platform is inferred, and the scan tool's printed label is the only definition for this car). The suffix is the failure type: **87 missing message** (the expected message did not arrive in time), **86 signal invalid** (it arrived and failed a content check), **2F erratic** (intermittent). [O] These meanings come from a trade article and a page for another car in the group, not from SAE J2012-DA (paid), so they are paraphrase-grade. A lost message is 87, not 2F; an earlier project text that called U1713 "lost communication" was corrected.

## The BCM-centred cluster

[E] The BCM is the only module with complaints in **both directions**.

| Direction | Codes |
|---|---|
| BCM says the engine computer's messages are erratic | U1713-2F in the BCM (10 of 18 eight-module scans, 06-07 to 10-19; failing on 10-13, 10-19) |
| BCM says the brake module's messages are erratic | U1711-2F, U1712-2F in the BCM (6 scans, 06-07 to 09-25; always together; never without U1713) |
| Others say the BCM is missing or implausible | ABS U1700-87; transfer case U0422-86; keyless hub B1040-64 and U2054-87; cluster B102E-64 |

- U1711 and U1712 always appear and disappear together, but the three do **not** move as one: U1713 occurred alone in several scans, so the pair is a subset of U1713 episodes [E].
- The engine computer's own list **never** holds a network code [E]; the transfer case holds "engine computer missing" (U0100-87) in 6 of 10 U1713 scans and 1 of 8 others.
- The driver-assistance link code C141C tracks the brake pair (6 of 6), but the DASM and the BCM were always cleared in the same session, so joint removal is confounded [E]. The camera code C141B is independent of the cluster [E].
- [I] The common element is the BCM, but sender and receiver cannot be split because the complaints run both ways. A network, gateway or BCM supply or ground problem would give a two-way pattern; a single dead sender would not. **Not proven.**

### Return after clears

[E] BCM clears were followed by a return in 2.6 to over 8.9 days (11.0 and 10.0 days for the full trio on two occasions, 6.1 days and 2.6 days for U1713 alone; after the 09-29 clear it was absent at least 8 days 22 hours and back by 10-13; after the 10-14 clear, clean 10 hours later, back within 4 days 5 hours). The return time is not constant, which is why the proof of fix asks for 21 days.

## The 10.6 V event and the module voltages

[E] The one low-voltage reading in the whole corpus is in the ABS freeze frame of **U1700-87**: battery **10.6 V**, startups counter 14280, speed 0, pedal off, taken 2026-09-04. The engine computer stored its first EVAP code of 08-27 at startup 14281, one count later; the startup counter appears shared across modules [I]. So the 10.6 V moment sits just before an engine start, a supply-side observation, not a brake one. A low-voltage moment can plausibly set body and brake communication codes [I]; no BCM freeze frame exists to test it.

[E] Every other voltage on record is normal: the BCM's own supply reads (data identifier `1004`, formula unverified) were **14.4 V and 14.5 V** on 10-14 and 10-19, matching the voltage at the OBD port (14.0 to 14.5 V) within about 0.1 V, and the engine computer's records show 12.0 to 14.3 V. U1713 was failing at 14.4 to 14.5 V, so **a low supply is not needed for the code to be present at read time**. [I] Module voltages tracking the port voltage show no large drop between the port and the BCM at the times it was read, with the engine running and no load step; they say nothing about a dip during cranking or a load, which has never been logged.

## Timing of other codes

[E] Several codes first appeared in windows that held tool activity. The BCM, cluster and keyless codes of 10-13 and 10-14 (B1176, U1736, U1765, B10AA) were all present then and all absent on every read after the 10-14 clear, which looks like one cluster of events in the 5 days 11 hours between 10-08 and 10-13 [I]. A supply interruption would fit all of them but is not shown by any reading; the owner's battery-work question is unanswered. Separately, the radar and transfer-case codes first seen on 10-19 (U1702-87, U0422-86) fall in an interval with no module read that contains the **2026-10-14 night incident** on the chassis bus ([[Safety Rules|Safety-Rules]]) and the guided scan after it; they are classed probable tool artefacts, not proven. The other 10-19 codes (C1408, C141C) existed before it and cannot be blamed on it.

## Brakes and ESP-named codes

C104B-92 is told on [[Code Reviews|Code-Reviews]]: service-induced per the owner (pad inspection), pending a confirming ABS read. The rear pads are planned for replacement on 2026-10-23 (owner-attested); a new brake or ABS code after that job should be compared with the C104B-92 freeze frame, and only the ABS/EPB module is cleared, never the engine module. The codes that **name** the brake or ESP side elsewhere (C1408-86, U0418-86, U0428-86, U1960-83, U1711, U1712) are text about *received signals*, not hydraulic evidence. The ABS itself has not been read since 2026-09-04, apart from one silent attempt on 10-15 ([[Vehicle Networks|Vehicle-Networks]]). ESP-, DASM- and camera-named receiver codes are **downstream of the BCM cluster**, so the first useful action is a fresh read of the brake and steering modules in the same session as the BCM, not chasing the yaw sensor or the steering rack.

## What outside literature ranks as likely [O]

No bulletin, recall or forum thread was found that lists U1711, U1712, U1713, U1702, U1736, U1765, U0418, C1408, C1431, C1403 or C141B for a 2017 to 2019 Giulia or Stelvio; the lookups that could settle scope are VIN-gated. The ranking below is therefore an **inference from how closely each source's symptom pattern matches several modules flagging intermittent or invalid signals with a clean brake module**; no source gives a probability.

| Rank | Cause | Basis [O] | Confirming test |
|---|---|---|---|
| 1 | **BCM supply or ground** (fuse, feed, battery, battery sensor, ground strap) | Bulletin S1808000005 (no start with several modules not responding; inspect the BCM feeds including the stand-alone fuse and, on the Stelvio, fuse F82 in the rear power distribution); a battery-monitor bulletin after a software flash | Battery load test; cranking-voltage log; **voltage drop** on the BCM feeds and grounds under load, in the failing state |
| 2 | **Connector or terminal fault** (BCM, brake module, radar, camera) | Bulletin S1708000262 (intermittent CAN private or LIN codes: pushed-out or spread terminals) | **Wiggle test** with live data and a bus-error watch; pin-tension and visual check |
| 3 | **Water in the BCM or A-pillar connector** | **Recall 18V205**; Transport Canada recall 2018151 lists the 2018 Stelvio (water corrodes the connector; named effects are warning lights and loss of wipers, exterior lights, horn and turn signals) | VIN lookup; inspect the A-pillar connector and seal ([[Recalls and Campaigns|Recalls-and-Campaigns]]) |
| 4 | Configuration or software mismatch after earlier flashes | Bulletins 08-045-20 (2020 builds), S2018000004, 08-044-19 (build-date window, no cruise control) | Compare software and configuration levels; a dealer-tool step |
| 5 | CAN physical layer (wiring, terminators) | Generic ISO bus test: about 60 ohm between CAN-H and CAN-L with the ignition off | Resistance at the correct access point; the terminator locations and the port pins' position behind the gateway are **not found** |
| 6 | Security gateway fault | Bulletin S1708000246 (the gateway sets no code when it blocks aftermarket messages; with it not communicating every module shows red) | Topology view; the observed pattern is not what that document predicts for a gateway fault |
| 7 | Aftermarket device on the port | Same bulletin; an old forum case on another car | Repeat the scan with every device unplugged |
| 8 | Camera obstruction (C141B only) | Meaning of FTB 97 | Clean the windscreen patch |

Not supported by any source found: a brake-module or radar hardware failure as the root cause of the network codes (no code in the ABS apart from the single clean-cleared event, and no bulletin).

**A judgement, not a measurement.** The project's own rough estimate is that a **grounding or supply fault has perhaps a 20 percent likelihood** of being behind the cluster. It is a weighting offered for planning, not derived from any reading, and no outside source gives a probability; it should be dropped the first time a measurement says otherwise.

## The tests that discriminate

All read-only or meter-only; none clears a code.

1. **Battery and supply, free to cheap.** Battery at rest after 12 hours, during cranking and running; a **battery load test**; terminals. Rule-of-thumb figures (about 12.4 V or less at rest is weak; a cranking dip below about 9.6 V is poor; charging outside about 13.8 to 14.8 V is suspect) are generic, **not a Stelvio specification**.
2. **Voltage drop under load** across the BCM feeds, fuse F82, the stand-alone BCM fuse and the grounds, with the car in the failing state. Log the BCM voltage identifier and the battery sensor across key-off, crank and run; a sag at crank points at supply or network, a clean record at module-internal.
3. **Wiggle test** at the BCM, brake module, radar and camera connectors with live data on screen.
4. **Reciprocity snapshot.** In one key-on session while U1713 is active, read the BCM, brake module, engine computer, transfer case, cluster and keyless hub with full status bytes before any clear. All sides complaining points at the BCM transmit side, the gateway or the bus; only the BCM complaining points at its receive side; only the others complaining about the BCM points at the BCM as sender.
5. **Frame census** of the brake, engine and BCM frames at the port on the verified bit rate with the engine running: healthy frames at the port while the BCM still flags them means the receiver or its branch; missing, jittery or bad frames mean the sender or the bus. The listen-only decoder on [[Passive Chassis Decoding|Passive-Chassis-Decoding]] is a step toward this for the chassis bus.
6. **One quiet read** after at least three tool-free days, engine running: codes present are the car's; codes that appear only on session days are bystanders.
7. **Owner questions** (free): battery work or jump starts, aftermarket electrical devices, engine bay washed, windscreen replaced, any warning lamp since the 10-14 night, any dashboard message from the driver-assistance features. These are unanswered.

Proof that the cluster is resolved is the group proof on [[Code Reviews|Code-Reviews]]: none of the codes on three reads over at least 21 days, one taken under the conditions that showed them.

Related: [[Vehicle Networks|Vehicle-Networks]], [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].
