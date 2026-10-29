"""Parity board: every function a dealership technician uses in MultiEcuScan or AlfaOBD, with CUORE's
state and what closes the gap (``/v/{vin}/parity``).

Data: ``cuore/data/parity_items.json`` (compiled 2026-10-29 from the gap studies; one row per function).
Owner state changes are an overlay in ``CUORE_STATE_DIR/parity_overrides.json`` (``{item_id: {"state": ...,
"note": ..., "at": ...}}``) so the shipped file stays the reference and a row can be moved to "done" with the
proof that moved it. Read-only here; nothing contacts the car.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

DATA_FILE = Path(__file__).resolve().parents[1] / "data" / "parity_items.json"

STATE_ORDER = ["car_session", "build", "documents", "decision", "done"]
STATE_MARK = {"done": "\u2713", "car_session": "\u25cb", "build": "+", "documents": "\u25a1", "decision": "?"}
STATE_WHY = {
    "car_session": "Closable at the next car connection with the session kits already on the Bench; no documents needed.",
    "build": "Needs only a CUORE build: no documents and no car. The next things to build.",
    "documents": "Waits for the manufacturer's documents (docs/project/MES_PARITY_PLAN.md, section 1).",
    "decision": "Waits for an owner decision.",
    "done": "Working in CUORE today, with the proof named on the row.",
}
HAS_MARK = {"yes": ("\u2713", "yes"), "partial": ("\u25d0", "partial"), "no": ("\u2717", "no"), "unknown": ("?", "unknown")}


def _state_dir() -> Path:
    try:
        from ..config import settings  # type: ignore
        d = getattr(settings, "state_dir", None)
        if d:
            return Path(d)
    except Exception:  # noqa: BLE001
        pass
    import os
    return Path(os.environ.get("CUORE_STATE_DIR", r"C:\ProgramData\cuore"))


def load() -> dict[str, Any]:
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"_about": "parity_items.json missing or invalid", "states": {}, "groups": {}, "items": []}
    ov_file = _state_dir() / "parity_overrides.json"
    overrides: dict[str, Any] = {}
    try:
        if ov_file.is_file():
            overrides = json.loads(ov_file.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        overrides = {}
    for it in data.get("items", []):
        ov = overrides.get(it.get("id"))
        if isinstance(ov, dict):
            it["override"] = ov
            if ov.get("state") in STATE_WHY:
                it["state"] = ov["state"]
    return data


def board(state: Optional[str] = None, group: Optional[str] = None) -> dict[str, Any]:
    """Grouped view for the page: counts, filters and the rows per state (car session first)."""
    data = load()
    items = list(data.get("items", []))
    states = data.get("states") or {k: k for k in STATE_ORDER}
    groups = data.get("groups") or {}
    counts_state = {k: sum(1 for i in items if i.get("state") == k) for k in STATE_ORDER}
    counts_group = {k: sum(1 for i in items if i.get("group") == k) for k in groups}
    sel = [i for i in items if (not state or i.get("state") == state) and (not group or i.get("group") == group)]
    for i in sel:
        for tool in ("mes", "alfaobd", "cuore"):
            has = (i.get(tool) or {}).get("has", "unknown")
            i[f"{tool}_mark"], i[f"{tool}_word"] = HAS_MARK.get(has, HAS_MARK["unknown"])
        i["state_mark"] = STATE_MARK.get(i.get("state"), "?")
        i["state_label"] = states.get(i.get("state"), i.get("state"))
        i["group_label"] = groups.get(i.get("group"), i.get("group"))
    sections = []
    for k in STATE_ORDER:
        rows = [i for i in sel if i.get("state") == k]
        if rows or not state:
            rows.sort(key=lambda i: (list(groups).index(i.get("group")) if i.get("group") in groups else 99, i.get("function", "")))
            sections.append({"key": k, "label": states.get(k, k), "mark": STATE_MARK[k], "why": STATE_WHY[k],
                             "rows": rows, "n": len(rows), "open": k != "done"})
    return {"about": data.get("_about", ""), "states": states, "groups": groups, "state": state or "", "group": group or "",
            "counts_state": counts_state, "counts_group": counts_group, "total": len(items), "shown": len(sel),
            "sections": sections, "state_order": STATE_ORDER, "state_mark": STATE_MARK}


def to_csv() -> str:
    import csv
    import io
    data = load()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "group", "function", "mes", "mes_note", "alfaobd", "alfaobd_note", "cuore", "cuore_note", "state", "closes", "refs"])
    for i in data.get("items", []):
        w.writerow([i.get("id"), i.get("group"), i.get("function"),
                    (i.get("mes") or {}).get("has"), (i.get("mes") or {}).get("note"),
                    (i.get("alfaobd") or {}).get("has"), (i.get("alfaobd") or {}).get("note"),
                    (i.get("cuore") or {}).get("has"), (i.get("cuore") or {}).get("note"),
                    i.get("state"), i.get("closes"), "; ".join(i.get("refs") or [])])
    return out.getvalue()
