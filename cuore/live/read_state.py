"""One shared answer to "did this module read actually come back?".

Silence must never look clean: a module that did not answer, answered with
an adapter/bus error, answered with a negative response, or was never read
has NO code list to show -- an empty ``dtcs`` on such a result is absence of
data, not a clean read. Every surface that turns a module read into
something a technician sees asks :func:`is_read` / :func:`reason` here
instead of testing ``error``/``nrc``/``warning`` ad hoc.

Pure functions, no I/O.
"""

from __future__ import annotations

from typing import Any, Optional

READ = "read"
NOT_READ = "not_read"
PARTIAL = "partial"

_SILENT = "no answer from the module"


def reason(d: Optional[dict[str, Any]]) -> Optional[str]:
    """Why this module result is not a read, or ``None`` when it is one.

    ``None``/empty (never read) is a reason too: "never read"."""
    if not d:
        return "never read"
    if d.get("read_state") == NOT_READ and d.get("not_read_reason"):
        return str(d["not_read_reason"])
    if d.get("read_state") == PARTIAL and d.get("partial_reason"):
        return str(d["partial_reason"])
    if d.get("skipped"):
        return f"skipped: {d['skipped']}"
    if d.get("error"):
        e = str(d["error"])
        return e[9:].split(", do not treat")[0] if e.startswith("NOT READ: ") else f"adapter/bus error: {e}"
    if d.get("nrc"):
        return f"negative response {d['nrc']}"
    if _SILENT in str(d.get("warning") or ""):
        return "module did not answer"
    return None


def is_read(d: Optional[dict[str, Any]]) -> bool:
    return reason(d) is None


def banner(why: str) -> str:
    return f"NOT READ: {why}, do not treat as clean"


def stamp(d: dict[str, Any], mark_error: bool = True) -> dict[str, Any]:
    """Make a module result say its own state. A failed read gets
    ``read_state="not_read"``, a ``not_read`` banner and an ``error`` (so
    every consumer that already skips errored reads skips it too); counts
    that would otherwise read ``[]``/``0`` become ``None``. Returns ``d``."""
    why = reason(d)
    if why is None:
        d["read_state"] = READ
        return d
    d["read_state"] = NOT_READ
    d["not_read_reason"] = why
    d["not_read"] = banner(why)
    if mark_error:
        d.setdefault("error", d["not_read"])
    for k in ("active", "history", "tracked", "not_run_since_clear"):
        if k in d:
            d[k] = None
    return d


def unread_modules(observations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Modules whose NEWEST ``module_dtcs`` observation did not answer.

    ``observations`` in any order; each ``{"at", "data": {"ecu", ...}}``.
    Returns ``[{"ecu", "at", "why", "banner", "last_good"}]`` sorted by
    module, ``last_good`` being the date of the newest answered read of that
    module (shown only as "not read this session"), else ``None``."""
    newest: dict[str, dict[str, Any]] = {}
    good: dict[str, str] = {}
    for o in sorted(observations, key=lambda x: str(x.get("at") or "")):
        d = o.get("data") or {}
        ecu = str(d.get("ecu") or "").upper()
        if not ecu:
            continue
        newest[ecu] = o
        if is_read(d):
            good[ecu] = str(o.get("at") or "")
    out = []
    for ecu, o in sorted(newest.items()):
        why = reason(o.get("data") or {})
        if why:
            out.append({"ecu": ecu, "at": o.get("at"), "why": why,
                        "banner": banner(why), "last_good": good.get(ecu)})
    return out


# --- identity: one status per identifier -------------------------------------

ANSWERED = "answered"        # positive reply with data
REFUSED = "refused"          # negative response (the module answered: it refuses this one)
NO_ANSWER = "no_answer"      # silence
ERROR = "error"              # adapter / bus error, no usable reply
NOT_ASKED = "not_asked"      # stopped before this identifier (bus kept failing)


def field_status(f: dict[str, Any]) -> str:
    """Status of one identity field as :func:`uds.identity` records it."""
    if f.get("status") in (ANSWERED, REFUSED, NO_ANSWER, ERROR, NOT_ASKED):
        return str(f["status"])
    if f.get("error"):
        return ERROR
    if f.get("ascii") or f.get("bytes"):
        return ANSWERED
    return REFUSED if f.get("nrc") else NO_ANSWER


def identity_summary(fields: dict[str, Any]) -> dict[str, Any]:
    """Which identifiers answered, which were refused (and with what), which did
    not answer. Complete only when every identifier was answered or refused by
    the module and at least one answered; anything silent, errored or not asked
    makes the identity partial, and none answered makes it not read."""
    answered, refused, silent, errored, not_asked = [], {}, [], {}, []
    for did, f in fields.items():
        st = field_status(f)
        if st == ANSWERED:
            answered.append(did)
        elif st == REFUSED:
            nrc = f.get("nrc")
            refused[did] = ", ".join(str(v) for v in nrc.values()) if isinstance(nrc, dict) else str(nrc)
        elif st == NO_ANSWER:
            silent.append(did)
        elif st == ERROR:
            errored[did] = str(f.get("error"))
        else:
            not_asked.append(did)
    unanswered = silent + list(errored) + not_asked
    if not answered:
        state = NOT_READ
    elif unanswered:
        state = PARTIAL
    else:
        state = READ
    parts = [f"{len(answered)} of {len(fields)} answered"]
    if refused:
        parts.append("refused " + ", ".join(f"{k} ({v})" for k, v in refused.items()))
    if silent:
        parts.append("no answer " + ", ".join(silent))
    if errored:
        parts.append("bus error " + ", ".join(errored))
    if not_asked:
        parts.append("not asked " + ", ".join(not_asked))
    return {"state": state, "answered": answered, "refused": refused, "no_answer": silent,
            "error": errored, "not_asked": not_asked, "asked": len(fields),
            "line": f"identity {state}: " + "; ".join(parts)}


def stamp_identity(d: dict[str, Any]) -> dict[str, Any]:
    """Put the per-identifier summary on an identity result and say plainly
    whether it is complete, partial or not read. Returns ``d``."""
    s = identity_summary(d.get("fields") or {})
    d["summary"] = s
    d["read_state"] = s["state"]
    if s["state"] == PARTIAL:
        d["partial"] = True
        d["partial_reason"] = "PARTIAL " + s["line"]
    elif s["state"] == NOT_READ:
        d["not_read_reason"] = s["line"]
        d["not_read"] = banner(s["line"])
        d.setdefault("error", d["not_read"])
    return d
