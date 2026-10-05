# Refresh the sea level stations from this PC and push the result.
#
# UHSLC drops connections from GitHub runner IPs, so the sea level half of the
# update runs here (Windows Task Scheduler) while CI keeps doing SST.
#
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts\update_sl_local.ps1
#
# Everything is appended to %LOCALAPPDATA%\el_nino\update_sl.log. Exits non-zero
# on any failure, and never pushes after a failed pull or a failed update.

$Repo   = Split-Path -Parent $PSScriptRoot
$Python = 'C:\Users\a47575\projects\venv313\Scripts\python.exe'
$LogDir = Join-Path $env:LOCALAPPDATA 'el_nino'
$Log    = Join-Path $LogDir 'update_sl.log'
$Fresh  = 'data/output/freshness.json'

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$env:PYTHONUNBUFFERED = '1'
$env:PYTHONIOENCODING = 'utf-8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Log([string]$msg) {
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $msg
    Add-Content -Path $Log -Value $line -Encoding UTF8
    Write-Host $line
}

# Run a native command, log its output line by line, return its exit code.
function Run([string]$exe, [string[]]$argv) {
    Log ("> {0} {1}" -f $exe, ($argv -join ' '))
    & $exe @argv 2>&1 | ForEach-Object { Log ("  " + $_.ToString()) }
    return $LASTEXITCODE
}

function Fail([string]$msg) {
    Log "FAILED: $msg"
    Log '=== end (failure) ==='
    exit 1
}

# Put docs and freshness.json back as they were, so a failed run leaves a
# clean tree and the next pull is not blocked.
function Restore {
    Run 'git' @('checkout', '--', 'docs', $Fresh) | Out-Null
}

Log '=== update_sl_local start ==='
Set-Location $Repo

$dirty = git status --porcelain --untracked-files=no
if ($dirty) { Fail "working tree has uncommitted changes:`n$($dirty -join "`n")" }

if ((Run 'git' @('pull', '--rebase')) -ne 0) {
    Run 'git' @('rebase', '--abort') | Out-Null
    Fail 'git pull --rebase failed'
}

if ((Run $Python @('scripts/update_website.py', '--sl-only', '--no-push')) -ne 0) {
    Restore
    Fail 'update_website.py exited non-zero'
}

# update_website.py exits 0 when a station fails (it keeps the old data and
# notes "fetch pending"). Treat that as a failed update here: do not push.
$state = Get-Content $Fresh -Raw | ConvertFrom-Json
$stations = @($state.stations.PSObject.Properties | ForEach-Object { $_.Value })
$stamp = ($stations | ForEach-Object { $_.last_attempt } | Sort-Object | Select-Object -Last 1)
$failed = @($stations | Where-Object { $_.last_attempt -eq $stamp -and -not $_.ok } | ForEach-Object { $_.name })
if ($failed.Count -gt 0) {
    Restore
    Fail ('not refreshed: ' + ($failed -join ', '))
}

Run 'git' @('add', 'docs') | Out-Null
Run 'git' @('add', '-f', $Fresh) | Out-Null
git diff --cached --quiet
if ($LASTEXITCODE -ne 0) {
    $month = ($stations | ForEach-Object { $_.as_of } | Sort-Object | Select-Object -Last 1)
    if ((Run 'git' @('commit', '-m', "data: update sea level through $month [local]")) -ne 0) { Fail 'git commit failed' }
} else {
    Log 'No new data; site already up to date.'
}

# Push this run's commit, or one left behind by an earlier failed push.
$ahead = git rev-list --count '@{u}..HEAD'
if ([int]$ahead -gt 0) {
    if ((Run 'git' @('push')) -ne 0) { Fail 'git push failed (commit kept locally; the next run pushes it)' }
}

Log '=== end (ok) ==='
exit 0
