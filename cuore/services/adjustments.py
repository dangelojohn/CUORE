"""Adjustments catalogue: every reset / configuration procedure CUORE knows, its status and sources.

Read-only and offline. Nothing here opens an adapter or writes anything. It reuses
``cuore.live.procedure_sources`` (``list()`` / ``load()`` merge the shipped JSON with the state-dir override;
``is_accepted()`` reads the append-only acceptance log). procedure_sources exposes no log of verified runs, so
"performed_verified" is read here from an optional ``procedure_runs.jsonl`` in the state dir (records with
``procedure`` and ``verified: true``); that file does not exist yet, so nothing is "performed_verified" today.
A card never offers a run: ``can_run`` is always False on this screen.
"""
from __future__ import annotations

import json
from typing import Any

from ..live import procedure_sources
from ..live.config import state_dir

STATUS_ORDER = ["performed_verified", "accepted", "documented", "awaiting source"]
STATUS_MARK = {"performed_verified": "✓", "accepted": "●", "documented": "◐", "awaiting source": "○"}
STATUS_WORD = {"performed_verified": "Performed and verified", "accepted": "Accepted by the owner",
               "documented": "Documented, not accepted", "awaiting source": "Awaiting source"}
GROUPS = [("resets", "Resets and routines", "Counters and reminders set back after a service."),
          ("config", "Configuration", "Choices stored in a module's configuration, with options.")]
WHY_NOT = {
    "awaiting source": "Awaiting the manufacturer's documented procedure. Then: dry run, gate, typed consent, read-back.",
    "documented": "Documented but not accepted by the owner yet. Then: dry run, gate, typed consent, read-back.",
    "accepted": "Run control is not part of this screen. Runs go through the gated session path: dry run, gate, typed consent, read-back.",
    "performed_verified": "Run control is not part of this screen. A repeat goes through the gated session path: dry run, gate, typed consent, read-back.",
}


def _verified_runs() -> set[str]:
    out: set[str] = set()
    try:
        for line in (state_dir() / "procedure_runs.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if isinstance(r, dict) and r.get("verified") is True and r.get("procedure"):
                out.add(str(r["procedure"]))
    except OSError:
        pass
    return out


def _status(d: dict[str, Any], verified: set[str]) -> str:
    name = d["name"]
    steps = d.get("steps") or []
    acc = procedure_sources.is_accepted(name, _d=d)["accepted"]
    if acc and name in verified:
        return "performed_verified"
    if acc:
        return "accepted"
    if steps and (d.get("source") or {}).get("citation"):
        return "documented"
    return "awaiting source"


def _card(d: dict[str, Any], verified: set[str]) -> dict[str, Any]:
    name = d["name"]
    st = _status(d, verified)
    src = d.get("source") or {}
    cite = src.get("citation")
    steps = procedure_sources.normalized_steps(d) if d.get("steps") else []
    checks = (d.get("read_back") or {}).get("checks") or []
    dids = [str(c["did"]) for c in checks if c.get("did")]
    rb_status = (d.get("read_back") or {}).get("status")
    if dids:
        reads = ", ".join(dids)
    elif checks and rb_status != "unknown":
        reads = "DID not yet identified; will check: " + ", ".join(str(c.get("quantity")) for c in checks)
    else:
        reads = "unknown"
    pre = d.get("preconditions") or {}
    options = [{"id": o.get("id"), "label": o.get("label"), "meaning": o.get("meaning"), "source": o.get("source")}
               for o in d.get("options") or []]
    return {
        "name": name,
        "title": d.get("title") or str(d.get("mes_function") or name.replace("_", " ")).strip().capitalize(),
        "module": d.get("module"),
        "intent": d.get("intent"),
        "status": st, "mark": STATUS_MARK[st], "word": STATUS_WORD[st],
        "source": cite or "none yet",
        "source_confidence": src.get("confidence"),
        "writes": steps if steps else "unknown until documented",
        "reads_back": reads,
        "preconditions": pre.get("label") or None,
        "options": options,
        "group": "config" if options else "resets",
        "follow_up": d.get("follow_up"),
        "risks": d.get("risks") or [],
        "needs_from_manufacturer": d.get("needs_from_manufacturer") or [],
        "public_values": d.get("public_values"),
        "mes_runs": d.get("mes_runs") or d.get("last_mes_runs") or [],
        "mes_function": d.get("mes_function"),
        "can_run": False,
        "why_not": WHY_NOT[st],
    }


def cards() -> list[dict[str, Any]]:
    verified = _verified_runs()
    out = []
    for row in procedure_sources.list():
        try:
            out.append(_card(procedure_sources.load(row["name"]), verified))
        except KeyError:
            continue
    return out


def board(open_name: str = "") -> dict[str, Any]:
    cs = cards()
    counts = {k: sum(1 for c in cs if c["status"] == k) for k in STATUS_ORDER}
    groups = [{"key": k, "label": label, "why": why, "cards": [c for c in cs if c["group"] == k]} for k, label, why in GROUPS]
    groups = [g for g in groups if g["cards"]]
    return {"total": len(cs), "counts": counts, "order": STATUS_ORDER, "mark": STATUS_MARK, "word": STATUS_WORD,
            "groups": groups, "open_name": open_name, "known": any(c["name"] == open_name for c in cs)}
