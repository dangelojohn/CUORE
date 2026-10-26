# Keeps the cuore bench server running on this PC, with no dependency on the
# network or on Claude. Run by the scheduled task "CUORE Server" (at logon,
# and re-checked every 5 minutes). Install or remove the task with
# install-cuore-autostart.ps1.
#
# Loop, every 10 s:
#   * nothing listening on 127.0.0.1:5000        -> start cuore
#   * listening but /api/health fails 5x in a row (20 s timeout each, so a
#     slow page render is never mistaken for a hang) -> restart cuore
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
    # keep the keep-alive log from growing without bound (rotate at 2 MB)
    if ((Test-Path $KeepLog) -and ((Get-Item $KeepLog).Length -gt 2MB)) { Move-Item -Force $KeepLog "$KeepLog.old" }
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $msg" | Out-File -FilePath $KeepLog -Append -Encoding utf8
}

function Get-Listener {
    $c = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($c) { return Get-CimInstance Win32_Process -Filter "ProcessId=$($c.OwningProcess)" }
    return $null
}

function Test-Health([int]$TimeoutSec = 20) {
    # 200 with cuore's own health body ({"ok":..,"profile":..,"version":..}).
    # 20 s: cuore is a single process and a heavy page (MES corpus, PDFs) can
    # hold it for several seconds; 5 s x3 once killed it mid-render.
    try {
        $r = Invoke-WebRequest -UseBasicParsing $Health -TimeoutSec $TimeoutSec
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

function Test-CuoreStarting {
    # a "-m cuore" python started in the last 3 minutes that is not listening
    # yet (cold start loads the MES corpus): do not launch a second copy
    $p = Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
         Where-Object { $_.CommandLine -match '-m\s+cuore' -and $_.CreationDate -gt (Get-Date).AddMinutes(-3) }
    return [bool]$p
}

function Start-Cuore {
    if ((Test-Path $Log) -and ((Get-Item $Log).Length -gt 10MB)) {
        Move-Item -Force $Log "$Log.old"
    }
    # cmd /c so stdout and stderr land in the log; hidden window
    $cmd = "`"$Python`" -m cuore --profile bench --host 0.0.0.0 --port $Port >> `"$Log`" 2>&1"
    # the extra outer quotes survive cmd's strip-first-and-last-quote rule
    Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$cmd`"" -WorkingDirectory $Repo -WindowStyle Hidden
    Write-KeepLog "started cuore"
    for ($i = 0; $i -lt 60; $i++) { if (Test-Health 3) { Write-KeepLog "cuore healthy"; return }; Start-Sleep 1 }
    Write-KeepLog "cuore did not answer within 60 s"
}

Write-KeepLog "keep-alive running (pid $PID)"
Register-EngineEvent PowerShell.Exiting -Action { Write-KeepLog "keep-alive exiting (pid $PID)" } | Out-Null
$fails = 0
while ($true) {
    $listener = Get-Listener
    if (-not $listener) {
        $fails = 0
        if (Test-CuoreStarting) { Start-Sleep 10 } else { Start-Cuore }
    } elseif (-not (Test-IsCuore $listener)) {
        # another program owns the port: never touch it, just note it
        Write-KeepLog "port $Port is held by another program: $($listener.CommandLine)"
        Start-Sleep 60
    } elseif (Test-Health) {
        $fails = 0
    } else {
        $fails++
        if ($fails -ge 5) {
            Write-KeepLog "cuore not answering (5 checks of 20 s); restarting pid $($listener.ProcessId)"
            Stop-Process -Id $listener.ProcessId -Force
            Start-Sleep 2
            $fails = 0
        }
    }
    Start-Sleep 10
}
