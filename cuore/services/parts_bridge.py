"""The only module in CUORE that imports :mod:`mes.parts`.

``mes-log-mcp/mes/parts.py`` is being written in parallel by another agent
and may not exist yet. Every call into it is wrapped and falls back to a
built-in fixture (shaped exactly like that module's documented contract --
see ``_FIXTURE`` below) so the parts page, the ``/api/parts*`` endpoints and
the part cards embedded in ``code.html``/``maintenance.html``/
``oil_change.html``/``brakes_tires.html`` are developable and testable
before it lands. Once ``mes.parts`` exists, nothing here needs to change --
the lazy import just starts succeeding and the fixture stops being reached.

Contract (``mes.parts``, once it lands): ``get(key)``, ``for_code(code)``,
``for_job(job)``, ``all()``, each returning / each row shaped::

    {key, name, what_it_does,
     oem: [{number, brand, note, confidence, source}],
     supersedes, aftermarket: [{brand, number, confidence, source}],
     fits, location, related_codes, related_jobs, torque_keys,
     price: {low, high, currency, as_of, source} | None,
     buy: [{label, url}],
     images: [{url, source_page, source_name, kind, licence_note, verified_at}],
     notes}

``torque_keys`` is a list of keys into the torque libraries -- resolved
here, not by ``mes.parts`` itself, against ``mes.service_specs`` and
``mes.drivetrain_specs`` (the same two libraries
``cuore.services.service_bridge`` already reaches through its own bridge),
so a part card can show "25 Nm, SINGLE-SOURCE" without ``mes.parts`` needing
to duplicate the torque library. A key neither library recognises resolves
to an UNKNOWN row rather than being dropped, so the card can say so.

Every public function here degrades to an empty result ("No part data yet")
rather than raising -- the one exception is :func:`part`, which returns
``None`` for an unknown key so the API layer can turn that into a 404.
"""

from __future__ import annotations

from typing import Any, Optional

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path


# --- lazy imports, each independently guarded ------------------------------

def _parts_mod():
    """``mes.parts``, or ``None`` if it has not landed yet."""
    try:
        from mes import parts as parts_mod
        return parts_mod
    except Exception:  # noqa: BLE001 -- must never be why a page 500s
        return None


def _service_specs():
    try:
        from mes import service_specs
        return service_specs
    except Exception:  # noqa: BLE001
        return None


def _drivetrain_specs():
    try:
        from mes import drivetrain_specs
        return drivetrain_specs
    except Exception:  # noqa: BLE001
        return None


def _model_for_vin(vin: Optional[str]) -> Optional[str]:
    """Best-effort model name for ``vin`` via ``mes.platform``, or ``None``
    on any failure or an unrecognised VIN -- never raises."""
    if not vin:
        return None
    try:
        from mes import platform as platform_mod
        model = platform_mod.model_for_vin(vin)
    except Exception:  # noqa: BLE001
        return None
    return None if model == "UNKNOWN" else model


# --- fixture: the exact shape mes.parts.get()/for_code()/for_job()/all()
# will return, used until that module lands (or for any key it does not yet
# cover). Keyed to things this corpus already knows about -- the Stelvio's
# chronic P0455/P0456 EVAP family (see project_stelvio_evap.md) and the jobs
# oil_change.html/maintenance.html/brakes_tires.html already render -- so a
# developer working on those pages sees real-looking cards immediately. ----

_FIXTURE: dict[str, dict[str, Any]] = {
    "esim": {
        "key": "esim",
        "name": "EVAP Service/Integrity Monitor (ESIM)",
        "what_it_does": "Pressurizes the fuel-vapor system and watches the "
                        "decay rate to detect small and large EVAP leaks. A "
                        "failed self-test or a failed component sets "
                        "P0455/P0456/P0457, not necessarily a leak itself.",
        "oem": [{"number": "68245527AA", "brand": "Mopar",
                 "note": "ESIM / natural-vacuum leak-detection pump assembly",
                 "confidence": "SINGLE-SOURCE",
                 "source": "https://www.stelvioforum.com/threads/evap-esim-replacement.21004/"}],
        "supersedes": [],
        "aftermarket": [{"brand": "Standard Motor Products", "number": "EVAP1234",
                         "confidence": "UNKNOWN", "source": None}],
        "fits": "Alfa Romeo Giulia/Stelvio 2.0T (2017-2022)",
        "location": "Rear of the fuel tank, inline on the vapor line, ahead of the canister.",
        "related_codes": ["P0455", "P0456", "P0457"],
        "related_jobs": ["evap_leak"],
        "torque_keys": ["evap_esim_mount"],
        "price": {"low": 180.0, "high": 260.0, "currency": "CAD",
                  "as_of": "2026-09-20", "source": "rockauto.com listing"},
        "buy": [{"label": "RockAuto", "url": "https://www.rockauto.com"},
                {"label": "Mopar eStore", "url": "https://www.moparonlineparts.com"}],
        "images": [{"url": "https://www.stelvioforum.com/data/esim-photo.jpg",
                    "source_page": "https://www.stelvioforum.com/threads/evap-esim-replacement.21004/",
                    "source_name": "stelvioforum.com", "kind": "product_photo",
                    "licence_note": "forum upload, fair-use reference only",
                    "verified_at": "2026-09-20"}],
        "notes": "Verified against TSB 18-030-17 before replacing -- that TSB's ECM "
                 "calibration read fixes a false P0456 on some build dates without "
                 "any part being replaced.",
    },
    "purge_valve": {
        "key": "purge_valve",
        "name": "EVAP Purge Solenoid Valve",
        "what_it_does": "Opens under ECM control to let engine vacuum draw stored fuel "
                        "vapor from the canister into the intake. Stuck closed or "
                        "leaking, it can contribute to a P0455/P0456 decay-rate failure.",
        "oem": [{"number": "68093419AA", "brand": "Mopar",
                 "note": "Purge valve/solenoid", "confidence": "SINGLE-SOURCE",
                 "source": "https://www.alfaowner.com/threads/purge-valve-location.9821/"}],
        "supersedes": ["68093419A (earlier casting, same fit)"],
        "aftermarket": [{"brand": "Four Seasons", "number": "PV1029",
                         "confidence": "CORROBORATED", "source": None}],
        "fits": "Alfa Romeo Giulia/Stelvio 2.0T (2017-2022)",
        "location": "Intake manifold, driver's side, short hose run to the charcoal canister.",
        "related_codes": ["P0455", "P0456"],
        "related_jobs": ["evap_leak"],
        "torque_keys": ["evap_purge_valve_mount"],
        "price": {"low": 45.0, "high": 90.0, "currency": "CAD",
                  "as_of": "2026-09-20", "source": "rockauto.com listing"},
        "buy": [{"label": "RockAuto", "url": "https://www.rockauto.com"}],
        "images": [],
        "notes": "",
    },
    "oil_filter": {
        "key": "oil_filter",
        "name": "Engine Oil Filter (cartridge element)",
        "what_it_does": "Traps combustion byproducts and wear metal out of circulating oil.",
        "oem": [{"number": "68105175AA", "brand": "Mopar", "note": "cartridge element + housing cap",
                 "confidence": "CONFIRMED",
                 "source": "https://www.stelvioforum.com/threads/oil-change-maintenance-reset.19336/"}],
        "supersedes": [],
        "aftermarket": [{"brand": "Mopar/Mann filter element", "number": "HU 711/51x",
                         "confidence": "CORROBORATED", "source": None}],
        "fits": "Alfa Romeo Giulia/Stelvio 2.0T MultiAir (2017-2022)",
        "location": "Top of the engine, cartridge-style housing with a plastic cap.",
        "related_codes": [],
        "related_jobs": ["oil_change"],
        "torque_keys": ["filter_cap"],
        "price": {"low": 18.0, "high": 32.0, "currency": "CAD",
                  "as_of": "2026-09-20", "source": "rockauto.com listing"},
        "buy": [{"label": "RockAuto", "url": "https://www.rockauto.com"}],
        "images": [],
        "notes": "",
    },
    "engine_air_filter": {
        "key": "engine_air_filter",
        "name": "Engine Air Filter",
        "what_it_does": "Keeps intake air clean of dust/debris ahead of the MAF/turbo.",
        "oem": [{"number": "68248729AA", "brand": "Mopar", "note": "panel element",
                 "confidence": "SINGLE-SOURCE", "source": None}],
        "supersedes": [],
        "aftermarket": [{"brand": "K&N", "number": "33-5061", "confidence": "UNKNOWN",
                         "source": None}],
        "fits": "Alfa Romeo Giulia/Stelvio 2.0T (2017-2022)",
        "location": "Airbox, passenger side of the engine bay.",
        "related_codes": [],
        "related_jobs": ["engine_air_filter"],
        "torque_keys": [],
        "price": None,
        "buy": [],
        "images": [],
        "notes": "",
    },
    "brake_pads_front": {
        "key": "brake_pads_front",
        "name": "Front Brake Pad Set",
        "what_it_does": "Friction material clamped onto the front rotors by the caliper.",
        "oem": [{"number": "68273809AA", "brand": "Mopar", "note": "front pad set",
                 "confidence": "SINGLE-SOURCE", "source": None}],
        "supersedes": [],
        "aftermarket": [{"brand": "Brembo", "number": "P23165", "confidence": "CORROBORATED",
                         "source": None}],
        "fits": "Alfa Romeo Giulia/Stelvio, base brakes (2017-2022)",
        "location": "Front calipers.",
        "related_codes": [],
        "related_jobs": ["brakes_front"],
        "torque_keys": ["caliper_slider_front"],
        "price": {"low": 90.0, "high": 160.0, "currency": "CAD",
                  "as_of": "2026-09-20", "source": "rockauto.com listing"},
        "buy": [{"label": "RockAuto", "url": "https://www.rockauto.com"}],
        "images": [],
        "notes": "",
    },
    "wheel_lug_bolts": {
        "key": "wheel_lug_bolts",
        "name": "Wheel Lug Bolts",
        "what_it_does": "Clamps the wheel to the hub.",
        "oem": [{"number": "68247068AA", "brand": "Mopar", "note": "lug bolt, M14",
                 "confidence": "CORROBORATED", "source": None}],
        "supersedes": [],
        "aftermarket": [],
        "fits": "Alfa Romeo Giulia/Stelvio (2017-2022)",
        "location": "Each wheel, five per corner.",
        "related_codes": [],
        "related_jobs": ["wheels"],
        "torque_keys": ["wheel_lug"],
        "price": None,
        "buy": [],
        "images": [],
        "notes": "",
    },
}


def _fixture_all() -> list[dict[str, Any]]:
    return list(_FIXTURE.values())


def _fixture_get(key: str) -> Optional[dict[str, Any]]:
    return _FIXTURE.get(key)


def _fixture_for_code(code: str) -> list[dict[str, Any]]:
    code = (code or "").strip().upper()
    return [p for p in _FIXTURE.values() if code in (p.get("related_codes") or [])]


def _fixture_for_job(job: str) -> list[dict[str, Any]]:
    job = (job or "").strip()
    return [p for p in _FIXTURE.values() if job in (p.get("related_jobs") or [])]


# --- torque resolution -------------------------------------------------------

def _resolve_torque(key: str) -> dict[str, Any]:
    """One ``torque_keys`` entry resolved against the torque libraries.

    Tries ``service_specs`` first, then ``drivetrain_specs`` -- the same
    order ``cuore.services.service_bridge`` implies by which module it
    reaches for which job. A key neither recognises still comes back as a
    row (UNKNOWN), never ``None`` -- a part card should be able to say
    "no torque spec found for evap_esim_mount" rather than silently drop it.
    """
    for specs in (_service_specs(), _drivetrain_specs()):
        if specs is None:
            continue
        lookup = getattr(specs, "torque_by_key", None)
        if lookup is None:
            continue
        try:
            row = lookup(key)
        except Exception:  # noqa: BLE001 -- a bad key must never 500 a part card
            row = None
        if row:
            return {
                "key": key,
                "component": row.get("component"),
                "value": row.get("value"),
                "unit": row.get("unit"),
                "display": row.get("display"),
                "angle": row.get("angle"),
                "single_use": row.get("single_use"),
                "confidence": row.get("confidence", "UNKNOWN"),
                "source": row.get("source"),
                "notes": row.get("notes"),
            }
    return {"key": key, "component": None, "value": None, "unit": None,
            "display": "UNKNOWN", "angle": None, "single_use": False,
            "confidence": "UNKNOWN", "source": None,
            "notes": "no torque spec found for this key -- use the service manual (TechAuthority)"}


_DEFAULTS: dict[str, Any] = {
    "name": "", "what_it_does": "", "oem": [], "supersedes": [],
    "aftermarket": [], "fits": "", "location": "", "related_codes": [],
    "related_jobs": [], "torque_keys": [], "price": None, "buy": [],
    "images": [], "notes": "",
}


def _enrich(raw: dict[str, Any]) -> dict[str, Any]:
    """Fill in any field the contract promises but a given row omits, and
    resolve ``torque_keys`` into a ``torques`` list of full spec rows."""
    out = dict(_DEFAULTS)
    out.update(raw)
    out["torques"] = [_resolve_torque(k) for k in (out.get("torque_keys") or [])]
    return out


# --- public API ---------------------------------------------------------

def part(key: str) -> Optional[dict[str, Any]]:
    """One part by key, enriched with resolved torques -- or ``None`` if no
    part by that key exists anywhere (real module or fixture).

    ``mes.parts.get()`` returns the record without the key folded in (it's
    the dict key the caller already has); the fixture's own rows carry
    ``key`` already. Either way the result below always has it.
    """
    if not key or not key.strip():
        return None
    mod = _parts_mod()
    try:
        raw = mod.get(key) if mod is not None else _fixture_get(key)
    except Exception:  # noqa: BLE001
        raw = None
    if not raw:
        return None
    raw = {"key": key, **raw}
    return _enrich(raw)


def _label_siblings(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for r in rows:
        sibling_of = r.get("sibling_of")
        if sibling_of:
            r["label"] = f"from {str(sibling_of).title()} parts: verify fit"
    return rows


def parts_for_code(code: str, vin: Optional[str] = None) -> list[dict[str, Any]]:
    """Every part related to a DTC -- ``[]`` if none are known, never an error.

    ``vin``, if given, resolves a model via ``mes.platform.model_for_vin``
    and (only against the real ``mes.parts`` module, which supports it --
    the fixture does not) threads ``include_siblings=True`` through so any
    sourced sibling-platform part rows are included too, labeled "from
    <Model> parts: verify fit".
    """
    if not code or not code.strip():
        return []
    mod = _parts_mod()
    include_siblings = bool(_model_for_vin(vin))
    try:
        if mod is not None:
            rows = mod.for_code(code, include_siblings=include_siblings)
        else:
            rows = _fixture_for_code(code)
    except Exception:  # noqa: BLE001
        rows = []
    return _label_siblings([_enrich(r) for r in (rows or [])])


def parts_for_job(job: str, vin: Optional[str] = None) -> list[dict[str, Any]]:
    """Every part related to a maintenance/service job -- ``[]`` if none.
    See :func:`parts_for_code` for ``vin``/``include_siblings`` behavior."""
    if not job or not job.strip():
        return []
    mod = _parts_mod()
    include_siblings = bool(_model_for_vin(vin))
    try:
        if mod is not None:
            rows = mod.for_job(job, include_siblings=include_siblings)
        else:
            rows = _fixture_for_job(job)
    except Exception:  # noqa: BLE001
        rows = []
    return _label_siblings([_enrich(r) for r in (rows or [])])


def all_parts() -> list[dict[str, Any]]:
    """Every part known -- the backing list for the parts page's search box.

    ``mes.parts.all()`` returns ``{key: record}`` (the key not folded into
    the record, same as ``get()``); the fixture's own ``_fixture_all()``
    already returns a list of rows each carrying ``key``.
    """
    mod = _parts_mod()
    try:
        if mod is not None:
            rows = [{"key": k, **v} for k, v in mod.all().items()]
        else:
            rows = _fixture_all()
    except Exception:  # noqa: BLE001
        rows = []
    return [_enrich(r) for r in (rows or [])]


def search_parts(q: str = "") -> list[dict[str, Any]]:
    """Case-insensitive substring match over name/key/what-it-does/OEM numbers."""
    rows = all_parts()
    q = (q or "").strip().lower()
    if not q:
        return rows
    out = []
    for p in rows:
        haystack = " ".join([
            p.get("key", ""), p.get("name", ""), p.get("what_it_does", ""),
            " ".join(o.get("number", "") or "" for o in p.get("oem", [])),
        ]).lower()
        if q in haystack:
            out.append(p)
    return out


__all__ = ["part", "parts_for_code", "parts_for_job", "all_parts", "search_parts"]
