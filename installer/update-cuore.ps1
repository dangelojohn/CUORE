# Updates an installed CUORE from its update source, or rolls back to the previous version.
#
#   update-cuore.ps1                 apply the update from <state>\update_source.json (folder or URL)
#   update-cuore.ps1 -Check          only say whether a newer version is available
#   update-cuore.ps1 -Rollback       restore the version kept before the last update
#   update-cuore.ps1 -Source D       use this folder/URL instead of update_source.json
#   update-cuore.ps1 -DryRun         print the steps only
#
# Every file's SHA-256 is verified against the source's release.json before anything is
# replaced. Only files listed in the manifest are touched: never the state folder or .venv.
# CUORE is restarted afterwards (-NoRestart to skip).

param(
    [string]$InstallDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
    [string]$StateDir   = $(if ($env:CUORE_STATE_DIR) { $env:CUORE_STATE_DIR } else { "C:\ProgramData\cuore" }),
    [string]$Source     = "",
    [switch]$Check,
    [switch]$Rollback,
    [switch]$Force,
    [switch]$NoRestart,
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'
$Py = Join-Path $InstallDir ".venv\Scripts\python.exe"
$Port = 5000
$action = if ($Rollback) { "rollback" } elseif ($Check) { "check" } else { "apply" }

"CUORE update: $action"
"  install : $InstallDir"
"  state   : $StateDir (never modified)"
if ($DryRun) {
    "(dry run) 1. run: $Py -m cuore.services.updates $action --install-dir ... --state-dir ..."
    if ($action -ne "check") {
        "(dry run) 2. stop the running CUORE (the python '-m cuore' process on port $Port) before the files change"
        "(dry run) 3. restart CUORE with start-cuore.ps1 and check /api/health"
    }
    exit 0
}
if (-not (Test-Path $Py)) { Write-Host "STOP: $Py not found; is this an installed CUORE?" -ForegroundColor Red; exit 1 }

function Stop-Cuore {
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $conn) { return }
    $p = Get-CimInstance Win32_Process -Filter "ProcessId=$($conn.OwningProcess)"
    if ($p.CommandLine -match '-m\s+cuore' -or ($p.Name -eq 'python.exe' -and -not $p.CommandLine)) {
        Stop-Process -Id $p.ProcessId -Force
        for ($i = 0; $i -lt 20 -and (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 250 }
    } else { Write-Warning "Port $Port is used by another program; not touching it." }
}

$pyArgs = @("-m", "cuore.services.updates", $action, "--install-dir", $InstallDir, "--state-dir", $StateDir)
if ($Source) { $pyArgs += @("--source", $Source) }
if ($Force)  { $pyArgs += "--force" }

if ($action -eq "check") {
    Push-Location $InstallDir; try { & $Py @pyArgs } finally { Pop-Location }
    exit $LASTEXITCODE
}

if (-not $NoRestart) { Stop-Cuore }
Push-Location $InstallDir
try { & $Py @pyArgs; $rc = $LASTEXITCODE } finally { Pop-Location }
if ($rc -ne 0) {
    Write-Host "Update did not change anything (see the message above)." -ForegroundColor Yellow
}
if (-not $NoRestart) {
    $env:CUORE_STATE_DIR = $StateDir
    # if the keep-alive task is running it starts CUORE itself within ~10 s; start-cuore.ps1 copes with both cases
    & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir "start-cuore.ps1") -Page "/about"
    try {
        $h = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 5
        "CUORE is up: $(($h.Content | ConvertFrom-Json).version)"
    } catch { Write-Warning "CUORE did not answer /api/health yet; check $StateDir\logs." }
}
exit $rc
