"""What the sensors page tells the mechanic to do NOW, and the one-line state of every sensor.

Pure functions over the sensor rows of :mod:`cuore.services.sensor_health`, the open job's symptom texts and
the car's current codes (the same inputs the fuses page uses, :mod:`cuore.services.fuse_direct`). Nothing here
talks to the car and nothing is invented: a sensor is named in the call only because (a) it is faulty / not
answering in CUORE's own last reading, (b) a code is attached to it (a code on the job's list, or one CUORE
stored and a later scan no longer showed = "history, no live fault"), (c) it was never read, or (d) an open
symptom shares a word with the sensor's name.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from ..web import page_search

# row kinds, in the order a mechanic needs them
FAULT, CODE_LIVE, CODE_HISTORY, NEVER, OK_NOJUDGE, OK_JUDGED = (
    "fault", "code_live", "code_history", "never", "ok_nojudge", "ok_judged")
GROUPS = (("attention", "Needs attention", "Faults and sensors with a code on them"),
          ("never", "Never read", "No reading from this sensor yet"),
          ("ok", "OK", "Read, nothing wrong found"))
CHIP = {"red": "Dead / not responding", "orange": "Fault / out of range", "grey": "Not read yet",
        OK_JUDGED: "OK - in range", OK_NOJUDGE: "not judged"}
CONF_WORDS = {"SOURCED": "from a source", "INFERRED": "worked out, not checked", "GENERAL": "general knowledge",
              "UNKNOWN": "not known"}
CABLE = "needs the grey cable"
NO_CHANNEL = "no live channel in CUORE yet"
NO_ANSWER = "did not answer last time"
NO_VALID = "no valid reading"
SUSPECT = "suspect - check decoding"
_GENERIC = {"sensor", "sensors", "front", "rear", "left", "right", "bank", "system", "driver", "with", "from",
            "that", "this", "when", "then", "than", "have", "only", "after", "before", "about", "heard", "area",
            "same", "time", "sound", "given", "while", "still", "stops", "some", "very", "also"}


def base_code(code: Any) -> str:
    return str(code or "").split("-")[0].upper()


def judged(s: dict[str, Any]) -> bool:
    return any(v.get("range") and v.get("in_range") is not None for v in s.get("values") or [])


def never_why(s: dict[str, Any]) -> str:
    """Why a grey sensor has no reading, from the sensor's own bus / readable fields."""
    if s.get("no_valid"):
        return NO_VALID
    if s.get("suspect"):
        return SUSPECT
    if not s.get("readable", True):
        return CABLE if str(s.get("bus") or "").lower() in ("can_ch", "can-ch") else NO_CHANNEL
    return NO_ANSWER


def kind_of(s: dict[str, Any], job_bases: frozenset = frozenset()) -> str:
    st = s.get("status")
    if st in ("red", "orange"):
        return FAULT
    codes = s.get("codes") or []
    if any(c.get("state") != "superseded" for c in codes):
        return CODE_LIVE
    if codes:
        return CODE_HISTORY
    if st == "green":
        return OK_JUDGED if judged(s) else OK_NOJUDGE
    return NEVER


def group_of(kind: str) -> str:
    return "attention" if kind in (FAULT, CODE_LIVE, CODE_HISTORY) else "never" if kind == NEVER else "ok"


def code_chips(s: dict[str, Any]) -> list[dict[str, str]]:
    out = []
    for c in s.get("codes") or []:
        hist = c.get("state") == "superseded"
        out.append({"code": c.get("code") or "", "base": base_code(c.get("code")),
                    "text": "history, no live fault" if hist else (c.get("state") or "stored"),
                    "history": hist})
    return out


def fmt_time(t: Any) -> str:
    """ISO timestamp -> "Oct 25, 19:56" (the text unchanged when it is not an ISO time)."""
    from datetime import datetime
    raw = str(t or "").strip()
    if not raw:
        return ""
    try:
        d = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    return f"{d:%b} {d.day}, {d:%H:%M}"


def _read_when(s: dict[str, Any]) -> str:
    return fmt_time(s.get("last_read"))


def _num(v: Any) -> str:
    return f"{v:.4g}" if isinstance(v, float) else str(v)


_SUFFIX_UNIT = (("_mA", "mA"), ("_V", "V"), ("_pct", "%"), ("_C", "°C"), ("_bar", "bar"), ("_kPa", "kPa"))
_HIDE_PARTS = {"bitmap", "bits", "flags", "status_bits"}


def _unit(u: Any) -> str:
    u = str(u or "").strip()
    return {"C": "°C", "degC": "°C"}.get(u, u)


def human_label(name: Any) -> str:
    """A channel's raw key-like name -> words a mechanic reads ("throttle position b" -> "Throttle position B")."""
    n = str(name or "").strip().replace("_", " ")
    n = re.sub(r"o2 b(\d)s(\d)", r"O2 bank  sensor ", n, flags=re.I)
    n = re.sub(r"^(throttle position|accelerator pedal) ([a-f])$", lambda m: f"{m.group(1)}, sensor {m.group(2).upper()}", n)
    return n[:1].upper() + n[1:]


def split_parts(value: dict, outer_unit: Any = "") -> list[dict[str, Any]]:
    """One entry per part of a multi-part value: {key, label, value, unit, hidden}. Unit comes from the part's own
    key suffix (current_mA -> mA) or, for a sensor/bank key, from the channel's unit."""
    out = []
    for k, y in value.items():
        k = str(k)
        unit, base = "", k
        for suf, u in _SUFFIX_UNIT:
            if k.endswith(suf):
                unit, base = u, k[:-len(suf)]
                break
        m = re.match(r"^bank(\d+)_sensor(\d+)$", base)
        if m:
            label, unit = f"sensor {m.group(2)}", unit or _unit(outer_unit)
        else:
            label = base.replace("_", " ")
        out.append({"key": k, "label": label, "value": y, "unit": unit, "hidden": base in _HIDE_PARTS})
    return out


def reading_text(s: dict[str, Any], limit: int = 2) -> str:
    """The last valid reading(s) with units for the collapsed row: "6.07 bar" or "lambda 0.9932, current 0 mA".
    A value the module marked "not available" is not a reading and is left out (the row line says so)."""
    vals = [v for v in s.get("values") or [] if v.get("value") is not None and not v.get("invalid") and not v.get("suspect")]
    out = []
    for v in vals[:limit]:
        x, unit = v.get("value"), _unit(v.get("unit"))
        if isinstance(x, dict):
            parts = [p for p in split_parts(x, unit) if not p["hidden"]]
            txt = ", ".join(f"{p['label']} {_num(p['value'])}" + (f" {p['unit']}" if p["unit"] else "") for p in parts)
            if len(vals) > 1:
                txt = f"{human_label(v.get('label') or v.get('channel'))}: {txt}"
            out.append(txt)
        else:
            name = f"{human_label(v.get('label') or v.get('channel'))}: " if len(vals) > 1 else ""
            out.append(f"{name}{_num(x)}" + (f" {unit}" if unit else ""))
    return "; ".join(out) + (f" (+{len(vals) - limit} more)" if len(vals) > limit else "")


def one_line(s: dict[str, Any], kind: str) -> str:
    """ONE reason for the row. Details (the other reasons) live in the opened row."""
    reasons = [str(r) for r in s.get("reasons") or [] if r]
    if kind == FAULT:
        pick = next((r for r in reasons if "answered" not in r.lower() and "no range" not in r.lower()), "")
        return pick or reasons[0] if reasons else CHIP[s.get("status") or "orange"]
    if kind in (CODE_LIVE, CODE_HISTORY):
        c = (s.get("codes") or [{}])[0]
        n = len(s.get("codes") or [])
        extra = f" (+{n - 1} more)" if n > 1 else ""
        if kind == CODE_HISTORY:
            by = str(c.get("superseded_by") or "").strip()
            return f"{c.get('code')} was stored earlier{extra}; {by or 'a later scan did not show it'} - history, no live fault."
        return f"{c.get('code')} {c.get('state') or 'stored'}{extra}" + (f": {c['description']}" if c.get("description") else "") + "."
    if kind == NEVER:
        why = never_why(s)
        lead = next((r for r in s.get("reasons") or [] if str(r).startswith(("No valid reading for", "Suspect"))), "")
        return {NO_VALID: lead or "No valid reading: the module answered 'not available' (raw value in the details).",
                SUSPECT: lead or "Suspect - check decoding (reason in the details).",
                "needs the grey cable": "Not read yet: needs the CAN-CH (grey) cable.",
                NO_CHANNEL: "Not read yet: CUORE has no live channel for this sensor.",
                NO_ANSWER: "Asked, but it did not answer last time. Check all sensors again."}[why]
    when = _read_when(s)
    if kind == OK_JUDGED:
        return f"Read {when}; inside the normal range." if when else "Inside the normal range."
    return f"Read {when}; no normal range on record, so not judged." if when else "Read; no normal range on record."


def detail_reasons(s: dict[str, Any], line: str) -> list[str]:
    """The other reasons, minus the one shown on the row and minus statements the chip already makes."""
    out: list[str] = []
    for r in s.get("reasons") or []:
        r = str(r).strip()
        low = r.lower()
        if not r or r in out or r in line or low.startswith("no range on record"):
            continue
        if low.startswith("not readable:") and ("grey" in line or "live channel" in line):
            continue
        if low.startswith("code ") and "was stored earlier" in low and "history" in line:
            continue
        out.append(r)
    return out


def sensor_row(s: dict[str, Any], job_bases: frozenset = frozenset()) -> dict[str, Any]:
    kind = kind_of(s, job_bases)
    st = s.get("status") if s.get("status") in ("green", "orange", "red", "grey") else "grey"
    if kind == FAULT:
        chip = CHIP[st]
    elif kind == NEVER:
        chip = (NO_VALID.capitalize() if s.get("no_valid") else SUSPECT.capitalize() if s.get("suspect")
                else CHIP["grey"])
    elif kind in (OK_JUDGED, OK_NOJUDGE):
        chip = CHIP[kind]
    else:   # a code is attached: the chip still says what the reading itself showed
        chip = CHIP[OK_JUDGED if judged(s) else OK_NOJUDGE] if st == "green" else CHIP[st]
    line = one_line(s, kind)
    chips = code_chips(s)
    for c in chips:
        c["job"] = c["base"] in job_bases
    return {"kind": kind, "group": group_of(kind), "chip": chip, "line": line, "codes": chips,
            "extra": detail_reasons(s, line), "reading": reading_text(s),
            "read_when": _read_when(s), "read_iso": str(s.get("last_read") or ""),
            "area_chip": "Area: " + CONF_WORDS.get(s.get("location_confidence") or "UNKNOWN", "not known"),
            "never_why": never_why(s) if kind == NEVER else ""}


def _names(rows: list[dict[str, Any]], n: int = 3) -> tuple[list[dict[str, Any]], int]:
    return rows[:n], max(0, len(rows) - n)


def _tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z]{4,}", (text or "").lower()) if w not in _GENERIC]


def _alts(w: str) -> set[str]:
    out = {w}
    for grp in page_search.SENSOR_SYNONYMS:
        if w in grp:
            out |= set(grp)
    return out


def symptom_links(sensors: list[dict[str, Any]], symptoms: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """[{symptom, word, ids}] where an open symptom shares a whole word with a sensor's name or system."""
    words = {s["id"]: set(re.findall(r"[a-z0-9]+", f"{s.get('label') or ''} {s.get('system') or ''}".lower()))
             for s in sensors}
    out = []
    for sy in symptoms:
        text = sy.get("text") or ""
        for w in dict.fromkeys(_tokens(text)):
            ids = [s["id"] for s in sensors if words[s["id"]] & _alts(w)]
            if ids and len(ids) <= 6:
                out.append({"symptom": re.split(r"[.;]|\n", text, 1)[0][:70].strip(), "word": w, "ids": ids})
                break
    return out


def direct(sensors: list[dict[str, Any]], numbers: dict[str, int], codes: list[str], code_text: dict[str, str],
           symptoms: list[dict[str, Any]], cable_ok: Optional[bool] = None) -> dict[str, Any]:
    """The call. ``codes``: the job's current code list; ``symptoms``: open ones, newest first ``{text, at}``.
    Returns ``call`` (text), ``call_segs`` ({text, href} pieces, every sensor name links to its row),
    ``targets`` (go-to chips), ``why`` (full-sentence lines), ``rows`` ({sensor id: row}), ``counts``,
    ``never`` (breakdown), ``call_ids`` (rows to open)."""
    jb = frozenset(base_code(c) for c in codes)
    rows = {s["id"]: sensor_row(s, jb) for s in sensors}
    by = {s["id"]: s for s in sensors}

    def of(kind: str) -> list[dict[str, Any]]:
        return [s for s in sensors if rows[s["id"]]["kind"] == kind]

    def ref(s: dict[str, Any]) -> str:
        return f"#{numbers.get(s['id'], '?')} {s.get('label') or s['id']}"

    faults, live, hist = of(FAULT), of(CODE_LIVE), of(CODE_HISTORY)
    never = [s for s in sensors if s.get("status") not in ("green", "orange", "red")]
    segs: list[dict[str, str]] = []
    targets: list[dict[str, str]] = []
    why: list[str] = []
    call_ids: list[str] = []

    def put(text: str, href: str = "") -> None:
        segs.append({"text": text, "href": href})

    def names(group: list[dict[str, Any]], suffix: Any = None) -> None:
        shown, more = _names(group)
        for k, s in enumerate(shown):
            put(", " if k else "")
            put(ref(s), "#sensor-" + s["id"])
            if suffix:
                put(suffix(s))
            targets.append({"kind": rows[s["id"]]["kind"], "text": ref(s), "href": "#sensor-" + s["id"]})
            call_ids.append(s["id"])
        if more:
            put(f" and {more} more")

    def codes_of(s: dict[str, Any]) -> str:
        cs = rows[s["id"]]["codes"]
        return " (" + ", ".join(c["code"].split("-")[0] + (" history" if c["history"] else " live") for c in cs[:2]) + ")"

    def cable_of(s: dict[str, Any]) -> bool:
        return never_why(s) == CABLE

    faults.sort(key=lambda s: (s.get("status") != "red", not any(c["job"] for c in rows[s["id"]]["codes"]),
                               numbers.get(s["id"], 0)))
    if faults:
        put("Fault: ")
        names(faults)
        put(". ")
        why += [f"{ref(s)}: {rows[s['id']]['line']}" for s in faults]

    def job_first(group: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(group, key=lambda s: (not any(c["job"] for c in rows[s["id"]]["codes"]), numbers.get(s["id"], 0)))

    now = job_first([s for s in live + hist if s.get("readable", True)])
    if now:
        put("Read now: ")
        names(now, codes_of)
        put(".")
    later = job_first([s for s in live + hist if not s.get("readable", True)])
    if later:
        why.append("Code on these but CUORE can't read them yet: " + "; ".join(
            ref(s) + codes_of(s) + (" - needs the grey cable" if cable_of(s) else " - no live channel in CUORE yet")
            for s in later) + ".")
    for s in live + hist:
        for c in rows[s["id"]]["codes"]:
            why.append(f"{c['code']} on {ref(s)}: {c['text']}" + (" (it is on this job's code list)" if c["job"] else "")
                       + (f" - {code_text[c['base']]}" if code_text.get(c["base"]) else ""))
    links = symptom_links(sensors, symptoms)
    if links and not (faults or live or hist):
        lk = links[0]
        put(f"Open symptom \"{lk['symptom']}\" mentions {lk['word']}: ")
        names([by[i] for i in lk["ids"]])
        put(".")
    for lk in links:
        why.append(f"Symptom \"{lk['symptom']}\" shares the word \"{lk['word']}\" with: "
                   + ", ".join(ref(by[i]) for i in lk["ids"]) + " (linked by name only).")
    n_cable = sum(1 for s in never if never_why(s) == CABLE)
    n_chan = sum(1 for s in never if never_why(s) == NO_CHANNEL)
    n_ans = sum(1 for s in never if never_why(s) == NO_ANSWER)
    n_inv = sum(1 for s in never if never_why(s) == NO_VALID)
    parts = [(n_cable, "need the grey cable"), (n_chan, "have no live channel in CUORE yet"),
             (n_ans, "did not answer last time"), (n_inv, "returned no valid value"),
             (sum(1 for s in never if never_why(s) == SUSPECT), "are suspect - check decoding")]
    parts = [f"{n} {w}" for n, w in parts if n]
    if never:
        why.append(f"{len(never)} sensors have no reading yet: " + "; ".join(parts) + ".")
    if not segs:
        if sensors and (never or later):
            put(f"Nothing readable is flagged; {len(never)} sensor{'s' if len(never) != 1 else ''} not read yet "
                "(see Why these?).")
        else:
            put(f"All {len(sensors)} sensors read; nothing flagged." if sensors else "No sensors known for this car yet.")
    segs[-1]["text"] = segs[-1]["text"].rstrip() if not segs[-1]["href"] else segs[-1]["text"]
    counts = {g: sum(1 for r in rows.values() if r["group"] == g) for g, _, _ in GROUPS}
    return {"call": "".join(x["text"] for x in segs).strip(), "call_segs": segs, "targets": targets[:6],
            "why": why, "rows": rows, "counts": counts, "call_ids": call_ids,
            "never": {"cable": n_cable, "no_channel": n_chan, "no_answer": n_ans, "no_valid": n_inv, "total": len(never)},
            "links": links}


# ---------------------------------------------------------------------------------------------------------------
# The Sensors page's one-line rows, worst first (Bench-screen principles: one call, then rows ordered by priority
# then most recent, each opening to its detail). Pure functions; nothing here touches the car.
# ---------------------------------------------------------------------------------------------------------------

# the same validity words everywhere on the page
INVALID, SUSPECT_W, UNCONF, NOT_REC, OK_W = "Invalid", "Suspect", "Unconfirmed decoding", "Not recorded", "OK"
MARKS = {INVALID: "✕", SUSPECT_W: "!", UNCONF: "?", NOT_REC: "–", OK_W: "✓"}
TONE_CHIP = {"bad": "returned", "warn": "chronic", "ok": "ok", "plain": "plain"}
# (group id, title, open by default). Faults and codes first (hard evidence), then the ladder.
PGROUPS = (("fault", "Fault or code on it", True), ("invalid", "Invalid", True),
           ("suspect", "Suspect or unconfirmed decoding", True), ("crosscheck", "Cross-check disagrees", True),
           ("nodata", "No data", False), ("ok", "OK", False))
CC_WORDS = {"DISAGREE": "Disagrees", "UNCONFIRMED DECODING": "Unconfirmed decoding", "AGREE": "Agrees",
            "CONDITION NOT MET": "Condition not met", "NOT RECORDED": "Not recorded"}


def age_seconds(iso: Any, now: Any = None) -> Optional[float]:
    from datetime import datetime
    raw = str(iso or "").strip()
    if not raw:
        return None
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    n = now or datetime.now(t.tzinfo)
    return max(0.0, (n - t).total_seconds())


def age_text(sec: Optional[float]) -> str:
    """"just now" / "12 min ago" / "15 h ago" / "3 d ago"; "never" when there is no time."""
    if sec is None:
        return "never"
    if sec < 90:
        return "just now"
    if sec < 5400:
        return f"{round(sec / 60)} min ago"
    if sec < 172800:
        return f"{round(sec / 3600)} h ago"
    return f"{round(sec / 86400)} d ago"


def _base_key(key: Any) -> str:
    return re.split(r"[@.]", str(key or ""), 1)[0]


def _cc_val(side: dict[str, Any], unit: str) -> str:
    v = side.get("value")
    if v is None:
        return "not recorded"
    try:
        return f"{round(float(v), 2):g} {unit}".strip()
    except (TypeError, ValueError):
        return f"{v} {unit}".strip()


def crosscheck_links(sensors: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """{sensor id: [the cross-checks that have one of the sensor's channels on a side]}. Each link carries the
    status word, the readings of both sides and whether THIS sensor's side has a confirmed decoding."""
    by_ch: dict[str, list[str]] = {}
    for s in sensors:
        for ch in s.get("channels") or []:
            by_ch.setdefault(ch, []).append(s["id"])
    out: dict[str, list[dict[str, Any]]] = {s["id"]: [] for s in sensors}
    for r in results or []:
        sides = r.get("sides") or []
        unit = r.get("unit") or ""
        seen: set[str] = set()
        for i, side in enumerate(sides):
            for sid in by_ch.get(_base_key(side.get("key")), []):
                if sid in seen:
                    continue
                seen.add(sid)
                other = [x for j, x in enumerate(sides) if j != i]
                has_vals = r.get("status") in ("AGREE", "DISAGREE", "UNCONFIRMED DECODING")
                sus = str(r.get("suspects") or "")
                lab = str(side.get("label") or "")
                out[sid].append({
                    "title": r.get("title") or "", "status": r.get("status") or "", "word": CC_WORDS.get(r.get("status"), ""),
                    "would_be": r.get("would_be") or "", "this_confirmed": bool(side.get("confirmed")),
                    "line": (f"{lab} {_cc_val(side, unit)} vs " + ", ".join(f"{o.get('label')} {_cc_val(o, unit)}" for o in other)
                             if has_vals else str(r.get("reason") or "")),
                    "named": bool(sus and lab and lab in sus.split(";")[0]),
                    "suspects": sus, "condition": str(r.get("condition_text") or ""),
                    "tolerance": (r.get("tolerance") or {}).get("text", ""), "age": str(r.get("age_text") or "")})
    return out


def priority_rows(sensors: list[dict[str, Any]], rows: dict[str, dict[str, Any]], numbers: dict[str, int],
                  cc_results: list[dict[str, Any]], now: Any = None,
                  live: Optional[dict[str, dict[str, Any]]] = None) -> list[dict[str, Any]]:
    """One entry per sensor, already in page order: group (PGROUPS order), then the rank inside the group, then the
    most recent reading first. ``live``: {channel: {value, unit}} from the running live session, if any."""
    links = crosscheck_links(sensors, cc_results)
    live = live or {}
    gorder = {g: i for i, (g, _, _) in enumerate(PGROUPS)}
    out: list[dict[str, Any]] = []
    for s in sensors:
        r = rows[s["id"]]
        kind, lk = r["kind"], links.get(s["id"], [])
        dis = [x for x in lk if x["status"] == "DISAGREE"]
        unc = [x for x in lk if x["status"] == "UNCONFIRMED DECODING" and not x["this_confirmed"]]
        why, sub = r["line"], 0
        if kind in (FAULT, CODE_LIVE):
            group, word, tone = "fault", r["chip"], "bad" if s.get("status") == "red" else "warn"
            sub = {FAULT: 0, CODE_LIVE: 1}[kind] * 2 + (0 if s.get("status") == "red" else 1)
        elif s.get("no_valid"):
            group, word, tone, sub = "invalid", INVALID, "bad", 0
        elif s.get("suspect"):
            group, word, tone, sub = "suspect", SUSPECT_W, "warn", 0
        elif unc:
            group, word, tone = "suspect", UNCONF, "warn"
            sub = 1 if any(x["would_be"] == "DISAGREE" for x in unc) else 2
            why = ("Decoding not confirmed on this car: " + "; ".join(
                f"{x['title']} ({'values would disagree' if x['would_be'] == 'DISAGREE' else 'values agree'})" for x in unc[:2]) + ".")
        elif dis:
            group, word, tone = "crosscheck", SUSPECT_W, "warn"
            sub = 0 if any(x["named"] for x in dis) else 1
            why = "Cross-check disagrees: " + dis[0]["title"] + (f" - {dis[0]['suspects']}" if dis[0]["suspects"] else "") + "."
        elif kind == NEVER or (kind == CODE_HISTORY and s.get("status") != "green"):
            group, word, tone = "nodata", NOT_REC, "plain"
            why = "Not recorded: " + (s["reasons"][0] if s.get("stale") and s.get("reasons") else
                                      {CABLE: "needs the grey (CAN-CH) cable", NO_CHANNEL: "CUORE has no live channel for it yet",
                                       NO_ANSWER: "timeout - it did not answer last time"}.get(never_why(s), r["line"])).rstrip(".") + "."
        else:
            group, word, tone = "ok", OK_W, "ok"
        if group == "nodata":
            reading = {CABLE: "needs grey cable", NO_CHANNEL: "no channel", NO_ANSWER: "timeout"}.get(never_why(s), "no data")
            if s.get("stale"):
                reading = "old reading"
        elif group == "invalid":
            reading = "no valid value"
        else:
            reading = reading_text(s, 1) or ("no value" if not s.get("values") else "")
        live_hit = next((c for c in s.get("channels") or [] if c in live), "")
        if live_hit:
            lv = live[live_hit]
            try:
                reading = f"{round(float(lv.get('value')), 2):g} {_unit(lv.get('unit'))}".strip()
            except (TypeError, ValueError):
                live_hit = ""
        iso = str(s.get("last_read") or "")
        age_s = age_seconds(iso, now)
        out.append({"s": s, "r": r, "n": numbers.get(s["id"], 0), "group": group, "sub": sub, "word": word, "tone": tone,
                    "chip": TONE_CHIP[tone], "mark": MARKS.get(word, "!"), "reading": reading, "why": why,
                    "age_s": age_s, "age": "now" if live_hit else age_text(age_s),
                    "iso": iso, "live": bool(live_hit), "links": lk})
    out.sort(key=lambda x: (gorder[x["group"]], x["sub"], x["age_s"] if x["age_s"] is not None else 1e12, x["n"]))
    return out


def nodata_summary(rows_: list[dict[str, Any]]) -> str:
    """"7 no live channel in CUORE, 4 need the grey cable" for the folded No data group."""
    n = {"no channel": 0, "needs grey cable": 0, "timeout": 0}
    for x in rows_:
        if x["reading"] in n:
            n[x["reading"]] += 1
    parts = [(n["no channel"], "no live channel in CUORE"), (n["needs grey cable"], "need the grey cable"),
             (n["timeout"], "timed out last time")]
    return ", ".join(f"{k} {w}" for k, w in parts if k)


def page_call(prio: list[dict[str, Any]], cc: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The ONE line at the top: which sensor to look at first and why. ``sid`` links the row; ``why`` = lines for the
    "Why this?" fold; ``eid`` / ``elabel`` = element id and name for the "Electrical path for <sensor>" chip."""
    n = len(prio)
    why: list[str] = []
    top: Optional[dict[str, Any]] = None
    text = ""
    dis = sorted((x for x in prio if x["group"] == "crosscheck"), key=lambda x: x["sub"])
    if dis:   # a confirmed cross-check disagreement names the culprit sensor
        top = dis[0]
        lk = next(l for l in top["links"] if l["status"] == "DISAGREE")
        cond = lk["condition"] if lk["condition"] and not lk["condition"].startswith("none") else ""
        label = top["s"].get("label") or top["s"]["id"]
        text = (f"{label}: {lk['line']} disagree" + (f" at {cond}" if cond else "")
                + (f", allowed {lk['tolerance']}" if lk["tolerance"] else "") + " - "
                + ("check its connector and wiring" if top["s"].get("element_id") else "check its decoding and wiring") + ".")
        why.append(f"A confirmed cross-check disagrees: {lk['title']}. {lk['suspects'] or 'Either reading may be wrong.'}")
    else:
        first = next((x for x in prio if x["group"] in ("fault", "invalid", "suspect")), None)
        if first:
            top = first
            label = first["s"].get("label") or first["s"]["id"]
            reasons = [str(r) for r in first["s"].get("reasons") or [] if r]
            if first["group"] == "fault":
                text = f"{label}: {first['r']['line']}"
                why.append("A fault or a stored code on a sensor outranks decoding doubts.")
            elif first["group"] == "invalid":
                lead = next((r for r in reasons if r.startswith("No valid reading")), first["r"]["line"])
                text = f"{label}: Invalid - {lead.rstrip('.')}."
                why.append("Invalid = the module returned a value it marks 'not available', or an impossible one.")
            elif first["word"] == SUSPECT_W:
                lead = next((r for r in reasons if r.startswith("Suspect")), first["r"]["line"])
                body = re.sub(r"^Suspect - check decoding:\s*", "", lead).rstrip(".")
                head, sep, rest = body.partition(": ")
                if sep and head.lower().startswith(label.lower()[:10]):    # do not say the sensor's name twice
                    body = rest
                text = f"{label}: Suspect - " + body + "; check the decoding before trusting it."
                why.append("Suspect = a reading that disagrees with a related channel or looks decoded wrongly.")
            else:
                text = f"{label}: Unconfirmed decoding - " + first["why"].replace("Decoding not confirmed on this car: ", "").rstrip(".") + "."
                why.append("Unconfirmed decoding = the channel's formula is not yet confirmed on this car, so its number is not proof.")
    if top is not None:
        others = [x for x in prio if x["group"] in ("fault", "invalid", "suspect", "crosscheck") and x is not top]
        if others:
            why.append("Also needs a look: " + "; ".join(f"{x['s'].get('label') or x['s']['id']} ({x['word']})" for x in others[:6])
                       + (f"; and {len(others) - 6} more" if len(others) > 6 else "") + ".")
        why.append("Row order: faults and codes, invalid, suspect or unconfirmed decoding, cross-check disagreement, no data, OK. "
                   "Inside each group the newest reading is first.")
    nd = [x for x in prio if x["group"] == "nodata"]
    last = min((x["age_s"] for x in prio if x["age_s"] is not None), default=None)
    if top is None:
        read_n = n - len(nd)
        if not n:
            text = "No sensors known for this car yet."
        elif read_n:
            text = (f"All {read_n} sensors read plausibly" if not nd else
                    f"All {read_n} sensors that gave a reading read plausibly; {len(nd)} have no data")
            text += f" · last read {age_text(last)}." if last is not None else "."
        else:
            text = f"No sensor has a reading yet ({len(nd)} not recorded)."
        why.append(f"{sum(1 for x in prio if x['group'] == 'ok')} sensors are OK; none is invalid, suspect, unconfirmed or in disagreement.")
    if nd:
        why.append(f"{len(nd)} sensors have no data: {nodata_summary(nd)}.")
    if cc and (cc.get("counts") or {}).get("total"):
        c = cc["counts"]
        why.append(f"Cross-checks: {c.get('DISAGREE', 0)} disagree, {c.get('UNCONFIRMED DECODING', 0)} unconfirmed decoding, "
                   f"{c.get('AGREE', 0)} agree, {c.get('CONDITION NOT MET', 0)} condition not met, {c.get('NOT RECORDED', 0)} not recorded.")
    cand = ([top] if top else []) + prio
    ep = next((x for x in cand if x["s"].get("element_id")), None)
    return {"text": text, "sid": top["s"]["id"] if top else "", "why": why,
            "eid": ep["s"]["element_id"] if ep else "", "elabel": (ep["s"].get("label") or ep["s"]["id"]) if ep else "",
            "last_age": age_text(last)}
