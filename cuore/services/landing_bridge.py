"""The landing page's car list: every car CUORE knows, one dict per car.

A car is *known* when any of these mention its VIN: a real (non-simulated)
MES log, an intake visit, or a job. Nothing here touches the adapter; it only
reads what CUORE already holds, so a card can say how old its facts are.

Facts about a car (make, model year, line art) are decoded from the VIN or read
from data files -- brands live in data/brands.json and nothing is named per
brand in code or template, so the same pages serve any marque.

Honest wording rule (same as the rest of CUORE): silence is never "clean". A
car CUORE has never read is shown as ``NOT READ``, and a clean verdict always
says it is as of the last read.
"""

from __future__ import annotations

import json
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import cache, dossier_bridge, flow_bridge, mes_bridge

_STATIC = Path(__file__).resolve().parents[1] / "web" / "static"

_DATA = Path(__file__).resolve().parents[1] / "data"


@lru_cache(maxsize=1)
def brands() -> list[dict[str, Any]]:
    """The brand picker, in display order, from ``data/brands.json``. Each
    entry gains ``mark_url`` (None when the mark file is not on disk)."""
    try:
        raw = json.loads((_DATA / "brands.json").read_text(encoding="utf-8")).get("brands") or []
    except (OSError, ValueError):
        raw = []
    out = []
    for b in raw:
        f = next((m for m in (b.get("mark_local"), b.get("mark")) if m and (_STATIC / "brand" / m).is_file()), "")
        lm = b.get("landing_mark") or ""
        out.append(dict(b, mark_url=f"/static/brand/{f}" if f else None,
                        landing_url=f"/static/brand/{lm}" if lm and (_STATIC / "brand" / lm).is_file() else None))
    return out


def brand(key: str) -> dict[str, Any] | None:
    return next((b for b in brands() if b["key"] == key), None)


#: verdict state -> (rank, word). Lower rank = worse = sorted first.
#: The words are for a *card*: they say what was last read, never "all good".
_STATES: dict[str, tuple[int, str]] = {
    "ACTIVE_FAULTS": (0, "Active faults"),
    "UNVERIFIED_REPAIR": (1, "Unverified repair"),
    "NO_DATA": (2, "NOT READ"),
    "VERIFIED_CLEAN": (3, "Verified clean at last read"),
}

#: ISO 3779 model-year letters for VIN position 10 (I, O, Q, U, Z, 0 unused), 1980 cycle.
_YEAR_CODES = "ABCDEFGHJKLMNPRSTVWXY123456789"


def model_year(vin: str) -> int | None:
    """Model year from VIN position 10, or None. The code repeats every 30
    years; the latest year not beyond next year is taken (no pre-1980 cars)."""
    if len(vin) != 17:
        return None
    i = _YEAR_CODES.find(vin[9].upper())
    if i < 0:
        return None
    limit = datetime.now().year + 1
    year = 1980 + i
    while year + 30 <= limit:
        year += 30
    return year


def short_vin(vin: str) -> str:
    return f"…{vin[-6:]}" if len(vin) > 8 else vin


def _model_slug(name: str) -> str:
    """Last word of the vehicle name, lowercased -- the photo file name
    convention in static/brand/README-images.txt (same as the hero band)."""
    words = (name or "").split()
    return "".join(ch for ch in words[-1].lower() if ch.isalnum()) if words else ""


@lru_cache(maxsize=16)
def _side_art(slug: str) -> dict[str, str] | None:
    """The traced side-view line art for a model (data/car_art/<slug>-*.json),
    or None when that model has none -- a card without art is left clean,
    never given a stand-in drawing."""
    for f in sorted((_DATA / "car_art").glob(f"{slug}-*.json")) if slug else []:
        try:
            side = json.loads(f.read_text(encoding="utf-8")).get("side") or {}
        except (OSError, ValueError):
            continue
        if side.get("ink"):
            return {"ink": side["ink"], "silhouette": side.get("silhouette") or ""}
    return None


def _art(vin: str, name: str) -> dict[str, str] | None:
    """Model from the VIN rule when it is sure; else the stored card's model
    field; else the words of the name read from the end, skipping a trailing
    model year ("Maserati Grecale 2023" -> grecale). Only a model that has
    art files can match, so any other model gets no drawing."""
    try:
        from mes import platform as _plat
        model = _plat.model_for_vin(vin).lower()
    except Exception:  # noqa: BLE001
        model = ""
    if model.isalnum() and model != "unknown":
        return _side_art(model)
    try:
        from . import car_identify
        card = car_identify.get_card(vin) or {}
        raw = (card.get("fields") or {}).get("model")
        raw = raw.get("value") if isinstance(raw, dict) else raw
        art = _side_art(_model_slug(str(raw or "")))
        if art:
            return art
    except Exception:  # noqa: BLE001
        pass
    for word in reversed((name or "").split()):
        slug = "".join(ch for ch in word.lower() if ch.isalnum())
        if slug.isdigit():
            continue
        art = _side_art(slug)
        if art:
            return art
    return None


from . import demo_cars as demo_cars_mod  # noqa: E402


def _verdict(vin: str, has_logs: bool) -> dict[str, Any]:
    """State word for a card. Reuses the cached workup + view the Bench uses,
    so a card can never disagree with the page it opens."""
    from . import demo_cars   # an invented showcase car has its own demo dossier, not logs
    if not has_logs and not demo_cars.is_demo(vin):
        return {"state": "NO_DATA", "rank": 2, "word": "NOT READ",
                "detail": "No codes have been read from this car yet.", "not_read": 0}
    try:
        dossier = cache.get_or_build(("workup", vin, mes_bridge.newest_mtime(vin)),
                                     lambda: mes_bridge.workup(vin=vin))
        verdict = dossier_bridge.build_view(vin, dossier, None)["verdict"]
    except Exception:  # noqa: BLE001 -- one broken car must not blank the landing page
        return {"state": "NO_DATA", "rank": 2, "word": "NOT READ",
                "detail": "CUORE could not work out this car's state.", "not_read": 0}
    state = verdict.get("state") or "NO_DATA"
    rank, word = _STATES.get(state, (2, "NOT READ"))
    n_unread = len(verdict.get("not_read") or [])
    detail = verdict.get("summary") or ""
    if state == "NO_DATA":
        detail = "Nothing open and no clear on file."
    return {"state": state, "rank": rank, "word": word, "detail": detail, "not_read": n_unread}


def _open_jobs(vin: str) -> list[dict[str, Any]]:
    try:
        from mes import jobs as jobs_mod
        return list(jobs_mod.open_jobs(vin))
    except Exception:  # noqa: BLE001
        return []


def _gather() -> dict[str, dict[str, Any]]:
    """vin -> raw facts from the three places a car can be mentioned."""
    cars: dict[str, dict[str, Any]] = {}

    def rec(vin: str) -> dict[str, Any]:
        return cars.setdefault(vin, {"vin": vin, "name": "", "last_seen": "", "logs": 0,
                                     "in_bay": False, "complaint": ""})

    try:
        for v in mes_bridge.vehicles(real_only=True):
            r = rec(v["vin"])
            r["name"] = (v.get("names") or [""])[0]
            r["last_seen"] = max(r["last_seen"], v.get("last_seen") or "")
            r["logs"] = v.get("real_logs") or 0
    except Exception:  # noqa: BLE001
        pass
    shop = flow_bridge._shop_mod()
    if shop is not None:
        try:
            for visit in shop.load():
                vin = (visit.get("vin") or "").strip()
                if not vin:
                    continue
                r = rec(vin)
                r["name"] = r["name"] or visit.get("vehicle") or ""
                r["last_seen"] = max(r["last_seen"], (visit.get("in_at") or "").replace("T", " "))
                if visit.get("status") != "out":
                    r["in_bay"] = True
                    r["complaint"] = visit.get("complaint") or r["complaint"]
        except Exception:  # noqa: BLE001
            pass
    jobs = flow_bridge._jobs_mod()
    if jobs is not None:
        try:
            for job in jobs.load():
                vin = (job.get("vin") or "").strip()
                if vin and job.get("status") != "closed":
                    rec(vin)
        except Exception:  # noqa: BLE001
            pass
    return cars


def cars(query: str = "", marque: str = "") -> list[dict[str, Any]]:
    """Known cars, ready for a card; ``marque`` keeps one brand (by VIN rule),
    ``query`` filters by VIN or name.

    Order: the car in the bay first, then the worst state, then the most
    recently seen -- the car that needs a technician is never below the fold.
    """
    q = (query or "").strip().lower()
    out: list[dict[str, Any]] = []
    for vin, r in _gather().items():
        if marque and mes_bridge.marque_for_vin(vin) != marque:
            continue
        name = r["name"] or vin
        if q and q not in vin.lower() and q not in name.lower():
            continue
        verdict = _verdict(vin, r["logs"] > 0)
        jobs = _open_jobs(vin)
        out.append({
            "vin": vin, "short_vin": short_vin(vin), "name": name, "marque": mes_bridge.marque_for_vin(vin),
            "make": (brand(marque) or {}).get("name", ""), "year": model_year(vin),
            "last_seen": r["last_seen"], "in_bay": r["in_bay"],
            "complaint": (jobs[0].get("complaint") if jobs else "") or r["complaint"],
            "open_jobs": len(jobs), "verdict": verdict, "art": _art(vin, name),
            "demo": demo_cars_mod.is_demo(vin),
        })
    out.sort(key=lambda c: (not c["in_bay"], c["verdict"]["rank"], _neg(c["last_seen"])))
    return out


def _neg(stamp: str) -> tuple[int, ...]:
    """Sort key putting newer stamps first without parsing: invert each char."""
    return tuple(-ord(ch) for ch in stamp)


def counts() -> dict[str, int]:
    """Cars known per marque key (cheap: no verdicts)."""
    n: dict[str, int] = {}
    for vin in _gather():
        k = mes_bridge.marque_for_vin(vin)
        n[k] = n.get(k, 0) + 1
    return n
