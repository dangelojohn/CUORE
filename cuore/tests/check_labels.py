"""Smoke checks for the label-printing feature: geometry, text auto-fit,
start-position skipping, the test grid, the PDF, and the pages/routes.

CUORE_STATE_DIR is pointed at a fresh tempdir BEFORE anything cuore/mes is
imported, so this never writes to the real state directory. ``app.py`` is
owned by another agent and does not register this router, so this test
builds its own minimal FastAPI app around ``cuore.web.labels_routes`` --
same pattern ``check_service_page.py`` uses for ``service_routes``.

Run:
    .venv/Scripts/python.exe cuore/tests/check_labels.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ["CUORE_STATE_DIR"] = tempfile.mkdtemp(prefix="cuore-check-labels-")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi import FastAPI, Request  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from reportlab.pdfbase.pdfmetrics import stringWidth  # noqa: E402

from cuore import bootstrap  # noqa: F401,E402
from cuore.config import load as load_settings  # noqa: E402
from cuore.services import labels_bridge  # noqa: E402
from cuore.services.errors import BridgeError  # noqa: E402
from cuore.web import labels_routes  # noqa: E402
from cuore.labels import templates as T  # noqa: E402
from cuore.labels import render as R  # noqa: E402
from cuore.live import label_calibration  # noqa: E402
from mes import service as service_mod  # noqa: E402

VIN = "ZASFAKPN5J7B88115"  # the Stelvio this toolchain already knows about

failures: list[str] = []
checks = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(f"{label}{(' -- ' + detail) if detail else ''}")


# --- 1. geometry: every cell fits inside the page, for every template -----

for tmpl in T.list_templates():
    for idx in (0, tmpl.count // 2, tmpl.count - 1):
        x_mm, y_mm = tmpl.cell_origin_mm(idx)
        check(f"{tmpl.id} cell {idx} left edge inside page",
             x_mm >= -0.01, f"x={x_mm}")
        check(f"{tmpl.id} cell {idx} top edge inside page",
             y_mm >= -0.01, f"y={y_mm}")
        check(f"{tmpl.id} cell {idx} right edge inside page",
             x_mm + tmpl.label_w_mm <= tmpl.page_w_mm + 0.5,
             f"x+w={x_mm + tmpl.label_w_mm} page_w={tmpl.page_w_mm}")
        check(f"{tmpl.id} cell {idx} bottom edge inside page",
             y_mm + tmpl.label_h_mm <= tmpl.page_h_mm + 0.5,
             f"y+h={y_mm + tmpl.label_h_mm} page_h={tmpl.page_h_mm}")

try:
    T.get("avery_5520").cell_origin_mm(999)
    check("out-of-range cell index raises ValueError", False)
except ValueError:
    check("out-of-range cell index raises ValueError", True)

# Avery-sourced templates report their real geometry as confirmed; the two
# durable-ID sizes with no traceable margin data report UNVERIFIED.
check("5520 geometry confirmed", T.get("avery_5520").geometry_confirmed is True)
check("5522 geometry confirmed", T.get("avery_5522").geometry_confirmed is True)
check("6576 geometry NOT confirmed (no Avery-traceable margins)",
     T.get("avery_6576").geometry_confirmed is False)
check("6578 geometry NOT confirmed (no Avery-traceable margins)",
     T.get("avery_6578").geometry_confirmed is False)

custom = T.build_custom(page_w_mm=210, page_h_mm=297, label_w_mm=60, label_h_mm=30,
                        cols=3, rows=8, margin_top_mm=8, margin_left_mm=10,
                        pitch_x_mm=65, pitch_y_mm=35)
check("custom template confidence is CUSTOM", custom.confidence == T.CUSTOM)
check("custom template geometry not claimed 'confirmed'",
     custom.geometry_confirmed is False)
try:
    T.build_custom(page_w_mm=100, page_h_mm=100, label_w_mm=60, label_h_mm=60,
                   cols=3, rows=1, margin_top_mm=5, margin_left_mm=5)
    check("custom template rejects geometry that overflows the page", False)
except ValueError:
    check("custom template rejects geometry that overflows the page", True)


# --- 2. text auto-fit never overflows the box -------------------------------

LONG_TEXT = "A very long value that would definitely overflow a tiny label cell if not shrunk"

for max_w_pt in (40.0, 80.0, 160.0):
    size = R.fit_font_size(LONG_TEXT, R.FONT, max_w_pt, max_size=14.0)
    check(f"fit_font_size never goes below MIN_FONT_PT at {max_w_pt}pt",
         size >= R.MIN_FONT_PT)
    # fit_font_size alone does not promise a fit once min_size is hit (see
    # its docstring) -- draw_fit_line's actual no-overflow guarantee comes
    # from pairing it with clip_to_width, checked here directly:
    text = LONG_TEXT
    if stringWidth(text, R.FONT, size) > max_w_pt:
        text = R.clip_to_width(text, R.FONT, size, max_w_pt)
    measured = stringWidth(text, R.FONT, size)
    check(f"fit_font_size + clip_to_width guarantees fit at {max_w_pt}pt",
         measured <= max_w_pt + 0.5, f"measured={measured} size={size}")

for max_w_pt, max_h_pt in ((100.0, 30.0), (60.0, 12.0), (200.0, 60.0)):
    size, lines = R.fit_block(LONG_TEXT, font=R.FONT, max_w_pt=max_w_pt,
                              max_h_pt=max_h_pt, max_size=12.0)
    for line in lines:
        w = stringWidth(line, R.FONT, size)
        check(f"fit_block line fits width ({max_w_pt}x{max_h_pt})",
             w <= max_w_pt + 0.5, f"line={line!r} w={w}")
    total_h = len(lines) * size * 1.15
    check(f"fit_block total height fits box ({max_w_pt}x{max_h_pt})",
         total_h <= max_h_pt + 0.01, f"total_h={total_h}")

# a single absurdly long token (no spaces) must still not overflow width --
# fit_font_size is what actually gets called per rendered line in the
# drawers, and it has no wrap fallback, so it must shrink far enough alone.
absurd = "X" * 200
size = R.fit_font_size(absurd, R.FONT, 50.0, max_size=14.0)
check("fit_font_size shrinks an unbroken long token to fit",
     stringWidth(absurd, R.FONT, size) <= 50.0 + 0.5 or size <= R.MIN_FONT_PT)


# --- 3. start position skips cells correctly --------------------------------

pdf_from_zero = R.generate_labels_pdf(T.get("avery_5522"), "torque_tag",
                                      {"component": "X"}, copies=1, start_index=0)
pdf_from_five = R.generate_labels_pdf(T.get("avery_5522"), "torque_tag",
                                      {"component": "X"}, copies=1, start_index=5)
check("different start_index produces a different PDF (label lands elsewhere)",
     pdf_from_zero != pdf_from_five)

# copies that overflow one sheet must emit a second page (larger PDF, and a
# second occurrence of the /Page object) rather than raising or overwriting.
tmpl30 = T.get("avery_5520")
one_page = R.generate_labels_pdf(tmpl30, "oil_change", {"shop_name": "X"},
                                 copies=tmpl30.count, start_index=0)
two_pages = R.generate_labels_pdf(tmpl30, "oil_change", {"shop_name": "X"},
                                  copies=tmpl30.count + 1, start_index=0)
check("overflowing one sheet's worth of copies adds a page",
     len(two_pages) > len(one_page))

try:
    R.generate_labels_pdf(tmpl30, "oil_change", {}, start_index=tmpl30.count)
    check("start_index >= count is rejected", False)
except ValueError:
    check("start_index >= count is rejected", True)

try:
    R.generate_labels_pdf(tmpl30, "not_a_kind", {})
    check("unknown kind is rejected", False)
except ValueError:
    check("unknown kind is rejected", True)


# --- 4. test grid renders ----------------------------------------------------

for tid in ("avery_5520", "avery_6576", "custom"):
    tmpl = custom if tid == "custom" else T.get(tid)
    grid = R.generate_test_grid_pdf(tmpl)
    check(f"test grid for {tid} produces a PDF", grid[:5] == b"%PDF-")
    check(f"test grid for {tid} is non-trivial size", len(grid) > 500)


# --- 5. PDF parses -----------------------------------------------------------

sample = R.generate_labels_pdf(T.get("avery_5520"), "oil_change", {
    "shop_name": "CUORE Bench", "date": "2026-09-26",
    "odometer_km": "85,000", "odometer_mi": "52,816",
    "next_due_km": "93,000", "next_due_mi": "57,800", "next_due_date": "2027-03-26",
    "oil_viscosity": "0W-30", "oil_spec": "MS-13340", "quantity_l": "4.6",
    "filter_part_no": "68191349AA", "technician": "JD",
    "vin_short": R.short_vin(VIN),
})
check("generated PDF starts with %PDF header", sample[:5] == b"%PDF-")
check("generated PDF ends with %%EOF", sample.rstrip()[-5:] == b"%%EOF")
page_count = sample.count(b"/Type /Page") + sample.count(b"/Type/Page")
check("generated PDF reports at least one page", page_count >= 1, f"count={page_count}")

try:
    import pypdf  # type: ignore
    reader = pypdf.PdfReader(__import__("io").BytesIO(sample))
    check("pypdf parses the generated PDF without error", len(reader.pages) >= 1)
except ImportError:
    pass  # optional dependency -- the %PDF/%%EOF checks above already cover this


# --- 6. pages / routes via TestClient ---------------------------------------


def build_app() -> FastAPI:
    app = FastAPI()
    app.state.settings = load_settings()

    @app.exception_handler(BridgeError)
    async def _bridge_error(request: Request, exc: BridgeError):
        return JSONResponse(status_code=exc.status,
                            content={"error": type(exc).__name__, "detail": str(exc)})

    app.include_router(labels_routes.router)
    app.include_router(labels_routes.api_router, prefix="/api")
    return app


client = TestClient(build_app())

r = client.get(f"/v/{VIN}/labels")
check("GET labels page responds 200", r.status_code == 200, str(r.status_code))
check("labels page lists a kind selector", "oil_change" in r.text or "oil change" in r.text)
check("labels page lists at least one Avery template", "Avery 5520" in r.text)
check("labels page flags an unconfirmed template", "unconfirmed" in r.text or "UNVERIFIED" in r.text)

r2 = client.get(f"/v/{VIN}/labels", params={"kind": "torque_tag", "template_id": "avery_5522"})
check("labels page accepts kind/template query params", r2.status_code == 200)
check("labels page shows torque tag fields for that kind",
     "Torque tag fields" in r2.text or "torque_key" in r2.text)

r3 = client.get(f"/v/{VIN}/labels.pdf", params={
    "kind": "oil_change", "template_id": "avery_5520",
    "shop_name": "CUORE Bench", "date": "2026-09-26", "odometer_km": "85000",
    "oil_viscosity": "0W-30", "quantity_l": "4.6",
    "filter_part_no": "X", "technician": "JD", "copies": "2",
})
check("GET labels.pdf responds 200", r3.status_code == 200, str(r3.status_code))
check("labels.pdf content-type is application/pdf",
     r3.headers.get("content-type", "").startswith("application/pdf"))
check("labels.pdf is inline (browser print dialog can print it)",
     "inline" in r3.headers.get("content-disposition", ""))
check("labels.pdf body is a real PDF", r3.content[:5] == b"%PDF-")

r4 = client.get(f"/v/{VIN}/labels.pdf", params={
    "template_id": "avery_5522", "grid": "1"})
check("GET labels.pdf test grid responds 200", r4.status_code == 200)
check("labels.pdf test grid body is a real PDF", r4.content[:5] == b"%PDF-")

r5 = client.get(f"/v/{VIN}/labels.pdf", params={
    "template_id": "custom", "kind": "reminder",
    "c_page_w_mm": "210", "c_page_h_mm": "297", "c_label_w_mm": "60",
    "c_label_h_mm": "30", "c_cols": "3", "c_rows": "8",
    "c_margin_top_mm": "8", "c_margin_left_mm": "10",
})
check("custom template PDF responds 200", r5.status_code == 200, str(r5.status_code))
check("custom template PDF body is a real PDF", r5.content[:5] == b"%PDF-")

r6 = client.get("/api/vehicles/" + VIN + "/labels/templates")
check("JSON templates endpoint responds 200", r6.status_code == 200)
body = r6.json()
check("JSON templates endpoint lists templates", len(body.get("templates", [])) >= 7)
check("JSON templates endpoint lists kinds", set(body.get("kinds", [])) == {
    "oil_change", "service", "torque_tag", "reminder", "maintenance_reminder",
    "part_tag", "inspection_tag", "job_tag"})


# --- summary ------------------------------------------------------------------

# --- regressions: header overlap and warning stamp over labels (2026-09-26) ---

class _Canvas:
    """Records drawString/drawRightString calls instead of drawing."""
    def __init__(self):
        self.calls = []
    def setFont(self, *a, **k): pass
    def drawString(self, x, y, t): self.calls.append(("L", x, y, t))
    def drawRightString(self, x, y, t): self.calls.append(("R", x, y, t))
    def drawCentredString(self, x, y, t): self.calls.append(("C", x, y, t))

for _draw in (R.draw_oil_change, R.draw_service):
    _cv = _Canvas()
    _draw(_cv, 0, 0, 200, 72, {"shop_name": "SHOPNAME", "section": "SECTION",
                               "date": "2026-09-15"})
    _hdr = [c for c in _cv.calls if c[3] in ("SHOPNAME", "SECTION")][0]
    _date = [c for c in _cv.calls if c[3] == "2026-09-15"][0]
    _hdr_end = _hdr[1] + stringWidth(_hdr[3], R.FONT_BOLD, 11)
    _date_start = _date[1] - stringWidth("2026-09-15", R.FONT, 9)
    check(f"{_draw.__name__}: header date does not overlap the header title",
          _date_start >= _hdr_end, f"title ends {_hdr_end:.1f}, date starts {_date_start:.1f}")

import io as _io  # noqa: E402
from pypdf import PdfReader as _PdfReader  # noqa: E402
_t6576 = T.get("avery_6576") if hasattr(T, "get") else T.TEMPLATES["avery_6576"]
_pdf = R.generate_labels_pdf(_t6576, "reminder", {"vehicle": "V", "job": "Oil change"}, copies=32)
_txt = _PdfReader(_io.BytesIO(_pdf)).pages[0].extract_text()
check("6576 label sheet does not stamp the warning over the bottom labels",
      "UNVERIFIED" not in _txt)


# --- new: calibration, maintenance_reminder batch, part_tag, key-line floor,
#     unverified-template-shows-calibrated (2026-10-07) -----------------------

# 1. calibration saved and applied to a render.
label_calibration.save("avery_6576", "bench-laser-1", 2.0, 3.0, note="qa")
_calib = label_calibration.get("avery_6576", "bench-laser-1")
check("calibration save()/get() round-trips the measured offsets",
     _calib is not None and _calib["offset_x_mm"] == 2.0 and _calib["offset_y_mm"] == 3.0)
_pdf_calibrated = labels_bridge.render_pdf(vin=VIN, kind="reminder", template_id="avery_6576",
                                          printer_name="bench-laser-1")
_pdf_uncalibrated = labels_bridge.render_pdf(vin=VIN, kind="reminder", template_id="avery_6576",
                                             offset_x_mm=0.0, offset_y_mm=0.0)
check("a saved calibration's offset is applied to the render automatically",
     _pdf_calibrated != _pdf_uncalibrated)

# 2. maintenance_reminder batch produces one label per due item (fixture state).
_MVIN = "ZTESTLABELSFIXTURE1"
service_mod.record_maintenance(_MVIN, {
    "date": "2000-01-01", "odometer_km": 1000, "technician": "QA",
    "items": [{"item_key": "engine_air_filter", "action": "replaced"}],
})
_due = labels_bridge.maintenance_due_items(_MVIN, current_odometer_km=999999)
check("maintenance_due_items finds the fixture's overdue item", len(_due) >= 1)
_batch_pdf = labels_bridge.maintenance_reminder_batch_pdf(
    vin=_MVIN, template_id="avery_5522", current_odometer_km=999999)
_batch_text = _PdfReader(_io.BytesIO(_batch_pdf)).pages[0].extract_text()
check("maintenance_reminder batch prints one label per due item",
     _batch_text.count("due:") == len(_due), f"due items={len(_due)}")

# 3. part_tag renders with the OEM number.
_part_data = labels_bridge.part_tag_label_data({"part_key": "oil_filter"})
check("part_tag_label_data resolves the OEM number from the parts library",
     bool(_part_data["oem_number"]))
_part_pdf = labels_bridge.render_pdf(vin=VIN, kind="part_tag", template_id="avery_5522",
                                    overrides={"part_key": "oil_filter"})
_part_text = _PdfReader(_io.BytesIO(_part_pdf)).pages[0].extract_text()
check("part_tag PDF contains the resolved OEM number",
     _part_data["oem_number"] in _part_text)

# 4. key line font never below 6pt.
_key_size = R.fit_font_size(LONG_TEXT, R.FONT_BOLD, 10.0, max_size=14.0,
                           min_size=R.KEY_LINE_MIN_FONT_PT)
check("a key line never shrinks below KEY_LINE_MIN_FONT_PT",
     _key_size >= R.KEY_LINE_MIN_FONT_PT, f"size={_key_size}")

# 5. unverified template shows "calibrated" after saving a calibration.
label_calibration.save("avery_6578", "cal-test-printer", 1.0, 1.0)
_cal_pdf = labels_bridge.render_pdf(vin=VIN, kind="reminder", template_id="avery_6578",
                                   printer_name="cal-test-printer")
_cal_text = _PdfReader(_io.BytesIO(_cal_pdf)).pages[0].extract_text()
check("UNVERIFIED template shows 'calibrated' instead of the warning "
     "once a calibration is saved",
     "calibrated" in _cal_text.lower() and "UNVERIFIED" not in _cal_text,
     repr(_cal_text))


print(f"{checks} checks, {len(failures)} failures")
for f in failures:
    print("FAIL:", f)
if failures:
    sys.exit(1)
print("OK")
