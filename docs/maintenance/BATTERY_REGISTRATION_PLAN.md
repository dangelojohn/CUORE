# Battery registration check (owner does it in MES; CUORE reads before and after)

**Car:** 2018 Alfa Romeo Stelvio 2.0T, VIN ZASFAKPN5J7B88115. **Date:** 2026-10-26.
**Why:** owner reports (note 9854020de8ad) the 12 V battery was replaced in December 2025 with
a new, correct-size AGM battery, with no battery registration and no IBS relearn, and neither
MES nor the Launch tool was told. See also `docs/design/CUORE_ADJUSTMENTS_PLAN.md` (Part 2).

## What needs teaching, and what does not

- **IBS relearn (battery sensor): almost certainly not needed.** CUORE's research notes cite
  FCA bulletin S1408000384: after a new battery the IBS relearns by itself after one crank and
  2-4 h of sleep (OUTSIDE fact, stored locally; not a CUORE reading). After ~10 months of normal
  use this has long happened.
- **Battery registration (PROXI byte 63, in the BCM): only if it does not match the battery.**
  Byte 63 holds the battery type/size (e.g. 80 Ah / 95 Ah, flooded / AGM). If the original battery
  was also an AGM of the same size, nothing changes. If not, the car may be using the wrong
  charging strategy for the AGM (forum reports mixed, unproven).

## Who does it

The **owner, in MultiEcuScan**. No dealer visit is needed. CUORE cannot write this setting (no MES
keys; PROXI changes stay MES-only per the adjustments plan); CUORE reads before and after.

## Risks and how each is avoided

1. **Wrong value** (wrong type registered) -> read the battery label first; register only what it says.
2. **Interrupted write** (voltage dip, dropped connection mid-PROXI write) can leave modules
   disagreeing; on this platform a mismatch is documented to set TCM P1500 with limited power
   (CUORE drivetrain notes, not a reading from this car) -> battery maintainer connected, engine
   off, laptop on mains power, do not touch doors/keys during the write.
3. **No easy undo** (no evidence MES can restore a saved PROXI) -> screenshot the current value
   before changing anything.
- **B10AA-4A** "PROXI configuration incorrect component" is already stored in the BCM (MES reads
  2026-10-23); cause unknown. It is a reason to READ before writing, not a reason to wait for the
  dealer. A mismatched battery byte could even be related.

## Steps

1. **Battery label:** record type (H7 / H8), Ah, CCA, and confirm AGM. Send to CUORE (note).
2. **Before (CUORE, read-only session):** BCM codes (incl. B10AA), other module codes, battery
   voltage.
3. **Read only in MES:** CAN Setup -> view the battery setting (PROXI byte 63). Screenshot it.
   Do NOT write yet. MES keeps the read in its log.
4. **If it already matches the AGM battery: stop.** Nothing to do; record the result in CUORE.
5. **If it does not match:** connect a battery maintainer, then in MES change only the battery
   type to match the label and let it finish.
6. **After (CUORE):** read the codes again and compare with step 2; any new code is recorded, not
   cleared. Watch the battery charge over the next few days (voltage at rest; IBS state of charge
   once its DID is verified).

## Record in CUORE

The label values, the byte 63 value before (and after, if changed), the MES log file name, the
before/after code lists, and whether B10AA changed.
