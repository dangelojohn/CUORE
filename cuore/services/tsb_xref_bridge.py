"""Bulletin cross-reference engine: every TSB / recall / CSN / campaign in
``cuore/data/tsb_catalogue.json`` related, by explicit rules, to

* (a) each DTC the car has or had (``code_match``),
* (b) each repair / part / inspection already on a job (``repair_interaction``),
* (c) each open hypothesis on the open job (``hypothesis_interaction``),
* (d) the systems-dependency layer (``system_match``: the fault's own system
  and the systems one ``depends_on`` hop up/downstream of it).

Rules, not guesses: every relation carries a ``reason`` string a mechanic can
check against the catalogue row, the DTC history, the job ledger or the
systems graph. Nothing here writes anything -- suggested evidence is only
*offered* (a form on the page posts to the existing job evidence endpoint).

Complements, never replaces, the dossier's ``tsb_matches`` (``mes.knowledge``
via ``dossier_bridge``): that one is the curated per-code bulletin list; this
one is the whole catalogue scored against everything the car and the job
carry.

Catalogue rows may or may not carry the optional fields ``components``,
``symptoms``, ``repair_implied`` ("flash" | "replace:<part>" |
"procedure:<name>" | "inspect") and ``depends_on_systems``. When
``repair_implied`` is missing it is derived from the remedy text by the
keyword rules in :func:`_repair_implied` and the reason says so.

Score (small integer; each relation type counted once per bulletin):
explains 3, same_system 2, dependent_system 1, candidate 1,
already_applied + did_not_resolve 2 ("evidence that this remedy is not the
fix"), hypothesis supports 1; other-model / model-year doubt -2,
ruled_out_by_inspection -2; floor 0. ``applies == "no"`` keeps every
relation but the score is 0 and the bulletin is flagged ``not_applicable``.

Loaders (``_load_*``) are module-level so tests can patch them.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..data import load_tsb_catalogue
from . import systems_bridge

WEIGHTS = {"explains": 3, "same_system": 2, "dependent_system": 1, "candidate": 1,
           "not_the_fix": 2, "supports": 1, "applicability_doubt": -2,
           "ruled_out_by_inspection": -2}

#: Catalogue system tags that ``mes.systems.normalize_system`` does not
#: resolve on its own (catalogue vocabulary -> systems-graph key).
_CAT_SYSTEM_ALIASES = {
    "ecm": "engine_management", "pcm": "engine_management", "engine": "engine_management",
    "turbo": "air_intake_boost", "engine oil": "lubrication", "tcm": "transmission_driveline",
    "transmission": "transmission_driveline", "battery monitor": "electrical_supply",
}

#: Reporting-module text (MES/live) -> systems-graph key. Exact substrings.
_MODULE_SYSTEM = (
    (re.compile(r"\b(ECM|PCM|Engine|Injection)\b", re.I), "engine_management"),
    (re.compile(r"\b(TCM|DTCM|Gearbox)\b", re.I), "transmission_driveline"),
    (re.compile(r"\bBCM\b"), "body_comfort"),
)

#: Model names this marque family uses; a bulletin whose text says
#: "<other model> only" or "<this model> not listed" is flagged. Marque data,
#: kept here as one table so a port only edits this tuple.
KNOWN_MODELS = ("Giulia", "Stelvio", "Tonale", "Giulietta", "MiTo", "4C",
                "Ghibli", "Levante", "Quattroporte", "Grecale")

_ACTIVE_STATUSES = ("stored", "returned")
_REPAIR_KINDS = ("repair", "part")
_RULED_OUT_RE = re.compile(
    r"rul(?:ed|es|ing)\s+out|not\s+the\s+cause|does\s+not\s+apply|not\s+applicable|"
    r"excluded|no\s+fuel\s+(?:was\s+)?found|negative", re.I)
_FLASH_RE = re.compile(
    r"\b(re-?program\w*|re-?flash\w*|flash(?:ed|ing)?|software\s+update|"
    r"updat\w*\s+(?:the\s+)?(?:ECM|PCM|TCM)?\s*software)\b", re.I)
_GENERIC_HEADS = {"valve", "sensor", "hose", "line", "module", "pump", "filter", "switch"}


# --- loaders (patched by tests) -------------------------------------------


def _load_catalogue() -> dict[str, Any]:
    return load_tsb_catalogue()


def _load_dtc_history(vin: str) -> list[dict[str, Any]]:
    """``mes.analysis.dtc_history`` rows via ``mes_bridge.extract_dtcs``:
    dtc, first_seen, last_seen, sessions, occurrences, modules, severity."""
    from . import mes_bridge
    try:
        return list(mes_bridge.extract_dtcs(vin=vin).get("dtcs") or [])
    except Exception:  # noqa: BLE001 -- unknown VIN: no history, not a 500
        return []


def _load_live_active(vin: str) -> set[str]:
    try:
        from . import owner_events_bridge
        return set(owner_events_bridge._live_active_codes(vin))
    except Exception:  # noqa: BLE001
        return set()


def _load_jobs(vin: str) -> list[dict[str, Any]]:
    try:
        from mes import jobs as jobs_mod
        return list(jobs_mod.load(vin))
    except Exception:  # noqa: BLE001
        return []


def _load_identity(vin: str) -> dict[str, str]:
    """Module-identity numbers on file (``mes.ecm.installed``: live
    module_identity read + MES ECU info), as ``{label: value}``."""
    try:
        from mes import ecm as ecm_mod
        ident = ecm_mod.installed(vin) or {}
    except Exception:  # noqa: BLE001
        return {}
    out: dict[str, str] = {}
    for src in ("live", "mes"):
        for k, v in (ident.get(src) or {}).items():
            if k in ("read_at", "file", "timestamp", "ecu", "software_version"):
                continue
            if isinstance(v, str) and len(v.strip()) >= 6:
                out[f"{src}.{k}"] = v.strip()
    return out


# --- small helpers -----------------------------------------------------------


def _base(code: str) -> str:
    return (code or "").strip().upper().split("-")[0]


def _ts(s: Optional[str]) -> str:
    return (s or "").replace("T", " ")[:16]


def system_keys(tags: list[str]) -> list[str]:
    """Catalogue system tags -> systems-graph keys (unresolvable tags dropped)."""
    from mes import systems as systems_mod
    out: list[str] = []
    for t in tags or []:
        key = systems_mod.normalize_system(t) or _CAT_SYSTEM_ALIASES.get(str(t).strip().lower())
        if key and key not in out:
            out.append(key)
    return out


def _labels() -> dict[str, str]:
    return {k: v["label"] for k, v in systems_bridge.systems().items()}


def _code_systems(code: str, description: str = "") -> list[str]:
    return [e["system"] for e in systems_bridge.systems_for_code(code, description)
            if e["role"] == "primary" and e["system"] != "UNKNOWN"]


def _module_systems(modules: list[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for m in modules or []:
        for rx, key in _MODULE_SYSTEM:
            if rx.search(m or "") and key not in [k for k, _ in out]:
                out.append((key, m))
    return out


def number_patterns(number: str) -> list[re.Pattern[str]]:
    """Regexes that find a bulletin number in free text: each '/'-separated
    alternative, revision suffix dropped, separators optional between
    characters ("18-030-17" matches "18 030 17"/"1803017"; "18V636" matches
    "18V-636"). A leading "STAR"/"TSB" word is optional."""
    pats: list[re.Pattern[str]] = []
    for alt in re.split(r"\s*/\s*", number or ""):
        alt = re.split(r"\s*\bREV\b\.?", alt, maxsplit=1, flags=re.I)[0].strip()
        alt = re.sub(r"^(STAR|TSB)\s+", "", alt, flags=re.I)
        chars = re.sub(r"[^A-Za-z0-9]", "", alt)
        if len(chars) < 4:
            continue
        body = r"[\s\-.]?".join(re.escape(c) for c in chars)
        pats.append(re.compile(r"(?<![A-Za-z0-9])" + body + r"(?![A-Za-z0-9])", re.I))
    return pats


def cites(text: str, number: str) -> bool:
    return any(p.search(text or "") for p in number_patterns(number))


def _snippet(text: str, m: re.Match[str], width: int = 40) -> str:
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("..." if a else "") + text[a:b].strip() + ("..." if b < len(text) else "")


def _repair_implied(item: dict[str, Any]) -> tuple[str, list[str], str]:
    """``(kind, parts, how)``: kind is flash|replace|procedure|inspect; parts
    the components it touches; how says whether it came from the catalogue
    field or the remedy-text rule."""
    comps = [str(c) for c in (item.get("components") or []) if str(c).strip()]
    ri = str(item.get("repair_implied") or "").strip()
    if ri:
        kind, _, arg = ri.partition(":")
        kind = kind.strip().lower()
        kind = {"software_update": "flash", "reflash": "flash", "reprogram": "flash"}.get(kind, kind)
        parts = comps or ([arg.strip()] if arg.strip() else [])
        return kind, parts, f"catalogue repair_implied '{ri}'"
    remedy = str(item.get("remedy") or "")
    title = str(item.get("title") or "")
    if _FLASH_RE.search(remedy) or title.lower().startswith("flash"):
        mods = [m for m in ("ECM", "PCM", "TCM") if re.search(rf"\b{m}\b", remedy + " " + title)]
        return "flash", comps or mods or ["ECM"], "remedy text names a reprogram/flash"
    m = re.search(r"\breplace\b([^.;]*)", remedy, re.I)
    if m:
        phrase = re.sub(r"\b(both|the|a|an|all)\b", " ", m.group(1), flags=re.I)
        parts = [p.strip() for p in re.split(r",|\band\b|\bor\b", phrase) if p.strip()]
        return "replace", comps or parts, f"remedy text says 'replace{m.group(1)[:60]}'"
    if re.search(r"\b(run|perform)\b.*\b(test|procedure|routine)\b", remedy, re.I):
        return "procedure", comps, "remedy text names a test/procedure"
    return "inspect", comps, "no flash/replace/procedure wording in the remedy"


def _part_rx(part: str) -> Optional[re.Pattern[str]]:
    """Case-insensitive match for a part name/number; vapour/vapor folded.
    Falls back to the head noun ("canister") unless it is generic ("valve")."""
    p = part.strip()
    if not p:
        return None
    alts = [re.escape(p)]
    words = p.split()
    if len(words) > 1 and words[-1].lower() not in _GENERIC_HEADS and len(words[-1]) >= 4:
        alts.append(re.escape(words[-1]))
    body = "|".join(a.replace("vapour", "vapou?r").replace("vapor", "vapou?r") for a in alts)
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.I)


def _other_model(item: dict[str, Any], model: str) -> Optional[str]:
    """Quoted text when the bulletin says it is for another model."""
    text = " ".join(str(item.get(k) or "") for k in ("title", "summary", "applies_to",
                                                     "cuore_relevance"))
    if not model:
        return None
    m = re.search(rf"\b{re.escape(model)}\b[^.]{{0,15}}\bnot\s+listed\b", text, re.I)
    if m:
        return _snippet(text, m, 30)
    for other in KNOWN_MODELS:
        if other.lower() == model.lower():
            continue
        m = re.search(rf"\b{re.escape(other)}[\s-]+only\b", text, re.I)
        if m:
            return _snippet(text, m, 30)
    return None


def _year_doubt(item: dict[str, Any], year: Any) -> Optional[str]:
    text = str(item.get("applies_to") or "")
    if not text or not year:
        return None
    try:
        y = int(year)
    except (TypeError, ValueError):
        return None
    ranges = [(int(a), int(b)) for a, b in re.findall(r"\b(20\d\d)\s*(?:-|–|to)\s*(20\d\d)\b", text)]
    singles = {int(s) for s in re.findall(r"\b(20\d\d)\b", text)}
    if not singles or y in singles or any(a <= y <= b for a, b in ranges):
        return None
    return f"applies_to names model years {sorted(singles)}, not {y}: '{text[:90]}'"


def _code_links(vin: str, base: str) -> dict[str, str]:
    fam = "other"
    try:
        from . import dossier_bridge as _db
        if base in _db._EVAP_CODES:
            fam = "evap"
        else:
            f = _db._generic_family_for(base)
            fam = (f[0] if f else "other").lower()
    except Exception:  # noqa: BLE001
        pass
    return {"code_href": f"/v/{vin}/code/{base}", "dossier_href": f"/v/{vin}/dossier#cluster-{fam}"}


# --- the engine ----------------------------------------------------------------


def _code_table(vin: str) -> dict[str, dict[str, Any]]:
    """base code -> {code, first_seen, last_seen, count, status, active,
    active_why, modules, systems}."""
    hist = _load_dtc_history(vin)
    live = {_base(c) for c in _load_live_active(vin)}
    newest = max((_ts(r.get("last_seen")) for r in hist), default="")
    out: dict[str, dict[str, Any]] = {}
    for r in hist:
        base = _base(r.get("dtc") or r.get("code") or "")
        if not base:
            continue
        occ = r.get("occurrences") or []
        last_status = (occ[-1].get("status") if occ else None) or (
            (r.get("statuses_seen") or r.get("statuses") or ["stored"])[-1])
        last = _ts(r.get("last_seen"))
        row = out.get(base)
        if row is None or last > row["last_seen"]:
            desc = (r.get("descriptions") or [""])[0]
            out[base] = row = {
                "code": base, "dtc": r.get("dtc"), "first_seen": _ts(r.get("first_seen")),
                "last_seen": last, "count": int(r.get("sessions") or len(occ) or 1),
                "status": last_status, "modules": list(r.get("modules") or []),
                "systems": _code_systems(base, desc),
            }
        if base in live:
            row["active"], row["active_why"] = True, "the live link reads it now"
        elif last_status in _ACTIVE_STATUSES and last and last == newest:
            row["active"], row["active_why"] = True, f"{last_status} in the newest scan on file ({last})"
        else:
            row.setdefault("active", False)
            row.setdefault("active_why", f"last seen {last or '?'} ({last_status}), not in the newest read")
    for base in live - set(out):
        out[base] = {"code": base, "dtc": base, "first_seen": "", "last_seen": "", "count": 0,
                     "status": "stored", "modules": [], "systems": _code_systems(base),
                     "active": True, "active_why": "the live link reads it now"}
    return out


def _rel(kind: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "reason": reason, **extra}


def xref(vin: str) -> dict[str, Any]:
    """The whole cross-reference for one VIN. See module docstring."""
    vin = (vin or "").strip().upper()
    cat = _load_catalogue()
    vehicle = cat.get("vehicle") or {}
    model, year = str(vehicle.get("model") or ""), vehicle.get("year")
    labels = _labels()
    codes = _code_table(vin)
    jobs = _load_jobs(vin)
    open_job = next((j for j in reversed(jobs) if j.get("status") != "closed"), None)
    actions = [dict(a, job_id=j["id"]) for j in jobs for a in (j.get("actions") or [])]
    hyps = [h for h in ((open_job or {}).get("hypotheses") or []) if not h.get("deleted")]
    identity = _load_identity(vin)

    active_systems: dict[str, list[str]] = {}   # system -> active codes
    module_systems: dict[str, list[str]] = {}   # system -> active codes (via reporting module)
    for c in codes.values():
        if not c["active"]:
            continue
        for s in c["systems"]:
            active_systems.setdefault(s, []).append(c["code"])
        for s, _m in _module_systems(c["modules"]):
            module_systems.setdefault(s, []).append(c["code"])

    bulletins: list[dict[str, Any]] = []
    by_code: dict[str, list[dict[str, Any]]] = {}
    by_repair: list[dict[str, Any]] = []
    by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    by_system: dict[str, list[dict[str, Any]]] = {}

    for item in cat.get("items") or []:
        num = item.get("number") or item["id"]
        keys = system_keys(item.get("systems") or [])
        key_src = {k: "catalogue systems tag" for k in keys}
        for comp in item.get("components") or []:   # exact component name -> its system
            for k, rec in systems_bridge.systems().items():
                if any(str(comp).strip().lower() == c.lower() for c in rec.get("components") or []):
                    if k not in keys:
                        keys.append(k)
                        key_src[k] = f"component '{comp}' is part of this system"
        dep_keys = system_keys(item.get("depends_on_systems") or [])
        rels: list[dict[str, Any]] = []
        flags: list[str] = []
        applies = item.get("applies") or "vin_check"
        doubt = _other_model(item, model)
        ydoubt = _year_doubt(item, year)

        # applicability
        app_reason = {"yes": "catalogue marks it as applying to this car",
                      "no": "catalogue marks it as NOT applying to this car",
                      "vin_check": "applicability needs a VIN / dealer check"}[applies]
        rels.append(_rel("applicability", app_reason, applies=applies))
        if applies == "no":
            flags.append("not_applicable")
        if doubt:
            flags.append("other_model")
            rels.append(_rel("applicability", f"bulletin text points at another model: '{doubt}'"))
        if ydoubt:
            flags.append("year_doubt")
            rels.append(_rel("applicability", ydoubt))
        btext = " ".join(str(item.get(k) or "") for k in ("title", "summary", "remedy",
                                                          "condition", "applies_to"))
        for label, val in identity.items():
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(val)}(?![A-Za-z0-9])", btext, re.I):
                rels.append(_rel("identity_match",
                                 f"bulletin names {val}, which this car's module identity "
                                 f"reports ({label})", value=val))

        # (a) code match
        matched_codes: list[str] = []
        for dtc in item.get("dtcs") or []:
            c = codes.get(_base(dtc))
            if not c:
                continue
            matched_codes.append(c["code"])
            kind = "explains" if c["active"] else "historical"
            reason = (f"{c['code']} is in the bulletin's DTC list and is "
                      f"{'active: ' + c['active_why'] if c['active'] else 'historical: ' + c['active_why']}"
                      f"; first seen {c['first_seen'] or '?'}, last seen {c['last_seen'] or '?'}, "
                      f"{c['count']} session(s)")
            r = _rel("code_match", reason, relation=kind, code=c["code"], **_code_links(vin, c["code"]))
            rels.append(r)
            by_code.setdefault(c["code"], []).append({"bulletin": item["id"], "number": num,
                                                      "relation": kind, "reason": reason})

        # (d) system match
        for k in keys:
            if k in active_systems:
                rels.append(_rel("system_match",
                                 f"bulletin targets {labels.get(k, k)} ({key_src.get(k)}), the "
                                 f"system of active code(s) {', '.join(sorted(set(active_systems[k])))}",
                                 relation="same_system", system=k))
        hit_dep: set[str] = set()
        for s, s_codes in active_systems.items():
            if s in keys:
                continue
            for rs in systems_bridge.related_systems(s, depth=1):
                if rs["system"] in keys and rs["system"] not in hit_dep:
                    hit_dep.add(rs["system"])
                    arrow = " -> ".join(labels.get(p, p) for p in rs["path"])
                    rels.append(_rel("system_match",
                                     f"bulletin targets {labels.get(rs['system'], rs['system'])}, "
                                     f"{rs['direction']} of {labels.get(s, s)} (active "
                                     f"{', '.join(sorted(set(s_codes)))}); path {arrow}: {rs['why'][:140]}",
                                     relation="dependent_system", system=rs["system"],
                                     path=rs["path"]))
            if s in dep_keys and s not in hit_dep:
                hit_dep.add(s)
                rels.append(_rel("system_match",
                                 f"bulletin declares a dependency on {labels.get(s, s)}, the system "
                                 f"of active {', '.join(sorted(set(s_codes)))}",
                                 relation="dependent_system", system=s))
        for s, s_codes in module_systems.items():
            if s in keys and s not in active_systems and s not in hit_dep:
                hit_dep.add(s)
                rels.append(_rel("system_match",
                                 f"active {', '.join(sorted(set(s_codes)))} is set by the "
                                 f"{labels.get(s, s)} module, which this bulletin targets",
                                 relation="dependent_system", system=s))

        # (c) hypotheses (before repair: 'touches' needs it)
        hyp_rels: list[dict[str, Any]] = []
        for h in hyps:
            htext = h.get("text") or ""
            cited = cites(htext, num)
            hsys = h.get("system") or ""
            already = {(e or {}).get("id") for e in (h.get("evidence_for") or []) + (h.get("evidence_against") or [])}
            if cited and (applies == "no" or doubt):
                why = "the catalogue marks it not applicable" if applies == "no" else f"its text says '{doubt}'"
                rel = "weakens"
                reason = f"hypothesis cites {num}, but {why}"
                side = "against"
            elif applies == "yes" and not doubt and hsys and hsys in keys:
                rel, side = "supports", "for"
                reason = (f"remedy targets {labels.get(hsys, hsys)}, the hypothesis's system, "
                          f"and the catalogue marks it as applying" + (" (hypothesis cites it)" if cited else ""))
            elif cited or (hsys and hsys in keys):
                rel, side = "neutral", None
                reason = ((f"hypothesis cites {num}; " if cited else
                           f"bulletin targets {labels.get(hsys, hsys)}, the hypothesis's system; ")
                          + app_reason)
            else:
                continue
            suggestion = None
            if side and item["id"] not in already:
                suggestion = {"side": side, "kind": "bulletin", "ref_id": item["id"],
                              "label": f"Bulletin {num}: {reason}"[:300],
                              "action": f"/v/{vin}/job/{open_job['id']}/hypotheses/{h['id']}/evidence"}
            hr = _rel("hypothesis_interaction", reason, relation=rel, hyp_id=h["id"],
                      job_id=open_job["id"], hyp_text=htext[:140],
                      href=f"/v/{vin}/job/{open_job['id']}#hyp-{h['id']}", suggestion=suggestion)
            hyp_rels.append(hr)
            by_hypothesis.setdefault(h["id"], []).append({"bulletin": item["id"], "number": num,
                                                         "relation": rel, "reason": reason,
                                                         "suggestion": suggestion})
        rels.extend(hyp_rels)

        # (b) repairs / parts / inspections
        touches = bool(matched_codes) or any(r["type"] == "system_match" for r in rels) or any(
            r.get("relation") != "neutral" or cites((r.get("hyp_text") or ""), num) for r in hyp_rels)
        rkind, parts, how = _repair_implied(item)
        applied: list[dict[str, Any]] = []
        ruled_out: list[dict[str, Any]] = []
        for a in actions:
            atext = a.get("text") or ""
            akind = a.get("kind") or ""
            cited_here = cites(atext, num)
            if akind in ("inspection", "test") and cited_here and _RULED_OUT_RE.search(atext):
                ruled_out.append(a)
                continue
            if akind not in _REPAIR_KINDS:
                continue
            hit = None
            if cited_here:
                hit = f"the action cites {num}"
            elif rkind == "flash" and _FLASH_RE.search(atext):
                mods = [p for p in parts if re.search(rf"\b{re.escape(p)}\b", atext, re.I)]
                if mods or not any(re.search(rf"\b{m}\b", atext) for m in ("ECM", "PCM", "TCM")):
                    hit = f"the action records a {'/'.join(mods) or 'module'} flash/reprogram"
            else:
                for p in parts:
                    rx = _part_rx(p)
                    if rx and rx.search(atext):
                        hit = f"the action names '{p}'"
                        break
            if hit:
                applied.append(dict(a, why=hit))
        for a in ruled_out:
            reason = (f"{a['kind']} on {_ts(a['at'])} cites {num} and rules it out: "
                      f"'{(a.get('text') or '')[:120]}'")
            rels.append(_rel("repair_interaction", reason, relation="ruled_out_by_inspection",
                             at=a["at"], href=f"/v/{vin}/job/{a['job_id']}#actions"))
            by_repair.append({"bulletin": item["id"], "number": num, "relation": "ruled_out_by_inspection",
                              "reason": reason, "at": a["at"], "action": a.get("text", "")[:160]})
        for a in applied:
            at = _ts(a["at"])
            reason = (f"same remedy already done ({how}; {a['why']}): {a['kind']} on {at} "
                      f"'{(a.get('text') or '')[:100]}'")
            rels.append(_rel("repair_interaction", reason, relation="already_applied", at=a["at"],
                             href=f"/v/{vin}/job/{a['job_id']}#actions"))
            by_repair.append({"bulletin": item["id"], "number": num, "relation": "already_applied",
                              "reason": reason, "at": a["at"], "action": a.get("text", "")[:160]})
            check_codes = matched_codes or sorted({c for k in keys for c in active_systems.get(k, [])})
            for cc in check_codes:
                c = codes[cc]
                if (c["last_seen"] and c["last_seen"] > at) or c["active"]:
                    when = f"last seen {c['last_seen']}" if c["last_seen"] > at else c["active_why"]
                    r2 = (f"{cc} came back after the {at} {a['kind']} ({when}): evidence that this "
                          f"remedy is not the fix")
                    rels.append(_rel("repair_interaction", r2, relation="did_not_resolve",
                                     code=cc, at=a["at"]))
                    by_repair.append({"bulletin": item["id"], "number": num,
                                      "relation": "did_not_resolve", "reason": r2, "at": a["at"],
                                      "action": a.get("text", "")[:160]})
                    break
        if touches and not applied and not ruled_out and applies != "no" and rkind != "none":
            rels.append(_rel("repair_interaction",
                             f"remedy ({rkind}{': ' + ', '.join(parts) if parts else ''}; {how}) "
                             f"not recorded on any job for this VIN",
                             relation="candidate", repair_kind=rkind, parts=parts))

        # by_system: what each system is touched by (independent of codes)
        for k in keys:
            by_system.setdefault(k, []).append({"bulletin": item["id"], "number": num,
                                                "relation": "targets",
                                                "reason": f"bulletin lists {labels.get(k, k)}"})
            for rs in systems_bridge.related_systems(k, depth=1):
                arrow = " -> ".join(labels.get(p, p) for p in reversed(rs["path"]))
                by_system.setdefault(rs["system"], []).append({
                    "bulletin": item["id"], "number": num, "relation": "dependency",
                    "reason": f"bulletin lists {labels.get(k, k)}, "
                              f"{'which depends on' if rs['direction'] == 'upstream' else 'a dependency of'} "
                              f"this system (path {arrow})"})

        score, parts_used = _score(rels, flags, ruled_out)
        bulletins.append({
            "id": item["id"], "number": num, "kind": item.get("kind"), "title": item.get("title"),
            "applies": applies, "systems": keys, "relations": rels, "flags": flags,
            "score": score, "score_parts": parts_used,
            "href": f"/tsb?vin={vin}#tsb-row-{re.sub(r'[^A-Za-z0-9]+', '-', item['id']).strip('-')}",
        })

    bulletins.sort(key=lambda b: (-b["score"], b["number"]))
    order = {b["id"]: i for i, b in enumerate(bulletins)}
    score_of = {b["id"]: b["score"] for b in bulletins}
    for lst in list(by_code.values()) + list(by_hypothesis.values()) + list(by_system.values()):
        for e in lst:
            e["score"] = score_of[e["bulletin"]]
        lst.sort(key=lambda e: order[e["bulletin"]])
    by_repair.sort(key=lambda e: (order[e["bulletin"]], e.get("at") or ""))
    return {"vin": vin, "job_id": (open_job or {}).get("id"), "weights": WEIGHTS,
            "bulletins": bulletins, "by_code": by_code, "by_repair": by_repair,
            "by_hypothesis": by_hypothesis, "by_system": by_system,
            "hypotheses": {h["id"]: (h.get("text") or "")[:140] for h in hyps}}


def _score(rels: list[dict[str, Any]], flags: list[str],
           ruled_out: list[dict[str, Any]]) -> tuple[int, list[str]]:
    rel = {r.get("relation") for r in rels}
    parts: list[str] = []
    if "explains" in rel:
        parts.append("explains")
    if "same_system" in rel:
        parts.append("same_system")
    if "dependent_system" in rel:
        parts.append("dependent_system")
    if "candidate" in rel:
        parts.append("candidate")
    if "already_applied" in rel and "did_not_resolve" in rel:
        parts.append("not_the_fix")
    if "supports" in rel:
        parts.append("supports")
    if "other_model" in flags or "year_doubt" in flags:
        parts.append("applicability_doubt")
    if ruled_out:
        parts.append("ruled_out_by_inspection")
    if "not_applicable" in flags:
        return 0, parts + ["not_applicable -> 0"]
    return max(0, sum(WEIGHTS[p] for p in parts)), parts


def top(view: dict[str, Any], n: int = 5) -> list[dict[str, Any]]:
    """The ``n`` best-scoring bulletins with a non-zero score."""
    return [b for b in view.get("bulletins") or [] if b["score"] > 0][:n]


def for_system(view: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Bulletins touching ``key`` or one of its dependencies, best first,
    one row per bulletin (its first reason)."""
    seen: set[str] = set()
    out = []
    for e in view.get("by_system", {}).get(key) or []:
        if e["bulletin"] in seen:
            continue
        seen.add(e["bulletin"])
        out.append(e)
    return out


def safe_xref(vin: str) -> Optional[dict[str, Any]]:
    """:func:`xref`, or ``None`` on any error -- pages degrade, never 500."""
    try:
        return xref(vin)
    except Exception:  # noqa: BLE001
        return None


__all__ = ["xref", "safe_xref", "top", "for_system", "system_keys", "cites",
           "number_patterns", "WEIGHTS", "KNOWN_MODELS"]
