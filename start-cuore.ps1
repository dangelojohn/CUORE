# Launches the cuore bench server (if it is not already up) and opens a page
# in the default browser. What the desktop and Start Menu shortcuts point to.
#
#   start-cuore.ps1                                  -> home page
#   start-cuore.ps1 -Page /v/ZASFAKPN5J7B88115/gauges -> that page
#   start-cuore.ps1 -Restart                         -> restart the server first
#
# A cuore server started before the newest code change is restarted
# automatically, so a shortcut never opens a stale build without the latest
# pages. Only a process whose command line is "python -m cuore" is stopped.

param(
    [string]$Page = "/",
    [switch]$Restart
)

$ErrorActionPreference = 'SilentlyContinue'
Set-Location -Path $PSScriptRoot

$Port = 5000
$Base = "http://127.0.0.1:$Port"
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

function Get-CuoreProcess {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return $null }
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)"
    return $proc
}

function Get-NewestCodeTime {
    # newest source change under cuore/ and mes-log-mcp/mes/ (committed or not)
    $files = Get-ChildItem -Path (Join-Path $PSScriptRoot "cuore"), (Join-Path $PSScriptRoot "mes-log-mcp\mes") `
                           -Recurse -Include *.py, *.html, *.css, *.js -File -ErrorAction SilentlyContinue |
             Where-Object { $_.FullName -notmatch '\\(tests|__pycache__)\\' }
    return ($files | Measure-Object -Property LastWriteTime -Maximum).Maximum
}

$proc = Get-CuoreProcess
if ($proc) {
    # command line may be unreadable if another account/rights started it:
    # fall back to "python.exe answering cuore's health check"
    $healthy = $false
    try { $healthy = (Invoke-WebRequest -UseBasicParsing "$Base/api/health" -TimeoutSec 3).Content -match '"profile"' } catch { }
    $isCuore = ($proc.CommandLine -match '-m\s+cuore') -or ((-not $proc.CommandLine) -and $proc.Name -eq 'python.exe') -or $healthy
    $started = $proc.CreationDate
    $stale = $isCuore -and ($started -lt (Get-NewestCodeTime))
    if ($isCuore -and ($Restart -or $stale)) {
        Stop-Process -Id $proc.ProcessId -Force
        for ($i = 0; $i -lt 20 -and (Get-CuoreProcess); $i++) { Start-Sleep -Milliseconds 250 }
        $proc = $null
    } elseif (-not $isCuore) {
        # Something else holds port 5000: do not touch it, just tell the user.
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show("Port $Port is in use by another program:`n$($proc.CommandLine)`n`ncuore was not started.", "CUORE") | Out-Null
        exit 1
    }
}

# If the "CUORE Server" keep-alive is running it starts cuore itself (within
# ~10 s); starting a second copy here would just lose the race for the port.
$keepAlive = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" |
             Where-Object { $_.CommandLine -match 'cuore-keepalive\.ps1' }
if (-not $proc -and -not $keepAlive) {
    Start-Process -FilePath $Python `
                  -ArgumentList "-m", "cuore", "--profile", "bench", "--port", "$Port" `
                  -WorkingDirectory $PSScriptRoot -WindowStyle Minimized
}

# Wait until cuore actually answers (a cold start loads the MES log corpus).
for ($i = 0; $i -lt 120; $i++) {
    try {
        $r = Invoke-WebRequest -UseBasicParsing "$Base/api/health" -TimeoutSec 2
        if ($r.StatusCode -eq 200) { break }
    } catch { }
    Start-Sleep -Milliseconds 500
}

if (-not $Page.StartsWith("/")) { $Page = "/" + $Page }
Start-Process "$Base$Page"
