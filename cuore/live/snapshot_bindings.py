"""Snapshot (UDS 19 04) field scaffolds and owner bindings for modules whose
DID layout is not yet known (ABS first).

Nothing here is a layout. A scaffold lists the *names* a module's own
freeze frame is known to carry, anchored to a MultiEcuScan decode, with every
DID, length and scale left ``None`` and status ``"unbound"``. The only way a
DID gets a name is :func:`bind`, called by the owner after comparing a live
19 04 reply with the same freeze frame shown by MES. Proposals
(:func:`propose`) pair a parsed DID record with candidate names by byte length
and plausible range; they are suggestions (status ``"proposed"``) and are never
written to the bindings file.

Read-only: this module never touches the adapter. Bindings live in
``<state_dir>/snapshot_bindings.json`` (C:\\ProgramData\\cuore on the car PC):
``{vin: {module: {"1234": {name, length, unit, mul, div, offset, bound_at}}}}``.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .config import state_dir
from .errors import BadCommand

BOUND_STATUS = "bound (owner)"
_LOCK = threading.Lock()


def bindings_path() -> Path:
    return state_dir() / "snapshot_bindings.json"


# --- scaffolds ------------------------------------------------------------------------

_ABS_ANCHOR = (
    "MultiEcuScan log FESLog_2609042001 (C:\\Program Files (x86)\\MultiEcuScan, 2026-09-04, "
    "Continental ABS MK C1, VIN ZASFAKPN5J7B88115): per-code environmental data. "
    "C104B-92: operating time 330849 min, startups 14356, brake pedal switch ON, brake contact 2 ON, "
    "parking brake Released, battery 12.1 V, speed 0.000 km/h, hydraulic circuit pressure 11.1 bar, "
    "brake pedal pressure 3.6 bar. U1700-87: operating time 329228 min, startups 14280, switches OFF, "
    "battery 10.6 V, speed 0.000 km/h, hydraulic 2.6 bar, pedal 0.0 bar. MES also shows dynamic control "
    "selector, reversing status, ASR/ESP switch and operating mode; not in this scaffold.")

# name, unit, plausible (lo, hi) in `unit`, candidate raw lengths (None = any), note.
# Ranges are sanity bounds for suggestions only, not scales.
_ABS_FIELDS: tuple[tuple[str, Optional[str], Optional[tuple[float, float]], tuple[int, ...], str], ...] = (
    ("Operating time", "min", (0, 4_000_000), (3, 4), "MES 330849 / 329228 min"),
    ("Startups counter", None, (0, 100_000), (2, 3), "MES 14356 / 14280"),
    ("Brake switches", None, (0, 255), (1,),
     "MES brake pedal switch, brake contact 2, parking brake: ON/OFF/Released states, probably bit flags"),
    ("Battery voltage", "V", (6, 18), (1, 2), "MES 12.1 / 10.6 V"),
    ("Vehicle speed", "km/h", (0, 350), (1, 2), "MES 0.000 km/h in both records"),
    ("Hydraulic circuit pressure", "bar", (0, 250), (1, 2), "MES 11.1 / 2.6 bar"),
    ("Brake pedal pressure", "bar", (0, 250), (1, 2), "MES 3.6 / 0.0 bar"),
)
_DIVISORS = (1, 10, 100)


def _scaffold(anchor: str, rows: Any) -> list[dict[str, Any]]:
    return [{"name": n, "unit": u, "did": None, "length": None, "scale": None, "status": "unbound",
             "mes_example": note, "anchor": anchor} for n, u, _r, _l, note in rows]


SCAFFOLDS: dict[str, list[dict[str, Any]]] = {"ABS": _scaffold(_ABS_ANCHOR, _ABS_FIELDS)}
_RANGES = {"ABS": {n: (rng, lens) for n, _u, rng, lens, _note in _ABS_FIELDS}}


def scaffold(module: str) -> list[dict[str, Any]]:
    return [dict(f) for f in SCAFFOLDS.get(module.upper(), [])]


def has_scaffold(module: str) -> bool:
    return module.upper() in SCAFFOLDS


# --- persistence ----------------------------------------------------------------------

def _load() -> dict[str, Any]:
    try:
        d = json.loads(bindings_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def bindings_for(vin: Optional[str], module: str) -> dict[int, dict[str, Any]]:
    """``{did_int: binding}`` for this car and module (empty without a VIN)."""
    if not vin:
        return {}
    raw = (_load().get(vin.upper()) or {}).get(module.upper()) or {}
    out: dict[int, dict[str, Any]] = {}
    for k, v in raw.items():
        try:
            out[int(k, 16)] = v
        except ValueError:
            continue
    return out


def bind(vin: str, module: str, did: str, field_name: str, *, length: Optional[int] = None,
         unit: Optional[str] = None, mul: int = 1, div: Optional[int] = None,
         offset: float = 0) -> dict[str, Any]:
    """Owner binds one snapshot DID to a field name. Nothing is inferred: a
    ``length``/``div`` the owner does not supply stays ``None`` (raw bytes kept,
    value withheld). Saved to snapshot_bindings.json and used by the decoder."""
    vin = (vin or "").strip().upper()
    module = (module or "").strip().upper()
    if len(vin) != 17:
        raise BadCommand("vin must be 17 characters")
    if not module:
        raise BadCommand("module is required")
    try:
        did_int = int((did or "").strip(), 16)
    except ValueError:
        raise BadCommand(f"did must be hex, got {did!r}")
    if not 0 <= did_int <= 0xFFFF:
        raise BadCommand("did must be 0000..FFFF")
    names = [f["name"] for f in SCAFFOLDS.get(module, [])]
    if names and field_name not in names:
        raise BadCommand(f"{module} field_name must be one of {names}")
    if not names and not (field_name or "").strip():
        raise BadCommand("field_name is required")
    if length is not None and not 1 <= int(length) <= 32:
        raise BadCommand("length must be 1..32 bytes")
    if div is not None and int(div) == 0:
        raise BadCommand("div must not be 0")
    entry = {"name": field_name, "length": int(length) if length is not None else None,
             "unit": unit, "mul": int(mul), "div": int(div) if div is not None else None,
             "offset": offset, "status": BOUND_STATUS,
             "bound_at": datetime.now().isoformat(timespec="seconds")}
    with _LOCK:
        data = _load()
        mods = data.setdefault(vin, {}).setdefault(module, {})
        # one name -> one DID: re-binding a name moves it
        for k in [k for k, v in mods.items() if v.get("name") == field_name and k != f"{did_int:04X}"]:
            del mods[k]
        mods[f"{did_int:04X}"] = entry
        p = bindings_path()
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, p)
    return {"vin": vin, "module": module, "did": f"{did_int:04X}", **entry}


def unbound_names(module: str, vin: Optional[str]) -> list[str]:
    bound = {b["name"] for b in bindings_for(vin, module).values()}
    return [f["name"] for f in SCAFFOLDS.get(module.upper(), []) if f["name"] not in bound]


# --- suggestions ----------------------------------------------------------------------

def propose(module: str, identifiers: list[dict[str, Any]], vin: Optional[str] = None
            ) -> list[dict[str, Any]]:
    """One entry per parsed (not yet bound) DID record: ``{did, length, raw, bytes,
    candidates:[{name, status:"proposed", fits, why}]}``. Pairing is by byte length
    and by whether the raw value, at divisor 1, 10 or 100, lies inside the field's
    plausible range. A suggestion to check against MES, never a binding."""
    ranges = _RANGES.get(module.upper())
    if not ranges:
        return []
    free = set(unbound_names(module, vin))
    out: list[dict[str, Any]] = []
    for ident in identifiers:
        if ident.get("status") == BOUND_STATUS:
            continue
        b = ident.get("bytes") or []
        raw = int("".join(b), 16) if b else 0
        cands = []
        for name, (rng, lens) in ranges.items():
            if name not in free or len(b) not in lens:
                continue
            fits = [d for d in _DIVISORS if rng[0] <= raw / d <= rng[1]]
            if not fits:
                continue
            cands.append({"name": name, "status": "proposed", "fits_divisor": fits,
                          "why": f"{len(b)} byte(s), raw {raw} within {rng[0]:g}..{rng[1]:g} "
                                 f"at divisor {fits}; suggestion only"})
        out.append({"did": ident.get("did"), "length": len(b), "raw": raw, "bytes": b,
                    "candidates": cands})
    return out
