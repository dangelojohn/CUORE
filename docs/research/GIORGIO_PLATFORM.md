# Giorgio Platform (Giulia 952 / Stelvio 949, MY2017-2020) — Technical Reference

**Captured:** 2026-08-27. Sourced from GitHub REST API, NHTSA recalls + 371 complaint narratives, and vendor documentation. **Forums were unreachable** — §7 is correspondingly thin.

---

# 1. THE HEADLINE: your communication cascade has a known, documented cause

## Read the failure-type bytes first

Not one code in the cascade is a **component-internal** failure type (`49` internal electronic, `96` component internal, `4B` over-temperature). Every one is a **bus/message-integrity** type:

| FTB | Meaning | Your codes |
|---|---|---|
| `2F` | signal erratic | `U1711`, `U1712`, `U1713`, `U1716` |
| `86` | signal invalid | `C1403`, `C1408`, `C1431`, `C141C` |
| `87` | missing message | `U0100`, `U2054` |
| `64` | plausibility | `B1029`, `B102E`, `B1040` |
| `97` | component obstructed/blocked | `B1176` — **the one genuine component code** |

> **Every module in the cascade is complaining that messages it expected did not arrive, or arrived malformed. That is a power, ground or bus-integrity event — not eight modules failing at once.**

## #1 candidate — corroded engine/transmission-to-body ground strap
**CONFIRMED as a Giorgio failure mode. LIKELY your root cause. Not on the original candidate list.**

**13 independent NHTSA complaints**, all 2018-2019 Stelvio (9x MY2018) plus one 2018 Giulia, filed Dec 2023 - Aug 2026 — **5-8 years of vehicle age, exactly this car's cohort.**

> ODI **11629949**: *"Alfa Romeo Giulia (and Stelvio) models have an **exposed powertrain ground strap under the vehicle body**… prone to corrosion which causes the fine wire braid… to become brittle and break… further accelerated due to the **acute 90 degree bend**… When the ground strap fails… **alternate grounding paths may be sought by the current from the starting circuit**, [resulting in] substantial and expensive damage to other wiring and electrical components."*

> ODI **11664142** (2018 Stelvio): *"Ground wire to starter had corroded and broke… This also caused **all warning lights to come on the dash including steering, ABS**, and about four other warning lights."*

> ODI **11563485**: *"corroded main grounding wire going from the **transmission to the frame**… the path of least resistance was the smaller gauge wiring in the electrical harness **to include the ABS and starting/charging circuits** which melted."*

Dealer-diagnosed cases at **54,000 mi** (ODI 11754904) and **102,000 mi** (ODI 11682898).

**Why it fits precisely:** a high-resistance (not yet open) strap raises the powertrain modules' reference potential relative to body modules during any high-current event — cranking, cooling-fan step, ABS pump, EPS assist. CAN is differential but its transceivers have a **common-mode range** (~-12 V to +12 V, ISO 11898-2). Push chassis-vs-powertrain ground offset outside that window for milliseconds and **every module on the segment simultaneously logs erratic / invalid / missing-message faults, then recovers cleanly.** Which is exactly what happened.

**It also explains "cleared to SUCCESS and never came back"** — intermittent and load-dependent, not a dead module.

> **Action: voltage-drop test the transmission/engine-to-body strap and both front knuckle straps under load. Target < 0.1 V across each path. Inspect for corroded braid and the 90-degree bend.** This is a ~$200 part that prevents a $6,000-$9,000 harness replacement — multiple owners quoted exactly those figures. **There is no recall.**

⚠️ These are owner complaints, self-reported. But the count (13), tight model/year clustering, mechanism consistency, and repeated dealer attribution make this substantially stronger than forum noise.

## #2 — BCM water intrusion. **CONFIRMED — this is a recall on this exact car**

**NHTSA 18V205000 / FCA code U36**, 2018-03-29, **12,595 vehicles — all 2018 Alfa Romeo Stelvio.** That is essentially the entire MY2018 US population, so **this VIN is almost certainly in scope.**

> *"Water may leak into the **body control module and its connectors, causing corrosion**… can cause illumination of one or more malfunction indicator lamps, a loss of windshield wiper function, a loss of exterior lighting, a loss of horn function and/or unintended turn signal activation."*
> Remedy: *"install additional sealing protection."*

Companion **18V203000 / U34**, same population: water into the **liftgate wiring connectors**.

**The remedy was a sealing kit, not a redesign, and it demonstrably does not always hold** — ODI 11307971 had U36 performed 2018-05-09 and suffered BCM water intrusion again on 2019-12-16.

Intrusion path: **water runs down the front cowl near the fresh-air intake into the passenger footwell, where the BCM lives.**

**Why it fits:** the BCM is the **B-CAN ↔ C-CAN gateway**. Corroded connector pins produce exactly this bidirectional pattern — BCM reports peripherals erratic (`U1711/U1712/U1713/U1716-2F`) *and* peripherals report losing the BCM (`RFHUB U2054-87`, `IPC B102E-64`).

> **Action: pull the passenger kick panel. Check for staining, silt line, or green/white corrosion on the BCM connectors. Check cowl drains and the U36 kit's integrity. Confirm U36 and U34 were performed on this VIN.**

## #3 — The diagnostic session itself. **LIKELY a contributor, possibly the whole story**

Three mechanisms:

**(a) UDS session control silences normal broadcasts.** When a tester puts a module into extended/programming session (`$10 03`, `$10 02`), many FCA modules **stop or reduce normal application-layer transmissions**. Every subscriber then logs missing (`-87`) or erratic (`-2F`). A tool that walks module-by-module through a whole-vehicle scan does this *serially to every module on the bus*.

**(b) Re-pinning the DLC on a live bus.** Reaching Giorgio's other buses means unplugging and replugging the interface. MES publishes this warning, naming this car:
> **"DO NOT USE MODIFIED INTERFACES WITH SHORT CIRCUIT BETWEEN PINS 1 AND 9 ON … GIULIA, STELVIO …"**

**(c) A marginal SGW bypass dongle** is a physically inserted bus device; quality varies enormously.

> ### The decisive test, and it is cheap
> **Read extended DTC data (`DTC EX` in MES) on every code that returned. Check odometer, occurrence count and aging counter.**
> **If every code shares one odometer value and one occurrence, your scan made them.** Do this *before* clearing — clearing destroys the only evidence.

## #4 — Battery / IBS. **LIKELY as a general Giorgio issue, UNCERTAIN here**
23 of 371 complaints mention battery problems. But **only 1 in 371 mentions a battery sensor / IBS by name** — no evidence Giorgio IBS sensors fail at notable rates. Rank below the ground strap, which explains the *simultaneity* better. Still test battery, IBS connection and parasitic draw on a 140,600 km car.

## Recommended diagnostic order
1. **Read `DTC EX` on every returned code** — cheapest, most decisive.
2. **Voltage-drop test all grounds under load.**
3. **Passenger footwell / BCM connector inspection**; verify U36 and U34 on this VIN.
4. **Battery + IBS + parasitic draw.**
5. **Only then** consider a genuine module fault. **Do not replace anything on the strength of a `-2F`/`-87` cascade alone.**

---

# 2. The three-bus DLC map — CONFIRMED from vendor pinout diagrams

```
                    OBD-II DLC (SAE J1962)
  pin 6 / 14  -> BUS A  "diagnostic / powertrain"
  pin 3 / 11  -> BUS B  "body, comfort, infotainment"   (adapter A5, blue)
  pin 12 / 13 -> BUS C  "chassis, ADAS, safety"          (adapter A6, grey)
                             |
                    [ SGW (2018+) ] blocks writes, actuators, procedures, DTC clear
                             |
  === BUS A ===  ECM (IAW 10JA) · ZF 8HP TCM · ZF Gear Shift Module
                 Magna Q4 Transfer Case (DTCM) · Body Computer Marelli 949  <-- GATEWAY
                 PROXI Alignment (949) · IPC · RFHUB · Service Interval Reset
                             |
              +--------------+--------------+
  === BUS B (A5) ===              === BUS C (A6) ===
  TRW Climate Control             Continental ABS MK C1
  AlfaConnect Radio/Nav           ZF Electric Steering (EPS)
  Amplifier Ask/Beats             Bosch Airbag (ORC)
  ESEM · Multimedia knob          Steering Lock TRW
  CSWM / CRSM comfort seats       DASM radar --private CAN-- HALF camera
  Blind Spot Sensors L+R          Torque Vectoring Module
  Power Liftgate (PLGM)           Adaptive headlights · Parking control
```

**Why this is decisive:** MES requires you to *physically move CAN-H/CAN-L to different DLC pins* to reach Bus B and Bus C. That is only necessary if they are **electrically separate CAN pairs at the connector**. Direct published evidence, not inference.

Independently corroborated from the other end of the car by the comma.ai port author: *"the CAN topology seems to keep a lot of powertrain stuff away from the camera… I haven't been able to locate a CC button message or even a driver gas-press signal."*

**The BCM is the gateway.** A BCM that browns out, resets, or has corroded connectors produces faults in **both directions simultaneously**. Your fault set is a textbook BCM-gateway-disturbance signature — which does not prove the BCM is bad, only that it stopped gatewaying for a moment.

**`C141C` — the DASM↔HALF private CAN.** DASM = Bosch radar (front bumper); HALF = Bosch **MFK2** forward camera (windshield). They share a direct point-to-point bus that does not transit the vehicle network, running windshield header → A-pillar → front bumper. FTB `-86` (invalid) means the link delivered malformed data — consistent with the transient event. A broken link would give `-87` and would not self-clear.

---

# 3. The Q4 transfer case and your `U0100-87`

MES capability line, verbatim: `Magna Q4 Transfer Case |INFO|DTC|DTC EX|PRM|ADJ| ELM (no adapter)`

| Function | Available | Meaning |
|---|:-:|---|
| `INFO` / `DTC` / `DTC EX` / `PRM` | yes | identification, codes, **extended detail**, live parameters |
| `ACT` | **no** | **you cannot command the clutch/actuator from MES** |
| `ADJ` | yes | an adjustment procedure exists — **MES does not document what it is** |

> **`U0100-87` is LIKELY a bystander code, not a transfer case fault.** `U0100` is "lost communication with ECM/PCM", and the DTCM and ECM are **on the same bus segment (Bus A)**. A missing-message code from the DTCM means *the ECM's frames stopped arriving on Bus A* — exactly what happens when a scan tool puts the ECM into a diagnostic session, or when the powertrain ground reference shifts. **It does not implicate the transfer case at all.** Combined with it clearing and not returning, and no Q4-specific component code, do not pursue the transfer case on this evidence.

**Confirmed negative:** **no Q4/AWD recall exists for 2017-2020 Giulia/Stelvio.**

**Could not verify:** actuator architecture, fluid spec/capacity/interval, part numbers, whether replacement needs a calibration, clutch shudder prevalence, whether Proxi alignment is required after DTCM replacement.

---

# 4. The opendbc Giorgio CAN database

**Raw file (verified, 9,471 bytes, 243 lines):**
`https://raw.githubusercontent.com/commaai/opendbc/master/opendbc/dbc/fca_giorgio.dbc`

**Provenance:** one commit, 2024-09-18, by Jason Young (`jyoung8607`, maintainer of comma's VW port), PR #1250 — *"Checkpoint / initial DBC, **working and driving on Alfa Romeo Stelvio and Giulia**."* **Never modified since.** Genuine reverse-engineering validated on moving cars, but a ~2-year-old first pass — roughly 40% of signals are still named `NEW_SIGNAL_n`.

## Most useful decoded messages

| Addr | Name | Key signals |
|---|---|---|
| `0x0DE` | EPS_1 | `STEERING_ANGLE` (0.1°, offset -716.8), `STEERING_RATE` |
| `0x0EE` | ABS_1 | `WHEEL_SPEED_FL/FR/RL/RR` — 13-bit each, 0.017 m/s, **100 Hz** |
| **`0x0F1`** | — | **`MAYBE_VOLTAGE`** (10-bit, x0.02 -> 0-20.46 V) |
| `0x0FA` | ABS_3 | `BRAKE_PEDAL_SWITCH`, `BRAKE_PRESSURE_THRESHOLD`, **100 Hz** |
| `0x0FC` | ENGINE_1 | `ENGINE_RPM`, `ACCEL_PEDAL`, `REVERSE` |
| `0x0FE` | ABS_2 | `LONG_ACCEL`, `LATERAL_ACCEL`, `YAW_RATE` (filtered) |
| `0x101` | ABS_6 | `VEHICLE_SPEED`, `BRAKE_PRESSURE_1/2` |
| `0x106` | EPS_2 | `DRIVER_TORQUE`, **`LKA_STATUS`**, **`LKA_FAULT`** |
| `0x10E` | ABS_7 | `LONG_ACCEL_RAW`, `LATERAL_ACCEL_RAW`, `YAW_RATE_RAW` — **raw twins of ABS_2** |
| `0x122` | EPS_3 | `EPS_TORQUE`, **100 Hz** |
| `0x5A2` | ACC_1 | `HUD_SPEED`, `TARGET_SPEED`, **`CRUISE_STATUS`**, 12 Hz |

## Checksum / counter algorithm — not available anywhere else
- **Checksum = last byte.** **Counter = low nibble (`& 0x0F`) of the second-to-last byte.**
- CRC-8, **polynomial 0x2F** (SAE J1850 poly), **init 0x00**, over all bytes except the last, table-driven.
- **Final XOR = 0x00** for every message except `0xFF`, which uses `0xFF`.
- ⚠️ Source carries `// TODO: bruteforce final XORs` and the safety layer sets `.ignore_checksum = true` on ABS_1/ABS_3/EPS_3/ACC_1. **Treat as LIKELY-correct-but-incomplete.**

Bus layout: **everything lives on the bus at the forward camera connector** (bus 0 = car side, bus 2 = camera side). Corresponds to **Bus C** plus gatewayed engine/BCM summary frames.

## What it buys you, and what it does not

**Buys:** sensor validation without a scope — yaw/lateral accel (filtered `ABS_2` **vs** raw `ABS_7` is a free plausibility check), steering angle and rate, driver torque vs EPS motor torque, individual wheel speeds and direction, brake pressure. Maps **directly** onto DASM codes `C1431` (yaw), `C1403` (EPS), `C1408` (ESP). Loads into SavvyCAN, `cantools`, python-can, Wireshark.

**`0x0F1.MAYBE_VOLTAGE`** is almost certainly system voltage at ~100 Hz. **Validate it once against a DVOM, then trust it** — it gives you a high-rate battery-voltage trace, which is exactly the instrument for the ground-strap question. **A ground or battery problem shows up here as sag or noise that a handheld meter averages away.**

**Does not buy:** no transfer case / DTCM, no ZF 8HP, no IPC, no BCM body traffic. **Zero UDS/diagnostic content** — it decodes *broadcast* traffic only and will never read `U1711` or `U0100`. Gear position, driver gas, cruise buttons, seatbelt and BSM are explicitly unlocated.

⚠️ Scale factors marked "TBD"/"estimated" in the DBC (ABS_2 accel and yaw) are the author's estimates — use for **relative comparison, not absolute calibration.**

---

# 5. Failure patterns by mileage

NHTSA complaint baseline (2017-2020 Giulia + Stelvio, n=371): **2018 Stelvio 127** · 2018 Giulia 85 · 2017 Giulia 65 · 2019 Giulia 43 · 2019 Stelvio 36 · 2020 Stelvio 7. **MY2018 is the problem year by a wide margin.**

Keyword frequency: fuel pump **79** · stalling 56 · module 40 · warning lights 31 · battery 23 · limp mode 23 · steering 20 · **ground 14** · wiring 14 · sunroof 14 · transmission 12 · body control 8 · water leak 4 · instrument cluster 3 · EVAP 3 · oil consumption 2 · **transfer case 0** · **timing chain 0**.

⚠️ NHTSA is a **safety** database of unverified owner reports. Good evidence of symptom prevalence, useless for root cause. Non-safety items are **structurally under-represented** — zero transfer-case complaints does **not** mean they don't fail.

## Recalls covering this platform (19 total; the ones that matter)

| Campaign | Code | Population | Issue |
|---|---|---:|---|
| **25V586000** | **93C** | **53,849** | **Fuel pump / fuel delivery module.** 2017-19 Giulia + **2018-19 Stelvio**. Interim letters 2025-10-07; **final remedy anticipated July 2026.** NHTSA appended a rebuke that FCA *"may have been aware… more than five business days before filing"* |
| **18V205000** | **U36** | **12,595** | **BCM water intrusion — all MY2018 Stelvio** |
| 18V203000 | U34 | 12,595 | Liftgate connector water intrusion |
| 18V636000 | UA4 | 34,357 | 2.0L misfire -> cat overheat -> harness heat damage. Remedy = ECM software |
| 19V551000 | V84 | 21,914 | BCM misreports fuel level -> stall. **BCM software update** |
| 24V510000 | — | 337,128 | Front airbag connection, 2017-20 Giulia+Stelvio |
| 19V148000 | — | 19,114 | Blind-spot module / ACC software |
| 18V147000 | — | 1,505 | Windshield wiper motor, MY2018 Stelvio |

**Fuel pump signature DTCs from complaint narratives: `P008A` (5 mentions) and `P0087` (4)** — fuel rail/system pressure too low. Also `P0299`, `P0191`, `P062A`, misfires `P0300-P0303`. Typical presentation: sudden power loss, no restart, often preceded by *"Service Electronic Throttle Control"* messages.

## Assessment of the original "known-bad list"

| Item | Verdict |
|---|---|
| Instrument cluster | **Weakly supported** — 3 complaints |
| Body computer | **Strongly supported** — but the mode is **water/corrosion and software**, not spontaneous death. Two recalls |
| EVAP canister | **Unconfirmed** — 3 complaints |
| Fuel pump / 25V586 / 93C | **Fully confirmed.** The single biggest platform issue |
| Q4 transfer case actuator | **Could not verify at all.** Zero NHTSA signal (expected) |
| Valve-train / timing | **Could not verify.** Zero timing-chain mentions in 371 |
| Oil consumption | **Weakly supported** — 2 complaints |
| **MISSING: ground strap corrosion** | **Add it. On a 140,600 km 2018 Stelvio it is arguably the #1 thing to inspect.** |

---

# 6. Sensor validation without a scope

With a CAN interface at the camera connector (or Bus C at pins 12/13) and the DBC in SavvyCAN/`cantools`:

| Suspect | Cross-check | Method |
|---|---|---|
| **Yaw / lateral accel** (`C1431`) | `ABS_2` filtered **vs** `ABS_7` raw | Same sensor cluster, two messages. Stationary, level ground: both ~0. Divergence = sensor or its supply |
| **Steering angle** | `EPS_1.STEERING_ANGLE` | Straight-ahead ~0.0°, full lock ±~540°. `STEERING_RATE` must be the derivative |
| **EPS** (`C1403`) | `EPS_2.DRIVER_TORQUE` vs `EPS_3.EPS_TORQUE` vs `LKA_FAULT` | Hands off: driver torque ~0. Apply steady torque: EPS torque follows with assist |
| **Wheel speeds** | `ABS_1` + `ABS_5.ACTIVE_*`, `FORWARD/REVERSE` | Roll slowly; all four track within a few counts. Dropout with `ACTIVE` still set = wiring, not sensor. **Front wheel-well ABS wiring is a documented corrosion point** |
| **Brake** (`U1711/U1712`) | `ABS_3.BRAKE_PEDAL_SWITCH` vs `ABS_4/ABS_6` pressure | Switch and pressure must agree — classic brake-switch fault, visible with no wiring access |
| **The cascade itself** | **`0x0F1.MAYBE_VOLTAGE`** | Validate against DVOM once, then log at 100 Hz while cranking and cycling ABS pump / fan / EPS. **Highest-value single measurement for this problem** |

## Professional discipline
1. **Never chase a `-2F`/`-86`/`-87` cascade as component faults.** Find the common-mode cause: power, ground, gateway, or your own tool.
2. **Always pull `DTC EX` before clearing.** Clearing destroys the only evidence.
3. **Scan discipline:** connect once, known-good interface, fully charged battery or proper supply (not a trickle charger). Note odometer before and after. If codes appear only after your first scan, suspect your scan.
4. **The one genuine code wins.** `B1176-97` is a real component code — diagnose the window regulator; treat the rest as one event.

---

# 7. Verified resources

| Resource | URL |
|---|---|
| **opendbc Giorgio DBC** | `raw.githubusercontent.com/commaai/opendbc/master/opendbc/dbc/fca_giorgio.dbc` |
| opendbc port PR (open draft) | `github.com/commaai/opendbc/pull/1251` |
| Original RE discussion | `github.com/commaai/openpilot/pull/32898` |
| **MES coverage matrix** | `multiecuscan.net/SupportedVehiclesList.aspx` — best free architecture document found |
| MES adapter pinouts | `multiecuscan.net/images/OBDAdapter5.png` and `OBDAdapter6.png` |
| MES per-VIN support check | `multiecuscan.net/VehicleSupportCheck.aspx` |
| AlfaOBD supported vehicles | `alfaobd.com/supported_cars.html` |
| **NHTSA recalls API** | `api.nhtsa.gov/recalls/recallsByVehicle?make=alfa%20romeo&model=stelvio&modelYear=2018` |
| **NHTSA complaints API** | `api.nhtsa.gov/complaints/complaintsByVehicle?make=alfa%20romeo&model=stelvio&modelYear=2018` |

> **The two NHTSA APIs deserve a specific recommendation:** free, unauthenticated, complete narrative text, far more useful for pattern-finding than the consumer website. Substituting make/model/year works for any vehicle.

**Verified negative results:** the AlfaOBD help PDF contains **zero** Giulia/Stelvio- or Proxi-specific content. `fca_giorgio.dbc` is the **only** Giorgio artifact in mainline opendbc. **No Q4/AWD recall exists** for 2017-2020. **No recall exists for the ground strap**, despite 13 complaints describing fire risk.

**Could not verify:** any FCA TSB (NHTSA's TSB API is not public); an authoritative FTB table (`-64` unresolved); most of the Q4 section; the ground strap's Mopar part number; whether Proxi is required after DTCM replacement; wiTECH licensing and cost; techauthority.com contents; all forum quality assessment.

**Skepticism note that the data itself illustrates:** ODI 11363581 blames repeated fuel-system failures on *"a lot of water in the [fuel] system"* from a gas station. Given recall 25V586, the far likelier cause is the recalled pump. **The owner's symptom was real; the owner's explanation was wrong.** That is the failure mode of forum content in miniature — symptom reports aggregate well, root-cause claims do not.
