# ZF 8HP50 / 850RE — OEM Service Data (Alfa Romeo Stelvio)

**Captured:** 2026-08-27. Sourced from FCA/Alfa service information for the 2018 Stelvio, ZF Aftermarket doc **1087.754.107c** ("Oil Filling Specification 8HP | 8P", 05.02.2026), BMW of North America G30 service info, GEARS and Transmission Digest.

> ⚠️ **Provenance caveat.** Much of the FCA text was reached via `lemon-manuals.la`, an **unauthorised mirror of Mitchell1 OEM data**. The content is genuine OEM text (it carries "Courtesy of CHRYSLER GROUP, LLC" attributions throughout), but for any commercially published work cite the underlying FCA/Alfa service information rather than the mirror.

---

# 1. ⚠️ The fill temperature window — the common number is WRONG

## ZF doc 1087.754.107c, Table 1, p.6

| Variant | Min | Max |
|---|---|---|
| **General — RWD / AWD / basic transmission 8HPxxA** | **30 °C** | **50 °C** |
| All-wheel distributor transmission and differential, 8HPxxAxx | **30 °C** | **50 °C** |
| Hybrid — 8P70H / 8P75(X)PH | 40 °C | 50 °C |
| BMW | 40 °C | 50 °C |
| 8HP70L / Iveco | 30 °C | 40 °C |
| BeGas / Marshall Engines 8HP70 | 30 °C | 40 °C |
| 8HP76X / JLR AJ20 (P6, D6) | **55 °C** | **60 °C** |
| 8HP70 / Maserati | **50 °C** | **60 °C** |

> **The general 8HP window is 30–50 °C, not 30–40 °C.** The widely repeated "30–40 °C" is the **Iveco/BeGas** row, not the general one.

**Independently confirmed by the FCA/Alfa OEM procedure for this exact vehicle:**
> *"verify that the transmission fluid temperature is below 30 °C (86 °F)"* to start, and *"A full transmission will have fluid at the fill hole with the transmission between **30 °C (86 °F) and 50 °C (122 °F)**. Do not over fill."*

**Outliers commonly missed:** JLR AJ20 (8HP76X) at **55–60 °C**; Maserati 8HP70 at **50–60 °C**.

⚠️ **Do not treat rows 5–6 as authoritative pairings** — the bottom five rows are **mis-flowed in ZF's own PDF**, with manufacturer and model names straddling row borders. Geometry and rendering both confirm this is how the document prints. The BMW = 40–50 °C row is unambiguous; the 8HP70L/Iveco pairing is not.

## Level-check sequence

**ZF:** engine running, P selected, 2000 rpm for 30 s, return to idle, cycle P-R-D-1-2 with ≥10 s dwell each, back to P, then check temperature and open the plug.

**FCA (equivalent, different order):** fill first, then R 5 s → D 5 s → accelerate to 2nd 5 s → N at 2000 rpm 5 s → P.

**With auxiliary coolers fitted**, ZF requires raising temperature **above 75 °C** and letting it fall back into the window, to purge the cooler circuit.

**4th-generation 8HP can only be level-checked and filled with an OEM test device running a dedicated routine** — no manual plug procedure exists (ZF §5).

## Capacities and fluid
- **Overhaul dry fill: 9 L (9.5 qt)**, poured through the side plug with the unit tipped, before installation. **+0.7 L if the cooler was replaced.**
- ⚠️ *"A unique transmission fluid has been developed for this transmission. This fluid is **NOT compatible with ATF+4** or any other current FCA US LLC transmission fluid."*
- ⚠️ *"Oil dye is **not** required to find leaks in the 8HP… The oil dye can cause shift quality issues and is not recommended. The 8HP fluid has illuminance that is visible under a black light."*
- Oil pan and filter are an **integrated assembly, not separately serviceable**. 13 bolts at **10 N·m (89 in-lb)**. Pan gasket is reusable if undamaged.
- **BMW torques:** mechatronics-to-transmission M6×59/M6×20 **8 N·m, replace screws**, sequence 1→17; output rpm sensor **4 N·m + 12°**; pan M6 **10 N·m** sequence 1→13, **pan must be replaced each time it is released**; drain plug M18 **8 N·m**.

---

# 2. ⚠️ Major DTC corrections

## There is no P0741 on the 8HP
The complete DTC index for both the **8HP50/850RE (209 codes)** and the **8HP75** contains **no P0741, P0740 or P0742**. The functional equivalent:

**`P1DB7-00` — TORQUE CONVERTER CLUTCH PERFORMANCE.** Set when *"the difference between the actual slip and target slip of the TCC is greater than a calibrated threshold for an amount of time."* Monitored when TCC closed or in closed-loop mode, calculated TCC pressure above threshold, engine torque below threshold.
**Default action:** MIL first trip; *"the TCM will limit the current to the TCC solenoid to 50 mA. The TCC will be open."*
Circuit faults are **P2761–P2764**.

> **Do not publish a P0741 detection threshold for 8HP — the code does not exist there.**

## There is no P0730 and no P0736
Per-gear ratio codes are **non-contiguous**:

| Gear | 1 | 2 | 3 | 4 | 5 | **6** | **7** | **8** |
|---|---|---|---|---|---|---|---|---|
| Code | P0731 | P0732 | P0733 | P0734 | P0735 | **P0729** | **P076F** | **P07D9** |

## ⭐ Clutch-resolved ratio faults — the genuinely valuable part
The 8HP does not just report "ratio error" — it **infers which clutch is slipping** from which gears fail:

- **`P1D8F`–`P1D93`** — Incorrect Gear Ratio, **Clutch 1 … Clutch 5 Defective**
- **`P1D96`–`P1D9F`** — clutch **pairs**: A|B, A|D, B|D, B|E, C|D, A|E, A|C, B|C, C|E, D|E
- **`P1DA0`–`P1DA8`** — clutch **triplets**: A/B/C, A/B/E, B/C/E, B/D/E, B/C/D, C/D/E, A/C/D, A/D/E, A/B/D
- `P1D95` — TCM Clutch Failure **Undetermined**
- `P1DB4` — during gear engagement or in gear · `P1DB5` — during shift · `P1DEB` — incorrect gear **displayed**

## The failsafe gear is an adaptive ladder, not fixed 6th
> *"After a calibrated number of failure symptoms are detected, a DTC is stored and the TCM commands a calibrated default gear. This gear is monitored as well and if a failure is detected for this gear, an alternative default gear is engaged and so on… This logic will detect a damaged clutch and to finally select an alternative gear that consists of a combination of clutches in which the damaged clutch is not involved."*

## ⭐ P1731 — the only hard slip threshold FCA publishes anywhere
**`P1731` "Incorrect Gear Engaged"** sets when, with a gear engaged, any of:
- actual (calculated) gear differs from target gear
- **turbine slip (difference between actual and calculated turbine speeds) is greater than 300 RPM**
- calculated transmission ratio above a calibrated value
- during a downshift, actual gear > target gear (exception: actual 1st / target 2nd)

Monitored when engine speed **> 450 RPM** and vehicle speed **> 10 km/h**, with no ISS, ESM or ABS DTCs set. Default: MIL first trip, **limp-in**, special shift modes and stop/start disabled.

---

# 3. What the sensors actually are

## Three temperature sensors, only one readable
> *"The transmission monitoring system uses three temperature sensors."*

- One **2-wire NTC thermistor in the oil sump** — the only one on a scan tool, exposed as **"Oil Temperature Sensor"**. Used for transmission *control*.
- **Two more embedded on the TCM printed circuit board**, in separate areas. **Cannot be monitored with a scan tool**, cannot be serviced separately. Used for over-temperature shutdown and rationality.
- **MIL illuminates only when more than one fails.** With a single failure the TCM runs on the other two, and the manual explicitly says **do not perform temperature-sensor repairs.**

**Sump sensor resistance (for bench checks):**

| Temp | Resistance |
|---|---|
| −30 °C | 37,400 – 50,600 Ω |
| 10 °C | 5,810 – 7,100 Ω |
| 110 °C | 231 – 263 Ω |
| 145 °C | 105 – 117 Ω |

**Clutch temperature is modelled, not measured.** `P1DC7/P1DC8/P1DC9` derive from input/output speed, current and target gear, and calculated clutch pressure. *"No repair action is required. This fault is only used to initiate a calibration strategy."*

## ⭐ Line pressure is COMMANDED, not measured
The complete sensor complement inside the TCMA is: **input speed, output speed, park position, sump thermistor, and two TCM-internal PCB temperature sensors.** **There is no pressure transducer anywhere in the hydraulic circuit.**

Line pressure is *commanded* by the Line Pressure Solenoid (P0960–P0963). The feedback loop is **solenoid current, temperature-compensated**:
> *"the TCM monitoring software uses a PWM feedback signal generated by the current regulator in the output stage… the TCM software calculates the actual current dependent on the PWM feedback signal, the output stage power supply voltage and the actual transmission oil temperature."*

> **So any "line pressure" PID on an 8HP scan tool is a commanded/modelled figure, not a measured pressure. Treat published "normal line pressure" tables for 8HP with suspicion.**

*Torque converter circuit pressures are specified: retention valve TCH1-V holds a minimum **0.35 bar (5 psi)** with TCC open; with TCC applied, TCH2-V holds **1.0 bar (14.5 psi)**.*

## Speed sensors
Both **Hall-effect**. **ISS reads input shaft speed from the magnetic ring on the P2 carrier**; **OSS reads output shaft speed from the P4 carrier**. Both integral to the TCMA, not individually serviceable. If OSS is unavailable, output speed is calculated from the **wheel-speed CAN signal** — with a dedicated correlation code **P215C**.

---

# 4. Clutch fill adaptation — the four PIDs and their real ranges

Per clutch (A–E), the scan tool exposes:

| Label | OEM definition |
|---|---|
| **Fast Filling Counter** | number of Clutch **Filling Pressure** adaptations performed — the first learned values on a new transmission or after a reset |
| **Filling Counter** | number of Clutch **Filling Time** adaptations performed |
| **Filling Pressure** | learned pressure; changes over transmission life from build variation then clutch wear |
| **Filling Time** | learned time; same |

**Healthy counter range: 5 to 12 counts per clutch** — `CONFIRMED` by two sources (OEM manual and GEARS body text):
> *"You will need to allow 5 to 12 fast filling counts per clutch to properly learn the clutch adaptations. If the shift quality is sufficient after 5 counts, no further adaptation learns for that clutch are necessary."*

⚠️ **Correction:** figures circulating as *"filling counter minimum 2"* and *"fast filling counter minimum 4"* **conflict with both** the OEM manual and GEARS, which both say 5–12. Drop them.

⚠️ **Could not corroborate** the health ranges **−300 to +600 mbar** (filling pressure) and **−120 to +120 ms** (filling time). These appear only in GEARS figure images. **The FCA OEM manual publishes no numeric health range for these at all** — it only describes behaviour. Single-source, unverified.

**Useful framing (consistent with OEM definitions):** adaptation ≈ fuel trim. Counters = correction *activity*; values = where it *landed*. **Counters climbing while values move = the system is chasing a fault.**

---

# 5. ⚠️ Adaptations are NOT lost on battery disconnect

From **P062F (Internal Control Module EEPROM Error)**:
> *"The EEPROM includes all data that can change from transmission to transmission but has to be stored in **non-volatile memory**… The physical EEPROM emulation memory in flash is sub-divided into several sector groups… To always ensure a valid backup of the EEPROM data, at least 2 non-defective sector groups are needed. Each sector group is checksum protected and the validity of the checksum is verified before reading and after writing the data."*

> **The persistent forum claim that pulling the battery resets ZF 8HP adaptations has no support in OEM documentation and is contradicted by it.** Resetting requires a scan-tool **"RESET ADAPTIVE VALUES"** routine.

## When a relearn IS required
- **Fast Filling Adaptation** — when the TCM, TCMA or transmission assembly has been replaced, or adaptations were reset. **Must be done before Standard Clutch Filling Adaptation.**
- **Standard Clutch Filling Adaptation** — when a transmission internal component, **torque converter**, TCM, TCMA or transmission has been replaced, or adaptations were reset; also when the car may not have been driven in a way that encourages learning.
- ✅ **Not required after a re-flash alone:** *"This procedure does not need to be performed if the existing TCM or TCMA is re-flashed and that was the only repair performed."*
- ✅ **Not listed as a trigger:** a routine fluid-and-filter change.

> ⚠️ **The most commonly violated rule in the field:** *"Performing a reset of the Transmission Adaptation values does **not** automatically trigger the TCM to relearn… If a reset is performed, **both** procedures must be performed to restore optimal shift quality. **Do not reset these values unless specifically instructed to do so.**"*
> Resetting adaptations and handing the car back leaves it **worse** than before.

---

# 6. Quick Learn / STADA

The routine is **"QUICK LEARN"** or **"STATIC ADAPTATION (STADA)"**, with a separate **"RESET ADAPTIVE VALUES"**.

> **It is not "Transmission Clutch Volume Learn".** CVI is the older Chrysler A604/RFE concept and does **not** apply to the 8HP — GEARS makes exactly this point: the CVI philosophy was *replaced*, not carried over.

**Conditions:**
- Transmission fluid **at least 55 °C (131 °F)** (two-source confirmed)
- Drive briefly first so **all clutches have engaged at least twice** — this purges air from the apply circuits
- Engine running throughout
- Run **RESET ADAPTIVE VALUES**, then **QUICK LEARN**
- Takes **2–5 minutes**; scan tool must be at the newest revision

**Quick Learn is not sufficient on its own.** If shift quality is not corrected, the full TCM adaptation procedures must follow. GEARS: *"What Quick Learn does not do is fully adapt the transmission, and it most certainly does not replace road testing."*

---

# 7. The adaptation drive cycle — exact numbers

## Fast Filling Adaptation (learns *pressure*, during the shift)
Erase DTCs. Display Oil Temperature, Torque, Turbine (Input) Speed, and per-clutch Filling Counter.
- Oil temperature **above 30 °C**; valid band **30–100 °C**
- Upshifts through all gears at **light-medium throttle**, **input 1,250–2,000 rpm**, **torque 100–150 N·m**
- Then release throttle to **0 %** and coast for a **6-5 downshift** — the only way B clutch adapts: **torque −60 to −40 N·m**, **input 750–1,100 rpm**
- Repeat until **Filling Counters reach 10** per clutch
- **Smooth road required** — the TCM aborts on rough road

### Which shift adapts which clutch

| Clutch | Adapting shift | Condition |
|---|---|---|
| A | **6-7** | highway, above **80 km/h (50 mph)** |
| B | **6-5** | coasting, throttle 0 % |
| C | **2-3 and 4-5** | light-medium throttle |
| D | **3-4** | light-medium throttle |
| E | **1-2 and 5-6** | light-medium throttle |

## Standard Clutch Filling Adaptation (learns *time*, in steady state)
Note: *"The TCM learns the Standard Clutch Filling Adaptation values when the applicable clutch is **not applied**."*
Oil temperature **above 50 °C**; aborts **above 100 °C**. Hold gears manually. **1st, 2nd and 5th require no standard adaptation.**

| Clutch | Hold gear | Speed | Input speed | Torque |
|---|---|---|---|---|
| **D** | 3rd | 32–56 km/h | 950–1750 rpm | 25–180 N·m |
| **C** | 4th | 32–56 km/h | 950–1750 rpm | 25–120 N·m |
| **A** | 6th | 73–81 km/h | 950–1750 rpm | 50–120 N·m |
| **B** | 7th | 73–81 km/h | 950–1750 rpm | 50–120 N·m |
| **E** | 7th | 73–81 km/h | 950–1750 rpm | 50–120 N·m |

Repeat until Fast Filling Counters increment by **at least 5**; up to **12** may be necessary.

## ⭐ Diagnosing one specific bad shift
Identify which clutches apply and release on that shift from the application chart, then look up the **steady-state gear in which each of those clutches adapts.**
OEM worked example: *"if a rough 2-1 downshift is noted, note that clutch C and clutch E are applying and releasing… clutch C and clutch E require the adaptation procedure performed in 4th and 7th gear."*

## Post-repair Transmission Verification Test
Erase TCM + ESM + ABS + PCM DTCs · parking brake on · warm to **43 °C (110 °F)** · check leaks and level · perform TCM adaptation if internals or TCM were touched · road test **15–20 upshifts through all gears, 0 to 72 km/h, constant throttle 20–25 degrees**, plus several **kickdowns to 1st from below 40 km/h** · re-read DTCs.

---

# 8. TCM / mechatronic replacement — programming and coding required

- *"New Transmission Control Modules are supplied with **generic software**. When replacing a TCM, it must be programmed with vehicle specific software."* Enforced by **`P1DC6` "TCM Not Programmed"** → immediate MIL, **limp-in**.
- **VIN write required** — **`P0610`**: *"The VIN stored in the TCM is not equal to the VIN received via CAN."* → MIL first trip + limp-in. Also `U3002-00`.
- **Vehicle configuration / PROXI alignment required** — **`P1500`**: *"The vehicle configuration codes stored in the TCM are not equal to the vehicle configuration codes received via CAN from the Body Control Module."* → limp-in, and the TCM will not request positive torque interventions.
- ⭐ **Hardware/software matching is enforced** — **`P167A` "Calibration Mismatch"**: detects whether the programmed TCM software matches the **Hydraulic Identification Number stored in the TCM EEPROM, written during manufacture of the valve body by the transmission supplier.** → limp-in.
- Procedure: battery charger on, **10–16 V**, ambient **0–60 °C**, selector in PARK → download flash file → program → run the **"Gearbox Replacement"** routine → Transmission Verification Test.

> **What this means for "cloning":** the mechatronic carries a **hardware identity burned in at manufacture**. A donor unit cannot simply be bolted in and left alone. Cloning here means transferring the *vehicle-side* identity — VIN, configuration/PROXI, calibration — onto the replacement, not copying the hardware ID.

**BMW:** the G30 mechatronics procedure opens with *"Load specific data status with the diagnostic system using an appropriate scan tool."* BMW labour operations are titled *"Replace mechatronics (after vehicle diagnosis) **(without programming/encoding)**"* — confirming programming is required and billed separately. Designations: GA8HP50Z, GA8HP51Z, GA8HP75Z, GA8HP76Z, GA8HP95Z.
⚠️ **Could not verify** BMW EGS ISN / immobiliser alignment or BMW's own ISTA oil-level window. **Do not assert BMW ISN behaviour from this.**

---

# 9. Failsafe behaviour and the mechanism behind it

Ratio-code default action, verbatim: MIL immediately · **limp-in** · *"the TCM will limit the current to the TCC solenoid to **50 mA**. The TCC will be open."* · Sport/Winter/Manual disabled · **"Shift adaptation functions will be disabled."** · stop/start disabled.

> ⚠️ **"Shift adaptation functions will be disabled" also appears on `P1DB1` (TCM System Voltage Excessively Low).** Practically: **a weak battery or bad TCM supply silently stops adaptation.**

Below that threshold, *"the TCM will not supply power to the solenoid valves and pressure regulators."*

## ⭐ Why the 8HP behaves predictably when it loses electrical control
> *"The **yellow** EDS have a **rising** characteristic curve; there is no control pressure when they are not powered. The **blue** EDS have a **falling** characteristic curve; the maximum control pressure is obtained when the solenoid valves are not powered."*

This is the single most useful fact for reasoning about de-energised state, and it is rarely stated in aftermarket material.

*(GEARS' claim that "line pressure defaults high" in failsafe is **not** stated in FCA's default-action text for any code pulled. Mechanically plausible given the above, but single-source.)*

---

# 10. Gear ratios — a real discrepancy to flag

The FCA/Alfa manual for the 2018 Stelvio, section "8HP50/850RE":

| | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | R |
|---|---|---|---|---|---|---|---|---|---|
| Description & Operation | 4.69 | 3.13 | 2.10 | 1.67 | 1.28 | 1.00 | 0.84 | 0.67 | 3.30 |
| Road Testing chart | 4.71 | 3.14 | 2.11 | 1.67 | 1.29 | 1.00 | 0.84 | 0.67 | — |

**These are Gen-1 (8HP45/70) ratios**, not the Gen-2 set (5.000, 3.200, 2.143, 1.720, 1.314, 1.000, 0.822, 0.640) that public references list for 8HP50/75. `CONFIRMED` that the OEM manual says this; `UNCERTAIN` why — either the FCA "8HP50" retains the Gen-1 gearset, or the section was carried over.

> **For ratio-error diagnosis on a Giulia/Stelvio, the OEM manual's numbers are what the TCM compares against** — and the two tables inside the same manual disagree in the third significant figure, so don't over-precision this.

---

# 11. Clutch application vs solenoid energisation — two different tables

**Engagement** (three elements closed per gear, two open):

| Gear | A | B | C | D | E |
|---|:-:|:-:|:-:|:-:|:-:|
| R | X | X | | X | |
| 1 | X | X | X | | |
| 2 | X | X | | | X |
| 3 | | X | X | | X |
| 4 | | X | | X | X |
| 5 | | X | X | X | |
| 6 | | | X | X | X |
| 7 | X | | X | X | |
| 8 | X | | | X | X |

The second OEM table — **which solenoids are energised** — differs: **in 6th gear no solenoid is energised at all**, while N energises C, D and E. Combined with the yellow/blue EDS curves in §9, this is the mechanism behind the 8HP's de-energised default state.

*Reverse = A, B and D — which independently matches the ATSG case published on ZF 8HP bind-up in reverse, where an unnecessary o-ring added at the valve-body feed hole in the case centre caused a reverse bind. There is **no** o-ring there in any ZF or ATSG documentation.*

---

# 12. Other confirmed notes

- **8HP50 in this application is rated for torque requests up to 500 N·m (369 lb-ft).**
- Valve body, TCM, all solenoids and all sensors are **one non-serviceable assembly** — *"If any component of the valve body including the TCM sensors or solenoids needs to be replaced, the complete TCMA (valve body) must be replaced."* **Extremely ESD-sensitive; ground strap mandatory.**
- Stop/start cars carry a **High Impulse Solenoid (HIS)** — a ~1 L hydraulic accumulator letting the gear engage **within 350 ms** of restart. Own DTCs P093A/P093B/P093C. **A stop/start engagement clunk complaint should point here.**
- Adaptation learning **aborts above 100 °C**; valid band 30–100 °C fast filling, 50–100 °C standard.
- **`P0634`** (TCM internal temperature too high) → limp-in, remote start and stop/start disabled. Threshold is *"a calibrated value"* — not published.

---

# 13. Could not verify — do not publish

1. **Line pressure values** (idle P/N, in gear, under load) in bar/psi for any 8HP variant — and note no pressure sensor exists.
2. **P0741 threshold** — moot; the code does not exist on 8HP.
3. **Normal TCC controlled-slip RPM** — only "actual vs target exceeds a calibrated threshold".
4. **Per-clutch slip RPM for worn vs healthy** — the only published slip number in the system is **P1731's 300 RPM**.
5. **The −300/+600 mbar and −120/+120 ms health ranges** — single-source (GEARS figure images); the OEM manual publishes no such ranges.
6. **Sump temperature triggering limp mode or a "transmission hot" message** — every OEM threshold is "a calibrated value".
7. **BMW ISTA oil-level window and BMW EGS ISN/immobiliser alignment.**
8. **Whether ZF Aftermarket ships mechatronics pre-programmed**, and vendor cloning practice.

**Method note for future sessions:** general search engines are heavily walled (DuckDuckGo 202 anomaly, Mojeek/searx/Startpage JS challenges, Brave 429). What worked was **direct fetching of `lemon-manuals.la`** and **WordPress REST search** (`/wp-json/wp/v2/search?search=…`) on gearsmagazine.com and transmissiondigest.com. Transmission Digest is paywalled after the first paragraph; GEARS full text is readable but its numeric tables are images.
