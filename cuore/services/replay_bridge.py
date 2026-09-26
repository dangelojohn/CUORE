"""The only place the live replay reaches into ``mes`` (CSV parsing and the
MES recordings directory). Kept thin: :mod:`cuore.live.replay` does the
pacing and message shaping; this module just exposes the parser."""
from __future__ import annotations

from .. import bootstrap  # noqa: F401  -- side effect: puts `mes` on sys.path

from mes import csvlog, paths as mes_paths  # noqa: E402
from mes.errors import MesError  # noqa: E402

load_csv = csvlog.load_csv
iter_csv_files = mes_paths.iter_csv_files
resolve_csv = mes_paths.resolve_csv

__all__ = ["load_csv", "iter_csv_files", "resolve_csv", "MesError"]
