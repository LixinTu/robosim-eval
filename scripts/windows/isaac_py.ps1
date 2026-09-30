# isaac_py.ps1 - RoboSim Eval D3: run one of the repository's Kit-side Python files inside Isaac Sim through
# isaacsim.code_editor.python_server (enabled only by start_isaac_ros2.ps1 -PythonServer, user decision 2026-09-30).
#   powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\isaac_py.ps1 -CodeFile <file>
#       [-Call "<python expression>"] [-Context robosim] [-TimeoutS 60]
# Only files under D:\RoboSim-Eval\robosim_eval\kit are accepted. The file is sent first (it defines functions in the
# named context); -Call then evaluates one expression in the same context and its value is returned.
# The server listens on 127.0.0.1:8226 only; the token is read from the console copy
# %LOCALAPPDATA%\RoboSimEval\isaac-console.log (outside the repository) and is never printed.
# Output: the server's JSON response on stdout. Exit: 0 status ok; 1 status error; 2 bad arguments;
# 3 server unreachable; 4 no token found.
param(
    [Parameter(Mandatory = $true)][string]$CodeFile,
    [string]$Call = '',
    [string]$Context = 'robosim',
    [int]$TimeoutS = 60
)
$ErrorActionPreference = 'Stop'
$allowedRoot = 'D:\RoboSim-Eval\robosim_eval\kit\'
$full = [System.IO.Path]::GetFullPath($CodeFile)
if (-not $full.StartsWith($allowedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path $full)) {
    Write-Output (@{ status = 'error'; evalue = "only existing files under $allowedRoot are accepted: $CodeFile" } | ConvertTo-Json -Compress)
    exit 2
}
$consoleLog = Join-Path $env:LOCALAPPDATA 'RoboSimEval\isaac-console.log'
$token = $null
if (Test-Path $consoleLog) {
    $m = Select-String -Path $consoleLog -Pattern 'Python server authentication token:\s*(\S+)' | Select-Object -Last 1
    if ($m) { $token = $m.Matches[0].Groups[1].Value }
}
if (-not $token) {
    Write-Output (@{ status = 'error'; evalue = "no python_server token in $consoleLog (was Isaac started with -PythonServer?)" } | ConvertTo-Json -Compress)
    exit 4
}

function Invoke-Kit([string]$code) {
    $envelope = @{ auth_token = $token; code = $code; context = $Context; timeout = $TimeoutS } | ConvertTo-Json -Compress -Depth 4
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect('127.0.0.1', 8226)
    } catch {
        return $null
    }
    try {
        $client.ReceiveTimeout = ($TimeoutS + 15) * 1000
        $stream = $client.GetStream()
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($envelope)
        $stream.Write($bytes, 0, $bytes.Length)
        $client.Client.Shutdown([System.Net.Sockets.SocketShutdown]::Send)
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        return $reader.ReadToEnd()
    } finally {
        $client.Close()
    }
}

$source = [System.IO.File]::ReadAllText($full, [System.Text.Encoding]::UTF8)
$resp = Invoke-Kit $source
if ($null -eq $resp) {
    Write-Output (@{ status = 'error'; evalue = 'python_server not reachable on 127.0.0.1:8226' } | ConvertTo-Json -Compress)
    exit 3
}
if ($Call) {
    $first = $resp | ConvertFrom-Json
    if ($first.status -ne 'ok') { Write-Output $resp; exit 1 }
    $resp = Invoke-Kit $Call
    if ($null -eq $resp) {
        Write-Output (@{ status = 'error'; evalue = 'python_server not reachable on 127.0.0.1:8226' } | ConvertTo-Json -Compress)
        exit 3
    }
}
Write-Output $resp
if (($resp | ConvertFrom-Json).status -eq 'ok') { exit 0 } else { exit 1 }
