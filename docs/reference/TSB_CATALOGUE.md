# Alfa Romeo Stelvio / Giulia TSB Catalogue (NHTSA)

**Captured:** 2026-08-27. **295 unique NHTSA manufacturer-communication records → 201 unique FCA bulletin numbers.** All 295 PDFs retrieved; 287 yielded extractable text (8 are image-only scans).

Full index CSV, PDFs and extracted text are in the session scratchpad:
`…\scratchpad\AlfaRomeo_TSB_index.csv`, `…\scratchpad\pdfs\`, `…\scratchpad\txt\`

Groups: Electrical/BCM/Network **103** · Transmission/Driveline **26** · EVAP/Fuel **21** · Body/Glass/Lighting **16** · Engine/Cooling **15** · Equipment/Infotainment **13** · Suspension/Steering **5** · Brakes **1** · Restraints **1**.
*(Grouping is a keyword heuristic — treat the label as a filter aid, not authority.)*

---

# ⭐ 1. The communication cascade — settled, and my earlier ranking was wrong

## There is NO ground-strap TSB

A full-text regex sweep across all 287 readable PDFs for `ground strap|cable|braid|point|stud|eyelet|jumper`, `G\d{3}`, and body/engine/chassis ground found **nothing describing a strap as a failing part**, and no inspection or replacement bulletin targeting one.

> **The 13 NHTSA owner complaints remain uncorroborated by any FCA publication.** The mechanism is still sound and the complaints are still real — but this is owner-reported, not documented, and it should not have been ranked first.

**Three STAR cases document the same failure mode by different mechanisms**, and two are better first tests.

## `S2008000032` — the closest published match
2020-04-07 · NHTSA 10175659 · *"EVIC Displays Multiple Warning Messages"*
`https://static.nhtsa.gov/odi/tsbs/2020/MC-10175659-9999.pdf`

> *"EVIC displayed Service Electronic Throttle Control, Service Adaptive Headlamp System, Start & Stop Not Available, and Parking Light Out Messages… Scanned the vehicle and found multiple active DTCs. Inspect common circuitry inline connector **XY201** was loose secured. Inspect grounds **G003A/G003B** clean and secure involved frame grounds. Cleared DTCs… **no parts required.**"*

A multi-module, multi-warning, multi-DTC cascade resolved by securing one inline connector and cleaning two frame grounds. **This is the document to hand the technician.**

⚠️ NHTSA associates it only with **2020 Stelvio**, though the GU platform circuitry is shared.

## `S1808000005` — the test the ground-strap hypothesis would miss
2020-04-04 · NHTSA 10175655 · *"No Start, Multiple Modules Are Not Responding"* · **2018/2019/2020 Stelvio**
`https://static.nhtsa.gov/odi/tsbs/2020/MC-10175655-9999.pdf`

> *"For conditions of a no start with multiple modules not responding, inspect all **power feed** circuits to the BCM including the stand alone fuse… Check and correct **B+ A0 circuit** to the BCM Or 20 Amp standalone fuse as needed. **For GU / Stelvio inspect the F82 fuse in the rear PDC to the BCM A901 circuit.**"*

> **This attacks the SUPPLY side, not ground.** A BCM losing its A901 feed drops off the bus and every module gatewaying through it throws U-codes — which is exactly this car's module list. **Cheap, high-yield, and a ground-only hypothesis never gets there.**

## `S1708000262 REV. A` — spread terminals
2020-11-17 · NHTSA 10184414 / 10184714 / 10224037 · *"Check Engine Lamp Is On, Intermittent Module CAN Private Or LIN BUS Codes"*

> *"Vehicle setting CAN private or LIN BUS DTC's… Inspect the involved connector terminal for **pushed out, or spread terminals**."*

## Supporting
- **`S1408000384 REV. J`** (latest of 7 revisions; 2026-03-04) — IBS/battery sensor. Contains **`U113E` "Lost communication with intelligent battery"** LIN diagnostics: **wiggle the IBS 2-way harness takeout and watch whether U113E responds** — if it does, the harness is the fault. Also carries the **"DO NOT BLIND CHARGE"** rule.
- **`S2308000004`** (2023-01-19) — *"Vehicle Cranks, No Start"*: verify all ECM/PCM B+ feeds **and grounds**.
- **`S2018000004`** (2020-04-15) — PCM sets **`U04B1-00` Invalid Data Received From Battery Monitor Module** after a **W05** flash. Fix is a **BCM restore-configuration routine**, not circuit diagnosis. Rule out if this car ever had W05 done.
- **`S2308000089`** (2023-07-21) — replacement **BCM front harness** has 2 extra connectors and a fuse holder vs the original. A trap during harness replacement.
- **`9004386`** (2021-06-09) — contact FCA for a **repair kit** before replacing a body harness.
- **`CSN 64C`** (2026-01-06) — PCM harness misrouted and exposed to abrasion, ~3,600 vehicles. **Giulia 2.9L QV only** — does not apply to a Stelvio, but it is the only harness-damage campaign in the set.
- **`S2108000163`** (2021-07-09) — module-replacement / PROXI sequencing when replacing several modules at once.

⚠️ **`9100226` "Connector kit"** (NHTSA 10244348 / 10248509) is **image-only, unread**. Its API summary references Mopar connector repair kit `68018957A$`. Potentially relevant here — needs OCR or a human read:
`https://static.nhtsa.gov/odi/tsbs/2023/MC-10244348-9999.pdf`

---

# 2. EVAP

See `docs/research/EVAP_STELVIO.md` §0 for the clinical ordering. Index entries:

| Bulletin | Date | Content |
|---|---|---|
| **`S2125000002`** | 2021-06-18 | ⭐ **P0456/P0455/P0441/P1CEA — check the recirculation-line mid-point quick-connect first**, then re-run the wiTECH EVAP leak test |
| **`S2125000003`** | 2021-07-29 | P1CEA alone — borescope the **Ejector Tee** in the clean-air duct for debris |
| **`9100471`** | 2025-03-17 | ⭐ **Supersedes/extends 9100469.** Hard-to-fill tree; canister flooded with **fuel** from a disconnected internal vapour line at the **FDM port**; replace **both** canister and ESIM |
| **`9100469`** | 2024-12-16 | ESIM is a separate part from the canister — replace only the ESIM if only it is at fault |
| **`9100468`** | 2024-12 | Canister **filter** restriction check; references customer-paid Mopar **Dual EVAP Filter kit** (`25-009-24`) for dusty conditions |
| **`9100325 Rev 1`** | 2025-10-02 | Purge control valve; kinked or mis-connected purge hoses at ejector tees, purge solenoid, intake |
| **`18-048-23`** | 2023-04-15 | ⭐ **Supersedes `18-089-19`** — the current wiTECH SLVT bulletin |
| `18-089-19` | 2019-11-01 | original SLVT bulletin (superseded) |

**The `18-0xx` PCM flash family** (`18-030-17` → REV. B → `18-097/098/101/103-19` → `18-024/025/026/027-20` → `18-045/046-23`) repeatedly lists **P0440/P0441/P0455/P0456** in its fixed-DTC lists. Latest of that number is **`18-030-17 REV. B`**.

> ⚠️ **No water-ingress or splash-shield EVAP bulletin exists.** Swept for `splash|shield|deflector|water ingress|water intrusion|moisture|flooded|debris shield` — the only flooded-canister content is `9100471`, and it is **fuel**, with no shield in the remedy. The only water-infiltration bulletins are `S2623000037` / REV. A, which cover **headlights and lamps**.

---

# 3. Transmission and AWD

Less here than elsewhere, and **nothing on transfer-case hardware failure.**

## `S2621000003 REV. A` — the substantive 8HP document
2026-03-09 · NHTSA 11030138 · **explicitly 2017-2026 Giulia (GA) and 2018-2026 Stelvio (GU)**
`https://static.nhtsa.gov/odi/tsbs/2026/MC-11030138-9999.pdf`

Covers 8HP45/50/70/75/90/95 with `P07E4`, `P1DB2`, `P0716`, `P1B14`, `P0733`, `P1D90`, `P1DB7`, `P1B13`.

Key content:
- **Burnt fluid odour is normal and does not justify replacement.**
- **Fine metallic content is normal wear.**
- ⭐ **Valve body replacement is the first option before transmission replacement.**
- For `P1B13`/`P1B14`, check the **MPR cable is not stuck**.
- For `P0733`, follow TSB **`21-029-25 REV. A`** (8HP75) for the **clutch-D repair** first.

## `S1821000001 REV. A` — the cheap AWD check
2021-04-16 · gear-ratio DTCs, shift concerns, shudder.

> Root cause addressed is **tyre circumference mismatch on AWD — must be within 1/8"**, or it causes shudder, bind, and **transfer case damage**.

**Rule this out before condemning any driveline hardware.**

## `S2008000078 / REV. A` — a U-code that isn't a bus fault
2020-05-30 / 2022-07-22. **`U0102` "Lost Communication With Transfer Case Control Module/AWD" active on a RWD car** after ECM replacement or flash — caused by **AWD software loaded on a RWD vehicle**. A configuration fault wearing a communication code's clothes.

## Other
- TCM flashes: `21-032-17` (the only one naming 8HP explicitly), `21-044-19`, `21-045-19`, **`21-032-20`** (latest, 2020-04-16).
- **`CSN W05`** (2020-03-10) — PCM reprogram campaign; ties to the `U04B1` STAR case above.
- **`9004150`** (2019-10-17) — PTU/stubshaft: if replacing the stubshaft for an ATX fluid leak, **do not** replace the PTU seals.

> **No TSB addresses Q4 transfer case internal failure, actuator, or propshaft.**

---

# 4. Using the NHTSA API — working notes

The chain from `docs/research/GIORGIO_PLATFORM.md` §7 is correct, with three refinements learned the hard way:

1. **`pagination.total` counts vehicle trim records (1-2), not bulletins.** The TSBs are nested in `results[].safetyIssues.manufacturerCommunications[]`.
2. **The PDF URL is one level deeper than the docs imply:** `results[].manufacturerCommunications[].associatedDocuments[].url` — *not* `results[].associatedDocuments[]`.
3. **`static.nhtsa.gov` rate-limits at roughly 95 concurrent fetches (403).** Serial with ~0.35 s delay ran 200/200 clean.

**Giulia 2020 does not exist as a vehicle record in NHTSA's database** — `byYmmt` returns 0, and `products/vehicle/models?modelYear=2020` returns only STELVIO across all issue types. This is a gap on NHTSA's side, not a query error, and it is **recoverable**: 134 of the 295 records list "2020 GIULIA" in `associatedProducts`.

Per-year coverage from `associatedProducts`: Giulia 2017 **171** · 2018 **148** · 2019 **149** · 2020 **134**; Stelvio 2018 **142** · 2019 **157** · 2020 **153**.

## ⚠️ Duplicate-number trap
NHTSA lists the same FCA bulletin under multiple ids with **different formatting of the same number** — `18-030-17` vs `1803017`, `08-045-20 REV. A` vs `0804520REVA`. Normalising took 295 records to 201 bulletins. **A naive dedupe on the raw string leaves ~70 phantom rows.** The CSV's `duplicate_nhtsa_ids` column preserves the mapping.

## Revision chains present
`S1408000384` REV. J > I > H > G > F > base (7 records) · `31-001-25` REV. B > A > base, superseding `31-001-24` > `31-001-23` > `31-002-22` (aluminium corrosion, annual reissue) · `08-103-20` REV. A · `08-045-20` REV. A · `08-026-17` REV. A · `18-030-17` REV. B · `02-002-25` REV. A · `S2623000037` REV. A · `08-394-25` REV. A · `S1708000118` REV. B > A · `S1809000007` REV. C > A · `S2008000113` REV. · `S2008000078` REV. A · `S1708000262` REV. A · `S2621000003` REV. A · `S1821000001` REV. A · `S1908000028` REV. A · `S2408000056` REV. A · `S2208000011` REV. B · `S228A000017` REV. A · `S1705000002` REV. A · `9100325` Rev 1 · `08-027-17` REV. B.

## Not read
8 records are **image-only PDFs with no extractable text**, retrieved but not characterised: `10236969` (9100142 mirror) · `10242717` (9100196 fluids) · `10243208`/`10243209` (warranty) · **`10244348`/`10248509` (9100226 connector kit — potentially relevant to §1)** · `10244356` (9100229 lifters) · `11034335` (112842 bolt).
