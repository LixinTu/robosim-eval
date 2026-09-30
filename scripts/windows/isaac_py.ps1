# isaac_py.ps1 - RoboSim Eval D3: run one of the repository's Kit-side Python files inside Isaac Sim through
# isaacsim.code_editor.python_server (enabled only by start_isaac_ros2.ps1 -PythonServer, user decision 2026-09-30).
#   powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\isaac_py.ps1 -CodeFile <file>
#       [-Call "<python expression>"] [-Context robosim] [-TimeoutS 60]
# Only files under D:\RoboSim-Eval\robosim_eval\kit are accepted. The file is sent first (it defines functions in the
# named context); -Call then evaluates one expression in the same context and its value is returned.
# The server listens on 127.0.0.1:8226 only; the token is read from the console copy
# %LOCALAPPDATA%\RoboSimEval\isaac-console.log (outside the repository) and is never printed.
# -Port and -ConsoleLog exist for tests (a private listener and token file); their defaults are the values above.
# Output: the server's JSON response on stdout. Exit: 0 status ok; 1 status error; 2 bad arguments;
# 3 server unreachable; 4 no token found.
# Dot-sourcing the file only defines its functions (tests/test_contacts.py uses that); nothing is sent to Isaac.
param(
    [Parameter(Mandatory = $true)][string]$CodeFile,
    [string]$Call = '',
    [string]$Context = 'robosim',
    [int]$TimeoutS = 60,
    [int]$Port = 8226,
    [string]$ConsoleLog = (Join-Path $env:LOCALAPPDATA 'RoboSimEval\isaac-console.log')
)
$ErrorActionPreference = 'Stop'

function Get-AllowedKitRoot {
    return 'D:\RoboSim-Eval\robosim_eval\kit\'
}

function Resolve-KitFile([string]$Path, [string]$AllowedRoot) {
    # Full path of an existing file under $AllowedRoot, or $null.
    $full = [System.IO.Path]::GetFullPath($Path)
    if (-not $full.StartsWith($AllowedRoot, [System.StringComparison]::OrdinalIgnoreCase) -or -not (Test-Path $full)) {
        return $null
    }
    return $full
}

function Read-ServerToken([string]$LogPath) {
    # The token python_server printed at startup (last one in the console copy), or $null.
    if (Test-Path $LogPath) {
        $m = Select-String -Path $LogPath -Pattern 'Python server authentication token:\s*(\S+)' | Select-Object -Last 1
        if ($m) { return $m.Matches[0].Groups[1].Value }
    }
    return $null
}

function Invoke-Kit([string]$Code, [string]$Token, [int]$ServerPort, [string]$KitContext, [int]$WaitS) {
    # One request to python_server on 127.0.0.1:$ServerPort; the raw reply text, or $null when it cannot connect.
    $envelope = @{ auth_token = $Token; code = $Code; context = $KitContext; timeout = $WaitS } | ConvertTo-Json -Compress -Depth 4
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect('127.0.0.1', $ServerPort)
    } catch {
        return $null
    }
    try {
        $client.ReceiveTimeout = ($WaitS + 15) * 1000
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

function Invoke-IsaacPy {
    $allowedRoot = Get-AllowedKitRoot
    $full = Resolve-KitFile $CodeFile $allowedRoot
    if (-not $full) {
        Write-Output (@{ status = 'error'; evalue = "only existing files under $allowedRoot are accepted: $CodeFile" } | ConvertTo-Json -Compress)
        exit 2
    }
    $token = Read-ServerToken $ConsoleLog
    if (-not $token) {
        Write-Output (@{ status = 'error'; evalue = "no python_server token in $ConsoleLog (was Isaac started with -PythonServer?)" } | ConvertTo-Json -Compress)
        exit 4
    }
    $source = [System.IO.File]::ReadAllText($full, [System.Text.Encoding]::UTF8)
    $resp = Invoke-Kit $source $token $Port $Context $TimeoutS
    if ($null -eq $resp) {
        Write-Output (@{ status = 'error'; evalue = "python_server not reachable on 127.0.0.1:$Port" } | ConvertTo-Json -Compress)
        exit 3
    }
    if ($Call) {
        $first = $resp | ConvertFrom-Json
        if ($first.status -ne 'ok') { Write-Output $resp; exit 1 }
        $resp = Invoke-Kit $Call $token $Port $Context $TimeoutS
        if ($null -eq $resp) {
            Write-Output (@{ status = 'error'; evalue = "python_server not reachable on 127.0.0.1:$Port" } | ConvertTo-Json -Compress)
            exit 3
        }
    }
    Write-Output $resp
    if (($resp | ConvertFrom-Json).status -eq 'ok') { exit 0 } else { exit 1 }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-IsaacPy }
