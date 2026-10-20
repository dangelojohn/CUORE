# Testing

CUORE's tests are plain scripts, not a framework. Each is run with the project's virtual-environment interpreter, prints one line per check, and exits non-zero on failure.

## Where the tests are

| Directory | Count | Covers |
|---|---|---|
| `cuore/tests/check_*.py` | about 105 | Web app, API, live link (including a playback stream that needs no hardware), pages, bridges, scan log, guided scan, evidence, jobs, bulletins, labels, mobile page |
| `mes-log-mcp/tests/check_*.py` | about 31 | The MES library and MCP server, against the log corpus |
| `obd2-mcp/tests/` | 3 scripts | The MCP wrapper: client, readiness decoding, fixes |

A one-off example of running a check from the repository root:

```
.venv\Scripts\python.exe cuore\tests\check_fullscan.py
```

Run the relevant scripts once before a change is committed; a convention from the project's working notes is four or five focused checks per feature and one run of the whole suite per commit.

## How a check stays safe

- **Isolated state.** Each script sets `CUORE_STATE_DIR` (and `MES_LOG_DIR` where needed) to a temporary directory **before** importing the packages, so a check never reads or writes the real state directory.
- **No serial port.** Live-link checks use scripted or playback streams and fake adapters. A check never opens a serial port. A scripted adapter answers "OK" to any AT or ST command, which is why wire-sequence tests assert the exact command order instead.
- **No clock assumptions.** Tests never assume a "latest" timestamp from the live corpus; a test that reads `mtime` is brittle against clock skew and concurrent writes. Fixtures are used instead.
- **Fixtures from real data.** Several checks are built from copies of real observation lines and MES scan files, never the production files.

## Examples of what the checks guard

| Area | Examples |
|---|---|
| Live layer | active probe, 11-bit discovery, guided and coverage scans (including out-of-order cables), clearing (consent and read-back), mode 06 decoding, transport performance (multi-PID batching, held-session sweep, optional baud raise, pass-filter restore) |
| Evidence | job rules (the hypothesis status path), scan-health grading, the MIL (lamp) block, readiness |
| Bulletins | the cross-reference and scoring, mechanic-plan generation |
| Pages | dossier, job, tests, liveboard, gauges, media, drivetrain, electrical, maintenance, mobile theme, error pages and API contract |
| Marque port | a Maserati fixture check that `data-marque` is derived from the VIN |

## Gotchas

- **Headless browser.** On the development PC, plain headless `--dump-dom` and `--screenshot` do not work; page checks drive Edge over the DevTools Protocol and kill it by its temporary profile directory afterwards (`cuore/tests/_edge_cleanup.py`), otherwise processes leak.
- **Jinja.** A dictionary key named `items` is shadowed by the method `dict.items()`; each `*_routes.py` creates its own Jinja environment, so globals must be registered on each.
- **Uploads.** Starlette uploads are not FastAPI's subclass; code duck-types on `filename` and `read`.
- **MCP servers hold their code.** After editing `obd2-mcp/server.py` or `mes-log-mcp/server.py`, reload with `/mcp` before re-diagnosing.
- **One known flake.** One MES-library check ("vehicle name present") was flagged as a pre-existing, unrelated flake.

## Verification beyond unit tests

For code that reaches the car, a passing script is not proof. The project's pattern is to test against a fake stream, then verify on the car and record what was read (for example, the first real reads on 2026-10-13 found three problems no fake had shown: a gateway-silent bus, a legislated-OBD route that varied by day, and a filter reset that left every reply as NO DATA). Unverified-on-hardware items are labelled **UNVERIFIED** in the code and in [[Known Limitations and Open Issues|Known-Limitations-and-Open-Issues]].

Related: [[Architecture]], [[Safety Rules|Safety-Rules]].
