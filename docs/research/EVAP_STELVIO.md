# EVAP Diagnosis — 2018 Stelvio 2.0T (GME-T4)

**Case:** VIN ZASFAKPN5J7B88115, 140,572 km. `P0456` chronic since 2025-09-24 @ 114,008 km; `P0455` + `P0440` new 2026-08-27. All three cleared in that session, not yet re-driven.

---

# 1. ⭐ THE MOST IMPORTANT FACT: you cannot road-test this repair

**TSB 18-089-19** — *"wiTECH Small Leak Verification Test (SLVT) – P0456-EVAP SYSTEM SMALL LEAK"*, nhtsaId 10169219, 1 Nov 2019, Group 18, applies to **all 2015-2020 FCA US gasoline vehicles**. **CONFIRMED — official, full PDF retrieved.**

> *"It is mandatory to run the wiTECH SLVT while performing the P0456 diagnostics… **A road test will not confirm the repair, as P0456 is only set with multiple engine off and drive cycles, which cannot be reproduced during a dealer visit.** wiTECH SLVT is the only tool currently available to confirm a fix after the repair."*

PDF: `https://static.nhtsa.gov/odi/tsbs/2019/MC-10169219-9999.pdf`
Cross-references Warranty Bulletin D-19-23 and Master Tech course **MTCE1901 "EVAP System Overview and Diagnosis"**. Still live — reissued as `1808919`, again as `1804823` (Apr 2023).

### What this means for this job

- **The drive-cycle plan is not sufficient.** P0456 sets only after *multiple* engine-off soak/drive cycles. A clean scan after one drive proves nothing, and even several drives may not reproduce it.
- **MultiEcuScan cannot run SLVT.** This is a wiTECH routine. MES exposes EVAP actuator tests and live parameters but not the leak-verification routine.
- **This is exactly the dealer-tech-knows / generic-scan-tool-user-doesn't item.** Anyone verifying an FCA small-leak repair by driving the car is guessing.

**Practical options:** wiTECH 2 aftermarket 1-yr launch package ~$2,800 (renewal ~$1,600/yr, includes a secure microPod II) · a 3-day or monthly wiTECH subscription · or subcontract the verification.

---

# 2. Architecture correction: Giorgio uses an ESIM, and it is separately serviceable

**TSB 9100469**, nhtsaId 11011985, 16 Dec 2024, applicability **MY18-25 GA / GU** (Giulia and Stelvio). **CONFIRMED — official.**

> Part numbers: `68400620A$`, `68402531A$`, **`68528496A$`**, `68534104A$` — Part Description: **VAPOR CANISTER**
> *"If an issue is detected with the **EVAPORATIVE SYSTEM INTEGRITY MODULE DETECTOR** and not the VAPOR CANISTER, only replace the EVAPORATIVE SYSTEM INTEGRITY MODULE DETECTOR."*

PDF: `https://static.nhtsa.gov/odi/tsbs/2024/MC-11011985-0001.pdf`

> **FCA's own bulletin says ESIM — do not accept aftermarket catalogue naming as evidence of architecture.** Parts sites list Alfa "Leak Detection Pump" entries (`68300626AA`, `4861961AD`); `4861961AD` is an old Chrysler LDP series and one listing scopes `68300626AA` to the 2.9 V6 only. A forum user's *"$110 leak detector pump"* is most likely the ESIM under a colloquial name.

**Consequence: the canister and the ESIM are separate parts.** Replacing a $275+ canister when the ESIM is at fault is a documented, bulletin-warned error.

---

# 3. Check the canister filter first — it is cheap and scheduled

**TSB 9100468**, nhtsaId 11012010, Dec 2024. **CONFIRMED — official.** The EVAP fuel vapour canister **filter** must be checked for restriction or blockage on the owner's-manual schedule and replaced if blocked.

**A blocked filter is a cheap, checkable cause that precedes any canister decision.** Do this before condemning anything.

---

# 4. Field failure evidence — what actually fails

## Rank 1: charcoal canister / vapor canister module assembly
**LIKELY** — converging forum evidence across two sites plus dealer statements.

- A dealer reportedly called P0440 *"the most common problem he repairs on Stelvios"*, seen in 5 of 9 Stelvios locally; second most common is the instrument cluster.
- A dealer service manager: happens *"primarily in 2018 to 2020 Stelvios, and to a lesser extent, Giulias."*
- A poster identifying as an Alfa tech: *"Generally the P2422 code sets from a plugged canister"* — and he had replaced **only one vent valve in six years**.
- Mopar P/N **68528496AA** confirmed across Mopar catalogue and three retailers; located **behind the driver's-side rear wheel liner**; **supply-constrained**.

**Design root cause (UNCERTAIN, forum-sourced but mechanically coherent):** the original canister places the charcoal bed at the **bottom** of the module, so topping off lets liquid fuel migrate in and pool by gravity, saturating the bed. A revised design moves the charcoal canister to the **top** with the original bottom area blanked off.

**Repeat failure is a real pattern (LIKELY).** Owners report second failures within 6-16 months; *"Both dealers told me they are extremely common fail points for the car and they are usually on back order."* Two competing causal theories:
- **Overfilling** past the first pump click. Attributed to a dealer tech: *"best practice is once the pump shuts off, be done filling the tank."*
- **Water ingress** — *"they told me it was full of water so clearly, nothing to do with overfilling"*; another poster: *"water can somehow get around the fender apron and into the unit. A TSB and additional shield addressed this."* **UNCERTAIN** — TSB number not located. But note this model has **two confirmed water-ingress recalls** (18V203000 liftgate, 18V205000 BCM), so water intrusion is an established Giorgio theme, not a fringe theory.

## Rank 2: purge solenoid — **low yield alone**
Frequently replaced *alongside* the canister. Several owners report replacing the purge valve alone with **no resolution**.

> **The shop's own logs are evidence here:** on 2025-09-24 the `Evaporation control valve` actuator test was run **six times, all COMPLETED**, at 114,008 km, in the same session P0456 was stored. The purge valve actuated correctly while the code was present.

## Rank 3: canister vent valve as a discrete part — evidence argues **against**
Despite P2422 meaning "vent valve stuck closed," field consensus is the **canister is plugged, not the valve**. On NA cars the vent function is **integrated into the canister module**, which is why canister replacement clears P2422. Do not sell a standalone vent valve on P2422 without proving it.

## Not substantiated at all
Filler neck / ORVR check valve, fuel pump module flange gasket, lock ring seal — **zero field reports** implicating these on Giulia/Stelvio.

---

# 5. "Pump clicks off during refuelling" ← canister

**CONFIRMED at forum quality with a sound mechanism; LIKELY overall.** Independent threads on two forums, including one clean cause-and-effect sequence: symptom → FTP sensor replacement **failed** → *"Replaced charcoal canister assembly"* → *"The car has not had problem filling up since."*

**Mechanism:** ORVR requires displaced tank vapour to exit through the canister and out the vent during fill. A plugged/saturated canister blocks that path, tank pressure spikes, fuel backs up the filler neck, and the nozzle's vacuum-sensing port trips.

> **P2422 + "pump clicks off" is close to pathognomonic for a blocked canister/vent on this platform.**

Secondary tell: topping off after auto-shutoff overfills the canister, throwing codes **and disabling remote start**.

---

# 6. The dual-path boost purge — and why P1CEA is a different animal

`LIKELY` — reconstructed from FCA's own possible-cause list, labour-operation naming, and technician discussion. No OEM "Description and Operation" text was obtainable.

A turbo engine loses manifold vacuum exactly when it needs purge flow. GME-T4 runs **two purge paths off one solenoid**, each gated by a check valve:
- **Off-boost:** manifold vacuum draws vapour straight into the intake manifold.
- **On-boost:** manifold pressure is positive, so path 1's check valve closes. Boost is tapped from the **CAC duct** and driven through an **ejector tee** (venturi); the motive flow entrains vapour and discharges into the **air cleaner / turbo inlet**, upstream of the compressor where pressure is always sub-atmospheric.

FCA's labour operation names the part the **"Boost Vacuum Purge Tube Assembly"** — authoritative corroboration of the two-mode design.

**P1CEA** = *"insufficient vapor flow detected during a boost condition"* — a **flow/performance rationality monitor, not a leak monitor**. It runs **only after the small-leak test has passed**, which is why P1CEA and P0456 rarely coexist and why leak codes are fixed first.

### FCA's published possible-cause list for P1CEA
> FTP sensor 5-volt supply / signal / return circuit resistance · **BLOCKAGE/FLASH AT THE PORTS ON THE CAC DUCT AND THE AIR CLEANER** · purge hose/tube and air filter obstruction · **OBD VENT VALVE OR THE EJECTOR TEE MALFUNCTION** · fuel tank pressure sensor · purge solenoid vacuum supply · purge solenoid · PCM

**"Blockage/flash at the ports"** — moulding flash left in the CAC duct and air cleaner ports is an explicitly listed factory defect mode.

### The ejector tee is directional and it does fail
- FCA precedent on the 1.4L turbo: **the tee installed backwards** set P1CEA; remedy was harness **04627485AC**.
- A documented Giulia P1CEA resolved to a **missing/defective T-junction check valve in an aftermarket Eurocompulsion intake kit**: *"My kit was missing the valve and it was easy to blow either way."*
- **Functional test worth stealing:** one side of the "T" should be **much harder to blow through** than the other.

> ⚠️ That resolved case was an **aftermarket-intake** problem, not a stock failure. Its value is (a) the blow-test technique and (b) the warning that **any aftermarket intake on GME-T4 must correctly reinstate the boost purge tee.**

### On a stock Stelvio with P1CEA, work this order
PCM software level (**TSB 18-023-23 REV. B** — on-platform, authoritative, attributes P1CEA to PCM software on the 2023 GU Stelvio 2.0T) → **push-pull-push both EVAP quick connects at the air cleaner cover** (technique from TSB 25-002-23, a Grand Cherokee 4xe bulletin on the same engine family — *"EVAP vacuum lines not fully secured"*, LOP 0.2 hr) → ejector tee orientation and directional blow test → CAC duct / air cleaner port flash → FTP sensor circuits → purge solenoid.

---

# 7. Two cautions against the parts cannon

**1.** A 2018 Stelvio Ti owner: *"My dealer replaced every component of the evap purge system to resolve a CEL. Another shop properly diagnosed the leak detector pump, a $110 part was the culprit."* He describes the method plainly: *"they looked up the most likely cause of the code and replaced that part, when that didn't fix the issue, they replaced the second most likely cause, then the third, then the fourth… the dealer eventually gave up."* Same thread: a dealer quoted **$1,019.45** ($579.45 parts + $440.00 labour) for purge solenoid + canister to a customer **who had never read his own codes**.

**2.** NHTSA **ODI 11705307** (2019 Stelvio): *"diagnosed with an EVAP system leak; however, **the origin of the leak could not be determined**. The contact stated that the vehicle later failed to start… towed to an independent mechanic, where it was diagnosed with a **defective fuel pump**."*

---

# 8. Context: this VIN is in the fuel pump recall

**NHTSA 25V586000 / Mopar 93C** — 53,849 vehicles, 2017-19 Giulia + **2018-19 Stelvio**. *"The fuel pump may fail, which can result in a loss of fuel flow and loss of drive power."* Interim letters Oct 2025; **final remedy anticipated July 2026**; parts widely backordered.

⭐ **The flagship dealer-tech item:** the 93C failure presents as **"Service Electronic Throttle" / "Service Throttle Position"** plus limp mode and stalling — **not** as a fuel message. Owner-reported DTCs on the same cars: `P0087`, `P008A` (low rail pressure), `P01CA`, `P00C6`, misfires `P0300/P0302/P0303`.

> **On a Giorgio 2.0T, "Service Electronic Throttle" should raise fuel delivery, not the throttle body.**

Also relevant: one complaint theorises stalling *"immediately after fueling because the failing, recalled pump cannot maintain proper pressure to compensate for standard EVAP canister vapor purging cycles."* That is owner theory, not a finding — but the after-fuelling-stall pattern is a real correlation, since a saturated canister dumps a large vapour slug post-refuel and a marginal pump has no headroom.

---

# 9. Useful negative result

Keyword-binning all 174 Stelvio (MY18-21) and 193 Giulia (MY17-20) NHTSA complaints: EVAP/purge/P045x appears in **2 of 174** Stelvio and **1 of 193** Giulia. **EVAP on Giorgio is a nuisance/maintenance issue, not a safety-complaint theme.** Do not let complaint volume mislead triage — NHTSA is a safety database and systematically under-reports MIL-only emissions faults.

Also: **CarComplaints.com is unusable for this platform** — it reports *zero* complaints on file for the Stelvio for any model year. Low US sales volume means the site never accumulated data. Do not cite its counts.

---

# 10. Corrected diagnostic order for this car

1. **Check the EVAP canister filter** for restriction (TSB 9100468). Cheap, scheduled, precedes everything.
2. **KOEO actuator-test the purge valve and vent valve in MES.** Note the shop's logs already show the purge valve completing six actuations in Sept 2025 — so weight this toward the vent/canister side.
3. **Smoke test** to physically localise. EVAP is low-pressure — over-pressurising damages components.
4. **Distinguish ESIM from canister before ordering parts** (TSB 9100469).
5. **Verify the repair with wiTECH SLVT.** A road test cannot confirm it (TSB 18-089-19). This is non-negotiable if the goal is a confirmed fix rather than a hopeful one.

**Do not:** replace the purge solenoid alone (low yield, and this one actuates); condemn the gas cap (low hit rate on this platform; one owner spent ~$144 on a dealer cap with no change); or read a clean post-clear scan as proof of repair.

---

## Sources retrieved
- TSB 18-089-19 (SLVT): `static.nhtsa.gov/odi/tsbs/2019/MC-10169219-9999.pdf`
- TSB 9100469 (ESIM vs canister): `static.nhtsa.gov/odi/tsbs/2024/MC-11011985-0001.pdf`
- TSB 9100468 (canister filter), TSB 18-023-23 REV. B (P1CEA / PCM software), TSB 25-002-23 (quick connects)
- Recall 25V586000 / Mopar 93C

**Could not verify:** an FCA service-manual "Description and Operation" for the GME-T4 EVAP system (the dual-path description in §6 is reconstructed); the water-ingress EVAP TSB and shield; whether Giulia/Stelvio NA uses LDP, ESIM or NVLD terminology consistently; Alfa fitment for purge solenoid `68337662AC` and vent valve `5281586AB`.
