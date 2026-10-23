# Alfa Romeo Stelvio / Giulia TSB Catalogue (NHTSA)

# 0. The machine-readable catalogue (cuore/data/tsb_catalogue.json)

`cuore/data/tsb_catalogue.json` is the structured twin of this document: one row per bulletin, recall, CSN or lookup placeholder for the 2018 Stelvio 2.0T Q4 (VIN ZASFAKPN5J7B88115), `updated` 2026-10-15, 99 Stelvio rows (`vehicle_scope` this_model) plus 41 sibling-engine analogue rows (see *Sibling-engine analogues* below). Row ids are stable (the per-VIN checklist is keyed on them); extra fields are tolerated.

**Schema.** Required: `id`. Core fields: `kind` (tsb/recall/csn/campaign/extended_warranty/emissions/field_report), `number`, `nhtsa_id`, `title`, `date`, `summary`, `condition`, `remedy`, `systems` (display tags), `dtcs`, `links` ([{label,url}] or null), `applies`, `source`, `verified`. Cross-reference fields (optional, never invented, empty when the research is silent): `components` (parts/part numbers inspected, replaced or flashed), `symptoms` (plain-words conditions), `repair_implied` (`flash` | `replace:<part>` | `procedure:<name>` | `inspect` | `software_update` | `none`), `depends_on_systems` (keys from `mes.systems.SYSTEMS`, e.g. evap, fuel, engine_management, air_intake_boost, transmission_driveline).

**Semantics.** `applies`: `yes` = scope covers this car; `no` = documented as a different engine/model year/trim; `vin_check` = scope plausible or unconfirmed, only a VIN lookup settles it. `verified`: true only when the source document itself was read; false when only indexed or inferred (summary-only rows).

**Corrections of 2026-10-15.**
- **18-030-17**: the opened NHTSA copy (REV. D, id 10216318) is Giulia-only (2017, built on or before 2017-06-29); Stelvio is not listed, so applicability is `vin_check`, not assumed.
- **18-026-20** is the directly applicable 2018 Stelvio 2.0T ECM flash. It lists P1CEA/P24D6 but not P0440/P0455/P0456.
- **18V636** (2.0L misfire/catalytic converter recall, ECM software update) covers 2018 Stelvio and is the best lead for "was the ECM ever reflashed"; VIN check required.
- **W05** (CSN, PCM reprogram for turbo oil-feed weep) covers 2018-2019 Stelvio; if done, the ECM was already reflashed.

| Number | Kind | Title | Applies | repair_implied | Link |
|---|---|---|---|---|---|
| 18-030-17 REV. B | tsb | Flash: Powertrain Diagnostic and System Improvements (NHTSA copy is REV. D, Giulia-only) | vin_check | flash | [NHTSA TSB 10216318 (REV. D, Giulia)](https://static.nhtsa.gov/odi/tsbs/2017/MC-10216318-9999.pdf) |
| 18-048-23 | tsb | EVAP small-leak verification requires wiTECH SLVT | yes | procedure:wiTECH SLVT | [NHTSA TSB 10236933](https://static.nhtsa.gov/odi/tsbs/2023/MC-10236933-9999.pdf) |
| 9100471 | tsb | Hard to fill / EVAP canister flooded with fuel | yes | replace:vapour canister and ESIM | none on file |
| 18-026-20 | tsb | Flash: Powertrain Control Module (PCM) Updates | yes | flash | [NHTSA TSB 10174245](https://static.nhtsa.gov/odi/tsbs/2020/MC-10174245-9999.pdf) |
| CSN W05 | csn | Customer Satisfaction Notification W05 - Reprogram Powertrain Control Module (turbo oil-feed weep) | vin_check | flash | [NHTSA CSN W05 10175524](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175524-9999.pdf) |
| 21-035-20 | tsb | Flash: Transmission Control Module (TCM) Update | yes | flash | [NHTSA TSB 10176569](https://static.nhtsa.gov/odi/tsbs/2020/MC-10176569-9999.pdf) |
| 18-089-19 | tsb | wiTECH SLVT - P0456 EVAP System Small Leak | yes | procedure:wiTECH SLVT | [NHTSA TSB 10169219](https://static.nhtsa.gov/odi/tsbs/2019/MC-10169219-9999.pdf) |
| STAR S2025000004 | tsb | P0456/P0455 analysis with wiTECH SLVT (dealer case record) | vin_check | procedure:wiTECH SLVT | [NHTSA 10175692](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175692-9999.pdf) |
| 18-023-23 / 18-041-23 / 18-045-23 | tsb | Flash: PCM Updates (P1CEA) - later model years | no | flash | [NHTSA TSB 10236922 (18-045-23)](https://static.nhtsa.gov/odi/tsbs/2023/MC-10236922-9999.pdf) |
| 18-017-21 | tsb | Flash: PCM Updates (replace oil vapor recovery tube) | no | replace:blowby tube K68499935AA and connector cap K68393276AA | [NHTSA TSB 10220605](https://static.nhtsa.gov/odi/tsbs/2021/MC-10220605-9999.pdf) |
| 18-088-19 | tsb | Flash: PCM Updates | no | flash | [NHTSA TSB 10169218](https://static.nhtsa.gov/odi/tsbs/2019/MC-10169218-9999.pdf) |
| S2018000004 / S2018000011 / 01-001-20 / D-17-21 | tsb | STAR/warranty/oil-monitor items listed for Stelvio | vin_check | none | [recallcheck.net listing (third party)](https://recallcheck.net/tsb/1480) |
| 18V636 | recall | 2.0L engine misfire may overheat catalytic converter / damage wiring | vin_check | software_update | [Source](https://www.nhtsa.gov/recalls?nhtsaId=18V636) |
| 18V635 | recall | Coolant hose (Quadrifoglio) | no | replace:coolant hose | [Source](https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018505) |
| 18V147 | recall | Wiper motor limited to low speed | vin_check | replace:wiper motor | [Source](https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018116) |
| 18V203 | recall | Liftgate wiring/switch water intrusion | vin_check | procedure:add sealing / water protection | [Source](https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018150) |
| 18V205 | recall | BCM water intrusion | vin_check | procedure:add sealing at A-pillar / HVAC box | [Source](https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2018151) |
| 17V823 | recall | Contaminated brake fluid | vin_check | inspect | [Source](https://www.nhtsa.gov/recalls?nhtsaId=17V823) |
| 19V148 | recall | Adaptive cruise cannot be disabled after wheel-slip event | vin_check | software_update | [Source](https://www.nhtsa.gov/recalls?nhtsaId=19V148) |
| 19V551 | recall | BCM fuel level reads high | vin_check | software_update | [Source](https://www.nhtsa.gov/recalls?nhtsaId=19V551) |
| 23V382 | recall | Carbon ceramic brake rotor fracture | no | software_update | [Source](https://www.nhtsa.gov/recalls?nhtsaId=23V382) |
| 24V510 | recall | Seat belt buckle switch sensor connector | vin_check | procedure:repair connector | [Source](https://www.nhtsa.gov/recalls?nhtsaId=24V510) |
| 25V586 (FCA 93C) | recall | Fuel pump failure | vin_check | replace:fuel delivery module | [NHTSA recall 25V586](https://www.nhtsa.gov/recalls?nhtsaId=25V586) |
| 2024379 | recall | Incorrect tire pressure/size labels | no | none | [Source](https://recalls-rappels.canada.ca/en/alert-recall/transport-canada-recall-2024379-fiat-chrysler-automobiles) |
| 2024767 | recall | Brake booster input rod | no | none | [Source](https://mobile.guideautoweb.com/en/recalls/2024767) |
| U24/U34/U36 | csn | Customer-satisfaction handling for 2018 wiper, liftgate, BCM recalls | vin_check | none | [Source](https://static.nhtsa.gov/odi/rcl/2018/RCMN-18V205-2178.pdf) |
| - | campaign | Standalone CSN/service campaign, extended warranty, EVAP or uConnect special coverage | vin_check | none | [Source](https://www.mopar.com/en-us/my-vehicle/recalls/search.html) |
| - | emissions | CARB/EPA emissions recall | vin_check | none | [Source](https://www.nhtsa.gov/recalls) |
| 9002519 | tsb | 82212076, 82203694 - Fabric Cleaner This "fabric cleaner" is not intended for sale in California, the otc... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2018/MC-10129008-9999.pdf) |
| 05152029 | tsb | Washer Fluid Level Sensor Prior to replacing this part due to "Low Washer Fluid" tell tale light on the... | vin_check | - | none on file |
| 9003696 | tsb | Door Hinge Assembly Side door hinge noisy. Only replace the door hinge with the integral check device. Do... | vin_check | - | none on file |
| 9003109 | tsb | Washer Fluid Level Sensor Prior to replacing this part due to "Low Washer Fluid" tell tale light on the... | vin_check | - | none on file |
| 9003293 | tsb | A/C Pressure Transducer A/C inoperative and diagnosis leads to pressure transducer. Call Steve Rice at... | vin_check | - | none on file |
| 08-044-19 | tsb | Flash: Anti-Lock Brake System (ABS) Module Diagnostic and System Updates This bulletin involves... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2019/MC-10162530-9999.pdf) |
| 08-081-19 | tsb | RAN RAP RAG and RSD 2.5 Radio Software Enhancements This bulletin involves inspecting and if required,... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2019/MC-10166576-9999.pdf) |
| 9003220 | tsb | RADIO [RES] - New and/or Service Exchange For RES radio concerns. Use the wiTECH 2.0 and inspect the radio... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2019/MC-10166537-9999.pdf) |
| 9004130 | tsb | Battery Prior to replacing the battery, please call Cary Powell at (248) 500-7751. If no response in 15... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2019/MC-10166551-9999.pdf) |
| 31-004-19 | tsb | Authentic Mopar® Glass Replacement This bulletin involves discussing FCA US LLC position with regard to... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2019/MC-10169246-9999.pdf) |
| 31-005-19 | tsb | Use of Aftermarket Parts This bulletin involves discussing FCA US LLC position with regard to collision... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2019/MC-10169249-9999.pdf) |
| 3100319 | tsb | Use of Salvage/Recycled Parts This bulletin involves discussing FCA US LLC position with regard to... | vin_check | - | none on file |
| 3100619 | tsb | Repair Parts Used For Structural Repairs This bulletin involves discussing FCA US LLC position with regard... | vin_check | - | none on file |
| 9004022 | tsb | Air Suspension Components Star Parts Catalog has been updated to show individual service parts for the... | vin_check | - | none on file |
| S2008000010 | tsb | Apple Carplay Inoperative Or Not Working, Phone Not Pairing, Carplay Lockup Or Freeze. | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10173305-9999.pdf), [NHTSA PDF (10178642)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10178642-9999.pdf) |
| S2008000013 | tsb | Key Programming, Security Pin Request, Pin Invalid | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10173328-9999.pdf) |
| S2008000017 | tsb | ESS Unavailable In Areas 5,250 Feet (1600 Meters) Above Sea Level | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10174135-9999.pdf), [NHTSA PDF (10175055)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175055-9999.pdf) |
| 08-029-20 | tsb | RAN RAP RAJ RAG and RSD Radio Software Enhancements This bulletin involves inspecting and if required,... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10174204-9999.pdf), [NHTSA PDF (10175124)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175124-9999.pdf) |
| S2008000021 | tsb | PCM ESS Inhibits List Show Driver Door Condition Inhibiting The S&S | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10174150-9999.pdf), [NHTSA PDF (10175070)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175070-9999.pdf) |
| S1808000005 | tsb | No Start, Multiple Modules Are Not Responding | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175655-9999.pdf) |
| S2019000002 | tsb | Hands On Steering Wheel Message In EVIC | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175674-9999.pdf) |
| 18-039-20 | tsb | Possible Driveability Issues due to the Winter-Blend Fuel into the Warmer Season | yes | none | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175733-9999.pdf) |
| 08-049-20 | tsb | Charging System, Battery Diagnostic Tools and Warranty This information only bulletin discusses using the... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175735-9999.pdf) |
| 23-015-20 | tsb | Disinfectant Solution Recommended for COVID-19 | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10175743-9999.pdf) |
| 08-065-20 | tsb | RAN RAP RAG and RSD 2.5 Radio Software Enhancements This bulletin involves inspecting and if required,... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10177540-9999.pdf) |
| S2008000093 | tsb | Blind Spot Or Park Assist Warnings, False Activation | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10177504-9999.pdf) |
| S2008000113 | tsb | No Start Intermittently, Vehicle Requires Multiple Keyless Push To Start Attempts To Start Vehicle | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10180203-9999.pdf), [NHTSA PDF (10194007)](https://static.nhtsa.gov/odi/tsbs/2021/MC-10194007-9999.pdf) |
| 9003637 | tsb | USB PORT, Media Hub For Android Auto and Apple Carplay issues, do not replace this part. Android Auto and... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10180177-9999.pdf) |
| S1908000028 | tsb | (Rev. A) Power Inverter Load Ratings | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184399-9999.pdf), [NHTSA PDF (10184699)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184699-9999.pdf) |
| S1908000102 | tsb | (Rev. A) Power Inverter Load Ratings | vin_check | - | none on file |
| S2018000012 | tsb | Check engine lamp on. Fault code P0244- TURBOCHARGER/SUPERCHARGER WASTEGATE SOLENOID "A" RANGE/PERFORMANCE... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184402-9999.pdf), [NHTSA PDF (10184702)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184702-9999.pdf) |
| S1708000262 | tsb | (Rev. A) Check Engine Lamp Is On, Intermittent Module CAN Private Or LIN BUS Codes | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184414-9999.pdf), [NHTSA PDF (10184714)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184714-9999.pdf) |
| 9004335 | tsb | Turbocharger If the turbo is being replaced for an oil leak concern, please inspect the area around the... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184380-9999.pdf), [NHTSA PDF (10184680)](https://static.nhtsa.gov/odi/tsbs/2020/MC-10184680-9999.pdf) |
| 01-001-21 | tsb | Oil Change Monitor Displaying Prematurely This bulletin involves resetting the oil life monitor and if... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2021/MC-10188822-9999.pdf) |
| S2123000016 | tsb | Creak Noise From Front Of Vehicle | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2021/MC-10190628-9999.pdf) |
| S1809000007 | tsb | Customer complaint may include engine oil leak/consumption. | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2021/MC-10190667-9999.pdf) |
| 9004009 | tsb | Transmission Kit with Torque Converter 1. All Promaster (VF) 3.6L/62TE equipped vehicles. If the... | no | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2022/MC-10221097-9999.pdf) |
| S16080002261 | tsb | Battery Tester Warranty Code Procedures, Medtronic Update Process | vin_check | - | none on file |
| S1821000001 | tsb | Gear Ratio DTC?s, Transmission Shift Concerns, Does Not Shift At Times, Shudders | vin_check | - | none on file |
| S1608000226 | tsb | Battery Tester Warranty Code Procedures, Midtronics Charger Update Process | vin_check | - | none on file |
| S1708000118 | tsb | Battery Drain Concern, Dual USB Port Normal Operational Draw, Extended Illumination After Key Off | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2021/MC-10194017-9999.pdf), [NHTSA PDF (10220697)](https://static.nhtsa.gov/odi/tsbs/2022/MC-10220697-9999.pdf) |
| 9004386 | tsb | WIRING, Body Before replacing this harness, please contact FCA Redacted Content to see if a repair kit is... | vin_check | - | none on file |
| S2109000004 | tsb | Issue involves overheating, running hot, coolant leaks and related symptoms after a Mopar replacement... | vin_check | - | none on file |
| S2108000163 | tsb | No Start, Cannot Complete Module Replace, Proxi Or Module Proxi Configuration | vin_check | - | none on file |
| S2108000198 | tsb | Media Device Connection Guidelines For Bluetooth, Apple CarPlay, Android Auto Or USB To The Radio Head Unit | vin_check | - | none on file |
| S2208000073 | tsb | No Start, After Flash And Or PCM Replace, DTC P0513 Invalid Skim Key Setting | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2022/MC-10212318-9999.pdf), [NHTSA PDF (10220715)](https://static.nhtsa.gov/odi/tsbs/2022/MC-10220715-9999.pdf) |
| S2209000004 | tsb | If a Mopar oil filter is not available, use a filter that meets or exceeds USCAR36 specification and is... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2022/MC-10227983-9999.pdf) |
| S2223000047 | tsb | ACC Does Not Operate. Start Stop Unavailable, ACC Unavailable Service Required Messages. C1452-86 Engine... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2022/MC-10221417-9999.pdf) |
| 3100122 | tsb | Approved Use of Weld Through Primers This bulletin documents the FCA US LLC position regarding the use of... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2022/MC-10225287-9999.pdf), [NHTSA PDF (10225424)](https://static.nhtsa.gov/odi/tsbs/2022/MC-10225424-9999.pdf) |
| S2218000018 | tsb | Check engine lamp/Mil lamp-on. Engine misfires. | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2022/MC-10225219-9999.pdf), [NHTSA PDF (10225356)](https://static.nhtsa.gov/odi/tsbs/2022/MC-10225356-9999.pdf) |
| 0100122 | tsb | Oil Change Monitor Displaying Prematurely This bulletin involves resetting the oil life monitor and if... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2022/MC-10226029-9999.pdf) |
| 31-002-22 | tsb | Aluminum Body Panel Corrosion Repair Aluminum corrosion or bubbling along the leading edge of hood, hinges... | vin_check | - | none on file |
| 3100123 | tsb | Aluminum Body Panel Corrosion Repair Aluminum corrosion or bubbling along the leading edge of hood, hinges... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10234468-9999.pdf) |
| S1408000384 | tsb | Start Stop Charging Warning Lamp Illuminated On, Intelligent Battery Sensor (IBS) State of Charge (SOC)... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10234420-9999.pdf), [NHTSA PDF (10251783)](https://static.nhtsa.gov/odi/tsbs/2024/MC-10251783-9999.pdf) |
| 0700723 | tsb | Water Quality When Mixed With Engine Coolant | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10239957-9999.pdf) |
| 9100196 | tsb | Lubrication and Maintenance Fluids If MOPAR fluids and chemicals are not readily available, please review... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10242717-9999.pdf) |
| 93023 | tsb | Warranty Bulletin D-16-03 - "Can / Am" Warranty Coverage - 594 / 595 / 596 WCC (Rev. B) | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10243208-9999.pdf) |
| 93120 | tsb | FCA Caribbean Warranty Bulletin ID-23-20 "Can / Am" Warranty Coverage - 594 / 595 / 596 WCC | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10243209-9999.pdf) |
| 9100226 | tsb | Connector kit Before ordering this connector repair kit 68018957A$, check it in the Mopar Connector Repair... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10244348-9999.pdf) |
| 9100229 | tsb | LIFTER, Hydraulic Roller Deactivating Please do not replace MDS lifters because the disconnecting pin is... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2023/MC-10244356-9999.pdf) |
| 31-001-24 | tsb | "Aluminum Body Panel Corrosion Repair Aluminum corrosion or bubbling along the leading edge of hood,... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2024/MC-11005320-0001.pdf) |
| 01-002-24 | tsb | "Oil Change Monitor Displaying Prematurely Customers may experience the following: ● The oil change light... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2024/MC-11010645-0001.pdf) |
| 9100469 | tsb | VAPOR CANISTER If an issue is detected with the EVAPORATIVE SYSTEM INTEGRITY MODULE DETECTOR and not the... | yes | replace:ESIM only (not the vapor canister, when the ESIM is the faulty part) | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2024/MC-11011985-0001.pdf) |
| S1705000002 | tsb | Front Brake Pulsation and/or Clunk Noise | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2025/MC-11013151-0001.pdf) |
| 31-001-25 | tsb | Aluminum Body Panel Corrosion Repair Aluminum corrosion or bubbling along the leading edge of hood, hinges... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2025/MC-11022003-0001.pdf), [NHTSA PDF (11022012)](https://static.nhtsa.gov/odi/tsbs/2025/MC-11022012-0001.pdf) |
| 9100325 | tsb | Before replacing any parts please refer to SOL S2518000008 if it applies to the vehicle you are working on... | yes | inspect | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2025/MC-11024035-0001.pdf) |
| S2621000003 | tsb | The vehicle will exhibit a service transmission/check engine warning indicator for the following... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2026/MC-11030138-0001.pdf) |
| 01-001-26 | tsb | Oil Change Monitor Displaying Prematurely Customers may experience the following: ● The oil change light... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2026/MC-11032849-0001.pdf) |
| S2623000037 | tsb | Condensation Or Water Infiltration In Headlights, Daytime Running Lights (DRL), Turn Signals, Fog Lights,... | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2026/MC-11033309-0001.pdf), [NHTSA PDF (11034923)](https://static.nhtsa.gov/odi/tsbs/2026/MC-11034923-0001.pdf) |
| 112842 | tsb | BOLT - HEX FLANGE HEAD | vin_check | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2026/MC-11034335-0001.pdf) |
| 22D Combo | emissions | Emissions Recall 22D - On Board Diagnostics - Dealer Notification | no | - | [NHTSA PDF](https://static.nhtsa.gov/odi/tsbs/2026/MC-11037271-0001.pdf), [NHTSA PDF (11037356)](https://static.nhtsa.gov/odi/tsbs/2026/MC-11037356-0001.pdf) |


**Coverage (NHTSA merge, 2026-10-15).** The NHTSA flat files TSBS_RECEIVED_2015-2019, 2020-2024 and 2025-2026 (static.nhtsa.gov/odi/ffdd/tsbs) hold 144 records for the MY2018 Stelvio, which collapse to 81 distinct manufacturer numbers (revisions and duplicate component records share one row). Of the 144 records, 96 have a PDF on NHTSA and 48 do not; 6 of the PDFs are image-only (no extractable text; their rows carry the flat-file summary only). Pre-2015 flat files were not checked. Rows added from the flat file are `verified: false` and `applies: vin_check` unless the bulletin was opened (EVAP/ECM set: 9100469, 9100325, 18-039-20, 18-089-19, 18-048-23, 18-026-20, 18-017-21) or its title excludes the car (22D is 2.9L Quadrifoglio only; 9004009 is Promaster). Row counts are in the header of `tsb_catalogue.json` (`sources` lists the flat files).

**9100469 (ESIM / vapor canister).** One-page GPOP note dated 2024-12-16, models MY 18-25 GA and MY 18-25 GU (Stelvio), no engine stated. Canister part numbers 68400620A, 68402531A, 68528496A, 68534104A. Text: if the issue is with the evaporative system integrity module detector and not the vapor canister, replace only the ESIM detector. No ESIM part number, DTC or symptom is named.

---


**Captured:** 2026-08-27. **295 unique NHTSA manufacturer-communication records → 201 unique FCA bulletin numbers.** All 295 PDFs retrieved; 287 yielded extractable text (8 are image-only scans).

Full index CSV, PDFs and extracted text are in the session scratchpad:
`…\scratchpad\AlfaRomeo_TSB_index.csv`, `…\scratchpad\pdfs\`, `…\scratchpad\txt\`

Groups: Electrical/BCM/Network **103** · Transmission/Driveline **26** · EVAP/Fuel **21** · Body/Glass/Lighting **16** · Engine/Cooling **15** · Equipment/Infotainment **13** · Suspension/Steering **5** · Brakes **1** · Restraints **1**.
*(Grouping is a keyword heuristic — treat the label as a filter aid, not authority.)*

---

## Sibling-engine analogues

**Rule.** When real Stelvio 2.0L information is lacking, bulletins and documented repairs from other vehicles with the same FCA GME-T4 2.0L engine family (Jeep Wrangler JL 2.0T, Cherokee KL 2.0T, Grand Cherokee WL 2.0T, Compass 2.0T, Dodge Hornet, Alfa Giulia 2.0T) are included as ANALOGUES. They are labelled as such, never presented as Stelvio bulletins, and ranked below Stelvio-specific evidence. Nothing here is a statement that the bulletin applies to this car.

**Fields.** `vehicle_scope` (`this_model` on the 99 Stelvio rows, `sibling_engine` on analogues), `sibling_vehicle` (`<model years engine>` the document was written for), `transferability` (the research's inference sentence, prefixed `inference: `), `stelvio_equivalent` (number of the Stelvio row it parallels, or null), `also_applies_to` (on a `this_model` row: sibling vehicles covered by the same number; 18-048-23 gained the Wrangler JL SLVT entry instead of a duplicate row). `field_report` rows are forum/retailer claims: `verified` false, `applies` no, summary `analogue only`, no links. Links only where the research opened the NHTSA document. `applies` is `vin_check` for analogues (`no` where the research says not applicable, e.g. PHEV-only).

**Scoring** (`cuore/services/tsb_xref_bridge.py`). Analogue rows get relation `analogue` (reason names the sibling vehicle, and `analogue of Stelvio <number>` when `stelvio_equivalent` exists in the catalogue); score = floor(score x 0.5), minimum 1 when a DTC matches; `field_report` rows carry relation `field_report` and never exceed 1. They sort after every Stelvio row, stay out of `by_code` / `by_hypothesis` / `by_system` / `by_repair` / `top()`, and appear in `analogues` and `analogues_by.{by_code,by_hypothesis,by_system}`; each Stelvio bulletin lists related analogues (same DTC, same system or declared equivalent) under *Same engine, other models (analogues)*. `/tsb` has a Scope filter (this model / sibling engine / field reports) and an `Analogue: <vehicle>` badge on sibling rows.

**Rows (42).** Research gaps (no bulletin found): engine mounts, wastegate, timing chain/MultiAir, walnut blast/intake carbon, oil consumption, IBS, Cherokee oil/PCV. 18-048-23 is not repeated (already a Stelvio row).

| Number | Kind | Sibling vehicle | Title | Stelvio equivalent | Opened |
|---|---|---|---|---|---|
| 18-018-20 (supersedes 18-034-19 Rev A; RRT 18-137) | tsb | 2018 Jeep Wrangler JL 2.0T eTorque (EC3) | Flash: PCM Updates |  | yes |
| 18-014-20 (supersedes 18-041-19) | tsb | 2018 Jeep Wrangler JL 2.0T ESS (EC1) | Flash: PCM Updates |  | yes |
| 14-005-22 Rev B (RSU 22-072) | tsb | 2021 Jeep Wrangler JL 2.0T EC1/ECX (built 2021-06-01 to 2021-10-06, non-locking cap), also | Updated Fuel Filler Cap |  | yes |
| STAR Online case S2125000002 Rev A | tsb | 2019-2021 Jeep Wrangler JL 2.0L and 3.6L, PHEV ECX | EVAP codes - check mid-point quick-connect of recirculation lines |  | yes |
| 18-035-20 (RRT 20-027) | tsb | 2020 Jeep Grand Cherokee WK / Durango WD 3.6L ERC (built 2019-11-04 to 2020-03-09) | Fuel Vapor Hose Not Connected |  | yes |
| 25-002-15 Rev B / Rev A | tsb | 2015 Jeep Grand Cherokee WK / Dodge Durango WD (3.6/5.7) | Purge valve hose may split |  | no |
| MAS003111 (MTB 22-15) | tsb | MY22 Maserati V6 Levante/Ghibli/Quattroporte | P043E EVAP leak detection reference orifice low flow |  | yes |
| UA4 | recall | 2017-2018 Alfa Giulia and 2018 Stelvio 2.0L (EC2) [reference] | Engine control software, inadequate catalyst overheat protection | 18V636 | yes |
| CSN 46A | csn | 2023 Alfa Giulia and Stelvio 2.0L | PCM software, ignition coil electrical overstress |  | yes |
| 18-052-20 (supersedes 18-050-19) | tsb | 2019 Jeep Cherokee KL 2.0L (EC1) | Flash: PCM updates |  | yes |
| 18-161-22 | tsb | 2019 Jeep Cherokee KL 2.0L | Flash: PCM updates |  | yes |
| 18-090-21 | tsb | 2020 Jeep Cherokee KL 2.0L | Flash: PCM updates |  | yes |
| 18-057-24 (rev of 18-019-21) | tsb | 2021 Jeep Cherokee KL 2.0L | Flash: PCM updates |  | yes |
| 18-070-23 | tsb | 2020 Jeep Wrangler JL 2.0L | Flash: PCM updates |  | yes |
| 18-011-25 | tsb | 2024 Jeep Wrangler JL 2.0L (EC1) | Flash: PCM updates (cam/OCV/cat) |  | yes |
| 18-037-24 Rev B | tsb | 2024 Dodge Hornet 2.0L | Flash: PCM updates |  | yes |
| 18-079-23 | tsb | 2023 Dodge Hornet 2.0L (built 2023-01-28 to 03-09) | Engine misfire |  | yes |
| U87 | csn | 2017-2019 Cherokee KL, 2018 Wrangler JL, others incl 2.0L EC1/EC3 (built 2017-08-30 to 201 | Powertrain Control Module (voltage regulator chip) |  | yes |
| 09-012-23 Rev A / RSU 23-201 | tsb | 2022-2023 Grand Cherokee WL 2.0L PHEV (ECX), built to 2023-05-25 | Oil leak from turbo oil return tube | W05 | yes |
| unknown (Mitchell1 summary) | tsb | 2025 Wrangler and Compass 2.0L (built 2024-11-20 to 2025-05-01) | Leaky turbo oil return line | W05 | no |
| 09-017-26 Rev A | tsb | 2026-27 Grand Cherokee WL 2.0L Hurricane4 (EC7) | Umbrella valve seal missing from cylinder head cover |  | yes |
| 18-052-20 / 18-161-22 / 18-070-23 | tsb | 2019 Cherokee KL, 2020 Wrangler JL 2.0L | PCV/crankcase vent DTCs cleared by PCM flash |  | yes |
| 07-001-22 Rev B / RSU 22-085 | tsb | 2018-2022 Wrangler JL 2.0L (EC1,EC3,ECX) built to 2022-03-10 | Water pump inlet tube fastener torque |  | yes |
| 07-001-24 | tsb | 2022 Wrangler JL 2.0L (EC1,ECX) built 2021-06-01 to 2022-06-09 | Thermostat housing manifold coolant leak |  | yes |
| 09-018-25 | tsb | 2021-2024 Wrangler JL, Compass MP, Grand Cherokee WL 2.0L | Cylinder block porosity |  | no |
| 09-016-23 / RSU 23-225 | tsb | 2023 Compass 2.0L (built 2023-02-27/28) | Incorrect coolant mix, low-temp system |  | yes |
| 07-006-23 | tsb | 2022 Wrangler PHEV 2.0L | Mis-installed 3-way coolant valve |  | yes |
| Y10 | recall | 2020 Wrangler JL 2.0L | Fuel supply line connector may leak |  | yes |
| 08-106-24 Rev C / RSU 24-075 | tsb | 2022-2023 Wrangler JL 2.0L (EC1,ECX) built 2022-01-01 to 2023-02-19 | Performance Limited Fuel System, no DTCs |  | yes |
| 08-106-21 Rev A | tsb | 2021 Wrangler PHEV | 12V battery low charge |  | yes |
| 09-009-26 (XC2) | extended_warranty | 2024-25 Wrangler, 2023-25 Grand Cherokee PHEV 2.0L (ECX) | PHEV engine replacement warranty extension |  | yes |
| 21-034-24 | tsb | 2022 Wrangler JL 2.0L EC1 + 850RE (DFT) | Flash: TCM updates | 21-035-20 | yes |
| 21-022-20 | tsb | 2020 Wrangler JL EC3 + 850RE built to 2020-02-20 | Flash: TCM updates | 21-035-20 | yes |
| 21-036-24 Rev A | tsb | 2024 Dodge Hornet 2.0L + 948TE | Flash: TCM (shift paddles) |  | yes |
| 21-027-26 (XX1) | extended_warranty | 2017-2019 Cherokee KL 2.0L | Two-speed PTU failure warranty extension |  | yes |
| FIELD REPORT 1 | field_report | Jeep Wrangler JL 2.0T 2019 | Jeep Wrangler JL 2.0T 2019: P0456 after trailer harness install; suspected knocked connect |  | no |
| FIELD REPORT 2 | field_report | Jeep Wrangler JL | Jeep Wrangler JL: Evaporative emissions leak MIL thread |  | no |
| FIELD REPORT 3 | field_report | Jeep (parts retailer guide) | Jeep (parts retailer guide): owner replaced ESIM after dealer found failed; cured P0456 |  | no |
| FIELD REPORT 4 | field_report | Jeep Renegade/Fiat 500X (third-party) | Jeep Renegade/Fiat 500X (third-party): ESIM O-ring degrades/flattens causing small leak; E |  | no |
| FIELD REPORT 5 | field_report | Alfa Giulia 2.0 | Alfa Giulia 2.0: Giulia P0455 guide: cap, then canister; no Giulia ESIM-specific forum fix |  | no |
| FIELD REPORT 6 | field_report | Jeep Wrangler JK | Jeep Wrangler JK: P0456 fixed at canister connection / kinked seal (JK, not JL) |  | no |

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
