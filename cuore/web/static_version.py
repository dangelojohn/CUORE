"""Registers the ``static_url`` Jinja global on every template environment,
so a browser always loads the current CSS/JS instead of a stale cached copy.

``static_url(path)`` returns ``"/static/<path>?v=<hash>"`` where the hash is
derived from that file's mtime on disk -- the URL changes exactly when the
file changes, so a plain browser cache (no explicit no-cache headers) still
revalidates on a redeploy, and nothing has to bump a version number by hand.

Same trick ``cuore.web.experience_globals`` and ``cuore.web.icons`` use for
``experience_links`` / ``icon``, applied to a longer module list: those two
only register on the two ``Jinja2Templates`` instances their own features'
pages render through (``routes`` and ``service_routes``, found via
``drivetrain_routes`` and ``timeline_routes`` re-exporting ``routes``'s).
``static_url`` has to be safe on *every* page, and two more modules --
``labels_routes`` and ``media_routes`` -- build their own separate
``Jinja2Templates`` instance over the same template directory (see
``cuore.web.media_routes``'s own comment on this: "each a separate
environment over the same template directory"). Every page extends
``base.html``, which calls ``static_url`` for ``cuore.css``/``cuore.js`` etc,
so *all four* base instances need the global or those pages 500. Importing
this module is the side effect that does the registration; nothing here is
called directly. ``cuore.app`` imports it at module load time (see its own
import list), so including that import is what wires this in.
"""

from __future__ import annotations

import hashlib
import importlib
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"


def fonts_css_link() -> str:
    """``<link>`` for ``static/fonts/fonts.css`` when that file exists, else ``""``.
    The marque font files are owner-approved drops (static/fonts/README.txt); until
    they exist no stylesheet is linked, so nothing 404s and the --display /
    --numerals tokens in cuore.css fall through to the system stacks."""
    if (STATIC_DIR / "fonts" / "fonts.css").is_file():
        return f'<link rel="stylesheet" href="{static_url("fonts/fonts.css")}">'
    return ""


def static_url(path: str) -> str:
    """``"cuore.css"`` -> ``"/static/cuore.css?v=<hash of its mtime+size>"``.

    Falls back to a plain, unversioned ``/static/<path>`` if the file can't
    be stat'd (missing file, odd permissions, ...) -- a template global must
    never 500 a page just because a cache-buster couldn't be computed.
    """
    try:
        st = (STATIC_DIR / path).stat()
        digest = hashlib.sha1(f"{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()[:10]
        return f"/static/{path}?v={digest}"
    except OSError:
        return f"/static/{path}"


def code_watch_state() -> dict:
    """The live new-code alert's current state for ``_code_watch.html``'s no-JS render."""
    try:
        from ..live import poller as poller_mod
        return poller_mod.poller().status()["code_watch"]
    except Exception:  # noqa: BLE001 -- a banner must never 500 a page
        return {"enabled": False, "new": [], "count_new": 0}


def top_car_name(vin: str) -> str:
    """The name in the header for a page that has a car but no vehicle bar."""
    from ..services import shop_bridge
    try:
        return shop_bridge.resolve_vehicle_name(vin)
    except Exception:  # noqa: BLE001 -- the header must still render
        return ""


def local_ferrari_mark() -> bool:
    """True when the machine-only Ferrari mark is on disk (see data/brands.json)."""
    return (STATIC_DIR / "brand" / "ferrari-horse.svg").is_file()


def simulation_active() -> bool:
    """True while a SIMULATED live session runs (drives the site-wide banner)."""
    try:
        from ..live import poller as poller_mod
        st = poller_mod.poller().status()
        return bool(st.get("active") and st.get("simulation"))
    except Exception:  # noqa: BLE001 -- a banner must never 500 a page
        return False


def _register(templates: Any) -> None:
    templates.env.globals["static_url"] = static_url
    templates.env.globals["fonts_css_link"] = fonts_css_link
    templates.env.globals["code_watch_state"] = code_watch_state
    templates.env.globals["simulation_active"] = simulation_active
    templates.env.globals["local_ferrari_mark"] = local_ferrari_mark
    templates.env.globals["top_car_name"] = top_car_name
    from . import units as _units
    templates.env.filters["dist"] = _units.dist
    templates.env.filters["speed"] = _units.speed
    templates.env.globals["dist_unit"] = _units.dist_unit


# The four distinct ``Jinja2Templates`` instances in this package (``routes``
# and ``service_routes``, plus ``labels_routes`` and ``media_routes`` which
# each build their own) -- ``drivetrain_routes``/``timeline_routes`` are
# listed too, defensively, in case either ever stops re-exporting
# ``routes``'s; registering the same global twice on one object is harmless.
for _module_name in (
    "routes", "service_routes", "drivetrain_routes", "timeline_routes",
    "labels_routes", "media_routes", "owner_routes",
):
    try:
        _mod = importlib.import_module(f".{_module_name}", __package__)
        _tmpl = getattr(_mod, "templates", None) or getattr(_mod, "_shared_templates", None)
        if _tmpl is not None:
            _register(_tmpl)
    except Exception:  # noqa: BLE001 -- import-time side effect, must never raise
        pass


__all__ = ["static_url", "STATIC_DIR"]
