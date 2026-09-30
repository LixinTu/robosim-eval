# test_codex_queue_lib.ps1 - fixed-input checks for the Codex queue helpers (no Codex call): the usage-limit time
# parser, the queue lock and the detection of a review round that is still running (finding shell-9).
#   powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\test_codex_queue_lib.ps1
# Exit 0 when every case matches, 1 otherwise.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'codex_queue_lib.ps1')
$fail = 0
$now = [datetime]'2026-09-30T06:57:00'
$cases = @(
    @{ Text = "ERROR: You've hit your usage limit. ... or try again at 8:38 AM."; Now = $now; Want = [datetime]'2026-09-30T08:41:00' },
    @{ Text = "ERROR: ... try again at 8:38 AM."; Now = [datetime]'2026-09-30T09:00:00'; Want = [datetime]'2026-10-01T08:41:00' },
    @{ Text = "ERROR: ... try again at 12:05 PM."; Now = $now; Want = [datetime]'2026-09-30T12:08:00' },
    @{ Text = "ERROR: ... try again at Sep 30th, 2026 8:38 AM."; Now = $now; Want = [datetime]'2026-09-30T08:41:00' },
    @{ Text = "ERROR: ... try again at October 2nd, 2026 1:07 PM."; Now = $now; Want = [datetime]'2026-10-02T13:10:00' },
    @{ Text = 'ERROR: something else'; Now = $now; Want = $null }
)
# The stderr file is Codex's whole transcript: it also holds the text of files it read (including these scripts).
# Only Codex's own "ERROR:" lines at the start of a line count (review finding shell-1).
$transcript = @(
    '    $limit = [bool](Select-String -Path $stderr -Pattern ''hit your usage limit'' -Quiet)',
    '# Codex writes either "try again at Sep 30th, 2026 8:38 AM" or only "try again at 8:38 AM"',
    'exec powershell.exe -Command ...'
) -join [Environment]::NewLine
$limitLine = "ERROR: You've hit your usage limit. Upgrade to Pro ... or try again at 12:06 PM."
$cases += @(
    @{ Text = $transcript + [Environment]::NewLine + $limitLine; Now = $now; Want = [datetime]'2026-09-30T12:09:00' },
    @{ Text = $transcript; Now = $now; Want = $null },
    # parsed a little after the displayed minute: still today, not tomorrow (review finding shell-7)
    @{ Text = $limitLine; Now = [datetime]'2026-09-30T12:06:30'; Want = [datetime]'2026-09-30T12:09:00' }
)
$limitCases = @(
    @{ Text = $transcript; Want = $false },
    @{ Text = $transcript + [Environment]::NewLine + $limitLine; Want = $true }
)
foreach ($c in $limitCases) {
    $got = Test-UsageLimitText -Text $c.Text
    if ($got -ne $c.Want) { $fail++ }
    "{0}  usage limit in text of {1} chars -> got {2} want {3}" -f ($(if ($got -eq $c.Want) { 'PASS' } else { 'FAIL' })), $c.Text.Length, $got, $c.Want
}
foreach ($c in $cases) {
    $got = ConvertFrom-RetryText -Text $c.Text -Now $c.Now
    $ok = if ($null -eq $c.Want) { $null -eq $got } else { $got -eq $c.Want }
    if (-not $ok) { $fail++ }
    "{0}  {1}  -> got {2} want {3}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $c.Text, $got, $c.Want
}
# ---- queue lock and still-running rounds (review finding shell-9) ----
$checks = 0
function Test-Case([string]$Name, $Got, $Want) {
    $script:checks++
    $ok = $Got -eq $Want
    if (-not $ok) { $script:fail++ }
    "{0}  {1} -> got {2} want {3}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $Name, $Got, $Want
}
# Holder decisions with a fixed process table: 4242 is a live queue started at tick 1, 4246 an unrelated program.
$lookup = {
    param([int]$Id)
    if ($Id -eq 4242) { return [pscustomobject]@{ StartTicks = 1; CommandLine = 'powershell -File C:\r\scripts\windows\run_codex_review_queue.ps1 -Items a/b' } }
    if ($Id -eq 4246) { return [pscustomobject]@{ StartTicks = 1; CommandLine = 'C:\Windows\explorer.exe' } }
    return $null
}
Test-Case 'holder: an empty lock file names nobody' (Test-LockHolderAlive -Content '' -GetProcess $lookup) $false
Test-Case 'holder: pid with its recorded start time is alive' (Test-LockHolderAlive -Content 'pid=4242 start=1 script=x' -GetProcess $lookup) $true
Test-Case 'holder: pid reused by a later process (start time differs) is stale' (Test-LockHolderAlive -Content 'pid=4242 start=2 script=x' -GetProcess $lookup) $false
Test-Case 'holder: pid no longer running is stale' (Test-LockHolderAlive -Content 'pid=4250 start=1 script=x' -GetProcess $lookup) $false
Test-Case 'holder: old-style bare pid of a live queue is alive' (Test-LockHolderAlive -Content '4242' -GetProcess $lookup) $true
Test-Case 'holder: old-style bare pid reused by another program is stale' (Test-LockHolderAlive -Content '4246' -GetProcess $lookup) $false

# Real lock files in a temporary folder; the "other queue" is a second Enter-QueueLock from this process.
$myTicks = (Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks
$tmp = Join-Path ([IO.Path]::GetTempPath()) ('codex-lock-test-' + [guid]::NewGuid())
New-Item -ItemType Directory $tmp | Out-Null
try {
    $lockPath = Join-Path $tmp 'codex-queue.lock'
    $a = Enter-QueueLock -Path $lockPath -Script 'test-a'
    Test-Case 'lock: the first queue acquires it' $a.Acquired $true
    Test-Case 'lock: the holder record names pid and start time' ((Read-LockHolder -Path $lockPath) -like "pid=$PID start=$myTicks script=test-a") $true
    $b = Enter-QueueLock -Path $lockPath -Script 'test-b'
    Test-Case 'lock: a second queue is refused while the first holds it' $b.Acquired $false
    Test-Case 'lock: the refusal names the holder' ($b.Reason -like "*pid=$PID*") $true
    Test-Case 'lock: release leaves nothing behind' ((Exit-QueueLock -Lock $a -Path $lockPath) + (Test-Path $lockPath)) 'False'
    "pid=$PID start=12345 script=old" | Out-File $lockPath -Encoding ascii
    $c = Enter-QueueLock -Path $lockPath -Script 'test-c'
    Test-Case 'lock: a stale record (pid reused, start time differs) is taken over' $c.Acquired $true
    Exit-QueueLock -Lock $c -Path $lockPath | Out-Null
    "$PID" | Out-File $lockPath -Encoding ascii
    $d = Enter-QueueLock -Path $lockPath -Script 'test-d'
    Test-Case 'lock: an old-style lock naming a live non-queue process is taken over' $d.Acquired $true
    Exit-QueueLock -Lock $d -Path $lockPath | Out-Null
    "pid=$PID start=$myTicks script=x" | Out-File $lockPath -Encoding ascii
    $e = Enter-QueueLock -Path $lockPath -Script 'test-e'
    Test-Case 'lock: a record naming a live process with its own start time is honoured' $e.Acquired $false
    Test-Case 'lock: ... and that record is left untouched' ((Get-Content $lockPath -Raw).Trim()) "pid=$PID start=$myTicks script=x"
} finally {
    Remove-Item -Recurse -Force $tmp
}

# A review round still running from an earlier (killed) queue: its codex process names the report, its runner the
# round and folder.
$procs = @(
    [pscustomobject]@{ ProcessId = 11; CommandLine = 'cmd.exe /c codex exec --sandbox read-only -C "D:\r" -o "D:\r\docs\review\d0\codex-r1-report.md" "Read the file D:\r\docs\review\d0\codex-prompt-r1.md"' },
    [pscustomobject]@{ ProcessId = 12; CommandLine = '"powershell" -NoProfile -ExecutionPolicy Bypass -File D:\r\scripts\windows\run_codex_review.ps1 -Round r1 -Dir D:\r\docs\review\d0' },
    [pscustomobject]@{ ProcessId = 13; CommandLine = '"powershell" -NoProfile -File D:\r\scripts\windows\run_codex_review.ps1 -Round r10 -Dir D:\r\docs\review\d0' },
    [pscustomobject]@{ ProcessId = 14; CommandLine = '"powershell" -NoProfile -File D:\r\scripts\windows\run_codex_review.ps1 -Round r1 -Dir D:\r\docs\review\d01' },
    [pscustomobject]@{ ProcessId = 15; CommandLine = $null }
)
$hit = @(Find-RoundProcess -Processes $procs -Round 'r1' -Dir 'D:\r\docs\review\d0' -Exclude 0 | ForEach-Object { $_.ProcessId }) -join ','
Test-Case 'running round: codex (report path) and runner (-Round r1 -Dir d0) found; r10 and d01 not' $hit '11,12'
$hit = @(Find-RoundProcess -Processes $procs -Round 'r1' -Dir 'D:\R\DOCS\review\d0' -Exclude 11 | ForEach-Object { $_.ProcessId }) -join ','
Test-Case 'running round: path case ignored, -Exclude honoured' $hit '12'

# The queue script itself, on an item whose prompt file is missing: it stops before any Codex call (exit 1). This
# checks that it takes and releases the lock, and that it refuses to start while another holder has the lock.
$root = Join-Path ([IO.Path]::GetTempPath()) ('codex-queue-test-' + [guid]::NewGuid())
New-Item -ItemType Directory (Join-Path $root 'f') | Out-Null
try {
    $queueScript = Join-Path $PSScriptRoot 'run_codex_review_queue.ps1'
    $queueLock = Join-Path $root 'codex-queue.lock'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $queueScript -ReviewRoot $root -Items 'f/no-such-round' | Out-Null
    Test-Case 'queue: stops at the missing prompt, before any Codex call (exit 1)' $LASTEXITCODE 1
    Test-Case 'queue: its lock is released afterwards' (Test-Path $queueLock) $false
    $h = Enter-QueueLock -Path $queueLock -Script 'test-holder'
    & powershell -NoProfile -ExecutionPolicy Bypass -File $queueScript -ReviewRoot $root -Items 'f/no-such-round' | Out-Null
    Test-Case 'queue: refuses to start while another holder has the lock (exit 3)' $LASTEXITCODE 3
    Exit-QueueLock -Lock $h -Path $queueLock | Out-Null
    Test-Case 'queue: the refusal is logged with the holder' ((Get-Content (Join-Path $root 'codex-queue.log') -Raw) -like '*refuse: another queue holds*script=test-holder*') $true
} finally {
    Remove-Item -Recurse -Force $root
}

$total = $cases.Count + $limitCases.Count + $checks
if ($fail) { "FAILED $fail of $total"; exit 1 }
"all $total cases pass"; exit 0
