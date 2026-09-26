# Stelvio 2.0T (GU) Drivetrain Specifications — Transmission, Transfer Case, Differentials, Driveline, Mounts

**Vehicle:** 2018 Alfa Romeo Stelvio 2.0T (GU), US market, 2.0L GME-T4 turbo I4 (Sales Code **EC2**),
ZF 8HP50 automatic (MES reports it as **"ZF 8HP50/75"** — one shared MES database entry for both
box sizes; this car's TCM part number `10344202761` is the 8HP50 fitment per
`docs/reference/GIORGIO_MODULE_MAP.md`), Magna Q4 active on-demand AWD transfer case.

**Captured:** 2026-09-26. Builds on and does not contradict `docs/reference/ZF8HP_SERVICE_DATA.md`,
`docs/research/TRANSMISSION_ZF8HP_Q4.md`, `docs/reference/GIORGIO_MODULE_MAP.md`, and
`docs/reference/TSB_CATALOGUE.md`. Those files remain the deeper source for TCM adaptation
procedure, DTC taxonomy, module addressing and the TSB corpus — this document adds the missing
service numbers (fluid capacities, torques, part numbers) and organizes them by drivetrain
component for shop use.

## Confidence legend

- **CONFIRMED** — manufacturer document (owner's manual, FCA/ZF service literature, TSB/NHTSA filing).
- **CORROBORATED** — two independent non-manufacturer sources agree.
- **SINGLE-SOURCE** — one source only (forum consensus synthesis, aftermarket parts listing, etc.); treat as a starting point, not a shop-ready number.
- **UNKNOWN** — not found. Row says *"use the service manual (TechAuthority)"*.

No value in this document is invented. Where a number could not be found or only a single weak
source exists, it is labelled as such rather than presented as fact.

---

# 1. Transmission — ZF 8HP50 (incl. cooling)

## 1.1 Specs

| Item | Value | Unit | Source | Confidence |
|---|---|---|---|---|
| Fluid — must not be substituted with ATF+4 or any other current FCA ATF | "unique transmission fluid... NOT compatible with ATF+4" | — | `docs/reference/ZF8HP_SERVICE_DATA.md` §1 (ZF doc 1087.754.107c / FCA OEM text) | CONFIRMED |
| Fluid product | ZF LifeguardFluid 8, Mopar equivalent "8 & 9 Speed ATF", P/N **68218925AA** | — | ZF doc 1087.754.107c (repo doc); Mopar part no. from giuliaforums.com "How-To: ZF 8HP50/75 Fluid and Filter Change" thread | CORROBORATED (fluid identity CONFIRMED; part number SINGLE-SOURCE) |
| Overhaul dry fill (unit tipped, poured through side plug pre-install) | 9.0 (9.5 qt) | L | ZF doc 1087.754.107c Table 1, via `ZF8HP_SERVICE_DATA.md` §1 | CONFIRMED |
| Dry fill add if cooler replaced | +0.7 | L | same | CONFIRMED |
| Owner/service-manual "as fitted" capacity, 2.0 AWD | 9.3 (9.8 qt) | L | giuliatech.com fluid-specs table (independent of ZF doc, same ballpark) | SINGLE-SOURCE (plausible cross-check against the 9.0 L ZF number, not identical — do not treat as reconciled) |
| Service drain-and-fill (pan drop) quantity | not established — forum reports "a few quarts" pan volume plus a **0.5 L overfill during the level check** before final plug install | L / qt | giuliaforums.com "How-To" thread | UNKNOWN exact volume — **use the service manual (TechAuthority)** |
| Fill/level-check temperature window (general 8HP, this car's family) | 30–50 | °C (86–122 °F) | ZF doc 1087.754.107c Table 1 + FCA OEM procedure text, `ZF8HP_SERVICE_DATA.md` §1 | CONFIRMED |
| Level-check sequence | Engine running, P selected, 2000 rpm 30 s → idle → cycle P-R-D-1-2 ≥10 s dwell each → P → check temp, open plug (ZF); FCA equivalent: fill, then R 5s→D 5s→accelerate 2nd 5s→N@2000rpm 5s→P | — | `ZF8HP_SERVICE_DATA.md` §1 | CONFIRMED |
| 4th-gen 8HP (this box) level/fill | **Requires an OEM test device running a dedicated routine — no manual plug procedure exists** | — | ZF doc §5, `ZF8HP_SERVICE_DATA.md` §1 | CONFIRMED |
| Oil dye for leak detection | **Not required / not recommended** — fluid has UV illuminance; dye can cause shift-quality issues | — | `ZF8HP_SERVICE_DATA.md` §1 | CONFIRMED |
| Pan/filter | **Integrated assembly, not separately serviceable**; gasket reusable if undamaged | — | `ZF8HP_SERVICE_DATA.md` §1 | CONFIRMED |
| Service interval — FCA position | FCA markets 8HP as effectively "fill for life" under normal duty; no FCA-published mileage number for this car was found in this pass | — | — | UNKNOWN — **use the service manual (TechAuthority)** for the actual owner's-manual maintenance schedule entry |
| Service interval — ZF's own generic guidance | 50,000–75,000 | mi | forum synthesis (ZF-attributed) | SINGLE-SOURCE |
| Severe-duty guidance | Not found for this vehicle specifically | — | — | UNKNOWN — use the service manual severe-duty schedule (TechAuthority) |
| Adaptation relearn after service | **Fast Filling Adaptation** + **Standard Clutch Filling Adaptation**, run via wiTECH; MES exposes the same as "QUICK LEARN" / "STATIC ADAPTATION (STADA)" + separate "RESET ADAPTIVE VALUES" | — | `ZF8HP_SERVICE_DATA.md` §5–7 | CONFIRMED |
| Relearn required after routine fluid+filter change? | **Not listed as a trigger** in the OEM manual | — | `ZF8HP_SERVICE_DATA.md` §5 | CONFIRMED |
| Relearn required after TCM/TCMA re-flash alone (no parts replaced)? | **No** — explicitly excluded | — | `ZF8HP_SERVICE_DATA.md` §5 | CONFIRMED |
| Adaptations lost on battery disconnect? | **No** — stored in non-volatile EEPROM; the "pull the battery to reset" folk claim is contradicted by the OEM text | — | `ZF8HP_SERVICE_DATA.md` §5 (P062F description) | CONFIRMED |
| Cooler | Oil-to-coolant heat exchanger with a thermostatic element that deliberately keeps the box warm for warm-up/emissions | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §6 | CONFIRMED (architecture); track-only bypass is a modification, not a service step |
| Gearbox oil temperature — live read | TCM DID **`04FE`**, header `18DA18F1`, formula `A-40`, unit °C | °C | `docs/reference/GIORGIO_MODULE_MAP.md` Table C; implemented as `DidSpec(module="TCM", did=0x04FE, ...)` in `cuore/live/addressing.py:674-683` | UNVERIFIED on this 2.0T specifically (formula is the danardi78 Giulia 2.2D value, not yet confirmed against this car's own scan) — treat as SINGLE-SOURCE pending on-car verification |
| How cuore reads it live | `cuore.live.ops.module_did("TCM", "04FE", vin=<VIN>)` opens a session on CAN-C, addresses `18DA18F1`, issues UDS `22 04FE`, and records the observation; equivalently the `obd2` MCP's `read_did` tool against module `TCM`, DID `0x04FE` | — | `cuore/live/ops.py:485-496` (`module_did`) | CONFIRMED (code path exists and is wired to this DID) |

## 1.2 Torques

| Component | Value | Unit | Sequence / angle | Single-use | Source | Confidence |
|---|---|---|---|---|---|---|
| Pan/filter bolts (13×) | 10 | N·m (89 in-lb) | no stated sequence in repo doc | No (gasket reusable if undamaged; **BMW** parallel procedure says pan itself must be replaced each release — see below) | `ZF8HP_SERVICE_DATA.md` §1 (ZF doc 1087.754.107c) | CONFIRMED |
| **BMW G30 reference only** — mechatronics-to-transmission bolts M6×59/M6×20 | 8 | N·m | sequence 1→17; **screws replaced every time** | Yes | `ZF8HP_SERVICE_DATA.md` §1 | CORROBORATED for BMW 8HP family — **not Giorgio-specific**, use as a sanity check only |
| **BMW G30 reference only** — output speed sensor | 4 N·m + 12° | N·m + angle | — | not stated | `ZF8HP_SERVICE_DATA.md` §1 | CORROBORATED for BMW — not Giorgio-specific |
| **BMW G30 reference only** — pan bolts M6 (13×) | 10 | N·m | sequence 1→13; **pan must be replaced each time it is released** | Yes (pan) | `ZF8HP_SERVICE_DATA.md` §1 | CORROBORATED for BMW — Giorgio pan/filter is described in the FCA text as an integrated non-serviceable assembly, so treat "replace the unit" as the safer default until an Alfa-specific number is found |
| **BMW G30 reference only** — drain plug M18 | 8 | N·m | — | not stated | `ZF8HP_SERVICE_DATA.md` §1 | CORROBORATED for BMW — not Giorgio-specific |
| Giorgio-specific transmission drain/fill plug torque | — | — | — | — | not found in this pass | **UNKNOWN — use the service manual (TechAuthority)** |

## 1.3 DTCs to watch

| DTC | Meaning | Default action | Source | Confidence |
|---|---|---|---|---|
| `P1DB7-00` | Torque Converter Clutch Performance (the 8HP's functional equivalent of a "P0741" — **P0741/P0740/P0742 do not exist on this box**) | MIL first trip; TCC solenoid current limited to 50 mA, TCC forced open | `ZF8HP_SERVICE_DATA.md` §2 | CONFIRMED |
| `P0731`–`P0735`, `P0729` (6th), `P076F` (7th), `P07D9` (8th) | Per-gear ratio error — non-contiguous numbering | MIL, adaptive default-gear ladder | `ZF8HP_SERVICE_DATA.md` §2 | CONFIRMED |
| `P1D8F`–`P1D93`, `P1D96`–`P1D9F`, `P1DA0`–`P1DA8`, `P1D95` | Clutch-resolved ratio faults — single/pair/triplet clutch defective, or undetermined | limp-in, adaptive default gear | `ZF8HP_SERVICE_DATA.md` §2 | CONFIRMED |
| `P1731` | Incorrect Gear Engaged — turbine slip > 300 RPM is the only published hard slip threshold on this box | MIL first trip, limp-in, special shift modes and stop/start disabled | `ZF8HP_SERVICE_DATA.md` §2 | CONFIRMED |
| `P167A` | Calibration Mismatch (programmed software vs Hydraulic ID burned into TCMA EEPROM) | limp-in | `ZF8HP_SERVICE_DATA.md` §8 | CONFIRMED |
| `P1DC6` | TCM Not Programmed | immediate MIL, limp-in | `ZF8HP_SERVICE_DATA.md` §8 | CONFIRMED |
| `P0610`, `U3002-00` | VIN mismatch after TCM replacement | MIL first trip, limp-in | `ZF8HP_SERVICE_DATA.md` §8 | CONFIRMED |
| `P1500` | Vehicle configuration codes (PROXI) mismatch | limp-in, no positive torque interventions requested | `ZF8HP_SERVICE_DATA.md` §8 | CONFIRMED |
| `P07E4`, `P1DB2`, `P0716`, `P1B14`, `P0733`, `P1D90`, `P1DB7`, `P1B13` | Master 8HP shift-quality/valve-body TSB code set | see TSB `S2621000003 REV. A` below | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED |

## 1.4 Related TSBs

| TSB | Date | Applies to this car? | What it fixes | Source | Confidence |
|---|---|---|---|---|---|
| **`21-035-20`** — Flash: TCM Update | 2020-05-08 | **Yes — explicitly "2018 (GU) Alfa Romeo Stelvio," 2.0L I4 DI Turbo (EC2), North America** | MIL with `P0002-00`, `P026E-00`, `P1066-00`, `P26E4-00`, `P2B61-00`, `P2BC1-00`, `U1008-00`; reprograms TCM for **transmission shift-quality improvements** plus a turbo coolant-pump after-run update. Labor op `18-19-05-MX`, 0.3 hr. PCM must also be updated to latest at completion. | fetched directly from `static.nhtsa.gov/odi/tsbs/2020/MC-10176569-9999.pdf` | **CONFIRMED (manufacturer document, model/engine match exact)** |
| `21-044-19` — Flash: TCM Update | 2019-12-17 | 2019 (GU) Stelvio, EC2, built on/before Oct 10 2019 — **not this car's model year**, kept for context | Same symptom/DTC set and shift-quality fix as `21-035-20`, the prior software revision. Labor op `18-19-05-MU`. | fetched directly from `static.nhtsa.gov/odi/tsbs/2019/MC-10170397-9999.pdf` | CONFIRMED (manufacturer document; wrong model year for this VIN) |
| `21-032-17`, `21-045-19`, `21-032-20` | various | Referenced as the other TCM-flash bulletins in the same family | Not independently fetched this pass | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED bulletin numbers exist; content not re-verified here |
| `S2621000003 REV. A` | 2026-03-09 | 2017-2026 Giulia (GA) and 2018-2026 Stelvio (GU), covers 8HP45/50/70/75/90/95 | Burnt-fluid smell and fine metallic content are normal; **valve body replacement before transmission replacement**; `P1B13`/`P1B14` → check MPR cable; `P0733` → follow `21-029-25 REV. A` (8HP75 clutch-D repair — **not this car's box size**) | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED |
| `21-029-25 REV. A` | — | 8HP75 only | Clutch-D repair for `P0733` | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED bulletin exists; **not applicable to this car's 8HP50** |
| `CSN W05` | 2020-03-10 | PCM reprogram campaign | Ties to `U04B1-00` after a W05 flash; fixed by BCM restore-configuration routine, not circuit repair | `docs/reference/TSB_CATALOGUE.md` §1 | CONFIRMED |

## 1.5 Service checklist — transmission fluid service

1. **Confirm fluid identity before opening anything.** ZF LifeguardFluid 8 / Mopar 68218925AA only — never ATF+4. *(CONFIRMED, §1.1)*
2. Warm the transmission to the **30–50 °C** fill/level window; on a 4th-gen box (this one) the level check requires an **OEM scan tool routine**, not a manual plug-and-check. *(CONFIRMED, §1.1)*
3. Drop the pan/filter (integrated assembly). Do **not** plan on separately servicing the filter. *(CONFIRMED)*
4. Reinstall pan/filter: **13 bolts, 10 N·m.** *(CONFIRMED, §1.2)* — Giorgio-specific bolt sequence not found; BMW's 1→13 star-style sequence is a reasonable cross-check only.
5. Refill; forum practice is to overfill by **~0.5 L** and bleed back at the level-check plug — **treat this as unverified shop practice, not an OEM number**, and use the OEM scan-tool fill routine where available.
6. **Drain/fill plug torque: UNKNOWN — use the service manual (TechAuthority).**
7. Adaptation relearn is **not required** for a routine fluid-and-filter change per the OEM text — do not run "RESET ADAPTIVE VALUES" as a matter of course; resetting without following through both Fast Filling and Standard Clutch Filling Adaptation leaves the car worse than before. *(CONFIRMED, §1.1)*
8. Clear DTCs, road test, re-scan. If shift quality is off, check for `21-035-20` (this car's exact TCM flash) before condemning hardware.

---

# 2. Transfer case — Magna Q4 (active on-demand AWD)

## 2.1 Specs

| Item | Value | Unit | Source | Confidence |
|---|---|---|---|---|
| Behaviour | Rear-biased; 100% rear normally, on-demand up to **60%** to the front axle via a controlled clutch (not a centre differential) | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5 | CONFIRMED |
| Actuator architecture | **Hypothesis only**: electric-motor-driven ball ramp applying a multi-plate wet clutch (Magna Active Transfer Case pattern, shared with BMW xDrive / Jeep Active Drive) | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5 | UNVERIFIED for this specific vehicle — resolve via MES DTCM parameter-name read per that doc's method |
| Fluid product | Petronas Tutela Transmission Transfer Case (Q4) — Tutela Transmission Hypoide Gear Oil, Synthetic **SAE 75W**, FIAT approval **9.55550-DA11** | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5 (LIKELY) **and independently** giuliatech.com fluid-specs table, same FIAT number | **CORROBORATED** (two independent non-manufacturer sources agree on the FIAT approval number) |
| Capacity | **Conflicting figures**: ~1 L per repo doc (specialist retailer + forum) vs **0.7 L** per giuliatech.com's capacity table | L | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5; giuliatech.com | **SINGLE-SOURCE each, unreconciled — confirm the exact fill quantity at the dealer parts counter by VIN or in TechAuthority before doing the job** |
| Fill/drain plug torque | not found | N·m | — | **UNKNOWN — use the service manual (TechAuthority)** |
| Service interval | not found (no OEM number) | — | — | **UNKNOWN — use the service manual (TechAuthority)** |
| Fluid substitution warning | Do **not** substitute ATF or a generic 75W GL-5 — friction characteristics are matched to the clutch pack; the FIAT approval number is what matters, not just the viscosity grade | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5 | CONFIRMED reasoning (architecture); not a manufacturer quote |
| ADJ routine (DTCM) | **Hypothesis**: actuator position / clutch-clearance learn, drives to mechanical end stops and records encoder positions | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5 | UNVERIFIED — **read the MES procedure text before running; do not run with the vehicle on the ground or on a single-axle dyno** |
| No ACT (actuator test) exists | Consistent with a motor-driven ball ramp — nothing safe to statically test | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5 | LIKELY |
| Torque-split calibration | **Almost certainly not available** — no tool ecosystem lists a Giorgio DTCM | — | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §1, §5 | LIKELY NO |

## 2.2 Torques

| Component | Value | Unit | Notes | Single-use | Source | Confidence |
|---|---|---|---|---|---|---|
| Fill/drain plug | — | — | not found | — | — | **UNKNOWN — use the service manual (TechAuthority)** |

## 2.3 DTCs / known issues

| DTC / issue | Meaning | Source | Confidence |
|---|---|---|---|
| `U0100-87` | Lost Communication with ECM — observed as a **bystander code manufactured by whole-vehicle serial UDS sweeps**, not a real fault, on this exact car's own scan (`SCAN_2609041953`) | `docs/reference/GIORGIO_MODULE_MAP.md` Table B | CONFIRMED (this car's own log) |
| `U0102` "Lost Communication With Transfer Case Control Module/AWD" on a **RWD** car | A configuration fault (AWD software loaded on a RWD vehicle) after ECM replace/flash, wearing a communication code's clothes — **not applicable to a factory Q4 car**, listed for completeness | TSB `S2008000078 / REV. A`, `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED |
| Tyre-circumference mismatch on AWD (must be within 1/8") | Root cause of gear-ratio DTCs, shift concerns, shudder, **and transfer-case damage** — rule out before condemning any driveline hardware | TSB `S1821000001 REV. A`, `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED |
| No TSB addresses Q4 transfer-case internal failure, actuator failure, or propshaft | Explicit finding after a full-text regex sweep of 287 readable Alfa TSBs | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED (absence-of-evidence finding, not a guess) |
| PTU/stubshaft seal — `9004150` | If replacing the stubshaft for an ATX fluid leak, **do not** also replace the PTU seals | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED |
| Generic Magna active-transfer-case failure modes (not Alfa-specific) | Actuator motor brush wear / water ingress at connector / rising current draw pre-failure; position sensor / encoder faults; chain stretch/sprocket whine tracking road speed; clutch-pack glazing from wrong or degraded fluid | `docs/research/TRANSMISSION_ZF8HP_Q4.md` §5 | UNVERIFIED for this platform — offered as *what to look for*, not a reported Alfa failure rate |

## 2.4 Service checklist — transfer case service

1. Confirm fluid: **Tutela Transmission Transfer Case (Q4), SAE 75W, FIAT 9.55550-DA11.** Do not substitute a generic 75W GL-5 or ATF. *(CORROBORATED, §2.1)*
2. **Capacity is unreconciled between two single sources (0.7 L vs ~1 L)** — confirm the exact quantity for this VIN before ordering fluid or committing to a fill-to-level-hole procedure.
3. **Drain/fill plug torque: UNKNOWN — use the service manual (TechAuthority).**
4. Before condemning any transfer-case hardware for shudder/bind/ratio DTCs, **verify tyre circumference match within 1/8"** across all four tyres (TSB `S1821000001 REV. A`).
5. If a DTCM ADJ (actuator learn) routine is called for, **read its MES procedure text first** and do not run it with wheels on the ground or on a single-axle dyno.
6. There is no manufacturer-published torque-split calibration or internal-repair TSB for this unit — treat internal failures as replace-the-unit jobs pending TechAuthority confirmation.

---

# 3. Differentials

## 3.1 Front differential

| Item | Value | Unit | Source | Confidence |
|---|---|---|---|---|
| Fluid | SAE 75W-80, **API GL-5**, synthetic, FIAT approval **9.55550-DA10** | — | giuliatech.com fluid-specs table | SINGLE-SOURCE |
| Capacity, 2.0T | 0.5 | L | giuliatech.com | SINGLE-SOURCE |
| Capacity, 2.9 QV | 0.45 | L | giuliatech.com | SINGLE-SOURCE (not this car — reference only) |
| Fill/drain plug torque | — | — | not found | **UNKNOWN — use the service manual (TechAuthority)** |
| Service interval | Anecdotally lasts to ~100,000 km without visible wear (front sees less duty than rear on this rear-biased AWD system) | km | forum synthesis (giuliaforums/stelvioforum threads) | SINGLE-SOURCE — not an OEM schedule |
| LSD additive | Not applicable — front is a fixed-ratio open unit on 2.0T Q4, no LSD option found for the front axle | — | inference from architecture (Q4 clutch does the front torque modulation, not a front LSD) | LIKELY, not independently confirmed |

## 3.2 Rear differential

| Item | Value | Unit | Source | Confidence |
|---|---|---|---|---|
| Fluid | SAE 75W-85, synthetic, FIAT approval **9.55550-DA9** (2.0T variants: open **195**, mechanical-LSD **230-LSD**, electronic-LSD **210-eLSD**) | — | giuliatech.com fluid-specs table | SINGLE-SOURCE |
| Fluid, 2.9 QV torque-vectoring (**230-TV**, reference only — not this car) | SAE 75W-85, **API GL-5**, synthetic, FIAT approval **9.55550-DA8** | — | giuliatech.com | SINGLE-SOURCE |
| Capacity, 2.0T variants | 0.9–1.1 (varies by internal type — 195 / 230-LSD / 210-eLSD) | L | giuliatech.com | SINGLE-SOURCE |
| Capacity, 2.9 QV TV (reference only) | Main 0.8 L + Left TV 0.5 L + Right TV 0.6 L (Giulia) or 0.61–0.68 L (Stelvio) — **3-chamber unit** | L | giuliatech.com | SINGLE-SOURCE |
| Fill/drain plug torque | **26** (both drain and fill, reported as the same fastener spec) | N·m | stelvioforum.com "Transfer case drain/fill plug torque specs" thread — given by the original poster as a known rear-diff value while asking (unsuccessfully) about the transfer case's own plug torque | **SINGLE-SOURCE** — not independently corroborated; the poster's own thread leaves the transfer case value as an open question, which is itself a useful cross-check that this number is not being casually reused across both units |
| Service interval | Forum guidance: rear wears faster than front, some recommend ~50,000–60,000 km | km | forum synthesis | SINGLE-SOURCE — not an OEM schedule |
| Trim/option note | This car's actual rear differential type (open **195** vs mechanical-LSD **230-LSD** vs electronic **210-eLSD**) depends on trim/options (**Ti Sport and Q4-package cars are the ones most likely to carry the LSD/eLSD unit**) | — | user-provided trim context + giuliatech.com option-code naming | UNKNOWN which unit is fitted to this specific VIN — **decode the build sheet / option codes, or confirm at a dealer parts counter by VIN, before ordering fluid or parts** |
| LSD additive | Not found as a separate additive requirement for the mechanical-LSD (**230-LSD**) unit; the fluid above may already be a friction-modified GL-5 — not confirmed | — | — | **UNKNOWN — use the service manual (TechAuthority)**; do not assume a standard GL-5 is friction-safe for the LSD unit without checking |

## 3.3 Service checklist — differential service (front and rear)

1. **Decode this VIN's rear differential type first** (195 open / 230-LSD / 210-eLSD) — fluid and any LSD-additive requirement may differ. *(UNKNOWN — confirm before ordering parts, §3.2)*
2. Front: SAE 75W-80 GL-5 synthetic, FIAT 9.55550-DA10, ~0.5 L. *(SINGLE-SOURCE, §3.1)*
3. Rear: SAE 75W-85 synthetic, FIAT 9.55550-DA9, ~0.9–1.1 L depending on internal type. *(SINGLE-SOURCE, §3.2)*
4. **Do not assume a generic 75W-85/90 GL-5 is friction-safe for a mechanical-LSD rear unit** without checking for an LSD additive requirement — unresolved in this pass.
5. Rear plug torque: **26 N·m** (SINGLE-SOURCE, both drain and fill) — front plug torque: **UNKNOWN, use the service manual (TechAuthority).**
6. No OEM service interval was found for either unit in this pass; forum-only guidance (~50,000–100,000 km depending on axle) is not a substitute for the owner's-manual schedule.

---

# 4. Driveline — propshaft/driveshaft, CV axles, hub nuts

## 4.1 Specs

| Item | Value | Source | Confidence |
|---|---|---|---|
| Propshaft material | Referenced by an aftermarket parts vendor as a **carbon-fibre driveshaft** on 2017-2025 Giulia/Stelvio (page content could not be fully retrieved this pass — title/URL only) | go-parts.com garage article (title/metadata only — body fetch blocked, HTTP 403) | SINGLE-SOURCE, and weakly so — confirm construction (steel vs carbon-fibre, one-piece vs two-piece with centre bearing) against the parts catalogue for this VIN before ordering |
| Centre support bearing | Not confirmed present or absent | — | **UNKNOWN — use the service manual (TechAuthority)**; a two-piece propshaft on a mid-size AWD platform commonly has one, but this was not verified for the Giorgio platform |
| Flex disc / coupling | Front flex-disc bolts described as **possibly torque-to-yield, requiring replacement** | forum synthesis (alfabb.com) | SINGLE-SOURCE |

## 4.2 Torques

| Component | Value | Unit | Sequence / angle | Single-use | Source | Confidence |
|---|---|---|---|---|---|---|
| Propshaft flange/centre-carrier nut | UNKNOWN | — | **Do not use the 72.3–101.1 ft-lb figure found online:** fact-check 2026-09-26 traced it to the 1970s Alfa 2000 shop manual (10–14 m-kg), not the Giorgio platform | not stated | none for this car | UNKNOWN — use the service manual (TechAuthority) |
| Central M14 bolt, **Q4 (4×4) versions specifically** | 124–136 | N·m | not stated; location not independently confirmed — likely a front-driveline or subframe pivot fastener unique to AWD cars | not stated | forum synthesis (alfaowner.com) | SINGLE-SOURCE, and location ambiguous — verify which fastener this is before use |
| Front/rear axle (hub) nut | 52 ft-lb + **47° additional angle**; **new nut required every time** | ft-lb + angle | torque-then-angle procedure | **Yes** | stelvioforum.com forum synthesis | SINGLE-SOURCE |
| Front/rear hub mounting bolts | 74 | ft-lb (≈100 N·m) | not stated | not stated | forum synthesis (stelvioforum.com) | SINGLE-SOURCE |
| Wheel lug bolts (reference — not a drivetrain fastener) | ~89 | ft-lb (≈120 N·m) | not stated | not stated | forum synthesis (giuliaforums.com/alfaowner.com) | SINGLE-SOURCE — included for completeness only |

## 4.3 Known issues

| Issue | Note | Source | Confidence |
|---|---|---|---|
| Front flex-disc bolts | May be torque-to-yield; must be replaced, not reused | alfabb.com forum synthesis | SINGLE-SOURCE |
| PTU/stubshaft seal (`9004150`) | If replacing the stubshaft for an ATX fluid leak, do **not** also replace the PTU seals | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED |
| No TSB addresses propshaft failure | Explicit finding from the full TSB corpus sweep | `docs/reference/TSB_CATALOGUE.md` §3 | CONFIRMED (absence finding) |

## 4.4 Service checklist — axle/propshaft work

1. Confirm propshaft construction (material, one- vs two-piece, centre bearing presence) against the parts catalogue for this VIN before ordering — **not verified in this pass.**
2. Propshaft flange/centre-carrier nut: **UNKNOWN — use the service manual.** The 72.3–101.1 ft-lb figure online is from the 1970s Alfa 2000 manual, not this car. *(fact-check 2026-09-26)*
3. **Front axle/hub nut is torque + angle (52 ft-lb + 47°) and single-use — always fit a new nut.** *(SINGLE-SOURCE, §4.2 — verify against TechAuthority before relying on it for a customer job)*
4. Hub mounting bolts: 74 ft-lb reported. *(SINGLE-SOURCE)*
5. If replacing the stubshaft for a fluid leak, **do not** replace the PTU seals at the same time (`9004150`). *(CONFIRMED)*
6. Check any flex-disc/coupling bolts for a torque-to-yield callout before reusing them.
7. After any driveline disassembly on a Q4 car, verify tyre circumference match (1/8") before returning the car — mismatched tyres present as driveline symptoms (`S1821000001 REV. A`).

---

# 5. Mounts — engine and transmission

## 5.1 Torques

| Component | Value | Unit | Notes | Single-use | Source | Confidence |
|---|---|---|---|---|---|---|
| Engine mount bolts into the aluminium block | 22–27 | N·m | — | not stated | forum synthesis (alfaowner.com) | SINGLE-SOURCE |
| Longitudinal mount (torque strut / dogbone) bolts | 25–31 | N·m | Alfa Romeo specifies the **mount itself must be replaced** on removal | **Yes (mount)** | forum synthesis (alfaowner.com) + an aftermarket install-instruction PDF referenced by the same search (PDF itself could not be text-extracted this pass — binary/encoded stream) | SINGLE-SOURCE |
| Central M14 bolt, Q4 versions | 124–136 | N·m | Location ambiguous — may be an engine-mount-to-subframe pivot fastener unique to AWD cars, or may belong with the driveline flange in §4.2; **not resolved in this pass** | not stated | forum synthesis (alfaowner.com) | SINGLE-SOURCE, location unconfirmed |
| Transmission-bracket-to-transmission-case fasteners | Torque value not found; **fasteners are called out as one-time-use, must be replaced** per a referenced TSB for the 2021 Stelvio (bulletin number not independently verified this pass) | — | single-use per that TSB reference | **Yes** | forum synthesis (alfaowner.com), citing an unidentified FCA TSB | SINGLE-SOURCE, and the TSB number itself is unverified — confirm in `docs/reference/TSB_CATALOGUE.md`'s corpus or TechAuthority before quoting a torque |

## 5.2 Known wear issues

| Issue | Note | Source | Confidence |
|---|---|---|---|
| Transmission mount clunk/vibration | Referenced as a common complaint by an aftermarket parts vendor's diagnostic guide for 2017-2025 Giulia/Stelvio/Grecale 2.0L (page body could not be retrieved this pass — title/URL only, HTTP 403) | go-parts.com garage article (title/metadata only) | SINGLE-SOURCE, and weakly so — treat as a plausible lead, not a confirmed failure pattern |

## 5.3 Service checklist — mount replacement

1. Engine mount bolts (to aluminium block): **22–27 N·m** reported. *(SINGLE-SOURCE, §5.1)*
2. Longitudinal (dogbone) mount: **25–31 N·m**, and **the mount itself is single-use — do not reinstall a removed mount.** *(SINGLE-SOURCE, §5.1)*
3. On Q4 cars, identify and torque the central M14 bolt correctly — **confirm its exact location (engine-mount pivot vs driveline flange) before relying on the 124–136 N·m figure**, since two different forum threads used it in two different contexts. *(SINGLE-SOURCE, ambiguous location — §5.1/§4.2)*
4. Transmission-mount-bracket fasteners are reported single-use on at least one model year — **always fit new fasteners and confirm the actual torque value in TechAuthority**, since none was found independently in this pass.
5. A transmission-mount clunk/vibration complaint should prompt inspection of this mount before condemning the transmission or driveline — treat the underlying source as unverified until corroborated.

---

# 6. What is UNKNOWN — summary

Every row below says **"use the service manual (TechAuthority)"**:

- Transmission drain/fill plug torque (Giorgio-specific).
- Transmission service drain-and-fill exact quantity (only "a few quarts + 0.5 L overfill" is known, from forum practice, not an OEM spec).
- FCA's actual published transmission service interval and severe-duty guidance for this VIN (only ZF's generic 50,000–75,000 mi guidance was found, single-source).
- Transfer case fill/drain plug torque, and its exact capacity (0.7 L vs ~1 L are unreconciled single sources).
- Transfer case service interval.
- Front differential plug torque (rear is SINGLE-SOURCE at 26 N·m, not confirmed).
- Transfer case plug torque, specifically — one forum thread's poster knew the rear-diff 26 N·m figure but left the transfer case's own value as an open, unanswered question.
- Front and rear differential service intervals (OEM number).
- Whether the mechanical-LSD rear differential requires a separate friction/LSD additive.
- Which rear differential unit (195 open / 230-LSD / 210-eLSD) is actually fitted to this VIN.
- Propshaft construction detail (material, centre bearing presence) for this VIN.
- Exact location and correct value of the "central M14 bolt, Q4 versions" (124–136 N·m) — competing plausible locations in engine-mount and driveline contexts were not resolved.
- Torque value for transmission-mount-bracket fasteners (single-use fastener is reported, value is not).
- The TSB number behind the transmission-mount single-use-fastener claim.

**Sources fetched directly this pass:** `static.nhtsa.gov/odi/tsbs/2020/MC-10176569-9999.pdf` (TSB 21-035-20), `static.nhtsa.gov/odi/tsbs/2019/MC-10170397-9999.pdf` (TSB 21-044-19), `giuliatech.com/t/alfa-romeo-giulia-fluid-specs-and-capacities/91`. Other figures are WebSearch's own synthesis of forum threads at giuliaforums.com, alfabb.com, alfaowner.com, stelvioforum.com, and shop.alfissimo.com/shop.alfisti.net product listings — several of the underlying pages could not be fetched directly (paywalled via a `tollbit.*` redirect layer, or HTTP 403/binary PDF), so those numbers are marked SINGLE-SOURCE and should be re-verified before being used on a customer vehicle. The rear differential plug torque (26 N·m) was located via `mes-log-mcp/mes/service_specs.py`'s independent research pass (its `rear_diff_drain_plug` / `rear_diff_fill_plug` rows, sourced to the same stelvioforum thread) and folded in here rather than re-derived.


## Owner's manual check (2026-09-26)

- **Transfer case oil**: replace at 80,000 mi (128,000 km) / 8 years (CONFIRMED, 2018 US owner's manual Maintenance Plan). This car is about 142,290 km, so it is due unless already done.
- The Maintenance Plan lists no automatic transmission fluid or differential oil change.
