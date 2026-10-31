"""Invented showcase cars (Maserati Grecale, Ferrari Purosangue) for a dealer demo.

Everything a demo car shows comes from ONE file per car, ``data/demo_cars/<VIN>.json``, plus store
records tagged ``demo: true`` that ``tools/demo_cars.py`` writes and removes. Nothing here comes from
a car, a manufacturer document or a manual; every value is plainly illustrative and every page that
shows it carries the banner below (``base.html`` / ``m_base.html`` / the print sheets).

Rule 11 (docs/project/RULES.md): demo content is never evidence and never feeds learning. The VIN
test lives in ``mes.demo`` so ``mes`` stores (cases, tool usage) can skip these cars too. This module
only ever READS the JSON; it never touches the adapter, the consent gate or a live session.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- puts `mes` on sys.path
from mes import demo as _demo

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "demo_cars"
BANNER = "DEMO DATA: invented for a demonstration. Not from a car."
CHIP = "DEMO"


def _norm(vin: Any) -> str:
    return str(vin or "").strip().upper()


def vins() -> list[str]:
    return sorted(_demo.demo_vins())


def is_demo(vin: Any) -> bool:
    return _demo.is_demo_vin(vin)


@lru_cache(maxsize=8)
def _read(vin: str) -> Optional[dict[str, Any]]:
    try:
        return json.loads((DATA_DIR / f"{vin}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load(vin: Any) -> Optional[dict[str, Any]]:
    v = _norm(vin)
    return _read(v) if v in _demo.demo_vins() else None


def name(vin: Any) -> str:
    d = load(vin) or {}
    return " ".join(str(d[k]) for k in ("make", "model", "model_year") if d.get(k))


def _at(days_ago: Any, hour: int = 9) -> str:
    day = datetime.now().replace(hour=hour, minute=0, second=0, microsecond=0) - timedelta(days=int(days_ago or 0))
    return day.isoformat(sep=" ", timespec="seconds")


def _base(dtc: str) -> str:
    return dtc.split("-")[0]


_STATUS = {"active": "stored", "pending": "pending", "history": "cleared"}
_SEVERITY = {"active": "chronic", "pending": "seen-once", "history": "cleared"}
_STATE_WORD = {"active": "active now", "pending": "pending", "history": "stored history"}


def dtc_records(vin: Any) -> list[dict[str, Any]]:
    """The codes in the same shape ``mes_bridge.extract_dtcs`` returns (classified records)."""
    d = load(vin)
    if not d:
        return []
    out = []
    for c in d.get("codes", []):
        first, last = _at(c["first_days_ago"]), _at(c["last_days_ago"])
        occ = [{"file": "DEMO sample session", "timestamp": first, "status": _STATUS[c["state"]],
                "odometer_km": c["odometer_first_km"]}]
        if c["sessions"] > 1:
            occ.append({"file": "DEMO sample session", "timestamp": last, "status": _STATUS[c["state"]],
                        "odometer_km": c["odometer_last_km"]})
        out.append({
            "dtc": c["dtc"], "descriptions": [c["description"]], "modules": [c["module"]],
            "vins": [d["vin"]], "vehicles": [name(vin)], "statuses_seen": [_STATUS[c["state"]]],
            "sessions": c["sessions"], "first_seen": first, "last_seen": last, "occurrences": occ,
            "odometer_first_km": c["odometer_first_km"], "odometer_last_km": c["odometer_last_km"],
            "distance_span_km": c["odometer_last_km"] - c["odometer_first_km"],
            "assessment": f"DEMO: {_STATE_WORD[c['state']]}, invented for the demonstration",
            "chronic": c["state"] == "active", "returned_after_clear": False, "severity": _SEVERITY[c["state"]],
            "demo": True, "demo_state": c["state"],
        })
    return out


def extract_dtcs(vin: Any) -> dict[str, Any]:
    rows = dtc_records(vin)
    return {"count": len(rows), "logs_considered": 0, "simulation_included": False, "dtcs": rows, "demo": True}


def dtc_history(vin: Any, code: str) -> Optional[dict[str, Any]]:
    wanted = (code or "").strip().upper()
    rows = [r for r in dtc_records(vin) if wanted in (r["dtc"], _base(r["dtc"]))]
    return {"code": wanted, "matches": rows, "demo": True} if rows else None


def freeze_frames(vin: Any, code: str = "") -> dict[str, Any]:
    d = load(vin) or {}
    wanted = (code or "").strip().upper()
    found = []
    for c in d.get("codes", []):
        if c.get("freeze_frame") and (not wanted or wanted in (c["dtc"], _base(c["dtc"]))):
            found.append({"dtc": c["dtc"], "description": c["description"], "status": _STATUS[c["state"]],
                          "status_meaning": "DEMO: invented", "file": "DEMO sample session",
                          "timestamp": _at(c["last_days_ago"]), "ecu": c["module"], "vin": d["vin"],
                          "freeze_frame": dict(c["freeze_frame"]), "demo": True})
    return {"count": len(found), "frames": found, "demo": True}


def _hist(rec: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in rec.items() if k not in ("chronic", "returned_after_clear", "severity")}


def dossier(vin: Any) -> dict[str, Any]:
    """A logless-style dossier filled from the demo file (same keys ``mes.workup.build`` returns)."""
    d = load(vin) or {}
    rows = dtc_records(vin)
    modules = [m["name"] for m in d.get("modules", [])]
    code_dicts = [{"code": _base(c["dtc"]), "dtc": c["dtc"], "full": c["dtc"], "description": c["description"],
                   "status": _STATUS[c["state"]], "module": c["module"], "freeze_frame": c.get("freeze_frame") or {}}
                  for c in d.get("codes", []) if c["state"] in ("active", "pending")]
    ts = _at(d.get("visit_days_ago", 1))
    per_code: dict[str, list[dict[str, Any]]] = {}
    for b in d.get("tsb", []):
        for c in b.get("dtcs", []):
            per_code.setdefault(c, []).append({"bulletin": b["id"], "date": "DEMO", "title": b["title"],
                                               "action": b["action"], "applies": "DEMO", "dtcs": b["dtcs"],
                                               "source": "DEMO placeholder"})
    return {
        "identity": {"vin": d.get("vin", _norm(vin)), "vehicle": name(vin), "ecu_seen": modules, "log_count": 1,
                     "first_log": None, "last_log": None, "odometer_first_km": d.get("odometer_km"),
                     "odometer_last_km": d.get("odometer_km")},
        "current_picture": {
            "latest_session": {"file": "DEMO sample session", "timestamp": ts, "ecu": d.get("module_label", ""),
                               "odometer_km": d.get("odometer_km"), "dtcs": code_dicts},
            "freeze_frames": {c["dtc"]: dict(c["freeze_frame"]) for c in d.get("codes", []) if c.get("freeze_frame")},
            "latest_scan": {"file": "DEMO sample scan", "timestamp": ts,
                            "modules_with_faults": [{"module": m["name"], "dtcs": []} for m in d.get("modules", [])
                                                    if "NOT READ" not in m["state"] and not m["codes"].startswith("No codes")],
                            "provenance": BANNER},
        },
        "history": {"chronic": [_hist(r) for r in rows if r["chronic"]], "returned_after_clear": [],
                    "seen_once": [_hist(r) for r in rows if not r["chronic"]]},
        "tsb_matches": {"bulletins_considered": len(d.get("tsb", [])), "family_findings": [], "per_code": per_code},
        "already_attempted": [],
        "blind_spots": [{"question": "Which modules did the sample scan not read?",
                         "why_unknown": "DEMO: one module is shown as NOT READ on purpose. Not read is not the same as clean.",
                         "closes_it": "a real read of the car (not possible in the demo)"}],
        "notes": {"vehicle": []},
        "provenance_note": BANNER,
        "demo": True,
    }


def open_work(vin: Any, checklist: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    """Open-work cards (same shape as dossier_bridge's) built from the demo job's own next tests."""
    d = load(vin) or {}
    checklist = checklist or {}
    hyps = d.get("job", {}).get("hypotheses", [])
    cards = []
    for c in d.get("codes", []):
        if c["state"] not in ("active", "pending"):
            continue
        base = _base(c["dtc"])
        texts = [h["next_test"] for h in hyps if base in (h.get("codes") or []) and h.get("next_test")]
        texts.append("DEMO: read the codes again after the repair (the demo cannot connect to a car).")
        steps, done = [], 0
        for i, text in enumerate(texts):
            sid = f"demo-{base}-{i + 1}"
            st = checklist.get(sid) or {}
            done += int(bool(st.get("done")))
            steps.append({"id": sid, "text": text, "ref": "DEMO", "ref_href": None, "done": bool(st.get("done")),
                          "done_at": st.get("done_at"), "done_by": st.get("done_by")})
        cards.append({"family": f"demo_{base.lower()}", "title": f"{c['description'].split(' (DEMO')[0]}: one open issue",
                      "codes": [base], "steps": steps, "refs": [], "progress": {"done": done, "total": len(steps)},
                      "generic": True, "safety_relevant": False})
    return cards


def plan(vin: Any) -> dict[str, Any]:
    """A one-step Next-connection plan so the Bench names the job's next test instead of 'Start a job'."""
    d = load(vin) or {}
    nxt = next((h["next_test"] for h in d.get("job", {}).get("hypotheses", []) if h.get("next_test")), "")
    if not nxt:
        return {"steps": []}
    return {"steps": [{"id": "demo-next", "order": 1, "title": nxt, "why": "DEMO: the next test on the leading hypothesis.",
                       "href": f"/v/{_norm(vin)}/job", "link_label": "Open the job", "preconditions": "",
                       "source": "DEMO"}]}


def sample_page(vin: Any, slug: str) -> Optional[dict[str, Any]]:
    """A small DEMO table for a page the brand has no real data for (``None`` = keep the empty panel)."""
    d = load(vin)
    spec = ((d or {}).get("sample_pages") or {}).get(slug)
    if not spec:
        return None
    rows = spec.get("rows")
    if spec.get("from") == "maintenance_due":
        rows = [[r["item"], r["due"], r["basis"]] for r in d.get("maintenance_due", [])]
    elif spec.get("from") == "tsb":
        rows = [[b["id"], b["title"], ", ".join(b["dtcs"])] for b in d.get("tsb", [])]
    return {"title": spec.get("title", slug), "columns": spec["columns"], "rows": rows or []}


def modules_table(vin: Any) -> Optional[dict[str, Any]]:
    d = load(vin)
    if not d:
        return None
    return {"title": "Modules", "columns": ["Module (DEMO)", "State", "Codes"],
            "rows": [[m["name"], m["state"], m["codes"]] for m in d.get("modules", [])]}


def liveboard_sample(vin: Any) -> list[dict[str, Any]]:
    return list((load(vin) or {}).get("liveboard_sample", []))


def page_sample(vin: Any, slug: str) -> Optional[dict[str, Any]]:
    return modules_table(vin) if slug == "modules" else sample_page(vin, slug)


__all__ = ["BANNER", "CHIP", "is_demo", "vins", "load", "name", "dtc_records", "extract_dtcs", "dtc_history",
           "freeze_frames", "dossier", "page_sample", "liveboard_sample", "open_work", "plan"]
