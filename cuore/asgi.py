"""Import target for ASGI servers: ``uvicorn cuore.asgi:app``.

Used by ``--reload`` (uvicorn needs an import string to re-import on change)
and by any external server that wants to host the app directly.

**Configuration here comes from the environment only.** A reloading worker is a
fresh process that never saw the parent's ``argv``, so CLI flags cannot reach
it. Under ``--reload``, set ``CUORE_PROFILE`` / ``CUORE_HOST`` / ``CUORE_PORT``
/ ``CUORE_TOKEN`` instead -- or drop ``--reload`` and the flags apply normally.
"""

from __future__ import annotations

from . import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path
from .app import create_app  # noqa: E402

app = create_app()
