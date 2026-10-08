"""Render label PDFs with reportlab.

Everything here takes a :class:`cuore.labels.templates.LabelTemplate` plus a
plain dict of field values and returns PDF bytes -- no ``mes``/``cuore``
imports, no filesystem, no state directory, so this is testable standalone.

Text auto-fit: every drawer below measures with
``reportlab.pdfbase.pdfmetrics.stringWidth`` before drawing and shrinks the
font (down to ``MIN_FONT_PT``) rather than letting a long value run past the
label's edge -- these sheets are small on purpose, so overflow is the normal
case to guard against, not an edge case. Every drawing call additionally
happens inside a clip path scoped to that one cell, so even a bug in a fit
calculation cannot bleed into the next label.

No colour dependence: severity/emphasis is carried by font weight, size and
box rules only, so a mono laser printer (most of the target sheets are laser-
only anyway) renders every label correctly.
"""

from __future__ import annotations

from io import BytesIO
from typing import Any, Callable, Optional

from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from .templates import LabelTemplate

PT_PER_MM = 72.0 / 25.4
KM_PER_MI = 1.609344
NM_PER_LBFT = 1.35582

FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
MIN_FONT_PT = 4.0
#: Floor for the one "key line" of each label kind (the value a tech must
#: still be able to read even on a badly-shrunk label) -- every other line
#: on the label still falls back to MIN_FONT_PT. Raised from 4pt to 6pt
#: per the readability requirement; drawers pass this as ``min_size`` only
#: on their key line, never globally.
KEY_LINE_MIN_FONT_PT = 6.0
PAD_MM = 1.4


def mm_to_pt(mm: float) -> float:
    return mm * PT_PER_MM


def km_to_mi(km: Optional[float]) -> Optional[float]:
    if km is None:
        return None
    try:
        return float(km) / KM_PER_MI
    except (TypeError, ValueError):
        return None


def nm_to_lbft(nm: Optional[float]) -> Optional[float]:
    if nm is None:
        return None
    try:
        return float(nm) / NM_PER_LBFT
    except (TypeError, ValueError):
        return None


def short_vin(vin: str, n: int = 8) -> str:
    vin = (vin or "").strip()
    return vin[-n:] if len(vin) > n else vin


# --- text fitting ------------------------------------------------------------


def fit_font_size(text: str, font: str, max_w_pt: float, max_size: float,
                  min_size: float = MIN_FONT_PT) -> float:
    """Largest size (stepping down by 0.5pt) at which ``text`` fits within
    ``max_w_pt`` on one line, never going below ``min_size``.

    This alone does not guarantee the text fits at ``min_size`` -- a long
    enough string can still overflow a narrow box even at the smallest
    readable font. Callers that must never overflow (every drawer below)
    pair this with :func:`clip_to_width`, which truncates with an ellipsis
    as the last resort."""
    if max_w_pt <= 0:
        return min_size
    size = max_size
    while size > min_size and stringWidth(text, font, size) > max_w_pt:
        size -= 0.5
    return round(max(size, min_size), 2)


def clip_to_width(text: str, font: str, size: float, max_w_pt: float) -> str:
    """Truncate ``text`` (adding an ellipsis) until it fits ``max_w_pt`` at
    ``size`` -- the guaranteed-no-overflow fallback once shrinking the font
    has hit its floor. Returns ``""`` if even an ellipsis does not fit."""
    if max_w_pt <= 0:
        return ""
    if stringWidth(text, font, size) <= max_w_pt:
        return text
    ell = "…"
    for n in range(len(text), 0, -1):
        candidate = text[:n].rstrip() + ell
        if stringWidth(candidate, font, size) <= max_w_pt:
            return candidate
    return ell if stringWidth(ell, font, size) <= max_w_pt else ""


def draw_fit_line(c: canvas.Canvas, x: float, y_baseline: float, max_w_pt: float,
                  text: str, *, font: str = FONT, max_size: float = 9.0,
                  min_size: float = MIN_FONT_PT, align: str = "left") -> float:
    """Draw ``text`` as a single line inside ``max_w_pt``, shrinking to fit
    and, if even ``min_size`` cannot fit, truncating with an ellipsis --
    guaranteed to never draw past ``max_w_pt``. Returns the font size used."""
    text = "" if text is None else str(text)
    size = fit_font_size(text, font, max_w_pt, max_size, min_size)
    if stringWidth(text, font, size) > max_w_pt:
        text = clip_to_width(text, font, size, max_w_pt)
    c.setFont(font, size)
    if align == "right":
        c.drawRightString(x + max_w_pt, y_baseline, text)
    elif align == "center":
        c.drawCentredString(x + max_w_pt / 2.0, y_baseline, text)
    else:
        c.drawString(x, y_baseline, text)
    return size


def _split_long_word(word: str, font: str, size: float, max_w_pt: float) -> list[str]:
    """Hard-break a single word wider than ``max_w_pt`` into pieces that
    each fit -- otherwise a URL/part-number/VIN with no spaces would sail
    past the edge of a narrow cell no matter how small the font gets."""
    if max_w_pt <= 0 or stringWidth(word, font, size) <= max_w_pt:
        return [word]
    pieces: list[str] = []
    cur = ""
    for ch in word:
        trial = cur + ch
        if not cur or stringWidth(trial, font, size) <= max_w_pt:
            cur = trial
        else:
            pieces.append(cur)
            cur = ch
    if cur:
        pieces.append(cur)
    return pieces


def _wrap_lines(text: str, font: str, size: float, max_w_pt: float) -> list[str]:
    """Word-wrap ``text`` to ``max_w_pt`` at ``size``. Every returned line
    is guaranteed to fit ``max_w_pt`` (a word alone wider than the box is
    hard-broken by :func:`_split_long_word`), so a caller that already
    picked a size this wraps at can draw every line without re-checking."""
    words = (text or "").split()
    if not words:
        return [""]
    lines: list[str] = []
    cur = ""
    for w in words:
        if stringWidth(w, font, size) > max_w_pt:
            if cur:
                lines.append(cur)
                cur = ""
            lines.extend(_split_long_word(w, font, size, max_w_pt))
            continue
        trial = (cur + " " + w).strip()
        if not cur or stringWidth(trial, font, size) <= max_w_pt:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def fit_block(text: str, *, font: str = FONT, max_w_pt: float, max_h_pt: float,
             max_size: float = 9.0, min_size: float = MIN_FONT_PT,
             line_spacing: float = 1.15) -> tuple[float, list[str]]:
    """Wrap ``text`` to ``max_w_pt`` and shrink the font until every line
    fits both the width and the total block height. Guaranteed to return a
    layout that fits ``max_h_pt`` at ``min_size`` by truncating with an
    ellipsis as a last resort, so a caller can never overflow the cell."""
    size = max_size
    while size >= min_size:
        lines = _wrap_lines(text, font, size, max_w_pt)
        if len(lines) * size * line_spacing <= max_h_pt:
            return size, lines
        size -= 0.5
    lines = _wrap_lines(text, font, min_size, max_w_pt)
    max_lines = max(1, int(max_h_pt / (min_size * line_spacing)))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        lines[-1] = clip_to_width(last + "…", font, min_size, max_w_pt)
    # Safety net: _wrap_lines already guarantees each line fits max_w_pt at
    # min_size, but re-clip anyway so this holds even if that invariant is
    # ever broken by a future edit -- draw_fit_block must never overflow.
    lines = [clip_to_width(l, font, min_size, max_w_pt) for l in lines]
    return min_size, lines


def draw_fit_block(c: canvas.Canvas, x: float, y_top: float, w_pt: float, h_pt: float,
                   text: str, *, font: str = FONT, max_size: float = 9.0,
                   min_size: float = MIN_FONT_PT, line_spacing: float = 1.15) -> float:
    """Draw a wrapped, auto-shrunk text block with its top-left at
    ``(x, y_top)`` (reportlab y-up coordinates). Returns the font size used."""
    size, lines = fit_block(text, font=font, max_w_pt=w_pt, max_h_pt=h_pt,
                            max_size=max_size, min_size=min_size,
                            line_spacing=line_spacing)
    c.setFont(font, size)
    y = y_top - size
    for line in lines:
        c.drawString(x, y, line)
        y -= size * line_spacing
    return size


def _qr_drawing(url: str, size_pt: float):
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    widget = QrCodeWidget(url)
    b = widget.getBounds()
    w, h = b[2] - b[0], b[3] - b[1]
    d = Drawing(size_pt, size_pt, transform=[size_pt / w, 0, 0, size_pt / h, 0, 0])
    d.add(widget)
    return d


def _draw_qr(c: canvas.Canvas, x: float, y: float, size_pt: float, url: str) -> None:
    from reportlab.graphics import renderPDF
    renderPDF.draw(_qr_drawing(url, size_pt), c, x, y)


# --- per-kind drawers ---------------------------------------------------------
# Each drawer signature: (canvas, x, y, w, h, data, qr_url) -- x/y is the
# cell's bottom-left corner in points (reportlab's native origin), w/h its
# size in points. Drawers must stay inside (x, y, x+w, y+h); the caller also
# clips to this rect so a bug here cannot bleed into the neighbouring label.


def _pad(w: float, h: float) -> float:
    return mm_to_pt(PAD_MM)


def draw_oil_change(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                    data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    qr_w = mm_to_pt(h / PT_PER_MM * 0.55) if qr_url else 0.0
    if qr_url:
        iw -= qr_w + pad
    top = y + h - pad
    shop = data.get("shop_name") or "CUORE"
    date = data.get("date") or ""
    row_h = h / 5.0

    draw_fit_line(c, ix, top - row_h * 0.75, iw * 0.62, shop, font=FONT_BOLD,
                 max_size=min(10.0, row_h))
    draw_fit_line(c, ix + iw * 0.62, top - row_h * 0.75, iw * 0.38, date, font=FONT,
                 max_size=min(9.0, row_h), align="right", )

    next_km = data.get("next_due_km")
    next_mi = data.get("next_due_mi")
    next_date = data.get("next_due_date")
    bits = []
    if next_km:
        bits.append(f"{next_km} km")
    if next_mi:
        bits.append(f"{next_mi} mi")
    next_line = "NEXT: " + " / ".join(bits) if bits else "NEXT: unknown"
    if next_date:
        next_line += f" or {next_date}"
    basis = data.get("next_due_basis")
    if basis:
        next_line += f" (basis: {basis})"
    draw_fit_line(c, ix, top - row_h * 1.9, iw, next_line, font=FONT_BOLD,
                 max_size=min(11.0, row_h * 1.1), min_size=KEY_LINE_MIN_FONT_PT)

    odo_km = data.get("odometer_km")
    odo_mi = data.get("odometer_mi")
    odo_line = f"Odo: {odo_km or '?'} km ({odo_mi or '?'} mi)"
    draw_fit_line(c, ix, top - row_h * 2.9, iw, odo_line, font=FONT,
                 max_size=min(8.0, row_h))

    oil_line = " / ".join(x for x in (
        data.get("oil_viscosity"), data.get("oil_spec"),
        (f"{data.get('quantity_l')} L" if data.get("quantity_l") else None),
    ) if x)
    draw_fit_line(c, ix, top - row_h * 3.7, iw, oil_line or "oil: unknown",
                 font=FONT, max_size=min(8.0, row_h))

    tail = " | ".join(x for x in (
        (f"Filter {data.get('filter_part_no')}" if data.get("filter_part_no") else None),
        (f"Tech {data.get('technician')}" if data.get("technician") else None),
        (f"VIN..{data.get('vin_short')}" if data.get("vin_short") else None),
    ) if x)
    draw_fit_line(c, ix, top - row_h * 4.6, iw, tail, font=FONT,
                 max_size=min(7.0, row_h))

    if qr_url:
        _draw_qr(c, x + w - pad - qr_w, y + pad, qr_w, qr_url)


def draw_service(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                 data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    qr_w = mm_to_pt(h / PT_PER_MM * 0.4) if qr_url else 0.0
    if qr_url:
        iw -= qr_w + pad
    top = y + h - pad

    section = (data.get("section") or "Service").upper()
    date = data.get("date") or ""
    header_h = h * 0.14
    draw_fit_line(c, ix, top - header_h * 0.8, iw * 0.65, section, font=FONT_BOLD,
                 max_size=11.0)
    draw_fit_line(c, ix + iw * 0.65, top - header_h * 0.8, iw * 0.35, date, font=FONT,
                 max_size=9.0, align="right")

    body_top = top - header_h - mm_to_pt(0.6)
    body_h = h * 0.38
    draw_fit_block(c, ix, body_top, iw, body_h,
                   data.get("work_done") or "(no summary recorded)",
                   font=FONT, max_size=8.5)

    line_h = h * 0.13
    y2 = body_top - body_h - mm_to_pt(0.4)
    odo_line = (f"Odo {data.get('odometer_km') or '?'} km "
               f"({data.get('odometer_mi') or '?'} mi)")
    draw_fit_line(c, ix, y2, iw, odo_line, font=FONT, max_size=8.0)

    y2 -= line_h
    next_line = "Next due: " + (data.get("next_due") or "unknown")
    draw_fit_line(c, ix, y2, iw, next_line, font=FONT_BOLD, max_size=8.5,
                 min_size=KEY_LINE_MIN_FONT_PT)

    y2 -= line_h
    spec_line = " / ".join(x for x in (
        (f"Spec: {data.get('key_spec')}" if data.get("key_spec") else None),
        (f"Torque: {data.get('key_torque')}" if data.get("key_torque") else None),
    ) if x)
    draw_fit_line(c, ix, y2, iw, spec_line or "", font=FONT, max_size=8.0)

    tech_line = f"Tech {data.get('technician') or '?'}"
    draw_fit_line(c, ix, y + pad, iw, tech_line, font=FONT, max_size=7.5)

    if qr_url:
        _draw_qr(c, x + w - pad - qr_w, y + pad, qr_w, qr_w)


def draw_torque_tag(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                    data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    top = y + h - pad

    header_h = h * 0.18
    draw_fit_line(c, ix, top - header_h * 0.8, iw, data.get("component") or "Component",
                 font=FONT_BOLD, max_size=10.0)

    nm = data.get("torque_nm")
    lbft = data.get("torque_lbft")
    parts = []
    if nm:
        parts.append(f"{nm} Nm")
    if lbft:
        parts.append(f"{lbft} lb-ft")
    torque_line = " / ".join(parts) if parts else "UNKNOWN torque"
    if data.get("angle"):
        torque_line += f" + {data['angle']}"
    val_h = h * 0.34
    draw_fit_line(c, ix, top - header_h - val_h * 0.6, iw, torque_line,
                 font=FONT_BOLD, max_size=16.0, min_size=KEY_LINE_MIN_FONT_PT)

    flags = []
    if data.get("single_use"):
        flags.append("SINGLE-USE -- DO NOT REUSE")
    y2 = top - header_h - val_h - mm_to_pt(0.4)
    if flags:
        draw_fit_line(c, ix, y2, iw, " | ".join(flags), font=FONT_BOLD, max_size=8.5)
        y2 -= h * 0.14

    tail = " | ".join(x for x in (
        data.get("date"),
        (f"Tech {data.get('technician')}" if data.get("technician") else None),
    ) if x)
    draw_fit_line(c, ix, y + pad, iw, tail, font=FONT, max_size=8.0)


def draw_reminder(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                  data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    top = y + h - pad

    draw_fit_line(c, ix, top - h * 0.12, iw, "NEXT SERVICE DUE", font=FONT_BOLD,
                 max_size=10.0)

    bits = []
    if data.get("next_due_km"):
        bits.append(f"{data['next_due_km']} km")
    if data.get("next_due_mi"):
        bits.append(f"{data['next_due_mi']} mi")
    due_line = " / ".join(bits) if bits else "UNKNOWN"
    draw_fit_line(c, ix, top - h * 0.42, iw, due_line, font=FONT_BOLD, max_size=20.0,
                 min_size=KEY_LINE_MIN_FONT_PT)

    if data.get("next_due_date"):
        draw_fit_line(c, ix, top - h * 0.64, iw, f"or {data['next_due_date']}",
                     font=FONT, max_size=11.0)

    tail = " -- ".join(x for x in (data.get("vehicle"), data.get("job")) if x)
    draw_fit_line(c, ix, y + pad + h * 0.06, iw, tail, font=FONT, max_size=9.0)


def draw_maintenance_reminder(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                              data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    """One overdue/due-soon :mod:`mes.maintenance_specs` item -- the per-item
    label the "Print all due" batch produces one of for each item."""
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    top = y + h - pad

    status = (data.get("status") or "").upper().replace("_", " ")
    draw_fit_line(c, ix, top - h * 0.14, iw, status or "MAINTENANCE DUE",
                 font=FONT_BOLD, max_size=10.0)

    item = data.get("item") or "(item)"
    draw_fit_line(c, ix, top - h * 0.42, iw, item, font=FONT_BOLD, max_size=14.0,
                 min_size=KEY_LINE_MIN_FONT_PT)

    bits = []
    if data.get("due_km"):
        bits.append(f"{data['due_km']} km")
    if data.get("due_date"):
        bits.append(data["due_date"])
    due_line = "due: " + " / ".join(bits) if bits else "due: unknown"
    draw_fit_line(c, ix, top - h * 0.64, iw, due_line, font=FONT, max_size=9.0)

    vin_short = data.get("vin_short")
    if vin_short:
        draw_fit_line(c, ix, y + pad + h * 0.04, iw, f"VIN..{vin_short}", font=FONT,
                     max_size=7.5)


def draw_part_tag(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                  data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    top = y + h - pad

    name = data.get("part_name") or "(part)"
    draw_fit_line(c, ix, top - h * 0.16, iw, name, font=FONT_BOLD, max_size=11.0,
                 min_size=KEY_LINE_MIN_FONT_PT)

    oem = data.get("oem_number")
    conf = data.get("oem_confidence")
    oem_line = (f"OEM {oem}" + (f" ({conf})" if conf else "")) if oem else "OEM: unknown"
    draw_fit_line(c, ix, top - h * 0.38, iw, oem_line, font=FONT, max_size=9.0)

    y2 = top - h * 0.58
    if data.get("torque"):
        draw_fit_line(c, ix, y2, iw, f"Torque: {data['torque']}", font=FONT, max_size=8.0)
        y2 -= h * 0.16

    tail = " | ".join(t for t in (
        data.get("related"),
        data.get("date"),
        (f"by {data.get('technician')}" if data.get("technician") else None),
    ) if t)
    draw_fit_line(c, ix, y + pad, iw, tail, font=FONT, max_size=7.5)


def draw_inspection_tag(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                        data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    top = y + h - pad

    draw_fit_line(c, ix, top - h * 0.16, iw, data.get("element") or "(element)",
                 font=FONT_BOLD, max_size=11.0)

    condition = (data.get("condition") or "unknown").upper()
    draw_fit_line(c, ix, top - h * 0.46, iw, condition, font=FONT_BOLD, max_size=16.0,
                 min_size=KEY_LINE_MIN_FONT_PT)

    tail = " | ".join(t for t in (data.get("date"),
                                  (f"by {data.get('by')}" if data.get("by") else None)) if t)
    draw_fit_line(c, ix, y + pad, iw, tail, font=FONT, max_size=8.0)


def draw_job_tag(c: canvas.Canvas, x: float, y: float, w: float, h: float,
                 data: dict[str, Any], qr_url: Optional[str] = None) -> None:
    pad = _pad(w, h)
    ix, iw = x + pad, w - 2 * pad
    top = y + h - pad

    header = f"JOB {data.get('job_id') or '?'}"
    draw_fit_line(c, ix, top - h * 0.14, iw, header, font=FONT_BOLD, max_size=10.0)

    status = (data.get("status") or "open").upper()
    draw_fit_line(c, ix, top - h * 0.38, iw, status, font=FONT_BOLD, max_size=14.0,
                 min_size=KEY_LINE_MIN_FONT_PT)

    draw_fit_block(c, ix, top - h * 0.5, iw, h * 0.3,
                   data.get("complaint") or "(no complaint)", font=FONT, max_size=8.0)

    tail = " | ".join(t for t in (
        (f"Tech {data.get('technician')}" if data.get("technician") else None),
        data.get("opened_date"),
    ) if t)
    draw_fit_line(c, ix, y + pad, iw, tail, font=FONT, max_size=7.5)


_DRAWERS: dict[str, Callable[..., None]] = {
    "oil_change": draw_oil_change,
    "service": draw_service,
    "torque_tag": draw_torque_tag,
    "reminder": draw_reminder,
    "maintenance_reminder": draw_maintenance_reminder,
    "part_tag": draw_part_tag,
    "inspection_tag": draw_inspection_tag,
    "job_tag": draw_job_tag,
}

KINDS = tuple(_DRAWERS.keys())


# --- page assembly -------------------------------------------------------


def _draw_cell_border_stub(c: canvas.Canvas, x: float, y: float, w: float, h: float) -> None:
    """A faint 0.25pt outline -- helps see the cell edge when proofing on
    plain paper; invisible enough not to matter on the real film."""
    c.saveState()
    c.setLineWidth(0.25)
    c.setStrokeGray(0.85)
    c.rect(x, y, w, h, stroke=1, fill=0)
    c.restoreState()


def _finish_page(c: canvas.Canvas, template: LabelTemplate, page_w_pt: float,
                 page_h_pt: float, used: bool,
                 calibration_note: Optional[str] = None) -> None:
    if not used:
        return
    if not template.geometry_confirmed:
        # Only stamp the warning where it cannot land on a label: the
        # bottom margin must be at least 5 mm (evenly-distributed fallback
        # layouts often leave ~3 mm) for the full warning sentence -- but a
        # short "calibrated on ..." note needs only enough room for one
        # line of 6.5pt text (~2.3mm), so it gets a lower bar and still
        # shows on tight layouts like 6576/6578 (~2.8/4.2mm). The web page
        # and the test grid always carry the warning, so skipping it here
        # loses nothing.
        _, last_y = template.cell_origin_mm(template.count - 1)
        bottom_margin_mm = template.page_h_mm - (last_y + template.label_h_mm)
        min_margin_mm = 2.5 if calibration_note else 5.0
        if bottom_margin_mm < min_margin_mm:
            return
        c.saveState()
        c.setFont(FONT, 6.5)
        c.setFillGray(0.5)
        # A saved calibration for this (template, printer) pair is better
        # news than the generic warning -- someone already measured this
        # sheet on this printer, so say so instead of telling them to.
        msg = calibration_note or (
            f"UNVERIFIED geometry ({template.id}) -- print a test "
            "grid on plain paper and check alignment before using "
            "film. See docs/reference/AVERY_LABEL_TEMPLATES.md.")
        c.drawString(mm_to_pt(3), mm_to_pt(min(3.0, bottom_margin_mm / 2.0 - 1.0)), msg)
        c.restoreState()


def generate_labels_pdf_multi(template: LabelTemplate, kind: str,
                              data_list: list[dict[str, Any]], *, start_index: int = 0,
                              offset_x_mm: float = 0.0, offset_y_mm: float = 0.0,
                              qr_url: Optional[str] = None,
                              show_cell_outline: bool = False,
                              calibration_note: Optional[str] = None) -> bytes:
    """Render one label per entry in ``data_list`` (all the same ``kind``),
    walking cells left-to-right/top-to-bottom from 0-based cell
    ``start_index`` and overflowing onto additional pages as needed -- the
    batch form of :func:`generate_labels_pdf`, for a caller (e.g. "print
    all due") that needs a different value per label rather than N copies
    of one."""
    if kind not in _DRAWERS:
        raise ValueError(f"unknown label kind: {kind!r} (have {', '.join(KINDS)})")
    if not data_list:
        raise ValueError("data_list must not be empty")
    if not (0 <= start_index < template.count):
        raise ValueError(
            f"start_index {start_index} out of range for {template.id!r} "
            f"(0..{template.count - 1})")

    draw_fn = _DRAWERS[kind]
    buf = BytesIO()
    page_w_pt = mm_to_pt(template.page_w_mm)
    page_h_pt = mm_to_pt(template.page_h_mm)
    c = canvas.Canvas(buf, pagesize=(page_w_pt, page_h_pt))

    idx = start_index
    used_on_page = False
    for data in data_list:
        if idx >= template.count:
            _finish_page(c, template, page_w_pt, page_h_pt, used_on_page, calibration_note)
            c.showPage()
            idx = 0
            used_on_page = False
        x_mm, y_mm = template.cell_origin_mm(idx)
        x_pt = mm_to_pt(x_mm + offset_x_mm)
        y_top_pt = mm_to_pt(y_mm + offset_y_mm)
        w_pt = mm_to_pt(template.label_w_mm)
        h_pt = mm_to_pt(template.label_h_mm)
        y_bottom_pt = page_h_pt - y_top_pt - h_pt

        c.saveState()
        if show_cell_outline:
            _draw_cell_border_stub(c, x_pt, y_bottom_pt, w_pt, h_pt)
        p = c.beginPath()
        p.rect(x_pt, y_bottom_pt, w_pt, h_pt)
        c.clipPath(p, stroke=0, fill=0)
        draw_fn(c, x_pt, y_bottom_pt, w_pt, h_pt, data, qr_url)
        c.restoreState()

        used_on_page = True
        idx += 1

    _finish_page(c, template, page_w_pt, page_h_pt, used_on_page, calibration_note)
    c.showPage()
    c.save()
    return buf.getvalue()


def generate_labels_pdf(template: LabelTemplate, kind: str, data: dict[str, Any],
                        *, copies: int = 1, start_index: int = 0,
                        offset_x_mm: float = 0.0, offset_y_mm: float = 0.0,
                        qr_url: Optional[str] = None,
                        show_cell_outline: bool = False,
                        calibration_note: Optional[str] = None) -> bytes:
    """Render ``copies`` repeats of one label (``kind``, ``data``) onto
    ``template``, starting at 0-based cell ``start_index`` so a partly-used
    sheet can be reused, overflowing onto additional pages as needed."""
    if copies < 1:
        raise ValueError("copies must be >= 1")
    return generate_labels_pdf_multi(
        template, kind, [data] * copies, start_index=start_index,
        offset_x_mm=offset_x_mm, offset_y_mm=offset_y_mm, qr_url=qr_url,
        show_cell_outline=show_cell_outline, calibration_note=calibration_note)


def generate_test_grid_pdf(template: LabelTemplate, *,
                           offset_x_mm: float = 0.0, offset_y_mm: float = 0.0) -> bytes:
    """One page outlining every label cell plus its index, for checking
    alignment on plain paper before committing to film."""
    buf = BytesIO()
    page_w_pt = mm_to_pt(template.page_w_mm)
    page_h_pt = mm_to_pt(template.page_h_mm)
    c = canvas.Canvas(buf, pagesize=(page_w_pt, page_h_pt))

    confirmed = ("Avery-confirmed geometry" if template.geometry_confirmed
                else "UNVERIFIED geometry (evenly-distributed placeholder)")
    # The page header needs ~11 mm above the first row; tight layouts (the
    # evenly-distributed durable-ID fallback leaves ~3 mm) get the template
    # name printed inside each cell instead, so nothing covers a cell edge.
    _, first_y_mm = template.cell_origin_mm(0)
    header_fits = first_y_mm + offset_y_mm >= 11.0
    cell_tag = (f"{template.id} test grid -- "
                + ("confirmed" if template.geometry_confirmed else "UNVERIFIED"))
    if header_fits:
        c.setFont(FONT_BOLD, 8)
        c.drawString(mm_to_pt(3), page_h_pt - mm_to_pt(6),
                     f"TEST GRID -- {template.name}")
        c.setFont(FONT, 6.5)
        c.drawString(mm_to_pt(3), page_h_pt - mm_to_pt(10),
                     f"{confirmed} -- {template.cols}x{template.rows} = "
                     f"{template.count} labels, {template.label_w_in} x "
                     f"{template.label_h_in} nominal. Print at 100% / actual "
                     "size, never fit-to-page.")

    for idx in range(template.count):
        x_mm, y_mm = template.cell_origin_mm(idx)
        x_pt = mm_to_pt(x_mm + offset_x_mm)
        y_top_pt = mm_to_pt(y_mm + offset_y_mm)
        w_pt = mm_to_pt(template.label_w_mm)
        h_pt = mm_to_pt(template.label_h_mm)
        y_bottom_pt = page_h_pt - y_top_pt - h_pt

        c.saveState()
        c.setLineWidth(0.5)
        c.setStrokeGray(0.2)
        c.rect(x_pt, y_bottom_pt, w_pt, h_pt, stroke=1, fill=0)
        # a crosshair at the cell centre makes a scanner-drum skew visible
        cx, cy = x_pt + w_pt / 2, y_bottom_pt + h_pt / 2
        c.line(cx - 3, cy, cx + 3, cy)
        c.line(cx, cy - 3, cx, cy + 3)
        c.setFont(FONT, min(8.0, h_pt * 0.3))
        c.drawCentredString(cx, y_bottom_pt + 2, str(idx))
        if not header_fits:
            draw_fit_line(c, x_pt + 2, y_bottom_pt + h_pt - 8, w_pt - 4, cell_tag,
                          font=FONT, max_size=6.0, align="center")
        c.restoreState()

    c.showPage()
    c.save()
    return buf.getvalue()


__all__ = [
    "generate_labels_pdf", "generate_labels_pdf_multi", "generate_test_grid_pdf", "KINDS",
    "fit_font_size", "fit_block", "draw_fit_line", "draw_fit_block",
    "clip_to_width", "km_to_mi", "nm_to_lbft", "short_vin", "mm_to_pt",
    "MIN_FONT_PT", "KEY_LINE_MIN_FONT_PT",
]
