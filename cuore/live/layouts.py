"""Dashboard layouts for the live-data UI: schema, validation, storage.

A layout is a named set of pages, each holding widgets bound to channel ids
from :mod:`cuore.live.channels`. Built-in layouts are generated on every call
from the current channel registry (so they never reference a channel that
does not exist); user layouts are plain JSON files under
``<state>/live_layouts/``.

Nothing here talks to the adapter -- this module only reads the channel
registry (for names/units/presets) and the filesystem (for user layouts).
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Optional

from ..services.errors import BadRequest, NotFound
from . import channels as channels_mod
from .config import state_dir

_LOCK = threading.Lock()

_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")

#: Widget type -> (min_channels, max_channels or None for unlimited).
WIDGET_TYPES: dict[str, tuple[int, Optional[int]]] = {
    "digital": (1, 1),
    "bar": (1, 1),
    "dial": (1, 1),
    "line": (1, 1),
    "scope": (1, 1),
    "hud": (1, 1),
    "multiline": (1, 4),
    "stacked": (1, 6),
    "scatter": (2, 2),
    "table": (1, None),
    "tiles": (1, None),
}

_ORIENTATIONS = {"horizontal", "vertical"}


def layouts_dir() -> Path:
    d = state_dir() / "live_layouts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _path_for(layout_id: str) -> Path:
    return layouts_dir() / f"{layout_id}.json"


# ===========================================================================
# validation
# ===========================================================================

def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise BadRequest(msg)


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.strip().lower()).strip("_-")
    return s or "layout"


def validate_size(size: Any) -> list[int]:
    _require(isinstance(size, (list, tuple)) and len(size) == 2,
             f"size must be [w, h], got {size!r}")
    w, h = size
    _require(isinstance(w, int) and not isinstance(w, bool) and 1 <= w <= 4,
             f"widget size width must be an integer 1-4, got {w!r}")
    _require(isinstance(h, int) and not isinstance(h, bool) and 1 <= h <= 3,
             f"widget size height must be an integer 1-3, got {h!r}")
    return [w, h]


def _validate_band(name: str, band: Any) -> Optional[list[float]]:
    if band is None:
        return None
    _require(isinstance(band, (list, tuple)) and len(band) == 2,
             f"{name} must be [lo, hi] or null, got {band!r}")
    lo, hi = band
    _require(isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and not
             isinstance(lo, bool) and not isinstance(hi, bool),
             f"{name} bounds must be numbers, got {band!r}")
    _require(lo <= hi, f"{name} lo must be <= hi, got {band!r}")
    return [float(lo), float(hi)]


def validate_widget(widget: dict[str, Any]) -> dict[str, Any]:
    """Validate one widget dict, returning a normalised copy.

    Raises :class:`BadRequest` with a clear message on anything wrong: unknown
    type, malformed size, wrong channel count for the widget type, malformed
    bands.
    """
    _require(isinstance(widget, dict), "widget must be an object")
    wid = widget.get("id")
    _require(isinstance(wid, str) and wid.strip(), "widget.id is required")
    wtype = widget.get("type")
    _require(wtype in WIDGET_TYPES,
             f"unknown widget type {wtype!r}; one of {sorted(WIDGET_TYPES)}")

    channels_in = widget.get("channels") or []
    _require(isinstance(channels_in, list) and all(isinstance(c, str) for c in channels_in),
             "widget.channels must be a list of channel id strings")
    channels_list = list(channels_in)

    x_ch = widget.get("xChannel")
    y_ch = widget.get("yChannel")
    if wtype == "scatter":
        _require(bool(x_ch) and bool(y_ch),
                 "scatter widgets require xChannel and yChannel")
        if channels_list:
            _require(set(channels_list) == {x_ch, y_ch} and len(channels_list) == 2,
                     "scatter widget.channels must be exactly [xChannel, yChannel]")
        else:
            channels_list = [x_ch, y_ch]
    else:
        _require(x_ch is None and y_ch is None,
                 f"xChannel/yChannel only apply to scatter widgets, not {wtype!r}")

    lo, hi = WIDGET_TYPES[wtype]
    n = len(channels_list)
    _require(n >= lo, f"{wtype} widget needs at least {lo} channel(s), got {n}")
    if hi is not None:
        _require(n <= hi, f"{wtype} widget allows at most {hi} channel(s), got {n}")
    if wtype == "scatter":
        _require(len(set(channels_list)) == 2, "scatter widget needs two distinct channels")

    size = validate_size(widget.get("size", [1, 1]))

    warn = _validate_band("warn", widget.get("warn"))
    alarm = _validate_band("alarm", widget.get("alarm"))

    decimals = widget.get("decimals")
    if decimals is not None:
        _require(isinstance(decimals, int) and not isinstance(decimals, bool) and 0 <= decimals <= 6,
                 f"decimals must be an integer 0-6, got {decimals!r}")

    smoothing = widget.get("smoothing")
    if smoothing is not None:
        _require(isinstance(smoothing, (int, float)) and not isinstance(smoothing, bool)
                 and 0.0 <= float(smoothing) <= 1.0,
                 f"smoothing must be 0..1, got {smoothing!r}")

    window_sec = widget.get("windowSec")
    if window_sec is not None:
        _require(isinstance(window_sec, (int, float)) and not isinstance(window_sec, bool)
                 and window_sec > 0,
                 f"windowSec must be a positive number, got {window_sec!r}")

    orientation = widget.get("orientation")
    if orientation is not None:
        _require(orientation in _ORIENTATIONS,
                 f"orientation must be one of {sorted(_ORIENTATIONS)}, got {orientation!r}")

    mirror = widget.get("mirror")
    if mirror is not None:
        _require(isinstance(mirror, bool), "mirror must be a boolean")

    rates = widget.get("rates")
    if rates is not None:
        _require(isinstance(rates, dict), "rates must be an object of {channel: hz}")
        for k, v in rates.items():
            _require(isinstance(k, str), "rates keys must be channel id strings")
            _require(isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0,
                     f"rates[{k!r}] must be a positive number, got {v!r}")

    for lim, val in (("min", widget.get("min")), ("max", widget.get("max"))):
        if val is not None:
            _require(isinstance(val, (int, float)) and not isinstance(val, bool),
                     f"{lim} must be a number or null, got {val!r}")

    out: dict[str, Any] = {
        "id": wid, "type": wtype, "title": widget.get("title", ""),
        "channels": channels_list, "size": size,
        "min": widget.get("min"), "max": widget.get("max"),
        "warn": warn, "alarm": alarm,
        "decimals": decimals, "smoothing": smoothing, "windowSec": window_sec,
    }
    if orientation is not None:
        out["orientation"] = orientation
    if wtype == "scatter":
        out["xChannel"], out["yChannel"] = x_ch, y_ch
    if mirror is not None:
        out["mirror"] = mirror
    if rates is not None:
        out["rates"] = rates
    if widget.get("note"):
        out["note"] = str(widget["note"])
    return out


def validate_layout(layout: dict[str, Any], *, layout_id: Optional[str] = None) -> dict[str, Any]:
    """Validate a whole layout dict, returning a normalised copy.

    ``layout_id`` overrides ``layout["id"]`` when the caller (a PUT to a named
    route) is the source of truth for the id.
    """
    _require(isinstance(layout, dict), "layout must be an object")
    lid = layout_id if layout_id is not None else layout.get("id")
    _require(isinstance(lid, str) and _ID_RE.match(lid or ""),
             f"layout id must match {_ID_RE.pattern!r}, got {lid!r}")
    name = layout.get("name")
    _require(isinstance(name, str) and name.strip(), "layout.name is required")
    version = layout.get("version", 1)
    _require(version == 1, f"layout.version must be 1, got {version!r}")

    pages_in = layout.get("pages")
    _require(isinstance(pages_in, list) and len(pages_in) > 0,
             "layout.pages must be a non-empty list")
    pages_out = []
    seen_page_ids: set[str] = set()
    for i, page in enumerate(pages_in):
        _require(isinstance(page, dict), f"pages[{i}] must be an object")
        pid = page.get("id")
        _require(isinstance(pid, str) and pid.strip(), f"pages[{i}].id is required")
        _require(pid not in seen_page_ids, f"duplicate page id {pid!r}")
        seen_page_ids.add(pid)
        widgets_in = page.get("widgets") or []
        _require(isinstance(widgets_in, list), f"pages[{i}].widgets must be a list")
        widgets_out = []
        seen_widget_ids: set[str] = set()
        for w in widgets_in:
            vw = validate_widget(w)
            _require(vw["id"] not in seen_widget_ids,
                     f"duplicate widget id {vw['id']!r} on page {pid!r}")
            seen_widget_ids.add(vw["id"])
            widgets_out.append(vw)
        pages_out.append({"id": pid, "title": page.get("title", pid),
                          "widgets": widgets_out})

    return {"id": lid, "name": name, "version": 1, "builtin": False,
           "pages": pages_out}


# ===========================================================================
# built-in layouts, generated from the channel registry
# ===========================================================================

def _chan_widget(cid: str, wtype: str, *, size=(1, 1), min=None, max=None,
                 note: str = "", title: str = "") -> Optional[dict[str, Any]]:
    reg = channels_mod.registry()
    ch = reg.get(cid)
    if ch is None:
        return None
    w: dict[str, Any] = {"id": f"w_{cid}", "type": wtype,
                         "title": title or ch.name, "channels": [cid],
                         "size": list(size), "min": min, "max": max,
                         "warn": None, "alarm": None, "decimals": None,
                         "smoothing": None, "windowSec": None}
    if note:
        w["note"] = note
    return w


def _multi_widget(wid: str, wtype: str, cids: list[str], *, size, title: str,
                  window_sec: Optional[float] = None) -> Optional[dict[str, Any]]:
    reg = channels_mod.registry()
    present = [c for c in cids if c in reg]
    if not present:
        return None
    lo, hi = WIDGET_TYPES[wtype]
    if hi is not None:
        present = present[:hi]
    return {"id": wid, "type": wtype, "title": title, "channels": present,
           "size": list(size), "min": None, "max": None, "warn": None,
           "alarm": None, "decimals": None, "smoothing": None,
           "windowSec": window_sec}


def _page(pid: str, title: str, widgets: list[Optional[dict[str, Any]]]) -> dict[str, Any]:
    return {"id": pid, "title": title, "widgets": [w for w in widgets if w is not None]}


def _layout(lid: str, name: str, pages: list[dict[str, Any]]) -> dict[str, Any]:
    return {"id": lid, "name": name, "version": 1, "builtin": True, "pages": pages}


def _stelvio_engine() -> dict[str, Any]:
    widgets = [
        _chan_widget("engine_rpm", "digital", size=(1, 1)),
        _chan_widget("vehicle_speed", "digital", size=(1, 1)),
        _chan_widget("engine_coolant_temp", "dial", size=(2, 2), min=0, max=130,
                    note="generic gasoline-engine coolant range guideline, not a "
                         "Stelvio-specific spec"),
        _chan_widget("intake_air_temp", "digital", size=(1, 1)),
        _chan_widget("absolute_load", "bar", size=(1, 2), min=0, max=100),
        _chan_widget("throttle_position", "bar", size=(1, 2), min=0, max=100),
        _chan_widget("battery_voltage", "digital", size=(1, 1), min=11.5, max=15,
                    note="generic 12V lead-acid operating range guideline"),
    ]
    return _layout("stelvio_engine", "Engine basics", [_page("engine", "Engine", widgets)])


def _stelvio_boost() -> dict[str, Any]:
    widgets = [
        _chan_widget("intake_map", "dial", size=(2, 2)),
        _chan_widget("barometric_pressure", "digital", size=(1, 1)),
        _chan_widget("boost", "dial", size=(2, 2),
                    note="computed as MAP - baro; compare against the unverified "
                         "ECM boost DID below"),
        _chan_widget("ecm_195a", "digital", size=(1, 1),
                    note="unverified DID; cross-check against the computed boost value"),
    ]
    return _layout("stelvio_boost", "Boost / turbo", [_page("boost", "Boost", widgets)])


def _stelvio_evap() -> dict[str, Any]:
    top = [
        _chan_widget("commanded_evap_purge", "bar", size=(1, 2), min=0, max=100),
        _chan_widget("fuel_level", "bar", size=(1, 2), min=0, max=100),
        _chan_widget("evap_vapor_pressure", "digital", size=(1, 1)),
        _chan_widget("evap_vapor_pressure_abs", "digital", size=(1, 1)),
        _chan_widget("engine_coolant_temp", "digital", size=(1, 1)),
        _chan_widget("intake_air_temp", "digital", size=(1, 1)),
    ]
    trace = _multi_widget(
        "w_evap_stacked", "stacked",
        ["commanded_evap_purge", "evap_vapor_pressure", "evap_vapor_pressure_abs",
         "fuel_level"],
        size=(4, 2), title="EVAP Test A trace (purge / vapor pressure / fuel level)")
    return _layout("stelvio_evap", "EVAP job", [_page("evap", "EVAP", top + [trace])])


def _stelvio_transmission() -> dict[str, Any]:
    widgets = [
        _chan_widget("tcm_04fe", "digital", size=(1, 1)),
        _chan_widget("tcm_0518", "digital", size=(1, 1)),
        _multi_widget("w_trans_line", "multiline", ["tcm_04fe", "tcm_0518"],
                     size=(2, 2), title="Transmission channels"),
    ]
    return _layout("stelvio_transmission", "Transmission",
                   [_page("transmission", "Transmission", widgets)])


def _stelvio_tpms() -> dict[str, Any]:
    cids = ["rfhub_40b1_pressure", "rfhub_40b1_temp", "rfhub_40b2_pressure",
           "rfhub_40b2_temp", "rfhub_40b3_pressure", "rfhub_40b3_temp",
           "rfhub_40b4_pressure", "rfhub_40b4_temp"]
    tiles = _multi_widget("w_tpms_tiles", "tiles", cids, size=(4, 2), title="Tire pressure/temp")
    return _layout("stelvio_tpms", "TPMS", [_page("tpms", "TPMS", [tiles])])


def _mes_parameters() -> dict[str, Any]:
    cids = list(channels_mod.PRESETS.get("engine_basics", ()))
    reg = channels_mod.registry()
    present = [c for c in cids if c in reg]
    table = _multi_widget("w_mes_table", "table", present, size=(4, 3),
                          title="Parameters")
    graph_cids = present[:4]
    graph = _multi_widget("w_mes_graph", "multiline", graph_cids, size=(4, 2),
                          title="Graph")
    return _layout("mes_parameters", "MES Parameters + Graph",
                   [_page("parameters", "Parameters", [table, graph])])


_BUILTIN_FACTORIES = (_stelvio_engine, _stelvio_boost, _stelvio_evap,
                      _stelvio_transmission, _stelvio_tpms, _mes_parameters)


def builtin_layouts() -> dict[str, dict[str, Any]]:
    """Every built-in layout, generated fresh from the current channel registry.

    A layout whose every widget referenced a now-missing channel would end up
    with empty pages; that is left as-is rather than hidden, since the caller
    (a dashboard) can render "no widgets" more usefully than a 404 for a
    built-in id it expects to always exist.
    """
    out: dict[str, dict[str, Any]] = {}
    for factory in _BUILTIN_FACTORIES:
        layout = factory()
        out[layout["id"]] = layout
    return out


def is_builtin(layout_id: str) -> bool:
    return layout_id in builtin_layouts()


# ===========================================================================
# user layout storage
# ===========================================================================

def _load_user(layout_id: str) -> Optional[dict[str, Any]]:
    p = _path_for(layout_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _save_user(layout: dict[str, Any]) -> None:
    p = _path_for(layout["id"])
    p.write_text(json.dumps(layout, indent=2), encoding="utf-8")


def list_layouts() -> list[dict[str, Any]]:
    out = []
    for lid, layout in sorted(builtin_layouts().items()):
        out.append({"id": lid, "name": layout["name"], "builtin": True,
                    "pages": len(layout["pages"])})
    with _LOCK:
        for p in sorted(layouts_dir().glob("*.json")):
            data = _load_user(p.stem)
            if data is None:
                continue
            out.append({"id": data.get("id", p.stem), "name": data.get("name", p.stem),
                        "builtin": False, "pages": len(data.get("pages", []))})
    return out


def get_layout(layout_id: str) -> dict[str, Any]:
    builtins = builtin_layouts()
    if layout_id in builtins:
        return builtins[layout_id]
    with _LOCK:
        data = _load_user(layout_id)
    if data is None:
        raise NotFound(f"no layout named {layout_id!r}")
    return data


def put_layout(layout_id: str, body: dict[str, Any]) -> dict[str, Any]:
    _require(isinstance(layout_id, str) and _ID_RE.match(layout_id),
             f"layout id must match {_ID_RE.pattern!r}, got {layout_id!r}")
    if is_builtin(layout_id):
        raise BadRequest(f"{layout_id!r} is a built-in layout and is read-only")
    validated = validate_layout(body, layout_id=layout_id)
    with _LOCK:
        _save_user(validated)
    return validated


def delete_layout(layout_id: str) -> dict[str, Any]:
    if is_builtin(layout_id):
        raise BadRequest(f"{layout_id!r} is a built-in layout and cannot be deleted")
    with _LOCK:
        p = _path_for(layout_id)
        if not p.exists():
            raise NotFound(f"no layout named {layout_id!r}")
        p.unlink()
    return {"deleted": layout_id}


def _free_id(preferred: str) -> str:
    builtins = builtin_layouts()
    with _LOCK:
        existing = {p.stem for p in layouts_dir().glob("*.json")}
    if preferred not in builtins and preferred not in existing:
        return preferred
    i = 2
    while True:
        cand = f"{preferred}-{i}"
        if cand not in builtins and cand not in existing:
            return cand
        i += 1


def import_layout(body: dict[str, Any]) -> dict[str, Any]:
    """Import a layout, assigning a free id if the given one is taken."""
    _require(isinstance(body, dict), "layout must be an object")
    raw_id = body.get("id") or _slugify(body.get("name", "layout"))
    _require(isinstance(raw_id, str) and raw_id.strip(), "layout id or name is required")
    slug = _slugify(raw_id) if not _ID_RE.match(raw_id) else raw_id
    free_id = _free_id(slug)
    validated = validate_layout(body, layout_id=free_id)
    with _LOCK:
        _save_user(validated)
    return validated


def export_layout(layout_id: str) -> dict[str, Any]:
    return get_layout(layout_id)


__all__ = ["WIDGET_TYPES", "validate_widget", "validate_layout", "builtin_layouts",
          "is_builtin", "list_layouts", "get_layout", "put_layout", "delete_layout",
          "import_layout", "export_layout", "layouts_dir"]
