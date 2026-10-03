# test_codex_queue_lib.ps1 - fixed-input checks for the Codex queue's usage-limit time parser (no Codex call).
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
if ($fail) { "FAILED $fail of $($cases.Count + $limitCases.Count)"; exit 1 }
"all $($cases.Count + $limitCases.Count) cases pass"; exit 0
