# 2018 Stelvio 2.0T - service / oil-change message reset: official sources (2026-10-26)

Labels: CONFIRMED (official doc) / CORROBORATED / SINGLE_SOURCE / UNKNOWN.
Method: downloaded the Mopar-hosted 2018 US owner's manual PDF
(vehicleinfo.mopar.com ... P124461_18_GU_OM_EN_USC_DIGITAL_2nd_V2.pdf, 2nd ed.)
and the NHTSA-hosted FCA TSB 01-001-26 PDF; extracted text with pdftotext and
read the relevant pages. Web searches for the rest. No COM3, no code edits.
The EU "Stelvio Owner Handbook" was NOT located/read (UNKNOWN).

## 1. Owner's manual (NA 2018) - what it actually says

- Warning-light table (p. 86): "ENGINE OIL CHANGE REQUIRED -- IF EQUIPPED"
  -> action: "Contact an authorized dealer as soon as possible."
  Telltale "illuminated only for a limited time"; after first indication it
  re-illuminates at each engine start "until the oil is changed". CONFIRMED.
- Scheduled Servicing plan (p. 213-215), note (3): interval "depends on the
  vehicle usage conditions and is signaled by the warning light or message"
  and "never exceed 1 year/10,000 miles (16,000 km)". CONFIRMED.
- Plan row (p. 214): "Check engine control system operation (via diagnostic
  tool) and, if equipped, engine oil degradation (2)"; note (2): if oil
  degradation ratio "(data collectable from diagnostic device)" is over 80%,
  replace oil and filter. CONFIRMED. So the car carries an oil-degradation
  ratio that only a diagnostic tool reads.
- Text search of the whole manual found NO driver reset procedure (no cluster
  menu, no pedal sequence, no Uconnect reset), no "Service Due" message, no
  "Scheduled Maintenance" Uconnect feature. The manual's only instruction is
  "see dealer". CONFIRMED absence in this edition (full-text search, not a
  page-by-page read of images; a graphic-only page could be missed).
- Oil filter (p. 223): "must be replaced each time the engine oil is
  changed... genuine spare part". Filter TYPE (spin-on vs cartridge) is NOT
  stated anywhere in the manual (search for cartridge/spin-on/canister: only
  tyre-sealant hits). Manual does not settle filter type.

## 2. Official reset method that DOES exist: FCA TSB 01-001-26

Title "Oil Change Monitor Displaying Prematurely", 2018-2026 (GU) Stelvio and
(GA) Giulia, NA market, rev. of 01-002-24 (earlier: 01-001-20, 01-001-21,
01-001-22). Source: https://static.nhtsa.gov/odi/tsbs/2026/MC-11032849-0001.pdf
CONFIRMED (manufacturer document, dealer-facing, public via NHTSA).

Symptom: oil light on within 4,000 mi of delivery; cause "Extended vehicle
sitting time". Repair step 2, "Resetting the oil change indicator system"
(no tool needed):
1. Without brake, press ENGINE START/STOP, cycle to ON/RUN (do not start).
2. Fully depress accelerator "slowly, five times within 10 seconds".
3. Without brake, press START/STOP once -> OFF/LOCK.
Note: "If the indicator message illuminates when you start the vehicle, the
oil change indicator system did not reset. If necessary, repeat... If the
above process fails to complete, use the scan tool to complete the reset."

=> The pedal method is the manufacturer's own dealer procedure, so it is
official, but it is in a TSB, not the owner's manual. Count is FIVE in 10 s
(forum copy in service_specs.py says 3, "some need 4-6": count differs).

TSB also gives data the car holds (read via RDI, dealer terminology):
| Parameter | RDI |
|---|---|
| Days | 0x3815 |
| Miles | 0x3818 |
| Cold start number | 0x3816 |
| Oil soot accumulation | 0x3819 |
(RDI = routine/data identifier read after reset as evidence; mapping to the
module that hosts them is not stated in the TSB: UNKNOWN. Likely ECM-side
oil-degradation inputs given "cold start" and "soot", but that is inference.)
Pre-delivery rule: if build <=365 days and <=150 mi, reset only; otherwise
change oil and filter, then reset. Warranty labor 09-55-01-94/95/96.
TSB parts list (CONFIRMED): oil filter 04892339AB; oil 68492706AA (0W-30 full
synthetic), 5.5 qt. Confirms the filter number and capacity CUORE holds.

## 3. Two counters or one? (Q2)

- Official documents describe ONE driver-visible indicator: the "oil change
  light / oil life monitor", reset as above. No official document describes a
  separate cluster service-interval km/days counter or a Uconnect "scheduled
  maintenance" counter for this car. UNKNOWN whether they exist.
- The TSB's data table (Days, Miles, Cold starts, Soot) plus the manual's
  "oil degradation ratio" show the monitor is an algorithm with day, mile,
  cold-start and soot inputs: i.e. one monitor with several inputs, not
  separate counters. Which module computes it (ECM vs IPC) is NOT stated:
  UNKNOWN. stelvioforum thread (SINGLE_SOURCE, previously cited) says wiTECH
  path is IPC > Misc Functions > Maintenance Reset; Klavkarr (aftermarket)
  lists "ECU Maintenance Interval / Reset Maintenance Information".
  Those point to ECU-side maintenance data reset via the cluster/ECU menus
  but are not official.
- "Service Due" message wording: not found in the manual or the TSB.
  UNKNOWN. Do not map it to a counter.

## 4. Security (SGW / 0x27) (Q4)

No official or dealer-tool document found stating the reset needs security
access or SGW unlock. The TSB's own fallback is "use the scan tool", with no
detail. Aftermarket pages (Klavkarr) show a scan-tool reset with no mention of
SGW. UNKNOWN. Note the pedal method needs no tool at all, so by design the
function is not behind dealer-level security (inference from the TSB: a tool-free
route is officially provided; an SGW-gated tool route is not documented).

## 5. wiTECH / bulletins (Q3)

- TSB series 01-001-20 / 01-001-21 / 01-001-22 / 01-002-24 / 01-001-26 (all
  already in docs/reference/TSB_CATALOGUE.md) = the oil monitor TSB family.
  Only 01-001-26 text was read this pass; earlier revisions same family.
- wiTECH "Maintenance Reset under IPC Misc Functions": SINGLE_SOURCE (forum),
  no FCA document located. wiTECH docs are not public.

## 6. Cross-check vs service_specs.py (Q5)

- Interval 8,000 mi/12 mo conservative; manufacturer max 10,000 mi/1 yr
  CONFIRMED in manual: agrees with existing note.
- reset_methods "accelerator pedal ... 3 times (some need 4-6)": the
  official TSB says FIVE presses within 10 s, ignition ON/RUN engine off,
  then OFF/LOCK (not "start the engine"). RECOMMEND correcting to the TSB
  and upgrading that method's confidence to CONFIRMED (source: TSB
  01-001-26). The oil_life_system "source" field should cite the TSB.
- OIL_FILTER_PARTS 4892339 / suffix AB: TSB lists 04892339AB: upgrade to
  CONFIRMED for the part number. But the TSB does not say cartridge vs
  spin-on, and neither does the owner's manual. The "cartridge under plastic
  cap, 25 Nm" (filter_cap torque, SINGLE_SOURCE) claim is therefore still
  unsupported by any official text; the owner's spin-on HENGST H98W stands
  unresolved by documents. Search turned up conflicting retail listings (a
  German retailer lists both a spin-on OE 50057786 and a cartridge element
  OE 71779389 for the 2.0 Q4); SINGLE_SOURCE, inconsistent, not usable as proof.
  The fiat500usa how-to calls the filter "a common FCA oil filter used on
  numerous cars" and mentions a wrench (suggests canister): inference only.
  Best settlement: physical part in hand vs Mopar 04892339AB by VIN.
- Manual-level facts to add: oil-degradation >80% -> replace (CONFIRMED).

## Summary table

| Message | Counter / module | Official reset method | Source | Confidence |
|---|---|---|---|---|
| ENGINE OIL CHANGE REQUIRED telltale | Oil life monitor (days/miles/cold starts/soot inputs; host module not stated) | Owner's manual: "Contact an authorized dealer" | 2018 US OM p. 86 | CONFIRMED |
| Oil change light / oil life monitor | same | Ignition ON (no brake, engine off), accelerator fully x5 within 10 s, ignition OFF; else scan tool | FCA TSB 01-001-26 (NHTSA PDF) | CONFIRMED |
| Oil degradation ratio >80% | ECM-side data, "diagnostic device" read | Replace oil+filter (no reset described) | OM p. 214 note 2 | CONFIRMED |
| "Service" / "Service Due" | not found in manual or TSB | none found | - | UNKNOWN |
| Separate cluster km/days or Uconnect scheduled-maintenance counter | not documented | none found | - | UNKNOWN |
| Reset needs SGW/0x27 | not documented; tool-free route exists | n/a | TSB implies none | UNKNOWN (inference: no) |
| wiTECH IPC > Misc Functions > Maintenance Reset | IPC | wiTECH menu | stelvioforum | SINGLE_SOURCE |

What the owner can do with no tool: the TSB pedal sequence above (repeat if
the message returns at start; official note says it may need repeating). If
it still fails, the manufacturer's fallback is a scan tool (MES/wiTECH-class).
After resetting, a post-change confirmation would be a CUORE read of the
four RDI values (days/miles/cold starts/soot) if readable: unverified.

Single most important finding: the pedal-sequence reset is in the OFFICIAL
FCA TSB 01-001-26 (five presses in 10 s), not just forum lore, while the owner's
manual says only "see dealer" and never states the filter type.
