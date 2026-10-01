# Keeps the cuore bench server running on this PC, with no dependency on the
# network or on Claude. Run by the scheduled task "CUORE Server" (at logon,
# and re-checked every 5 minutes). Install or remove the task with
# install-cuore-autostart.ps1.
#
# Loop, every 10 s:
#   * nothing listening on 127.0.0.1:5000        -> start cuore
#   * listening but /api/health fails 3x in a row -> restart cuore (hung)
# Server output goes to C:\ProgramData\cuore\logs\server.log (rotated at 10 MB).
# Only one keep-alive runs at a time (a named mutex).

$ErrorActionPreference = 'SilentlyContinue'
$Repo   = $PSScriptRoot
$Port   = 5000
$Health = "http://127.0.0.1:$Port/api/health"
$Python = Join-Path $Repo ".venv\Scripts\python.exe"
$LogDir = if ($env:CUORE_STATE_DIR) { Join-Path $env:CUORE_STATE_DIR "logs" } else { "C:\ProgramData\cuore\logs" }
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log     = Join-Path $LogDir "server.log"
$KeepLog = Join-Path $LogDir "keepalive.log"

$created = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\CuoreKeepAlive", [ref]$created)
if (-not $created) {
    # another keep-alive is already watching; note it so silent exits are visible
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  launch $PID skipped: another keep-alive holds the lock" |
        Out-File -FilePath $KeepLog -Append -Encoding utf8
    exit 0
}

function Write-KeepLog([string]$msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Out-File -FilePath $KeepLog -Append -Encoding utf8
}

function Get-Listener {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" }
    return $null
}

function Test-Health {
    # 200 with cuore's own health body ({"ok":..,"profile":..,"version":..})
    try {
        $r = Invoke-WebRequest -UseBasicParsing $Health -TimeoutSec 5
        return ($r.StatusCode -eq 200 -and $r.Content -match '"profile"')
    } catch { return $false }
}

function Test-IsCuore($p) {
    # The command line can be unreadable (process started with other rights),
    # so also accept a python.exe that answers cuore's health check.
    if ($p.CommandLine -match '-m\s+cuore') { return $true }
    if (-not $p.CommandLine -and $p.Name -eq 'python.exe') { return $true }
    return (Test-Health)
}

function Start-Cuore {
    if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 10MB)) {
        Move-Item -Force $Log "$Log.old"
    }
    # cmd /c so stdout and stderr land in the log; hidden window
    $cmd = "`"$Python`" -m cuore --profile bench --port $Port >> `"$Log`" 2>&1"
    # the extra outer quotes survive cmd's strip-first-and-last-quote rule
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$cmd`"" -WorkingDirectory $Repo -WindowStyle Hidden
    Write-KeepLog "started cuore"
    for ($i = 0; $i -lt 60; $i++) { if (Test-Health) { Write-KeepLog "cuore healthy"; return }; Start-Sleep 1 }
    Write-KeepLog "cuore did not answer within 60 s"
}

Write-KeepLog "keep-alive running (pid $PID)"
Register-EngineEvent PowerShell.Exiting -Action { Write-KeepLog "keep-alive exiting (pid $PID)" } | Out-Null
$fails = 0
while ($true) {
    $listener = Get-Listener
    if (-not $listener) {
        $fails = 0
        Start-Cuore
    } elseif (-not (Test-IsCuore $listener)) {
        # another program owns the port: never touch it, just note it
        Write-KeepLog "port $Port is held by another program: $($listener.CommandLine)"
        Start-Sleep 60
    } elseif (Test-Health) {
        $fails = 0
    } else {
        $fails++
        if ($fails -ge 3) {
            Write-KeepLog "cuore not answering (3 checks); restarting pid $($listener.ProcessId)"
            Stop-Process -Id $listener.ProcessId -Force
            Start-Sleep 2
            $fails = 0
        }
    }
    Start-Sleep 10
}
