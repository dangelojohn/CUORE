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

Sibling-engine analogues: catalogue rows with ``vehicle_scope ==
"sibling_engine"`` (bulletins / field reports from other models with the same
FCA GME-T4 2.0L engine) are never Stelvio evidence. They get a relation
"analogue" (a ``stelvio_equivalent`` that exists in the catalogue is linked in
its reason: "analogue of Stelvio <number>"), their score is halved (rounded
down; a code match keeps at least 1), ``field_report`` rows never score above
1 and carry relation "field_report". They sort after every Stelvio row, are
kept out of ``by_code`` / ``by_hypothesis`` / ``by_system`` / ``by_repair`` /
:func:`top` / :func:`for_system`, and are listed in ``analogues`` (all of them)
and ``analogues_by`` (``by_code`` / ``by_hypothesis`` / ``by_system``
sub-lists). Each Stelvio bulletin also carries ``analogues``: the analogue
rows sharing one of its DTCs or systems, or declared as its equivalent.

Loaders (``_load_*``) are module-level so tests can patch them.
"""

from __future__ import annotations

import functools
import re
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..data import load_tsb_catalogue
from . import systems_bridge

ANALOGUE_FACTOR = 0.5   # analogue score = floor(score * ANALOGUE_FACTOR)
FIELD_REPORT_CAP = 1
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
_REPAIR_KINDS = ("repair", "part")             # replace:<part> / inspect remedies
_FLASH_KINDS = ("repair", "part", "test")      # flash and procedure remedies
_INSPECT_KINDS = ("inspection", "test")        # ruled_out_by_inspection
#: ruled_out_by_inspection needs one of these in the same action that cites the bulletin.
#: Strongest first: the first one found is the phrase quoted in the reason.
_RULED_OUT_ORDER = tuple(re.compile(rf"\b{p}\b", re.I) for p in (
    r"ruled\s+out", r"not\s+the\s+cause", r"no\s+longer\s+possible", r"excluded", r"negative"))
#: A flash/software_update bulletin counts as applied only with one of these
#: words AND the same module named in the action (or the bulletin cited).
_FLASH_WORDS_RE = re.compile(
    r"\b(reflashed|reflash|flashed|flash|calibration\s+updated|software\s+updated|"
    r"PCM\s+update|ECM\s+update)\b", re.I)
_MODULE_RE = re.compile(r"\b(ECM|PCM|TCM|DTCM|BCM|ABS|ORC|IPC|RFHUB|DASM|EPS|SGW)\b", re.I)
_MODULE_SAME = {"PCM": "ECM", "DTCM": "TCM"}   # same physical module, two names
#: Words never matched alone as a component / procedure name.
_GENERIC_WORDS = {"valve", "sensor", "hose", "line", "module", "pump", "filter", "switch",
                  "test", "system", "part", "parts", "evap", "fuel", "engine", "detector",
                  "assembly", "kit", "seal", "software", "procedure", "routine", "check",
                  "witech", "witech 2"}
#: Interpretation clauses ("Meaning: ...", "Outcome: ...") are not what was
#: done; remedy matching only reads the text before them.
_CLAUSE_CUT_RE = re.compile(r"\b(Meaning|Outcome)\s*:", re.I)
#: Fallback for when the job store does not decorate actions with
#: ``effective_date`` (same rules as ``mes.jobs.effective_date``).
_ISO = r"(\d{4}-\d{2}-\d{2})"
_MONTHS = ("January|February|March|April|May|June|July|August|September|October|"
           "November|December")
_RE_REPAIR_ISO = re.compile(r"^\s*REPAIR HISTORY,\s*" + _ISO, re.I)
_RE_REPAIR_MONTH = re.compile(r"^\s*REPAIR HISTORY,\s*(?:" + _MONTHS + r")\s+\d{4}\b.*?\bdated\s+"
                              + _ISO, re.I | re.S)
_RE_LEADING = re.compile(r"^\s*" + _ISO + r"(?:[ T](\d{2}:\d{2}))?")
_RE_BETWEEN = re.compile(r"\bbetween\s+" + _ISO + r"\s+and\s+" + _ISO, re.I)
_FLASH_RE = re.compile(
    r"\b(re-?program\w*|re-?flash\w*|flash(?:ed|ing)?|software\s+update|"
    r"updat\w*\s+(?:the\s+)?(?:ECM|PCM|TCM)?\s*software)\b", re.I)


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
    return list(_number_patterns(number or ""))


@functools.lru_cache(maxsize=2048)
def _number_patterns(number: str) -> tuple[re.Pattern[str], ...]:
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
    return tuple(pats)


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


def _event_date(a: dict[str, Any]) -> tuple[str, bool, str]:
    """``(date, uncertain, range_note)`` of what an action records: the job
    store's ``effective_date`` when present, else the same text rules
    (REPAIR HISTORY forms, leading ISO date, "between A and B" -> the later
    date, uncertain), else the record time ``at``."""
    text = a.get("text") or ""
    rng = _RE_BETWEEN.search(text)
    note = f"between {rng.group(1)} and {rng.group(2)}" if rng else ""
    eff = a.get("effective_date")
    if eff:
        unc = bool(a.get("date_uncertain") or a.get("uncertain"))
        return str(eff), unc, note if unc else ""
    ev = (a.get("event_date") or "").strip()
    if ev:
        return ev, False, ""
    for rx in (_RE_REPAIR_ISO, _RE_REPAIR_MONTH):
        m = rx.match(text)
        if m:
            return m.group(1), False, ""
    m = _RE_LEADING.match(text)
    if m:
        return m.group(1) + (" " + m.group(2) if m.group(2) else ""), False, ""
    if rng:
        return max(rng.group(1), rng.group(2)), True, note
    return a.get("at") or "", False, ""


def _after(seen: str, event: str) -> bool:
    """``seen`` strictly after ``event``; a date-only event compares by day."""
    seen, event = _ts(seen), _ts(event)
    if not seen or not event:
        return False
    if len(event) <= 10:
        return seen[:10] > event[:10]
    return seen > event


@functools.lru_cache(maxsize=2048)
def _word_rx(term: str) -> re.Pattern[str]:
    """Whole word/phrase, case-insensitive; vapour/vapor folded."""
    words = [re.escape(w) for w in term.split()]
    body = r"[\s\-]+".join(words).replace("vapour", "vapou?r").replace("vapor", "vapou?r")
    return re.compile(rf"(?<![A-Za-z0-9])(?:{body})(?![A-Za-z0-9])", re.I)


def _cited_token(text: str, item: dict[str, Any], num: str) -> Optional[str]:
    """The exact text that cites the bulletin number or its nhtsa_id."""
    for n in (num, str(item.get("nhtsa_id") or "")):
        for p in number_patterns(n):
            m = p.search(text or "")
            if m:
                return m.group(0)
    return None


def _modules(text: str) -> set[str]:
    return {_MODULE_SAME.get(m.upper(), m.upper()) for m in _MODULE_RE.findall(text or "")}


def _remedy_terms(item: dict[str, Any], rkind: str, parts: list[str]) -> list[str]:
    """Component / procedure names (and part numbers) a replace / procedure
    remedy is matched on. Never a lone generic word."""
    ri = str(item.get("repair_implied") or "")
    arg = ri.partition(":")[2]
    comps = [str(c) for c in (item.get("components") or [])]
    if arg.strip():
        clean = re.sub(r"\([^)]*\)", " ", arg)
        clean = re.sub(r"\b(only|both|the|a|an|all|new)\b", " ", clean, flags=re.I)
        names = [n.strip() for n in re.split(r",|/|\band\b|\bor\b", clean, flags=re.I) if n.strip()]
    else:
        names = list(parts)
    terms: list[str] = []
    heads: list[str] = []   # head nouns go last: a specific name wins over 'canister'

    def add(t: str) -> None:
        t = re.sub(r"\s+", " ", t).strip(" -")
        if (len(t) >= 3 and t.lower() not in _GENERIC_WORDS
                and t.lower() not in [x.lower() for x in terms]):
            terms.append(t)

    for n in names:
        add(n)
        words = n.split()
        if rkind == "replace" and len(words) > 1 and len(words[-1]) >= 4:
            heads.append(words[-1])   # head noun ("canister"); generic heads ("valve") dropped by add()
        for c in comps:      # the catalogue component naming that part: long name, abbreviation, PN
            if not _word_rx(n).search(c):
                continue
            add(re.sub(r"\([^)]*\)", " ", c))
            for ab in re.findall(r"\(([^)]*)\)", c):
                add(ab)
            for pn in re.findall(r"\b(?=[A-Z0-9]*\d)(?=[A-Z0-9]*[A-Z])[A-Z0-9]{7,}\b", c):
                add(pn)
    for h in heads:
        add(h)
    if rkind == "procedure":
        for t in list(terms):
            for ac in re.findall(r"\b[A-Z]{3,}\b", t):
                add(ac)
        if "smoke" in (arg + " " + " ".join(comps)).lower():
            add("smoke test")
    return terms


def _match_action(a: dict[str, Any], item: dict[str, Any], num: str, rkind: str,
                  parts: list[str]) -> Optional[str]:
    """Why action ``a`` records this bulletin's remedy, quoting the exact
    token that matched, or None.

    * flash: kind repair|part|test; cites the number / nhtsa_id, or a flash
      word ("reflashed", "PCM update", ...) AND the bulletin's module.
    * replace:<part>: kind part|repair; the part number (exact token) or the
      component name as a whole word/phrase; else a citation.
    * procedure:<name>: kind repair|part|test; the procedure name / acronym
      or a citation.
    * inspect: kind part|repair citing the number.
    Only the text before a "Meaning:" / "Outcome:" clause is read."""
    akind = a.get("kind") or ""
    text = a.get("text") or ""
    m = _CLAUSE_CUT_RE.search(text)
    done = text[:m.start()] if m else text
    if rkind == "flash":
        if akind not in _FLASH_KINDS:
            return None
        tok = _cited_token(done, item, num)
        if tok:
            return f"the action cites {num} ('{tok}')"
        mods = _modules(" ".join(parts) + " " + str(item.get("remedy") or "") + " "
                        + str(item.get("title") or "")) or {"ECM"}
        for fm in _FLASH_WORDS_RE.finditer(done):
            for mm in _MODULE_RE.finditer(done):
                if _MODULE_SAME.get(mm.group(1).upper(), mm.group(1).upper()) in mods:
                    return (f"the action records a {mm.group(1).upper()} flash/reprogram "
                            f"('{fm.group(0)}' + '{mm.group(0)}')")
        return None
    if akind not in (_FLASH_KINDS if rkind == "procedure" else _REPAIR_KINDS):
        return None
    if rkind in ("replace", "procedure"):
        for t in _remedy_terms(item, rkind, parts):
            hit = _word_rx(t).search(done)
            if hit:
                return f"the action names '{hit.group(0)}'"
    tok = _cited_token(done, item, num)
    if tok:
        return f"the action cites {num} ('{tok}')"
    return None


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
            row["active"], row["active_why"], row["live"] = True, "the live link reads it now", True
        elif last_status in _ACTIVE_STATUSES and last and last == newest:
            row["active"], row["active_why"] = True, f"{last_status} in the newest scan on file ({last})"
        else:
            row.setdefault("active", False)
            row.setdefault("active_why", f"last seen {last or '?'} ({last_status}), not in the newest read")
    for base in live - set(out):
        out[base] = {"code": base, "dtc": base, "first_seen": "", "last_seen": "", "count": 0,
                     "status": "stored", "modules": [], "systems": _code_systems(base),
                     "active": True, "active_why": "the live link reads it now", "live": True}
    return out


def _eq_key(number: str) -> str:
    return re.sub(r"^CSN", "", re.sub(r"[^A-Z0-9]", "", (number or "").upper()))


def _rel(kind: str, reason: str, **extra: Any) -> dict[str, Any]:
    return {"type": kind, "reason": reason, **extra}


def xref(vin: str) -> dict[str, Any]:
    """The whole cross-reference for one VIN. See module docstring.

    Memoised for the rest of a GET request (one page asks once per code)."""
    from mes.catalog import scoped
    return scoped(("tsb_xref", (vin or "").strip().upper()), lambda: _xref(vin))


def _xref(vin: str) -> dict[str, Any]:
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

    own_by_eq = {_eq_key(i.get("number") or ""): i for i in cat.get("items") or []
                 if i.get("vehicle_scope") != "sibling_engine"}
    a_code: dict[str, list[dict[str, Any]]] = {}
    a_hyp: dict[str, list[dict[str, Any]]] = {}
    a_sys: dict[str, list[dict[str, Any]]] = {}
    shape: dict[str, dict[str, Any]] = {}   # bulletin id -> dtcs / systems / equivalent id
    bulletins: list[dict[str, Any]] = []
    s_code: dict[str, list[dict[str, Any]]] = {}
    s_repair: list[dict[str, Any]] = []
    s_hyp: dict[str, list[dict[str, Any]]] = {}
    s_sys: dict[str, list[dict[str, Any]]] = {}

    for item in cat.get("items") or []:
        num = item.get("number") or item["id"]
        is_an = item.get("vehicle_scope") == "sibling_engine"
        by_code, by_hypothesis, by_system, by_repair = (
            (a_code, a_hyp, a_sys, []) if is_an else (s_code, s_hyp, s_sys, s_repair))
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
        doubt = None if is_an else _other_model(item, model)    # analogues are other models by definition
        ydoubt = None if is_an else _year_doubt(item, year)
        eq_row = own_by_eq.get(_eq_key(str(item.get("stelvio_equivalent") or ""))) if is_an else None

        # applicability
        app_reason = {"yes": "catalogue marks it as applying to this car",
                      "no": "catalogue marks it as NOT applying to this car",
                      "vin_check": "applicability needs a VIN / dealer check"}[applies]
        app_rel = {"yes": "applies", "no": "not_applicable", "vin_check": "vin_check"}[applies]
        rels.append(_rel("applicability", app_reason, relation=app_rel, applies=applies))
        if is_an:
            sv = item.get("sibling_vehicle") or "another model with the same engine family"
            if item.get("kind") == "field_report":
                rels.append(_rel("analogue", f"field report (unverified forum/retailer claim) about {sv}; "
                                 f"same-engine anecdote, not a bulletin", relation="field_report"))
            else:
                why = f"analogue: same GME-T4 2.0L engine family, written for {sv}; not a Stelvio bulletin"
                if eq_row:
                    why += f"; analogue of Stelvio {eq_row.get('number') or eq_row['id']}"
                rels.append(_rel("analogue", why, relation="analogue",
                                 **({"stelvio_equivalent": eq_row["id"]} if eq_row else {})))
        if applies == "no":
            flags.append("not_applicable")
        if doubt:
            flags.append("other_model")
            rels.append(_rel("applicability", f"bulletin text points at another model: '{doubt}'",
                             relation="other_model_doubt"))
        if ydoubt:
            flags.append("year_doubt")
            rels.append(_rel("applicability", ydoubt, relation="model_year_doubt"))
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
            if side and item["id"] not in already and not is_an:
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
            if (a.get("kind") or "") in _INSPECT_KINDS:
                tok = _cited_token(atext, item, num)
                ro = next((m for rx in _RULED_OUT_ORDER for m in [rx.search(atext)] if m),
                          None) if tok else None
                if ro:
                    ruled_out.append(dict(a, why=f"cites '{tok}' and says '{ro.group(0)}'"))
                    continue
            hit = _match_action(a, item, num, rkind, parts)
            if hit:
                applied.append(dict(a, why=hit))
        for a in ruled_out:
            ev, unc, note = _event_date(a)
            reason = (f"{a['kind']} on {_ts(ev)}{' (uncertain: ' + note + ')' if unc else ''} "
                      f"(recorded {_ts(a['at'])[:10]}) {a['why']}: "
                      f"'{(a.get('text') or '')[:120]}'")
            rels.append(_rel("repair_interaction", reason, relation="ruled_out_by_inspection",
                             at=a["at"], event_date=ev, href=f"/v/{vin}/job/{a['job_id']}#actions"))
            by_repair.append({"bulletin": item["id"], "number": num, "relation": "ruled_out_by_inspection",
                              "reason": reason, "at": a["at"], "action": a.get("text", "")[:160]})
        system_codes = sorted(cc for cc, c in codes.items() if set(c["systems"]) & set(keys))
        for a in applied:
            ev, unc, note = _event_date(a)
            evs, rec = _ts(ev), _ts(a["at"])[:10]
            when = (f"{evs} (uncertain: {note or 'date range'}; the later date is used)"
                    if unc else evs)
            reason = (f"same remedy already done ({how}; {a['why']}): {a['kind']} on {when} "
                      f"(recorded {rec}) '{(a.get('text') or '')[:100]}'")
            rels.append(_rel("repair_interaction", reason, relation="already_applied", at=a["at"],
                             event_date=ev, href=f"/v/{vin}/job/{a['job_id']}#actions"))
            by_repair.append({"bulletin": item["id"], "number": num, "relation": "already_applied",
                              "reason": reason, "at": a["at"], "action": a.get("text", "")[:160]})
            what = re.search(r"'([^']*)'", a["why"])
            label = what.group(1) if what else "remedy"
            verb = {"part": "replaced", "repair": "repaired"}.get(a["kind"], "done")
            for cc in matched_codes or system_codes:
                c = codes[cc]
                if _after(c["last_seen"], ev):
                    seen = f"{cc} last seen {c['last_seen']}"
                elif c.get("live") and ev:
                    seen = f"{cc} active now ({c['active_why']}, after {evs})"
                else:
                    continue
                r2 = (f"{label} {verb} {when} (recorded {rec}); {seen} \u2192 did not resolve: "
                      f"evidence that this remedy is not the fix")
                rels.append(_rel("repair_interaction", r2, relation="did_not_resolve",
                                 code=cc, at=a["at"], event_date=ev))
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
        if is_an and score > 0:
            score = max(int(score * ANALOGUE_FACTOR), 1 if matched_codes else 0)
            parts_used = parts_used + [f"analogue x{ANALOGUE_FACTOR}"]
        if is_an and item.get("kind") == "field_report" and score > FIELD_REPORT_CAP:
            score = FIELD_REPORT_CAP
            parts_used = parts_used + ["field_report cap 1"]
        shape[item["id"]] = {"dtcs": {_base(d) for d in item.get("dtcs") or []}, "keys": set(keys),
                             "eq": eq_row["id"] if eq_row else None}
        bulletins.append({
            "id": item["id"], "number": num, "kind": item.get("kind"), "title": item.get("title"),
            "applies": applies, "systems": keys, "relations": rels, "flags": flags,
            "vehicle_scope": item.get("vehicle_scope") or "this_model", "analogues": [],
            "verified": bool(item.get("verified")),
            **({"sibling_vehicle": item.get("sibling_vehicle")} if is_an else {}),
            "score": score, "score_parts": parts_used,
            "href": f"/tsb?vin={vin}#tsb-row-{re.sub(r'[^A-Za-z0-9]+', '-', item['id']).strip('-')}",
        })

    def _rank(b: dict[str, Any]) -> tuple:
        an = b["vehicle_scope"] == "sibling_engine"   # Stelvio rows first; analogues: verified, more code hits first
        ncodes = sum(1 for r in b["relations"] if r["type"] == "code_match")
        return (an, -b["score"], (not b["verified"], -ncodes) if an else (0, 0), b["number"])

    bulletins.sort(key=_rank)
    order = {b["id"]: i for i, b in enumerate(bulletins)}
    score_of = {b["id"]: b["score"] for b in bulletins}
    analogues = [b for b in bulletins if b["vehicle_scope"] == "sibling_engine"]
    for b in bulletins:   # which analogues sit under which Stelvio bulletin
        if b["vehicle_scope"] == "sibling_engine":
            continue
        me, found = shape[b["id"]], []
        for a in analogues:
            sh, why = shape[a["id"]], []
            if sh["eq"] == b["id"]:
                why.append(f"analogue of Stelvio {b['number']}")
            if me["dtcs"] & sh["dtcs"]:
                why.append("same DTC " + ", ".join(sorted(me["dtcs"] & sh["dtcs"])))
            if me["keys"] & sh["keys"]:
                why.append("same system " + ", ".join(sorted(me["keys"] & sh["keys"])))
            if why:
                found.append(((sh["eq"] != b["id"], -a["score"], order[a["id"]]),
                              {"id": a["id"], "number": a["number"], "title": a["title"],
                               "sibling_vehicle": a.get("sibling_vehicle"), "score": a["score"],
                               "kind": a["kind"], "href": a["href"], "reason": "; ".join(why)}))
        found.sort(key=lambda t: t[0])
        b["analogues"] = [e for _k, e in found[:5]]
    by_code, by_hypothesis, by_system, by_repair = s_code, s_hyp, s_sys, s_repair
    for lst in (list(by_code.values()) + list(by_hypothesis.values()) + list(by_system.values())
                + list(a_code.values()) + list(a_hyp.values()) + list(a_sys.values())):
        for e in lst:
            e["score"] = score_of[e["bulletin"]]
        lst.sort(key=lambda e: order[e["bulletin"]])
    by_repair.sort(key=lambda e: (order[e["bulletin"]], e.get("at") or ""))
    return {"vin": vin, "job_id": (open_job or {}).get("id"), "weights": WEIGHTS,
            "bulletins": bulletins, "by_code": by_code, "by_repair": by_repair,
            "by_hypothesis": by_hypothesis, "by_system": by_system,
            "analogues": analogues,
            "analogues_by": {"by_code": a_code, "by_hypothesis": a_hyp, "by_system": a_sys},
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
    return [b for b in view.get("bulletins") or []
            if b["score"] > 0 and b.get("vehicle_scope") != "sibling_engine"][:n]


def top_analogues(view: dict[str, Any], n: int = 3) -> list[dict[str, Any]]:
    """The ``n`` best-scoring sibling-engine analogues with a non-zero score."""
    return [b for b in view.get("analogues") or [] if b["score"] > 0][:n]


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


__all__ = ["xref", "safe_xref", "top", "top_analogues", "for_system", "system_keys", "cites",
           "number_patterns", "WEIGHTS", "KNOWN_MODELS"]
