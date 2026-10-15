"""Mechanic steps for one hypothesis: the ordered, numbered tasks a mechanic
performs to confirm or refute it.

Rules, not guesses -- every step's ``source`` cites what put it there: a
bulletin number (via ``tsb_xref_bridge.xref``), a fragment of the
hypothesis's own CONFIRM / REFUTE / NEXT TESTS text, a job action, or a
systems-graph dependency path. Derivation order (see :func:`plan`):

1. pre-conditions (never clear codes; no CAN-CH transmit without consent);
2. bulletin cross-reference for this hypothesis (VIN checks, flash per,
   procedure per, inspect per; excluded bulletins go to the rationale);
3. module currency (controlling module's calibration vs its flash bulletins);
4. the hypothesis's CONFIRM / REFUTE / NEXT TESTS text -> drive cycle,
   reads, decide;
5. dependency layer (``systems_bridge.related_systems(depth=1)``);
6. job actions already recorded mark steps done (moved to "already done");
7. final step: record every step on the job.

Read-only. The only write is :func:`save_as_next_test`, called from an
explicit button press, which goes through ``jobs_bridge.edit_hypothesis``.
Loaders (``_load_*``) are module-level so tests can patch them.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import systems_bridge, tsb_xref_bridge

KINDS = ("precondition", "vin_check", "read", "flash", "test", "drive_cycle",
         "decide", "inspect", "record")
#: deterministic stage order (lower first); done steps go after everything
_STAGE = {"precondition": 0, "vin_check": 1, "currency": 2, "flash": 3, "test": 4,
          "proof": 3.5, "drive_cycle": 5, "read": 6, "decide": 7, "inspect": 8, "record": 9}

#: Monitor run conditions on file in the repo, per system. Only systems the
#: repo documents; anything else gets "drive until the monitor reports
#: complete" with no invented conditions.
DRIVE_CYCLES: dict[str, dict[str, Any]] = {
    "evap": {
        "monitor": "EVAP (Evaporative system)",
        "conditions": [
            "start from cold after a long engine-off soak",
            "fuel level between 15 % and 85 % (about 1/4 to 3/4 tank, the EVAP verification window)",
            "several drives, each followed by an engine-off soak (P0456 sets only "
            "across multiple engine-off soak/drive cycles)",
            "check readiness in CUORE after each drive",
        ],
        "source": "mes.faulttree EVAP V1/V2 ('EVAP monitor needs fuel level roughly 15-85% "
                  "and cold-start windows'; 'P0456 sets only across multiple engine-off "
                  "soak/drive cycles') and mes.workup next_step",
    },
}

_LABEL_RE = re.compile(r"\b(CLAIM|EVIDENCE FOR|EVIDENCE AGAINST|CONFIRM|REFUTE|NEXT TESTS?|UPDATE)"
                       r"\b[^:\n]{0,90}:")
_CODE_RE = re.compile(r"\b[PBCU][0-9A-F]{4}\b")
_MONITOR_DONE_RE = re.compile(r"monitor\w*\s+(?:now\s+|has\s+|have\s+)?(?:reports?\s+|reported\s+|is\s+|was\s+|"
                              r"are\s+|were\s+)?(?:run\s+(?:to\s+)?)?complete(?:d)?\b", re.I)
#: a sentence that only plans or asks (not a record of something done)
_FORWARD_RE = re.compile(r"\b(next|until|should|if|whether|ask|once|when|need\w*|incomplete|not|"
                         r"pending|plan\w*|to\s+do)\b", re.I)
#: per stage: what a sentence must say, next to the citation, to count as done
_DONE_VERB = {
    "vin_check": re.compile(r"\b(VIN|dealer|lookup|looked\s+up|performed|applies|listed)\b", re.I),
    "flash": re.compile(r"\b(flash\w*|reprogram\w*|re-?flash\w*)\b", re.I),
    "test": re.compile(r"\b(ran|run|performed|result|passed|failed|pass|fail)\b", re.I),
    "inspect": re.compile(r"\b(inspect\w*|checked|found|seated|clean|ruled\s+out)\b", re.I),
}
_CURRENCY_DONE_RE = re.compile(r"calibration\s+part\s+number|(?:ECM|PCM)\s+(?:software|calibration)"
                               r"\s+(?:level|version|part)", re.I)
_DONE_VERB["proof"] = _DONE_VERB["test"]
#: a procedure that verifies a repair rather than performs one
_VERIFY_RE = re.compile(r"verification\s+test|SLVT|leak\s+test|smoke\s+test|proof\s+of\s+(?:the\s+)?fix", re.I)
_STOP_LINE = "If it passes and the codes stay away, stop here; record the result."
_DONE_KINDS = ("part", "repair", "inspection", "test")
_MODULE_ALIASES = {"ECM": ("ECM", "PCM"), "PCM": ("ECM", "PCM")}


# --- loaders (patched by tests) -------------------------------------------


def _load_job(job_id: str) -> Optional[dict[str, Any]]:
    from mes import jobs as jobs_mod
    return jobs_mod.get(job_id)


def _load_xref(vin: str) -> dict[str, Any]:
    return tsb_xref_bridge.xref(vin)


def _load_catalogue() -> dict[str, Any]:
    return tsb_xref_bridge._load_catalogue()


def _load_code_table(vin: str) -> dict[str, dict[str, Any]]:
    try:
        return tsb_xref_bridge._code_table(vin)
    except Exception:  # noqa: BLE001
        return {}


# --- text helpers ------------------------------------------------------------


def sections(text: str) -> dict[str, str]:
    """Labelled segments of a hypothesis text: CLAIM, EVIDENCE FOR, CONFIRM,
    REFUTE, NEXT TESTS, UPDATE (the first of each label wins; text before
    any label is ``_lead``)."""
    out: dict[str, str] = {}
    ms = list(_LABEL_RE.finditer(text or ""))
    out["_lead"] = (text or "")[: ms[0].start()].strip() if ms else (text or "").strip()
    for i, m in enumerate(ms):
        label = m.group(1).upper()
        label = "NEXT TESTS" if label.startswith("NEXT TEST") else label
        end = ms[i + 1].start() if i + 1 < len(ms) else len(text)
        out.setdefault(label, text[m.end():end].strip())
    return out


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;])\s+(?=[A-Z(])", text or "") if s.strip()]


def _first_sentence(text: str, width: int = 220) -> str:
    s = _sentences(text)
    return (s[0] if s else (text or "")).strip()[:width]


def _hyp_codes(h: dict[str, Any], secs: dict[str, str]) -> list[str]:
    src = (secs.get("CLAIM") or secs.get("_lead") or h.get("text") or "")
    out: list[str] = []
    for c in list(h.get("codes") or []) + _CODE_RE.findall(src):
        b = str(c).strip().upper().split("-")[0]
        if b and b not in out:
            out.append(b)
    return out


def _ts(s: Optional[str]) -> str:
    return (s or "").replace("T", " ")[:16]


def _action_ref(a: dict[str, Any], i: int) -> str:
    return f"action #{i} ({a.get('kind')}, {_ts(a.get('at'))}): {(a.get('text') or '')[:90]}"


# --- step builder ------------------------------------------------------------


def _step(stage: str, title: str, detail: str, source: str, *, kind: Optional[str] = None,
          bulletins: Optional[list[str]] = None, tools: Optional[list[str]] = None,
          done_match: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    return {"stage": stage, "kind": kind or stage, "title": title, "detail": detail,
            "source": source, "done": False, "done_ref": "",
            "bulletins": list(bulletins or []), "tools": list(tools or []),
            "_match": done_match or {}}


# --- the generator -----------------------------------------------------------


def plan(vin: str, job_id: str, hypothesis_id: str, *,
         xref_view: Optional[dict[str, Any]] = None,
         job: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Ordered mechanic steps for one hypothesis. ``xref_view``/``job`` may
    be passed in by a page that already has them (one xref per render)."""
    vin = (vin or "").strip().upper()
    job = job if job is not None else _load_job(job_id)
    if not job:
        raise KeyError(f"job {job_id} not found")
    h = next((x for x in job.get("hypotheses") or [] if x.get("id") == hypothesis_id), None)
    if h is None:
        raise KeyError(f"hypothesis {hypothesis_id} not found on job {job_id}")
    view = xref_view if xref_view is not None else _load_xref(vin)
    cat_items = {i.get("id"): i for i in (_load_catalogue().get("items") or [])}
    graph = systems_bridge.systems()
    labels = {k: v.get("label", k) for k, v in graph.items()}
    text = h.get("text") or ""
    secs = sections(text)
    hsys = h.get("system") or ""
    hlabel = labels.get(hsys, h.get("system_text") or hsys or "this system")
    codes = _hyp_codes(h, secs)
    steps: list[dict[str, Any]] = []
    rationale: list[str] = []

    # 1. pre-conditions ---------------------------------------------------
    claim = secs.get("CLAIM") or secs.get("_lead") or text
    about_clear = bool(re.search(r"\b(clear\w*|reset\w*)\b", _first_sentence(claim), re.I))
    if not about_clear:
        steps.append(_step("precondition", "Never clear codes",
                           "Do not clear any DTC (no MES/CUORE/scan-tool clear) until this "
                           "hypothesis is confirmed or refuted: a clear resets the monitors and "
                           "Mode 06 results and erases the evidence the reads below need.",
                           "project rule: never clear codes"
                           + (f"; hypothesis text: '{m.group(0)}'" if (m := re.search(
                               r"[^.]*\b(?:not|never|no)\b[^.]*\bclear\w*[^.]*\.", text, re.I))
                              else ""),
                           tools=[]))
    else:
        rationale.append("No 'never clear' step: the hypothesis itself is about a clear "
                         f"('{_first_sentence(claim, 120)}').")

    ctable = _load_code_table(vin)
    car_active = {_base_code(c.get("code")) for c in ctable.values() if c.get("active") and c.get("code")}
    wanted_codes = car_active | {_base_code(c) for c in codes}

    # 2. bulletins ----------------------------------------------------------
    bmap = {b["id"]: b for b in view.get("bulletins") or []}
    hyp_rows = list((view.get("by_hypothesis") or {}).get(hypothesis_id) or [])
    if view.get("job_id") and view.get("job_id") != job.get("id"):
        rationale.append(f"Bulletin cross-reference covers the open job {view.get('job_id')}, "
                         f"not this job; no bulletin steps.")
        hyp_rows = []
    superseded = {}
    for row in hyp_rows:
        sup = str((cat_items.get(row["bulletin"]) or {}).get("supersedes") or "").strip()
        if sup:
            superseded[sup] = row["number"]
    vin_lines: list[tuple[str, str]] = []          # (number, line)
    weak_steps: list[dict[str, Any]] = []
    flash_rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    proc_groups: dict[str, list[dict[str, Any]]] = {}
    inspect_rows: list[tuple[dict[str, Any], dict[str, Any], str]] = []
    for row in hyp_rows:
        b = bmap.get(row["bulletin"]) or {}
        item = cat_items.get(row["bulletin"]) or {}
        num = row["number"]
        rels = b.get("relations") or []
        relset = {r.get("relation") for r in rels}
        rkind, parts, how = tsb_xref_bridge._repair_implied(item) if item else ("inspect", [], "")
        applies = b.get("applies") or item.get("applies") or "vin_check"
        ruled = [r for r in rels if r.get("relation") == "ruled_out_by_inspection"]
        if ruled:
            rationale.append(f"Excluded {num}: ruled out by inspection -- {ruled[0]['reason'][:200]}")
            continue
        applied = [r for r in rels if r.get("relation") == "already_applied"]
        genuine = [r for r in applied if _genuine_applied(r, num, rkind)]
        if genuine and "did_not_resolve" in relset:
            nr = next(r for r in rels if r.get("relation") == "did_not_resolve")
            rationale.append(f"Excluded {num}: already applied and did not resolve -- "
                             f"{genuine[0]['reason'][:160]}; {nr['reason'][:140]}")
            continue
        if applied and not genuine:
            rationale.append(f"Kept {num}: the cross-reference matched an action by part name "
                             f"only ({applied[0]['reason'][:120]}), but no action records this "
                             f"{rkind}.")
        if num in superseded:
            rationale.append(f"{num} is superseded by {superseded[num]}; folded into that step.")
        if applies == "no":
            rationale.append(f"Excluded {num}: the catalogue marks it as not applying to this car.")
            continue
        doubt = [r["reason"] for r in rels if r.get("type") == "applicability"
                 and "another model" in r.get("reason", "")]
        if row["relation"] == "weakens" or doubt:
            weak_steps.append(_step(
                "vin_check", f"Verify by VIN whether {num} applies to this car",
                f"Look {num} up by VIN (dealer / Service Library VIN search) before acting on it. "
                f"Doubt on file: {(doubt[0] if doubt else row['reason'])[:220]}. Do not "
                f"{'flash' if rkind == 'flash' else 'act'} per {num} unless the VIN lookup lists "
                f"this car.",
                f"bulletin {num}: relation '{row['relation']}' -- {row['reason'][:200]}",
                bulletins=[num], tools=["dealer / VIN lookup"],
                done_match={"cite": [num]}))
            continue
        if rkind == "none":
            rationale.append(f"No step for {num}: information only, no remedy "
                             f"({(item.get('title') or '')[:80]}).")
            continue
        if rkind == "flash":
            q = (f"{num} ({item.get('kind') or b.get('kind') or 'bulletin'}): was it performed on "
                 f"{vin}?")
            if b.get("kind") in ("recall", "csn") or applies == "vin_check":
                q += " If open, the dealer performs it."
            vin_lines.append((num, q))
            if applies == "yes" and b.get("kind") not in ("recall", "csn"):
                flash_rows.append((row, item))
            continue
        if rkind == "procedure":
            pname = str(item.get("repair_implied") or "").partition(":")[2].strip() or num
            proc_groups.setdefault(pname.lower(), []).append(dict(row, _item=item, _pname=pname,
                                                                  _applies=applies))
            continue
        if applies == "vin_check":
            vin_lines.append((num, f"{num}: does it apply to {vin}? ({(item.get('title') or '')[:70]})"))
        inspect_rows.append((row, item, rkind))

    if vin_lines:
        nums = [n for n, _ in vin_lines]
        steps.append(_step(
            "vin_check", "VIN checks (no tools): " + ", ".join(nums),
            "Ask the dealer / Mopar VIN lookup / Transport Canada recall search, record the answer "
            "and date: " + " ".join(f"({i + 1}) {ln}" for i, (_, ln) in enumerate(vin_lines)),
            "bulletins " + "; ".join(f"{r['number']}: {r['reason'][:110]}" for r in hyp_rows
                                     if r["number"] in nums),
            bulletins=nums, tools=["dealer / VIN lookup"], done_match={"cite": nums}))
    steps.extend(weak_steps)

    # 3. module currency -----------------------------------------------------
    module, mod_src = _controlling_module(vin, hsys, codes, graph)
    if module:
        aliases = _MODULE_ALIASES.get(module, (module,))
        mod_sys = _module_system(module, graph)
        mflash, doubtful, others = [], [], 0
        hyp_nums = {r["number"] for r in hyp_rows}
        for b in view.get("bulletins") or []:
            item = cat_items.get(b["id"]) or {}
            if not item or b.get("applies") == "no":
                continue
            rk, parts, _ = tsb_xref_bridge._repair_implied(item)
            if rk != "flash":
                continue
            names_mod = any(p.upper() in aliases for p in parts) or (mod_sys and mod_sys in (b.get("systems") or []))
            if not names_mod:
                continue
            if "other_model" in (b.get("flags") or []):
                doubtful.append(b["number"])
            elif b["number"] in hyp_nums or b.get("applies") == "yes":
                mflash.append(b["number"])
            else:
                others += 1
        if others:
            rationale.append(f"{others} further {module} flash bulletin(s) in the catalogue need a VIN "
                             f"check and are not tied to this hypothesis; not listed in the currency step.")
        if mflash:
            latest = [n for n, _r in ((r["number"], r) for r, _i in flash_rows)] or mflash[:1]
            steps.append(_step(
                "currency", f"wiTECH: read the current {module} calibration part number and compare",
                f"wiTECH, {module} flash tab: record the installed {module} calibration part number "
                f"and the latest available; compare with the release named in {', '.join(latest)}. "
                f"Bulletins/recalls on file that reflash this {module}: {', '.join(mflash)}"
                + (f" (doubtful applicability, not a target: {', '.join(doubtful)})" if doubtful else "")
                + ". Read only, no flash in this step.",
                f"module currency: {mod_src}; {module} flash bulletins in the cross-reference: "
                f"{', '.join(mflash)}",
                kind="read", bulletins=mflash, tools=["wiTECH"],
                done_match={"regex": _CURRENCY_DONE_RE}))
    for row, item in flash_rows:
        num = row["number"]
        steps.append(_step(
            "flash", f"If outdated: flash per {num}",
            f"Only if the {module or 'module'} calibration read above is older than the release for "
            f"{num}: reprogram per {num}; record before/after calibration part numbers. "
            f"Remedy on file: {(item.get('remedy') or '')[:200]}",
            f"bulletin {num}: relation '{row['relation']}' -- {row['reason'][:160]}",
            bulletins=[num], tools=["wiTECH"],
            done_match={"cite": [num]}))
    for pname, rows in proc_groups.items():
        rows.sort(key=lambda r: (r["number"] in superseded, r["_applies"] != "yes"))
        main = rows[0]
        nums = [r["number"] for r in rows]
        src = "; ".join(f"bulletin {r['number']}: relation '{r['relation']}' -- {r['reason'][:100]}"
                        for r in rows)
        also = f" (also named by {', '.join(nums[1:])})" if len(nums) > 1 else ""
        if any(_VERIFY_RE.search(r["_pname"]) or _VERIFY_RE.search(
                str(r["_item"].get("cuore_relevance") or "")) for r in rows):
            steps.append(_step(
                "proof", f"Proof of fix: {main['_pname']} per {main['number']}",
                f"Run {main['_pname']} per {main['number']}{also}. "
                f"{(main['_item'].get('remedy') or '')[:200]} Do it after any flash/repair above; "
                f"a road test alone does not prove an EVAP repair. {_STOP_LINE}",
                src, kind="test", bulletins=nums, tools=["wiTECH"] if "witech" in pname else [],
                done_match={"cite": nums}))
            continue
        steps.append(_step(
            "test", f"Procedure per {main['number']}: {main['_pname']}",
            f"Run {main['_pname']} per {main['number']}{also}. {(main['_item'].get('remedy') or '')[:200]} "
            f"Use it as the measured proof after any flash/repair above; a road test alone does not "
            f"prove an EVAP repair.",
            src, bulletins=nums, tools=["wiTECH"] if "witech" in pname else [],
            done_match={"cite": nums}))

    # 4. CONFIRM / REFUTE / NEXT TESTS ---------------------------------------
    confirm, refute, nxt = secs.get("CONFIRM", ""), secs.get("REFUTE", ""), secs.get("NEXT TESTS", "")
    reads = _reads(confirm + " " + refute, h, codes, module)
    monitors = _monitors_for(hsys)
    needs_monitor = bool(reads) and (re.search(r"\bmonitor", confirm, re.I)
                                     or any(r[0] in ("status", "mode06", "readiness", "permanent")
                                            for r in reads)) and (hsys in DRIVE_CYCLES or monitors)
    if needs_monitor:
        dc = DRIVE_CYCLES.get(hsys)
        mon = dc["monitor"] if dc else monitors[0]
        cond = ("; ".join(dc["conditions"]) if dc else
                "no drive-cycle conditions are on file for this monitor -- follow the service manual")
        frag = re.search(r"[^.]*\bmonitor[^.]*\.", confirm, re.I)
        steps.append(_step(
            "drive_cycle", f"Drive until the {mon} monitor reports complete",
            f"Conditions: {cond}. Never clear codes.",
            (f"hypothesis CONFIRM: '{frag.group(0).strip()[:160]}'; " if frag else "")
            + (f"monitor conditions: {dc['source']}" if dc else
               f"monitor for {hlabel}: mes.systems.MONITOR_TO_SYSTEM"),
            tools=["CUORE"], done_match={"regex": _MONITOR_DONE_RE, "kinds": ("test",)}))
    if reads:
        clause = re.search(r"\bread\b[^.]*", confirm, re.I)
        steps.append(_step(
            "read", "Read in CUORE" + (" after the monitor has run" if needs_monitor else ""),
            "; ".join(r[1] for r in reads) + ".",
            "hypothesis CONFIRM: '" + (clause.group(0).strip()[:200] if clause else confirm[:200]) + "'"
            + ("; REFUTE: '" + refute[:120] + "'" if refute else ""),
            tools=["CUORE"],
            done_match={"regex": _MONITOR_DONE_RE, "kinds": ("test",)} if needs_monitor else {}))
    rules = [s for s in _sentences(confirm) if re.search(r"\bconfirm", s, re.I)]
    rules += [s for s in _sentences(refute) if not re.search(r"\bclear", s, re.I)]
    covered = {n for s in steps for n in s["bulletins"]}
    for item_text in _next_items(nxt):
        first, _, rest = item_text.partition(". ")
        cited = [r["number"] for r in hyp_rows if tsb_xref_bridge.cites(first, r["number"])]
        if (cited and set(cited) <= covered) or (re.search(r"calibration", first, re.I)
                                                and any(s["stage"] == "currency" for s in steps)):
            rationale.append(f"NEXT TESTS item '{first[:90]}' is covered by the bulletin/currency steps.")
        else:
            kind = ("vin_check" if re.search(r"\b(dealer|VIN)\b", first) else
                    "inspect" if re.search(r"\binspect", first, re.I) else "test")
            steps.append(_step(kind, first[:90].rstrip(" ;,."), first.rstrip(" ;"),
                               f"hypothesis NEXT TESTS: '{first[:160]}'",
                               done_match={"cite": cited} if cited else {}))
        rules += [s for s in _sentences(rest) if re.match(r"\s*if\b", s, re.I)]
    if rules:
        steps.append(_step(
            "decide", "Decide: confirm or refute",
            " ".join(f"({i + 1}) {r.rstrip('.')}." for i, r in enumerate(rules))
            + " Set the hypothesis status from the result; the confirm gate needs the reads above "
              "attached as evidence.",
            "hypothesis " + " / ".join(lbl for lbl, t in (("CONFIRM", confirm), ("REFUTE", refute),
                                                           ("NEXT TESTS", nxt)) if t) + " text",
            tools=["CUORE"]))

    # inspect steps from bulletins
    for row, item, rk in inspect_rows:
        num = row["number"]
        bd = {_base_code(d) for d in item.get("dtcs") or []}
        if bd and not (bd & wanted_codes):
            rationale.append(f"Excluded {num}: no code overlap (bulletin codes {', '.join(sorted(bd))}; "
                             f"car active/hypothesis codes {', '.join(sorted(wanted_codes)) or 'none'}).")
            continue
        what = (f"before replacing {', '.join(item.get('components') or [])[:80]}" if rk == "replace"
                else "")
        steps.append(_step(
            "inspect", f"Inspect per {num}" + (f" {what}" if what else ""),
            f"{(item.get('remedy') or item.get('title') or '')[:240]}",
            f"bulletin {num}: relation '{row['relation']}' -- {row['reason'][:160]}",
            bulletins=[num], done_match={"cite": [num]}))

    # 5. dependency layer -------------------------------------------------
    if hsys in graph:
        for rs in systems_bridge.related_systems(hsys, depth=1):
            k = rs["system"]
            act = sorted({c["code"] for c in ctable.values() if c.get("active") and k in (c.get("systems") or [])})
            bul: list[str] = []
            for b in view.get("bulletins") or []:
                if b.get("applies") == "no":
                    continue
                rels_b = b.get("relations") or []
                if not any(r.get("relation") in ("same_system", "dependent_system") and r.get("system") == k
                           for r in rels_b):
                    continue
                # a bare system tag is not enough: the bulletin must also explain a code on k
                hit = [r["code"] for r in rels_b if r.get("relation") in ("explains", "historical")
                       and r.get("code") and (k in ((ctable.get(_base_code(r["code"])) or {}).get("systems") or [])
                                              or not ctable.get(_base_code(r["code"])))]
                if hit:
                    bul.append(f"{b['number']} ({hit[0]})")
            if not act and not bul:
                continue
            path = " -> ".join(labels.get(p, p) for p in rs["path"])
            trig = ([f"active {', '.join(act)}"] if act else []) + (
                [f"open bulletin(s) {', '.join(bul[:3])}" + (f" (+{len(bul) - 3} more)" if len(bul) > 3 else "")]
                if bul else [])
            steps.append(_step(
                "inspect", f"Inspect {labels.get(k, k)} {'first' if act else 'also'}",
                f"{labels.get(k, k)} is {rs['direction']} of {hlabel}: {rs['why'][:200]} Trigger: "
                f"{'; '.join(trig)}.",
                f"dependency path {path} (systems graph depends_on); {'; '.join(trig)}",
                bulletins=bul[:3],
                done_match={"components": list(graph[k].get("components") or []),
                            "kinds": ("inspection", "test")}))

    # 7. record --------------------------------------------------------------
    steps.append(_step("record", "Record every step on the job",
                       "Record every step on this job with date, values and meaning before the next.",
                       "project rule: every step is recorded on the job"))

    # 6. done marking + ordering -----------------------------------------
    actions = list(job.get("actions") or [])
    for s in steps:
        hit = _done_by(s, actions)
        if hit:
            s["done"], s["done_ref"] = True, hit
    order = sorted(range(len(steps)), key=lambda i: (steps[i]["done"], _STAGE[steps[i]["stage"]], i))
    out = []
    for n, i in enumerate(order):
        s = steps[i]
        s.pop("_match", None)
        s.pop("stage", None)
        s["n"] = n
        out.append({k: s[k] for k in ("n", "title", "detail", "kind", "source", "done", "done_ref",
                                      "bulletins", "tools")})
    rationale.insert(0, f"Hypothesis {hypothesis_id} ({hlabel}): {len(hyp_rows)} bulletin relation(s) "
                        f"in the cross-reference; codes {', '.join(codes) or 'none named'}.")
    return {"vin": vin, "job_id": job.get("id"), "hypothesis_id": hypothesis_id,
            "steps": out, "rationale": "\n".join(rationale),
            "generated_at": datetime.now().isoformat(timespec="seconds")}


def _base_code(c: Any) -> str:
    return str(c or "").strip().upper().split("-")[0]


def _genuine_applied(rel: dict[str, Any], num: str, rkind: str) -> bool:
    """xref's already_applied may match a flash bulletin by a part-name word
    only; a flash counts as applied only when the action cites the number or
    records a flash."""
    reason = rel.get("reason") or ""
    if f"the action cites {num}" in reason:
        return True
    if rkind != "flash":
        return True
    return "flash/reprogram" in reason


def _controlling_module(vin: str, hsys: str, codes: list[str],
                        graph: dict[str, Any]) -> tuple[Optional[str], str]:
    mods = [m.get("code") for m in (((graph.get(hsys) or {}).get("technical") or {}).get("modules") or [])
            if m.get("code")]
    if mods:
        return mods[0], f"systems layer lists {mods[0]} for {hsys}"
    ctable = _load_code_table(vin)
    for c in codes:
        row = ctable.get(c)
        if not row:
            continue
        for key, mname in tsb_xref_bridge._module_systems(row.get("modules") or []):
            km = [m.get("code") for m in ((graph.get(key) or {}).get("technical") or {}).get("modules") or []]
            if km:
                return km[0], (f"{c} is reported by '{mname}' in the DTC history; systems layer: "
                               f"{key} -> {km[0]}")
    return None, ""


def _module_system(module: str, graph: dict[str, Any]) -> Optional[str]:
    for k, rec in graph.items():
        if any(m.get("code") == module for m in (rec.get("technical") or {}).get("modules") or []) \
                and k not in ("network",):
            return k
    return None


def _monitors_for(hsys: str) -> list[str]:
    try:
        from mes import systems as systems_mod
        return systems_mod.monitors_for_system(hsys)
    except Exception:  # noqa: BLE001
        return []


def _reads(text: str, h: dict[str, Any], codes: list[str], module: Optional[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    frag_codes = []
    for c in _CODE_RE.findall(text):
        if c not in frag_codes:
            frag_codes.append(c)
    if re.search(r"status\s+byte", text, re.I):
        cs = frag_codes or codes
        out.append(("status", f"{module + ' ' if module else ''}status bytes of {', '.join(cs)}"))
    if re.search(r"mode\s*\$?0?6", text, re.I):
        tids = [e for e in (h.get("evidence_for") or []) + (h.get("evidence_against") or [])
                if str(e.get("id") or "").lower().startswith("mode06-")]
        if tids:
            out.append(("mode06", "Mode 06 test IDs " + ", ".join(
                f"{str(e['id'])[7:]} ({_tid_label(e.get('label') or '')})" for e in tids)
                + " -- values vs limits"))
        else:
            out.append(("mode06", "Mode 06 test results for this system -- values vs limits"))
    if re.search(r"readiness|monitor\w*\s+reports?\s+complete", text, re.I):
        out.append(("readiness", "readiness (monitor complete / incomplete)"))
    if re.search(r"permanent", text, re.I):
        out.append(("permanent", "permanent DTCs"))
    m = re.search(r"(?:the\s+)?[\w-]+(?:\s+[\w-]+)?\s+DID\b[^,.;()]*(?:\([^)]*\))?", text)
    if m:
        out.append(("did", f"DID: '{m.group(0).strip()[:140]}'"))
    m = re.search(r"freeze\s+frame", text, re.I)
    if m:
        out.append(("freeze", "freeze frames of the codes above"))
    return out


def _tid_label(label: str) -> str:
    """'Mode 06 EVAP 0.090" leak: FAIL 404 ms vs min 3965 ms (car, 2026-10-13)'
    -> 'EVAP 0.090" leak, last: FAIL 404 ms vs min 3965 ms (car, 2026-10-13)'."""
    label = re.sub(r"^\s*Mode\s*\$?0?6\s*", "", label, flags=re.I)
    return label.replace(": ", ", last: ", 1)[:110]


def _next_items(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r"\(\s*[a-z]\s*\)\s*", text)
    items = [p.strip() for p in parts[1:] if p.strip()] if len(parts) > 1 else [text.strip()]
    return items


def _done_sentences(a: dict[str, Any]) -> list[str]:
    """Sentences of an action that record something done (forward-looking
    'next / until / whether' sentences dropped)."""
    return [s for s in re.split(r"(?<=[.;:])\s+", a.get("text") or "")
            if s and not _FORWARD_RE.search(s)]


def _done_by(step: dict[str, Any], actions: list[dict[str, Any]]) -> str:
    """The first recorded action that shows this step done, as a ref, or ''.
    Matching is per sentence and ignores forward-looking sentences, so a
    'Next: drive until the monitor completes' never marks a step done."""
    m = step.get("_match") or {}
    if not m:
        return ""
    kinds = m.get("kinds") or _DONE_KINDS
    cands = [(i, a, _done_sentences(a)) for i, a in enumerate(actions)
             if (a.get("kind") or "") in kinds]
    verb = _DONE_VERB.get(step.get("stage") or "")
    if m.get("cite"):
        refs = []
        for num in m["cite"]:
            hit = next(((i, a) for i, a, ss in cands
                        if any(tsb_xref_bridge.cites(x, num) and (verb is None or verb.search(x))
                               for x in ss)), None)
            if not hit:
                return ""
            refs.append(_action_ref(hit[1], hit[0]))
        return "; ".join(dict.fromkeys(refs))
    if m.get("regex") is not None:
        for i, a, ss in cands:
            if any(m["regex"].search(x) for x in ss):
                return _action_ref(a, i)
    if m.get("components"):
        for i, a, ss in cands:
            if any(re.search(rf"\b{re.escape(c)}\b", x, re.I) and _DONE_VERB["inspect"].search(x)
                   for c in m["components"] for x in ss):
                return _action_ref(a, i)
    return ""


_XREF_MEMO: dict[tuple, dict[str, Any]] = {}
_XREF_TTL_S = 30


def _page_xref(vin: str) -> dict[str, Any]:
    """xref for page renders, memoised on (vin, job-store mtime, 30 s
    bucket): a job edit re-keys at once; DTC/catalogue changes show within
    30 s. The API and Save always compute fresh."""
    import time
    try:
        from mes import jobs as jobs_mod
        mt = jobs_mod.store_path().stat().st_mtime
    except Exception:  # noqa: BLE001
        mt = 0.0
    key = (vin, mt, int(time.time() // _XREF_TTL_S), id(_load_xref))
    if key not in _XREF_MEMO:
        _XREF_MEMO.clear()
        _XREF_MEMO[key] = _load_xref(vin)
    return _XREF_MEMO[key]


def plans_for_job(vin: str, job: Optional[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Plan per non-deleted hypothesis of ``job``; one xref per call; never
    raises (the job page must still render)."""
    out: dict[str, dict[str, Any]] = {}
    if not job:
        return out
    try:
        view = _page_xref(vin)
    except Exception:  # noqa: BLE001
        view = {"bulletins": [], "by_hypothesis": {}}
    for h in job.get("hypotheses") or []:
        if h.get("deleted"):
            continue
        try:
            out[h["id"]] = plan(vin, job["id"], h["id"], xref_view=view, job=job)
        except Exception:  # noqa: BLE001
            continue
    return out


def as_text(p: dict[str, Any]) -> str:
    """The plan as a numbered next_test text (open steps; done ones listed)."""
    lines = [f"{s['n']}. {s['title']}: {s['detail']}" for s in p["steps"] if not s["done"]]
    done = [f"{s['n']}. {s['title']} ({s['done_ref']})" for s in p["steps"] if s["done"]]
    if done:
        lines.append("Already done: " + " | ".join(done))
    return "\n".join(lines)


def save_as_next_test(vin: str, job_id: str, hypothesis_id: str, *, by: str = "CUORE mechanic plan") -> dict[str, Any]:
    """Explicit user action only: write the generated plan into the
    hypothesis's next_test through the existing jobs edit function."""
    from . import jobs_bridge
    p = plan(vin, job_id, hypothesis_id)
    return jobs_bridge.edit_hypothesis(job_id, hypothesis_id, next_test=as_text(p), by=by)


__all__ = ["plan", "plans_for_job", "as_text", "save_as_next_test", "sections", "DRIVE_CYCLES", "KINDS"]
