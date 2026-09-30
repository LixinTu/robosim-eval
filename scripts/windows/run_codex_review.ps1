# run_codex_review.ps1 — RoboSim Eval: run one read-only Codex review round, detached-friendly, with full logs.
#   powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\run_codex_review.ps1 -Round round1
# Inputs:  <Dir>\codex-prompt-<Round>.md (UTF-8 prompt; the short command-line prompt only tells Codex to read it,
#          which avoids Windows PowerShell 5.1 re-encoding Chinese text on the pipe).
# Outputs: <Dir>\codex-<Round>-report.md (last agent message, via -o), -stdout.txt, -stderr.txt,
#          -status.txt (start/end, real exit code, duration, and whether the account usage limit was hit).
# Read-only by construction: `codex exec --sandbox read-only`; no paid options are used.
param(
    [string]$Round = 'round1',
    [string]$Dir = 'D:\RoboSim-Eval\docs\review\2026-09-29-d0'
)
$ErrorActionPreference = 'Stop'
$promptFile = Join-Path $Dir "codex-prompt-$Round.md"
if (-not (Test-Path $promptFile)) { throw "prompt file not found: $promptFile" }
$report = Join-Path $Dir "codex-$Round-report.md"
$status = Join-Path $Dir "codex-$Round-status.txt"
$stdout = Join-Path $Dir "codex-$Round-stdout.txt"
$stderr = Join-Path $Dir "codex-$Round-stderr.txt"
$prompt = "Read the file $promptFile (UTF-8, Chinese) and carry out exactly the review it describes. Do not modify any file. Write the final report in Chinese."

"start $(Get-Date -Format o) round=$Round prompt_file=$promptFile" | Out-File $status -Encoding utf8
$t0 = Get-Date
$p = Start-Process -FilePath 'cmd.exe' -ArgumentList '/c', "codex exec --sandbox read-only -C D:\RoboSim-Eval -o `"$report`" `"$prompt`"" `
    -RedirectStandardOutput $stdout -RedirectStandardError $stderr -NoNewWindow -Wait -PassThru
. (Join-Path $PSScriptRoot 'codex_queue_lib.ps1')
$limit = Test-UsageLimitText -Text ((Get-Content -Raw $stderr -ErrorAction SilentlyContinue) + '')
"end $(Get-Date -Format o) exit=$($p.ExitCode) duration_s=$([int]((Get-Date) - $t0).TotalSeconds) report_written=$(Test-Path $report) usage_limit_hit=$limit" |
    Out-File $status -Append -Encoding utf8
Get-Content $status
exit $p.ExitCode
