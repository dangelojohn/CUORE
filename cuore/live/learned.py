"""Persistence for DID mappings learned by watching wiTECH's own traffic.

Same JSON-file-beside-lock-file pattern as :mod:`store` (see that module for
why: Phase 3 replaces this with the spec's SQLite store, the interface
stays). Kept separate from ``store.py`` because these entries are a
different kind of fact -- not an address this tool confirmed by asking the
car, but a DID/field meaning inferred from correlating wiTECH's requests
against what a technician read off its screen. Every entry is stamped with
that provenance and it is never upgraded to a stronger confidence here.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir
from .ui_store import atomic_write_text, quarantine_corrupt

_LOCK = threading.Lock()

#: The only confidence value this module ever writes.
CONFIDENCE = "learned from wiTECH capture"


def path() -> Path:
    return state_dir() / "learned_dids.json"


def _load() -> dict[str, Any]:
    try:
        data = json.loads(path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except OSError:
        return {}
    except ValueError:
        quarantine_corrupt(path())
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: dict[str, Any]) -> None:
    atomic_write_text(path(), json.dumps(data, indent=2))


def _field_key(module_code: str, did: str, field: Optional[dict[str, Any]]) -> tuple[str, str, str]:
    return (module_code.upper(), did.upper(), json.dumps(field or {}, sort_keys=True))


def accept(vin: str, module_code: str, did: str, name: str, field: dict[str, Any],
          scale: Optional[float] = None, offset: Optional[float] = None,
          unit: Optional[str] = None, evidence: Optional[list[dict[str, Any]]] = None
          ) -> dict[str, Any]:
    """Record an accepted mapping for ``vin``.

    ``field`` is the byte-level location within the DID's payload, e.g.
    ``{"offset": 2, "bit": 0}`` or ``{"offset": 0, "width": "byte"}`` --
    whatever :func:`learn.correlate` reported for the chosen candidate.
    Replaces any prior *accepted* entry for the same ``(module_code, did,
    field)`` on this VIN; rejected entries and other fields are kept.
    """
    entry = {
        "module": module_code.upper(), "did": did.upper(), "name": name, "field": field,
        "scale": scale, "offset": offset, "unit": unit, "evidence": evidence or [],
        "confidence": CONFIDENCE, "status": "accepted",
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    key = _field_key(module_code, did, field)
    with _LOCK:
        data = _load()
        entries = data.setdefault(vin, [])
        entries[:] = [e for e in entries
                     if not (e.get("status") == "accepted"
                             and _field_key(e.get("module", ""), e.get("did", ""),
                                            e.get("field")) == key)]
        entries.append(entry)
        _save(data)
    return entry


def reject(vin: str, module_code: str, did: str, field: Optional[dict[str, Any]] = None,
          reason: str = "") -> dict[str, Any]:
    """Record that a candidate mapping was looked at and turned down."""
    entry = {
        "module": module_code.upper(), "did": did.upper(), "field": field,
        "confidence": CONFIDENCE, "status": "rejected", "reason": reason,
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        data = _load()
        data.setdefault(vin, []).append(entry)
        _save(data)
    return entry


def learned(vin: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
    """All learned entries, or just ``vin``'s (``{vin: [...]}``, ``[]`` if none)."""
    with _LOCK:
        data = _load()
    if vin is None:
        return data
    return {vin: data.get(vin, [])}


# --- broadcast signals: learned from watching a bus, not a UDS request ------
#
# A DID mapping (above) is learned by correlating wiTECH's own UDS reads; a
# *broadcast* signal is learned by correlating a raw CAN id's bytes against a
# physical action a mechanic performed while a bus capture ran (see
# :mod:`cuore.live.buscapture`). There is no scale: nothing here ever
# measures or fits one, so every entry is stamped ``scale="unknown"`` and the
# Live board must show it as "learned, unscaled" rather than inventing a
# decoded value.

#: The only scale value this section ever writes.
UNSCALED = "unknown"


def _broadcast_key(bus: str, can_id: str, field: dict[str, Any]) -> tuple[str, str, str]:
    return (bus.lower(), can_id.upper(), json.dumps(field or {}, sort_keys=True))


def accept_broadcast(vin: str, bus: str, can_id: str, name: str, field: dict[str, Any],
                     evidence: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Record an accepted broadcast-signal mapping for ``vin``.

    ``field`` is the byte-level location within the frame, e.g.
    ``{"offset": 2, "width": "byte"}`` -- whatever
    :func:`cuore.live.buscapture.rank_changed_bytes` reported for the chosen
    candidate. Replaces any prior *accepted* entry for the same
    ``(bus, can_id, field)`` on this VIN; rejected entries and other fields
    are kept.
    """
    entry = {
        "kind": "broadcast", "bus": bus.lower(), "id": can_id.upper(), "name": name,
        "field": field, "scale": UNSCALED, "offset": None, "unit": "",
        "evidence": evidence or [], "confidence": CONFIDENCE, "status": "accepted",
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    key = _broadcast_key(bus, can_id, field)
    with _LOCK:
        data = _load()
        entries = data.setdefault(vin, [])
        entries[:] = [e for e in entries
                     if not (e.get("status") == "accepted" and e.get("kind") == "broadcast"
                             and _broadcast_key(e.get("bus", ""), e.get("id", ""),
                                                e.get("field")) == key)]
        entries.append(entry)
        _save(data)
    return entry


def learned_broadcast(vin: Optional[str] = None, bus: str = "") -> dict[str, list[dict[str, Any]]]:
    """Accepted broadcast entries only (``kind == "broadcast"``), optionally
    narrowed to one bus. Same ``{vin: [...]}`` shape as :func:`learned`."""
    data = learned(vin)
    out: dict[str, list[dict[str, Any]]] = {}
    for v, entries in data.items():
        rows = [e for e in entries if e.get("kind") == "broadcast" and e.get("status") == "accepted"]
        if bus:
            rows = [e for e in rows if e.get("bus") == bus.lower()]
        out[v] = rows
    return out


# --- DID discovery: answered during a read-only sweep, not yet decoded -----
#
# Different provenance from accept()/reject() above (which record a meaning
# correlated against wiTECH's own traffic): a discovery sweep
# (``cuore.live.fullscan``'s TCM DID discovery is the first caller) only
# learns THAT a DID answered, never what the bytes mean. Same "unscaled"
# posture as the broadcast section above -- stamped ``scale=UNSCALED`` and
# shown by the Live board as "learned, unscaled", never a decoded value.


def record_did_answer(vin: str, module_code: str, did: str, raw_bytes: list[str],
                      source: str = "") -> dict[str, Any]:
    """Record that ``did`` answered on ``module_code`` during a read-only
    discovery sweep -- raw bytes only. Appends unconditionally (no
    replace-by-key, contrast :func:`accept`): the same DID answering on a
    later sweep is corroborating evidence, not a correction, and the raw
    bytes may legitimately differ visit to visit (a live, if unscaled,
    reading) so neither copy is "wrong"."""
    entry = {
        "kind": "did", "module": module_code.upper(), "did": did.upper(),
        "scale": UNSCALED, "bytes": list(raw_bytes or []), "name": None,
        "source": source, "status": "observed",
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        data = _load()
        data.setdefault(vin, []).append(entry)
        _save(data)
    return entry


def learned_did_discovery(vin: Optional[str] = None, module: str = ""
                          ) -> dict[str, list[dict[str, Any]]]:
    """``kind == "did"``, ``status == "observed"`` entries only (i.e. from
    :func:`record_did_answer`, never :func:`accept`'s decoded ones),
    optionally narrowed to one module -- the Live board's "learned,
    unscaled" list under Transmission (module ``"TCM"``). Same ``{vin:
    [...]}`` shape as :func:`learned`."""
    data = learned(vin)
    out: dict[str, list[dict[str, Any]]] = {}
    for v, entries in data.items():
        rows = [e for e in entries if e.get("kind") == "did" and e.get("status") == "observed"]
        if module:
            rows = [e for e in rows if e.get("module") == module.upper()]
        out[v] = rows
    return out


# --- MES-learned DID mappings: fit against an MES CSV recording -----------
#
# A third kind of provenance, distinct from both accept()/reject() above
# (correlated against wiTECH's own traffic, technician-marked) and the
# broadcast/discovery sections (no scale ever fitted): these entries come
# from :mod:`cuore.live.mes_learn`, which listens passively on a SECOND
# adapter while MultiEcuScan runs its own live view, then fits the DID's raw
# byte series against the MES CSV recording's named parameter columns by
# least squares. Single-source (one MES session, not cross-checked against a
# second tool) and never a catalogue DID -- :func:`accept_mes` only ever adds
# a new entry here, it never touches :mod:`cuore.live.did_catalog`.

#: The only confidence value this section ever writes.
CONFIDENCE_MES = "SINGLE-SOURCE (learned)"

#: Byte-letter alphabet for the CarScanner-style formula built by
#: :func:`_mes_formula` -- same grammar :func:`cuore.live.readall.eval_formula`
#: evaluates (letters, ``SIGNED()``, ``+ - * /``), so a MES-learned channel's
#: formula is evaluated by the exact same poller code path as a catalogued
#: DID's (see ``cuore.live.poller``), not the separate Torque-style
#: arithmetic :func:`cuore.live.channels.eval_expr` uses for custom channels
#: (that grammar has no ``SIGNED()``, so it cannot express a signed field).
_MES_BYTE_LETTERS = "ABCDEFGHIJKLMNOP"


def _mes_key(module_code: str, did: str, field: Optional[dict[str, Any]]) -> tuple[str, str, str]:
    return (module_code.upper(), did.upper(), json.dumps(field or {}, sort_keys=True))


def _mes_formula(field: dict[str, Any], scale: float, offset: float) -> str:
    """Build the CarScanner-style formula for one learned field.

    For a signed 2-byte field this deliberately writes
    ``(SIGNED(<hi>)*256)+<lo>`` -- sign-correcting the HIGH byte alone --
    rather than ``SIGNED((<hi>*256)+<lo>)``. :func:`cuore.live.readall.
    _signed` picks its two's-complement width by the *magnitude* of its
    operand, trying 8 bits first: wrapping the already-combined 16-bit value
    in ``SIGNED()`` misreads any raw value whose high byte is 0 (so the
    combined value is < 256) as an 8-bit negative number instead of a small
    positive 16-bit one. Sign-correcting the high byte on its own is always
    unambiguous (a lone byte is always 8 bits) and is algebraically
    equivalent two's-complement for the full 16-bit value either way.
    """
    off = int(field.get("offset", 0))
    width = field.get("width", "byte")
    signed = bool(field.get("signed", False))
    if off < 0 or off >= len(_MES_BYTE_LETTERS) or (width == "u16" and off + 1 >= len(_MES_BYTE_LETTERS)):
        raise ValueError(f"offset {off} out of range for a formula letter")
    hi, lo = _MES_BYTE_LETTERS[off], (_MES_BYTE_LETTERS[off + 1] if width == "u16" else "")
    if width == "u16":
        expr = f"(({f'SIGNED({hi})' if signed else hi}*256)+{lo})"
    else:
        expr = f"SIGNED({hi})" if signed else hi
    scale_r = round(float(scale), 6)
    offset_r = round(float(offset), 6)
    def _num(x: float) -> str:   # plain decimal: the formula grammar has no 1e-05 exponent form
        return format(x, "f").rstrip("0").rstrip(".") if "." in format(x, "f") else format(x, "f")

    formula = f"{expr}*{_num(scale_r)}"
    if offset_r:
        formula += f" - {_num(abs(offset_r))}" if offset_r < 0 else f" + {_num(offset_r)}"
    return formula


def accept_mes(vin: str, module_code: str, did: str, name: str, field: dict[str, Any],
               scale: float, offset: float, unit: str, r2: float, source: str,
               evidence: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Record an accepted MES-learned DID mapping for ``vin``.

    ``field`` is ``{"offset": int, "width": "byte"|"u16", "signed": bool}`` --
    whatever :func:`cuore.live.mes_learn.align` reported for the chosen
    candidate. ``source`` is the full provenance sentence (``"learned from
    MES <csv name> <date>, fit R² <value>"``). Replaces any prior
    *accepted* MES entry for the same ``(module_code, did, field)`` on this
    VIN; a rejected entry or a different field is kept. Never overwrites a
    catalogue DID: this module only ever appends to its own JSON store.
    """
    entry = {
        "kind": "mes", "module": module_code.upper(), "did": did.upper(), "name": name,
        "field": field, "scale": scale, "offset": offset, "unit": unit or "", "r2": r2,
        "source": source, "evidence": evidence or [],
        "confidence": CONFIDENCE_MES, "status": "accepted",
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    key = _mes_key(module_code, did, field)
    with _LOCK:
        data = _load()
        entries = data.setdefault(vin, [])
        entries[:] = [e for e in entries
                     if not (e.get("status") == "accepted" and e.get("kind") == "mes"
                             and _mes_key(e.get("module", ""), e.get("did", ""),
                                          e.get("field")) == key)]
        entries.append(entry)
        _save(data)
    return entry


def reject_mes(vin: str, module_code: str, did: str, field: Optional[dict[str, Any]] = None,
              reason: str = "") -> dict[str, Any]:
    """Record that a MES-learned candidate was looked at and turned down --
    kept as observed-but-unscaled (``scale`` is :data:`UNSCALED`), never
    guessed."""
    entry = {
        "kind": "mes", "module": module_code.upper(), "did": did.upper(), "field": field,
        "scale": UNSCALED, "confidence": CONFIDENCE_MES, "status": "rejected", "reason": reason,
        "at": datetime.now().isoformat(timespec="seconds"),
    }
    with _LOCK:
        data = _load()
        data.setdefault(vin, []).append(entry)
        _save(data)
    return entry


def learned_mes(vin: Optional[str] = None) -> dict[str, list[dict[str, Any]]]:
    """``kind == "mes"`` entries only (both accepted and rejected), same
    ``{vin: [...]}`` shape as :func:`learned`."""
    data = learned(vin)
    return {v: [e for e in entries if e.get("kind") == "mes"] for v, entries in data.items()}


def learned_mes_channels(vin: Optional[str] = None) -> list[Any]:
    """Accepted MES-learned DID mappings as ready
    :class:`~cuore.live.channels.Channel` objects -- usable by the Live
    board as named, scaled channels.

    Same hand-off as :func:`cuore.live.ui_store.load_custom_channels`: this
    only hands back well-formed :class:`Channel` objects, formula built by
    :func:`_mes_formula` in the same ``SIGNED()``-capable grammar a
    catalogued DID's formula uses (see :mod:`cuore.live.readall`) so the
    existing poller code path (:mod:`cuore.live.poller`) evaluates it
    exactly like any other ``kind="did"`` channel -- wiring an accepted
    entry into the live registry (:func:`cuore.live.channels.
    available_channels`) belongs to whoever owns that module.
    """
    from . import channels as channels_mod  # local: avoid a top-level cycle

    out: list[Any] = []
    for _vin, entries in learned_mes(vin).items():
        for e in entries:
            if e.get("status") != "accepted":
                continue
            try:
                formula = _mes_formula(e.get("field") or {}, e.get("scale"), e.get("offset"))
                did_int = int(e.get("did", "0"), 16)
            except (ValueError, TypeError):
                continue
            did_hex = e.get("did", "0000")
            module = (e.get("module") or "").upper()
            out.append(channels_mod.Channel(
                id=f"mes_{module.lower()}_{did_hex.lower()}", name=e.get("name") or did_hex,
                unit=e.get("unit") or "", kind="did", bus="can_c", confidence=CONFIDENCE_MES,
                default_rate_hz=channels_mod.MED_HZ, module=module, did=did_int,
                formula=formula, note=f"learned from MES; {e.get('source', '')}".strip("; ")))
    return out


__all__ = ["path", "accept", "reject", "learned", "CONFIDENCE",
          "accept_broadcast", "learned_broadcast", "UNSCALED",
          "record_did_answer", "learned_did_discovery",
          "CONFIDENCE_MES", "accept_mes", "reject_mes", "learned_mes", "learned_mes_channels"]
