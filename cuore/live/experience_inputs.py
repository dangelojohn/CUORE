"""Driver/mechanic-added "Others' experience" links -- the owner's own
complaint, verbatim: *"I need to add Others' experiences input data from
driver and mechanic and identify which of the two found this external data;
I am unable to modify these fields."*

``mes.experience`` (bridged by :mod:`cuore.services.experience_bridge`) is a
read-only, hand-curated table someone else maintains. This module is the
other half: what a driver or mechanic finds *today* -- a YouTube video, a
forum thread, a photo of a sticker, a one-line note -- gets typed in here,
attributed to whoever found it, and shows up on the same card right away.
Nothing here is curated or re-verified by a human editor before it renders;
it is attested at confidence ``"reported"``, same posture as
:mod:`cuore.live.owner_events` and ``mes.symptoms`` -- a person's claim, not
a fact about the car.

Append-only JSONL under ``cuore.live.config.state_dir()``
(``CUORE_STATE_DIR``), one file, ``experience_inputs.jsonl``, four record
shapes distinguished by ``op``, the same fold-in-append-order convention
:mod:`cuore.live.owner_events` uses:

* ``input`` -- {op, id, vin, scope: {code, family, system, job}, url,
  url_norm, title, kind, found_by: {role, name}, found_at, note, rating,
  verified: {status, at, method}, confidence="reported"}
* ``input_edit`` -- {op, id, at, by, changes: {field: {from, to}}} --
  never rewrites the original ``input`` row.
* ``delete`` / ``restore`` -- {op, id, at} -- soft delete + undo, folded in
  append order exactly like :mod:`cuore.live.owner_events`.
* ``flag`` -- {op, id, target_id, at, by, note, flag_kind} -- "Flag as
  wrong/outdated" on *any* link id, curated or user-added (curated rows
  live in ``mes.experience``, not here, so a flag is the only write this
  module ever makes against one of their ids).
* ``worked`` -- {op, id, target_id, at, by, vin, job_ref} -- the "Worked on
  this car?" tick a mechanic leaves when they actually used a link,
  against any link id (curated or user-added).

Link verification reuses the exact posture ``mes.experience`` documents for
the curated table: a plain HTTP GET with a browser User-Agent is enough for
most hosts, but the four XenForo forums (stelvioforum/giuliaforums/alfabb/
alfaowner) sit behind a JS bot challenge that returns HTTP 202 to any plain
client, so those are only ever confirmed by driving a real (headless) browser
through the challenge. :func:`verify_entry` is that one entry point --
module-level, deliberately not inlined into :func:`add_input`, so a test can
monkeypatch ``experience_inputs.verify_entry`` and never spawn Edge at all.
It never raises: a verification failure (offline, Edge missing, timeout)
degrades to ``{"status": "unreachable", ...}`` rather than blocking the save
-- a driver/mechanic's find is worth keeping even before (or if never)
confirmed reachable.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir

_LOCK = threading.Lock()

MAX_NOTE = 2000
MAX_TITLE = 300
MAX_URL = 2000

#: Who can file an input. The mobile/desktop "+ Add what you found" form
#: only offers driver/mechanic chips; owner/cuore are accepted here too --
#: the owner can log their own find, and "cuore" is reserved for anything
#: this app itself ever wants to record the same way.
ROLES = ("driver", "mechanic", "owner", "cuore")

KINDS = ("video", "forum", "article", "manual", "audio", "photo", "note")

RATINGS = ("helped", "unsure", "wrong")

FLAG_KINDS = ("wrong", "outdated")

#: Scope fields a link can be pinned to -- any subset, all optional.
SCOPE_FIELDS = ("code", "family", "system", "job")

#: Same four XenForo domains ``mes.experience`` documents as blocking plain
#: HTTP behind a JS proof-of-work challenge.
FORUM_HOSTS = ("stelvioforum.com", "giuliaforums.com", "alfabb.com", "alfaowner.com")

#: Query params worth stripping before duplicate-comparing two URLs --
#: tracking noise that doesn't change what page you land on.
_TRACKING_PARAMS = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
                    "fbclid", "gclid", "igshid", "ref"}

#: curated-vocabulary kind a user-picked ``kind`` maps onto for
#: :func:`export_for_curation` -- matches the values ``mes.experience``
#: itself uses (``how_to_video``, ``forum_thread``, ``owner_report``,
#: ``sound_reference``); anything without a closer match becomes
#: ``owner_report``.
_CURATED_KIND_MAP = {
    "video": "how_to_video",
    "forum": "forum_thread",
    "audio": "sound_reference",
}

_BOT_WALL_MARKERS = ("just a moment", "checking your browser", "cf-browser-verification",
                     "attention required")

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

_EDGE_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
)


# --------------------------------------------------------------------------
# verification
# --------------------------------------------------------------------------

def _host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower().lstrip("www.")
    except ValueError:
        return ""


def _is_forum_host(host: str) -> bool:
    return any(host == h or host.endswith("." + h) for h in FORUM_HOSTS)


def _youtube_oembed(url: str) -> Optional[dict[str, Any]]:
    try:
        oembed = ("https://www.youtube.com/oembed?url="
                 + urllib.parse.quote(url, safe="") + "&format=json")
        req = urllib.request.Request(oembed, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status != 200:
                return None
            data = json.loads(resp.read().decode("utf-8", "replace"))
        return {"title": data.get("title") or ""}
    except Exception:  # noqa: BLE001 -- never raise out of a verifier
        return None


def _http_get_ok(url: str) -> tuple[bool, str]:
    """Best-effort plain GET. Returns (ok, body_sample)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read(4000).decode("utf-8", "replace")
            return resp.status == 200, body
    except Exception:  # noqa: BLE001
        return False, ""


def _edge_path() -> Optional[str]:
    for p in _EDGE_CANDIDATES:
        if Path(p).exists():
            return p
    return None


def _browser_verify(url: str) -> dict[str, Any]:
    """Drive headless Edge through the page and look for a bot-wall marker
    in the rendered DOM -- the same real-browser posture ``mes.experience``
    used to confirm forum threads a plain GET cannot reach. Never raises;
    any failure (Edge missing, timeout, crash) degrades to "unreachable"."""
    now = datetime.now().isoformat(timespec="seconds")
    edge = _edge_path() if sys.platform == "win32" else None
    if not edge:
        return {"status": "unverified", "at": now, "method": "browser_unavailable"}
    try:
        out = subprocess.run(
            [edge, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--dump-dom", url],
            capture_output=True, text=True, timeout=30)
        dom = (out.stdout or "").lower()
        if not dom.strip():
            return {"status": "unreachable", "at": now, "method": "browser_cdp"}
        if any(marker in dom for marker in _BOT_WALL_MARKERS):
            return {"status": "unverified", "at": now, "method": "browser_cdp"}
        return {"status": "verified", "at": now, "method": "browser_cdp"}
    except Exception:  # noqa: BLE001 -- verification must never block a save
        return {"status": "unreachable", "at": now, "method": "browser_cdp"}


def verify_entry(url: str) -> dict[str, Any]:
    """``{"status": "verified"|"unverified"|"unreachable", "at", "method"}``
    for ``url``. YouTube links go through oEmbed; the four XenForo forum
    hosts (which block plain HTTP behind a JS challenge -- see module
    docstring) escalate straight to a real headless-browser check; every
    other host is a plain GET. Never raises."""
    now = datetime.now().isoformat(timespec="seconds")
    url = (url or "").strip()
    if not url:
        return {"status": "unreachable", "at": now, "method": "no_url"}
    host = _host_of(url)
    if "youtube.com" in host or "youtu.be" in host:
        info = _youtube_oembed(url)
        if info is not None:
            return {"status": "verified", "at": now, "method": "youtube_oembed"}
        return {"status": "unreachable", "at": now, "method": "youtube_oembed"}
    if _is_forum_host(host):
        return _browser_verify(url)
    ok, _body = _http_get_ok(url)
    if ok:
        return {"status": "verified", "at": now, "method": "http_200"}
    return {"status": "unreachable", "at": now, "method": "http_200"}


def normalize_url(url: str) -> str:
    """Lower-cased host, stripped default port/trailing slash/fragment, and
    tracking params (``utm_*``, ``fbclid``...) dropped and remaining params
    sorted -- so ``...?utm_source=x`` and the bare link compare equal for
    duplicate detection."""
    url = (url or "").strip()
    if not url:
        return ""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url.lower()
    host = (parts.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parts.path.rstrip("/") or "/"
    qs = [(k, v) for k, v in urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
         if k.lower() not in _TRACKING_PARAMS]
    qs.sort()
    query = urllib.parse.urlencode(qs)
    scheme = "https"  # scheme differences (http vs https) shouldn't split a duplicate
    return urllib.parse.urlunsplit((scheme, host, path, query, ""))


# --------------------------------------------------------------------------
# storage plumbing (mirrors cuore.live.owner_events' append/fold convention)
# --------------------------------------------------------------------------

def state_path() -> Path:
    return state_dir() / "experience_inputs.jsonl"


def _append(entry: dict[str, Any]) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _raw_records() -> list[dict[str, Any]]:
    p = state_path()
    if not p.exists():
        return []
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _clean_role(role: str) -> str:
    role = (role or "").strip().lower()
    if role not in ROLES:
        raise ValueError("role must be one of: " + ", ".join(ROLES))
    return role


def _clean_note(note: str) -> str:
    note = (note or "").strip()
    if len(note) > MAX_NOTE:
        raise ValueError(f"note must be {MAX_NOTE} characters or fewer")
    return note


def _clean_scope(scope: Optional[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (scope or {}).items():
        k = str(k)
        if k not in SCOPE_FIELDS:
            continue
        sv = str(v or "").strip()
        if sv:
            out[k] = sv[:200]
    return out


def _fold(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Reduce raw ``input``/``delete``/``restore``/``input_edit`` rows to
    one current view per input id, in append order -- same convention as
    :func:`cuore.live.owner_events._fold`. ``flag``/``worked`` rows are not
    folded here (they target *any* link id, not just this store's own, so
    they are read directly by :func:`flags_for`/:func:`worked_for`)."""
    deleted: dict[str, bool] = {}
    inputs: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    edits_by_id: dict[str, list[dict[str, Any]]] = {}
    for rec in rows:
        op = rec.get("op")
        rid = rec.get("id")
        if not rid:
            continue
        if op == "input":
            if rid in inputs:
                continue
            inputs[rid] = dict(rec)
            order.append(rid)
        elif op == "delete":
            deleted[rid] = True
        elif op == "restore":
            deleted[rid] = False
        elif op == "input_edit":
            edits_by_id.setdefault(rid, []).append(rec)

    out: dict[str, dict[str, Any]] = {}
    for rid in order:
        view = dict(inputs[rid])
        note = view.get("note", "")
        rating = view.get("rating", "unsure")
        title = view.get("title", "")
        kind = view.get("kind", "note")
        scope = dict(view.get("scope") or {})
        verified = view.get("verified")
        audit: list[dict[str, Any]] = []
        for e in edits_by_id.get(rid, []):
            changes = e.get("changes") or {}
            if "note" in changes:
                note = changes["note"].get("to", note)
            if "rating" in changes:
                rating = changes["rating"].get("to", rating)
            if "title" in changes:
                title = changes["title"].get("to", title)
            if "kind" in changes:
                kind = changes["kind"].get("to", kind)
            if "scope" in changes:
                scope = changes["scope"].get("to", scope) or {}
            if "verified" in changes:
                verified = changes["verified"].get("to", verified)
            audit.append({"at": e.get("at"), "by": e.get("by"), "changes": changes})
        view["note"] = note
        view["rating"] = rating
        view["title"] = title
        view["kind"] = kind
        view["scope"] = scope
        view["verified"] = verified
        view["audit"] = audit
        view["edited_at"] = audit[-1]["at"] if audit else None
        view["deleted"] = deleted.get(rid, False)
        out[rid] = view
    return out


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def find_duplicate(url: str, vin: str = "", *, include_deleted: bool = False) -> Optional[dict[str, Any]]:
    """The existing, non-deleted input (if any) whose normalised URL
    matches ``url``, scoped to ``vin`` when given (a global link with no
    VIN still de-dupes against other global links)."""
    norm = normalize_url(url)
    if not norm:
        return None
    vin = (vin or "").strip()
    for view in load(vin, include_deleted=include_deleted):
        if view.get("url_norm") == norm:
            return view
    return None


def add_input(*, vin: str = "", scope: Optional[dict[str, Any]] = None, url: str,
             title: str = "", kind: str, role: str, name: str = "",
             note: str = "", rating: str = "unsure", verify: bool = True,
             confirm_duplicate: bool = False) -> dict[str, Any]:
    """Validate, optionally verify, and append one ``input`` row. Raises
    ``ValueError`` on bad input (same posture as every other ``cuore.live``
    store). Returns ``{"duplicate": True, "existing": {...}}`` without
    writing anything when a non-deleted entry with the same normalised URL
    already exists for this ``vin`` and ``confirm_duplicate`` was not set --
    the caller (API/UI) decides whether to add anyway."""
    url = (url or "").strip()
    if not url:
        raise ValueError("url is required")
    if len(url) > MAX_URL:
        raise ValueError(f"url must be {MAX_URL} characters or fewer")
    kind = (kind or "").strip().lower()
    if kind not in KINDS:
        raise ValueError("kind must be one of: " + ", ".join(KINDS))
    role = _clean_role(role)
    note = _clean_note(note)
    rating = (rating or "unsure").strip().lower()
    if rating not in RATINGS:
        raise ValueError("rating must be one of: " + ", ".join(RATINGS))
    vin = (vin or "").strip()
    url_norm = normalize_url(url)

    if not confirm_duplicate:
        dup = find_duplicate(url, vin)
        if dup is not None:
            return {"duplicate": True, "existing": dup}

    verified = verify_entry(url) if verify else {"status": "unverified", "at": _now(), "method": "skipped"}

    entry = {
        "op": "input",
        "id": uuid.uuid4().hex[:12],
        "vin": vin,
        "scope": _clean_scope(scope),
        "url": url,
        "url_norm": url_norm,
        "title": (title or "").strip()[:MAX_TITLE],
        "kind": kind,
        "found_by": {"role": role, "name": (name or "").strip()[:200]},
        "found_at": _now(),
        "note": note,
        "rating": rating,
        "verified": verified,
        "confidence": "reported",
    }
    with _LOCK:
        _append(entry)
    return entry


def edit_input(id: str, *, by_role: str, by_name: str = "", note: Optional[str] = None,
               rating: Optional[str] = None, title: Optional[str] = None,
               kind: Optional[str] = None, scope: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Append an ``input_edit`` amendment, same never-rewrite convention as
    :func:`cuore.live.owner_events.edit`. Raises ``ValueError`` on: no such
    input, the input is deleted, a bad role/rating/kind, or an edit that
    changes nothing."""
    iid = (id or "").strip()
    if not iid:
        raise ValueError("id is required")
    by_role = _clean_role(by_role)

    with _LOCK:
        rows = _raw_records()
        current = _fold(rows).get(iid)
        if current is None:
            raise ValueError(f"no experience input with id {iid!r}")
        if current.get("deleted"):
            raise ValueError(f"experience input {iid!r} is deleted")

        changes: dict[str, Any] = {}
        if note is not None:
            note_v = _clean_note(note)
            changes["note"] = {"from": current.get("note", ""), "to": note_v}
        if rating is not None:
            rating_v = (rating or "").strip().lower()
            if rating_v not in RATINGS:
                raise ValueError("rating must be one of: " + ", ".join(RATINGS))
            changes["rating"] = {"from": current.get("rating"), "to": rating_v}
        if title is not None:
            changes["title"] = {"from": current.get("title", ""), "to": (title or "").strip()[:MAX_TITLE]}
        if kind is not None:
            kind_v = (kind or "").strip().lower()
            if kind_v not in KINDS:
                raise ValueError("kind must be one of: " + ", ".join(KINDS))
            changes["kind"] = {"from": current.get("kind"), "to": kind_v}
        if scope is not None:
            changes["scope"] = {"from": current.get("scope", {}), "to": _clean_scope(scope)}

        if not changes:
            raise ValueError("edit must change at least one of: note, rating, title, kind, scope")

        entry = {
            "op": "input_edit",
            "id": iid,
            "at": _now(),
            "by": {"role": by_role, "name": (by_name or "").strip()[:200]},
            "changes": changes,
        }
        _append(entry)
    return entry


def verify_input(id: str) -> dict[str, Any]:
    """Run :func:`verify_entry` against a row's own URL right now and
    append the result as an ``input_edit`` amendment, same never-rewrite
    convention as :func:`edit_input`. This is the deferred half of
    ``add_input(verify=False)`` -- the add returns immediately with
    ``verified: {"status": "unverified"/"skipped", ...}`` so the save never
    blocks on an outbound network check (2026-10-14, N3); the caller (the
    "+ Add what you found" form) calls this right after, in the
    background, and swaps the row's "Verifying..." badge for whatever
    comes back. Raises ``ValueError`` on: no such input, the input is
    deleted."""
    iid = (id or "").strip()
    if not iid:
        raise ValueError("id is required")
    with _LOCK:
        rows = _raw_records()
        current = _fold(rows).get(iid)
        if current is None:
            raise ValueError(f"no experience input with id {iid!r}")
        if current.get("deleted"):
            raise ValueError(f"experience input {iid!r} is deleted")
        url = current.get("url", "")
    new_verified = verify_entry(url) if url else {"status": "unreachable", "at": _now(), "method": "no_url"}
    with _LOCK:
        rows = _raw_records()
        current = _fold(rows).get(iid)
        if current is None or current.get("deleted"):
            return current or {}
        changes = {"verified": {"from": current.get("verified"), "to": new_verified}}
        entry = {
            "op": "input_edit",
            "id": iid,
            "at": _now(),
            "by": {"role": "cuore", "name": ""},
            "changes": changes,
        }
        _append(entry)
        return _fold(_raw_records())[iid]


def delete_input(id: str) -> dict[str, Any]:
    """Soft-delete: append a ``delete`` amendment. Never rewrites history."""
    iid = (id or "").strip()
    if not iid:
        raise ValueError("id is required")
    with _LOCK:
        rows = _raw_records()
        if not any(r.get("op") == "input" and r.get("id") == iid for r in rows):
            raise ValueError(f"no experience input with id {iid!r}")
        entry = {"op": "delete", "id": iid, "at": _now()}
        _append(entry)
    return entry


def restore_input(id: str) -> dict[str, Any]:
    """Undo a soft-delete ("Undo" on the post-delete confirmation)."""
    iid = (id or "").strip()
    if not iid:
        raise ValueError("id is required")
    with _LOCK:
        rows = _raw_records()
        if not any(r.get("op") == "input" and r.get("id") == iid for r in rows):
            raise ValueError(f"no experience input with id {iid!r}")
        entry = {"op": "restore", "id": iid, "at": _now()}
        _append(entry)
    return entry


def load(vin: str = "", *, include_deleted: bool = False, role: Optional[str] = None,
        scope_field: Optional[str] = None, scope_value: Optional[str] = None) -> list[dict[str, Any]]:
    """User-added input rows, newest ``found_at`` first, with every
    ``input_edit`` folded in. ``vin``, when given, also includes global
    (no-VIN) rows -- a link found while chasing a code isn't always tied to
    one car. Filter by ``role`` (driver/mechanic/owner/cuore) and/or one
    ``scope_field``/``scope_value`` pair (e.g. ``code``/``"P0456"``)."""
    vin = (vin or "").strip()
    with _LOCK:
        rows = _raw_records()
    folded = _fold(rows)

    out: list[dict[str, Any]] = []
    for view in folded.values():
        if view["deleted"] and not include_deleted:
            continue
        if vin and view.get("vin") and view.get("vin") != vin:
            continue
        if role and (view.get("found_by") or {}).get("role") != role:
            continue
        if scope_field and scope_value:
            if (view.get("scope") or {}).get(scope_field) != scope_value:
                continue
        out.append(dict(view))
    out.sort(key=lambda r: r.get("found_at") or "", reverse=True)
    return out


def flag_curated(target_id: str, *, by_role: str, by_name: str = "", note: str = "",
                 flag_kind: str = "wrong", vin: str = "") -> dict[str, Any]:
    """Record a "Flag as wrong/outdated" against any link id, curated or
    user-added. Curated rows (``mes.experience``) stay read-only -- this is
    an append-only feedback record alongside them, never a write into their
    table."""
    tid = (target_id or "").strip()
    if not tid:
        raise ValueError("target_id is required")
    by_role = _clean_role(by_role)
    flag_kind = (flag_kind or "wrong").strip().lower()
    if flag_kind not in FLAG_KINDS:
        raise ValueError("flag_kind must be one of: " + ", ".join(FLAG_KINDS))
    entry = {
        "op": "flag",
        "id": uuid.uuid4().hex[:12],
        "target_id": tid,
        "vin": (vin or "").strip(),
        "at": _now(),
        "by": {"role": by_role, "name": (by_name or "").strip()[:200]},
        "note": _clean_note(note),
        "flag_kind": flag_kind,
    }
    with _LOCK:
        _append(entry)
    return entry


def flags_for(target_id: str) -> list[dict[str, Any]]:
    """Every flag ever recorded against ``target_id``, oldest first."""
    tid = (target_id or "").strip()
    with _LOCK:
        rows = _raw_records()
    out = [r for r in rows if r.get("op") == "flag" and r.get("target_id") == tid]
    out.sort(key=lambda r: r.get("at") or "")
    return out


def mark_worked(target_id: str, *, by_role: str, by_name: str = "", vin: str = "",
                job_ref: str = "") -> dict[str, Any]:
    """"Worked on this car?" tick -- a mechanic confirming they actually
    used this link (curated or user-added) on this job. ``job_ref`` is free
    text naming the job/action it ties to; never validated against a job
    store so this never fails because a job lookup doesn't exist yet."""
    tid = (target_id or "").strip()
    if not tid:
        raise ValueError("target_id is required")
    by_role = _clean_role(by_role)
    entry = {
        "op": "worked",
        "id": uuid.uuid4().hex[:12],
        "target_id": tid,
        "vin": (vin or "").strip(),
        "at": _now(),
        "by": {"role": by_role, "name": (by_name or "").strip()[:200]},
        "job_ref": (job_ref or "").strip()[:300],
    }
    with _LOCK:
        _append(entry)
    return entry


def worked_for(target_id: str) -> list[dict[str, Any]]:
    """Every "worked on this car" tick ever recorded against ``target_id``,
    oldest first."""
    tid = (target_id or "").strip()
    with _LOCK:
        rows = _raw_records()
    out = [r for r in rows if r.get("op") == "worked" and r.get("target_id") == tid]
    out.sort(key=lambda r: r.get("at") or "")
    return out


def counts_by_role(items: list[dict[str, Any]]) -> dict[str, int]:
    """``{"mechanic": n, "driver": n, "owner": n, "cuore": n}`` over a list
    of folded input rows (or anything else carrying a ``found_by.role``) --
    used for the section-header tally ("3 mechanic 1 driver")."""
    out = {r: 0 for r in ROLES}
    for item in items:
        role = (item.get("found_by") or {}).get("role")
        if role in out:
            out[role] += 1
    return out


def export_for_curation(vin: str = "", *, role: str = "mechanic",
                        rating: str = "helped") -> list[dict[str, Any]]:
    """JSON export, in ``mes.experience``'s own curated-row shape, of
    user-added links matching ``role``/``rating`` (default: a mechanic's
    find, marked "helped") -- for the owner to review and hand-promote into
    the curated table. Never writes to that table itself; this is a review
    export, not an auto-promotion."""
    out: list[dict[str, Any]] = []
    for view in load(vin, role=role):
        if rating and view.get("rating") != rating:
            continue
        scope = view.get("scope") or {}
        keys = [v for v in (scope.get("code"), scope.get("family")) if v]
        if not keys and scope.get("job"):
            keys = [scope["job"]]
        out.append({
            "id": "export-" + view["id"],
            "keys": keys,
            "title": view.get("title") or view.get("url"),
            "url": view.get("url"),
            "source": _host_of(view.get("url", "")) or "unknown",
            "kind": _CURATED_KIND_MAP.get(view.get("kind"), "owner_report"),
            "covers": scope.get("system") or scope.get("job") or "",
            "vehicle_fit": "",
            "date": (view.get("found_at") or "")[:10],
            "reputation": "medium",
            "verified_at": (view.get("verified") or {}).get("at", ""),
            "verified_how": (view.get("verified") or {}).get("method", ""),
            "found_by": view.get("found_by"),
            "note": view.get("note", ""),
        })
    return out


__all__ = ["ROLES", "KINDS", "RATINGS", "FLAG_KINDS", "SCOPE_FIELDS", "FORUM_HOSTS",
          "MAX_NOTE", "MAX_TITLE", "MAX_URL", "state_path", "verify_entry",
          "normalize_url", "find_duplicate", "add_input", "edit_input",
          "delete_input", "restore_input", "load", "flag_curated", "flags_for",
          "mark_worked", "worked_for", "counts_by_role", "export_for_curation"]
