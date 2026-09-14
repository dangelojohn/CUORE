# CUORE live-link survey - read-only code review

Primary inputs: `C:\Users\User\mcp-servers\cuore`, `C:\Users\User\mcp-servers\obd2-mcp\server.py`,
`C:\Users\User\Documents\stelvio_scan\src\stelvio_scan`, plus `C:\Users\User\mcp-servers\docs\`.

---

## 1. CUORE architecture

### Entry / factory / registration

| Concern | Location |
|---|---|
| CLI entry `python -m cuore` | `C:\Users\User\mcp-servers\cuore\__main__.py:45-78` - argparse (`--profile/--host/--port/--token/--reload`), then `uvicorn.run()`; reload path passes the import string `cuore.asgi:app` (`__main__.py:61`) |
| ASGI target | `cuore\asgi.py:17` - `app = create_app()`, env-only config |
| App factory | `cuore\app.py:50-112` - `create_app(settings=None)`, idempotent, used directly by tests |
| Lifespan | `app.py:54-64` - logs profile/bind, warns on `unguarded_lan` |
| Error handlers | `app.py:82-98` - `BridgeError` -> `exc.status`, `MesError` -> 400; `_render_failure` branches on `request.url.path.startswith("/api")` to return JSON vs. an HTML error page |
| Router registration | `app.py:101-106` - `include_router(<mod>.router, prefix="/api")` for `system, vehicles, reference, recordings, logs`, then `web_routes.router` unprefixed; `app.mount("/static", ...)` at `app.py:108` |
| `sys.path` bootstrap | `cuore\bootstrap.py` - `MES_ROOT` (`mes-log-mcp`) inserted at `bootstrap.py:33-40`; **`OBD_ROOT = REPO_ROOT / "obd2-mcp"` already declared at `bootstrap.py:30`** with the comment "recorded here so the P2 live path has one authoritative answer" |

### Config

`cuore\config.py:29-67`. Pydantic-settings `BaseSettings`, `env_prefix="CUORE_"`, `.env` file,
`extra="ignore"`. Fields: `profile, host (127.0.0.1), port (5000), token (""), reload`.
Properties `lan_exposed` (`config.py:59`) and `unguarded_lan` (`config.py:64`).
`load(**overrides)` at `config.py:70-77` drops `None` so unset CLI flags fall through to env.

**There is no serial/port/baud setting anywhere in cuore today** - a live layer must add
`CUORE_OBD_PORT`, `CUORE_OBD_BAUD`, `CUORE_LIVE_ENABLED`, etc. here. Note the existing doctrine
at `config.py:16-19`: things owned by another subsystem (MES log roots) are deliberately *not*
duplicated in `Settings`. By that rule port/baud should keep the obd2 precedence chain
*argument -> env -> MES registry*, with cuore settings only as the "argument" tier.

### Profiles and capability flags

`cuore\profiles.py`:

- `Profile` enum `BENCH`/`DRIVE` (`profiles.py:19-23`).
- `FEATURES` closed tuple (`profiles.py:28-40`) - `live_obd` line 36, `live_can` line 37,
  `drive_recorder` line 38, `actuators` line 39, each annotated with its phase.
- `_BENCH` dict `profiles.py:43-55` (all four live flags `False`, lines 51-54);
  `_DRIVE` dict `profiles.py:61-73` (lines 68-72).
- `features_for(profile)` `profiles.py:81-89` returns a **fresh dict by value**, with the explicit
  comment that a caller may overlay runtime state. That is the designed hook: the live layer
  overlays `features["live_obd"] = adapter_reachable` exactly the way `api/system.py:50-53`
  already overlays corpus features *down* when the corpus is unreachable.

### Models

`cuore\models.py`:

- `CorpusInfo` (`models.py:23-36`)
- **`AdapterInfo` (`models.py:39-51`)** - `present: bool = False`, `port: str | None`,
  `blocked_by: str | None`, `note: str = "live link not built yet (P2)"`. The docstring explicitly
  says `blocked_by` exists so "the P2 interlock has somewhere to say MES holds the port".
  This maps 1:1 onto `mes_status()["state"] == "connected"` and onto the advisory lock holder
  in obd2-mcp.
- `Capabilities` (`models.py:54-68`) - `profile, version, features, corpus, adapter, lan_exposed,
  authenticated`
- `Health` (`models.py:71-78`), `ErrorBody` (`models.py:81-86`),
  `Measurement`/`MeasurementType` (`models.py:89-107`), `VerdictRequest` (`models.py:110-128`).
- Deliberate policy (`models.py:1-11`): library payloads are returned as raw dicts; only contracts
  CUORE *owns* get Pydantic models. A live layer owns its own contract, so `LiveStatus`, `BusInfo`,
  `UdsReadResult`, `CaptureSession` **should** be modelled here (or in `cuore/live/models.py`).

### What `/api/capabilities` returns today

`cuore\api\system.py:40-63`. Shape:

```json
{"profile":"bench","version":"0.1.0",
 "features":{"corpus":true,"workup":true,"fault_tree":true,"verdict":true,
             "modules":true,"recordings":true,"log_read":true,
             "live_obd":false,"live_can":false,"drive_recorder":false,"actuators":false},
 "corpus":{"...CorpusInfo..."},
 "adapter":{"present":false,"port":null,"blocked_by":null,
            "note":"live link not built yet (P2)"},
 "lan_exposed":false,"authenticated":false}
```

`adapter=AdapterInfo()` is hard-coded at `api/system.py:60` - that single line is where live
adapter state gets wired in. `_corpus_info()` at `api/system.py:22-37` is the pattern to copy for
an `_adapter_info()` that never raises.

Other system routes: `/api/health` (`system.py:66-71`, includes `cache.stats()`),
`/api/status` (`system.py:74-77`), `/api/roots` (`system.py:80-82`).

### mes_bridge pattern

`cuore\services\mes_bridge.py` (598 lines). "The only module in CUORE that imports `mes`"
(`mes_bridge.py:1`). Rules it establishes, and which a `live_bridge` must follow:

- routers never import the domain library; they call free functions in the bridge
  (`mes_bridge.py:46-598`);
- the bridge translates "no result" into `NotFound`/`BadRequest` from `services/errors.py` rather
  than returning an `{"error": ...}` dict (`errors.py:1-34`, statuses 404/400/**503 `Unavailable`**
  - already the right code for "live link not available / MES holds the port");
- it mirrors the MCP tool surface call-for-call so the two cannot drift (`mes_bridge.py:3-6`).
  The same doctrine says the new live MCP tools and the new `/api/live/*` routes must both call
  one `cuore.live` module.

Representative functions: `corpus_status` (46), `log_roots` (51), `vehicles` (63),
`newest_mtime` (77), `list_logs` (86), `read_log` (102, the path-containment boundary),
`search_logs` (141), `workup` (183), `extract_dtcs` (232), `freeze_frames` (269),
`actuator_history` (313), `fault_tree` (423), `assess_verdict` (441), `open_codes_for` (458),
`module_registry` (499), `list_recordings` (531).

### Cache

`cuore\services\cache.py`: module-level `OrderedDict` LRU, `MAX_ENTRIES = 16` (`cache.py:26`),
`get_or_build(key, build)` (`cache.py:31-44`), `clear()` (47), `stats()` (`cache.py:52`) surfaced
in `/api/health`. Keys embed a freshness token (newest mtime).
**Live data must not use this cache** - the key discipline ("key must include whatever makes the
value stale") has no analogue for a live bus read.

### Auth / token handling

`cuore\api\deps.py`. `settings_of(request)` reads `request.app.state.settings`
(`deps.py:22-24`, set at `app.py:75`). `require_token` (`deps.py:27-49`) accepts `X-Cuore-Token`
header or `?token=`, `hmac.compare_digest`, no-op when the token is empty, 401 with
`WWW-Authenticate: Token`. Applied as a **router-level dependency**:
`dependencies=[Depends(require_token)]` on every router (`api/system.py:19`, `vehicles.py:19`,
`reference.py:17`, `recordings.py:19`, `logs.py:28`, `web/routes.py:44-45`). A live router must do
the same - and arguably needs a *second*, stronger gate for anything that touches the bus.

### Web surface

`cuore\web\routes.py` (269 lines) - Jinja2 pages that are *clients of the bridge*, never a second
implementation (`routes.py:1-6`). `_page()` helper (51-56), `error_page()` (59-72) used by the
app's exception handlers, `_dossier()` cached workup (75-80), `_vehicle_bar()` (83-106). Pages:
`/` (112), `/v/{vin}` (122), `/codes` (132), `/code/{code}` (144), `/tree` (158), `/gate` GET (169)
and POST (182, hand-parsed parallel `m_*` fields so the form degrades without JS), `/modules`
(234), `/recordings` (241), `/recording/{name}` (247), `/logs` (262).
`web/templates/modules.html:66-72` already tells the technician that only Bus A (pins 6/14) is
reachable without cables - the bus story has a UI home already.

### Tests

`cuore\tests\check_api.py` (287 lines). Plain script, `sys.exit(1)` on failure, no pytest/mocks/
fixtures; the real MES corpus is the fixture (`check_api.py:1-11`). `TestClient(create_app())` at
line 40; a `check(label, cond, detail)` counter at lines 33-37. Notably it **pins the live flags to
False today** - `check_api.py:50-53` assert `live_obd`, `drive_recorder`, `actuators` are `False`
and `adapter.present is False`. **Those four assertions must be rewritten when the live layer
lands, not silently broken.** Containment regression block at lines 208-241; auth block at 263-276.

obd2-mcp uses the identical style (`obd2-mcp\tests\test_fixes.py`, `test_readiness.py` - plain
scripts importing `server as s`, no hardware, `check(label, got, want)`).

### Requirements

`cuore\requirements.txt`: fastapi>=0.115, uvicorn>=0.30 (plain, not `[standard]`, deliberately -
comment at lines 7-10), **websockets>=12 ("the one extra the live stream will use at P3",
currently unused)**, jinja2>=3.1, pydantic>=2.7, pydantic-settings>=2.2.
`pyserial` is **not** there; `obd2-mcp\requirements.txt` is `mcp>=1.2.0` + `pyserial>=3.5`.

### Where `cuore/live/` and `cuore/api/live.py` plug in - exactly

1. `cuore\api\live.py`: `router = APIRouter(tags=["live"], dependencies=[Depends(require_token)])`,
   registered with one line at `cuore\app.py:106`
   (`app.include_router(live.router, prefix="/api")`) plus the import at `app.py:27`.
2. `cuore\live\` sits beside `services/` as a peer package - it is not a *bridge* to a library,
   it owns hardware state and a lifecycle.
3. `cuore\api\system.py:60` changes `adapter=AdapterInfo()` -> `adapter=live.adapter_info()`, and
   `api/system.py:50-53`'s overlay block gains the live flags, lowering `live_obd`/`live_can` when
   no port resolves or MES holds it.
4. `cuore\profiles.py:51-54` / `61-72` flip to `True` per profile (bench gets
   `live_obd`/`live_can`; `actuators` stays `False`).
5. `cuore\config.py` gains the port/baud/enable settings; `cuore\requirements.txt` gains
   `pyserial>=3.5` (and `PyYAML` if the DID catalog comes across).
6. `cuore\bootstrap.py:30`'s `OBD_ROOT` is the sanctioned pointer if the transport is *imported*
   from obd2-mcp rather than moved - but see section 2: moving it into `cuore.live.transport` and
   having obd2-mcp import *that* is the cleaner direction, and matches review recommendation
   `MES_DEEP_INTEGRATION_REVIEW.md:166` ("move the live link into `cuore` as the one process that
   owns the port").

---

## 2. obd2-mcp/server.py - what moves, what stays

File: `C:\Users\User\mcp-servers\obd2-mcp\server.py`, 1417 lines, rewritten at commit `96473d5`.

### Move into a shared transport module (`cuore/live/transport.py` + `cuore/live/safety.py`)

| Block | Lines | Notes |
|---|---|---|
| `ObdError` | 63-64 | Should become a `BridgeError` subclass (or be mapped by the live bridge) so FastAPI maps it to 503/400 |
| MES registry config: `MES_REG_PATH`, `_REDACTED_PREFIXES`, `mes_registry()`, `mes_folders()`, `resolve_port()`, `resolve_baud()` | 71-151 | Pure, Windows-guarded, no MCP coupling. `mes_folders()` arguably belongs with `mes.paths` instead - it is MES-log territory, not transport |
| MES interlock: `mes_pids()`, `_window_texts_for_pids()`, `mes_status()` | 158-236 | The A3 interlock. Pure ctypes/subprocess, zero MCP coupling. Feeds `AdapterInfo.blocked_by` directly |
| Lock file: `_lock_path()`, `_pid_alive()`, `read_lock()`, `_acquire_lock()`, `_release_lock()` | 243-321 | Already writes to `%PROGRAMDATA%\cuore\adapter.lock` (line 247) - the shared location is **already chosen**. `_acquire_lock` writes `"process": "obd2-mcp"` (line 307); that must become a parameter so cuore identifies itself |
| `_PROTOCOL_HEADER_BITS` | 330-335 | Already contains the STN presets `31/32/33/34/35/36/51/52/53/54` - i.e. `STP 34` (HS-CAN 29-bit) and `STP 54` (MS-CAN 29-bit) that B2 needs. This is the seed of the bus table |
| `_clamp_timeout`, `_validate_command`, `_cmd`, `_looks_like_wrong_baud`, `_init_adapter`, `_maybe_pin_protocol`, `_session`, `_run` | 355-498 | The whole session engine. `_run` (489-498) is the only MCP-flavoured one - it JSON-serialises; split into `run(purpose, fn, **kw) -> dict` with the `json.dumps` left to the MCP adapter |
| Parsing: `ADAPTER_ERRORS`, `BENIGN_LINES`, `adapter_error`, `_hex_pairs`, `_reassemble`, `_payloads_for`, `_decode_dtc_bytes`, `_decode_dtcs` | 506-666 | `_reassemble` (558-627) is the good ISO-TP implementation - see section 3 comparison |
| PID table + decode: `_u16`, `_s16`, `PIDS`, `_PID_BY_HEX`, `_resolve_pid`, `_decode_pid`, `_query_service`, `_no_data` | 673-766 | 33 J1979 PIDs with formulas |
| Readiness: `_NON_CONTINUOUS`, `_CONTINUOUS`, `_decode_readiness`, `_readiness_body` | 1104-1186 | Includes the EVAP verdict text (1161-1170), which is the analysis that justifies the whole tool |
| Command classification: `_WRITE_SERVICES`, `_AT_READ_ONLY`, `_ST_READ_ONLY`, `_MONITOR_COMMANDS`, `classify_command`, `_classify_write` | 1285-1364 | Pure function of a string. Belongs in `cuore/live/safety.py` verbatim |
| `_evidence_dir()` and the pre-clear evidence capture inside `clear_dtcs` | 1205-1275 | The *capture* logic is reusable; the MCP `confirm=` gate is not |

### Stays MCP-specific

- `mcp = FastMCP("obd2")` (line 53) and every `@mcp.tool()` wrapper: `list_ports` (773),
  `status` (784), `mes_state` (813), `mes_settings` (823), `connect` (853), `disconnect` (903),
  `read_dtcs`/`read_pending_dtcs`/`read_permanent_dtcs` (946-961), `read_pid` (964),
  `read_voltage` (997), `read_supported_pids` (1008), `read_freeze_frame` (1040), `read_vin`
  (1075), `read_readiness` (1189), `clear_dtcs` (1212), `send_raw` (1367),
  `if __name__ == "__main__": mcp.run()` (1416).
- The `json.dumps(..., indent=2)` return convention and the `refused: ...` dicts (1222, 1385-1401)
  - that is an MCP tool-return idiom; HTTP wants a status code plus an `ErrorBody`.
- The boolean consent flags in tool signatures (`confirm`,
  `i_understand_this_writes_to_the_vehicle`, `allow_adapter_reconfiguration`,
  `allow_while_mes_connected`). The *policy* they enforce moves; the *parameter shape* is
  per-surface.

### Module-global coupling that must be refactored into a class

`STATE = State()` at **line 352**, `@dataclass State` at **338-349** (fields
`ser, port, baud, port_source, baud_source, protocol, headers_on, identity, last_open,
lock: threading.RLock`). Every read of it:

- `_cmd` reads `STATE.ser` (380)
- `_init_adapter` reads/writes `STATE.baud`, `STATE.baud_source`, `STATE.port`, `STATE.protocol`,
  `STATE.headers_on` (418-434)
- `_maybe_pin_protocol` writes `STATE.protocol` (439-444)
- `_session` takes `STATE.lock` and assigns
  `STATE.ser/port/baud/port_source/baud_source/last_open`, clears `STATE.ser` in `finally`
  (450-486)
- `_reassemble` defaults `headers_on` from `STATE.headers_on` (571-572) - **the sneakiest one**:
  a pure parser reaching into global device state
- `status()` reads six STATE fields (798-800)
- `connect()` writes `STATE.identity` and resets `STATE.protocol` (881, 898)
- `disconnect()` mutates `STATE.ser`/`STATE.protocol` under `STATE.lock` (906-914)
- `clear_dtcs` reads `STATE.port` for the evidence record (1252)

Refactor: `class AdapterLink` owning `_ser/_port/_baud/_protocol/_headers_on/_identity/_lock`, with
`session(purpose, port="", baud=0, allow_while_mes_connected=False)` as a context-manager method
and `cmd(...)`, `query_service(...)` as methods. Make
`_reassemble`/`_hex_pairs`/`adapter_error`/`_decode_*`/`classify_command` **module-level pure
functions with no default from device state** (pass `headers_on` explicitly) - they are already
pure apart from line 571-572, and obd2-mcp's own tests call them that way
(`tests/test_fixes.py` calls `s._reassemble(..., headers_on=True)`).

Two more couplings worth naming:

- **One lock per process, one process per adapter.** `STATE.lock` (349) serialises within a
  process; `_acquire_lock` (296) warns across processes. Inside cuore, a single `AdapterLink`
  instance on `app.state` gives you the first for free - but FastAPI is async and `_session`/`_cmd`
  are blocking. Every live route must be `def` (threadpool) not `async def`, or wrapped in
  `run_in_threadpool`, or the event loop stalls for the whole 4 s adapter timeout.
- **The `protocol` pin is global to the adapter, not per-bus.** `_init_adapter` sends one
  `ATSP{protocol}` (434). A three-bus design makes "the pinned protocol" a property of the *bus
  selection*, not of the link - this is the single biggest structural change the multi-bus
  requirement forces on the existing code.

Also: `clear_dtcs` is the only vehicle write in the file and it is already evidence-gated; cuore's
`actuators` flag is `False` and should stay `False` - the live layer should ship **read-only** and
not port `clear_dtcs` at all at first.

---

## 3. stelvio_scan reuse map

Root: `C:\Users\User\Documents\stelvio_scan\src\stelvio_scan\`. Repo is v0.2.0 in `pyproject.toml`
but README says "v0.6, pre-release", and **"Nothing in this codebase has been validated against a
real car yet - every test is mocked"** (README line 5). There is no `tests/` directory in the tree.

### `adapter/transport.py` (59 lines) - **reuse as-is**

Pure Python (abc + dataclass), no deps. `AdapterError`/`NoDataError`/`BusError`/
`NegativeResponseError(nrc, text)` (lines 7-25), frozen `AdapterInfo(name, firmware, protocol)`
(28-32), `ObdAdapter` ABC (35-59). The exception taxonomy is better than obd2-mcp's single
`ObdError` and maps cleanly onto HTTP: `NoDataError` -> 200-with-warning, `BusError` -> 503,
`NegativeResponseError` -> 200 carrying the NRC. **Take this file.**

### `adapter/stream.py` (173 lines) - **reuse as-is**

Pure Python + `pyserial`. `Stream` ABC (21-45) with
`read(n)/write/flush/reset_input_buffer/reset_output_buffer`; `SerialConfig`/`SerialStream`
(50-100); `TcpConfig`/`TcpStream` (105-173, with `TCP_NODELAY` and a non-blocking drain in
`reset_input_buffer`, 159-173). This injectable-transport seam is the one thing obd2-mcp lacks - it
is what makes `RecordingStream`/`PlaybackStream` and an ELM327-emulator CI harness possible.
**Highest-value single file in the repo for this project.**

Caveat: `SerialStream.open()` (62-68) passes no separate `write_timeout` policy and does not set
`exclusive`; obd2-mcp's `serial.Serial(..., timeout=0.25, write_timeout=2)` (`server.py:466`) with
the 0.25 s poll loop is the better open for a prompt-driven REPL - merge obd2-mcp's parameters into
this class.

### `adapter/elm327.py` (411 lines) - **adapt (harvest ~3 parts, rewrite the rest)**

Depends on `pyserial` (via stream), `stelvio_scan.audit`, lazy `stelvio_scan.uds.*`. No PySide6.
Quality: decent structure, several real correctness problems.

- **29-bit normal-fixed addressing: yes, and it is the best part.** `_setup_for_ecu` (218-243)
  selects protocol 7 for 29-bit / 6 for 11-bit, formats `ATSH{req:08X}` and `ATCRA{resp:08X}`, and
  **caches** `_current_protocol/_current_request_id/_current_response_id` so it does not re-issue
  AT commands per request (230-243). `_restore_broadcast_obd_if_needed` (201-216) un-narrows back
  to `ATSH7DF`/`ATCRA` before a broadcast OBD request. This state-machine idea is exactly what a
  multi-bus live layer needs - **adopt the concept, extend the key from `(protocol, req, resp)` to
  `(bus, protocol, req, resp)`.**
- **STN commands: no.** The class docstring says "ELM327 / STN driver" (line 58) but there is not a
  single `ST*` command in the file. No `STP`, no `STCFCPA`, no `STCSEGR/STCSEGT`, no `STM/STMA`,
  no `STCMM`, no `STFPA`, no `STBR`. Confirmed by grep across the whole package: zero hits for
  MS-CAN, 125 k, `STP 54`, IHS, or monitor modes. **Everything in review items B1/B2/B3 is
  unwritten here.**
- **No flow control setup.** No `ATFCSH`/`ATFCSD`/`ATFCSM`, which the connectivity research
  (section 6) calls mandatory for multi-frame to non-OBD modules. A 29-bit UDS read longer than
  7 bytes will likely stall without it.
- **ISO-TP framing is incorrect in several ways** - `_parse_responses` (328-378) +
  `_assemble_isotp` (381-411):
  1. Header-width detection is `if len(line) >= 8 and line[:2] in {"18","98"}` (355-358) - a
     heuristic on the *first two hex chars*, so any 11-bit response whose line happens to start
     `18`/`98` is misparsed, and any 29-bit ID not starting `18`/`98` falls back to a 3-char
     header. obd2-mcp's parity test (`server.py:602`, `hdr_len = 3 if len(blob) % 2 else 8`) is
     strictly more robust under `ATS0`.
  2. It never sends a flow-control frame and never checks the FC/CTS handshake; it only
     concatenates whatever consecutive frames happened to arrive (400-407).
  3. It ignores consecutive-frame **sequence numbers** - it checks only `(cf[0] >> 4) != 0x2` (404)
     and breaks, so a dropped or out-of-order CF silently truncates rather than erroring. obd2-mcp
     has the same weakness but at least clamps to the declared length (`server.py:624-625`).
  4. `_assemble_isotp` returns only the first frame group's assembly and degrades unknown PCI types
     to "raw payload of first frame" (411).
- **Error detection is substring-based and thin**: `raw.startswith("NO DATA")`,
  `"UNABLE TO CONNECT" / "BUS INIT" / "CAN ERROR" in raw` (149-154, 259-264). obd2-mcp's
  `ADAPTER_ERRORS` tuple (`server.py:506-510`, 16 conditions incl. `BUFFER FULL`, `BUS BUSY`,
  `STOPPED`, `RX ERROR`, `LV RESET`, `OUT OF MEMORY`, `TIMEOUT`) is the one the research says never
  to swallow. **Use obd2-mcp's.**
- **`ATZ` on every open** (95) - the research explicitly prefers `ATWS` ("on some clones `ATZ`
  resets the UART to 38400 and you lose the port"). Default `baudrate=38400` (`ELM327Config`,
  line 40) is wrong for this adapter; MES's registry says 115200.
- **It holds the port for the object's lifetime** (`open()`/`close()`, 83-127) - the opposite of
  the lazy-per-operation rule that Tier A4 and `server.py:447-487` establish. **This is the
  architectural reason elm327.py cannot be lifted wholesale.**
- `request_uds(ecu, service, payload)` (131-170) and `scan_module_dtcs(ecu, mask)` (172-199) are
  good API shapes - keep the signatures, reimplement the body on obd2-mcp's session engine.

**Verdict: adapt.** Harvest `_setup_for_ecu`'s idempotent header/filter cache, the
`request_uds`/`scan_module_dtcs` API shape, and the exception mapping; discard
`_parse_responses`/`_assemble_isotp` in favour of `server.py:_reassemble`; discard the
persistent-open lifecycle.

### `uds/addresses.py` (114 lines) - **reuse as-is (as data), verify against the car**

Pure Python, zero deps, zero I/O. Frozen `ECUAddress(name, short, request_id, response_id,
addressing, description)` with `is_29bit` (33-45). The `_29bit()` helper is correct normal-fixed:
`req = 0x18DA0000 | (tb << 8) | 0xF1`, `resp = 0x18DAF100 | tb`.
**No functional address (`18DB33F1`) and no bus field** - both must be added for the three-bus
design. The docstring itself flags the provenance risk (lines 13-16) and it is corroborated by
`CONNECTIVITY_AND_SGW.md` section 3 ("FCA body-module CAN IDs remain UNCERTAIN ... Derive
empirically; do not guess"). Note the target bytes here **disagree** with the review's community
list in `MES_DEEP_INTEGRATION_REVIEW.md` B1 (ECM `10`, TCM `18`, BCM `40`, IPC `60`, steering `2A`,
RF hub `C7`) - this file has ECM/TCM as 11-bit only, BCM `40` agrees, IPC `60` agrees, SAS `76` vs
steering `2A`. **Reconcile before use.**

Verbatim, `C:\Users\User\Documents\stelvio_scan\src\stelvio_scan\uds\addresses.py:48-114`:

```python
# 11-bit OBD-II powertrain modules - answer the standard 7DF broadcast too.
ECM = ECUAddress("Engine control module", "ECM", 0x7E0, 0x7E8, Addressing.CAN_11BIT,
                 "Powertrain - engine management. Always present.")
TCM = ECUAddress("Transmission control module", "TCM", 0x7E1, 0x7E9, Addressing.CAN_11BIT,
                 "ZF 8HP mechatronic. Powertrain.")

# 29-bit physical addressing - derived target_byte values for FCA Giorgio.
# Format: request 18 DA <tb> F1, response 18 DA F1 <tb>
def _29bit(tb: int) -> tuple[int, int]:
    req = 0x18DA0000 | (tb << 8) | 0xF1
    resp = 0x18DAF100 | tb
    return req, resp


_ABS_REQ, _ABS_RESP = _29bit(0x28)
ABS = ECUAddress("ABS / ESC control module", "ABS", _ABS_REQ, _ABS_RESP, Addressing.CAN_29BIT,
                 "Antilock braking + stability. Reads wheel speed sensors.")

_SRS_REQ, _SRS_RESP = _29bit(0x50)
SRS = ECUAddress("Restraints control module (airbag)", "SRS", _SRS_REQ, _SRS_RESP, Addressing.CAN_29BIT,
                 "Airbag, pretensioner, occupant detection.")

_BCM_REQ, _BCM_RESP = _29bit(0x40)
BCM = ECUAddress("Body control module", "BCM", _BCM_REQ, _BCM_RESP, Addressing.CAN_29BIT,
                 "Lighting, doors, central locking, stop/start logic.")

_IPC_REQ, _IPC_RESP = _29bit(0x60)
IPC = ECUAddress("Instrument panel cluster", "IPC", _IPC_REQ, _IPC_RESP, Addressing.CAN_29BIT,
                 "Cluster / gauges / driver display.")

_EPB_REQ, _EPB_RESP = _29bit(0x38)
EPB = ECUAddress("Electric park brake", "EPB", _EPB_REQ, _EPB_RESP, Addressing.CAN_29BIT,
                 "Caliper motor control. NEEDED for service mode (pad change).")

_HVAC_REQ, _HVAC_RESP = _29bit(0x68)
HVAC = ECUAddress("HVAC / climate control", "HVAC", _HVAC_REQ, _HVAC_RESP, Addressing.CAN_29BIT,
                 "Climate control panel + blower / actuators.")

_SAS_REQ, _SAS_RESP = _29bit(0x76)
SAS = ECUAddress("Steering angle sensor", "SAS", _SAS_REQ, _SAS_RESP, Addressing.CAN_29BIT,
                 "Steering angle. Needs calibration after alignment / battery disconnect.")

_PROXI_REQ, _PROXI_RESP = _29bit(0x6D)
PROXI = ECUAddress("PROXI (vehicle configuration)", "PROXI", _PROXI_REQ, _PROXI_RESP, Addressing.CAN_29BIT,
                   "Stores VIN-to-module mapping. Mismatches cause B2204.")

# Q4 AWD coupling control - only on AWD models.
_AWD_REQ, _AWD_RESP = _29bit(0x29)
AWD = ECUAddress("AWD (Q4) coupling control", "AWD", _AWD_REQ, _AWD_RESP, Addressing.CAN_29BIT,
                 "Active torque distribution to front axle. Q4 models only.")

# Telematics / radio (some markets only)
_RADIO_REQ, _RADIO_RESP = _29bit(0x6F)
RADIO = ECUAddress("Radio / Uconnect head unit", "RADIO", _RADIO_REQ, _RADIO_RESP, Addressing.CAN_29BIT,
                   "Infotainment unit. May not respond if asleep.")


# All known modules. UI exposes this for the 'scan all modules' flow.
MODULES_GIORGIO: list[ECUAddress] = [
    ECM, TCM,
    ABS, SRS, BCM, IPC, EPB, HVAC, SAS, PROXI, AWD, RADIO,
]

# Order to scan in: powertrain first (most common DTCs), then safety, then body.
DEFAULT_SCAN_ORDER: list[ECUAddress] = [
    ECM, TCM, ABS, SRS, EPB, BCM, IPC, SAS, PROXI, AWD, RADIO,
]
```

### `uds/service10.py` (67) - **reuse as-is**

Pure. `SessionType` enum, `session_name`, `SessionResponse(session_type, p2_server_ms,
p2_star_server_ms)`, `build_request_10`, `parse_response_10` (P2* correctly x10 ms, line 66).
Correct per ISO 14229.

### `uds/service19.py` (128) - **reuse as-is**

Pure (imports only `uds.addresses`, `uds.dtc`). `StatusMask` IntEnum (21-31), `NRC` IntEnum incl.
`RESPONSE_PENDING = 0x78` (34-49), `_NRC_HUMAN` + `nrc_description` (52-72), `build_request_19_02`,
`parse_response_19_02` (75-91), `ScanStatus`/`ScanResult` (97-128).
**Only sub-function 0x02 is implemented**; `0x01`, `0x04` (snapshot/freeze frame), `0x06` (extended
data) are named in the docstring but absent - `0x04`/`0x06` are what you need for UDS freeze frames
and must be written. **Nothing anywhere handles NRC 0x78 by waiting and re-reading** - the research
calls this "a common client bug"; it is present here (`elm327.py:164-167` raises on 0x78).

### `uds/service22.py` (70) - **reuse as-is**

Pure. `build_request_22(*dids)` (18-31), `parse_response_22(response, expected=None)` (45-70).
The multi-DID split relies on a caller-supplied `{did: length}` map and otherwise assumes one DID -
correct behaviour given UDS transmits no per-DID length, and honestly documented (lines 7-10,
65-68).

### `uds/service27.py` (125) - **keep, do not wire**

Pure. Seed/key protocol only; `LocalKeyComputer` is an explicit test XOR (111-125) and the
docstring is emphatic that no FCA algorithm is embedded (20-26). A read-only live link does not
need it. Keep the file for completeness; do not expose it as an MCP tool or HTTP route.

### `uds/security_state.py` (78) - **keep, do not wire**

Pure + threading. `UnlockRecord`/`SecurityState` with TTL expiry (default 30 s, line 34). Only
relevant once writes exist.

### `uds/service31.py` (75) - **keep out of scope**

Pure, correct RoutineControl framing. **0x31 is a vehicle write** (`server.py:1295` classifies it
so). Out of scope for a read-only layer.

### `uds/dtc.py` (132) - **adapt**

Imports `stelvio_scan.obd.dtc` (which pulls PyYAML + the bundled `dtc_codes.yaml`).
`format_uds_dtc(high, middle, low)` (80-103) correctly maps the 3-byte UDS DTC onto the 5-char code
and preserves `raw_24`; `DtcStatus` bitfield with all 8 ISO 14229 D.2 bits (20-62);
`decode_uds_dtc_block` (106-132) walks 4-byte tuples and skips all-zero padding.
**This is genuinely good and cuore has no equivalent** - obd2-mcp only decodes 2-byte OBD-II DTCs
(`server.py:635-659`). But: it **drops the low byte from the displayed code** (comment at lines
92-93), and MES's whole corpus keys on `P0456-00`/`U0100-87` form - `mes.dtc.failure_type()` exists
precisely to decode that suffix. **Adapt to emit `f"{code}-{low:02X}"` so live UDS DTCs join the
corpus vocabulary**, which is the B5 correlation prerequisite. Strip the `obd.dtc.lookup()`
dependency and route descriptions through `mes` instead (191 YAML entries vs. the mes library's
corpus-backed tables).

### `uds/did.py` (178) - **reuse as-is**

Pure (logging only). Frozen `DID` metadata (20-37), `DIDValue` with `.display` (40-52), 10 named
codecs (57-127), a `custom:<name>` dispatch (136-154), `decode()` applying scale/offset (157-178).
Clean, declarative, extensible. **Take it.**

### `uds/did_catalog.py` (146) - **adapt**

Depends on `PyYAML` + **`platformdirs`**. Loads `data/did_catalog.yaml` via `importlib.resources`
(31-38) plus a user overlay at `%APPDATA%/stelvio_scan/user_dids.yaml` (40-54); module singleton
`default_catalog()` (129-141) with `reload_catalog()`. `add_discovered()` (114-126) supports the
DID-sweep workflow. Adapt: change the resource package and the overlay path to cuore's, or drop
`platformdirs` and use `%PROGRAMDATA%\cuore\` to match the existing lock-file location
(`server.py:243-258`).

### `uds/__init__.py` (83) - re-export barrel; rewrite to match whatever subset moves.

### `obd/pids.py` (251) - **adapt or skip**

Pure. Frozen `PID(pid, name, unit, n_bytes, decode, description)` dataclass (14-26) keyed by
**int**; J1979 decoders only. obd2-mcp's `PIDS` (`server.py:683-716`) is keyed by **friendly name**
with the hex as a value and has the same ~33 entries. **Duplication - pick one.** stelvio_scan's is
the better data model (a real dataclass, `n_bytes`, description); obd2-mcp's has `_resolve_pid`
accepting both name and hex (`server.py:721-731`), which the tool surface needs. Recommendation:
keep stelvio_scan's `PID` dataclass, port obd2-mcp's resolver on top.

### `obd/dtc.py` (173) - **skip / replace with `mes`**

Pure Python + PyYAML. `format_dtc` (56-63), `decode_dtc_bytes` with odd-length count-byte heuristic
(66-93), YAML DB loader (101-138), `lookup()` with a graceful unknown-code fallback (141-157).
Functionally fine, but it duplicates `mes.dtc`/`mes.knowledge` which is corpus-backed and already
the system of record in cuore. **Take `format_dtc` only if needed; drop the 191-entry YAML.**

### `obd/session.py` (474) - **rewrite**

Pure Python but architecturally incompatible: it wraps a *persistently open* adapter and
`isinstance(self.adapter, ELM327Adapter)` checks appear seven times (146, 179, 214, 279, 313, 366).
Useful as a **specification** of the operation set - `supported_pids` (50-79), `read_pid` (81-99),
`readiness` (101-115), `stored/pending/permanent_dtcs` (119-140), `enter_extended_session`
(173-189), `unlock_security` (193-264), `read_did` (272-293), `discover_dids` (295-346),
`scan_modules` with per-module progress callback (350-387), `clear_dtcs` (391-399),
`freeze_frame_dtc` (403-413), `vin`/`calibration_id`/`ecu_name` (435-474).
`discover_dids` (295-346) is the one behaviour neither cuore nor obd2-mcp has and that the DID work
needs. Rewrite its body against a lazy session; keep the signatures.

### `obd/readiness.py` (145) - **adapt**

Pure. Better than obd2-mcp's: it models `MonitorState`/`Monitor`/`ReadinessStatus` as dataclasses
and **handles the diesel (compression-ignition) non-continuous layout** via byte B bit 3, which
`server.py:_decode_readiness` (1112-1143) does not (it only reports
`"ignition": "spark"/"compression"` and then uses the spark table regardless - a real bug on a
diesel Stelvio). **Merge stelvio_scan's layout handling into obd2-mcp's `_decode_readiness`, keep
obd2-mcp's EVAP verdict text.**

### `obd/capture.py` (85) - **reuse as-is**

Pure, threadsafe. `PidStats` (14-49) min/max/avg/duration; `CaptureBook` (52-86) with a lock and
`snapshot()`. Exactly what a polling loop needs. Note the min/max update at lines 42-45 is written
oddly but is correct.

### `obd/expected_ranges.py` (128) - **optional**

Pure + PyYAML; depends on `stelvio_scan.vehicle.EngineVariant`. `Zone` enum,
`ExpectedRange.classify()` (37-48). UI-colouring concern. Adopt only if cuore grows live gauges;
`data/expected_ranges.yaml` is 198 lines of hand-estimated ranges with no stated provenance.

### `recording/recorder.py` (129) - **reuse as-is**

Pure. `RecordingFile` writes JSONL (`{"t","kind":"write"|"read"|"header"|"footer","data":hex}`,
format documented at 4-11), flushes every event (88-89), `RecordingStream(Stream)` tees an inner
stream (92-129). **This is byte-level wire capture, not the `csvlog` parameter schema** - do not
confuse it with the P3 drive recorder, which `cuore/api/recordings.py:5-8` says must write the MES
CSV schema. Both are wanted, for different purposes.

### `recording/player.py` (128) - **reuse as-is**

Pure. `PlaybackStream(Stream)` replays a JSONL recording, `strict_writes` optional (34-41).
**This is the no-car test harness the whole live layer needs** - combined with `Stream` injection
it lets `check_live.py` run the full UDS stack with no adapter and no car. Higher practical value
than the ELM327-emulator + virtual COM pair the review suggests (B6), because it needs no external
process.

### `audit.py` (79) - **adapt**

Depends on **`platformdirs`** only. Module-level lock, JSONL append, `record(event, **fields)` with
bytes-to-hex coercion and never-raises semantics (37-56), `read_recent(n)` (59-79). cuore has **no
audit log at all**, and a tool that touches a customer's car needs one. Adapt: drop `platformdirs`,
write to `%PROGRAMDATA%\cuore\audit.jsonl` beside `adapter.lock`. Add rotation - it appends
unbounded.

### `vehicle/profile.py` (113) - **partially reuse**

Pure. `EngineVariant` enum with `is_diesel`/`banks` (14-27) - **`is_diesel` is what
`obd/readiness.py` needs to pick the right monitor layout**, and it is the strongest reason to take
this file. `DEFAULT_DASHBOARD` PID list (32-45). `decode_vin` (66-81) and `suggest_engine_from_vin`
(84-103) are explicitly "best-effort" with an unpublished position-8 table (86-92) - cuore should
prefer `mes`'s corpus-derived VIN identity. `_MODEL_YEAR` table (106-113) is standard and fine.
`StelvioGiuliaProfile` (48-56) is a docstring in a dataclass.

### `data/*.yaml`

- `did_catalog.yaml` (204 lines, **27 DIDs**) - ISO 14229 Annex C standard identifiers only, every
  entry carrying a `source:` field. Deliberately excludes FCA-proprietary DIDs (header comment
  lines 1-8). **Reuse as-is**; it is the honest baseline and the schema is documented in-file
  (lines 9-24).
- `dtc_codes.yaml` (1474 lines, **191 codes**) - J2012 + FCA notes, severity and causes.
  **Skip**: `mes` already owns DTC knowledge against the actual corpus.
- `expected_ranges.yaml` (198 lines) - per-variant PID zones, unsourced estimates. Optional.

### PySide6 coupling

**None of the files listed above imports PySide6.** Confirmed: PySide6 lives only under `ui/`
(12 files) and is pulled transitively by `analysis/overlay_chart.py` (pyqtgraph) and
`reports/pdf.py` (reportlab). The reusable dependency set is `pyserial`, `PyYAML`, `platformdirs` -
and `platformdirs` is needed by only two files (`audit.py`, `uds/did_catalog.py`), both of which
should be repathed to `%PROGRAMDATA%\cuore\` anyway.
**Net new cuore dependency: `pyserial` + `PyYAML`.**

### Summary verdict table

| Module | Deps | 29-bit normal-fixed | STN cmds | ISO-TP | Verdict |
|---|---|---|---|---|---|
| `adapter/transport.py` | none | n/a | n/a | n/a | reuse as-is |
| `adapter/stream.py` | pyserial | n/a | n/a | n/a | reuse as-is |
| `adapter/elm327.py` | pyserial, audit | yes (ATSH/ATCRA cache) | **none** | flawed (header heuristic, no FC, no SN check) | adapt |
| `uds/addresses.py` | none | yes (18DA<TA>F1) | n/a | n/a | reuse as data, verify |
| `uds/service10.py` | none | n/a | n/a | n/a | reuse as-is |
| `uds/service19.py` | uds only | n/a | n/a | n/a | reuse as-is (add 0x04/0x06, 0x78) |
| `uds/service22.py` | none | n/a | n/a | n/a | reuse as-is |
| `uds/service27.py` | none | n/a | n/a | n/a | keep, do not wire |
| `uds/security_state.py` | none | n/a | n/a | n/a | keep, do not wire |
| `uds/service31.py` | none | n/a | n/a | n/a | out of scope (write) |
| `uds/dtc.py` | PyYAML (via obd.dtc) | n/a | n/a | n/a | adapt (keep the -XX suffix) |
| `uds/did.py` | none | n/a | n/a | n/a | reuse as-is |
| `uds/did_catalog.py` | PyYAML, platformdirs | n/a | n/a | n/a | adapt (repath) |
| `obd/pids.py` | none | n/a | n/a | n/a | adapt or skip (dup of obd2-mcp) |
| `obd/dtc.py` | PyYAML | n/a | n/a | n/a | skip (use `mes`) |
| `obd/session.py` | adapter, obd, uds | n/a | n/a | n/a | rewrite (spec only) |
| `obd/readiness.py` | none | n/a | n/a | n/a | adapt (diesel layout wins) |
| `obd/capture.py` | none | n/a | n/a | n/a | reuse as-is |
| `obd/expected_ranges.py` | PyYAML | n/a | n/a | n/a | optional |
| `recording/recorder.py` | none | n/a | n/a | n/a | reuse as-is |
| `recording/player.py` | none | n/a | n/a | n/a | reuse as-is (CI harness) |
| `audit.py` | platformdirs | n/a | n/a | n/a | adapt (repath, rotate) |
| `vehicle/profile.py` | none | n/a | n/a | n/a | partial (take `EngineVariant`) |
| `data/did_catalog.yaml` | - | n/a | n/a | n/a | reuse as-is |
| `data/dtc_codes.yaml` | - | n/a | n/a | n/a | skip |
| `data/expected_ranges.yaml` | - | n/a | n/a | n/a | optional |

---

## 4. Licensing

**Confirmed MIT, but not fully papered.**

- `C:\Users\User\Documents\stelvio_scan\pyproject.toml:12` - `license = { text = "MIT" }`
- `C:\Users\User\Documents\stelvio_scan\src\stelvio_scan.egg-info\PKG-INFO` - `License: MIT`
- `C:\Users\User\Documents\stelvio_scan\README.md:129-131` - `## License` / `MIT.`

**There is no `LICENSE` / `COPYING` file in the repository** (only vendored ones under `.venv/`),
and no SPDX header in any source file. Three independent declarations of MIT is unambiguous intent,
and the repo is the user's own, so reuse is unconstrained in practice. Two cheap fixes worth doing
before copying code across: add a `LICENSE` file with the MIT text and a copyright line to
`stelvio_scan`, and put a one-line provenance comment at the top of each file copied into cuore
(`# Adapted from stelvio_scan (MIT), src/stelvio_scan/uds/addresses.py`).

Note also that `autoauth/client.py` targets a commercial service and `service27.py:20-26` is
explicit about *not* embedding FCA's algorithm - carrying those files over carries no licence risk,
but they also carry no value for a read-only layer.

---

## 5. Recommended `cuore/live/` layout

```
cuore/
  live/
    __init__.py        # public surface: link(), status(), the singleton accessor
    errors.py          # LiveError hierarchy -> BridgeError subclasses
    config.py          # port/baud/bus resolution: arg -> CUORE_* -> MES registry
    interlock.py       # MES liveness + advisory lock file
    stream.py          # Stream ABC, SerialStream, TcpStream, PlaybackStream
    transport.py       # AdapterLink: lazy session, cmd, init, protocol/bus pin
    framing.py         # pure parsers: adapter_error, reassemble, hex_pairs
    buses.py           # Bus table: CAN-C / CAN-IHS / CAN-CH, STN protocol map
    addressing.py      # ECUAddress, normal-fixed 18DA<TA>F1, Giorgio table
    obd.py             # J1979: PIDs, DTCs, readiness, VIN, freeze frame
    uds.py             # 0x10 / 0x19 / 0x22 / 0x3E + NRC handling
    capture.py         # passive monitor: STCMM 0 + STM/STMA, frame store
    safety.py          # classify_command, read-only allowlist, write gate
    audit.py           # JSONL audit log
    models.py          # Pydantic contracts for the live surface
  api/
    live.py            # the HTTP router
  mcp_live.py          # (or obd2-mcp/server.py re-pointed) MCP tool adapter
```

### Minimal interfaces

**`live/stream.py`** - lifted from `stelvio_scan/adapter/stream.py` plus `recording/player.py`:

```python
class Stream(ABC):
    def open(self); def close(self); def is_open(self) -> bool
    def read(self, n: int) -> bytes; def write(self, data: bytes)
    def flush(self); def reset_input_buffer(self); def reset_output_buffer(self)
```

Injectable so `PlaybackStream` gives a no-car test harness and `RecordingStream` gives wire capture.

**`live/interlock.py`** - from `server.py:158-321`:

```python
def mes_status() -> dict          # {running, pids, state, label}; state in
                                  # {not_running, disconnected, connected, unknown}
def read_lock() -> dict | None    # {pid, port, purpose, since, process, stale, path}
def acquire(port: str, purpose: str, process: str = "cuore") -> None
def release() -> None
def blocked_by() -> str | None    # the one string AdapterInfo.blocked_by wants
```

**`live/buses.py`** - the piece neither codebase has. One record per physical bus, carrying the STN
selector, the pin pair, the speed, the addressing mode, and how confident we are it works:

```python
@dataclass(frozen=True)
class Bus:
    key: str                  # "can_c" | "can_ihs" | "can_ch"
    name: str                 # "CAN-C (main HS-CAN)"
    pins: tuple[int, int]     # (6, 14) | (3, 11) | (12, 13)
    bitrate: int              # 500_000 | 125_000 | 125_000
    addressing: str           # "29bit-normal-fixed" | "11bit"
    elm_protocol: str | None  # "7"  -> ATSP7 for CAN-C
    stn_protocol: str | None  # "34" -> STP 34 ; "54" -> STP 54 (MS-CAN / CAN-IHS)
    reachable_via: str        # "direct" | "stn-ms-can" | "cable-a6-grey"
    status: str               # "confirmed" | "untested" | "unreachable"
    note: str

CAN_C   = Bus("can_c",   ..., (6, 14),  500_000, "29bit-normal-fixed", "7",  "34", "direct",
              "confirmed", "reachable with any ELM327")
CAN_IHS = Bus("can_ihs", ..., (3, 11),  125_000, "29bit-normal-fixed", None, "54", "stn-ms-can",
              "untested", "vLinker FS Ford MS-CAN wires pins 3/11; verify STP 54 is not "
                          "overridden by the auto-switch firmware, and STFPA vs legacy STFAP "
                          "spelling on fw 4.3.2")
CAN_CH  = Bus("can_ch",  ..., (12, 13), 125_000, "29bit-normal-fixed", None, None, "cable-a6-grey",
              "unreachable", "no STN transceiver mapping; the grey A6 cable stays mandatory "
                             "for ABS/ESC")
```

Every live result must name the bus it came from, and `/api/capabilities` should surface the bus
table with `status` so a client renders "CAN-CH: needs the grey cable" instead of an empty module
list. `server.py:_PROTOCOL_HEADER_BITS` (330-335) already carries the `34`/`54` header-width facts
and should be derived from this table rather than duplicated.

**`live/transport.py`** - `State` (`server.py:338-352`) promoted to a class, `_session` (447-487)
becomes a method, bus selection replaces the single protocol pin:

```python
class AdapterLink:
    def __init__(self, resolve_port, resolve_baud, interlock, stream_factory): ...
    @contextmanager
    def session(self, purpose: str, *, bus: Bus = CAN_C, port="", baud=0,
                allow_while_mes_connected=False) -> Iterator["Session"]: ...

class Session:                          # valid only inside the context manager
    bus: Bus
    headers_on: bool
    def cmd(self, command: str, timeout: float = 4.0) -> str
    def query(self, request_hex: str, response_byte: str,
              timeout: float = 4.0) -> dict      # {raw, error, ecus}
    def target(self, ecu: ECUAddress) -> None    # ATSH/ATCRA/STCFCPA, idempotent
    def uds(self, ecu: ECUAddress, service: int, payload: bytes = b"") -> bytes
```

`session()` does, in order: resolve port/baud -> `interlock.mes_status()` ->
`interlock.acquire()` -> open stream -> `ATWS`/`ATE0`/`ATL0`/`ATS0`/`ATH1` -> select bus
(`ATSP{n}` or `STP {n}`) -> set flow control (`ATFCSH`/`ATFCSD`/`ATFCSM1` or
`STCFCPA`/`STCSEGR 1`/`STCSEGT 1`) -> yield -> close -> `interlock.release()`.
**One operation, one open** - the non-negotiable rule from `server.py:7-12` and Tier A4.

**`live/framing.py`** - pure functions, no device state, directly testable (this is what fixes
`server.py:571-572`):

```python
def adapter_error(text: str) -> str
def hex_pairs(text: str) -> list[str]
def reassemble(raw: str, *, headers_on: bool) -> dict[str, list[str]]
def payloads_for(ecus, response_byte: str) -> dict[str, list[str]]
```

**`live/uds.py`** - read-only services only, built on `Session.uds`:

```python
def session_control(s, ecu, session=0x01) -> SessionResponse      # 0x10 01 default only
def tester_present(s, ecu) -> None                                # 0x3E 80, suppressPosRsp
def read_dtcs(s, ecu, mask=0xFF) -> ScanResult                    # 0x19 02
def read_dtc_snapshot(s, ecu, dtc, record=0xFF) -> ...            # 0x19 04  (to write)
def read_dtc_extended(s, ecu, dtc, record=0xFF) -> ...            # 0x19 06  (to write)
def read_did(s, ecu, did: int) -> DIDValue                        # 0x22
def discover_dids(s, ecu, rng: range, on_hit=None) -> dict[int, bytes]
def scan_modules(s, modules=None, on_result=None) -> list[ScanResult]
```

Must handle NRC `0x78` by waiting `p2_star` and re-reading rather than raising - the bug present in
`elm327.py:164-167`.

**`live/capture.py`** - passive, never transmits, works with the SGW locked:

```python
def start(bus: Bus, *, filters: list[int] = (), seconds: float,
          max_frames: int) -> CaptureHandle
# STCMM 0 (listen-only, no ACK) -> STFPA pass filters -> STM/STMA -> read until deadline
def frames(handle) -> list[Frame]      # {t, can_id, data_hex, bus}
```

This must **not** go through `Session.cmd`: `_MONITOR_COMMANDS` (`server.py:1317`) are blocked
precisely because they never return to the prompt. It needs its own read loop with a deadline
and an explicit interrupt byte, and its own `classify_command` exemption. Budget for
`OUT OF MEMORY` from filter allocation (noted in review B3).

**`live/safety.py`** - `classify_command` verbatim from `server.py:1320-1358`, plus one addition
the HTTP surface needs:

```python
def classify_command(cmd: str) -> tuple[str, str]   # read | vehicle_write | adapter_state | blocked
READ_ONLY_UDS = {0x10: {0x01}, 0x19, 0x22, 0x3E}    # the only services the layer may emit
def assert_read_only(service: int, payload: bytes) -> None
```

With `actuators=False` in `profiles.py`, **the HTTP layer should have no code path that can emit a
write at all** - not a flag that defaults off. Keep the `send_raw`-equivalent behind
`allow_adapter_reconfiguration` on the MCP surface only.

**`live/models.py`** / `api/live.py` - the contract and the routes:

```
GET  /api/live/status          -> LiveStatus  {port, baud, sources, mes, lock, buses[], identity}
GET  /api/live/ports           -> serial ports, marking MES's Interface 0
POST /api/live/probe           -> ATWS + identity + ATRV + protocol search   (connect equivalent)
GET  /api/live/obd/dtcs        ?kind=stored|pending|permanent
GET  /api/live/obd/pid/{pid}
GET  /api/live/obd/readiness
GET  /api/live/obd/vin
GET  /api/live/obd/freeze
GET  /api/live/modules         ?bus=can_c            -> UDS 0x19 sweep, per-module ScanResult
GET  /api/live/module/{short}/dtcs
GET  /api/live/module/{short}/did/{did}
POST /api/live/capture         -> start a passive capture, returns a handle
GET  /api/live/capture/{id}    -> frames / decoded signals
```

Every route `def` (not `async def`) so blocking serial work runs in the threadpool. Every route
returns the bus it used and the `adapter_error` string when the read did not complete - never an
empty list that reads as "no faults" (`server.py:926-927` is the precedent).

**`mcp_live.py`** - the thinnest possible layer: one `@mcp.tool()` per `cuore.live` function,
`json.dumps(result, indent=2)`, plus the consent flags. Either replace `obd2-mcp/server.py`'s body
with imports from `cuore.live` (keeping the tool names stable so existing Claude sessions keep
working), or point `obd2-mcp` at cuore over HTTP so there is genuinely **one process that owns
COM3** - which is what `MES_DEEP_INTEGRATION_REVIEW.md:166` recommends and what the "three obd2
processes alive at once" incident argues for.

**Tests** - `cuore/tests/check_live.py`, same plain-script style as `check_api.py`: pure-function
regression over `framing.py`/`safety.py`/`addressing.py` (port `obd2-mcp/tests/test_fixes.py`
wholesale), plus a `PlaybackStream`-backed end-to-end that runs the full UDS stack with no
hardware. And update `check_api.py:50-56` rather than letting the live flags quietly break it.

---

## Supporting documents worth reading before implementation

- `C:\Users\User\mcp-servers\docs\research\MES_DEEP_INTEGRATION_REVIEW.md:129-142` - Tier B items
  B1 (native UDS/ISO-TP over STN, with the exact `STP 34` / `ATSH 18DA10F1` / `STCFCPA` /
  `STCSEGR 1` / `STCSEGT 1` sequence and community target addresses ECM 10, TCM 18, BCM 40,
  IPC 60, steering 2A, RF hub C7 - the last reported to trip the immobiliser, avoid),
  B2 (`STP 54` for CAN-IHS on pins 3/11), B3 (passive capture: `STCMM 0` + `STM`/`STMA` + `STFPA`),
  B4 (Mode $06), B5 (correlation layer), B6 (server shape).
- `C:\Users\User\mcp-servers\docs\research\CONNECTIVITY_AND_SGW.md` - section 1 the three-bus
  ceiling, section 4 the vLinker FS is the *Ford* variant (its MS-CAN switching targets pins 3/11,
  which *is* one of Giorgio's extra buses - untested), section 5 two apps cannot share COM3 and the
  correct handoff pattern, section 6 ELM327 reliability engineering (pin the protocol, `ATH1`
  mandatory, flow control, never swallow the error strings, prefer `ATWS` over `ATZ`).
- `C:\Users\User\mcp-servers\docs\COMPANION_APP_SPEC.md:250-310` (Tier 1 vs Tier 2 live data and
  the honesty rule about labelling which tier produced a number) and `:560-580` (the P0-P9 phasing).
