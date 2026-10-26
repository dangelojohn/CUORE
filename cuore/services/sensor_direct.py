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
_GENERIC = {"sensor", "sensors", "front", "rear", "left", "right", "bank", "system", "driver", "with", "from",
            "that", "this", "when", "then", "than", "have", "only", "after", "before", "about", "heard", "area",
            "same", "time", "sound", "given", "while", "still", "stops", "some", "very", "also"}


def base_code(code: Any) -> str:
    return str(code or "").split("-")[0].upper()


def judged(s: dict[str, Any]) -> bool:
    return any(v.get("range") and v.get("in_range") is not None for v in s.get("values") or [])


def never_why(s: dict[str, Any]) -> str:
    """Why a grey sensor has no reading, from the sensor's own bus / readable fields."""
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


def reading_text(s: dict[str, Any], limit: int = 2) -> str:
    """The last reading(s) with units for the collapsed row, e.g. "6.07 bar" or "lambda 0.993"."""
    vals = [v for v in s.get("values") or [] if v.get("value") is not None]
    out = []
    for v in vals[:limit]:
        x, unit = v.get("value"), str(v.get("unit") or "").strip()
        if isinstance(x, dict):
            out.append(", ".join(f"{k} {_num(y)}" for k, y in x.items()) + (f" {unit}" if unit else ""))
        else:
            name = f"{v.get('label') or v.get('channel')}: " if len(vals) > 1 else ""
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
        return {"needs the grey cable": "Not read yet: needs the CAN-CH (grey) cable.",
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
        chip = CHIP["grey"]
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
    parts = [(n_cable, "need the grey cable"), (n_chan, "have no live channel in CUORE yet"),
             (n_ans, "did not answer last time")]
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
            "never": {"cable": n_cable, "no_channel": n_chan, "no_answer": n_ans, "total": len(never)},
            "links": links}
