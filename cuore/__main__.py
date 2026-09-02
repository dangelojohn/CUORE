"""Entry point: ``python -m cuore``.

    .venv/Scripts/python.exe -m cuore --profile bench --port 5000

CLI flags win over ``CUORE_*`` environment variables, which win over the
defaults in :mod:`cuore.config`. Log-corpus locations are not settable here --
they belong to ``MES_LOG_DIR`` / ``MES_LOG_DIRS``, and having two ways to set
one thing is how they end up disagreeing.
"""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__, bootstrap  # noqa: F401  -- side effect: sys.path
from .config import load
from .profiles import Profile


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="cuore",
        description="Companion service over the MES diagnostic toolchain.",
    )
    parser.add_argument("--profile", choices=[p.value for p in Profile],
                        default=None,
                        help="bench (log corpus, this PC) or drive (in-car "
                             "node). Default: bench.")
    parser.add_argument("--host", default=None,
                        help="Bind address. Default 127.0.0.1. Use 0.0.0.0 to "
                             "serve the shop LAN -- set --token as well.")
    parser.add_argument("--port", type=int, default=None,
                        help="Default 5000.")
    parser.add_argument("--token", default=None,
                        help="Shared secret required on every request.")
    parser.add_argument("--reload", action="store_true", default=None,
                        help="Development autoreload. Not for the drive node.")
    parser.add_argument("--version", action="version",
                        version=f"cuore {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )

    settings = load(profile=args.profile, host=args.host, port=args.port,
                    token=args.token, reload=args.reload)

    import uvicorn

    # Passing the import string rather than the app object is what makes
    # --reload work; without it uvicorn has nothing to re-import.
    uvicorn.run(
        "cuore.asgi:app" if settings.reload else create_app_instance(settings),
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_config=None,          # keep the format configured above
        access_log=True,
    )
    return 0


def create_app_instance(settings):
    """Build the app eagerly, for the non-reload path."""
    from .app import create_app
    return create_app(settings)


if __name__ == "__main__":
    sys.exit(main())
