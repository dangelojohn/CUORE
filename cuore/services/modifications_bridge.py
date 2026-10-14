"""``/api/mods*`` and ``/v/{vin}/mods``: the Modifications layer.

**CUORE diagnoses; it never performs coding/configuration writes itself**
(NO-GO decided 2026-10-14 -- see
``docs/research/MES_PADDLE_SHIFT_CODING_2026-10-14.md`` and
``docs/research/mes_paddle_shift_function.json``). A modification is done
in MES/wiTECH (or the car's own menu, for the one named exception) via a
handoff card, and RECORDED here with who/when/from->to/backup/verification.
Diagnostics elsewhere in CUORE reach this module's :func:`non_stock` --
never ``cuore.live.modifications`` directly -- to know the car is non-stock.

Two stores sit behind this bridge, neither duplicating the other:

* :mod:`mes.modifications` -- the read-only, sourced *catalogue* of known
  modifications for this platform (paddle shift NA/Euro first).
* :mod:`cuore.live.modifications` -- the per-VIN, append-only *ledger* of
  what was actually done to one car.

A third source is merged in on READ only, never duplicated in storage: a
``battery_electrical/module_coded`` or ``parts_repairs_elsewhere/
part_fitted_elsewhere`` entry already filed through "Tell CUORE"
(:mod:`cuore.live.owner_events`) shows up in this ledger's view tagged
``source: "reported_by_owner"`` -- see :func:`ledger`. Saving one of those
owner events does not write a second copy here; this bridge reads
``owner_events.load`` fresh every call and folds the two views together,
so there is exactly one place either kind of record lives on disk.

MES handoff reuse: when a catalogue row carries a ``mes_function_id`` that
cross-references :mod:`mes.mes_functions`, :func:`handoff_for` returns the
exact same handoff card :mod:`cuore.services.mes_handoff_bridge` already
renders for the Tests/Job pages -- never a second, parallel card format.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from ..live import modifications as store
from ..live import owner_events as owner_events_store
from . import mes_handoff_bridge
from .errors import BadRequest, NotFound

from mes import modifications as mods_mod  # noqa: E402

# ===========================================================================
# 1. Catalogue (read-only, sourced)
# ===========================================================================


def all_mods() -> list[dict[str, Any]]:
    """Every catalogued modification, paddle shift first."""
    return mods_mod.all_mods()


def mod(mod_id: str) -> dict[str, Any]:
    """One catalogue row by id. Raises :class:`NotFound` for an unknown id."""
    row = mods_mod.mod(mod_id)
    if row is None:
        raise NotFound(f"unknown modification id {mod_id!r}")
    return row


def mods_for_module(module_substring: str) -> list[dict[str, Any]]:
    return mods_mod.mods_for_module(module_substring)


def search_mods(text: str) -> list[dict[str, Any]]:
    return mods_mod.search(text)


def handoff_for(mod_id: str) -> Optional[dict[str, Any]]:
    """The "Do it in MES" handoff card for a catalogue row, reusing
    :mod:`cuore.services.mes_handoff_bridge`'s own card renderer -- ``None``
    when the row has no ``mes_function_id`` cross-reference, or that
    function id is not (or no longer) in ``mes.mes_functions``."""
    row = mods_mod.mod(mod_id)
    if row is None:
        return None
    fn_id = (row.get("mes_function_id") or "").strip()
    if not fn_id:
        return None
    try:
        return mes_handoff_bridge.card(fn_id)
    except Exception:  # noqa: BLE001 -- a missing cross-ref is never fatal
        return None


# ===========================================================================
# 2. Per-VIN ledger
# ===========================================================================


def record(vin: str, **kwargs: Any) -> dict[str, Any]:
    """Record one modification done to ``vin``. ``kwargs`` are
    :func:`cuore.live.modifications.add`'s own keywords. Raises
    :class:`BadRequest` on invalid input."""
    try:
        return store.add(vin, **kwargs)
    except ValueError as exc:
        raise BadRequest(str(exc)) from exc


def edit(entry_id: str, **kwargs: Any) -> dict[str, Any]:
    try:
        return store.edit(entry_id, **kwargs)
    except ValueError as exc:
        msg = str(exc)
        if msg.startswith("no modification record"):
            raise NotFound(msg) from exc
        raise BadRequest(msg) from exc


def delete(entry_id: str) -> dict[str, Any]:
    try:
        return store.delete(entry_id)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


def restore(entry_id: str) -> dict[str, Any]:
    try:
        return store.restore(entry_id)
    except ValueError as exc:
        raise NotFound(str(exc)) from exc


#: owner_events (category, kind) pairs that are themselves a modification
#: report, per the owner's own instruction ("the mobile owner-events kind
#: 'parts fitted elsewhere / module coded' already exists -- map it").
_OWNER_EVENT_MOD_KINDS = (
    ("battery_electrical", "module_coded"),
    ("parts_repairs_elsewhere", "part_fitted_elsewhere"),
)


def _owner_reported_rows(vin: str) -> list[dict[str, Any]]:
    """Owner-events rows that are modification reports, reshaped into this
    ledger's own record shape, tagged ``source: "reported_by_owner"``.
    Read-side merge only -- see this module's own docstring; nothing is
    written to ``cuore.live.modifications`` here."""
    out: list[dict[str, Any]] = []
    try:
        events = owner_events_store.load(vin)
    except Exception:  # noqa: BLE001 -- a broken owner_events read must
        # never sink this ledger's own view
        return out
    for e in events:
        key = (e.get("category"), e.get("kind"))
        if key not in _OWNER_EVENT_MOD_KINDS:
            continue
        fields = e.get("fields") or {}
        if key == ("battery_electrical", "module_coded"):
            free_text = f"Module coded/flashed: {fields.get('module') or 'unspecified module'}"
            by_name = fields.get("by_whom") or ""
        else:
            free_text = f"Part fitted elsewhere: {fields.get('part') or 'unspecified part'}"
            by_name = fields.get("who") or ""
        out.append({
            "op": "record",
            "id": f"oe:{e['id']}",
            "vin": vin,
            "at": e.get("recorded_at") or e.get("at"),
            "mod_id": "",
            "free_text": free_text,
            "done_at": e.get("at"),
            "by": {"role": e.get("by", {}).get("role") or "owner",
                  "name": by_name or (e.get("by", {}).get("name") or "")},
            "tool": "other",
            "from_value": "", "to_value": "",
            "backup": "none",
            "verification": {"how": "", "when": "", "result": ""},
            "proxi_realigned": None,
            "notes": e.get("note") or "",
            "media_ids": e.get("media_ids") or [],
            "audit": [],
            "edited_at": None,
            "deleted": False,
            "source": "reported_by_owner",
        })
    return out


def ledger(vin: str, *, include_deleted: bool = False) -> list[dict[str, Any]]:
    """Every modification on file for ``vin`` -- mechanic-recorded rows
    from :mod:`cuore.live.modifications` plus owner-reported rows merged
    in from "Tell CUORE" (see :func:`_owner_reported_rows`), newest first."""
    vin = (vin or "").strip()
    if not vin:
        return []
    rows = [{**r, "source": r.get("source") or "recorded"}
            for r in store.load(vin, include_deleted=include_deleted)]
    rows.extend(_owner_reported_rows(vin))
    rows.sort(key=lambda r: r.get("done_at") or r.get("at") or "", reverse=True)
    return rows


def status(vin: str) -> dict[str, Any]:
    """``{"status": "stock"|"modified", "modifications": [...]}`` -- the
    full "This car" summary, catalogue names resolved where ``mod_id``
    matches, including owner-reported entries."""
    rows = ledger(vin)
    out_rows = []
    for r in rows:
        row = dict(r)
        if row.get("mod_id"):
            try:
                row["mod_name"] = mod(row["mod_id"])["name"]
            except NotFound:
                row["mod_name"] = row["mod_id"]
        else:
            row["mod_name"] = row.get("free_text") or "(unspecified)"
        out_rows.append(row)
    return {"status": "modified" if out_rows else "stock",
           "modifications": out_rows}


def _short_date(iso: Optional[str]) -> str:
    if not iso:
        return "unknown date"
    try:
        dt = datetime.fromisoformat(str(iso)[:19])
    except ValueError:
        return str(iso)
    # Not %-d/%e: Windows' strftime has neither -- build it by hand so this
    # works identically on the Pi (Linux) and a Windows dev box.
    return f"{dt.day} {dt.strftime('%b')}"


def non_stock(vin: str) -> list[dict[str, Any]]:
    """Chips for other surfaces (the health report, the transmission
    system page) to show -- e.g. ``{"label": "Non-stock configuration:
    paddle behaviour EU", "detail": "recorded 14 Oct by mechanic Tony"}``.
    Empty list for a stock car. Never raises -- a broken ledger/catalogue
    read must never sink a diagnostics page that only wants to know
    whether this car is stock."""
    try:
        rows = ledger(vin)
    except Exception:  # noqa: BLE001
        return []
    chips: list[dict[str, Any]] = []
    for r in rows:
        name = ""
        if r.get("mod_id"):
            try:
                name = mod(r["mod_id"])["name"]
            except NotFound:
                name = r["mod_id"]
        name = name or r.get("free_text") or "unspecified modification"
        who = r.get("by") or {}
        role = who.get("role") or "unknown"
        who_name = who.get("name")
        by_txt = f"{role} {who_name}".strip() if who_name else role
        reported = " (reported by owner)" if r.get("source") == "reported_by_owner" else ""
        chips.append({
            "id": r.get("id"),
            "mod_id": r.get("mod_id") or "",
            "label": f"Non-stock configuration: {name}",
            "detail": f"recorded {_short_date(r.get('done_at') or r.get('at'))} "
                     f"by {by_txt}{reported}",
            "to_value": r.get("to_value") or "",
        })
    return chips


__all__ = ["all_mods", "mod", "mods_for_module", "search_mods", "handoff_for",
          "record", "edit", "delete", "restore", "ledger", "status",
          "non_stock"]
