# codex_queue_lib.ps1 - helpers for run_codex_review_queue.ps1 (dot-sourced; defines functions only).

# The retry time in a Codex usage-limit message, plus 3 minutes; $null when the text has none.
# Codex writes either "try again at Sep 30th, 2026 8:38 AM" or, when the reset is the same day, only
# "try again at 8:38 AM" (2026-09-30 queue run: the date-only pattern missed it and four attempts were wasted).
# A time-only value that is already past on $Now means the next day.
function ConvertFrom-RetryText([string]$Text, [datetime]$Now) {
    $inv = [Globalization.CultureInfo]::InvariantCulture
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
    if ($when -le $Now) { $when = $when.AddDays(1) }
    return $when.AddMinutes(3)
}
