"""The Tests surface: a catalogue of every mechanic test (:mod:`mes.mechanic_tests`)
grouped by category, each with this vehicle's latest recorded result and a
relevance ranking against its open codes and its job's open hypotheses.

Same posture as :mod:`cuore.services.liveboard_bridge`: one bridge module,
read-mostly, the single place ``cuore`` touches :mod:`mes.mechanic_tests` and
:mod:`mes.jobs` for this feature. Results are written through the existing
checklist result store (:mod:`cuore.live.checklists`), keyed
``step_id = "test:<test_id>"`` so they already flow into the job's
hypothesis evidence path the same way a job-page test row does (see
:mod:`cuore.api.checklists`'s own ``/result`` route, and
:func:`cuore.services.jobs_bridge.add_test_evidence`) -- :mod:`cuore.api.tests`
calls that same function, never a second copy of the auto-attach logic.

Nothing here writes to the car. ``bench_bridge.build_bench`` is read for its
``fuel_gate`` only, to flag the EVAP fuel-level verification window on the
tests it actually affects (the ESIM/EVAP monitor-verification family) --
same blocker the bench page itself already shows.
"""

from __future__ import annotations

from typing import Any, Optional

from datetime import datetime, timezone

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import checklists as checklist_store
from . import cache, mes_bridge
from .errors import BadRequest, NotFound

from mes import mechanic_tests  # noqa: E402

try:
    from mes import jobs as jobs_mod  # noqa: E402
except Exception:  # noqa: BLE001 -- the tests page must still render
    jobs_mod = None

try:
    from . import bench_bridge
except Exception:  # noqa: BLE001 -- blocker awareness is a nice-to-have
    bench_bridge = None

#: Step-id prefix for a test result in the checklist store -- see module
#: docstring. Every write/read against ``checklist_store`` for this feature
#: goes through :func:`_step_id`, never a hand-built string.
_STEP_PREFIX = "test:"

#: The family this catalogue's EVAP tests (``evap_smoke``, ``esim_vacuum_test_a``,
#: ``purge_vent_actuation``) share with the bench's own fuel-window blocker --
#: shown as a caution on these specific tests, not a generic banner on every
#: test.
_EVAP_MONITOR_TEST_IDS = ("evap_smoke", "esim_vacuum_test_a", "purge_vent_actuation")

RESULT_COUNT_KEYS = ("pass", "fail", "inconclusive", "not_possible", "not_done")


def step_id(test_id: str) -> str:
    return f"{_STEP_PREFIX}{test_id}"


def test_id_from_step(step: str) -> Optional[str]:
    """The test id a ``"test:<id>"`` step id names, or ``None`` if ``step``
    is not one of this feature's step ids."""
    if not step.startswith(_STEP_PREFIX):
        return None
    return step[len(_STEP_PREFIX):]


def _cached_dossier(vin: str) -> dict[str, Any]:
    mtime = mes_bridge.newest_mtime(vin)
    return cache.get_or_build(("workup", vin, mtime), lambda: mes_bridge.workup(vin=vin))


def _open_codes(vin: str, dossier: dict[str, Any]) -> list[str]:
    try:
        return mes_bridge.open_codes_for(dossier)
    except Exception:  # noqa: BLE001 -- relevance ranking is best-effort
        return []


def _open_hypotheses(vin: str) -> list[dict[str, Any]]:
    if jobs_mod is None:
        return []
    try:
        job = jobs_mod.current(vin)
    except Exception:  # noqa: BLE001
        return []
    if job is None:
        return []
    return [h for h in job.get("hypotheses", [])
           if h.get("status") == "open" and not h.get("deleted")]


def open_hypotheses_for_form(vin: str) -> list[dict[str, Any]]:
    """``{id, text, system}`` for every open hypothesis on this VIN's
    current job -- the select list the result form offers."""
    return [{"id": h["id"], "text": h.get("text") or "", "system": h.get("system") or ""}
           for h in _open_hypotheses(vin)]


def _fuel_gate(vin: str) -> dict[str, Any]:
    if bench_bridge is None:
        return {}
    try:
        return bench_bridge.build_bench(vin).get("fuel_gate") or {}
    except Exception:  # noqa: BLE001 -- blocker awareness must never 500 the page
        return {}


def _from_car(vin: str, dossier: dict[str, Any]) -> dict[str, Any] | None:
    """A read-only "From the car" strip: this vehicle's latest from-car
    Mode $06 read, if any. Never marks any catalogue test's own row --
    see the module docstring's cross-reference to the job-page evidence
    path, which is the only thing allowed to do that."""
    try:
        from . import dossier_bridge
        return dossier_bridge.build_view(vin, dossier, None).get("mode06")
    except Exception:  # noqa: BLE001 -- the strip is a nice-to-have
        return None


def _result_entry(vin: str, test_id: str) -> dict[str, Any]:
    entry = checklist_store.get(vin).get(step_id(test_id)) or {}
    result = entry.get("result")
    return {
        "result": result or "not_done",
        "value": entry.get("value"),
        "unit": entry.get("unit") or "",
        "reason": entry.get("reason") or "",
        "hypothesis_id": entry.get("hypothesis_id"),
        "when": entry.get("done_at"),
        "by": entry.get("done_by") or "",
        "media_ids": entry.get("media_ids") or [],
    }


def _base_code(code: str) -> str:
    code = (code or "").strip().upper()
    return code[:5] if len(code) >= 5 else code


def _why_for(t: dict[str, Any], open_codes: list[str],
            open_hyps: list[dict[str, Any]], next_test_ids: set[str]) -> list[str]:
    why: list[str] = []
    for h in open_hyps:
        if h.get("next_test") and h["next_test"] == t["id"]:
            why.append(f"next test for hypothesis: {h.get('text') or h['id']}")
    bases = [_base_code(c) for c in open_codes if c]
    for rel in t["related_codes"]:
        rel_u = rel.strip().upper()
        matched = sorted({c for c, b in zip(open_codes, bases) if b.startswith(rel_u)})
        if matched:
            why.append(f"open code {', '.join(matched)}")
    for h in open_hyps:
        if h.get("next_test") == t["id"]:
            continue  # already named above
        if (h.get("system") or "").strip().lower() in t["systems"]:
            why.append(f"open hypothesis: {h.get('text') or h['id']}")
    return why


def _hyp_rank(t: dict[str, Any], open_hyps: list[dict[str, Any]],
             next_test_ids: set[str]) -> int:
    """How strongly this test lines up with the job's open hypotheses --
    the ranking key for "Recommended for this car": 0 when the test is the
    fault tree's own ``next_test`` for an open hypothesis, 1 when the test's
    ``supports_hypotheses`` names one of those hypotheses' own text even
    without being the designated next test, 2 otherwise (an open-code match
    only). Catalogue order (``mechanic_tests._ORDER``, preserved by the
    stable sort in :func:`build_tests_view`) breaks every remaining tie --
    the same order this catalogue's own cross-references
    (:func:`_why_for`'s ``why`` strings, each test's own ``when_to_use``
    prose) were written in."""
    if t["id"] in next_test_ids:
        return 0
    hyp_texts = {(h.get("text") or "").strip() for h in open_hyps if h.get("text")}
    if hyp_texts & set(t["supports_hypotheses"]):
        return 1
    return 2


SORT_KEYS = ("priority", "system", "duration")

#: The state words every list page uses (Job / Codes / Bench / Tests): one
#: vocabulary, label always carried with the colour.
STATE_WORDS = {"pass": "PASS", "fail": "FAIL", "inconclusive": "Inconclusive",
               "not_possible": "Not possible", "skipped": "Skipped",
               "recommended": "Recommended", "not_done": "Not done"}

#: Skips live beside results in the checklist store under their own step id,
#: so a skip is never a result (it neither counts as done nor feeds evidence).
_SKIP_PREFIX = "testskip:"

#: Tool wording that means "read live values through the car link".
_LIVE_TOOL_WORDS = ("scan tool", "live ", "mcp obd2", "cuore", "mode $06")


def age_text(iso: Optional[str], now: Optional[datetime] = None) -> str:
    """"2 d ago" style age of an ISO timestamp; empty string when unknown
    (never guessed)."""
    if not iso:
        return ""
    try:
        then = datetime.fromisoformat(str(iso))
    except ValueError:
        return ""
    now = now or (datetime.now(then.tzinfo) if then.tzinfo else datetime.now())
    secs = (now - then).total_seconds()
    if secs < 0:
        return "just now"
    if secs < 3600:
        return f"{max(1, int(secs // 60))} min ago"
    if secs < 86400:
        return f"{int(secs // 3600)} h ago"
    days = int(secs // 86400)
    if days < 60:
        return f"{days} d ago"
    return f"{days // 30} mo ago"


def _state_of(r: dict[str, Any]) -> tuple[str, str]:
    """(state key, visible label) -- the label always carries the state in
    words so colour is never the only cue."""
    res = r["latest_result"]["result"]
    if res != "not_done":
        return res, STATE_WORDS.get(res, res.replace("_", " ").capitalize())
    if r.get("skip"):
        return "skipped", STATE_WORDS["skipped"]
    blk = r.get("blocker")
    if blk and blk.get("window"):
        return "blocked", "Blocked: " + str(blk.get("reason") or "see note")
    if r["recommended"]:
        return "recommended", STATE_WORDS["recommended"]
    return "not_done", STATE_WORDS["not_done"]


def _needs_live(t: dict[str, Any]) -> bool:
    """True when the test reads live values through the car link (a scan
    tool / CUORE live read / Mode $06), as opposed to hands, a meter or a
    smoke machine. Read from the catalogue's own tool wording, never guessed
    from the test's name."""
    return any(w in str(tool).lower() for tool in t.get("tools") or [] for w in _LIVE_TOOL_WORDS)


def _expects_reading(t: dict[str, Any]) -> bool:
    """True when the pass criteria carry a number or a unit to record."""
    return any(pc.get("unit") or isinstance(pc.get("spec"), (int, float))
               for pc in t.get("pass_criteria") or [])


def _skip_entry(vin: str, test_id: str, store: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
    entry = (store if store is not None else checklist_store.get(vin)).get(_SKIP_PREFIX + test_id) or {}
    if entry.get("done") and entry.get("outcome") == "skipped":
        return {"reason": entry.get("note") or "skipped", "when": entry.get("done_at"),
                "age": age_text(entry.get("done_at"))}
    return None


def _matched_codes(t: dict[str, Any], open_codes: list[str]) -> list[str]:
    out: list[str] = []
    for rel in t.get("related_codes") or []:
        rel_u = rel.strip().upper()
        for c in open_codes:
            if c and _base_code(c).startswith(rel_u) and c not in out:
                out.append(c)
    return out


def _layout(rows: list[dict[str, Any]], open_hyps: list[dict[str, Any]],
            next_test_ids: set[str], sort: str,
            pick_id: Optional[str] = None) -> dict[str, Any]:
    """Split the rows into the mechanic's reading order: the next test (one
    card), the rest of Do next, Blocked, Done (newest first), Skipped, then
    everything else folded by system. ``sort`` re-orders inside each section;
    ``pick_id`` is the test the suspect ranking says splits the suspects best
    (falls back to the first Do-next row)."""
    order = {r["id"]: i for i, r in enumerate(rows)}  # catalogue/priority order

    def prio(r: dict[str, Any]) -> tuple:
        if r["recommended"]:
            return (_hyp_rank(r, open_hyps, next_test_ids), -len(r["why"]), order[r["id"]])
        return (3, 0, order[r["id"]])

    def key(r: dict[str, Any]) -> tuple:
        if sort == "system":
            return (r["system"], prio(r))
        if sort == "duration":
            return (r["duration_min"], prio(r))
        return prio(r)

    for r in rows:
        r["state"], r["state_label"] = _state_of(r)
        r["system"] = (r["systems"][0] if r.get("systems") else "general")
        r["age"] = age_text(r["latest_result"].get("when"))

    todo = [r for r in rows if r["state"] in ("recommended", "not_done", "blocked")]
    do_next = sorted([r for r in todo if r["state"] == "recommended"], key=key)
    blocked = sorted([r for r in todo if r["state"] == "blocked"], key=key)
    done = sorted([r for r in rows if r["state"] not in ("recommended", "not_done", "blocked", "skipped")],
                  key=lambda r: r["latest_result"].get("when") or "", reverse=True)
    skipped = sorted([r for r in rows if r["state"] == "skipped"],
                     key=lambda r: (r["skip"] or {}).get("when") or "", reverse=True)
    rest_rows = sorted([r for r in todo if r["state"] == "not_done"], key=key)

    # the one next test: the ranking's pick if it can be done now, else the
    # first Do-next row, else the first undone test of any kind
    card = next((r for r in do_next + rest_rows if r["id"] == pick_id), None)
    if card is None and do_next:
        card = do_next[0]
    if card is None and rest_rows:
        card = rest_rows[0]
    if card is not None:
        do_next = [r for r in do_next if r is not card]
        rest_rows = [r for r in rest_rows if r is not card]

    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rest_rows:
        groups.setdefault(r["system"], []).append(r)
    rest = [{"system": k, "label": k.replace("_", " "), "rows": v, "count": len(v),
             "minutes": sum(x["duration_min"] for x in v)}
            for k, v in sorted(groups.items())]
    return {"card": card, "do_next": do_next, "blocked": blocked, "done": done,
            "skipped": skipped, "rest": rest,
            "rest_count": len(rest_rows), "sort": sort,
            "done_fail": sum(1 for r in done if r["state"] == "fail")}


def _ranking_pick(vin: str) -> Optional[dict[str, Any]]:
    """The suspect ranking's next-test pick (the test that best splits the
    top suspects per minute), or ``None`` -- the page then falls back to the
    first Do-next row. Cached inside ``suspect_ranking.diagnose``."""
    try:
        from . import suspect_ranking
        nt = suspect_ranking.diagnose(vin).get("next_test")
        return nt if nt and nt.get("kind") == "catalogue" else None
    except Exception:  # noqa: BLE001 -- the call degrades to the plain order
        return None


def _short(text: str, n: int = 110) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "..."


def _build_call(vin: str, layout: dict[str, Any], open_codes: list[str],
                open_hyps: list[dict[str, Any]], pick: Optional[dict[str, Any]],
                connected: bool) -> Optional[dict[str, Any]]:
    """The one-line directing call for the card test, its "Why this?" text
    and the go-to links. ``None`` when nothing is left to do."""
    t = layout["card"]
    if t is None:
        return None
    hyp = next((h for h in open_hyps if h.get("next_test") == t["id"]), None)
    proves = hyp.get("text") if hyp else None
    if not proves:
        texts = {(h.get("text") or "").strip() for h in open_hyps}
        proves = next((s for s in t.get("supports_hypotheses") or [] if s in texts), None)
    if not proves:
        proves = next(iter(t.get("supports_hypotheses") or []), None)
    if not proves:
        proves = t["system"].replace("_", " ")
    blockers: list[str] = []
    blk = t.get("blocker")
    if blk and blk.get("window"):
        blockers.append(f"Blocked: fuel level {blk.get('level')}% is {blk.get('direction')} the "
                        f"{blk['window'][0]}-{blk['window'][1]}% window")
    elif blk:
        blockers.append(f"Check first: {blk.get('reason')}")
    if t["needs_live"] and not connected:
        blockers.append("needs the car, not connected")
    ranked = bool(pick and pick.get("id") == t["id"])
    why: list[str] = []
    if ranked:
        why.append(str(pick.get("why") or "").rstrip("."))
        if pick.get("if_pass_rules_out"):
            why.append("A pass clears: " + "; ".join(_short(x, 90) for x in pick["if_pass_rules_out"][:2]))
        if pick.get("if_fail_rules_out"):
            why.append("A fail makes these less likely: " + "; ".join(_short(x, 90) for x in pick["if_fail_rules_out"][:3]))
    else:
        why.extend(t.get("why") or [])
    if not why:
        why.append("Next undone test in the catalogue order; no open code or hypothesis ranks it.")
    code = (_matched_codes(t, open_codes) or [None])[0]
    links = [{"label": "Job", "href": f"/v/{vin}/job"},
             {"label": "Codes", "href": f"/v/{vin}/codes"},
             {"label": f"Electrical path {code}" if code else "Electrical layout",
              "href": f"/v/{vin}/electrical" + (f"?code={code}" if code else "")},
             {"label": "Procedure sheet", "href": f"/v/{vin}/tests/{t['id']}/print"}]
    return {"id": t["id"], "name": t["name"],
            "effort": f"{t['duration_min']} min" if t.get("duration_min") else "effort unknown",
            "proves": _short(proves, 100), "blockers": blockers, "ranked": ranked,
            "why": why, "links": links}


def undo_banner(vin: str, did: str) -> Optional[dict[str, Any]]:
    """What the "just recorded" banner shows for ``?did=<test id>``: the
    result (or skip) now on file, with what Undo will clear. ``None`` when
    the id is unknown or nothing is on file for it."""
    t = mechanic_tests.test(did or "")
    if t is None:
        return None
    r = _result_entry(vin, did)
    if r["result"] != "not_done":
        return {"id": did, "name": t["name"], "kind": "result",
                "label": STATE_WORDS.get(r["result"], r["result"]),
                "result": r["result"], "value": r["value"], "unit": r["unit"], "reason": r["reason"],
                "expects_reading": _expects_reading(t), "system": (t["systems"] or [""])[0]}
    sk = _skip_entry(vin, did)
    if sk:
        return {"id": did, "name": t["name"], "kind": "skip", "label": STATE_WORDS["skipped"],
                "result": "", "value": None, "unit": "", "reason": sk["reason"],
                "expects_reading": False, "system": ""}
    return None


def skip_test(vin: str, test_id: str, reason: str = "", *, undo: bool = False,
              connected: bool = False) -> dict[str, Any]:
    """Defer a test to the bottom of the page (``undo=True`` puts it back).
    The reason defaults to the plainest true one: needs the car and it is not
    connected, else skipped by the mechanic. Never a result, never evidence."""
    t = mechanic_tests.test(test_id)
    if t is None:
        raise BadRequest(f"unknown test id {test_id!r}")
    if undo:
        checklist_store.set_step(vin, _SKIP_PREFIX + test_id, False)
        return {"test_id": test_id, "skipped": False}
    why = (reason or "").strip() or ("needs the car, not connected" if _needs_live(t) and not connected
                                      else "skipped by mechanic")
    checklist_store.set_step(vin, _SKIP_PREFIX + test_id, True, outcome="skipped", note=why[:120])
    return {"test_id": test_id, "skipped": True, "reason": why[:120]}


def build_tests_view(vin: str, sort: str = "priority", connected: bool = False) -> dict[str, Any]:
    """Everything ``tests.html`` needs: the full catalogue, each test's
    latest result, relevance ranking, and category/summary counts."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")

    dossier = _cached_dossier(vin)
    open_codes = _open_codes(vin, dossier)
    open_hyps = _open_hypotheses(vin)
    fuel_gate = _fuel_gate(vin)
    # Review #6 item 2: a stale fuel reading (older than the newest
    # readiness read) warns, it never hard-blocks -- same rule the bench's
    # own fuel gate already applies to its "fuel out of window" blocker.
    fuel_stale = bool(fuel_gate.get("stale"))
    fuel_blocked = fuel_gate.get("in_window") is False and not fuel_stale

    # Marque-filtered catalogue (MECHANIC_REVIEW_4/check_marque_port.py):
    # a test whose own applies_to rules out this vehicle's marque (e.g. the
    # Stelvio-specific wiTECH/ESIM-bench tests, which name the real Stelvio
    # VIN in their sourced pass_criteria text) must never render on another
    # marque's Tests page. mechanic_tests.all_tests() is the unfiltered
    # catalogue; tests_for_marque() is the one this page actually shows.
    catalogue = mechanic_tests.tests_for_marque(mes_bridge.marque_for_vin(vin))

    code_test_ids = {t["id"] for t in mechanic_tests.tests_for_codes(open_codes)}
    hyp_systems = [h.get("system") or "" for h in open_hyps if h.get("system")]
    sys_test_ids = {t["id"] for t in mechanic_tests.tests_for_systems(hyp_systems)} if hyp_systems else set()
    recommended_ids = code_test_ids | sys_test_ids

    # Catalogue siblings (2026-10-14 fix): a test that shares a
    # supports_hypotheses tag with an already-recommended test surfaces too,
    # even when it has no related_codes/system of its own to match on --
    # e.g. mil_bulb_check is inherently code-less (a bulb check, not a DTC
    # symptom) and its only system (infotainment_cluster) never matches an
    # open EVAP hypothesis, yet it shares "MIL request/lamp mismatch" with
    # mil_request_vs_lamp, which the open U1713 code already recommends --
    # both must surface together, same as the evap_test_a_esim_switch/
    # esim_commanded_vent_test/esim_wiring_test family already does via
    # their shared "evap" system.
    by_id = {t["id"]: t for t in catalogue}
    active_tags = {tag for tid in recommended_ids
                  for tag in (by_id.get(tid, {}).get("supports_hypotheses") or [])}
    sibling_ids = ({t["id"] for t in catalogue
                   if active_tags & set(t["supports_hypotheses"])}
                  if active_tags else set()) - recommended_ids
    recommended_ids |= sibling_ids
    next_test_ids = {h["next_test"] for h in open_hyps if h.get("next_test")}

    rows: list[dict[str, Any]] = []
    store = checklist_store.get(vin)
    counts = {k: 0 for k in RESULT_COUNT_KEYS}
    for t in catalogue:
        rid = t["id"]
        latest = _result_entry(vin, rid)
        counts[latest["result"]] = counts.get(latest["result"], 0) + 1
        blocker = None
        if rid in _EVAP_MONITOR_TEST_IDS:
            if fuel_blocked:
                blocker = {
                    "reason": "fuel out of window",
                    "window": fuel_gate.get("window"),
                    "level": fuel_gate.get("level"),
                    "direction": fuel_gate.get("direction"),
                }
            elif fuel_stale:
                blocker = {
                    "reason": "verify fuel reading",
                    "at": fuel_gate.get("at"),
                    "source": fuel_gate.get("source"),
                }
        why = _why_for(t, open_codes, open_hyps, next_test_ids) if rid in recommended_ids else []
        if not why and rid in sibling_ids:
            shared_tag = next(iter(active_tags & set(t["supports_hypotheses"])), None)
            if shared_tag:
                why = [f"shares hypothesis '{shared_tag}' with another recommended test"]
        rows.append({
            **t,
            "step_id": step_id(rid),
            "latest_result": latest,
            "recommended": rid in recommended_ids,
            "why": why,
            "blocker": blocker,
            "needs_live": _needs_live(t),
            "expects_reading": _expects_reading(t),
            "skip": _skip_entry(vin, rid, store),
        })

    # Recommended rows rank by the fault tree's next test, then by
    # supports_hypotheses match (_hyp_rank), with the catalogue's own order
    # (mechanic_tests._ORDER, already the order `rows` was built in) as the
    # stable tiebreak -- e.g. the EVAP: ESIM signal path line reads Test A
    # (evap_test_a_esim_switch, the hypothesis's own next_test), then the
    # ESIM commanded vent test, then the ESIM wiring test, exactly the
    # sequence those three tests' own when_to_use text cross-references.
    # Everything not recommended keeps the prior category/name grouping.
    rows.sort(key=lambda r: (
        (0, _hyp_rank(r, open_hyps, next_test_ids), "", "")
        if r["recommended"] else (1, 0, r["category"], r["name"])
    ))
    categories = sorted({t["category"] for t in catalogue})
    if sort not in SORT_KEYS:
        sort = "priority"
    pick = _ranking_pick(vin)
    layout = _layout(rows, open_hyps, next_test_ids, sort, pick.get("id") if pick else None)
    call = _build_call(vin, layout, open_codes, open_hyps, pick, connected)
    live_waiting = sum(1 for r in ([layout["card"]] if layout["card"] else []) + layout["do_next"]
                       if r["needs_live"])

    return {
        "layout": layout,
        "call": call,
        "connected": connected,
        "live_waiting": live_waiting,
        "vin": vin,
        "tests": rows,
        "categories": categories,
        "counts": counts,
        "total": len(rows),
        "open_codes": open_codes,
        "open_hypotheses": open_hypotheses_for_form(vin),
        "fuel_gate": fuel_gate,
        "from_car": _from_car(vin, dossier),
    }


def build_test_print_view(vin: str, test_id: str) -> dict[str, Any]:
    """Everything ``tests_print.html`` needs for one test's printable sheet:
    the test itself, this vehicle's latest recorded result (same
    ``step_id``/result-entry contract as :func:`build_tests_view`'s rows),
    and an as-of stamp. Raises :class:`NotFound` for an unknown test id --
    same posture as every other single-item lookup in this package."""
    vin = (vin or "").strip()
    if not vin:
        raise BadRequest("a VIN is required")
    t = mechanic_tests.test(test_id)
    if t is None:
        raise NotFound(f"unknown test id {test_id!r}")
    return {
        "vin": vin,
        "test": t,
        "step_id": step_id(test_id),
        "latest_result": _result_entry(vin, test_id),
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }


def record_result(vin: str, test_id: str, result: Optional[str], *, reason: str = "",
                  value: Optional[float] = None, unit: str = "",
                  hypothesis_id: Optional[str] = None, supports: str = "for",
                  by: str = "") -> dict[str, Any]:
    """Store one test's result and, when it names a hypothesis and the
    result is pass/fail, auto-attach it as evidence -- the same contract
    ``cuore.api.checklists``'s ``/result`` route already uses
    (:func:`cuore.services.jobs_bridge.add_test_evidence`), reused here
    rather than duplicated. ``supports`` is "for"/"against", exactly as
    that route's own field -- the caller (the result form) decides which
    side of the hypothesis this result counts toward; a plain pass/fail is
    not itself for/against any particular hypothesis without the tech
    saying so."""
    if mechanic_tests.test(test_id) is None:
        raise BadRequest(f"unknown test id {test_id!r}")
    if result is not None and result not in mechanic_tests.POSTABLE_RESULTS:
        raise BadRequest("result must be one of: "
                         + ", ".join(mechanic_tests.POSTABLE_RESULTS) + ", or null")
    if supports not in ("for", "against"):
        raise BadRequest("supports must be 'for' or 'against'")
    sid = step_id(test_id)
    entry = checklist_store.set_result(vin, sid, result, reason=reason, value=value,
                                       unit=unit, hypothesis_id=hypothesis_id, by=by)
    if hypothesis_id and result in ("pass", "fail"):
        t = mechanic_tests.test(test_id)
        label = f"{t['name']}: {result}"
        if value is not None:
            label += f" {value:g}{unit}"
        try:
            from . import jobs_bridge
            jobs_bridge.add_test_evidence(vin, hypothesis_id, sid, label, result,
                                          supports=supports, by=by)
        except Exception:  # noqa: BLE001 -- the result must still save
            pass
    return {"vin": vin, "test_id": test_id, "step_id": sid, **entry}


__all__ = ["build_tests_view", "build_test_print_view", "record_result", "step_id",
          "test_id_from_step", "open_hypotheses_for_form", "RESULT_COUNT_KEYS",
          "skip_test", "undo_banner", "STATE_WORDS"]
