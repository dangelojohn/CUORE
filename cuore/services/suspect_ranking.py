"""Ranked suspects and the best next test.

Suspects are scored from REAL evidence only: the TSB cross-reference
(``tsb_xref_bridge``), prior cases on this model (``cases_bridge``), the open
job's hypotheses, evidence, test results and recorded repairs, the shared-cause
finder (:mod:`cuore.services.common_cause`) and CUORE's own inspection and fuse
records. Every score is a list of reasons, each with a source id, a signed
weight and the one-line rationale of that weight. There are no probabilities
and no percentages: points from the table in
``cuore/data/diagnosis_weights.json`` ("heuristic, adjustable") map to a band
(High / Medium / Low).

The next test is the one that best splits the top suspects: a test touches
some suspects (a fail points at them, a pass rules them out). The expected
information gain over the bands (binary entropy of the split, weighted by
``band_prior``) is divided by the test's effort (``duration_min`` from the
mechanic test catalogue; "effort unknown" when CUORE has none).

Pure core: :func:`build`. Impure edge: :func:`gather`. Entry point:
:func:`diagnose` (cached on the inputs' mtimes).
"""

from __future__ import annotations

import math
import re
from datetime import datetime
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from . import cache, common_cause as cc

_STOP = {"with", "that", "this", "from", "have", "were", "been", "then", "than", "into", "when",
         "both", "each", "only", "also", "which", "their", "there", "these", "those", "does", "done",
         "check", "test", "fault", "code", "codes", "valve", "system"}
_BAD_CONDITIONS = {"loose", "chafed", "corroded", "water", "not_found"}


def _w(name: str, default: float = 0.0, section: str = "scoring") -> float:
    return float(cc.weight(section, name, default))


def _why(section: str, name: str) -> str:
    ent = (cc.load_weights().get(section) or {}).get(name)
    return ent.get("why", "") if isinstance(ent, dict) else ""


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]{4,}", (text or "").lower()) if t not in _STOP}


def cites(text: str, number: str) -> bool:
    try:
        from . import tsb_xref_bridge
        return tsb_xref_bridge.cites(text or "", number)
    except Exception:  # noqa: BLE001
        return False


def text_match(a: str, b: str) -> bool:
    """True when two short texts share at least two meaningful words and at
    least half of the shorter one's words. Deliberately strict."""
    ta, tb = _tokens(a), _tokens(b)
    if len(ta) < 2 or len(tb) < 2:
        return False
    common = ta & tb
    return len(common) >= 2 and len(common) >= 0.5 * min(len(ta), len(tb))


def band_of(points: float) -> str:
    if points >= _w("high_min", 5.0, "bands"):
        return "High"
    if points >= _w("medium_min", 2.0, "bands"):
        return "Medium"
    return "Low"


def _reason(source: str, source_id: str, text: str, name: str, points: float, section: str = "scoring",
            href: Optional[str] = None) -> dict[str, Any]:
    return {"source": source, "source_id": source_id, "text": text, "weight_name": name,
            "points": round(points, 2), "sign": "+" if points >= 0 else "-",
            "rationale": _why(section, name), "href": href}


# --- reasons ---------------------------------------------------------------------

def _tsb_reasons(bids: list[str], bulletins: dict[str, dict[str, Any]], by_repair: list[dict[str, Any]],
                 vin: str, neg: bool = True) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    linked = [bulletins[b] for b in bids if b in bulletins]
    if not linked:
        return out
    best = max(linked, key=lambda b: b.get("score", 0))
    sc = best.get("score", 0)
    if sc >= 5:
        name = "tsb_strong"
    elif sc >= 3:
        name = "tsb_moderate"
    elif sc >= 1:
        name = "tsb_weak"
    else:
        name = ""
    if name:
        first = next((r.get("reason") for r in best.get("relations", []) if r.get("type") == "code_match"),
                     None) or next((r.get("reason") for r in best.get("relations", [])
                                    if r.get("relation") in ("same_system", "dependent_system")), "")
        out.append(_reason("tsb", best["number"], f"Bulletin {best['number']} ({(best.get('title') or '')[:80]}) "
                           f"scores {sc} in the cross-reference: {str(first)[:160]}", name, _w(name),
                           href=best.get("href")))
    seen_rel: set[tuple] = set()
    for r in by_repair if neg else []:
        if r.get("bulletin") not in bids:
            continue
        rel = r.get("relation")
        if rel not in ("did_not_resolve", "ruled_out_by_inspection") or (r["bulletin"], rel) in seen_rel:
            continue
        seen_rel.add((r["bulletin"], rel))
        nm = "tsb_not_the_fix" if rel == "did_not_resolve" else "tsb_ruled_out"
        out.append(_reason("tsb", r.get("number") or r["bulletin"], str(r.get("reason"))[:200], nm, _w(nm)))
    return out


def _case_reasons(s: dict[str, Any], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    probe = f"{s['title']} {s['text'][:300]}"
    for c in cases:
        factor = _w("case_synthetic_factor", 0.5) if c.get("synthetic_from_logs") else 1.0
        cid = c.get("id") or "case"
        for fx in c.get("fixes_that_worked") or []:
            ft = fx if isinstance(fx, str) else str(fx.get("text") or fx)
            if text_match(probe, ft):
                out.append(_reason("case", cid, f"Prior case fix that worked: {ft[:120]}",
                                   "case_fix_worked", _w("case_fix_worked") * factor))
        for fx in c.get("fixes_that_did_not") or []:
            ft = fx if isinstance(fx, str) else str(fx.get("text") or fx)
            if text_match(probe, ft):
                out.append(_reason("case", cid, f"Prior case fix that did not work: {ft[:120]}",
                                   "case_fix_did_not", _w("case_fix_did_not") * factor))
        for h in c.get("hypotheses") or []:
            if text_match(probe, h.get("text") or ""):
                st = h.get("final_status")
                if st == "confirmed":
                    out.append(_reason("case", cid, f"Prior case confirmed: {(h.get('text') or '')[:120]}",
                                       "case_hyp_confirmed", _w("case_hyp_confirmed") * factor))
                elif st == "refuted":
                    out.append(_reason("case", cid, f"Prior case refuted: {(h.get('text') or '')[:120]}",
                                       "case_hyp_refuted", _w("case_hyp_refuted") * factor))
    return out


def _job_reasons(h: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    st = h.get("status")
    if st == "confirmed":
        out.append(_reason("job", h["id"], "Marked confirmed on the job.", "job_status_confirmed",
                           _w("job_status_confirmed")))
    elif st == "supported":
        out.append(_reason("job", h["id"], "Marked supported on the job.", "job_status_supported",
                           _w("job_status_supported")))
    kw = {k: v["value"] for k, v in (cc.load_weights().get("evidence_kind_weight") or {}).items()}
    for side, cap, mult, nm in (("evidence_for", _w("job_evidence_for_cap", 4.0), 1.0, "job_evidence_for_cap"),
                                ("evidence_against", _w("job_evidence_against_cap", 4.0),
                                 _w("job_evidence_against_mult", 1.5), "job_evidence_against_cap")):
        total = 0.0
        for ev in h.get(side) or []:
            wk = float(kw.get(ev.get("kind"), kw.get("default", 0.5)))
            pts = wk * mult
            if total + pts > cap:
                pts = max(0.0, cap - total)
            if pts <= 0:
                continue
            total += pts
            sign = 1 if side == "evidence_for" else -1
            lab = f"{'For' if sign > 0 else 'Against'} ({ev.get('kind') or 'evidence'}): {(ev.get('label') or ev.get('id') or '')[:140]}"
            out.append(_reason("job", f"{h['id']}/{ev.get('kind')}:{ev.get('id')}", lab,
                               "evidence_kind_weight", sign * pts, section="evidence_kind_weight"))
    return out


def _repair_reasons(s: dict[str, Any], actions: list[dict[str, Any]], code_seen: dict[str, str]
                    ) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    probe = f"{s['title']} {s['text'][:300]}"
    for a in actions:
        if a.get("kind") not in ("repair", "part") or a.get("retracted"):
            continue
        if not text_match(probe, a.get("text") or ""):
            continue
        when = str(a.get("effective_date") or a.get("at") or "")[:16].replace("T", " ")
        later = [c for c in s.get("codes") or [] if str(code_seen.get(c, "")) > when]
        if when and later:
            out.append(_reason("job", a.get("id") or "action",
                               f"Repair recorded {when[:10]} ('{(a.get('text') or '')[:90]}'); "
                               f"{', '.join(later[:3])} seen again after it.",
                               "repair_did_not_resolve", _w("repair_did_not_resolve")))
            break
    return out


def _cc_coverage_reasons(explains_n: int, of_n: int, who: str) -> list[dict[str, Any]]:
    if of_n and explains_n >= of_n:
        nm = "cc_explains_all"
    elif of_n and explains_n * 2 >= of_n:
        nm = "cc_explains_majority"
    elif explains_n >= 2:
        nm = "cc_explains_some"
    else:
        return []
    return [_reason("common_cause", who, f"Shared-cause finder: explains {explains_n} of {of_n} faults "
                    "with dependency data.", nm, _w(nm))]


# --- suspects --------------------------------------------------------------------

def _systems_for_member(kind: str, ids: list[str], elem_info: dict[str, dict[str, Any]]) -> list[str]:
    ks = (cc.load_weights().get("element_kind_systems") or {}).get(kind) or {}
    sysl = list(ks.get("value") or [])
    for i in ids:
        for s in (elem_info.get(i) or {}).get("part_of_systems") or []:
            if s not in sysl:
                sysl.append(s)
    return sysl


def build(inp: dict[str, Any]) -> dict[str, Any]:
    """Pure: inputs in, ranked suspects + next test out. See :func:`gather`."""
    hyps = [h for h in inp.get("hypotheses") or [] if not h.get("deleted") and h.get("status") != "refuted"]
    cc_res = inp.get("cc") or {"sets": [], "partial": [], "n_covered": 0}
    xref = inp.get("xref") or {}
    bulletins = {b["id"]: b for b in xref.get("bulletins") or [] if b.get("vehicle_scope") != "sibling_engine"}
    by_number = {}
    for b in bulletins.values():
        by_number[str(b["number"]).upper()] = b["id"]
    by_repair = xref.get("by_repair") or []
    elem_info = inp.get("element_info") or {}
    code_seen = inp.get("code_last_seen") or {}
    cases = inp.get("cases") or []
    label_of = inp.get("system_labels") or {}
    vin = inp.get("vin", "")
    of_n = cc_res.get("n_covered", 0)

    suspects: list[dict[str, Any]] = []
    cited_bulletins: set[str] = set()

    # classes for linking hypotheses to the shared-cause finder
    cand_cc: dict[str, dict[str, Any]] = {}
    for s in (cc_res.get("sets") or []) + (cc_res.get("partial") or []):
        for p, m in zip(s.get("paths") or [], s.get("members") or []):
            if m["level"] != "element":
                continue
            key = "|".join(m["ids"])
            cur = cand_cc.get(key)
            if cur is None or p["explains_n"] > cur["explains_n"]:
                cand_cc[key] = {"member": m, "explains_n": p["explains_n"], "path": p,
                                "in_full_set": s in (cc_res.get("sets") or [])}
    for key, c in cand_cc.items():
        c["systems"] = _systems_for_member(c["member"]["kind"], c["member"]["ids"], elem_info)

    for h in hyps:
        text = h.get("text") or ""
        title = h.get("_title") or text[:100]
        sysk = h.get("system") or ""
        s = {"id": f"hyp:{h['id']}", "kind": "hypothesis", "title": title, "text": text,
             "job_id": inp.get("job_id") or "", "updated_at": _hyp_latest(h),
             "system": sysk, "system_label": label_of.get(sysk, sysk), "codes": list(h.get("codes") or []),
             "status": h.get("status"), "next_test": h.get("next_test") or "", "systems": [sysk] if sysk else [],
             "test_labels": [], "href": f"/v/{vin}/job#hyp-{h['id']}", "ref_id": h["id"]}
        # Only explicit links count: the cross-reference's own hypothesis relations, a bulletin cited in
        # the hypothesis's evidence, or its number written in the hypothesis text. Sharing a DTC with a
        # bulletin does not make a hypothesis "the bulletin's remedy".
        bids: set[str] = set(e["bulletin"] for e in (xref.get("by_hypothesis") or {}).get(h["id"], []))
        evtext = " ".join(f"{e.get('id', '')} {e.get('label', '')}"
                          for e in (h.get("evidence_for") or []) + (h.get("evidence_against") or [])
                          if e.get("kind") == "bulletin")
        for bid, b in bulletins.items():
            num = str(b["number"])
            if bid in bids:
                continue
            if cites(text, num) or cites(evtext, num):
                bids.add(bid)
        s["_bids"] = sorted(bids)
        cited_bulletins |= bids
        reasons = _job_reasons(h) + _tsb_reasons(s["_bids"], bulletins, by_repair, vin)
        reasons += _case_reasons(s, cases) + _repair_reasons(s, inp.get("actions") or [], code_seen)
        # shared-cause coverage: the best finder class on this hypothesis's system
        link = [c for c in cand_cc.values() if sysk and sysk in c["systems"]]
        if link:
            best = max(link, key=lambda c: c["explains_n"])
            reasons += _cc_coverage_reasons(best["explains_n"], of_n, best["member"]["label"])
        s["reasons"] = reasons
        suspects.append(s)

    # shared-cause suspects (specific parts only)
    for key, c in sorted(cand_cc.items(), key=lambda kv: -kv[1]["explains_n"])[:6]:
        m = c["member"]
        codes = [f["id"][5:] for g in c["path"]["groups"] for f in g["faults"] if f["id"].startswith("code:")]
        sid = f"cc:{m['ids'][0]}"
        refs = []
        for i in m["ids"]:
            refs += (elem_info.get(i) or {}).get("tsb_refs") or []
        bids = sorted({by_number[r.upper()] for r in refs if r.upper() in by_number}
                      | {bid for num, bid in by_number.items() for r in refs if num and num in r.upper()})
        labels = list((cc.load_weights().get("element_kind_labels") or {}).get(m["kind"], {}).get("value") or [])
        s = {"id": sid, "kind": "shared_cause", "title": f"Shared cause: {m['label']}",
             "text": f"{m['label']} lies on the dependency path of {c['explains_n']} of {of_n} current faults "
                     f"({', '.join(codes[:6])}{'...' if len(codes) > 6 else ''}).",
             "system": c["systems"][0] if c["systems"] else "", "system_label": "", "codes": codes,
             "status": None, "next_test": "", "systems": c["systems"], "test_labels": labels,
             "href": None, "ref_id": m["ids"][0], "_bids": bids, "_member_ids": m["ids"]}
        reasons = _cc_coverage_reasons(c["explains_n"], of_n, m["label"])
        reasons += _tsb_reasons(bids, bulletins, by_repair, vin, neg=False)
        cited_bulletins |= set(bids)
        for rec in inp.get("inspections") or []:
            if rec.get("element") in m["ids"]:
                cond = rec.get("condition")
                if cond in _BAD_CONDITIONS:
                    reasons.append(_reason("inspection", str(rec.get("id") or rec.get("element")),
                                           f"Inspection of {rec.get('element')}: {cond}"
                                           f"{(' - ' + rec['note'][:80]) if rec.get('note') else ''}",
                                           "inspection_bad", _w("inspection_bad")))
                elif cond == "ok":
                    reasons.append(_reason("inspection", str(rec.get("id") or rec.get("element")),
                                           f"Inspection of {rec.get('element')}: OK", "inspection_ok",
                                           _w("inspection_ok")))
        for fi in inp.get("fuse_items") or []:
            if fi.get("id") in m["ids"] and fi.get("status") in ("red", "orange"):
                reasons.append(_reason("fuse_health", fi["id"], f"Fuse health {fi['status']}: "
                                       f"{'; '.join(map(str, (fi.get('reasons') or [])[:2]))[:140]}",
                                       "fuse_health_bad", _w("fuse_health_bad")))
        reasons += _repair_reasons(s, inp.get("actions") or [], code_seen)
        s["reasons"] = reasons
        suspects.append(s)

    # bulletin suspects: strong bulletins nobody has taken up yet
    taken = 0
    for b in xref.get("bulletins") or []:
        if taken >= 4:
            break
        if b.get("vehicle_scope") == "sibling_engine" or b["id"] in cited_bulletins:
            continue
        if b.get("score", 0) < 3 or b.get("applies") == "no" or "not_applicable" in (b.get("flags") or []):
            continue
        codes = sorted({r["code"] for r in b.get("relations", []) if r.get("type") == "code_match" and r.get("code")})
        if not codes:
            continue            # no current code of this car is in its list: not a suspect for this car
        if any(r.get("repair_kind") == "procedure" for r in b.get("relations", [])):
            continue            # a diagnostic procedure (e.g. SLVT) is a test, not a cause
        sysk = (b.get("systems") or [""])[0]
        s = {"id": f"tsb:{b['id']}", "kind": "bulletin", "title": f"{(b.get('title') or '')[:90]} (TSB {b['number']})",
             "text": b.get("title") or "", "system": sysk, "system_label": label_of.get(sysk, sysk),
             "codes": codes, "status": None, "next_test": "", "systems": list(b.get("systems") or []),
             "test_labels": [], "href": b.get("href"), "ref_id": b["id"], "_bids": [b["id"]]}
        s["reasons"] = _tsb_reasons([b["id"]], bulletins, by_repair, vin) + _case_reasons(s, cases)
        suspects.append(s)
        taken += 1

    for s in suspects:
        s["points"] = round(sum(r["points"] for r in s["reasons"]), 2)
        s["band"] = band_of(s["points"])
        s["has_evidence"] = bool(s["reasons"])
    order = {"hypothesis": 0, "shared_cause": 1, "bulletin": 2}
    suspects.sort(key=lambda s: (-s["points"], order[s["kind"]], s["title"]))
    for i, s in enumerate(suspects, 1):
        s["rank"] = i

    nt = pick_next_test(suspects, inp)
    ruled_out = [{"id": h["id"], "job_id": inp.get("job_id") or "", "title": h.get("_title") or (h.get("text") or "")[:100],
                  "system": h.get("system") or "", "system_label": label_of.get(h.get("system") or "", h.get("system") or ""),
                  "when": _hyp_latest(h), "href": f"/v/{vin}/job#hyp-{h['id']}"}
                 for h in inp.get("hypotheses") or [] if not h.get("deleted") and h.get("status") == "refuted"]
    ruled_out.sort(key=lambda r: r["when"], reverse=True)
    for s in suspects:
        _present(s, code_seen)
    return {"suspects": suspects, "next_test": nt, "groups": _group(suspects), "ruled_out": ruled_out}


# --- presentation (summary line, folded repeats, system groups) --------------------

_BAND_RANK = {"High": 0, "Medium": 1, "Low": 2}


def _hyp_latest(h: dict[str, Any]) -> str:
    """Newest dated thing on a hypothesis: evidence added, status change or last update."""
    cands = [str(h.get("updated_at") or "")]
    for a in h.get("audit") or []:
        if a.get("action") in ("evidence_added", "status", "created"):
            cands.append(str(a.get("at") or ""))
    return max(cands)


def _norm_reason(text: str) -> str:
    t = re.sub(r"[PCBU]\d{4}(-\d+)?", "CODE", text or "")
    return re.sub(r"\d+(\.\d+)?", "#", t).strip().lower()[:90]


def _present(s: dict[str, Any], code_seen: dict[str, str]) -> None:
    """Add the one-line summary, folded reason groups and newest-evidence date."""
    folded: dict[tuple, dict[str, Any]] = {}
    for r in sorted(s["reasons"], key=lambda r: -abs(r["points"])):
        key = (r["source"], r["points"] >= 0, r["weight_name"], _norm_reason(r["text"]))
        g = folded.get(key)
        if g is None:
            folded[key] = {**r, "count": 1, "total": r["points"]}
        else:
            g["count"] += 1
            g["total"] = round(g["total"] + r["points"], 2)
    s["reason_groups"] = list(folded.values())
    s["top_reason"] = (s["reason_groups"][0]["text"] if s["reason_groups"] else "")
    seen = [str(code_seen.get(c) or "") for c in s.get("codes") or []]
    s["latest_at"] = max([str(s.get("updated_at") or "")] + seen)[:19]


def _group(suspects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suspects grouped by system; groups ordered by best band, then newest evidence.
    Inside a group the order is the existing rank (points)."""
    groups: dict[str, dict[str, Any]] = {}
    for s in suspects:
        key = s.get("system") or "_other"
        g = groups.setdefault(key, {"key": key, "label": (s.get("system_label") or key.replace("_", " ").title())
                                    if key != "_other" else "Other / no single system", "suspects": []})
        g["suspects"].append(s)
    out = list(groups.values())
    for g in out:
        g["best_band"] = min((x["band"] for x in g["suspects"]), key=lambda b: _BAND_RANK[b])
        g["latest_at"] = max(x["latest_at"] for x in g["suspects"])
        g["n"] = len(g["suspects"])
        g["open"] = g["best_band"] == "High"
    out.sort(key=lambda g: (_BAND_RANK[g["best_band"]], _neg(g["latest_at"])))
    return out


def _neg(iso: str) -> tuple:
    """Sort key putting the newest ISO date first (and undated last)."""
    return tuple(-ord(c) for c in iso)


# --- next test --------------------------------------------------------------------

def _entropy(p: float) -> float:
    if p <= 0 or p >= 1:
        return 0.0
    return -(p * math.log2(p) + (1 - p) * math.log2(1 - p))


def _label_hit(label: str, s: dict[str, Any]) -> bool:
    lab = (label or "").lower().strip()
    if not lab:
        return False
    if any(lab == x.lower() for x in s.get("test_labels") or []):
        return True
    blob = f"{s['title']} {s['text'][:300]}".lower()
    if lab in blob:
        return True
    lt = _tokens(lab)
    if len(lt) < 2:
        return False
    return len(lt & _tokens(blob)) >= max(2, math.ceil(0.75 * len(lt)))


def _affinity(t: dict[str, Any], s: dict[str, Any], tree_hyps: list[dict[str, Any]]) -> int:
    probe = f"{s['title']} {s['text'][:300]}"
    for th in tree_hyps:
        if t["id"] in (th.get("tests") or []) and text_match(th.get("text") or "", probe):
            return 3
    for lab in list(t.get("supports_hypotheses") or []) + list(t.get("refutes_hypotheses") or []):
        if _label_hit(lab, s):
            return 2
    rel = [c.upper() for c in t.get("related_codes") or []]
    if rel and set(t.get("systems") or []) & set(s.get("systems") or []):
        if any(c.upper().startswith(r) for c in s.get("codes") or [] for r in rel):
            return 1
    return 0


def pick_next_test(suspects: list[dict[str, Any]], inp: dict[str, Any]) -> Optional[dict[str, Any]]:
    k = int(_w("top_suspects", 6, "next_test"))
    top = suspects[:k]
    if not top:
        return None
    prior = {b: float(v["value"]) for b, v in (cc.load_weights().get("band_prior") or {}).items()}
    wsum = sum(prior.get(s["band"], 1) for s in top)
    floor = _w("effort_floor_min", 5, "next_test")
    unknown = _w("unknown_effort_min", 15, "next_test")
    done = {tid for tid, r in (inp.get("test_results") or {}).items() if r in ("pass", "fail", "not_possible")}
    tree_hyps = inp.get("tree_hyps") or []
    vin = inp.get("vin", "")

    cands: list[dict[str, Any]] = []
    for t in inp.get("tests") or []:
        if t["id"] in done:
            continue
        aff = {s["id"]: _affinity(t, s, tree_hyps) for s in top}
        mx = max(aff.values(), default=0)
        if mx == 0:
            continue
        sel = [s for s in top if aff[s["id"]] == mx]
        cands.append({"id": t["id"], "name": t["name"], "kind": "catalogue", "minutes": t.get("duration_min"),
                      "tools": t.get("tools") or [], "car_state": t.get("car_state"),
                      "href": f"/v/{vin}/tests#test-{t['id']}", "sel": sel, "level": mx})
    for s in top:
        step = _first_step(s.get("next_test") or "")
        if step:
            cands.append({"id": f"next:{s['id']}", "name": step, "kind": "job_next_step", "minutes": None,
                          "tools": [], "car_state": None, "href": s.get("href"), "sel": [s], "level": 3})

    best, best_key = None, None
    for c in cands:
        p = sum(prior.get(s["band"], 1) for s in c["sel"]) / wsum if wsum else 0
        gain = _entropy(p)
        known = c["minutes"] is not None
        eff = (c["minutes"] if known else unknown) + floor
        c["gain"] = gain
        c["effort_known"] = known
        c["score"] = gain / eff
        c["p"] = p
        key = (round(c["score"], 6), c["level"], -(c["minutes"] if known else unknown), c["id"])
        if best_key is None or key > best_key:
            best, best_key = c, key
    if best is None:
        return None
    sel_ids = {s["id"] for s in best["sel"]}
    fail_pts = [s["title"] for s in best["sel"]]
    pass_pts = [s["title"] for s in top if s["id"] not in sel_ids]
    m = len(top)
    readonly = any("read-only" in str(x).lower() for x in best["tools"])
    effort = (f"{best['minutes']} min" if best["effort_known"] else "effort unknown")
    if len(best["sel"]) == m:
        why = (f"covers all {m} top suspects, so it cannot tell them apart; "
               f"{effort}{'; read-only' if readonly else ''}.")
        splits = False
    else:
        why = (f"separates the top {m} suspects into {len(best['sel'])} and {m - len(best['sel'])}: a pass rules out "
               f"{len(best['sel'])} of {m}, a fail points at them and makes the other {m - len(best['sel'])} "
               f"less likely; {effort}{'; read-only' if readonly else ''}.")
        splits = True
    return {"id": best["id"], "name": best["name"], "kind": best["kind"], "minutes": best["minutes"],
            "effort_known": best["effort_known"], "effort": effort, "read_only": readonly,
            "car_state": best["car_state"], "href": best["href"], "splits": splits,
            "if_pass_rules_out": [s["title"] for s in best["sel"]],
            "if_fail_rules_out": pass_pts,     # names kept for the API; read as "cleared" / "less likely" "touches": fail_pts, "of_suspects": m,
            "why": why, "alternatives": [{"id": c["id"], "name": c["name"], "minutes": c["minutes"]}
                                          for c in sorted(cands, key=lambda c: -c["score"])[1:4]]}


def _first_step(next_test: str) -> str:
    try:
        from . import job_direct
        return job_direct.first_step(next_test)
    except Exception:  # noqa: BLE001
        return (next_test or "").strip()[:160]


# --- the call -------------------------------------------------------------------------

def _short(text: str, n: int = 90) -> str:
    text = re.sub(r"\s+", " ", text or "").strip().rstrip(".")
    return text if len(text) <= n else text[:n - 1].rstrip().rstrip(".") + "..."


def _sentence(text: str) -> str:
    return text if text.endswith(".") else text + "."


def make_call(res: dict[str, Any], cc_res: dict[str, Any]) -> str:
    parts = []
    if res["suspects"]:
        t = res["suspects"][0]
        parts.append(f"Top suspect ({t['band']}): {_sentence(_short(t['title']))}")
    best = next((x for x in cc_res.get("sets") or [] if all(m["level"] == "element" for m in x["members"])), None)
    if best is None and cc_res.get("partial"):
        best = cc_res["partial"][0]
    if best is not None:
        names = " + ".join(_short(m["label"], 50) for m in best["members"])
        parts.append(f"Shared cause: {names} -- explains {best['explains_n']} of {best['of_n']} faults.")
    nt = res.get("next_test")
    if nt:
        mins = f", {nt['minutes']} min" if nt.get("effort_known") else ", effort unknown"
        parts.append(f"Next: {_short(nt['name'], 70)}{mins}.")
    return " ".join(parts) or "Nothing to rank yet: no current faults or hypotheses."


# --- gathering ------------------------------------------------------------------------------

def gather(vin: str) -> dict[str, Any]:
    from . import dossier_bridge, tsb_xref_bridge, cases_bridge, jobs_bridge, mes_bridge, job_direct
    from ..web import routes as web_routes
    view = dossier_bridge.build_view(vin, web_routes._dossier(vin), None)
    cc_res = cc.common_cause(vin)
    xref = tsb_xref_bridge.safe_xref(vin) or {}
    codes = [f["id"][5:] for f in cc_res.get("faults", []) if f["kind"] == "code"]
    try:
        cases = cases_bridge.match(vin, codes).get("matches") or []
    except Exception:  # noqa: BLE001
        cases = []
    job: dict[str, Any] = {}
    try:
        job = jobs_bridge.build_job_view(vin, None).get("job") or {}
    except Exception:  # noqa: BLE001
        job = {}
    hyps = [dict(h) for h in job.get("hypotheses") or []]
    labels: dict[str, str] = {}
    try:
        from . import systems_bridge
        labels = {k: v.get("label") or k for k, v in systems_bridge.systems().items()}
    except Exception:  # noqa: BLE001
        pass
    for h in hyps:
        try:
            h["_title"] = job_direct.hyp_title(h, labels)
        except Exception:  # noqa: BLE001
            h["_title"] = (h.get("text") or "")[:100]
    actions = [a for a in job.get("actions") or []]
    code_seen = {r["code"]: str(r.get("last_seen") or "") for r in view.get("codes") or []}

    elem_info: dict[str, dict[str, Any]] = {}
    try:
        from mes import electrical as el
        for s in (cc_res.get("sets") or []) + (cc_res.get("partial") or []):
            for m in s["members"]:
                for i in m["ids"]:
                    e = el.element(i)
                    if e:
                        elem_info[i] = {"tsb_refs": e.get("tsb_refs") or [],
                                        "part_of_systems": e.get("part_of_systems") or []}
    except Exception:  # noqa: BLE001
        pass
    try:
        from . import electrical_bridge
        inspections = electrical_bridge.list_inspections(vin)
    except Exception:  # noqa: BLE001
        inspections = []
    try:
        from . import fuse_health
        fuse_items = [i for i in fuse_health.health(vin).get("items") or [] if i.get("status") in ("red", "orange")]
    except Exception:  # noqa: BLE001
        fuse_items = []
    tests: list[dict[str, Any]] = []
    results: dict[str, str] = {}
    try:
        from mes import mechanic_tests
        tests = mechanic_tests.tests_for_marque(mes_bridge.marque_for_vin(vin))
        from ..live import checklists as checklist_store
        for sid, ent in (checklist_store.get(vin) or {}).items():
            if sid.startswith("test:") and ent.get("result"):
                results[sid[5:]] = ent["result"]
    except Exception:  # noqa: BLE001
        pass
    tree_hyps: list[dict[str, Any]] = []
    try:
        from mes import faulttree
        for t in faulttree.trees_for(codes):
            tree_hyps += [{"text": h.text, "tests": list(h.tests)} for h in t.hypotheses]
    except Exception:  # noqa: BLE001
        pass
    return {"vin": vin, "job_id": job.get("id") or "", "hypotheses": hyps, "actions": actions, "cc": cc_res, "xref": xref, "cases": cases,
            "element_info": elem_info, "inspections": inspections, "fuse_items": fuse_items,
            "tests": tests, "test_results": results, "tree_hyps": tree_hyps, "code_last_seen": code_seen,
            "system_labels": labels}


def compute(vin: str) -> dict[str, Any]:
    inp = gather(vin)
    res = build(inp)
    cc_res = inp["cc"]
    for s in res["suspects"]:
        s.pop("_bids", None)
        s.pop("_member_ids", None)
    res.update({
        "vin": vin,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "common_cause": cc_res,
        "call": make_call(res, cc_res),
        "table_note": "Bands come from the heuristic weights table (cuore/data/diagnosis_weights.json), "
                      "not from probabilities.",
        "weights": cc.weights_table(),
    })
    return res


def diagnose(vin: str) -> dict[str, Any]:
    """Full diagnosis view for one VIN, cached on the inputs' mtimes."""
    return cache.get_or_build(("diagnosis", vin) + cc.cache_key(vin), lambda: compute(vin))


__all__ = ["diagnose", "compute", "build", "gather", "pick_next_test", "band_of", "text_match"]
