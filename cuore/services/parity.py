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


STATUS_ORDER = ["PROVEN", "BUILT NOT PROVEN", "MISSING BUILDABLE", "NEEDS CAR", "NEEDS MANUFACTURER SOURCE"]
STATUS_SLUG = {"PROVEN": "proven", "BUILT NOT PROVEN": "built", "MISSING BUILDABLE": "buildable",
               "NEEDS CAR": "car", "NEEDS MANUFACTURER SOURCE": "source"}
SLUG_STATUS = {v: k for k, v in STATUS_SLUG.items()}
STATUS_MARK = {"PROVEN": "✓", "BUILT NOT PROVEN": "◐", "MISSING BUILDABLE": "+", "NEEDS CAR": "○",
               "NEEDS MANUFACTURER SOURCE": "□"}
STATUS_LABEL = {"PROVEN": "Proven", "BUILT NOT PROVEN": "Built, not proven", "MISSING BUILDABLE": "Missing, can be built now",
                "NEEDS CAR": "Needs a car session", "NEEDS MANUFACTURER SOURCE": "Needs a manufacturer source"}
STATUS_WHY = {
    "PROVEN": "A recorded CUORE reading on this car equals what MES shows.",
    "BUILT NOT PROVEN": "CUORE has built it or read it, but no side-by-side comparison with MES is on file.",
    "MISSING BUILDABLE": "Not in CUORE. Needs no car and no document, only a build.",
    "NEEDS CAR": "Closes with a car session; reads only.",
    "NEEDS MANUFACTURER SOURCE": "Waits for a manufacturer document, or is a write that needs one.",
}


def _is_mes_item(i: dict[str, Any]) -> bool:
    return i.get("group") != "cuore_only" and i.get("applies_to_reference_car", True) is not False


def board(state: Optional[str] = None, group: Optional[str] = None, status: Optional[str] = None,
          module: Optional[str] = None) -> dict[str, Any]:
    """Grouped view for the page. ``status`` takes a status name or its slug; counts are over every row, and the
    per-status counts follow the group and module filter so a person can narrow down and still see every item."""
    data = load()
    items = list(data.get("items", []))
    states = data.get("states") or {k: k for k in STATE_ORDER}
    groups = data.get("groups") or {}
    status = SLUG_STATUS.get(status or "", status or "") or ""
    if status and status not in STATUS_ORDER:
        status = ""
    for i in items:
        i.setdefault("status", "BUILT NOT PROVEN")
        i.setdefault("module", "All modules")
    counts_state = {k: sum(1 for i in items if i.get("state") == k) for k in STATE_ORDER}
    counts_group = {k: sum(1 for i in items if i.get("group") == k) for k in groups}
    modules = sorted({i["module"] for i in items}, key=lambda m: (m in ("All modules", "CUORE only"), m))
    counts_module = {m: sum(1 for i in items if i["module"] == m) for m in modules}
    counts_status_all = {k: sum(1 for i in items if i["status"] == k) for k in STATUS_ORDER}

    def keep(i: dict[str, Any], st: bool = True) -> bool:
        return ((not state or i.get("state") == state) and (not group or i.get("group") == group)
                and (not module or i["module"] == module) and (not st or not status or i["status"] == status))

    counts_status = {k: sum(1 for i in items if keep(i, False) and i["status"] == k) for k in STATUS_ORDER}
    sel = [i for i in items if keep(i)]
    for i in sel:
        for tool in ("mes", "alfaobd", "cuore"):
            has = (i.get(tool) or {}).get("has", "unknown")
            i[f"{tool}_mark"], i[f"{tool}_word"] = HAS_MARK.get(has, HAS_MARK["unknown"])
        i["state_mark"] = STATE_MARK.get(i.get("state"), "?")
        i["state_label"] = states.get(i.get("state"), i.get("state"))
        i["group_label"] = groups.get(i.get("group"), i.get("group"))
        i["status_mark"] = STATUS_MARK[i["status"]]
        i["status_label"] = STATUS_LABEL[i["status"]]
    sections = []
    for k in STATUS_ORDER:
        rows = [i for i in sel if i["status"] == k]
        if rows or not status:
            rows.sort(key=lambda i: (list(groups).index(i.get("group")) if i.get("group") in groups else 99, i["module"], i.get("function", "")))
            sections.append({"key": k, "label": STATUS_LABEL[k], "mark": STATUS_MARK[k], "why": STATUS_WHY[k],
                             "rows": rows, "n": len(rows), "open": bool(status or module or group) and bool(rows)})
    mes_items = [i for i in items if _is_mes_item(i)]
    proven = sum(1 for i in mes_items if i["status"] == "PROVEN")
    by_module = [{"module": m, "n": counts_module[m],
                  "by": {k: sum(1 for i in items if i["module"] == m and i["status"] == k) for k in STATUS_ORDER}}
                 for m in modules]
    by_group = [{"group": g, "label": groups[g], "n": counts_group[g],
                 "by": {k: sum(1 for i in items if i.get("group") == g and i["status"] == k) for k in STATUS_ORDER}}
                for g in groups]
    return {"about": data.get("_about", ""), "states": states, "groups": groups, "state": state or "", "group": group or "",
            "status": status, "module": module or "", "modules": modules, "counts_module": counts_module,
            "counts_state": counts_state, "counts_group": counts_group, "counts_status": counts_status,
            "counts_status_all": counts_status_all, "total": len(items), "shown": len(sel),
            "mes_total": len(mes_items), "mes_proven": proven, "by_module": by_module, "by_group": by_group,
            "sections": sections, "status_order": STATUS_ORDER, "status_slug": STATUS_SLUG, "status_mark": STATUS_MARK,
            "status_label": STATUS_LABEL, "state_order": STATE_ORDER, "state_mark": STATE_MARK}


def to_csv() -> str:
    import csv
    import io
    data = load()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "group", "function", "mes", "mes_note", "alfaobd", "alfaobd_note", "cuore", "cuore_note", "state", "closes", "refs", "status", "module", "seen_in"])
    for i in data.get("items", []):
        w.writerow([i.get("id"), i.get("group"), i.get("function"),
                    (i.get("mes") or {}).get("has"), (i.get("mes") or {}).get("note"),
                    (i.get("alfaobd") or {}).get("has"), (i.get("alfaobd") or {}).get("note"),
                    (i.get("cuore") or {}).get("has"), (i.get("cuore") or {}).get("note"),
                    i.get("state"), i.get("closes"), "; ".join(i.get("refs") or []),
                    i.get("status"), i.get("module"), i.get("seen_in")])
    return out.getvalue()
