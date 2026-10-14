# Shared helpers for scripts/backup-cuore-state.ps1 and
# scripts/save-session-artifacts.ps1. Dot-source this file; it defines
# functions only, no side effects.
#
#   . "$PSScriptRoot\_backup-common.ps1"

function Get-Sha256Hex {
    # Retries briefly: a file actively being written by a live process (e.g.
    # this very session's own task-output files) can be transiently locked.
    param([Parameter(Mandatory)][string]$Path)
    $attempts = 0
    while ($true) {
        try {
            return (Get-FileHash -Algorithm SHA256 -LiteralPath $Path -ErrorAction Stop).Hash.ToLowerInvariant()
        } catch {
            $attempts++
            if ($attempts -ge 4) { throw }
            Start-Sleep -Milliseconds (150 * $attempts)
        }
    }
}

function Test-IsEdgeProfilePath {
    # Heuristic: Edge/Chrome profile dirs under a browser user-data directory.
    param([Parameter(Mandatory)][string]$Path)
    return ($Path -match '(?i)[\\/](Edge|Chrome)[\\/]User ?Data[\\/]') -or
           ($Path -match '(?i)[\\/](Default|Profile \d+)[\\/](Cache|Cookies|History|Local Storage)')
}

function Compress-FileToGzip {
    # Writes $Dest (a new .gz file) from $Src using standard gzip format.
    param([Parameter(Mandatory)][string]$Src, [Parameter(Mandatory)][string]$Dest)
    $inStream = [System.IO.File]::OpenRead($Src)
    try {
        $outStream = [System.IO.File]::Create($Dest)
        try {
            $gz = New-Object System.IO.Compression.GZipStream($outStream, [System.IO.Compression.CompressionLevel]::Optimal)
            try { $inStream.CopyTo($gz) } finally { $gz.Dispose() }
        } finally { $outStream.Dispose() }
    } finally { $inStream.Dispose() }
}

$script:RedactableExtensions = @('.jsonl', '.json', '.html', '.htm', '.py', '.md', '.txt', '.csv', '.ps1', '.output')

function Get-RedactedText {
    # Pure string transform: redacts sk-ant-*, AKIA*, and "password": "..." in
    # $Text. Used both for files (Redact-SecretsInPlace) and for text already
    # extracted into memory (e.g. the discoveries digest), so a secret can
    # never leak into a derived document just because it wasn't re-read from
    # the (redacted) archived copy.
    param([Parameter(Mandatory)][AllowEmptyString()][string]$Text)
    $out = [regex]::Replace($Text, 'sk-ant-[A-Za-z0-9_\-]{8,}', 'sk-ant-[REDACTED]')
    $out = [regex]::Replace($out, 'AKIA[A-Z0-9]{16}', 'AKIA[REDACTED]')
    $out = [regex]::Replace($out, '("password"\s*:\s*")[^"]*(")', '${1}[REDACTED]${2}', [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    return $out
}

function Redact-SecretsInPlace {
    # Returns $true if the file was rewritten with redactions applied.
    param([Parameter(Mandatory)][string]$Path)
    $ext = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    if ($script:RedactableExtensions -notcontains $ext) { return $false }
    $raw = [System.IO.File]::ReadAllText($Path)
    $redacted = Get-RedactedText $raw
    if ($redacted -ne $raw) {
        [System.IO.File]::WriteAllText($Path, $redacted)
        return $true
    }
    return $false
}

function Get-ManifestLastHashes {
    # Reads a JSONL manifest and returns a hashtable: key -> last known sha256
    # for entries whose action was 'copied' or 'redacted' (i.e. physically present).
    param([Parameter(Mandatory)][string]$ManifestPath)
    $map = @{}
    if (Test-Path -LiteralPath $ManifestPath) {
        Get-Content -LiteralPath $ManifestPath | ForEach-Object {
            if ($_.Trim() -eq '') { return }
            try { $o = $_ | ConvertFrom-Json } catch { return }
            if ($o.action -eq 'copied' -or $o.action -eq 'redacted') {
                $map[$o.key] = $o.source_sha256
            }
        }
    }
    return $map
}

function Add-ManifestEntry {
    param(
        [Parameter(Mandatory)][string]$ManifestPath,
        [Parameter(Mandatory)][string]$Key,
        [string]$RunDate,
        [string]$SessionId,
        [string]$RelPath,
        [string]$Sha256,
        [string]$SourceSha256,
        [long]$SizeBytes,
        [Nullable[long]]$Lines,
        [Parameter(Mandatory)][string]$Action,
        [string]$Note
    )
    $entry = [ordered]@{
        ts            = (Get-Date).ToString('o')
        run_date      = $RunDate
        session_id    = $SessionId
        key           = $Key
        relpath       = $RelPath
        sha256        = $Sha256
        source_sha256 = $SourceSha256
        size_bytes    = $SizeBytes
        lines         = $Lines
        action        = $Action
        note          = $Note
    }
    $dir = Split-Path -Parent $ManifestPath
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $line = $entry | ConvertTo-Json -Compress
    # Transient sharing-violation retries: AV/indexer can briefly hold a lock
    # on a just-written small file under a tight append loop.
    $attempts = 0
    while ($true) {
        try {
            $fs = [System.IO.File]::Open($ManifestPath, [System.IO.FileMode]::Append, [System.IO.FileAccess]::Write, [System.IO.FileShare]::Read)
            try {
                $bytes = [System.Text.Encoding]::UTF8.GetBytes($line + "`r`n")
                $fs.Write($bytes, 0, $bytes.Length)
            } finally { $fs.Dispose() }
            break
        } catch {
            $attempts++
            if ($attempts -ge 6) { throw }
            Start-Sleep -Milliseconds (100 * $attempts)
        }
    }
}

function Copy-ArchiveItem {
    # Copies $SrcFile into $DestDir (creating it) as $RelName, applying:
    #  - size skip (> $MaxBytes, default 50MB, checked AFTER gzip if gzip applied)
    #  - gzip if raw size > $GzipThreshold (default 5MB)
    #  - secret redaction on text files (before hashing, after copy)
    #  - skip-if-unchanged via $LastHashes[$Key] (compares the PRE-copy source hash)
    # Appends one line to $ManifestPath in all cases (copied / skipped-unchanged /
    # skipped-size / skipped-type). Returns the action string.
    param(
        [Parameter(Mandatory)][string]$SrcFile,
        [Parameter(Mandatory)][string]$DestDir,
        [Parameter(Mandatory)][string]$RelName,
        [Parameter(Mandatory)][string]$Key,
        [Parameter(Mandatory)][hashtable]$LastHashes,
        [Parameter(Mandatory)][string]$ManifestPath,
        [string]$RunDate,
        [string]$SessionId,
        [long]$MaxBytes = 50MB,
        [long]$GzipThreshold = 5MB
    )
    if (Test-IsEdgeProfilePath $SrcFile) {
        Add-ManifestEntry -ManifestPath $ManifestPath -Key $Key -RunDate $RunDate -SessionId $SessionId `
            -RelPath $RelName -Sha256 '' -SizeBytes 0 -Action 'skipped-edge-profile' -Note 'Edge/Chrome profile path'
        return 'skipped-edge-profile'
    }

    try {
        $srcHash = Get-Sha256Hex $SrcFile
    } catch {
        Add-ManifestEntry -ManifestPath $ManifestPath -Key $Key -RunDate $RunDate -SessionId $SessionId `
            -RelPath $RelName -Sha256 '' -SizeBytes 0 -Action 'skipped-locked' -Note "source unreadable: $($_.Exception.Message)"
        return 'skipped-locked'
    }
    if ($LastHashes.ContainsKey($Key) -and $LastHashes[$Key] -eq $srcHash) {
        Add-ManifestEntry -ManifestPath $ManifestPath -Key $Key -RunDate $RunDate -SessionId $SessionId `
            -RelPath $RelName -Sha256 $srcHash -SourceSha256 $srcHash -SizeBytes (Get-Item -LiteralPath $SrcFile).Length `
            -Action 'skipped-unchanged' -Note 'hash matches most recent prior capture'
        return 'skipped-unchanged'
    }

    try {
        New-Item -ItemType Directory -Path $DestDir -Force | Out-Null
        $rawSize = (Get-Item -LiteralPath $SrcFile).Length
        $destFile = Join-Path $DestDir (Split-Path -Leaf $RelName)
        Copy-Item -LiteralPath $SrcFile -Destination $destFile -Force -ErrorAction Stop

        # Redact BEFORE gzip (and regardless of size) so a large transcript is
        # not exempted from the secret check just because it gets compressed.
        $redacted = Redact-SecretsInPlace -Path $destFile

        $didGzip = $false
        if ($rawSize -gt $GzipThreshold) {
            $gzDest = "$destFile.gz"
            Compress-FileToGzip -Src $destFile -Dest $gzDest
            Remove-Item -LiteralPath $destFile -Force
            $destFile = $gzDest
            $didGzip = $true
        }
    } catch {
        if ($destFile -and (Test-Path -LiteralPath $destFile)) { Remove-Item -LiteralPath $destFile -Force -ErrorAction SilentlyContinue }
        Add-ManifestEntry -ManifestPath $ManifestPath -Key $Key -RunDate $RunDate -SessionId $SessionId `
            -RelPath $RelName -Sha256 '' -SourceSha256 $srcHash -SizeBytes 0 -Action 'skipped-locked' `
            -Note "copy/compress failed: $($_.Exception.Message)"
        return 'skipped-locked'
    }

    $finalSize = (Get-Item -LiteralPath $destFile).Length
    if ($finalSize -gt $MaxBytes) {
        Remove-Item -LiteralPath $destFile -Force
        Add-ManifestEntry -ManifestPath $ManifestPath -Key $Key -RunDate $RunDate -SessionId $SessionId `
            -RelPath $RelName -Sha256 $srcHash -SourceSha256 $srcHash -SizeBytes $rawSize -Action 'skipped-size' `
            -Note "exceeds $MaxBytes byte limit (final $finalSize bytes$(if($didGzip){' after gzip'}))"
        return 'skipped-size'
    }

    $finalHash = Get-Sha256Hex $destFile
    $finalSize = (Get-Item -LiteralPath $destFile).Length
    $action = if ($redacted) { 'redacted' } else { 'copied' }
    $note = if ($didGzip) { 'gzipped' } else { '' }
    if ($redacted) { $note = ($note + ' secrets redacted (pattern match)').Trim() }

    Add-ManifestEntry -ManifestPath $ManifestPath -Key $Key -RunDate $RunDate -SessionId $SessionId `
        -RelPath $RelName -Sha256 $finalHash -SourceSha256 $srcHash -SizeBytes $finalSize -Action $action -Note $note
    return $action
}

function Get-JsonlLineCount {
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return 0 }
    (Get-Content -LiteralPath $Path | Where-Object { $_.Trim() -ne '' } | Measure-Object).Count
}

function Get-TaskOutputSummary {
    # Extracts (Timestamp, Heading/task text, final report) from one
    # tasks\*.output JSONL transcript. Returns $null for empty files, plain
    # (non-agent) logs, or transcripts with no extractable final report.
    param([Parameter(Mandatory)][string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $null }
    $fi = Get-Item -LiteralPath $Path
    if ($fi.Length -eq 0) { return $null }

    $firstLine = Get-Content -LiteralPath $Path -TotalCount 1
    if (-not $firstLine) { return $null }
    try { $firstObj = $firstLine | ConvertFrom-Json -ErrorAction Stop } catch { return $null }
    if (-not $firstObj -or $firstObj.type -ne 'user') { return $null }

    $taskText = $firstObj.message.content
    if ($taskText -is [System.Array]) {
        $taskText = ($taskText | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }) -join "`n"
    }
    if (-not $taskText) { return $null }

    $ts = $fi.LastWriteTime
    try { $ts = [datetime]$firstObj.timestamp } catch { }

    $raw = [System.IO.File]::ReadAllText($Path)
    $report = $null
    $handbackMatches = [regex]::Matches($raw, '"name"\s*:\s*"SubagentHandback"[^\{]*?"input"\s*:\s*\{\s*"message"\s*:\s*"((?:[^"\\]|\\.)*)"')
    if ($handbackMatches.Count -gt 0) {
        $capture = $handbackMatches[$handbackMatches.Count - 1].Groups[1].Value
        try { $report = ('"' + $capture + '"') | ConvertFrom-Json -ErrorAction Stop } catch { $report = $capture }
    } else {
        $lines = Get-Content -LiteralPath $Path
        $start = $lines.Count - 1
        $floor = [Math]::Max(0, $lines.Count - 30)
        for ($i = $start; $i -ge $floor; $i--) {
            if (-not $lines[$i].Trim()) { continue }
            try { $o = $lines[$i] | ConvertFrom-Json -ErrorAction Stop } catch { continue }
            if ($o.type -ne 'assistant') { continue }
            $content = $o.message.content
            if ($content -is [System.Array]) {
                $texts = $content | Where-Object { $_.type -eq 'text' } | ForEach-Object { $_.text }
                if ($texts) { $report = ($texts -join "`n`n"); break }
            } elseif ($content -is [string] -and $content) {
                $report = $content; break
            }
        }
    }
    if (-not $report) { return $null }
    $report = Get-RedactedText $report

    $headingSource = (Get-RedactedText ($taskText.Trim() -replace '\s+', ' '))
    $heading = if ($headingSource.Length -gt 100) { $headingSource.Substring(0, 100) + '...' } else { $headingSource }

    [pscustomobject]@{
        Timestamp = $ts
        Heading   = $heading
        Report    = $report
        File      = Split-Path -Leaf $Path
    }
}

function Build-AgentDiscoveriesDoc {
    # $Sessions: ordered array of @{ SessionId = '...'; Items = <array of
    # Get-TaskOutputSummary results> }, already in the order to render.
    param(
        [Parameter(Mandatory)][array]$Sessions,
        [Parameter(Mandatory)][string]$OutPath,
        [Parameter(Mandatory)][string]$RunDate
    )
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.AppendLine("# Agent discoveries - $RunDate")
    [void]$sb.AppendLine()
    [void]$sb.AppendLine("Durable record of what each subagent found or built, extracted from its task-output transcript (the last `SubagentHandback` call, or failing that the final assistant text). Generated by ``scripts/backup-cuore-state.ps1`` / ``scripts/save-session-artifacts.ps1``; regenerated whenever a session has new agent output to report.")
    [void]$sb.AppendLine()
    [void]$sb.AppendLine("## Index")
    foreach ($s in $Sessions) {
        [void]$sb.AppendLine("- Session ``$($s.SessionId)`` - $($s.Items.Count) agent report(s)")
    }
    [void]$sb.AppendLine()
    foreach ($s in $Sessions) {
        [void]$sb.AppendLine("## Session $($s.SessionId)")
        [void]$sb.AppendLine()
        $items = $s.Items | Sort-Object Timestamp
        $n = 0
        foreach ($item in $items) {
            $n++
            [void]$sb.AppendLine("### $n. $($item.Heading)")
            [void]$sb.AppendLine()
            [void]$sb.AppendLine("*Source: ``$($item.File)``, launched $($item.Timestamp.ToString('o'))*")
            [void]$sb.AppendLine()
            [void]$sb.AppendLine($item.Report)
            [void]$sb.AppendLine()
        }
    }
    $dir = Split-Path -Parent $OutPath
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    [System.IO.File]::WriteAllText($OutPath, $sb.ToString())
}
