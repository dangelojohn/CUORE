"""The TSB layer: every bulletin / recall / CSN / campaign / extended
coverage known for the car, as a per-VIN checklist.

* :func:`catalogue` -- the shipped list (``cuore/data/tsb_catalogue.json``).
* :func:`checklist` -- catalogue rows joined with this VIN's status/note,
  plus a cross-link into the dossier's Bulletins section when the same
  bulletin number appears in the dossier's ``tsb_matches``.
* :func:`set_status` -- record one row's status/note.

Status is stored the same way ``cuore.live.checklists`` stores shop-visible
checklist state: one small JSON file in the shared state dir, under its own
namespace (``tsb_checklist.json``: ``vin -> item_id -> {status, note,
updated_at}``), lock-guarded read-modify-write. Shared across terminals,
not per-browser.
"""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from ..data import load_tsb_catalogue
from ..live.config import state_dir
from .errors import BadRequest, NotFound

NAMESPACE = "tsb_checklist"
STATUSES = ("open", "done", "not_applicable", "to_verify")
STATUS_LABELS = {"open": "open", "done": "done", "not_applicable": "n/a",
                 "to_verify": "to verify"}
DEFAULT_STATUS = "open"

_LOCK = threading.Lock()


def path() -> Path:
    return state_dir() / f"{NAMESPACE}.json"


def _load() -> dict[str, Any]:
    try:
        return json.loads(path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict[str, Any]) -> None:
    p = path()
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(p)


def catalogue() -> dict[str, Any]:
    return load_tsb_catalogue()


# --- dossier cross-links ------------------------------------------------------


def _norm(num: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (num or "").upper())


def _base(num: str) -> str:
    """Number without its revision suffix: '18-030-17 REV. B' -> '1803017'."""
    return _norm(re.split(r"\s*(?:REV\.?|Rev)\b", num or "", maxsplit=1)[0])


def _slug(text: str) -> str:  # same rule as dossier_bridge._slug -> same anchors
    return re.sub(r"[^A-Za-z0-9]+", "-", (text or "").strip()).strip("-")


def dossier_bulletin_numbers(dossier: Optional[dict[str, Any]]) -> list[str]:
    """Every bulletin number the dossier's ``tsb_matches.per_code`` carries."""
    per_code = ((dossier or {}).get("tsb_matches") or {}).get("per_code") or {}
    out: list[str] = []
    for matches in per_code.values():
        for b in matches or []:
            num = (b or {}).get("bulletin")
            if num and num not in out:
                out.append(num)
    return out


def _cross_link(vin: str, number: str, dossier_nums: list[str]) -> Optional[dict[str, str]]:
    exact = [n for n in dossier_nums if _norm(n) == _norm(number)]
    loose = [n for n in dossier_nums if _base(n) == _base(number)]
    hit = (exact or loose or [None])[0]
    if not hit:
        return None
    anchor = f"tsb-{_slug(hit)}"
    return {"number": hit, "anchor": anchor, "href": f"/v/{vin}/dossier#{anchor}"}


# --- checklist ---------------------------------------------------------------


def row_anchor(item_id: str) -> str:
    return f"tsb-row-{_slug(item_id)}"


def _check_vin(vin: str) -> str:
    vin = (vin or "").strip().upper()
    if not vin:
        raise BadRequest("a VIN is required")
    return vin


def checklist(vin: str, dossier: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Catalogue rows joined with this VIN's status/note. ``dossier`` (the
    workup dict) is optional; when given, rows whose number is in its
    ``tsb_matches`` get a ``dossier_link``."""
    vin = _check_vin(vin)
    cat = catalogue()
    with _LOCK:
        saved = dict(_load().get(vin, {}))
    nums = dossier_bulletin_numbers(dossier)
    rows: list[dict[str, Any]] = []
    for item in cat["items"]:
        st = saved.get(item["id"]) or {}
        row = dict(item)
        row["status"] = st.get("status") if st.get("status") in STATUSES else DEFAULT_STATUS
        row["note"] = st.get("note") or ""
        row["status_updated_at"] = st.get("updated_at")
        row["anchor"] = row_anchor(item["id"])
        row["dossier_link"] = _cross_link(vin, item["number"], nums)
        rows.append(row)
    counts = Counter(r["status"] for r in rows)
    return {
        "vin": vin, "vehicle": cat["vehicle"], "updated": cat["updated"],
        "items": rows, "total": len(rows),
        "counts": {s: counts.get(s, 0) for s in STATUSES},
        "kinds": sorted({r["kind"] for r in rows}),
        "systems": sorted({s for r in rows for s in r["systems"]}),
    }


def set_status(vin: str, item_id: str, status: str, note: Optional[str] = None) -> dict[str, Any]:
    """Record one row's status (open | done | not_applicable | to_verify) and
    note. ``note=None`` keeps the stored note. Returns the stored entry."""
    vin = _check_vin(vin)
    status = (status or "").strip().lower().replace(" ", "_").replace("n/a", "not_applicable")
    if status not in STATUSES:
        raise BadRequest(f"status must be one of {', '.join(STATUSES)}")
    if item_id not in {i["id"] for i in catalogue()["items"]}:
        raise NotFound(f"no catalogue item {item_id!r}")
    with _LOCK:
        data = _load()
        per_vin = data.setdefault(vin, {})
        prev = per_vin.get(item_id) or {}
        entry = {
            "status": status,
            "note": (note if note is not None else prev.get("note")) or "",
            "updated_at": datetime.now().isoformat(timespec="seconds"),
        }
        per_vin[item_id] = entry
        _save(data)
    return {"vin": vin, "item_id": item_id, **entry}


__all__ = ["NAMESPACE", "STATUSES", "STATUS_LABELS", "catalogue", "checklist",
           "set_status", "dossier_bulletin_numbers", "path", "row_anchor"]
