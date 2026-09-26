# Avery Weatherproof/Durable Label Sheet Geometry

This is the human-readable companion to `cuore/labels/templates.py`, which
is what `cuore.labels.render` and the `/v/{vin}/labels` page actually use.
The two must agree — this file exists so a person can review the sourcing
and the arithmetic without reading Python.

**Confidence levels** (mirroring the convention already used by
`mes.service_specs`/`mes.drivetrain_specs` in this repo — never invented; an
unconfirmed number is `None` plus an on-screen warning, never a guess
presented as fact):

- **CONFIRMED** — Avery's own product/template page states the number
  directly.
- **CORROBORATED** — two or more independent non-Avery sources agree, *and*
  the numbers close exactly against the page size (checked below).
- **SINGLE-SOURCE** — one source, or a geometry this module derived itself
  from an Avery-confirmed label size/count plus the page size.
- **UNVERIFIED** — margins/pitch could not be confirmed anywhere
  Avery-traceable. `cuore/labels/templates.py` leaves them `None` and falls
  back to an evenly-distributed placeholder layout at render time (every
  cell is still provably inside the page — it is just not claimed to be the
  real die line). The label page shows this on screen and every rendered
  page/test-grid is stamped with a warning.
- **CUSTOM** — user-entered dimensions, entered on the labels page. Never
  claimed as verified either; same "print the test grid first" treatment.

Research pass done 2026-09-26 by web search against Avery's own
`avery.com/templates/*` and `avery.com/products/labels/*` pages (label size,
material, printer type, labels-per-sheet are read directly off these — the
pages are a JS app and did not expose margin/pitch numbers to a page fetch)
plus two label-geometry aggregator sites (`sheetstolabels.com`, a GitHub gist
of Avery sheet dimensions by armadsen) for margin/pitch, cross-checked in
this document by confirming each set of numbers closes exactly against an
8.5"×11" US Letter page. No paywalled/authenticated Avery template *file*
(the actual .doc/.pdf downloads, which would carry the numbers directly) was
opened during this pass — a future pass that downloads one of those and
confirms the 6576/6578 margins directly should upgrade those two rows to
CORROBORATED and delete the UNVERIFIED fallback path for them.

All Avery templates below share an 8.5" × 11" (215.9mm × 279.4mm) US Letter
page, 0 corner radius data found anywhere (left `None` throughout — labels
are printed as square rectangles; a die-cut sheet's physical corners are
rounded but no source gave a radius number, so none is claimed).

## Weatherproof laser film (5520 family — Ultrahold permanent adhesive, laser only)

| Template | Label (nominal) | Count | Cols×Rows | Top margin | Left margin | H-pitch | V-pitch | Confidence | Sources |
|---|---|---|---|---|---|---|---|---|---|
| **5520** | 1" × 2-5/8" | 30 | 3×10 | 0.5" | 0.188" | 2.75" | 1.0" | CORROBORATED | [avery.com/templates/5520](https://www.avery.com/templates/5520), [avery.com/products/labels/5520](https://www.avery.com/products/labels/5520), [gist](https://gist.github.com/armadsen/5084458) |
| **5522** | 1-1/3" × 4" | 14 | 2×7 | 0.833" | 0.156" | 4.188" | 1.333" | CORROBORATED | [avery.com/templates/5522](https://www.avery.com/templates/5522), [sheetstolabels 5162](https://sheetstolabels.com/avery-5162-template) |
| **5523** | 2" × 4" | 10 | 2×5 | 0.5" | 0.17" | 4.16" | 2.0" | CORROBORATED | [avery.com/templates/5523](https://www.avery.com/templates/5523), [sheetstolabels 5163](https://sheetstolabels.com/avery-5163-template) |
| **5524** | 3-1/3" × 4" | 6 | 2×3 | 0.5" | 0.156" | 4.188" | 3.333" | CORROBORATED | [avery.com/templates/5524](https://www.avery.com/templates/5524), [sheetstolabels 5164](https://sheetstolabels.com/avery-5164-template) |
| **5526** | 5-1/2" × 8-1/2" | 2 | 1×2 | 0" | 0" | 8.5" | 5.5" | SINGLE-SOURCE | [avery.com/templates/5526](https://www.avery.com/templates/5526), [avery.com/templates/5126](https://www.avery.com/templates/5126) |

**5520** = same physical die-cut as the ubiquitous Avery 5160 address label.
Arithmetic: `0.188 + 3(2.625) + 2(0.125) = 8.5`; `0.5 + 10(1.0) + 0.5 = 11.0`
(the 0.125" is the implied horizontal gap: `2.75 - 2.625`; vertical gap is 0,
labels butt against each other in a column — this is why "pitch" and "gap"
are not the same number and why `templates.py`'s docstring calls that out).

**5522** = same layout as Avery 5162. Arithmetic: `2(0.156) + 2(4.0) +
1(0.188) = 8.5`; `2(0.833) + 7(1.333) = 11.0` (rounding on the published
0.833"/1.333").

**5523** = same layout as Avery 5163. Arithmetic: `2(0.17) + 2(4.0) +
1(0.16) = 8.5`; `2(0.5) + 5(2.0) = 11.0`.

**5524** = same layout as Avery 5164. Arithmetic: `2(0.156) + 2(4.0) +
1(0.188) = 8.5`; `2(0.5) + 3(3.333) = 11.0` (rounding).

**5526**: Avery's own template-compatibility page groups 5526 with 5126/8126
(the half-sheet shipping label family) but no independent source gave a
numeric margin. The zero-margin, full-bleed geometry here is *this
project's own derivation*, not an Avery-stated number: the label is
confirmed at 5.5"×8.5" (landscape), 2/sheet, and `2 × 5.5 = 11.0` /
`1 × 8.5 = 8.5` exactly consumes the page with no room left for any margin —
it is the only geometry consistent with both Avery-confirmed facts. Marked
SINGLE-SOURCE rather than CORROBORATED for that reason; print the test grid
before trusting it against real film.

## Weatherproof laser film, inkjet-compatible siblings (9-prefixed)

Avery's own help article "[Temperature Range of Waterproof TrueBlock
Labels](https://www.avery.com/help/article/tempature-range-of-waterproof-trueblock-labels)"
lists `15513, 15516, 5520, 5522, 5526, 95520, 95522, 95523, 95526` together
as one weatherproof TrueBlock family. `cuore/labels/templates.py` reads this
as: 95520/95522/95523/95526 are the inkjet-compatible version of
5520/5522/5523/5526 respectively, same die-cut layout, and inherits each
one's geometry and confidence unchanged (not independently re-measured for
the 9-prefixed number itself).

## Durable ID labels (6576/6578 — permanent adhesive, laser)

| Template | Label (nominal) | Count | Cols×Rows | Confidence | Sources |
|---|---|---|---|---|---|
| **6576** | 1-1/4" × 1-3/4" | 32 | 4×8 | **UNVERIFIED** | [avery.com/templates/6576](https://www.avery.com/templates/6576), [avery.com/templates/6570](https://www.avery.com/templates/6570) |
| **6578** | 2" × 2-5/8" | 15 | 3×5 | **UNVERIFIED** | [avery.com/templates/6578](https://www.avery.com/templates/6578), [avery.com/templates/6572](https://www.avery.com/templates/6572) |

Label size and count for both are confirmed directly from Avery's own
product/template pages (6576 shares its layout with 6570; 6578 with 6572).
No Avery-traceable margin/pitch number was found for either:

- For 6576/6570, every source checked (Avery's page, foxylabels, hlabels,
  onlinelabels' generic size guide) gave the label size and count but not
  a margin/pitch figure.
- For 6578/6572, one secondary source gave top=0.5", side=0.1875",
  h-pitch=2.75", v-pitch=2.125". The horizontal figure closes exactly
  (`0.1875(2) + 3(2.625) + 2(0.125) = 8.5`) but the vertical one does not
  (`0.5(2) + 5(2.125) = 11.75`, not 11.0) — so this candidate is **not**
  trusted and is **not** used.

Both are therefore left `UNVERIFIED` in `templates.py`: margins/pitch are
`None`, `LabelTemplate.cell_origin_mm()` falls back to an evenly-distributed
placeholder (equal gutters computed from the confirmed label size/count and
page size), and every page/PDF that uses one of these two templates shows an
explicit on-screen/on-page warning to print the test grid on plain paper and
check it against a real sheet before using film. A future pass that opens
an actual downloaded Avery template file for either number should replace
this with a confirmed value.

## Custom template

The labels page also accepts a user-entered geometry (page size, label
size, columns/rows, top/left margin, optional horizontal/vertical pitch) —
`cuore.labels.templates.build_custom()`. This is always `CUSTOM` confidence:
the user supplied every number, so the module's only role is an arithmetic
sanity check (does the last label actually fit on the page), never a claim
that the numbers are correct for any real product. Same "print the test
grid first" treatment applies.

## What's deliberately not here

Corner radius: no source (Avery or otherwise) gave a numeric corner radius
for any of the templates above, so it is `None` everywhere rather than a
guessed value like the commonly-quoted "0.0625 inch" seen on generic label
sizing charts (which was not traced to these specific SKUs and so is not
used here).
