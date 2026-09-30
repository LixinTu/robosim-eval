# codex_queue_lib.ps1 - helpers for run_codex_review.ps1 and run_codex_review_queue.ps1 (dot-sourced; functions only).

# Codex's own error lines. The stderr file is its whole transcript and also holds the text of every file it read,
# including these scripts, so a plain search for "hit your usage limit" matched a successful review (finding shell-1).
function Get-CodexErrorLines([string]$Text) {
    return @(($Text -split "`r?`n") | Where-Object { $_ -match '^ERROR: ' })
}

function Test-UsageLimitText([string]$Text) {
    return [bool](@(Get-CodexErrorLines $Text | Where-Object { $_ -match 'hit your usage limit' }).Count)
}

# The retry time in a Codex usage-limit message, plus 3 minutes; $null when the text has none.
# Codex writes either "try again at Sep 30th, 2026 8:38 AM" or, when the reset is the same day, only
# "try again at 8:38 AM" (2026-09-30 queue run: the date-only pattern missed it and four attempts were wasted).
# Only Codex's ERROR lines are read. A time-only value more than 10 minutes before $Now means the next day; a value
# just past (parsed a little after the displayed minute) stays today (finding shell-7).
function ConvertFrom-RetryText([string]$Text, [datetime]$Now) {
    $inv = [Globalization.CultureInfo]::InvariantCulture
    $Text = (Get-CodexErrorLines $Text) -join "`n"
    $m = [regex]::Matches($Text, 'try again at ([A-Za-z]+) (\d{1,2})(?:st|nd|rd|th)?, (\d{4}) (\d{1,2}):(\d{2}) ?(AM|PM)')
    if ($m.Count -gt 0) {
        $g = $m[$m.Count - 1].Groups
        $s = '{0} {1} {2} {3}:{4} {5}' -f $g[1].Value, $g[2].Value, $g[3].Value, $g[4].Value, $g[5].Value, $g[6].Value
        $when = [datetime]::MinValue
        foreach ($fmt in 'MMM d yyyy h:mm tt', 'MMMM d yyyy h:mm tt') {
            if ([datetime]::TryParseExact($s, $fmt, $inv, [Globalization.DateTimeStyles]::None, [ref]$when)) {
                return $when.AddMinutes(3)
            }
        }
        return $null
    }
    $m = [regex]::Matches($Text, 'try again at (\d{1,2}):(\d{2}) ?(AM|PM)')
    if ($m.Count -eq 0) { return $null }
    $g = $m[$m.Count - 1].Groups
    $t = [datetime]::ParseExact(('{0}:{1} {2}' -f $g[1].Value, $g[2].Value, $g[3].Value), 'h:mm tt', $inv)
    $when = $Now.Date.Add($t.TimeOfDay)
    if ($when -lt $Now.AddMinutes(-10)) { $when = $when.AddDays(1) }
    return $when.AddMinutes(3)
}

# ---- queue lock (review finding shell-9) ----
# The queue keeps <ReviewRoot>\codex-queue.lock open for its whole run (write access, FileShare.Read): a second queue
# cannot open it for writing, and Windows closes the handle when the queue ends or is killed, so neither a dead owner
# nor a reused PID can block a new queue. The file names the holder, "pid=<PID> start=<process start, UTC ticks>
# script=<path>". A lock file that can be opened still counts as held when it names a live process with exactly that
# start time, or, in the older format (a bare PID, written by queues from before this lock), a live process whose
# command line runs run_codex_review_queue.ps1.

# Start time (UTC ticks) and command line of a running process; $null when there is no such process.
function Get-LockProcessInfo([int]$Id) {
    $p = Get-Process -Id $Id -ErrorAction SilentlyContinue
    if ($null -eq $p) { return $null }
    $ticks = if ($p.StartTime) { $p.StartTime.ToUniversalTime().Ticks } else { $null }
    $cmd = (Get-CimInstance Win32_Process -Filter "ProcessId=$Id").CommandLine
    return [pscustomobject]@{ StartTicks = $ticks; CommandLine = $cmd }
}

# $true when the lock file content names a holder that is still running; -GetProcess maps a PID to Get-LockProcessInfo.
function Test-LockHolderAlive([string]$Content, [scriptblock]$GetProcess = { param([int]$Id) Get-LockProcessInfo $Id }) {
    $Content = $Content.Trim()
    if ($Content -match '^pid=(\d+) start=(\d+)') {
        $info = & $GetProcess ([int]$Matches[1])
        return [bool]($info -and $null -ne $info.StartTicks -and [string]$info.StartTicks -eq $Matches[2])
    }
    if ($Content -match '^\d+$') {
        $info = & $GetProcess ([int]$Content)
        return [bool]($info -and $info.CommandLine -and $info.CommandLine -match 'run_codex_review_queue\.ps1')
    }
    return $false
}

# The holder record in a lock file, read without disturbing the holder's handle; '' when there is none.
function Read-LockHolder([string]$Path) {
    try {
        $fs = [IO.File]::Open($Path, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::ReadWrite)
    } catch [System.IO.FileNotFoundException] {
        return ''
    }
    try { return ((New-Object IO.StreamReader($fs)).ReadToEnd()).Trim() } finally { $fs.Dispose() }
}

# Takes the lock: returns Acquired, Stream (keep it until Exit-QueueLock), Reason (why refused) and Note (a stale
# record that was replaced).
function Enter-QueueLock([string]$Path, [string]$Script) {
    try {
        $fs = [IO.File]::Open($Path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::Read)
    } catch [System.IO.IOException] {
        return [pscustomobject]@{ Acquired = $false; Stream = $null; Note = ''
            Reason = "another queue holds $Path open ($(Read-LockHolder $Path))" }
    }
    $old = (New-Object IO.StreamReader($fs)).ReadToEnd().Trim()
    if (Test-LockHolderAlive -Content $old) {
        $fs.Dispose()
        return [pscustomobject]@{ Acquired = $false; Stream = $null; Note = ''
            Reason = "$Path names a queue that is still running ($old)" }
    }
    $ticks = (Get-Process -Id $PID).StartTime.ToUniversalTime().Ticks
    $bytes = [Text.Encoding]::ASCII.GetBytes("pid=$PID start=$ticks script=$Script`r`n")
    $fs.SetLength(0); $fs.Write($bytes, 0, $bytes.Length); $fs.Flush()
    $note = if ($old) { "replaced a stale lock record ($old): that process is gone or its PID was reused" } else { '' }
    return [pscustomobject]@{ Acquired = $true; Stream = $fs; Reason = ''; Note = $note }
}

# Releases the lock: empties and closes it, then deletes the file. Returns '' or a note when the file could not be
# deleted because another queue had just opened it (it is empty then, so it names no holder).
function Exit-QueueLock($Lock, [string]$Path) {
    $Lock.Stream.SetLength(0); $Lock.Stream.Dispose()
    try { [IO.File]::Delete($Path) } catch [System.IO.IOException] { return "lock file $Path left in place (opened by another process); it is empty" }
    return ''
}

# Processes that still work on review round $Round in folder $Dir: a codex/cmd process whose command line names the
# round's report or prompt file, or a run_codex_review.ps1 started with this -Round and -Dir. $Exclude is skipped.
function Find-RoundProcess($Processes, [string]$Round, [string]$Dir, [int]$Exclude) {
    $report = Join-Path $Dir "codex-$Round-report.md"
    $prompt = Join-Path $Dir "codex-prompt-$Round.md"
    $roundRe = '(?i)-Round\s+[''"]?' + [regex]::Escape($Round) + '[''"]?(\s|$)'
    $dirRe = '(?i)-Dir\s+[''"]?' + [regex]::Escape($Dir.TrimEnd('\')) + '\\?[''"]?(\s|$)'
    foreach ($p in $Processes) {
        $cmd = [string]$p.CommandLine
        if (-not $cmd -or $p.ProcessId -eq $Exclude) { continue }
        $names = $cmd.IndexOf($report, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
            $cmd.IndexOf($prompt, [StringComparison]::OrdinalIgnoreCase) -ge 0
        $runner = $cmd -match '(?i)run_codex_review\.ps1' -and $cmd -match $roundRe -and $cmd -match $dirRe
        if ($names -or $runner) { $p }
    }
}
