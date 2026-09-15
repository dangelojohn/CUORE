# Launches the cuore bench server (if it is not already up) and opens it
# in the default browser. What the desktop shortcut points to.

$ErrorActionPreference = 'SilentlyContinue'
Set-Location -Path $PSScriptRoot

$already = Get-NetTCPConnection -LocalPort 5000 -State Listen -ErrorAction SilentlyContinue
if (-not $already) {
    Start-Process -FilePath (Join-Path $PSScriptRoot ".venv\Scripts\python.exe") `
                  -ArgumentList "-m", "cuore", "--profile", "bench", "--port", "5000" `
                  -WorkingDirectory $PSScriptRoot -WindowStyle Normal
    Start-Sleep -Seconds 3
}

Start-Process "http://127.0.0.1:5000/"
