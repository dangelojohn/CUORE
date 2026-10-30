# Builds a CUORE release folder (and zip) from this checkout.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File installer\build-release.ps1 [-OutDir dist] [-SkipZip]
#
# Output: <OutDir>\cuore-<version>\ (release.json manifest with SHA-256 of every file, VERSION,
# requirements.txt, the app, data, docs and the start/keepalive/shortcut/installer scripts) and
# <OutDir>\cuore-<version>.zip. Nothing is read from C:\ProgramData or the .git folder.
# What was left out, by rule, is printed at the end.

param(
    [string]$OutDir = "dist",
    [switch]$SkipZip
)

$ErrorActionPreference = 'Stop'
$Repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not [IO.Path]::IsPathRooted($OutDir)) { $OutDir = Join-Path $Repo $OutDir }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

$verLine = Select-String -Path (Join-Path $Repo "cuore\__init__.py") -Pattern '^__version__\s*=\s*"([^"]+)"' | Select-Object -First 1
if (-not $verLine) { throw "cannot read __version__ from cuore/__init__.py" }
$Version = $verLine.Matches[0].Groups[1].Value

$Release = Join-Path $OutDir "cuore-$Version"
if ($Release.StartsWith($Repo + "\") -and -not ($Release.StartsWith((Join-Path $Repo "dist") + "\"))) {
    # a release folder inside the checkout would be scanned by the next build
    Write-Warning "OutDir is inside the checkout ($OutDir); it is skipped by the 'dist' rule only under <repo>\dist."
}
if (Test-Path $Release) { Remove-Item -Recurse -Force $Release }
New-Item -ItemType Directory -Force -Path $Release | Out-Null

# -- what goes in --------------------------------------------------------------
# docs: only what a shop needs (user guides, reference data, the mobile contract, the bundle schema the app
# reads). Research notes, project/corporate papers, design reviews, integration internals and the reference
# car's own reports and bulletin PDFs stay out of the release (privacy audit 2026-10-30).
$IncludeDirs  = @("cuore", "mes-log-mcp", "obd2-mcp", "data", "docs/handbook", "docs/hardware", "docs/reference",
                  "docs/mobile", "scripts", "installer")
$IncludeFiles = @("start-cuore.ps1", "cuore-keepalive.ps1", "install-cuore-autostart.ps1", "make-cuore-shortcuts.ps1",
                  "docs/integration/cuore_bundle.schema.json")

# -- exclusion rules -----------------------------------------------------------
$DirNames = @(".git", ".venv", "venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "dist", ".rollback", ".staging")
$FilePatterns = [ordered]@{
    "*.jsonl transcripts" = "*.jsonl"
    "compiled python"     = "*.pyc"
    "logs/backups"        = @("*.log", "*.bak", "*.orig")
    "password-named"      = "*password*"
    "secret-named"        = "*secret*"
    "token-named"         = "*token*"
    ".env files"          = @(".env", ".env.*")
    "session archives"    = @("*session*.zip", "*session*.7z", "*session*.tar", "*session*.tar.gz", "*session*.tgz")
}
$Excluded = [ordered]@{}   # rule -> list of paths
function Add-Excluded([string]$rule, [string]$rel) {
    if (-not $Excluded.Contains($rule)) { $Excluded[$rule] = New-Object System.Collections.Generic.List[string] }
    $Excluded[$rule].Add($rel)
}

function Get-DirRule([string]$rel, [string]$name) {
    if ($DirNames -contains $name) { return "directory $name" }
    if ($rel -in @("cuore/tests", "mes-log-mcp/tests", "obd2-mcp/tests")) { return "test suites" }
    if ($rel -eq "data/captures") { return "data/captures" }
    if ($rel -eq "docs/sessions") { return "docs/sessions" }
    if ($rel -like "docs/vehicles/*/state-backup") { return "docs/vehicles/*/state-backup" }
    if ($rel -like "docs/vehicles/*/sessions") { return "docs/vehicles/*/sessions (session archives)" }
    return $null
}
function Get-FileRule([string]$name) {
    foreach ($k in $FilePatterns.Keys) {
        foreach ($pat in @($FilePatterns[$k])) { if ($name -like $pat) { return $k } }
    }
    return $null
}

$Files = New-Object System.Collections.Generic.List[object]   # @{ rel; src }
function Walk([string]$dir, [string]$rel) {
    foreach ($item in Get-ChildItem -LiteralPath $dir -Force) {
        $r = if ($rel) { "$rel/$($item.Name)" } else { $item.Name }
        if ($item.PSIsContainer) {
            $rule = Get-DirRule $r $item.Name
            if ($rule) { Add-Excluded $rule "$r/"; continue }
            if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { Add-Excluded "symlink/junction" "$r/"; continue }
            Walk $item.FullName $r
        } else {
            $rule = Get-FileRule $item.Name
            if ($rule) { Add-Excluded $rule $r; continue }
            if ($item.FullName -like "C:\ProgramData\*") { Add-Excluded "ProgramData" $r; continue }
            $Files.Add(@{ rel = $r; src = $item.FullName })
        }
    }
}
foreach ($d in $IncludeDirs) {
    $p = Join-Path $Repo $d
    if (Test-Path $p) { Walk $p $d } else { Write-Warning "missing directory $d" }
}
foreach ($f in $IncludeFiles) {
    $p = Join-Path $Repo $f
    if (Test-Path $p) { $Files.Add(@{ rel = $f; src = $p }) } else { Write-Warning "missing file $f" }
}
$Files.Add(@{ rel = "requirements.txt"; src = (Join-Path $Repo "cuore\requirements.txt") })

# -- copy, VERSION, manifest ---------------------------------------------------
foreach ($f in $Files) {
    $dest = Join-Path $Release ($f.rel -replace '/', '\')
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $f.src -Destination $dest -Force
}
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText((Join-Path $Release "VERSION"), "$Version`n", $utf8)

$Commit = "unknown"
try {
    $c = (& git -C $Repo rev-parse --short HEAD 2>$null)
    if ($LASTEXITCODE -eq 0 -and $c) { $Commit = "$c".Trim() }
} catch { }

$hashes = [ordered]@{}
$all = Get-ChildItem -LiteralPath $Release -Recurse -File -Force | Sort-Object FullName
foreach ($f in $all) {
    $rel = $f.FullName.Substring($Release.Length + 1) -replace '\\', '/'
    $hashes[$rel] = (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash.ToLower()
}
$manifest = [ordered]@{
    version    = $Version
    build_date = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
    git_commit = $Commit
    files      = $hashes
}
[IO.File]::WriteAllText((Join-Path $Release "release.json"), ($manifest | ConvertTo-Json -Depth 4), $utf8)

$zip = $null
if (-not $SkipZip) {
    $zip = Join-Path $OutDir "cuore-$Version.zip"
    if (Test-Path $zip) { Remove-Item -Force $zip }
    Compress-Archive -Path (Join-Path $Release "*") -DestinationPath $zip
}

# -- report --------------------------------------------------------------------
"Release folder : $Release"
if ($zip) { "Release zip    : $zip" }
"Version        : $Version  (commit $Commit)"
"Files          : $($hashes.Count) (+ release.json)"
"Excluded by rule:"
foreach ($k in $Excluded.Keys) {
    $n = $Excluded[$k].Count
    $sample = ($Excluded[$k] | Select-Object -First 3) -join ", "
    "  {0,-45} {1,6}  e.g. {2}" -f $k, $n, $sample
}
"Not included (outside the include list): .git, .venv, external, archive, wiki, loose files in the repo root"
