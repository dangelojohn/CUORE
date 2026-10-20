# OBD2 MCP Server

A Model Context Protocol (MCP) server that connects Claude to your vehicle's OBD2 diagnostic system. Supports direct OBD2 adapter communication (USB and Bluetooth, including OBDLink MX++) and integrates with Multiecuscan for deep Fiat/Alfa Romeo/Lancia diagnostics.

## Features

### Direct OBD2 (via python-OBD)
- **Live sensor data** — RPM, speed, temperatures, fuel trims, throttle position, and 100+ standard PIDs
- **Diagnostic trouble codes** — Read current, pending, and freeze-frame DTCs
- **Vehicle info** — OBD compliance, fuel type, protocol, adapter details
- **O2 sensor diagnostics** — Voltage and current readings for all banks/sensors
- **Actuator commands** — Clear DTCs and send raw commands (with safety interlocks)

### Multiecuscan Integration
- **Session log parsing** — Extract DTCs, parameters, and vehicle info from Multiecuscan logs
- **CSV/XML export analysis** — Statistical summaries of logged data
- **DTC history search** — Find when a specific fault code appeared across all sessions
- **Manufacturer-specific codes** — Access to Fiat/Alfa/Lancia proprietary diagnostics

## Requirements

- **Python 3.10+**
- **Windows 10/11** (for Multiecuscan integration)
- **OBD2 adapter**: OBDLink MX++ (Bluetooth), OBDLink SX (USB), or any ELM327-compatible adapter
- **Multiecuscan** (optional, for Fiat/Alfa/Lancia deep diagnostics)

## Quick Start

### 1. Setup

```bash
# Clone or download this project, then:
setup.bat
```

Or manually:
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

### 2. Configure

Copy `config.example.json` to `config.json` and edit:

```json
{
    "obd2": {
        "port": "auto",          // or "COM3", "COM5", etc.
        "baudrate": 115200
    },
    "bluetooth": {
        "enabled": true,
        "device_name": "OBDLink MX+"
    },
    "multiecuscan": {
        "log_directory": "C:\\Users\\Public\\Documents\\Multiecuscan\\Logs"
    },
    "safety": {
        "allow_actuator_commands": false,
        "allow_dtc_clear": false
    }
}
```

### 3. Pair Your Bluetooth Adapter

For OBDLink MX++:
1. Turn vehicle ignition ON
2. Open Windows Settings → Bluetooth & devices
3. Pair "OBDLink MX+" (PIN: 1234 or 0000)
4. Note the assigned COM port in Device Manager → Ports

### 4. Add to Claude Desktop

Edit your Claude Desktop config file (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
    "mcpServers": {
        "obd2": {
            "command": "python",
            "args": ["-m", "src.server"],
            "cwd": "C:\\path\\to\\obd2-mcp-server"
        }
    }
}
```

Or if using the virtual environment:
```json
{
    "mcpServers": {
        "obd2": {
            "command": "C:\\path\\to\\obd2-mcp-server\\.venv\\Scripts\\python.exe",
            "args": ["-m", "src.server"],
            "cwd": "C:\\path\\to\\obd2-mcp-server"
        }
    }
}
```

### 5. Use It

Talk to Claude naturally:

> "Connect to my car and read the engine sensors"

> "Are there any trouble codes?"

> "Show me the latest Multiecuscan scan results"

> "What was the coolant temperature when that P0300 code was set?"

> "Search all my Multiecuscan sessions for code P0171"

## Available Tools (27 total)

### Connection
| Tool | Description |
|------|-------------|
| `connect_obd2` | Connect to OBD2 adapter (auto-detect or specify port) |
| `disconnect_obd2` | Disconnect from adapter |
| `connection_status` | Check connection state |
| `discover_adapters` | Scan all serial ports for adapters |
| `reconnect_obd2` | Reconnect after a drop |

### Live Sensors
| Tool | Description |
|------|-------------|
| `read_obd2_sensor` | Read a single sensor (RPM, SPEED, etc.) |
| `read_obd2_sensor_group` | Read a group (engine, fuel, emissions, performance, status) |
| `read_all_sensors` | Read every supported sensor |
| `list_sensor_groups` | Show available sensor groups |

### Diagnostics
| Tool | Description |
|------|-------------|
| `read_trouble_codes` | Read current DTCs and MIL status |
| `read_pending_trouble_codes` | Read pending/unconfirmed DTCs |
| `read_freeze_frame_data` | Read freeze frame snapshot |
| `vehicle_info` | Vehicle identification and connection info |
| `list_supported_commands` | All PIDs supported by the vehicle |
| `read_o2_sensor_data` | O2 sensor readings |

### Actuators (disabled by default)
| Tool | Description |
|------|-------------|
| `clear_trouble_codes` | Clear DTCs and MIL |
| `send_raw_obd_command` | Send raw hex command |
| `actuator_safety_status` | Check safety config |
| `actuator_command_history` | View command log |

### Multiecuscan
| Tool | Description |
|------|-------------|
| `multiecuscan_status` | Check installation status |
| `multiecuscan_list_logs` | List session log files |
| `multiecuscan_list_exports` | List CSV/XML exports |
| `multiecuscan_read_log` | Parse a session log |
| `multiecuscan_read_csv` | Analyze a CSV export |
| `multiecuscan_read_xml` | Parse an XML export |
| `multiecuscan_latest_session` | Most recent scan results |
| `multiecuscan_search_dtc` | Search DTCs across all sessions |

## Safety

Actuator commands (DTC clearing, raw commands) are **disabled by default**. To enable:

1. Edit `config.json`
2. Set `safety.allow_actuator_commands` and/or `safety.allow_dtc_clear` to `true`
3. Commands still require `confirmed=True` parameter
4. A cooldown timer prevents rapid-fire commands
5. All commands are logged

## Project Structure

```
obd2-mcp-server/
├── src/
│   ├── __init__.py
│   ├── server.py          # MCP server + all tool registrations
│   ├── connection.py      # OBD2 adapter connection manager
│   ├── diagnostics.py     # Sensor reading, DTCs, vehicle info
│   ├── actuators.py       # Write commands with safety guards
│   ├── multiecuscan.py    # Multiecuscan log/export parser
│   └── config.py          # Configuration management
├── tests/
│   └── __init__.py
├── config.example.json    # Template configuration
├── pyproject.toml         # Python project config
├── setup.bat              # Windows setup script
└── README.md
```

## Troubleshooting

**"No OBD2 adapter found"**
- Ensure adapter is plugged into vehicle and ignition is ON
- For Bluetooth: check it's paired in Windows Bluetooth settings
- Try specifying the port directly: `connect_obd2(port="COM5")`
- Run `discover_adapters()` to see available ports

**"Vehicle not responding"**
- Turn ignition to ON (not just accessory)
- Some vehicles need engine running for certain PIDs
- Try a different protocol: set `obd2.protocol` in config

**"Multiecuscan not found"**
- Verify the install path in config.json
- Check log/export directories exist and have files
- Run a scan in Multiecuscan first to generate log files
