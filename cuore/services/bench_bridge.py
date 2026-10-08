"""Data for the bench page: "what am I doing to this car, right now".

``cuore/web/routes.py``'s old ``/v/{vin}`` was the full dossier -- verdict,
every code, every bulletin, every freeze frame, all at once. That page still
exists (moved to ``/v/{vin}/dossier``); this module backs the thing a
mechanic actually wants the instant the car is on the lift: a resume
summary of what changed since the last visit, the verdict's own next-action
sentence, the tasks to go do about it (with procedure, pass criteria, parts
and tools each one needs already resolved), live preconditions, the fuel
gate and readiness panel, and a couple of jump-off points (codes, the job,
the full dossier) -- nothing that needs scrolling to reach on a 400x800
screen.

``build_bench`` is the only entry point. It composes bridges that already
exist -- ``dossier_bridge.build_view`` for the verdict/open-work/codes/
bulletins/freeze-frames, ``mes_bridge.fault_tree`` for sourced procedure
steps, ``electrical_bridge`` for electrical/physical inspect steps,
``known_good_bridge`` for expected readings, ``parts_bridge``/
``tools_kb_bridge`` for what a step needs, ``cuore.live.ops``/``checklists``
for live status and the shop-ticked checklist, ``shop_bridge``/
``cases_bridge`` for the header line and the case hint -- and invents no new
diagnosis of its own. See BENCH_UX_SPEC_2026-10-08.md for the walkthrough
this module answers.
"""

from __future__ import annotations

import json
import re
import threading
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from . import cache, dossier_bridge, known_good_bridge, mes_bridge, parts_bridge, tools_kb_bridge
from .errors import BadRequest
from ..live import checklists as checklist_store
from ..live.config import state_dir

try:
    from . import cases_bridge
except Exception:  # noqa: BLE001 -- the bench must still render without it
    cases_bridge = None

try:
    from . import shop_bridge
except Exception:  # noqa: BLE001
    shop_bridge = None

try:
    from . import electrical_bridge
except Exception:  # noqa: BLE001
    electrical_bridge = None

try:
    from ..live import ops as live_ops
except Exception:  # noqa: BLE001
    live_ops = None


#: Capped the same way the spec caps each bench card: 3 next actions, each
#: with at most 3 parts and 4 tools.
_MAX_ACTIONS = 3
_MAX_PARTS = 3
_MAX_TOOLS = 4
_MAX_SHORTCUTS = 6
_MAX_INSPECT_STEPS = 4

#: Hours since the newest scan/session before the bench flags it stale
#: (BENCH_UX_SPEC_2026-10-08.md A2) -- a stale read silently invalidates the
#: whole checklist, so this is surfaced on the bench itself, not just in the
#: dossier footer.
_STALE_HOURS = 24.0

#: Family key (lowercased, as ``dossier_bridge.FAMILY_STEPS``/the generic
#: SAE-range rules spell it) -> icon registry key, for the bench card's own
#: pictogram. Anything not listed here falls back to a generic glyph --
#: never a 500 for a family this table doesn't know about yet.
FAMILY_ICON: dict[str, str] = {
    "evap": "sys_evap", "network": "sys_network", "misfire": "sys_ignition",
    "fuel_trim": "sys_fuel", "cooling": "sys_cooling",
    "engine_management": "sys_engine_management",
    "transmission_driveline": "sys_transmission_driveline", "adas": "sys_adas_sensors",
    "chassis": "sys_suspension", "body": "sys_body_comfort",
    "powertrain_other": "sys_engine_management",
}

#: The chip colour legend rendered once below the DTC shortcut chips
#: (BENCH_UX_SPEC_2026-10-08.md D11) -- kept here, not guessed per-chip in
#: the template, so the legend and the chip classes can never drift apart.
_STATUS_LEGEND = [
    {"label": "Active", "css": "v-active"},
    {"label": "Cleared, unverified", "css": "v-cleared-unverified"},
]


# --- small helpers ----------------------------------------------------------


def _parse_full_ts(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        return datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _relative_time(ts: str | None) -> str | None:
    """"2 h ago" / "3 d ago" -- never a bare ISO stamp on the resume card."""
    dt = _parse_full_ts(ts)
    if dt is None:
        return None
    secs = max(0.0, (datetime.now() - dt).total_seconds())
    hours = secs / 3600
    if hours < 1:
        return f"{max(1, int(secs // 60))} min ago"
    if hours < 48:
        return f"{hours:.0f} h ago"
    return f"{hours / 24:.0f} d ago"


def _hours_since(ts: str | None) -> float | None:
    dt = _parse_full_ts(ts)
    if dt is None:
        return None
    return max(0.0, (datetime.now() - dt).total_seconds() / 3600)


# --- per-VIN visit tracking, for the resume card's "what changed" ----------
#
# A small JSON file beside checklists.json/addresses.json, same posture as
# cuore.live.checklists -- one file, one lock, read-modify-write. Kept here
# rather than in cuore.live because this is purely a bench-rendering
# convenience (the previous visit's snapshot), not shop-of-record state.

_VISIT_LOCK = threading.Lock()


def _visits_path() -> Path:
    # A SUBdirectory, not a file directly under state_dir(): bench_visits.json
    # is pure bench-rendering bookkeeping (the previous visit's snapshot),
    # not shop-of-record state -- but dossier_bridge._state_fingerprint()
    # folds the mtime of every *direct* file under state_dir() into its own
    # expensive-build cache key, so a file written on every single bench
    # page load (this one) would invalidate that cache on every single bench
    # page load too, defeating it completely. iterdir() is not recursive, so
    # a subdirectory's contents are invisible to that scan.
    d = state_dir() / "bench"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d / "visits.json"


def _load_visits() -> dict[str, Any]:
    try:
        return json.loads(_visits_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_visits(data: dict[str, Any]) -> None:
    try:
        _visits_path().write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _record_visit(vin: str, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    """Store this visit's snapshot for ``vin``, returning the PREVIOUS one
    (``None`` on this vehicle's first bench view)."""
    with _VISIT_LOCK:
        data = _load_visits()
        previous = data.get(vin)
        data[vin] = {**snapshot, "at": datetime.now().isoformat(timespec="seconds")}
        _save_visits(data)
        return previous


def _resume_changes(previous: dict[str, Any] | None, active_codes: list[str],
                    cleared_codes: list[str], last_read: str | None) -> list[str]:
    if previous is None:
        return []
    changes: list[str] = []
    new_active = sorted(set(active_codes) - set(previous.get("active_codes") or []))
    new_cleared = sorted(set(cleared_codes) - set(previous.get("cleared_codes") or []))
    if new_active:
        changes.append(("New code: " if len(new_active) == 1 else "New codes: ")
                       + ", ".join(new_active))
    if new_cleared:
        changes.append(("Cleared: " if len(new_cleared) == 1 else "Cleared: ")
                       + ", ".join(new_cleared))
    if last_read and previous.get("last_read") and last_read != previous.get("last_read"):
        changes.append(f"New record logged ({last_read})")
    return changes


# --- live status, read fresh for this page (ops.status() is cheap: no I/O
#    to the car, just the registry/lock file/MES process state) ------------


def _live_status() -> dict[str, Any]:
    if live_ops is None:
        return {"error": "live ops unavailable"}
    try:
        s = live_ops.status()
        return {
            "port": s.get("port"),
            "mes_state": (s.get("mes") or {}).get("state"),
            "lock_holder": (s.get("lock") or {}).get("process"),
            "error": None,
        }
    except Exception as exc:  # noqa: BLE001 -- a broken strip must never 500 the bench
        return {"error": str(exc)}


def _preconditions(text: str, live_status: dict[str, Any],
                   fuel_blocked: bool) -> list[dict[str, Any]]:
    """Per-task live preconditions with a one-click fix link
    (BENCH_UX_SPEC_2026-10-08.md C9): MES running for an actuator test
    (-> /live), the car connected for a readiness/verify/live-channel read
    (-> /tools), fuel in window for that same verify step (text only, no
    link -- there is nothing to click, only fuel to burn)."""
    low = (text or "").lower()
    out: list[dict[str, Any]] = []
    if "actuator" in low or "koeo" in low:
        out.append({
            "label": "MES running", "ok": live_status.get("mes_state") == "connected",
            "fix_href": "/live", "fix_label": "Open Live", "fix_text": None,
        })
    needs_car = any(k in low for k in
                    ("readiness", "verify", "mode $06", "slvt", "live channel"))
    if needs_car:
        out.append({
            "label": "Car connected", "ok": dossier_bridge.live_available(live_status),
            "fix_href": "/tools", "fix_label": "Tools", "fix_text": None,
        })
        if fuel_blocked:
            out.append({
                "label": "Fuel in window", "ok": False,
                "fix_href": None, "fix_label": None,
                "fix_text": "burn fuel into the 15-85% window",
            })
    return out


def _task_state(done: bool, preconditions: list[dict[str, Any]]) -> tuple[str, str | None]:
    if done:
        return "DONE", None
    unmet = next((p for p in preconditions if not p["ok"]), None)
    if unmet is not None:
        return "BLOCKED", unmet["label"]
    return "READY", None


# --- procedure detail: the fault tree's own step, plus electrical/physical
#    inspect steps, for the task's own expandable body --------------------


def _tree_candidates(vin: str, codes: list[str], mtime: float) -> list[dict[str, Any]]:
    """Every fault-tree :class:`mes.faulttree.Step` (as a dict) applicable to
    this card's codes -- steps plus verification, from every tree that
    matches.

    Memoised on ``(vin, codes, mtime)`` -- same posture as
    ``cuore.services.cache`` everywhere else in this app -- because
    ``mes_bridge.fault_tree`` annotates against this VIN's own FES-log
    evidence, which re-parses every log for the vehicle on every call;
    without this, every single bench page load repeated that full parse,
    which is both slow for a mechanic reloading the page and (observed
    directly) slow enough to break the 400px screenshot check's fixed
    render-wait budget.
    """
    if not codes:
        return []

    def _build() -> list[dict[str, Any]]:
        try:
            result = mes_bridge.fault_tree(",".join(codes), vin=vin)
        except Exception:  # noqa: BLE001
            return []
        out: list[dict[str, Any]] = []
        for t in result.get("trees") or []:
            out.extend(t.get("steps") or [])
            out.extend(t.get("verification") or [])
        return out

    return cache.get_or_build(("bench_tree_candidates", vin, tuple(codes), mtime), _build)


def _match_tree_step(candidates: list[dict[str, Any]], ref: str | None,
                     text: str) -> dict[str, Any] | None:
    """The step in ``candidates`` this open-work step is transcribed from,
    matched first by bulletin number (exact, when the step cites one), else
    by keyword overlap with the step's own text. ``None`` when nothing
    matches well enough -- the detail panel then says so honestly instead
    of guessing."""
    if not candidates:
        return None
    if ref:
        for c in candidates:
            if ref in (c.get("source") or ""):
                return c
    words = set(re.findall(r"[a-z]{4,}", (text or "").lower()))
    best, best_score = None, 0
    for c in candidates:
        blob = f"{c.get('title', '')} {c.get('test', '')}".lower()
        score = len(words & set(re.findall(r"[a-z]{4,}", blob)))
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 2 else None


def _action_doc(ref: str | None, ref_href: str | None,
                bulletins_by_id: dict[str, Any]) -> dict[str, Any] | None:
    if not ref:
        return None
    entry = bulletins_by_id.get(ref) or {}
    return {"id": ref, "href": ref_href, "title": entry.get("title"),
            "action": entry.get("action")}


def _inspect_steps(codes: list[str]) -> list[dict[str, Any]]:
    """Electrical/physical inspect steps for this step's family -- element,
    what to check, how, and the source -- when ``mes.electrical`` has a
    curated path for this code. ``[]`` otherwise, never invented."""
    if electrical_bridge is None or not codes:
        return []
    try:
        path = electrical_bridge.path_for_code(codes[0])
    except Exception:  # noqa: BLE001
        return []
    return (path or {}).get("inspect_steps") or []


def _action_detail(candidates: list[dict[str, Any]], inspect_steps: list[dict[str, Any]],
                   ref: str | None, ref_href: str | None, text: str,
                   bulletins_by_id: dict[str, Any]) -> dict[str, Any]:
    match = _match_tree_step(candidates, ref, text)
    if match:
        procedure = {"test": match.get("test"), "tools": match.get("tools"),
                     "source": match.get("source"), "caution": match.get("caution")}
        pass_line = match.get("expect") or None
        if_abnormal = match.get("if_abnormal")
    else:
        procedure = {"test": None, "tools": None, "source": ref, "caution": None}
        pass_line = None
        if_abnormal = None
    return {
        "procedure": procedure,
        "pass_line": pass_line or ("UNKNOWN -- no sourced pass criterion for this "
                                   "step yet; confirm on the car / service manual"),
        "if_abnormal": if_abnormal,
        "doc": _action_doc(ref, ref_href, bulletins_by_id),
        "inspect_steps": inspect_steps[:_MAX_INSPECT_STEPS],
    }


# --- parts/tools, job-level and per-task --------------------------------


def _family_parts(vin: str, codes: list[str]) -> list[dict[str, Any]]:
    """Up to :data:`_MAX_PARTS` parts for a family's codes, deduplicated by
    part key, each shaped ``{name, number, confidence}``. ``number`` and
    ``confidence`` come off the first OEM row a part carries, falling back
    to the first aftermarket row -- never invented when neither exists."""
    seen: dict[str, dict[str, Any]] = {}
    for code in codes:
        if len(seen) >= _MAX_PARTS:
            break
        try:
            rows = parts_bridge.parts_for_code(code, vin=vin)
        except Exception:  # noqa: BLE001
            rows = []
        for p in rows:
            key = p.get("key")
            if not key or key in seen:
                continue
            oem = p.get("oem") or []
            aftermarket = p.get("aftermarket") or []
            src = oem[0] if oem else (aftermarket[0] if aftermarket else {})
            seen[key] = {"name": p.get("name"), "number": src.get("number"),
                        "confidence": src.get("confidence", "UNKNOWN")}
            if len(seen) >= _MAX_PARTS:
                break
    return list(seen.values())


def _family_tools(family: str) -> list[dict[str, Any]]:
    """Up to :data:`_MAX_TOOLS` tools for this family, shaped
    ``{name, have}`` -- ``tools_kb_bridge.recommend`` already resolves
    ``have`` against the shop's own inventory. ``[]`` for a family
    ``mes.tools_kb`` has no job-tools table for yet (most of the generic
    families) -- never a guess at what tool a car needs."""
    try:
        rows = tools_kb_bridge.recommend((family or "").lower())
    except Exception:  # noqa: BLE001
        return []
    out = []
    for r in rows[:_MAX_TOOLS]:
        info = r.get("tool_info") or {}
        out.append({"name": info.get("name") or info.get("key"), "have": r.get("have")})
    return out


def _hoist_shared(actions: list[dict[str, Any]]) -> tuple[list[dict[str, Any]],
                                                           list[dict[str, Any]]]:
    """Pull parts/tools common to every visible task up to job level
    (BENCH_UX_SPEC_2026-10-08.md B6) -- each task then shows only what it
    uniquely needs. A no-op with 0 or 1 tasks: nothing is "shared" yet."""
    n = len(actions)
    if n <= 1:
        return [], []
    part_counts = Counter(p["number"] or p["name"] for a in actions for p in a["parts"])
    tool_counts = Counter(t["name"] for a in actions for t in a["tools"])
    shared_parts = {k for k, c in part_counts.items() if c == n}
    shared_tools = {k for k, c in tool_counts.items() if c == n}
    job_parts: list[dict[str, Any]] = []
    job_tools: list[dict[str, Any]] = []
    seen_p: set[str] = set()
    seen_t: set[str] = set()
    for a in actions:
        for p in a["parts"]:
            key = p["number"] or p["name"]
            if key in shared_parts and key not in seen_p:
                seen_p.add(key)
                job_parts.append(p)
        for t in a["tools"]:
            if t["name"] in shared_tools and t["name"] not in seen_t:
                seen_t.add(t["name"])
                job_tools.append(t)
        a["parts"] = [p for p in a["parts"] if (p["number"] or p["name"]) not in shared_parts]
        a["tools"] = [t for t in a["tools"] if t["name"] not in shared_tools]
    return job_parts, job_tools


# --- the task list itself ----------------------------------------------


def _next_actions(vin: str, open_work: list[dict[str, Any]],
                  codes_by_base: dict[str, str], checklist: dict[str, Any],
                  live_status: dict[str, Any], fuel_blocked: bool,
                  bulletins_by_id: dict[str, Any], mtime: float) -> list[dict[str, Any]]:
    """The top :data:`_MAX_ACTIONS` open-work steps across every family,
    ACTIVE families first (any of that family's codes currently ACTIVE in
    the code table), then in the same order
    ``dossier_bridge._build_open_work`` already put the cards in (curated
    families, then the generic ones) -- a stable sort preserves that
    ordering within each of the two groups.

    Unlike the old selection, a step already ticked still occupies its slot
    (BENCH_UX_SPEC_2026-10-08.md B8: a fixed roster with READY/BLOCKED/DONE
    states, not a shifting top-3-unchecked list) -- otherwise a task marked
    done would vanish from the bench the instant it was ticked, and "undo"
    would have nowhere to act.
    """
    def is_active(card: dict[str, Any]) -> bool:
        return any(codes_by_base.get(c) == "ACTIVE" for c in card.get("codes") or [])

    ordered = sorted(open_work, key=lambda c: 0 if is_active(c) else 1)

    actions: list[dict[str, Any]] = []
    for card in ordered:
        if len(actions) >= _MAX_ACTIONS:
            return actions
        family = card.get("family") or ""
        codes = card.get("codes") or []
        # Computed once per CARD, not per step: every step in a card shares
        # the same codes, and both the fault-tree lookup (re-parses this
        # VIN's own FES logs to annotate against its evidence) and the
        # electrical path lookup are otherwise paid again for every step.
        candidates = _tree_candidates(vin, codes, mtime)
        inspect_steps = _inspect_steps(codes)
        parts = _family_parts(vin, codes)
        tools = _family_tools(family)
        for step in card.get("steps") or []:
            entry = checklist.get(step["id"]) or {}
            done = bool(entry.get("done"))
            ref = step.get("ref")
            preconditions = _preconditions(step["text"], live_status, fuel_blocked)
            state, blocked_reason = _task_state(done, preconditions)
            actions.append({
                "step_id": step["id"], "family": family, "text": step["text"],
                "bulletin": ({"id": ref, "href": step.get("ref_href")} if ref else None),
                "parts": list(parts),
                "tools": list(tools),
                "done": done, "done_at": entry.get("done_at"),
                "done_by": entry.get("done_by"), "outcome": entry.get("outcome"),
                "note": entry.get("note"),
                "state": state, "blocked_reason": blocked_reason,
                "preconditions": preconditions,
                "detail": _action_detail(candidates, inspect_steps, ref,
                                         step.get("ref_href"), step["text"], bulletins_by_id),
                "href_tick": f"/v/{vin}/bench/done",
                "icon": FAMILY_ICON.get(family.lower(), "tools"),
            })
            if len(actions) >= _MAX_ACTIONS:
                return actions
    return actions


def _shortcuts(vin: str, codes: list[dict[str, Any]],
               open_work: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Up to :data:`_MAX_SHORTCUTS` code-page links, active codes and
    cleared-but-unverified codes only -- a stale code is not worth a tap
    target on a screen this small. Each chip carries what its hover/title
    needs: meaning, status, and which open-work task addresses it
    (BENCH_UX_SPEC_2026-10-08.md D11)."""
    addressed_by: dict[str, str] = {}
    for card in open_work:
        for c in card.get("codes") or []:
            addressed_by.setdefault(c, card.get("title") or card.get("family") or "")

    out = []
    for row in codes:
        if row.get("status") not in ("ACTIVE", "CLEARED_UNVERIFIED"):
            continue
        out.append({
            "code": row["code"], "href": row["href"], "status": row["status"],
            "status_label": row.get("status_label") or row["status"],
            "description": row.get("description") or None,
            "addressed_by": addressed_by.get(row["code"]),
        })
        if len(out) >= _MAX_SHORTCUTS:
            break
    return out


# --- header bits ---------------------------------------------------------


def _vehicle_name(vin: str, dossier: dict[str, Any]) -> str:
    """Never "(unnamed vehicle)" -- ``shop_bridge.resolve_vehicle_name``
    already guarantees that (corpus name, then dossier identity, then a WMI
    decode, then the VIN itself); if that bridge is unavailable for any
    reason, fall back to the dossier's own identity field, then the VIN."""
    if shop_bridge is not None:
        try:
            name = shop_bridge.resolve_vehicle_name(vin)
            if name:
                return name
        except Exception:  # noqa: BLE001
            pass
    return (dossier.get("identity") or {}).get("vehicle") or vin


def _complaint(vin: str) -> str | None:
    if shop_bridge is None:
        return None
    try:
        visit = shop_bridge.current_visit_for_vin(vin)
    except Exception:  # noqa: BLE001
        return None
    return (visit or {}).get("complaint") or None


def _case_hint(vin: str, open_codes: list[str]) -> str | None:
    """One line from ``cases_bridge.prefill`` -- only when a prior case
    actually matched; the honest "no prior case on file" summary
    ``mes.cases.prefill`` returns otherwise is not a hint worth a mechanic's
    attention."""
    if cases_bridge is None:
        return None
    try:
        prefill = cases_bridge.prefill(vin, open_codes)
    except Exception:  # noqa: BLE001
        return None
    if not prefill.get("matched_case"):
        return None
    return prefill.get("summary")


def _fuel_gate(vin: str, freeze_frames: list[dict[str, Any]]) -> dict[str, Any]:
    """The live fuel gate (BENCH_UX_SPEC_2026-10-08.md C10): current fuel %,
    the 15-85% EVAP window, and litres to burn to reach 85% -- only when a
    sourced tank capacity exists for this VIN; ``None`` (UNKNOWN) otherwise,
    never a guessed number."""
    status = dossier_bridge.fuel_status(freeze_frames)
    capacity = _tank_capacity_litres(vin)
    litres = None
    if (status["level"] is not None and status["direction"] == "above"
            and capacity is not None):
        litres = round((status["level"] - status["window"][1]) / 100.0 * capacity, 1)
    return {**status, "tank_capacity_l": capacity, "litres_to_target": litres}


def _tank_capacity_litres(vin: str) -> float | None:
    """Sourced tank capacity for this VIN (``mes.maintenance_specs`` /
    ``mes.service``), or ``None`` (UNKNOWN) -- this corpus carries no such
    spec today, so this always reads UNKNOWN in practice; kept as a real
    lookup (not a hardcoded None) so a future sourced spec picks it up for
    free."""
    try:
        from mes import maintenance_specs  # local: optional, see module docstring
        getter = getattr(maintenance_specs, "fuel_tank_capacity_l", None)
        if callable(getter):
            return getter(vin)
    except Exception:  # noqa: BLE001
        pass
    return None


def build_bench(vin: str) -> dict[str, Any]:
    """Everything ``bench.html`` needs, computed once.

    ``live_status`` is passed as ``None`` into ``dossier_bridge.build_view``
    -- the same choice ``flow_bridge.flow_state`` and
    ``shop_bridge._dossier_verdict`` already make from the service layer:
    it only affects whether the verdict's own action buttons render as
    enabled, never the verdict state itself (that comes from recorded
    observations), and the bench page does not render those buttons anyway.
    The bench's own precondition checks read a freshly computed live status
    instead (see :func:`_live_status`).
    """
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")

    mtime = mes_bridge.newest_mtime(vin)
    dossier = cache.get_or_build(("workup", vin, mtime), lambda: mes_bridge.workup(vin=vin))
    view = dossier_bridge.build_view(vin, dossier, None)
    identity = dossier.get("identity") or {}

    verdict_raw = view.get("verdict") or {}
    verdict = {
        "state": verdict_raw.get("state"),
        "label": verdict_raw.get("label"),
        "sentence": verdict_raw.get("summary"),
        "next_action": verdict_raw.get("next_action"),
        "blocker": verdict_raw.get("blocker"),
        "basis": verdict_raw.get("basis") or [],
    }

    codes = view.get("codes") or []
    codes_by_base = {row["code"]: row["status"] for row in codes}
    open_work = view.get("open_work") or []
    bulletins_by_id = {b["id"]: b for b in view.get("bulletins") or []}
    checklist = checklist_store.get(vin)
    live_status = _live_status()
    fuel_blocked = verdict["blocker"] == "fuel out of window"

    next_actions = _next_actions(vin, open_work, codes_by_base, checklist,
                                 live_status, fuel_blocked, bulletins_by_id, mtime)
    job_parts, job_tools = _hoist_shared(next_actions)

    latest = view.get("latest") or {}
    last_read = latest.get("session_short") or latest.get("scan_short")

    cp = dossier.get("current_picture") or {}
    scan_ts = (cp.get("latest_scan") or {}).get("timestamp")
    session_ts = (cp.get("latest_session") or {}).get("timestamp")
    newest_ts = max([t for t in (scan_ts, session_ts) if t], default=None)
    hours_since = _hours_since(newest_ts)

    done_total = sum((c.get("progress") or {}).get("done", 0) for c in open_work)
    steps_total = sum((c.get("progress") or {}).get("total", 0) for c in open_work)

    active_codes = sorted(r["code"] for r in codes if r["status"] == "ACTIVE")
    cleared_codes = sorted(r["code"] for r in codes if r["status"] == "CLEARED_UNVERIFIED")
    previous_visit = _record_visit(vin, {
        "active_codes": active_codes, "cleared_codes": cleared_codes,
        "last_read": last_read,
    })
    resume = {
        "last_scan_relative": _relative_time(newest_ts) or "no scan on file",
        "last_scan_at": newest_ts,
        "changed": _resume_changes(previous_visit, active_codes, cleared_codes, last_read),
        "is_first_visit": previous_visit is None,
        "done": done_total,
        "total": steps_total,
        "next_action": verdict["next_action"],
    }

    try:
        open_codes = mes_bridge.open_codes_for(dossier)
    except Exception:  # noqa: BLE001
        open_codes = []

    return {
        "vin": vin,
        "vehicle": _vehicle_name(vin, dossier),
        "vin_tail": vin[-6:] if len(vin) >= 6 else vin,
        "km": identity.get("odometer_last_km"),
        "complaint": _complaint(vin),
        "verdict": verdict,
        "resume": resume,
        "progress": {"done": done_total, "total": steps_total},
        "scan_stale": bool(hours_since is not None and hours_since > _STALE_HOURS),
        "scan_hours_since": hours_since,
        "next_actions": next_actions,
        "job_parts": job_parts,
        "job_tools": job_tools,
        "open_codes_count": (view.get("code_counts") or {}).get("active", 0),
        "last_read": last_read,
        "shortcuts": _shortcuts(vin, codes, open_work),
        "legend": _STATUS_LEGEND,
        "case_hint": _case_hint(vin, open_codes),
        "fuel_gate": _fuel_gate(vin, view.get("freeze_frames") or []),
        "readiness": dossier_bridge.readiness_panel(vin, dossier),
        "live_status": live_status,
    }


__all__ = ["build_bench", "FAMILY_ICON"]
