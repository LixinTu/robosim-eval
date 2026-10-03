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
