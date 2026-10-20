@echo off
echo ============================================
echo   OBD2 MCP Server - Setup for Windows
echo ============================================
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from python.org
    pause
    exit /b 1
)

echo [1/3] Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

echo [2/3] Installing dependencies...
pip install -e ".[dev]"

echo [3/3] Creating config file...
if not exist config.json (
    copy config.example.json config.json
    echo Created config.json from template. Edit it with your settings.
) else (
    echo config.json already exists, skipping.
)

echo.
echo ============================================
echo   Setup complete!
echo ============================================
echo.
echo Next steps:
echo   1. Edit config.json with your adapter and Multiecuscan settings
echo   2. Pair your OBDLink MX++ via Windows Bluetooth settings
echo   3. Add this server to your Claude Desktop config:
echo.
echo      "obd2": {
echo        "command": "python",
echo        "args": ["-m", "src.server"],
echo        "cwd": "%CD%"
echo      }
echo.
echo   4. Or run standalone: python -m src.server
echo.
pause
