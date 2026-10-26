# Fuses & relays page: mechanic-first spec (rev 3, 2026-10-25)

Owner's direction: CUORE directs, informs and gives REAL information. The
mechanic uses CUORE as the main tool and source of truth. The mechanic does
NOT create boxes or fill in data on this page.

## Principles
- Real data only, from the official owner's manual (and, where it exists, the
  owner's photos and the Mopar catalogue). Every value shows its source in
  small text; nothing invented; a gap is stated once, plainly.
- Direct the mechanic: the page opens with what to check NOW for this car's
  open job / codes / symptoms, then where it is, then how to reach it.
- Design spec (docs/design/cuore-bay-tablet.html): one-line "call" at top;
  grouped inset lists that drill down; chips = label + colour; 44 px targets;
  ~820 px column; app tokens; works light and dark.
- No data-entry forms on the mechanic page (no add box, add fuse, record
  spec, upload). Data maintenance lives on a separate owner page
  /v/{vin}/fuses/data, linked only from the page footer.
- One mechanic action stays: after testing a fuse or relay, one tap
  "Tested OK" / "Blown - replaced" (records evidence for the job).

## Page order
1. CALL: the one thing to do, e.g. "Rear-left window stops part way: check
   F47 and F48 (rear windows) in the passenger-footwell box." Built from the
   open job's symptoms and the current codes, matched to fuse circuits by
   their printed circuit text; the match is labelled "linked by circuit name".
   With no open job: "<N> fuses and relays, <boxes> boxes. Pick a box."
2. FOR THIS JOB (only if the call found fuses): cards for those fuses with
   box, position, amps, type, colour swatch, circuit, and a jump to the slot.
3. BOX PICKER: one card per box, each with a small locator thumbnail of the car
   (top view, box marked on the correct side), its printed name, "where" and
   how to reach it in one line.
4. BOX SECTION (one per box, id="fuse-box-<id>"):
   a. Where + how to reach it: the access steps as printed in the manual,
      with the page/figure reference.
   b. Real picture: the manual illustration of the box (if the owner approves
      saving it) and/or the owner's photo; otherwise the Mopar diagram.
   c. Slot layout line art following the REAL arrangement from the manual
      illustration (rows/columns/orientation); each slot shows number, amps,
      colour swatch; tap a slot to open its row.
   d. Full table from the manual: position, amps, type, colour, circuit,
      last test result. Relays in their own table: number, name/function,
      type, pins/orientation where printed.
5. CAR VIEWS (side/top toggle), compact, one marker per box, correct side.
6. Footer (collapsed): sources (manual title, edition, pages), gaps, link to
   the owner data page.
