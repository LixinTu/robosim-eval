# test_codex_queue_lib.ps1 - fixed-input checks for the Codex queue's usage-limit time parser (no Codex call).
#   powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\test_codex_queue_lib.ps1
# Exit 0 when every case matches, 1 otherwise.
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'codex_queue_lib.ps1')
$now = [datetime]'2026-09-30T06:57:00'
$cases = @(
    @{ Text = "ERROR: You've hit your usage limit. ... or try again at 8:38 AM."; Now = $now; Want = [datetime]'2026-09-30T08:41:00' },
    @{ Text = "ERROR: ... try again at 8:38 AM."; Now = [datetime]'2026-09-30T09:00:00'; Want = [datetime]'2026-10-01T08:41:00' },
    @{ Text = "ERROR: ... try again at 12:05 PM."; Now = $now; Want = [datetime]'2026-09-30T12:08:00' },
    @{ Text = "ERROR: ... try again at Sep 30th, 2026 8:38 AM."; Now = $now; Want = [datetime]'2026-09-30T08:41:00' },
    @{ Text = "ERROR: ... try again at October 2nd, 2026 1:07 PM."; Now = $now; Want = [datetime]'2026-10-02T13:10:00' },
    @{ Text = 'ERROR: something else'; Now = $now; Want = $null }
)
$fail = 0
foreach ($c in $cases) {
    $got = ConvertFrom-RetryText -Text $c.Text -Now $c.Now
    $ok = if ($null -eq $c.Want) { $null -eq $got } else { $got -eq $c.Want }
    if (-not $ok) { $fail++ }
    "{0}  {1}  -> got {2} want {3}" -f ($(if ($ok) { 'PASS' } else { 'FAIL' })), $c.Text, $got, $c.Want
}
if ($fail) { "FAILED $fail of $($cases.Count)"; exit 1 }
"all $($cases.Count) cases pass"; exit 0
