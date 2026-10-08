# Methods and gotchas

- Tests: plain scripts `cuore/tests/check_*.py`, `mes-log-mcp/tests/check_*.py`, `obd2-mcp/tests/check_*.py`; each sets CUORE_STATE_DIR to a temp dir before importing cuore and never writes to C:\ProgramData\cuore. Run them all once before a commit: `for t in ...; do .venv/Scripts/python.exe $t; done`.
- Headless Edge on this PC: `--dump-dom` and `--screenshot` do not work; drive Edge over the DevTools Protocol (pattern in `cuore/tests/check_live_widgets.py`) and kill it by its temp `--user-data-dir` with `cuore/tests/_edge_cleanup.py`, otherwise processes leak (266 found once).
- Verifying links: YouTube via oEmbed; forums and part sites block plain HTTP (202 bot wall or 403), so verify by opening the page in headless Edge and reading the title and first post, or the product image's natural size.
- Jinja: a dict key named `items` is shadowed by `dict.items()`; use bracket access or rename. Each `*_routes.py` module creates its own Jinja environment, so Jinja globals must be registered on each (see `experience_globals.py`, `timeline_routes.py`).
- Starlette uploads arrive as `starlette.datastructures.UploadFile`, not FastAPI's subclass; duck-type on `filename`/`read`.
- CUORE health endpoint: `/api/health`. The keep-alive identifies cuore by the health body. `cmd /c` needs extra outer quotes.
- Owner's manual (2018 US Stelvio, Mopar PDF) is a CONFIRMED source; decode the maintenance plan's bullet columns by character x-position.
- MES language files hold only description fragments; the code-to-text map is in MES's encrypted database (left alone).
- Git: agent-driven `git push` is blocked by the permission classifier; the owner approves a direct `git push github main`. Remote `forge` is unrelated; never push there.
- PDF sheets: reportlab in the project venv; render with pypdfium2 and look at the PNG; one US Letter page each; generators live in `docs/vehicles/<VIN>/pdf-sources/`.
