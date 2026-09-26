"""Avery weatherproof/durable label sheet geometry, as data.

Every template below is a physical Avery die-cut layout: page size, label
width/height, top/left margin, horizontal/vertical pitch (centre-to-centre
spacing, which is what actually matters for a print grid -- NOT the same
number as label-size-plus-gap when a sheet has an asymmetric bottom margin),
rows x cols, and corner radius. All dimensions are stored in millimetres
(the calibration offsets elsewhere in this feature are specified in mm, so
one canonical unit avoids a conversion bug at the boundary); the inch value
Avery itself advertises is kept in ``label_w_in``/``label_h_in`` for display.

Confidence levels, deliberately mirroring the convention already used by
``mes.service_specs`` and ``mes.drivetrain_specs`` in this repo:

* ``CONFIRMED``     -- Avery's own product/template page states the number
                       directly.
* ``CORROBORATED``  -- two or more independent non-Avery sources agree, AND
                       the numbers close exactly against the page size
                       (``margin*2 + rows*label + (rows-1)*gap == page``,
                       computed via pitch below) -- see ``docs/reference/
                       AVERY_LABEL_TEMPLATES.md`` for the arithmetic.
* ``SINGLE_SOURCE`` -- one source, or a geometry this module derived itself
                       from an Avery-confirmed label size/count plus the
                       page size (e.g. a zero-margin half-sheet label where
                       the label size already consumes the whole page).
* ``UNVERIFIED``    -- margins/pitch could not be confirmed anywhere Avery-
                       traceable. ``margin_top_mm``/``margin_left_mm``/
                       ``pitch_x_mm``/``pitch_y_mm`` are left ``None`` and
                       :meth:`LabelTemplate.cell_origin_mm` falls back to an
                       evenly-distributed layout that is geometrically valid
                       (every cell provably inside the page) but is NOT
                       claimed to be the real die line. Every caller must
                       show ``geometry_confirmed`` is ``False`` before the
                       user prints to film -- render.py stamps a warning on
                       the page, and the web page shows one too.
* ``CUSTOM``        -- user-entered dimensions. Never claimed as verified.

Never invented: a number this module cannot trace to a source is ``None``
plus this UNVERIFIED handling, not a guessed figure presented as fact. See
``docs/reference/AVERY_LABEL_TEMPLATES.md`` for the full research trail and
source URLs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

MM_PER_IN = 25.4


def _in(inches: float) -> float:
    return round(inches * MM_PER_IN, 3)


CONFIRMED = "CONFIRMED"
CORROBORATED = "CORROBORATED"
SINGLE_SOURCE = "SINGLE-SOURCE"
UNVERIFIED = "UNVERIFIED"
CUSTOM = "CUSTOM"
CONFIDENCE_LEVELS = (CONFIRMED, CORROBORATED, SINGLE_SOURCE, UNVERIFIED, CUSTOM)


@dataclass(frozen=True)
class LabelTemplate:
    id: str
    name: str
    material: str
    printer: str  # "laser", "inkjet", or "laser+inkjet"
    page_w_mm: float
    page_h_mm: float
    label_w_mm: float
    label_h_mm: float
    cols: int
    rows: int
    margin_top_mm: Optional[float]
    margin_left_mm: Optional[float]
    pitch_x_mm: Optional[float]
    pitch_y_mm: Optional[float]
    corner_radius_mm: Optional[float]
    confidence: str
    sources: tuple[str, ...] = ()
    notes: str = ""
    label_w_in: str = ""   # Avery's own advertised size, for display
    label_h_in: str = ""

    def __post_init__(self) -> None:
        if self.confidence not in CONFIDENCE_LEVELS:
            raise ValueError(f"bad confidence {self.confidence!r}")
        if self.cols < 1 or self.rows < 1:
            raise ValueError("cols/rows must be >= 1")

    @property
    def count(self) -> int:
        return self.cols * self.rows

    @property
    def has_explicit_geometry(self) -> bool:
        """True when margins/pitch are set at all (Avery-sourced or
        user-entered) rather than left ``None`` for the even-distribution
        fallback in :meth:`cell_origin_mm`."""
        return None not in (self.margin_top_mm, self.margin_left_mm,
                            self.pitch_x_mm, self.pitch_y_mm)

    @property
    def geometry_confirmed(self) -> bool:
        """True only for a template whose margins/pitch are both explicit
        AND traced to an Avery-sourced confidence level -- ``False`` for an
        UNVERIFIED Avery template (using the fallback) and for a CUSTOM one
        (the user's own numbers, never claimed as verified). Callers use
        this to decide whether to show the "print a test grid first"
        warning, not whether the geometry is usable at all."""
        return (self.confidence in (CONFIRMED, CORROBORATED, SINGLE_SOURCE)
                and self.has_explicit_geometry)

    def cell_origin_mm(self, index: int) -> tuple[float, float]:
        """Top-left corner (mm from the page's top-left) of cell ``index``
        (0-based, row-major: left-to-right, then top-to-bottom -- the order
        a partly-used sheet is normally worked through)."""
        if not (0 <= index < self.count):
            raise ValueError(
                f"cell index {index} out of range for {self.id!r} "
                f"(0..{self.count - 1})")
        row, col = divmod(index, self.cols)
        if self.has_explicit_geometry:
            x = self.margin_left_mm + col * self.pitch_x_mm
            y = self.margin_top_mm + row * self.pitch_y_mm
        else:
            gx = (self.page_w_mm - self.cols * self.label_w_mm) / (self.cols + 1)
            gy = (self.page_h_mm - self.rows * self.label_h_mm) / (self.rows + 1)
            gx, gy = max(gx, 0.0), max(gy, 0.0)
            x = gx + col * (self.label_w_mm + gx)
            y = gy + row * (self.label_h_mm + gy)
        return x, y


# --- Avery weatherproof laser (5520 family): same die-cut as the ubiquitous
#     5160/5162/5163/5164 address/shipping layouts, just printed on white
#     polyester film with Ultrahold adhesive instead of paper. Avery's own
#     product pages confirm label size/count; the margin/pitch numbers come
#     from two independent non-Avery sources that were cross-checked here by
#     confirming they close exactly against an 8.5x11 page (arithmetic in
#     docs/reference/AVERY_LABEL_TEMPLATES.md). -----------------------------

_LETTER_W, _LETTER_H = _in(8.5), _in(11.0)

TEMPLATES: dict[str, LabelTemplate] = {}


def _add(t: LabelTemplate) -> None:
    TEMPLATES[t.id] = t


_add(LabelTemplate(
    id="avery_5520", name="Avery 5520 WeatherProof — 1\" x 2-5/8\" (30/sheet)",
    material="White polyester film, Ultrahold permanent adhesive",
    printer="laser",
    page_w_mm=_LETTER_W, page_h_mm=_LETTER_H,
    label_w_mm=_in(2.625), label_h_mm=_in(1.0),
    cols=3, rows=10,
    margin_top_mm=_in(0.5), margin_left_mm=_in(0.188),
    pitch_x_mm=_in(2.75), pitch_y_mm=_in(1.0),
    corner_radius_mm=None,
    confidence=CORROBORATED,
    sources=(
        "https://www.avery.com/templates/5520",
        "https://www.avery.com/products/labels/5520",
        "https://gist.github.com/armadsen/5084458",
    ),
    notes="Same physical die-cut layout as Avery 5160 (address labels) --"
         " Avery documents 5520 as a weatherproof film version of the same"
         " 1\"x2-5/8\", 30-up sheet. Margin/pitch confirmed by closing "
         "exactly against an 8.5x11 page: 0.188+3(2.625)+2(0.125)=8.5, "
         "0.5+10(1.0)+0.5=11.0. This is the small size used for "
         "windshield-style service reminder tags.",
    label_w_in="2-5/8\"", label_h_in="1\"",
))

_add(LabelTemplate(
    id="avery_5522", name="Avery 5522 WeatherProof — 1-1/3\" x 4\" (14/sheet)",
    material="White polyester film, Ultrahold permanent adhesive",
    printer="laser",
    page_w_mm=_LETTER_W, page_h_mm=_LETTER_H,
    label_w_mm=_in(4.0), label_h_mm=_in(1.333),
    cols=2, rows=7,
    margin_top_mm=_in(0.833), margin_left_mm=_in(0.156),
    pitch_x_mm=_in(4.188), pitch_y_mm=_in(1.333),
    corner_radius_mm=None,
    confidence=CORROBORATED,
    sources=(
        "https://www.avery.com/templates/5522",
        "https://www.avery.com/products/labels/5522",
        "https://sheetstolabels.com/avery-5162-template",
    ),
    notes="Same layout as Avery 5162. Closes against 8.5x11: "
         "2(0.156)+2(4.0)+1(0.188)=8.5, 2(0.833)+7(1.333)=11.0 (rounding).",
    label_w_in="4\"", label_h_in="1-1/3\"",
))

_add(LabelTemplate(
    id="avery_5523", name="Avery 5523 WeatherProof — 2\" x 4\" (10/sheet)",
    material="White polyester film, Ultrahold permanent adhesive",
    printer="laser",
    page_w_mm=_LETTER_W, page_h_mm=_LETTER_H,
    label_w_mm=_in(4.0), label_h_mm=_in(2.0),
    cols=2, rows=5,
    margin_top_mm=_in(0.5), margin_left_mm=_in(0.17),
    pitch_x_mm=_in(4.16), pitch_y_mm=_in(2.0),
    corner_radius_mm=None,
    confidence=CORROBORATED,
    sources=(
        "https://www.avery.com/templates/5523",
        "https://www.avery.com/products/labels/5523",
        "https://sheetstolabels.com/avery-5163-template",
    ),
    notes="Same layout as Avery 5163. Closes: 2(0.17)+2(4.0)+1(0.16)=8.5, "
         "2(0.5)+5(2.0)=11.0.",
    label_w_in="4\"", label_h_in="2\"",
))

_add(LabelTemplate(
    id="avery_5524", name="Avery 5524 WeatherProof — 3-1/3\" x 4\" (6/sheet)",
    material="White polyester film, Ultrahold permanent adhesive",
    printer="laser",
    page_w_mm=_LETTER_W, page_h_mm=_LETTER_H,
    label_w_mm=_in(4.0), label_h_mm=_in(3.333),
    cols=2, rows=3,
    margin_top_mm=_in(0.5), margin_left_mm=_in(0.156),
    pitch_x_mm=_in(4.188), pitch_y_mm=_in(3.333),
    corner_radius_mm=None,
    confidence=CORROBORATED,
    sources=(
        "https://www.avery.com/templates/5524",
        "https://www.avery.com/products/labels/5524",
        "https://sheetstolabels.com/avery-5164-template",
    ),
    notes="Same layout as Avery 5164. Closes: 2(0.156)+2(4.0)+1(0.188)=8.5, "
         "2(0.5)+3(3.333)=11.0 (rounding).",
    label_w_in="4\"", label_h_in="3-1/3\"",
))

_add(LabelTemplate(
    id="avery_5526", name="Avery 5526 WeatherProof — 5-1/2\" x 8-1/2\" (2/sheet)",
    material="White polyester film, Ultrahold permanent adhesive",
    printer="laser",
    page_w_mm=_LETTER_W, page_h_mm=_LETTER_H,
    label_w_mm=_in(8.5), label_h_mm=_in(5.5),
    cols=1, rows=2,
    margin_top_mm=_in(0.0), margin_left_mm=_in(0.0),
    pitch_x_mm=_in(8.5), pitch_y_mm=_in(5.5),
    corner_radius_mm=None,
    confidence=SINGLE_SOURCE,
    sources=(
        "https://www.avery.com/templates/5526",
        "https://www.avery.com/templates/5126",
    ),
    notes="Avery's own template-compatibility listing groups 5526 with "
         "5126/8126 (the half-sheet shipping label family). No independent "
         "numeric margin source was found; the zero-margin, full-bleed "
         "geometry here is this module's own derivation from the "
         "Avery-confirmed label size (5.5x8.5, landscape) and count (2/sheet, "
         "stacked): 2x5.5=11.0 and 1x8.5=8.5 leave no room for any margin, "
         "so it is the only geometry consistent with both confirmed facts. "
         "Print the test grid before using film.",
    label_w_in="8-1/2\"", label_h_in="5-1/2\"",
))

# --- Avery Durable ID labels (6576/6578): label size and count are Avery-
#     confirmed; a plausible secondary-source margin/pitch was found for the
#     2x2-5/8 size but did not close exactly against the page (see the doc),
#     so both of these are left UNVERIFIED rather than presented as fact. ---

_add(LabelTemplate(
    id="avery_6576", name="Avery 6576 Durable ID — 1-1/4\" x 1-3/4\" (32/sheet)",
    material="White polyester film, permanent adhesive",
    printer="laser",
    page_w_mm=_LETTER_W, page_h_mm=_LETTER_H,
    label_w_mm=_in(1.75), label_h_mm=_in(1.25),
    cols=4, rows=8,
    margin_top_mm=None, margin_left_mm=None,
    pitch_x_mm=None, pitch_y_mm=None,
    corner_radius_mm=None,
    confidence=UNVERIFIED,
    sources=(
        "https://www.avery.com/templates/6576",
        "https://www.avery.com/products/labels/6576",
        "https://www.avery.com/templates/6570",
    ),
    notes="Label size (1.75x1.25) and count (32, 4x8) confirmed from "
         "Avery's own product/template pages (6576 shares its layout with "
         "6570). No Avery-traceable margin/pitch was found -- every source "
         "checked either omitted them or gave numbers that did not close "
         "against an 8.5x11 page. UNVERIFIED: uses the even-distribution "
         "fallback in LabelTemplate.cell_origin_mm(); print the test grid "
         "on plain paper and check alignment before using film.",
    label_w_in="1-3/4\"", label_h_in="1-1/4\"",
))

_add(LabelTemplate(
    id="avery_6578", name="Avery 6578 Durable ID — 2\" x 2-5/8\" (15/sheet)",
    material="White polyester film, permanent adhesive",
    printer="laser",
    page_w_mm=_LETTER_W, page_h_mm=_LETTER_H,
    label_w_mm=_in(2.625), label_h_mm=_in(2.0),
    cols=3, rows=5,
    margin_top_mm=None, margin_left_mm=None,
    pitch_x_mm=None, pitch_y_mm=None,
    corner_radius_mm=None,
    confidence=UNVERIFIED,
    sources=(
        "https://www.avery.com/templates/6578",
        "https://www.avery.com/products/labels/6578",
        "https://www.avery.com/templates/6572",
    ),
    notes="Label size (2.625x2.0) and count (15, 3x5) confirmed from "
         "Avery's own product/template pages (6578 shares its layout with "
         "6572). A secondary source gave top=0.5\", side=0.1875\", "
         "hpitch=2.75\", vpitch=2.125\" -- the horizontal numbers close "
         "exactly (0.1875*2+3*2.625+2*0.125=8.5) but the vertical numbers "
         "do not (0.5*2+5*2.125=11.75, not 11.0), so this candidate is not "
         "trusted and is not used. UNVERIFIED: uses the even-distribution "
         "fallback; print the test grid before using film.",
    label_w_in="2-5/8\"", label_h_in="2\"",
))

# --- inkjet siblings: Avery's own weatherproof-labels help article groups
#     these 9-prefixed numbers with their laser sibling above (same die-cut
#     layout, inkjet-compatible film/adhesive) -- see the doc for the exact
#     grouping quoted from Avery. Geometry is inherited unchanged. ----------

_INKJET_SIBLINGS = {
    "avery_95520": ("avery_5520", "Avery 95520 WeatherProof — 1\" x 2-5/8\" (30/sheet, inkjet)"),
    "avery_95522": ("avery_5522", "Avery 95522 WeatherProof — 1-1/3\" x 4\" (14/sheet, inkjet)"),
    "avery_95523": ("avery_5523", "Avery 95523 WeatherProof — 2\" x 4\" (10/sheet, inkjet)"),
    "avery_95526": ("avery_5526", "Avery 95526 WeatherProof — 5-1/2\" x 8-1/2\" (2/sheet, inkjet)"),
}
for _new_id, (_base_id, _new_name) in _INKJET_SIBLINGS.items():
    _base = TEMPLATES[_base_id]
    _add(LabelTemplate(
        id=_new_id, name=_new_name, material=_base.material,
        printer="inkjet",
        page_w_mm=_base.page_w_mm, page_h_mm=_base.page_h_mm,
        label_w_mm=_base.label_w_mm, label_h_mm=_base.label_h_mm,
        cols=_base.cols, rows=_base.rows,
        margin_top_mm=_base.margin_top_mm, margin_left_mm=_base.margin_left_mm,
        pitch_x_mm=_base.pitch_x_mm, pitch_y_mm=_base.pitch_y_mm,
        corner_radius_mm=_base.corner_radius_mm,
        confidence=_base.confidence,
        sources=_base.sources + (
            "https://www.avery.com/help/article/tempature-range-of-waterproof-trueblock-labels",
        ),
        notes="Inkjet-compatible film sibling of " + _base_id + " -- Avery's "
             "own help article groups this number with its laser sibling "
             "as the same weatherproof TrueBlock family; geometry inherited "
             "unchanged, not independently re-measured for this number.",
        label_w_in=_base.label_w_in, label_h_in=_base.label_h_in,
    ))


def list_templates() -> list[LabelTemplate]:
    return list(TEMPLATES.values())


def get(template_id: str) -> LabelTemplate:
    try:
        return TEMPLATES[template_id]
    except KeyError:
        raise ValueError(f"unknown label template: {template_id!r}") from None


def build_custom(*, page_w_mm: float, page_h_mm: float,
                 label_w_mm: float, label_h_mm: float,
                 cols: int, rows: int,
                 margin_top_mm: float, margin_left_mm: float,
                 pitch_x_mm: Optional[float] = None,
                 pitch_y_mm: Optional[float] = None,
                 corner_radius_mm: float = 0.0,
                 name: str = "Custom") -> LabelTemplate:
    """A user-entered geometry. Always CUSTOM confidence -- this is exactly
    the "never guess" boundary: the *user* supplied every number, so this
    module makes no claim about it beyond the arithmetic sanity checks
    below, and the page always shows a print-a-test-grid-first prompt for
    it, same as an UNVERIFIED Avery template.
    """
    pitch_x_mm = pitch_x_mm if pitch_x_mm is not None else label_w_mm
    pitch_y_mm = pitch_y_mm if pitch_y_mm is not None else label_h_mm
    for label, val in (("page_w_mm", page_w_mm), ("page_h_mm", page_h_mm),
                       ("label_w_mm", label_w_mm), ("label_h_mm", label_h_mm),
                       ("pitch_x_mm", pitch_x_mm), ("pitch_y_mm", pitch_y_mm)):
        if val <= 0:
            raise ValueError(f"{label} must be > 0")
    if cols < 1 or rows < 1:
        raise ValueError("cols/rows must be >= 1")
    right_edge = margin_left_mm + (cols - 1) * pitch_x_mm + label_w_mm
    bottom_edge = margin_top_mm + (rows - 1) * pitch_y_mm + label_h_mm
    if right_edge > page_w_mm + 0.5 or bottom_edge > page_h_mm + 0.5:
        raise ValueError(
            "custom geometry does not fit the page: last label would end "
            f"at ({right_edge:.1f}mm, {bottom_edge:.1f}mm) on a "
            f"{page_w_mm:.1f}x{page_h_mm:.1f}mm page")
    return LabelTemplate(
        id="custom", name=f"Custom — {name}", material="user-specified",
        printer="laser+inkjet",
        page_w_mm=page_w_mm, page_h_mm=page_h_mm,
        label_w_mm=label_w_mm, label_h_mm=label_h_mm,
        cols=cols, rows=rows,
        margin_top_mm=margin_top_mm, margin_left_mm=margin_left_mm,
        pitch_x_mm=pitch_x_mm, pitch_y_mm=pitch_y_mm,
        corner_radius_mm=corner_radius_mm,
        confidence=CUSTOM,
        sources=(), notes="User-entered dimensions -- not Avery-verified. "
                          "Print the test grid on plain paper first.",
        label_w_in=f"{label_w_mm / MM_PER_IN:.3f}\"",
        label_h_in=f"{label_h_mm / MM_PER_IN:.3f}\"",
    )


__all__ = [
    "LabelTemplate", "TEMPLATES", "list_templates", "get", "build_custom",
    "CONFIRMED", "CORROBORATED", "SINGLE_SOURCE", "UNVERIFIED", "CUSTOM",
    "CONFIDENCE_LEVELS", "MM_PER_IN",
]
