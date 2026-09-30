# run_codex_review_queue.ps1 - RoboSim Eval: run several read-only Codex review rounds in order, waiting out the
# account usage limit between attempts. Meant to be started detached, e.g.:
#   Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',
#     'D:\RoboSim-Eval\scripts\windows\run_codex_review_queue.ps1','-Rounds','round1c-a,round1c-b','-NotBefore','2026-09-30 03:38'
# For each round in order: skip it when codex-<round>-report.md already exists; otherwise run run_codex_review.ps1.
# A failed attempt keeps its files as codex-<round>-attemptN-{status,stderr,stdout}.txt. When the failure is the usage
# limit, the "try again at <time>" in stderr is parsed and the queue sleeps until 3 minutes after it (30 minutes when the
# time cannot be parsed), then retries the same round. Any other failure stops the queue (exit 1). At most MaxAttempts
# attempts per round (exit 2 when exhausted). Only one queue runs at a time (codex-queue.lock holds the owner PID).
# Log: <Dir>\codex-queue.log. Writes nothing outside <Dir>; Codex itself runs with --sandbox read-only.
param(
    [string]$Rounds = 'round1c-a,round1c-b,round1c-c,round1c-d',
    [string]$Dir = 'D:\RoboSim-Eval\docs\review\2026-09-29-d0',
    [int]$MaxAttempts = 4,
    [string]$NotBefore = ''
)
$ErrorActionPreference = 'Stop'
$log = Join-Path $Dir 'codex-queue.log'
$lock = Join-Path $Dir 'codex-queue.lock'
$runner = Join-Path $PSScriptRoot 'run_codex_review.ps1'
function Write-QueueLog([string]$msg) { "$(Get-Date -Format o) $msg" | Out-File $log -Append -Encoding utf8 }
function Wait-Until([datetime]$when, [string]$why) {
    $secs = [int][Math]::Ceiling(($when - (Get-Date)).TotalSeconds)
    Write-QueueLog "sleep until $($when.ToString('s')) ($secs s): $why"
    if ($secs -gt 0) { Start-Sleep -Seconds $secs }
}

if (Test-Path $lock) {
    $owner = (Get-Content $lock -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($owner -and (Get-Process -Id ([int]$owner) -ErrorAction SilentlyContinue)) {
        Write-QueueLog "refuse: another queue (pid $owner) holds $lock"; exit 3
    }
}
"$PID" | Out-File $lock -Encoding ascii
Write-QueueLog "queue start pid=$PID rounds=$Rounds max_attempts=$MaxAttempts not_before=$NotBefore"
try {
    if ($NotBefore) { Wait-Until ([datetime]::Parse($NotBefore)) 'NotBefore' }
    foreach ($round in ($Rounds -split ',')) {
        $round = $round.Trim()
        $report = Join-Path $Dir "codex-$round-report.md"
        if (-not (Test-Path (Join-Path $Dir "codex-prompt-$round.md"))) { Write-QueueLog "stop: prompt for $round missing"; exit 1 }
        if (Test-Path $report) { Write-QueueLog "skip $round (report exists)"; continue }
        $done = $false
        for ($attempt = 1; $attempt -le $MaxAttempts -and -not $done; $attempt++) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $runner -Round $round -Dir $Dir | Out-Null
            $rc = $LASTEXITCODE
            $stderr = Join-Path $Dir "codex-$round-stderr.txt"
            $limit = (Test-Path $stderr) -and [bool](Select-String -Path $stderr -Pattern 'hit your usage limit' -Quiet)
            Write-QueueLog "round=$round attempt=$attempt exit=$rc report=$(Test-Path $report) usage_limit=$limit"
            if ($rc -eq 0 -and (Test-Path $report) -and -not $limit) { $done = $true; continue }
            foreach ($kind in 'status', 'stderr', 'stdout') {
                $f = Join-Path $Dir "codex-$round-$kind.txt"
                if (Test-Path $f) { Move-Item $f (Join-Path $Dir "codex-$round-attempt$attempt-$kind.txt") -Force }
            }
            if (Test-Path $report) { Move-Item $report (Join-Path $Dir "codex-$round-attempt$attempt-report.md") -Force }
            if (-not $limit) { Write-QueueLog "stop: round=$round failed without a usage-limit message"; exit 1 }
            $kept = Join-Path $Dir "codex-$round-attempt$attempt-stderr.txt"
            $m = Select-String -Path $kept -Pattern 'try again at ([A-Za-z]+) (\d{1,2})(?:st|nd|rd|th)?, (\d{4}) (\d{1,2}):(\d{2}) ?(AM|PM)' |
                Select-Object -Last 1
            $when = (Get-Date).AddMinutes(30)
            if ($m) {
                $g = $m.Matches[0].Groups
                $text = '{0} {1} {2} {3}:{4} {5}' -f $g[1].Value, $g[2].Value, $g[3].Value, $g[4].Value, $g[5].Value, $g[6].Value
                try {
                    $when = [datetime]::ParseExact($text, [string[]]@('MMM d yyyy h:mm tt', 'MMMM d yyyy h:mm tt'),
                        [Globalization.CultureInfo]::InvariantCulture, [Globalization.DateTimeStyles]::None).AddMinutes(3)
                } catch { Write-QueueLog "could not parse '$text'; waiting 30 min" }
            }
            if ($attempt -lt $MaxAttempts) { Wait-Until $when "usage limit on $round" }
        }
        if (-not $done) { Write-QueueLog "stop: $round still failing after $MaxAttempts attempts"; exit 2 }
    }
    Write-QueueLog 'queue end: all rounds have reports'
    exit 0
} finally {
    Remove-Item $lock -ErrorAction SilentlyContinue
}
