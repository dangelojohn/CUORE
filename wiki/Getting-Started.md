# Getting Started

This page takes you from a fresh checkout to a running web app and a first read from the car. Hardware is covered on [[Hardware and Cables|Hardware-and-Cables]].

## What you need

- A Windows PC. The launch scripts are PowerShell, and the MES interlock reads Windows process and window state.
- Python 3.10 or newer.
- For live reads: an STN1170-based OBD adapter (see [[Hardware and Cables|Hardware-and-Cables]]) and the car. Everything else (log analysis, jobs, bulletins, reports) works with no adapter.
- Optional: MultiEcuScan installed, so CUORE can read its logs (default location is MES's own install directory).

## Install

From the repository root:

```
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r cuore/requirements.txt
```

The virtual environment lives in `.venv` at the repository root. The launch scripts expect it there.

## Start

```
powershell -NoProfile -ExecutionPolicy Bypass -File start-cuore.ps1 -Restart
```

`-ExecutionPolicy Bypass` is needed because the script is unsigned. `-Restart` stops a running CUORE first. Without it the script reuses a healthy server, and it restarts one automatically if the source files are newer than the running process.

What `start-cuore.ps1` does, in order:

1. Looks at who is listening on port 5000. If it is CUORE (a `python -m cuore` process, or something answering the health check) it is restarted when asked or stale. If it is another program, the script tells you and does not touch it.
2. If the optional keep-alive task is running, it leaves the start to that task.
3. Otherwise starts `python -m cuore --profile bench --host 0.0.0.0 --port 5000`, minimised.
4. Waits up to about a minute for `/api/health` (a cold start loads the MES log corpus).
5. Opens the browser at `http://127.0.0.1:5000` (or at the page given with `-Page`, for example `-Page /live`).

To run the server directly:

```
.venv\Scripts\python.exe -m cuore --profile bench --port 5000
```

Two helper scripts exist for a permanent setup: `cuore-keepalive.ps1` (restarts the server if it stops), `install-cuore-autostart.ps1` (a per-user scheduled task) and `make-cuore-shortcuts.ps1` (desktop and Start Menu shortcuts). They are optional.

### Network exposure

The script binds to all interfaces so a phone on the same network can reach the pages. The MES log corpus contains vehicle identifiers. Set an access token before exposing the app beyond a trusted network: `--token` or the `CUORE_TOKEN` environment variable. When a token is configured every page requires it. On Windows an inbound firewall rule for TCP 5000 is needed for other devices to connect; without it the app is reachable only from the PC itself.

## Health check

| URL | What it tells you |
|---|---|
| `http://127.0.0.1:5000/api/health` | The server is up and which profile it runs (`bench`). |
| `/api/status` | Server and adapter status. |
| `/api/capabilities` | What this host can do. Clients render this answer. |
| `/api/docs` | Interactive API reference (OpenAPI at `/api/openapi.json`). |

## Settings that matter

| Setting | Purpose |
|---|---|
| `CUORE_OBD_PORT`, `CUORE_OBD_BAUD` | Serial port and speed. Fallbacks: `OBD_PORT` / `OBD_BAUD`, then MES's own registry settings. |
| `CUORE_STATE_DIR` | Where CUORE stores everything it records. Default `%PROGRAMDATA%\cuore`. |
| `MES_LOG_DIR`, `MES_LOG_DIRS` | MES log folders (several, separated by the OS path separator; first match wins). |
| `MES_CSV_DIR`, `MES_CSV_DIRS` | Folders with MES CSV recordings. |
| `CUORE_TOKEN` | Access token for the web app. |
| `CUORE_HOST` | Bind address (default loopback in code; the launchers set all interfaces). |
| `CUORE_VERIFY_TTL`, `CUORE_AUTO_VERIFY` | How long a bus verification lasts (default 600 s) and whether sessions verify automatically (default on). |
| `CUORE_VISION_PROVIDER` | Photo reading. Default `none`; see [[Safety Rules|Safety-Rules]]. |

## First connection

1. **Close MultiEcuScan** or disconnect it. Only one program may hold the adapter's serial port. CUORE checks MES's state and a lock file before it opens the port and refuses if MES reports it is connected.
2. Plug the adapter into the OBD port with the ignition on. For a first look the engine can be off; a running engine gives a steadier picture and is needed for some tests.
3. Open `/live`. It shows the adapter, the **declared cable**, the buses and their verification state. With no bypass cable fitted, declare `none`; this reaches CAN-C only.
4. Use **Verify bus**, then **Probe adapter** and the OBD reads. CAN-C on this platform may carry no broadcast traffic, so verification falls back to one active Mode 01 request. See [[Vehicle Networks|Vehicle-Networks]].
5. For a whole-car read use the guided scan at `/v/{vin}/scan`, which pauses for each cable swap. See [[Guided Full Scan|Guided-Full-Scan]].
6. Open the vehicle's page (`/v/{vin}`) to see the bench view: what to do next for the car on the lift.

Every read is saved as an observation, so the Scans log, dossier and reports see it without extra steps.

## If something does not work

- Reads return `NO DATA`: check the ignition, the declared cable and the bus verification state on `/live`. A silent bus is a claim about the listener until a second method agrees.
- "Port in use" or access denied: another program holds the port (MES, a terminal, a leftover lock). Close it and retry. The USB cable or hub can also matter; the documents record a report of a USB 2.0 hub curing instability.
- A code change that "does not take" in Claude Code: the MCP servers run as long-lived processes. Reload them with `/mcp`.

Next: [[Features]] for a tour, or [[Safety Rules|Safety-Rules]] before touching the car.
