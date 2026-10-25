"""Advanced-mechanic extras for the code page's electrical-path panel.

Four features, all evidence-only (every value comes from CUORE's own saved
data or is labelled as a general check; missing data is "not recorded"):

* network view (U-codes): buses/modules from ``fullscan_last.json`` plus the
  Giorgio address/bus tables (``cuore.live.addressing`` / ``cuore.live.buses``,
  source docs/reference/GIORGIO_MODULE_MAP.md), coloured by the last scan.
* wiggle-test recorder: marks appended to ``wiggle_tests.jsonl`` and
  correlated with what the live session already logged.
* pin-level data: append-only ``pin_data.jsonl`` keyed by model.
* "when it sets": every freeze frame for the code on this car.

Nothing here opens the adapter. The only live-layer contact is reading the
in-process poller's *status* and the observation log it already wrote.
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

GIORGIO_DOC = "docs/reference/GIORGIO_MODULE_MAP.md"
_LOCK = threading.Lock()

MAX_NOTE = 300
MAX_FIELD = 80
MAX_SOURCE = 200
MAX_BY = 40
WIGGLE_BEFORE_S = 5
WIGGLE_AFTER_S = 20


def _state_dir() -> Path:
    from ..live.config import state_dir
    return state_dir()


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _append(name: str, entry: dict[str, Any]) -> None:
    p = _state_dir() / name
    with _LOCK:
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _read_lines(name: str) -> list[dict[str, Any]]:
    p = _state_dir() / name
    out: list[dict[str, Any]] = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    except OSError:
        pass
    return out


def model_key(vin: str) -> str:
    """Model key shared by same-model cars. Only the VIN prefix this
    project has verified (ZASFAKPN..J = Stelvio 2018 2.0T) maps to a model;
    any other VIN stays private to itself rather than guessing."""
    v = (vin or "").upper()
    if v.startswith("ZASFAKPN") and len(v) >= 10 and v[9] == "J":
        return "stelvio-2018-2.0"
    return f"vin:{v}"


# ===========================================================================
# 4. Network view
# ===========================================================================

_TOKEN_RE = re.compile(r"[A-Z][A-Z0-9/]{1,9}")
_BUS_ORDER = ("can_c", "can_ihs", "can_ch")


def decode_lost_modules(description: str) -> list[str]:
    """Module abbreviations a DTC *description* names (e.g. "Engine control
    (NCM) - Signal/message erratic" -> ECM, via the MES alias table). Only
    text actually present in the description is used; nothing is inferred
    from the code number. Empty list when nothing decodes."""
    try:
        from mes import modules as mes_modules
    except Exception:  # noqa: BLE001
        return []
    found: list[str] = []
    for tok in _TOKEN_RE.findall(description or ""):
        code = mes_modules.normalize_abbrev(tok)
        if code and code not in found:
            found.append(code)
    return found


def _code_description(vin: str, code: str) -> tuple[str, str]:
    """(text, source) from the car's own logs first, then the shipped table."""
    base = (code or "").upper().split("-")[0]
    try:
        from . import mes_bridge
        hist = mes_bridge.dtc_history(base, vin=vin)
        for m in hist.get("matches") or []:
            for d in m.get("descriptions") or []:
                if d:
                    return str(d), f"this car's MES logs ({m.get('dtc')})"
    except Exception:  # noqa: BLE001
        pass
    try:
        from mes import dtc_descriptions
        r = dtc_descriptions.code_description(base)
        text = r.get("description") or r.get("text") or ""
        if text and str(r.get("confidence", "")).lower() != "unknown":
            return str(text), "mes.dtc_descriptions"
    except Exception:  # noqa: BLE001
        pass
    return "", ""


def load_fullscan() -> Optional[dict[str, Any]]:
    p = _state_dir() / "fullscan_last.json"
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        data["_mtime"] = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
    except OSError:
        data["_mtime"] = None
    return data


def _scan_time(scan: dict[str, Any]) -> Optional[str]:
    m = re.search(r"(\d{10})$", str(scan.get("scan_id") or ""))
    if m:
        try:
            return datetime.strptime(m.group(1), "%y%m%d%H%M").strftime("%Y-%m-%d %H:%M")
        except ValueError:
            pass
    return scan.get("_mtime")


def load_discovery(vin: str) -> dict[str, dict[str, Any]]:
    """Persisted module discovery for this car: ``{module: {target, source, at}}``
    from ``addresses.json`` in the CUORE state dir (written by CUORE module
    discovery). Empty when absent or unreadable."""
    try:
        data = json.loads((_state_dir() / "addresses.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    rows = data.get(vin) if isinstance(data, dict) else None
    out: dict[str, dict[str, Any]] = {}
    for mod, r in (rows or {}).items():
        if isinstance(r, dict) and r.get("target"):
            out[str(mod).upper()] = r
    return out


def _norm_addr(v: Any) -> Optional[str]:
    if isinstance(v, int):
        return f"0x{v:02X}"
    try:
        return f"0x{int(str(v).replace('0x', '').replace('0X', ''), 16):02X}"
    except ValueError:
        return None


def build_network(vin: str, code: str, *, scan: Optional[dict[str, Any]] = None,
                  description: Optional[tuple[str, str]] = None,
                  discovery: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, Any]:
    """Buses -> modules coloured by the last full scan.

    status: ``answered`` | ``silent`` (asked, no answer) | ``unchecked`` (the
    scan could not ask: wrong cable, no known address, ...). ``lost`` marks
    modules the code's own description names; only when it decodes.
    """
    from ..live import addressing, buses as live_buses
    scan = scan if scan is not None else load_fullscan()
    text, text_src = description if description is not None else _code_description(vin, code)
    lost = decode_lost_modules(text) if text else []
    disc = discovery if discovery is not None else load_discovery(vin)
    scan_at = _scan_time(scan or {})

    rows = list((scan or {}).get("coverage") or [])
    by_bus: dict[str, list[dict[str, Any]]] = {k: [] for k in _BUS_ORDER}
    for r in rows:
        bus = r.get("bus")
        if bus not in by_bus:
            continue
        cat = r.get("category")
        status = cat if cat in ("answered", "silent") else "unchecked"
        addr = None
        try:
            a = addressing.by_code(str(r.get("module")))
            addr = a.target if a else None
        except Exception:  # noqa: BLE001
            addr = None
        mod = str(r.get("module"))
        scan_addr = f"0x{addr:02X}" if isinstance(addr, int) else None
        d = disc.get(mod.upper())
        d_addr = _norm_addr(d.get("target")) if d else None
        d_at = str(d.get("at") or "")[:16] if d else ""
        d_day = d_at[:10]
        scan_day = (scan_at or "")[:10]
        ev_scan = status in ("answered", "silent")
        # newest evidence wins; "unchecked" is not evidence, discovery answers are
        use_disc = bool(d_addr) and (not ev_scan or (d_at.replace("T", " ") >= (scan_at or "")))
        if use_disc:
            status, label = "answered", f"answered (discovery {d_day})"
        elif ev_scan:
            label = f"{status} (scan {scan_day})"
        else:
            label = "not checked" + (f" in scan {scan_day}" if scan_day else "")
        shown = d_addr if d_addr else scan_addr
        differs = scan_addr if (d_addr and scan_addr and scan_addr != d_addr) else None
        tip = [f"{mod}: {label}"]
        if d_addr:
            tip.append(f"discovery {d_day}: {d_addr} ({d.get('source')})")
        tip.append(f"scan {scan_day or '?'}: {r.get('category') or 'n/a'}"
                   + (f", registry address {scan_addr}" if scan_addr else ", no registry address")
                   + (f" ({r.get('why')})" if r.get("why") else ""))
        by_bus[bus].append({
            "code": mod, "status": status, "why": r.get("why"), "address": shown,
            "label": label, "address_differs_from_scan": differs,
            "address_source": ("discovery " + d_day) if d_addr else ("scan registry" if scan_addr else None),
            "evidence": tip, "collides_with": [],
            "lost": mod in lost,
        })
    # collisions: same shown address on different modules, reported as the data says
    owners: dict[str, list[dict[str, Any]]] = {}
    for bm in by_bus.values():
        for m in bm:
            if m["address"]:
                owners.setdefault(m["address"], []).append(m)
    for addr_, ms in owners.items():
        if len(ms) > 1:
            for m in ms:
                m["collides_with"] = [o["code"] for o in ms if o is not m]
                m["evidence"].append(f"address {addr_} is also reported for {', '.join(m['collides_with'])}"
                                     " (collision shown as recorded, not resolved)")
    buses = []
    for key in _BUS_ORDER:
        b = live_buses.BUSES.get(key)
        buses.append({"key": key, "name": b.name if b else key,
                      "bitrate": b.bitrate if b else None, "modules": by_bus[key]})
    on_map = {m["code"] for b in buses for m in b["modules"]}
    return {
        "code": (code or "").upper(), "description": text, "description_source": text_src,
        "lost": lost, "lost_decoded": bool(lost),
        "lost_off_map": [m for m in lost if m not in on_map],
        "buses": buses, "has_scan": bool(rows),
        "scan": {"id": (scan or {}).get("scan_id"), "at": _scan_time(scan or {}),
                 "vin": (scan or {}).get("vin"), "vin_match": (scan or {}).get("vin") in (None, vin),
                 "cable": (scan or {}).get("cable")},
        "gateway": "BCM",
        "gateway_source": f"{GIORGIO_DOC} (BCM 949 is the gateway; diagnostically reachable on CAN-C, gateways IHS)",
        "bus_source": GIORGIO_DOC,
    }


def _esc(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


def network_svg(net: dict[str, Any]) -> str:
    """Server-rendered SVG; colour comes from CSS classes (path_diag.css)."""
    node_w, node_h, gap, left = 66, 44, 8, 12
    row_h = 118
    buses = [b for b in net["buses"] if b["modules"]]
    width = left * 2 + max([len(b["modules"]) for b in buses] + [1]) * (node_w + gap)
    height = 30 + row_h * max(len(buses), 1)
    parts = [f'<svg class="pd-net" viewBox="0 0 {width} {height}" role="img" '
             f'aria-label="CAN bus and module map">']
    bcm_x: dict[str, float] = {}
    for i, b in enumerate(buses):
        y_line = 30 + i * row_h + 14
        parts.append(f'<text class="pd-bus-label" x="{left}" y="{y_line - 6}">'
                     f'{_esc(b["name"])}</text>')
        parts.append(f'<line class="pd-bus-line" x1="{left}" y1="{y_line}" '
                     f'x2="{width - left}" y2="{y_line}"/>')
        for j, m in enumerate(b["modules"]):
            x = left + j * (node_w + gap)
            y = y_line + 14
            cls = f'pd-node pd-{m["status"]}' + (" pd-lost" if m["lost"] else "")
            tip = "\n".join(m.get("evidence") or [m["code"]])
            parts.append(f'<line class="pd-stub" x1="{x + node_w / 2}" y1="{y_line}" '
                         f'x2="{x + node_w / 2}" y2="{y}"/>')
            parts.append(f'<g class="{cls}"><title>{_esc(tip)}</title>'
                         f'<rect x="{x}" y="{y}" width="{node_w}" height="{node_h}" rx="4"/>'
                         f'<text class="pd-node-name" x="{x + node_w / 2}" y="{y + 18}" '
                         f'text-anchor="middle">{_esc(m["code"])}</text>'
                         f'<text class="pd-node-sub" x="{x + node_w / 2}" y="{y + 34}" '
                         f'text-anchor="middle">{_esc(m["address"] or "no addr")}</text></g>')
            note = []
            if m.get("address_differs_from_scan"):
                note.append(f'differs from scan: {m["address_differs_from_scan"]}')
            if m.get("collides_with"):
                note.append("same addr as " + "/".join(m["collides_with"]))
            if note:
                parts.append(f'<text class="pd-node-note" x="{x + node_w / 2}" y="{y + node_h + 26}" '
                             f'text-anchor="middle" font-size="8">{_esc("; ".join(note))}</text>')
            if m["lost"]:
                parts.append(f'<text class="pd-lost-mark" x="{x + node_w / 2}" y="{y + node_h + 14}" '
                             f'text-anchor="middle">named by code</text>')
            if m["code"] == net["gateway"]:
                bcm_x[b["key"]] = x + node_w / 2
        # gateway link between the bus rows holding BCM
    if "can_c" in bcm_x:
        ihs_i = next((i for i, b in enumerate(buses) if b["key"] == "can_ihs"), None)
        c_i = next((i for i, b in enumerate(buses) if b["key"] == "can_c"), None)
        if ihs_i is not None and c_i is not None:
            x = bcm_x["can_c"] + node_w / 2 + 3
            parts.append(f'<path class="pd-gw" d="M{x} {30 + c_i * row_h + 28 + node_h / 2} '
                         f'H{width - 4} V{30 + ihs_i * row_h + 14}"><title>BCM gateways CAN-IHS '
                         f'({_esc(GIORGIO_DOC)})</title></path>')
    parts.append("</svg>")
    return "".join(parts)


CAN_CHECKLIST = {
    "label": "Standard CAN checks, general, not a Stelvio spec",
    "items": [
        "Ignition off. Measure resistance between DLC pins 6 and 14: about 60 ohm is normal "
        "(two 120 ohm terminators in parallel).",
        "About 120 ohm = one terminator (or one branch) is open. Very low (near 0) = CAN-H/CAN-L "
        "short together or to something.",
        "Bus active (ignition on): CAN-H to ground about 2.5 to 3.5 V, CAN-L to ground about "
        "1.5 to 2.5 V.",
        "Note: on 2018+ Giorgio cars CAN-C sits behind the Security Gateway; the DLC may show "
        "limited traffic. Record readings as inspections.",
    ],
}


# ===========================================================================
# 5. Wiggle-test recorder
# ===========================================================================

WIGGLE_FILE = "wiggle_tests.jsonl"
_CODE_RE = re.compile(r"^[A-Z0-9]{3,8}(-[0-9A-F]{2})?$")


def live_session_active() -> bool:
    """True when a CUORE live session (the in-process poller) is running.
    Reads in-memory state only; never touches the adapter."""
    try:
        from ..live import poller as live_poller
        return bool(live_poller.poller().is_active())
    except Exception:  # noqa: BLE001
        return False


def add_wiggle(vin: str, code: str, action: str, hop: str = "", note: str = "",
               *, valid_hops: Optional[set[str]] = None, by: str = "",
               at: Optional[str] = None, live_active: Optional[bool] = None) -> Optional[str]:
    """Append one mark. Returns an error string, or None on success."""
    code = (code or "").strip().upper()
    hop = (hop or "").strip()
    note = (note or "").strip()
    if action not in ("mark", "stop"):
        return "action must be mark or stop"
    if not _CODE_RE.match(code):
        return "bad code"
    if action == "mark":
        if not hop:
            return "no hop given"
        if valid_hops is not None and hop not in valid_hops:
            return "unknown hop"
    else:
        hop = ""
    if len(note) > MAX_NOTE:
        return f"note too long (max {MAX_NOTE})"
    _append(WIGGLE_FILE, {
        "id": uuid.uuid4().hex[:10], "vin": vin, "code": code, "action": action,
        "hop": hop, "note": note, "by": (by or "")[:MAX_BY], "at": at or _now(),
        "live_active": live_session_active() if live_active is None else bool(live_active),
    })
    return None


def wiggle_marks(vin: str, code: str) -> list[dict[str, Any]]:
    code = (code or "").upper()
    rows = [r for r in _read_lines(WIGGLE_FILE) if r.get("vin") == vin and r.get("code") == code]
    rows.sort(key=lambda r: r.get("at") or "")
    return rows


def _parse(ts: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(ts))
    except ValueError:
        return None


def live_events(vin: str, t0: datetime, t1: datetime,
                *, observations: Optional[list[dict[str, Any]]] = None,
                dtc_first_seen: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    """What the live session itself logged between t0 and t1: alarm events
    (``live_alarm`` observations, e.g. voltage channel alarms) and DTCs it
    first saw in that window. Module dropouts and a voltage trace are not
    recorded by the live layer, so they never appear here."""
    events: list[dict[str, Any]] = []
    if observations is None:
        try:
            from ..live import store
            observations = store.recent_observations(2000, kind="live_alarm")
            observations = [o for o in observations if store.is_from_car(o)]
        except Exception:  # noqa: BLE001
            observations = []
    for o in observations:
        if o.get("vin") not in ("", None, vin):
            continue
        t = _parse(o.get("at"))
        if t and t0 <= t <= t1:
            d = o.get("data") or {}
            events.append({"at": o["at"], "kind": "alarm",
                           "text": f"{d.get('channel')} {d.get('level')} ({d.get('value')})"})
    if dtc_first_seen is None:
        try:
            from ..live import poller as live_poller
            dtc_first_seen = live_poller.poller().dtc_snapshot().get("first_seen") or {}
        except Exception:  # noqa: BLE001
            dtc_first_seen = {}
    for c, ts in dtc_first_seen.items():
        t = _parse(ts)
        if t and t0 <= t <= t1:
            events.append({"at": ts, "kind": "dtc", "text": f"live session first saw {c}"})
    events.sort(key=lambda e: e["at"])
    return events


def wiggle_timeline(vin: str, code: str, *, marks: Optional[list[dict[str, Any]]] = None,
                    observations: Optional[list[dict[str, Any]]] = None,
                    dtc_first_seen: Optional[dict[str, str]] = None) -> list[dict[str, Any]]:
    """Each mark with the live events inside [-5 s, +20 s] of it. Marks made
    without a live session carry ``correlated=False`` ("no live data")."""
    marks = marks if marks is not None else wiggle_marks(vin, code)
    out = []
    for m in marks:
        t = _parse(m.get("at"))
        row = dict(m)
        row["events"] = []
        row["correlated"] = bool(m.get("live_active")) and t is not None
        if row["correlated"]:
            row["events"] = live_events(
                vin, t - timedelta(seconds=WIGGLE_BEFORE_S), t + timedelta(seconds=WIGGLE_AFTER_S),
                observations=observations, dtc_first_seen=dtc_first_seen)
        out.append(row)
    return out


# ===========================================================================
# 6. Pin-level data
# ===========================================================================

PIN_FILE = "pin_data.jsonl"
PIN_FIELDS = ("connector", "pin", "wire_colour", "circuit")


def _clean_fields(src: dict[str, Any]) -> tuple[dict[str, str], Optional[str]]:
    out = {}
    for k in PIN_FIELDS:
        v = str(src.get(k, "") or "").strip()
        if len(v) > MAX_FIELD:
            return {}, f"{k} too long (max {MAX_FIELD})"
        out[k] = v
    if not any(out.values()):
        return {}, "enter at least one of connector, pin, wire colour, circuit"
    return out, None


def add_pin(vin: str, element: str, fields: dict[str, Any], source: str, by: str,
            *, valid_elements: Optional[set[str]] = None, amends: str = "",
            at: Optional[str] = None) -> Optional[str]:
    """Append a pin row (or an amend line replacing an earlier row's fields).
    A source is required; nothing is ever pre-filled."""
    element = (element or "").strip()
    source = (source or "").strip()
    by = (by or "").strip() or "mechanic"
    if not element:
        return "no element given"
    if valid_elements is not None and element not in valid_elements:
        return "unknown element"
    if not source:
        return "source is required (e.g. TechAuthority wiring diagram page/figure, or 'observed on car')"
    if len(source) > MAX_SOURCE:
        return f"source too long (max {MAX_SOURCE})"
    if len(by) > MAX_BY:
        return f"name too long (max {MAX_BY})"
    clean, err = _clean_fields(fields)
    if err:
        return err
    entry = {"id": uuid.uuid4().hex[:10], "vin": vin, "model": model_key(vin),
             "element": element, **clean, "source": source, "by": by, "at": at or _now()}
    if amends:
        target = next((r for r in _read_lines(PIN_FILE) if r.get("id") == amends
                       and r.get("model") == entry["model"] and r.get("element") == element), None)
        if target is None:
            return "row to amend not found"
        entry["amends"] = amends
    _append(PIN_FILE, entry)
    return None


def pins_for(vin: str, element: str) -> list[dict[str, Any]]:
    """Effective rows for this element on this car's model (amends applied,
    latest wins). ``other_car`` is True when the row came from a different VIN."""
    model = model_key(vin)
    rows = [r for r in _read_lines(PIN_FILE) if r.get("model") == model and r.get("element") == element]
    rows.sort(key=lambda r: r.get("at") or "")
    base: dict[str, dict[str, Any]] = {}
    for r in rows:
        root = r.get("amends") or r.get("id")
        cur = dict(r)
        if root in base:
            cur["origin_vin"] = base[root].get("origin_vin", base[root].get("vin"))
            cur["amended"] = True
        else:
            cur["origin_vin"] = r.get("vin")
        cur["row_id"] = root
        base[root] = cur
    out = list(base.values())
    for r in out:
        r["other_car"] = r.get("origin_vin") != vin
    return out


# ===========================================================================
# 7. When it sets
# ===========================================================================

_NUM_RE = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(.*)$")


def _num(display: Any) -> tuple[Optional[float], str]:
    m = _NUM_RE.match(str(display or ""))
    if not m:
        return None, ""
    try:
        return float(m.group(1).replace(",", ".")), m.group(2).strip()
    except ValueError:
        return None, ""


#: label regex (matched against the freeze-frame's own parameter names) ->
#: (summary label, unit shown when the data carries none)
_FF_FIELDS = [
    ("voltage", re.compile(r"volt", re.I)),
    ("engine_temp", re.compile(r"^engine temperature$|coolant", re.I)),
    ("air_temp", re.compile(r"^air temperature$|ambient", re.I)),
    ("rpm", re.compile(r"^engine speed$|rpm", re.I)),
    ("speed", re.compile(r"^vehicle speed$", re.I)),
    ("startups", re.compile(r"startups counter|ignition cycle", re.I)),
    ("odometer", re.compile(r"odometer", re.I)),
]
_FF_TITLES = {"voltage": "Battery / module voltage", "engine_temp": "Engine temperature",
              "air_temp": "Air temperature", "rpm": "Engine speed", "speed": "Vehicle speed",
              "startups": "Startups counter", "odometer": "Odometer"}


def freeze_frames_for(vin: str, code: str) -> list[dict[str, Any]]:
    from . import mes_bridge
    from .errors import NotFound
    try:
        return mes_bridge.freeze_frames(code=(code or "").split("-")[0], vin=vin).get("frames") or []
    except NotFound:
        return []


def _pick(frame: dict[str, Any], rx: "re.Pattern[str]") -> tuple[Optional[float], str, str]:
    for label, disp in (frame.get("freeze_frame") or {}).items():
        if rx.search(label):
            v, unit = _num(disp)
            if v is not None:
                return v, unit, label
    return None, "", ""


def freeze_summary(vin: str, code: str, *,
                   frames: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    frames = frames if frames is not None else freeze_frames_for(vin, code)
    frames = sorted(frames, key=lambda f: f.get("timestamp") or "")
    n = len(frames)
    series: dict[str, list[float]] = {}
    units: dict[str, str] = {}
    labels: dict[str, str] = {}
    rows = []
    for f in frames:
        row = {"timestamp": f.get("timestamp"), "dtc": f.get("dtc"), "status": f.get("status"),
               "file": f.get("file")}
        for key, rx in _FF_FIELDS:
            v, unit, label = _pick(f, rx)
            row[key] = v
            if v is not None:
                series.setdefault(key, []).append(v)
                units[key] = unit or units.get(key, "")
                labels[key] = label
        rows.append(row)
    summaries = []
    for key, _ in _FF_FIELDS:
        vals = series.get(key)
        if not vals:
            summaries.append({"key": key, "title": _FF_TITLES[key], "text": "not recorded"})
            continue
        u = units.get(key, "")
        lo, hi = min(vals), max(vals)
        rng = f"{lo:g} {u}".strip() if lo == hi else f"{lo:g} to {hi:g} {u}".strip()
        summaries.append({"key": key, "title": _FF_TITLES[key], "label": labels.get(key),
                          "text": f"{rng} ({len(vals)} of {n} frames)", "unit": u})
    patterns = _patterns(series, units, n) if n >= 2 else []
    return {"count": n, "enough": n >= 2, "rows": rows, "summaries": summaries,
            "patterns": patterns, "units": units,
            "note": "" if n >= 2 else (
                "No freeze frame recorded for this code on this car." if n == 0
                else "Only 1 freeze frame recorded; patterns need at least 2.")}


def _patterns(series: dict[str, list[float]], units: dict[str, str], n: int) -> list[str]:
    """A pattern line only when every frame supports it (and every frame
    carried the value; missing values never count as support)."""
    out: list[str] = []

    def full(key: str) -> Optional[list[float]]:
        vals = series.get(key)
        return vals if vals and len(vals) == n else None

    v = full("voltage")
    if v:
        if all(x < 12.0 for x in v):
            out.append(f"all {n} occurrences below 12.0 V")
        elif all(x >= 13.0 for x in v):
            out.append(f"all {n} occurrences at or above 13.0 V")
    t = full("engine_temp")
    if t and all(x < 40 for x in t):
        out.append(f"all {n} with engine temperature < 40 {units.get('engine_temp') or 'C'}")
    elif t and all(x >= 80 for x in t):
        out.append(f"all {n} with engine temperature >= 80 {units.get('engine_temp') or 'C'}")
    r = full("rpm")
    if r and all(x == 0 for x in r):
        out.append(f"all {n} at 0 rpm")
    elif r and all(x > 0 for x in r):
        out.append(f"all {n} with engine running (rpm above 0)")
    s = full("speed")
    if s and all(x == 0 for x in s):
        out.append(f"all {n} at 0 {units.get('speed') or 'km/h'} (stationary)")
    elif s and all(x > 0 for x in s):
        out.append(f"all {n} while moving (speed above 0)")
    return out


# ===========================================================================
# Bundle for the code-page partial
# ===========================================================================

def more_for(vin: str, code: str, hops: list[dict[str, Any]]) -> dict[str, Any]:
    """Everything ``_electrical_path_more.html`` needs. Never raises."""
    code_u = (code or "").upper()

    def safe(fn: Callable[[], Any], default: Any) -> Any:
        try:
            return fn()
        except Exception:  # noqa: BLE001 -- an extra panel must never sink the code page
            return default

    is_u = code_u.startswith("U")
    net = safe(lambda: build_network(vin, code_u), None) if is_u else None
    return {
        "is_u": is_u, "net": net,
        "net_svg": safe(lambda: network_svg(net), "") if net else "",
        "checklist": CAN_CHECKLIST,
        "live_active": live_session_active(),
        "wiggle": safe(lambda: wiggle_timeline(vin, code_u), []),
        "hops": [{"id": h.get("id"), "label": h.get("label"), "role": h.get("role"),
                  "pins": safe(lambda h=h: pins_for(vin, h.get("id", "")), [])} for h in hops],
        "model": model_key(vin),
        "freeze": safe(lambda: freeze_summary(vin, code_u),
                       {"count": 0, "enough": False, "rows": [], "summaries": [], "patterns": [],
                        "units": {}, "note": "freeze-frame data not available"}),
    }
