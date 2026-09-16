# Sync local main with origin/main without pull conflicts.
# Uses rebase + autostash (configured in this repo's .git/config).
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

Write-Host "Fetching and rebasing onto origin/main (auto-stashing local changes)..." -ForegroundColor Cyan
git fetch origin
git pull

if ($LASTEXITCODE -ne 0) {
    Write-Host "`nSync failed. If autostash left conflicts, run: git status" -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "`nSync complete." -ForegroundColor Green
git status -sb
