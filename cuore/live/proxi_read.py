"""Read-only PROXI (vehicle configuration) read from the Body computer (BCM), saved per car.

UDS service 0x22 only, through ``ops.module_discover_dids`` (the same guarded, interlocked,
audited session path service_dids uses: refuses while MES holds the adapter, CAN-C 500k only).
No 0x27, 0x2E, 0x31, 0x10, 0x11, 0x14 and no raw send exists here.

* :func:`discover` sweeps the BCM and ranks candidate "configuration blocks".
* :func:`accept_candidate` is the only way a candidate becomes "the PROXI block" (owner's reason).
* :func:`read` reads the accepted identifier once and diffs it against the previous read.
* :func:`add_names` records names the technician read off MES's CAN Setup screen (naming only:
  nothing in this module sends names.json anywhere).
Files: ``<state>/proxi/<vin>/<timestamp>.json``, ``accepted.json`` and ``names.json``.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from . import audit
from .addressing import by_code
from .config import state_dir

MODULE = "BCM"
LIKELY_LEN = 64
#: service_dids' ranges plus the 0x2000-0x2FFF and 0xF100-0xF1FF blocks.
RANGES: list[tuple[int, int, str]] = [
    (0x0100, 0x01FF, "data block (as service_dids)"),
    (0x2000, 0x2FFF, "counter / configuration-style block"),
    (0xF100, 0xF1FF, "identification block"),
]
SECONDS_PER_REQUEST = 0.25
MAX_REQUESTS = sum(b - a + 1 for a, b, _ in RANGES)
NEVER = ["0x27", "0x2E", "0x2F", "0x31", "0x3D", "0x10", "0x11", "0x14", "0x34", "0x35", "0x36", "0x37"]
#: precedence when two entries cover the same byte and bits: lower wins.
KIND_RANK = {"manufacturer": 0, "mes_display": 1, "forum": 2}
KIND_LABEL = {"manufacturer": "manufacturer", "mes_display": "MES display", "forum": "forum (single source)"}


class ProxiRefused(Exception):
    pass


def _dir(vin: str) -> Path:
    d = state_dir() / "proxi" / vin
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%S%f")[:-3]


def _check_module(vin: str):
    """The BCM address must be confirmed on CAN-C, else refuse with a clear message."""
    ecu = by_code(MODULE)
    if ecu is None or ecu.bus_key != "can_c":
        raise ProxiRefused("The Body computer is not known on CAN-C; nothing was sent.")
    try:
        from . import uds as uds_mod
        return uds_mod.resolve_module(MODULE, vin or None)
    except Exception as exc:  # noqa: BLE001
        raise ProxiRefused(f"The Body computer (BCM) has no confirmed CAN-C address on this car; "
                           f"nothing was sent. Run module discovery first. ({exc})") from exc


def _bytes(h: dict[str, Any]) -> list[int]:
    out: list[int] = []
    for b in h.get("bytes") or []:
        try:
            out.append(int(str(b), 16) & 0xFF)
        except (TypeError, ValueError):
            return []
    return out


def _row(did: str, data: list[int]) -> dict[str, Any]:
    return {"did": did.upper(), "length": len(data), "first16": " ".join(f"{b:02X}" for b in data[:16]),
            "bytes": [f"{b:02X}" for b in data], "likely_configuration": len(data) >= LIKELY_LEN}


def rank(replies: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [_row(str(r.get("did", "")), _bytes(r)) for r in replies]
    rows = [r for r in rows if r["length"]]
    rows.sort(key=lambda r: (-r["length"], r["did"]))
    return rows


def _save(vin: str, doc: dict[str, Any]) -> Path:
    p = _dir(vin) / f"{doc['stamp']}.json"
    p.write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return p


def discover(vin: str, max_seconds: float = 1500) -> dict[str, Any]:
    """Sweep the BCM (0x22 only), record every positive reply, rank candidates. Never promotes."""
    from . import ops
    ecu = _check_module(vin)
    stamp = _stamp()
    started = datetime.now().isoformat(timespec="seconds")
    t0 = time.monotonic()
    replies: list[dict[str, Any]] = []
    errors: list[str] = []
    requests, aborted = 0, None
    audit.record("proxi_discover_start", vin=vin, max_requests=MAX_REQUESTS)
    for a, b, _why in RANGES:
        if time.monotonic() - t0 >= max_seconds:
            aborted = f"time budget of {max_seconds:g}s used up"
            break
        try:
            res = ops.module_discover_dids(MODULE, vin=vin, ranges=[f"{a:04X}-{b:04X}"],
                                           max_dids=b - a + 1)
        except Exception as exc:  # noqa: BLE001 -- LiveError/Refused: show, do not retry
            aborted = f"{type(exc).__name__}: {exc}"
            errors.append(aborted)
            break
        requests += int(res.get("tried") or 0)
        if res.get("stopped_early"):
            errors.append(f"{a:04X}-{b:04X}: stopped early ({res['stopped_early']})")
            aborted = f"stopped early ({res['stopped_early']})"
        for h in res.get("positive") or []:
            replies.append({"did": h["did"], "bytes": h.get("bytes") or [], "ascii": h.get("ascii")})
        if aborted:
            break
    ranked = rank(replies)
    doc = {"kind": "discover", "stamp": stamp, "vin": vin, "module": MODULE,
           "target": f"{ecu.target:02X}" if ecu.target is not None else None,
           "session": {"bus": "can_c", "bitrate": 500000, "service": "0x22", "diagnostic_session": "default"},
           "started": started, "finished": datetime.now().isoformat(timespec="seconds"),
           "requests": requests, "aborted_reason": aborted, "errors": errors,
           "responses": [_row(str(r["did"]), _bytes(r)) for r in replies if _bytes(r)],
           "candidates": ranked, "accepted": False,
           "status": "candidates only -- nothing is the PROXI block until the owner accepts one"}
    _save(vin, doc)
    audit.record("proxi_discover_end", vin=vin, requests=requests, replies=len(replies), aborted=aborted)
    return {"stamp": stamp, "requests": requests, "aborted_reason": aborted, "errors": errors,
            "candidates": ranked, "replies": len(replies)}


def accepted(vin: str) -> Optional[dict[str, Any]]:
    try:
        return json.loads((state_dir() / "proxi" / vin / "accepted.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def accept_candidate(vin: str, did: str, reason: str) -> dict[str, Any]:
    did = str(did).strip().upper().removeprefix("0X").zfill(4)
    reason = (reason or "").strip()
    if not reason:
        raise ProxiRefused("A reason is required, for example \"matches MES CAN Setup screenshot of <date>\".")
    cand = next((c for c in (latest_discovery(vin) or {}).get("candidates", []) if c["did"] == did), None)
    if cand is None:
        raise ProxiRefused(f"{did} is not a candidate from the latest discovery.")
    doc = {"vin": vin, "did": did, "length": cand["length"], "reason": reason,
           "accepted_at": datetime.now().isoformat(timespec="seconds")}
    (_dir(vin) / "accepted.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    audit.record("proxi_accept", vin=vin, did=did)
    return doc


def _files(vin: str, kind: str) -> list[Path]:
    d = state_dir() / "proxi" / vin
    out = []
    for p in sorted(d.glob("2*.json")) if d.is_dir() else []:
        try:
            if json.loads(p.read_text(encoding="utf-8")).get("kind") == kind:
                out.append(p)
        except (OSError, ValueError):
            continue
    return out


def _load(p: Path) -> dict[str, Any]:
    return json.loads(p.read_text(encoding="utf-8"))


def latest_discovery(vin: str) -> Optional[dict[str, Any]]:
    f = _files(vin, "discover")
    return _load(f[-1]) if f else None


def reads(vin: str) -> list[dict[str, Any]]:
    return [_load(p) for p in _files(vin, "read")]


def diff_blocks(old: list[str], new: list[str]) -> list[dict[str, Any]]:
    out = []
    for i in range(max(len(old), len(new))):
        a = old[i] if i < len(old) else None
        b = new[i] if i < len(new) else None
        if a != b:
            out.append({"index": i, "before": a, "after": b})
    return out


def read(vin: str) -> dict[str, Any]:
    """One 0x22 read of the accepted identifier, saved, with a diff against the previous read."""
    from . import ops
    acc = accepted(vin)
    if not acc:
        raise ProxiRefused("No identifier has been accepted yet; run discovery and accept a candidate first.")
    _check_module(vin)
    did = acc["did"]
    audit.record("proxi_read_start", vin=vin, did=did)
    res = ops.module_discover_dids(MODULE, vin=vin, ranges=[f"{did}-{did}"], max_dids=1)
    hit = next((h for h in res.get("positive") or [] if str(h.get("did", "")).upper() == did), None)
    if hit is None or not _bytes(hit):
        raise ProxiRefused(f"The Body computer gave no positive answer for {did}"
                           + (f" ({res['stopped_early']})" if res.get("stopped_early") else "") + ".")
    data = [f"{b:02X}" for b in _bytes(hit)]
    prev = reads(vin)
    doc = {"kind": "read", "stamp": _stamp(), "vin": vin, "module": MODULE, "did": did, "length": len(data),
           "bytes": data, "read_at": datetime.now().isoformat(timespec="seconds"),
           "session": {"bus": "can_c", "bitrate": 500000, "service": "0x22"},
           "previous": prev[-1]["stamp"] if prev else None,
           "changed": diff_blocks(prev[-1]["bytes"], data) if prev else None}
    _save(vin, doc)
    audit.record("proxi_read_end", vin=vin, did=did, length=len(data))
    return doc


# --- names from MES's CAN Setup screen (naming only; never sent anywhere) -----------------

def names(vin: str) -> list[dict[str, Any]]:
    try:
        return json.loads((state_dir() / "proxi" / vin / "names.json").read_text(encoding="utf-8")).get("rows", [])
    except (OSError, ValueError):
        return []


def _parse_mask(s: str) -> tuple[int, bool]:
    s = (s or "").strip().lower()
    if s in ("", "whole", "whole byte", "all", "ff", "0xff"):
        return 0xFF, True
    if re.fullmatch(r"[01x]{8}", s):
        return int("".join("1" if c != "x" else "0" for c in s), 2), False
    return int(s, 16) & 0xFF, False


def _agreement(raw: int, mask: int, shown: str, same_day: bool) -> str:
    if not same_day:
        return "no same-day read"
    s = (shown or "").strip().lower().replace(" ", "")
    if re.fullmatch(r"[01x]{8}", s):
        ok = all(c == "x" or int(c) == (raw >> (7 - i)) & 1 for i, c in enumerate(s))
        return "agrees" if ok else "disagrees"
    try:
        v = int(s, 16) if s.startswith("0x") or re.fullmatch(r"[0-9a-f]{1,2}", s) else None
    except ValueError:
        v = None
    if v is None:
        return "not comparable"
    return "agrees" if v in (raw & mask, raw) else "disagrees"


def add_names(vin: str, rows: list[dict[str, Any]], screenshot: str, mes_date: str) -> dict[str, Any]:
    """rows: byte, mask ("whole byte" or hex/xxxx1011), name, value. Validated against the accepted
    read; stored in names.json as source_kind "mes_display". Read-only naming."""
    screenshot, mes_date = (screenshot or "").strip(), (mes_date or "").strip()
    if not screenshot:
        raise ProxiRefused("A screenshot path or media id is required.")
    try:
        datetime.strptime(mes_date, "%Y-%m-%d")
    except ValueError:
        raise ProxiRefused("The MES session date must be YYYY-MM-DD.") from None
    rd = reads(vin)
    if not rd:
        raise ProxiRefused("No accepted PROXI read exists yet; read the block first.")
    last = rd[-1]
    same_day = any(r["read_at"][:10] == mes_date for r in rd)
    ref = next((r for r in reversed(rd) if r["read_at"][:10] == mes_date), last)
    out = []
    for r in rows:
        try:
            idx = int(str(r.get("byte")).strip())
            mask, whole = _parse_mask(str(r.get("mask", "")))
        except (ValueError, TypeError):
            raise ProxiRefused(f"Row not understood: {r}") from None
        name = str(r.get("name", "")).strip()
        if not name:
            raise ProxiRefused(f"Row for byte {idx} has no option name.")
        if not 0 <= idx < len(last["bytes"]):
            raise ProxiRefused(f"Byte {idx} does not exist in the accepted read ({len(last['bytes'])} bytes).")
        raw = int(ref["bytes"][idx], 16) if idx < len(ref["bytes"]) else int(last["bytes"][idx], 16)
        shown = str(r.get("value", "")).strip()
        out.append({"byte": idx, "mask": f"0x{mask:02X}", "whole_byte": whole, "name": name,
                    "mes_value": shown, "agreement": _agreement(raw, mask, shown, same_day),
                    "source_kind": "mes_display",
                    "source": f"MES CAN Setup screenshot {screenshot}, session {mes_date}",
                    "recorded_at": datetime.now().isoformat(timespec="seconds")})
    doc = {"vin": vin, "rows": names(vin) + out}
    (_dir(vin) / "names.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
    audit.record("proxi_names_added", vin=vin, rows=len(out))
    return {"added": out}


def parse_bulk(text: str) -> list[dict[str, Any]]:
    """One row per line: byte;mask;name;value"""
    rows = []
    for line in (text or "").splitlines():
        if not line.strip():
            continue
        p = [x.strip() for x in line.split(";")]
        if len(p) < 4:
            raise ProxiRefused(f"Line needs byte;mask;name;value: {line!r}")
        rows.append({"byte": p[0], "mask": p[1], "name": p[2], "value": ";".join(p[3:])})
    return rows


# --- page view (no car contact) ----------------------------------------------------------

def _map() -> dict[str, Any]:
    p = Path(__file__).resolve().parents[1] / "data" / "proxi_map_949.json"
    return json.loads(p.read_text(encoding="utf-8"))


def known_options(block: list[str], vin: str = "") -> list[dict[str, Any]]:
    """Decode the block from the sourced map and the per-car MES-display names. One row per
    byte/bits; precedence manufacturer > mes_display > forum; the others are listed as 'also'."""
    entries: list[dict[str, Any]] = []
    for o in _map()["options"]:
        entries.append({"name": o["name"], "byte": o["byte"], "mask": int(o["mask"], 16), "values": o["values"],
                        "source_kind": o.get("source_kind", "forum"), "source": o.get("source", ""),
                        "mes_value": None, "agreement": None})
    for n in names(vin) if vin else []:
        entries.append({"name": n["name"], "byte": n["byte"], "mask": int(n["mask"], 16), "values": {},
                        "source_kind": n["source_kind"], "source": n["source"],
                        "mes_value": n.get("mes_value"), "agreement": n.get("agreement")})
    groups: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for e in entries:
        groups.setdefault((e["byte"], e["mask"]), []).append(e)
    out = []
    for (idx, mask), g in sorted(groups.items()):
        g.sort(key=lambda e: KIND_RANK.get(e["source_kind"], 9))
        w = g[0]
        row = {**w, "mask_hex": f"0x{mask:02X}", "kind_label": KIND_LABEL.get(w["source_kind"], w["source_kind"]),
               "also": [f"{e['name']} ({KIND_LABEL.get(e['source_kind'], e['source_kind'])})" for e in g[1:]]}
        if idx >= len(block):
            row.update(present=False, raw=None, label="block too short for this byte")
        else:
            raw = int(block[idx], 16)
            masked = raw & mask
            label = w["values"].get(f"0x{masked:02X}")
            if label is None:
                label = ("MES shows: " + str(w["mes_value"])) if w["mes_value"] else "value not in the sourced list"
            row.update(present=True, raw=f"{raw:02X}", masked=f"{masked:02X}", label=label)
        out.append(row)
    return out


def view(vin: str) -> dict[str, Any]:
    disc, acc, rd = latest_discovery(vin), accepted(vin), reads(vin)
    state = "accepted" if acc and rd else ("candidates" if disc and disc.get("candidates") else "none")
    last = rd[-1] if rd else None
    v: dict[str, Any] = {"state": state, "discovery": disc, "accepted": acc, "last": last,
                         "candidates": (disc or {}).get("candidates", []), "names": names(vin)}
    if last:
        v["grid"] = [{"i": i, "hex": b, "bin": f"{int(b, 16):08b}"} for i, b in enumerate(last["bytes"])]
        v["options"] = known_options(last["bytes"], vin)
    return v
