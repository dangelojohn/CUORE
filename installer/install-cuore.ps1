# Installs (or repairs) CUORE on a shop PC from a release folder built by build-release.ps1.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install-cuore.ps1 [-InstallDir D] [-StateDir D]
#                                                                         [-ReleaseDir D] [-DryRun] [-SkipAdmin] [-NoStart]
#
#   -DryRun   only prints the steps; changes nothing.
#   Re-running is a repair: files are copied over, the venv is re-checked, an existing web token and
#   the state folder are left exactly as they are. The state folder is NEVER deleted.
#   Nothing is downloaded except Python packages from pip (requirements.txt).

param(
    [string]$InstallDir = (Join-Path $env:ProgramFiles "CUORE"),
    [string]$StateDir   = "C:\ProgramData\cuore",
    [string]$ReleaseDir = "",
    [switch]$DryRun,
    [switch]$SkipAdmin,
    [switch]$NoStart,
    [switch]$SkipShortcuts,
    [switch]$SkipAutostart
)

$ErrorActionPreference = 'Stop'
if (-not $ReleaseDir) { $ReleaseDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
$Port = 5000
$n = 0
function Step([string]$text) { $script:n++; "[{0}] {1}{2}" -f $script:n, $(if ($DryRun) { "(dry run) " } else { "" }), $text }
function Stop-Install([string]$msg) { Write-Host "STOP: $msg" -ForegroundColor Red; exit 1 }

# 1. Windows --------------------------------------------------------------------
Step "Check Windows 10 or later"
if ($env:OS -ne "Windows_NT") { Stop-Install "CUORE installs on Windows only." }
if ([Environment]::OSVersion.Version.Major -lt 10) { Stop-Install "Windows 10 or later is required." }

# 2. Python 3.11+ ---------------------------------------------------------------
Step "Check Python 3.11 or later"
function Find-Python {
    $cands = @(@("py", "-3"), @("python"), @("python3"))
    foreach ($c in $cands) {
        $exe = Get-Command $c[0] -ErrorAction SilentlyContinue
        if (-not $exe) { continue }
        try {
            $args2 = @($c | Select-Object -Skip 1) + @("-c", "import sys; print(int(sys.version_info[:2] >= (3, 11)), sys.executable)")
            $out = & $exe.Source @args2 2>$null
            if ($LASTEXITCODE -eq 0 -and "$out" -match '^1 (.+)$') { return $Matches[1].Trim() }
        } catch { }
    }
    return $null
}
$SysPython = Find-Python
if (-not $SysPython) {
    Write-Host "Python 3.11 or later was not found on this PC." -ForegroundColor Yellow
    Write-Host "Get it from https://www.python.org/downloads/windows/ (tick 'Add python.exe to PATH'),"
    Write-Host "then run this installer again. Nothing has been downloaded or changed."
    if ($DryRun) { "    (dry run: continuing to list the remaining steps)" } else { exit 1 }
} else { "    found $SysPython" }

# 3. Release folder --------------------------------------------------------------
Step "Check the release folder $ReleaseDir"
$manifestPath = Join-Path $ReleaseDir "release.json"
if (-not (Test-Path $manifestPath)) { Stop-Install "release.json not found in $ReleaseDir. Run this from an unpacked release (or pass -ReleaseDir)." }
$manifest = Get-Content -Raw -Encoding UTF8 $manifestPath | ConvertFrom-Json
"    CUORE $($manifest.version), built $($manifest.build_date), commit $($manifest.git_commit)"
$InstallFull = [IO.Path]::GetFullPath($InstallDir)
$ReleaseFull = [IO.Path]::GetFullPath($ReleaseDir)
$inPlace = ($InstallFull.TrimEnd('\') -ieq $ReleaseFull.TrimEnd('\'))
if (-not $DryRun) {
    Step "Verify every release file against release.json"
    $bad = @()
    foreach ($p in $manifest.files.PSObject.Properties) {
        $f = Join-Path $ReleaseDir ($p.Name -replace '/', '\')
        if (-not (Test-Path -LiteralPath $f) -or (Get-FileHash -LiteralPath $f -Algorithm SHA256).Hash.ToLower() -ne $p.Value) { $bad += $p.Name }
    }
    if ($bad.Count) { Stop-Install "$($bad.Count) release file(s) are missing or damaged (first: $($bad[0])). Re-copy the release." }
} else { Step "Verify every release file against release.json" }

# 4. Copy -------------------------------------------------------------------------
if ($inPlace) { Step "Release is already in $InstallDir; no copy needed (repair)" }
else {
    Step "Copy the release to $InstallDir (existing .venv is kept)"
    if (-not $DryRun) {
        New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
        Copy-Item -Path (Join-Path $ReleaseDir "*") -Destination $InstallDir -Recurse -Force
    }
}

# 5. venv + pip --------------------------------------------------------------------
$VenvPy = Join-Path $InstallDir ".venv\Scripts\python.exe"
Step "Create the virtual environment $InstallDir\.venv (if missing)"
if (-not $DryRun -and -not (Test-Path $VenvPy)) {
    & $SysPython -m venv (Join-Path $InstallDir ".venv")
    if ($LASTEXITCODE -ne 0) { Stop-Install "could not create the virtual environment." }
}
Step "Install the packages from requirements.txt (pip, needs internet the first time)"
if (-not $DryRun) {
    & $VenvPy -m pip install --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Stop-Install "pip failed. Check the internet connection and run the installer again." }
}

# 6. State folder + token -----------------------------------------------------------
Step "Create the state folder $StateDir (an existing one is never touched or deleted)"
if (-not $DryRun) { New-Item -ItemType Directory -Force -Path $StateDir | Out-Null }
$tokenFile = Join-Path $StateDir "web_token.txt"
Step "Write a random web token to $tokenFile (kept if it already exists)"
if (-not $DryRun -and -not (Test-Path $tokenFile)) {
    $bytes = New-Object byte[] 24
    $rng = [Security.Cryptography.RandomNumberGenerator]::Create(); $rng.GetBytes($bytes); $rng.Dispose()
    $token = ($bytes | ForEach-Object { $_.ToString("x2") }) -join ""
    [IO.File]::WriteAllText($tokenFile, $token, (New-Object System.Text.UTF8Encoding($false)))
}
if ($StateDir -ne "C:\ProgramData\cuore") {
    Step "Point CUORE at the custom state folder (user environment variable CUORE_STATE_DIR; sign out and in once)"
    if (-not $DryRun) { [Environment]::SetEnvironmentVariable("CUORE_STATE_DIR", $StateDir, "User"); $env:CUORE_STATE_DIR = $StateDir }
}

# 7. First admin (only if the accounts module exists) -----------------------------------
$hasAccounts = Test-Path (Join-Path $InstallDir "cuore\accounts.py")
if ($SkipAdmin) { Step "First admin account: skipped (-SkipAdmin)" }
elseif (-not $hasAccounts) { Step "First admin account: this release has no accounts module yet; skipped" }
else {
    Step "Create the first admin account (python -m cuore.accounts create-admin; you will be asked for a name and password)"
    if (-not $DryRun) {
        $env:CUORE_STATE_DIR = $StateDir
        Push-Location $InstallDir
        try { & $VenvPy -m cuore.accounts create-admin } finally { Pop-Location }
        if ($LASTEXITCODE -ne 0) { Write-Warning "create-admin did not finish; run it again later: $VenvPy -m cuore.accounts create-admin" }
    }
}

# 8. Autostart + shortcuts ------------------------------------------------------------------
if ($SkipShortcuts) { Step "Shortcuts: skipped" }
else {
    Step "Create the desktop and Start Menu shortcuts (make-cuore-shortcuts.ps1)"
    if (-not $DryRun) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir "make-cuore-shortcuts.ps1") }
}
if ($SkipAutostart) { Step "Autostart: skipped" }
else {
    Step "Install the 'CUORE Server' scheduled task for this user (install-cuore-autostart.ps1); it also starts CUORE"
    if (-not $DryRun) { & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $InstallDir "install-cuore-autostart.ps1") }
}

# 9. Start + health ----------------------------------------------------------------------------
if ($NoStart) { Step "Start and health check: skipped (-NoStart)" }
else {
    Step "Wait for http://127.0.0.1:$Port/api/health"
    if (-not $DryRun) {
        $ok = $false
        for ($i = 0; $i -lt 120 -and -not $ok; $i++) {
            try { $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:$Port/api/health" -TimeoutSec 2; $ok = ($r.StatusCode -eq 200) } catch { Start-Sleep -Milliseconds 1000 }
        }
        if ($ok) { "    CUORE is up: $(($r.Content | ConvertFrom-Json).version). Open http://127.0.0.1:$Port/" }
        else { Write-Warning "CUORE did not answer within 2 minutes. See $StateDir\logs\server.log and keepalive.log." }
    }
}
if ($DryRun) { "Dry run finished: nothing was changed." } else { "Install finished." }
