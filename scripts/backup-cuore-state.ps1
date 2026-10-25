# Durable, incremental, append-only archive of:
#   1. the CUORE car-state directory (C:\ProgramData\cuore by default) into
#      docs/vehicles/<VIN>/state-backup/<date>/
#   2. Claude Code session transcripts + their agent (task) output files and
#      scratchpad screenshots/html/json into docs/sessions/raw/<date>/<session>/
#   3. a regenerated docs/sessions/<date>-agent-discoveries.md digest for any
#      session that got new agent output this run.
#
# Idempotent: a file whose sha256 matches the last capture of the same key is
# never re-copied (it is marked 'skipped-unchanged' in the manifest, pointing
# back at the earlier capture). Nothing already written is ever deleted or
# overwritten -- re-running this script only ever adds.
#
#   .\scripts\backup-cuore-state.ps1                     # today's run, all defaults
#   .\scripts\backup-cuore-state.ps1 -SinceDays 9999      # full historical session backfill
#   .\scripts\backup-cuore-state.ps1 -Sessions a,b,c      # only these session ids
#   .\scripts\backup-cuore-state.ps1 -SkipSessionSweep    # car-state snapshot only
#   .\scripts\backup-cuore-state.ps1 -SkipCarState        # session sweep only
#   .\scripts\backup-cuore-state.ps1 -NoCommit            # archive only, no git add/commit
#
# Secrets: text files (.jsonl/.json/.html/.py/.md/.txt/.csv/.ps1) are scanned
# for sk-ant-*, AKIA*, and "password": "..." and those tokens (only) are
# replaced with [REDACTED] before hashing; the manifest notes when this
# happened. Edge/Chrome profile paths and files over 50MB (checked after any
# gzip) are skipped, not copied, and noted in the manifest.

param(
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$Date = (Get-Date).ToString('yyyy-MM-dd'),
    [string]$VIN = 'ZASFAKPN5J7B88115',
    [string]$StateDir = 'C:\ProgramData\cuore',
    [string]$ClaudeProjectsDir = (Join-Path $env:USERPROFILE '.claude\projects\C--Users-User'),
    [string]$ClaudeTempDir = (Join-Path $env:TEMP 'claude\C--Users-User'),
    [int]$SinceDays = 2,
    [string[]]$Sessions,
    [switch]$SkipCarState,
    [switch]$SkipSessionSweep,
    [switch]$NoCommit
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '_backup-common.ps1')

$touchedPaths = New-Object System.Collections.Generic.List[string]
$counts = @{}
function Bump($action) { $counts[$action] = ($counts[$action] + 1); if (-not $counts[$action]) { $counts[$action] = 1 } }

# ---------------------------------------------------------------- car state --
if (-not $SkipCarState) {
    $destDir = Join-Path $RepoRoot "docs\vehicles\$VIN\state-backup\$Date"
    $manifestJsonl = Join-Path $RepoRoot "docs\vehicles\$VIN\state-backup\MANIFEST.jsonl"
    $lastHashes = Get-ManifestLastHashes $manifestJsonl
    $todayEntries = @()

    $directFiles = @(
        'observations.jsonl', 'owner_events.jsonl', 'jobs.jsonl', 'checklists.json',
        'cases.jsonl', 'symptoms.jsonl', 'shop_visits.jsonl', 'audit.jsonl', 'fullscan_last.json',
        'notes.jsonl', 'service_records.jsonl', 'addresses.json', 'learned_dids.json',
        'feedback.jsonl', 'experience_inputs.jsonl', 'live_snapshots.jsonl', 'fullscan_guided.json',
        'mes_imports.json', 'mes_clear_watch.json', 'station.json',
        'element_locations.jsonl', 'path_tests.jsonl', 'wiggle_tests.jsonl', 'pin_data.jsonl',
        'sensor_checks.jsonl', 'sensor_ranges.jsonl',
        'fuse_checks.jsonl', 'fuse_items.jsonl'
    )
    foreach ($name in $directFiles) {
        $src = Join-Path $StateDir $name
        if (-not (Test-Path -LiteralPath $src)) { continue }
        $action = Copy-ArchiveItem -SrcFile $src -DestDir $destDir -RelName $name -Key "state:$name" `
            -LastHashes $lastHashes -ManifestPath $manifestJsonl -RunDate $Date
        Bump $action
        $lines = if ($name -like '*.jsonl') { Get-JsonlLineCount $src } else { $null }
        $todayEntries += [pscustomobject]@{ Name = $name; Action = $action; Lines = $lines; Size = (Get-Item $src).Length }
    }

    Get-ChildItem -LiteralPath $StateDir -Filter '*.bak-*' -File -ErrorAction SilentlyContinue | ForEach-Object {
        $action = Copy-ArchiveItem -SrcFile $_.FullName -DestDir $destDir -RelName $_.Name -Key "state:$($_.Name)" `
            -LastHashes $lastHashes -ManifestPath $manifestJsonl -RunDate $Date
        Bump $action
        $todayEntries += [pscustomobject]@{ Name = $_.Name; Action = $action; Lines = $null; Size = $_.Length }
    }

    foreach ($sub in @('scans', 'recordings', 'bench', 'live_layouts', 'media')) {
        $subDir = Join-Path $StateDir $sub
        if (-not (Test-Path -LiteralPath $subDir)) { continue }
        Get-ChildItem -LiteralPath $subDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
            $rel = "$sub/" + ($_.FullName.Substring($subDir.Length + 1) -replace '\\', '/')
            $relDestDir = Join-Path $destDir (Split-Path $rel -Parent)
            $action = Copy-ArchiveItem -SrcFile $_.FullName -DestDir $relDestDir -RelName (Split-Path $rel -Leaf) `
                -Key "state:$rel" -LastHashes $lastHashes -ManifestPath $manifestJsonl -RunDate $Date
            Bump $action
            $todayEntries += [pscustomobject]@{ Name = $rel; Action = $action; Lines = $null; Size = $_.Length }
        }
    }

    if (Test-Path -LiteralPath $destDir) { $touchedPaths.Add($destDir) }
    $touchedPaths.Add($manifestJsonl)

    # Human-readable manifest for this run's folder.
    $md = New-Object System.Text.StringBuilder
    [void]$md.AppendLine("# CUORE state backup - $Date")
    [void]$md.AppendLine()
    [void]$md.AppendLine("Source: ``$StateDir``. VIN ``$VIN``. Originals are never modified; this is a copy.")
    [void]$md.AppendLine()
    [void]$md.AppendLine("| item | action | size (bytes) | lines |")
    [void]$md.AppendLine("|---|---|---|---|")
    foreach ($e in $todayEntries) {
        $lineStr = if ($null -ne $e.Lines) { $e.Lines } else { '-' }
        [void]$md.AppendLine("| $($e.Name) | $($e.Action) | $($e.Size) | $lineStr |")
    }
    [void]$md.AppendLine()
    [void]$md.AppendLine("`skipped-unchanged` items are not duplicated in this folder -- same sha256 as the most recent prior capture; see ``MANIFEST.jsonl`` one directory up for full history and hashes.")
    if (Test-Path -LiteralPath $destDir) {
        [System.IO.File]::WriteAllText((Join-Path $destDir 'MANIFEST.md'), $md.ToString())
    } else {
        New-Item -ItemType Directory -Path $destDir -Force | Out-Null
        [System.IO.File]::WriteAllText((Join-Path $destDir 'MANIFEST.md'), $md.ToString())
    }
    $touchedPaths.Add((Join-Path $destDir 'MANIFEST.md'))
}

# ------------------------------------------------------------- session sweep --
$discoverySessions = @()
if (-not $SkipSessionSweep) {
    $manifestJsonl = Join-Path $RepoRoot 'docs\sessions\raw\MANIFEST.jsonl'
    $lastHashes = Get-ManifestLastHashes $manifestJsonl

    if ($Sessions) {
        $sessionIds = $Sessions
    } else {
        $cutoff = (Get-Date).Date.AddDays(-$SinceDays)
        $sessionIds = Get-ChildItem -LiteralPath $ClaudeProjectsDir -Filter '*.jsonl' -File -ErrorAction SilentlyContinue |
            Where-Object { $_.LastWriteTime -ge $cutoff } |
            ForEach-Object { $_.BaseName }
    }

    foreach ($sid in $sessionIds) {
        $destRoot = Join-Path $RepoRoot "docs\sessions\raw\$Date\$sid"
        $sessionTodayEntries = @()
        $sessionNewOutputs = @()

        $transcriptSrc = Join-Path $ClaudeProjectsDir "$sid.jsonl"
        if (Test-Path -LiteralPath $transcriptSrc) {
            $action = Copy-ArchiveItem -SrcFile $transcriptSrc -DestDir (Join-Path $destRoot 'transcript') `
                -RelName "$sid.jsonl" -Key "session:$sid:transcript" -LastHashes $lastHashes `
                -ManifestPath $manifestJsonl -RunDate $Date -SessionId $sid
            Bump $action
            $sessionTodayEntries += "transcript/$sid.jsonl : $action"
        }

        $tasksSrcDir = Join-Path $ClaudeTempDir "$sid\tasks"
        if (Test-Path -LiteralPath $tasksSrcDir) {
            Get-ChildItem -LiteralPath $tasksSrcDir -Filter '*.output' -File -ErrorAction SilentlyContinue | ForEach-Object {
                $action = Copy-ArchiveItem -SrcFile $_.FullName -DestDir (Join-Path $destRoot 'tasks') `
                    -RelName $_.Name -Key "session:$sid:tasks:$($_.Name)" -LastHashes $lastHashes `
                    -ManifestPath $manifestJsonl -RunDate $Date -SessionId $sid
                Bump $action
                $sessionTodayEntries += "tasks/$($_.Name) : $action"
                if ($action -eq 'copied' -or $action -eq 'redacted') { $sessionNewOutputs += $_.FullName }
            }
        }

        $scratchSrcDir = Join-Path $ClaudeTempDir "$sid\scratchpad"
        if (Test-Path -LiteralPath $scratchSrcDir) {
            $allowedExt = @('.png', '.jpg', '.jpeg', '.gif', '.html', '.htm', '.json')
            Get-ChildItem -LiteralPath $scratchSrcDir -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
                $rel = $_.FullName.Substring($scratchSrcDir.Length + 1) -replace '\\', '/'
                $ext = $_.Extension.ToLowerInvariant()
                if ($allowedExt -notcontains $ext) {
                    Add-ManifestEntry -ManifestPath $manifestJsonl -Key "session:$sid:scratchpad:$rel" `
                        -RunDate $Date -SessionId $sid -RelPath "scratchpad/$rel" -Sha256 '' -SizeBytes $_.Length `
                        -Action 'skipped-type' -Note 'not a screenshot/html/json file (out of scope)'
                    Bump 'skipped-type'
                    return
                }
                $relDestDir = Join-Path (Join-Path $destRoot 'scratchpad') (Split-Path $rel -Parent)
                $action = Copy-ArchiveItem -SrcFile $_.FullName -DestDir $relDestDir -RelName (Split-Path $rel -Leaf) `
                    -Key "session:$sid:scratchpad:$rel" -LastHashes $lastHashes -ManifestPath $manifestJsonl `
                    -RunDate $Date -SessionId $sid
                Bump $action
                $sessionTodayEntries += "scratchpad/$rel : $action"
            }
        }

        if (-not (Test-Path -LiteralPath $destRoot)) { New-Item -ItemType Directory -Path $destRoot -Force | Out-Null }
        $mdPath = Join-Path $destRoot 'MANIFEST.md'
        $md2 = New-Object System.Text.StringBuilder
        [void]$md2.AppendLine("# Session $sid raw archive - run $Date")
        [void]$md2.AppendLine()
        [void]$md2.AppendLine("Sources: ``$transcriptSrc``, ``$tasksSrcDir``, ``$scratchSrcDir``.")
        [void]$md2.AppendLine()
        if ($sessionTodayEntries.Count -gt 0) {
            foreach ($line in $sessionTodayEntries) { [void]$md2.AppendLine("- $line") }
        } else {
            [void]$md2.AppendLine("- nothing new or changed this run (unchanged, or no source found).")
        }
        [void]$md2.AppendLine()
        [void]$md2.AppendLine('Per-file sha256 and skip reasons: ``docs/sessions/raw/MANIFEST.jsonl`` (append-only, shared across all sessions/dates).')
        [System.IO.File]::WriteAllText($mdPath, $md2.ToString())
        $touchedPaths.Add($destRoot)

        if ($sessionNewOutputs.Count -gt 0) {
            $items = @()
            foreach ($f in $sessionNewOutputs) {
                $summary = Get-TaskOutputSummary -Path $f
                if ($summary) { $items += $summary }
            }
            if ($items.Count -gt 0) {
                $discoverySessions += [pscustomobject]@{ SessionId = $sid; Items = $items; FirstTs = ($items | Sort-Object Timestamp | Select-Object -First 1).Timestamp }
            }
        }
    }
    $touchedPaths.Add($manifestJsonl)
}

if ($discoverySessions.Count -gt 0) {
    $ordered = $discoverySessions | Sort-Object FirstTs
    $digestPath = Join-Path $RepoRoot "docs\sessions\$Date-agent-discoveries.md"
    Build-AgentDiscoveriesDoc -Sessions $ordered -OutPath $digestPath -RunDate $Date
    $touchedPaths.Add($digestPath)
}

# -------------------------------------------------------------------- summary --
"Backup run $Date complete."
$counts.GetEnumerator() | Sort-Object Name | ForEach-Object { "  $($_.Name): $($_.Value)" }

# ------------------------------------------------------------------------ git --
if (-not $NoCommit) {
    Push-Location $RepoRoot
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $isRepo = ((git rev-parse --is-inside-work-tree) -join '') -eq 'true'
        if ($isRepo -and $touchedPaths.Count -gt 0) {
            $existing = $touchedPaths | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique
            if ($existing.Count -gt 0) {
                git add -- $existing | Out-Null
                $staged = git diff --cached --name-only
                if ($staged) {
                    git commit -m "Archive: $Date state + sessions" -q | Out-Null
                    $hash = (git rev-parse --short HEAD)
                    "Committed locally as $hash (no push)."
                } else {
                    "Nothing new to commit (all unchanged)."
                }
            }
        } elseif (-not $isRepo) {
            "RepoRoot '$RepoRoot' is not a git repository; skipped commit."
        }
    } finally {
        $ErrorActionPreference = $prevEap
        Pop-Location
    }
}
