# One-shot archive of a single Claude Code session: its transcript, every
# tasks\*.output agent transcript, and scratchpad screenshots/html/json --
# into docs/sessions/raw/<date>/<session-id>/ -- plus a regenerated
# docs/sessions/<date>-agent-discoveries.md if that session has agent output.
# Thin wrapper around backup-cuore-state.ps1's session-sweep logic, scoped to
# one session id and skipping the car-state snapshot.
#
#   .\scripts\save-session-artifacts.ps1 -SessionId 7cb02eb5-e299-4baf-b34b-9eb82aebbf17
#   .\scripts\save-session-artifacts.ps1 -SessionId <id> -Date 2026-10-13 -NoCommit

param(
    [Parameter(Mandatory)][string]$SessionId,
    [string]$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,
    [string]$Date = (Get-Date).ToString('yyyy-MM-dd'),
    [string]$ClaudeProjectsDir = (Join-Path $env:USERPROFILE '.claude\projects\C--Users-User'),
    [string]$ClaudeTempDir = (Join-Path $env:TEMP 'claude\C--Users-User'),
    [switch]$NoCommit
)

& (Join-Path $PSScriptRoot 'backup-cuore-state.ps1') `
    -RepoRoot $RepoRoot -Date $Date -ClaudeProjectsDir $ClaudeProjectsDir -ClaudeTempDir $ClaudeTempDir `
    -Sessions @($SessionId) -SkipCarState -NoCommit:$NoCommit
