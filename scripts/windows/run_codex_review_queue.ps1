# run_codex_review_queue.ps1 - RoboSim Eval: run several read-only Codex review rounds in order, waiting out the
# account usage limit between attempts. Meant to be started detached, e.g.:
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',
#     'D:\RoboSim-Eval\scripts\windows\run_codex_review_queue.ps1',
#     '-Items','2026-09-29-d0/round1c-a,2026-09-29-d1/round1','-NotBefore','2026-09-30T03:38'
# -Items is a comma list of "<review folder under ReviewRoot>/<round>"; without it, -Rounds are run in -Dir.
# For each item in order: skip it when codex-<round>-report.md already exists in its folder; otherwise run
# run_codex_review.ps1 -Round <round> -Dir <folder>. A failed attempt keeps its files as
# codex-<round>-attemptN-{status,stderr,stdout}.txt. When the failure is the usage limit, the "try again at <time>" in
# stderr is parsed (codex_queue_lib.ps1) and the queue sleeps until 3 minutes after it (30 minutes when the time cannot be parsed), then
# retries the same round. Any other failure stops the queue (exit 1). At most MaxAttempts attempts per round (exit 2
# when exhausted). Only one queue runs at a time: <ReviewRoot>\codex-queue.lock holds the owner PID (exit 3 if taken).
# Log: <ReviewRoot>\codex-queue.log. Writes only review files; Codex itself runs with --sandbox read-only.
param(
    [string]$Items = '',
    [string]$Rounds = 'round1c-a,round1c-b,round1c-c,round1c-d',
    [string]$Dir = '',
    [string]$ReviewRoot = '',
    [int]$MaxAttempts = 4,
    [string]$NotBefore = ''
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent   # this checkout (a worktree queues its own reviews)
if (-not $ReviewRoot) { $ReviewRoot = Join-Path $repo 'docs\review' }
if (-not $Dir) { $Dir = Join-Path $repo 'docs\review\2026-09-29-d0' }
# Start-Process joins -ArgumentList items with spaces without quoting them: pass -NotBefore without spaces (ISO form
# 2026-09-30T03:38); a value containing a space is split and parameter binding fails before anything is logged.
$log = Join-Path $ReviewRoot 'codex-queue.log'
$lock = Join-Path $ReviewRoot 'codex-queue.lock'
$runner = Join-Path $PSScriptRoot 'run_codex_review.ps1'
function Write-QueueLog([string]$msg) { "$(Get-Date -Format o) $msg" | Out-File $log -Append -Encoding utf8 }
function Wait-Until([datetime]$when, [string]$why) {
    $secs = [int][Math]::Ceiling(($when - (Get-Date)).TotalSeconds)
    Write-QueueLog "sleep until $($when.ToString('s')) ($secs s): $why"
    if ($secs -gt 0) { Start-Sleep -Seconds $secs }
}
. (Join-Path $PSScriptRoot 'codex_queue_lib.ps1')
function Get-RetryTime([string]$stderrFile) {
    $when = ConvertFrom-RetryText -Text ((Get-Content -Raw $stderrFile -ErrorAction SilentlyContinue) + '') -Now (Get-Date)
    if ($null -eq $when) {
        Write-QueueLog "no retry time found in $stderrFile; waiting 30 min"
        return (Get-Date).AddMinutes(30)
    }
    return $when
}

if ($Items) {
    $queue = @($Items -split ',' | ForEach-Object {
        $p = $_.Trim(); $i = $p.LastIndexOf('/')
        if ($i -lt 1) { throw "bad item '$p' (expected <folder>/<round>)" }
        [pscustomobject]@{ Dir = (Join-Path $ReviewRoot $p.Substring(0, $i)); Round = $p.Substring($i + 1) }
    })
} else {
    $queue = @($Rounds -split ',' | ForEach-Object { [pscustomobject]@{ Dir = $Dir; Round = $_.Trim() } })
}

if (Test-Path $lock) {
    $owner = (Get-Content $lock -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($owner -and (Get-Process -Id ([int]$owner) -ErrorAction SilentlyContinue)) {
        Write-QueueLog "refuse: another queue (pid $owner) holds $lock"; exit 3
    }
}
"$PID" | Out-File $lock -Encoding ascii
Write-QueueLog "queue start pid=$PID items=$(($queue | ForEach-Object { (Split-Path $_.Dir -Leaf) + '/' + $_.Round }) -join ',') max_attempts=$MaxAttempts not_before=$NotBefore"
try {
    if ($NotBefore) { Wait-Until ([datetime]::Parse($NotBefore)) 'NotBefore' }
    foreach ($item in $queue) {
        $d = $item.Dir; $round = $item.Round; $tag = (Split-Path $d -Leaf) + '/' + $round
        $report = Join-Path $d "codex-$round-report.md"
        if (-not (Test-Path (Join-Path $d "codex-prompt-$round.md"))) { Write-QueueLog "stop: prompt for $tag missing"; exit 1 }
        if (Test-Path $report) { Write-QueueLog "skip $tag (report exists)"; continue }
        $done = $false
        # attempt numbers continue after files a previous queue run left behind, so nothing is overwritten (shell-8)
        $prev = @(Get-ChildItem $d -Filter "codex-$round-attempt*-status.txt" -ErrorAction SilentlyContinue |
            ForEach-Object { if ($_.Name -match 'attempt(\d+)-') { [int]$Matches[1] } })
        $base = if ($prev.Count) { ($prev | Measure-Object -Maximum).Maximum } else { 0 }
        for ($attempt = 1; $attempt -le $MaxAttempts -and -not $done; $attempt++) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Round $round -Dir $d | Out-Null
            $rc = $LASTEXITCODE
            $stderr = Join-Path $d "codex-$round-stderr.txt"
            $limit = (Test-Path $stderr) -and (Test-UsageLimitText -Text ((Get-Content -Raw $stderr) + ''))
            Write-QueueLog "item=$tag attempt=$attempt exit=$rc report=$(Test-Path $report) usage_limit=$limit"
            if ($rc -eq 0 -and (Test-Path $report)) { $done = $true; continue }
            foreach ($kind in 'status', 'stderr', 'stdout') {
                $f = Join-Path $d "codex-$round-$kind.txt"
                if (Test-Path $f) { Move-Item $f (Join-Path $d "codex-$round-attempt$($base + $attempt)-$kind.txt") }
            }
            if (Test-Path $report) { Move-Item $report (Join-Path $d "codex-$round-attempt$($base + $attempt)-report.md") }
            if (-not $limit) { Write-QueueLog "stop: $tag failed without a usage-limit message"; exit 1 }
            $when = Get-RetryTime (Join-Path $d "codex-$round-attempt$($base + $attempt)-stderr.txt")
            if ($attempt -lt $MaxAttempts) { Wait-Until $when "usage limit on $tag" }
        }
        if (-not $done) { Write-QueueLog "stop: $tag still failing after $MaxAttempts attempts"; exit 2 }
    }
    Write-QueueLog 'queue end: all items have reports'
    exit 0
} finally {
    Remove-Item $lock -ErrorAction SilentlyContinue
}
