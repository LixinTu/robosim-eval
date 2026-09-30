# isaac_py.ps1 - RoboSim Eval D3: run one of the repository's Kit-side Python files inside Isaac Sim through
# isaacsim.code_editor.python_server (enabled only by start_isaac_ros2.ps1 -PythonServer, user decision 2026-09-30).
#   powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\isaac_py.ps1 -CodeFile <file>
#       [-Call "<python expression>"] [-Context robosim] [-TimeoutS 60]
# Only existing files under robosim_eval\kit of the checkout this script is in are accepted
# (D:\RoboSim-Eval\robosim_eval\kit for the main checkout). The file is sent first (it defines functions in the
# named context); -Call then evaluates one expression in the same context and its value is returned.
# The server listens on 127.0.0.1:8226 only; the token is read from the console copy
# %LOCALAPPDATA%\RoboSimEval\isaac-console.log (outside the repository) and is never printed.
# -Port and -ConsoleLog exist for tests (a private listener and token file); their defaults are the values above.
# Output: exactly one JSON status line on stdout, ASCII only (non-ASCII text is \u-escaped, so the console code page
# cannot garble it): the server's response, or {"status": "error", "evalue": ...} from this client.
# Exit: 0 status ok; 1 status error from python_server; 2 bad arguments (no, unreadable or non-allowed -CodeFile);
# 3 server unreachable, or the connection failed or timed out; 4 no token found; 5 reply is not a JSON status object;
# 6 unexpected client error.
# Dot-sourcing the file only defines its functions (tests/test_contacts.py uses that); nothing is sent to Isaac.
param(
    [string]$CodeFile = '',
    [string]$Call = '',
    [string]$Context = 'robosim',
    [int]$TimeoutS = 60,
    [int]$Port = 8226,
    [string]$ConsoleLog = (Join-Path $env:LOCALAPPDATA 'RoboSimEval\isaac-console.log')
)
$ErrorActionPreference = 'Stop'

function Get-AllowedKitRoot {
    # <checkout>\robosim_eval\kit\ for the checkout this script is in
    $repo = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
    return (Join-Path $repo 'robosim_eval\kit') + '\'
}

function ConvertTo-AsciiJson([string]$Json) {
    # \u-escape every non-ASCII character; in JSON text they can only occur inside strings, so the result is valid JSON
    $sb = New-Object System.Text.StringBuilder
    foreach ($ch in $Json.ToCharArray()) {
        if ([int]$ch -gt 127) { [void]$sb.AppendFormat('\u{0:x4}', [int]$ch) } else { [void]$sb.Append($ch) }
    }
    return $sb.ToString()
}

function Get-ErrorText($ErrorRecord) {
    # The innermost exception message (a .NET method call wraps the real error in MethodInvocationException)
    $e = $ErrorRecord.Exception
    while ($null -ne $e.InnerException) { $e = $e.InnerException }
    return $e.Message
}

function New-ClientError([string]$Message) {
    return ConvertTo-AsciiJson (@{ status = 'error'; evalue = $Message } | ConvertTo-Json -Compress)
}

function Resolve-KitFile([string]$Path, [string]$AllowedRoot) {
    # @{ path = <full path of an existing file under $AllowedRoot> } or @{ path = $null; reason = <why not> }.
    # -LiteralPath: [ ] * ? in a name are not wildcards; -PathType Leaf: the kit directory itself is not a file.
    if (-not $Path) { return @{ path = $null; reason = 'no -CodeFile given' } }
    try {
        $full = [System.IO.Path]::GetFullPath($Path)
    } catch {
        return @{ path = $null; reason = "not a valid path: $(Get-ErrorText $_)" }
    }
    if (-not $full.StartsWith($AllowedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        return @{ path = $null; reason = "outside $AllowedRoot" }
    }
    if (-not (Test-Path -LiteralPath $full -PathType Leaf)) { return @{ path = $null; reason = 'no such file' } }
    return @{ path = $full; reason = '' }
}

function Read-ServerToken([string]$LogPath) {
    # The token python_server printed at startup (last one in the console copy), or $null.
    if (Test-Path -LiteralPath $LogPath -PathType Leaf) {
        $m = Select-String -LiteralPath $LogPath -Pattern 'Python server authentication token:\s*(\S+)' | Select-Object -Last 1
        if ($m) { return $m.Matches[0].Groups[1].Value }
    }
    return $null
}

function Invoke-Kit([string]$Code, [string]$Token, [int]$ServerPort, [string]$KitContext, [int]$WaitS,
                    [int]$ReceiveTimeoutMs) {
    # One request to python_server on 127.0.0.1:$ServerPort. Returns @{ reply = <raw reply text> }, or
    # @{ error = <message> } when it cannot connect or the exchange fails (reset, receive timeout): no .NET error
    # escapes to stderr.
    $envelope = @{ auth_token = $Token; code = $Code; context = $KitContext; timeout = $WaitS } | ConvertTo-Json -Compress -Depth 4
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        try {
            $client.Connect('127.0.0.1', $ServerPort)
        } catch {
            return @{ error = "python_server not reachable on 127.0.0.1:${ServerPort}: $(Get-ErrorText $_)" }
        }
        try {
            $client.ReceiveTimeout = $ReceiveTimeoutMs
            $stream = $client.GetStream()
            $bytes = [System.Text.Encoding]::UTF8.GetBytes($envelope)
            $stream.Write($bytes, 0, $bytes.Length)
            $client.Client.Shutdown([System.Net.Sockets.SocketShutdown]::Send)
            $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
            return @{ reply = $reader.ReadToEnd() }
        } catch {
            return @{ error = "python_server call on 127.0.0.1:${ServerPort} failed (receive timeout ${ReceiveTimeoutMs} ms): $(Get-ErrorText $_)" }
        }
    } finally {
        $client.Close()
    }
}

function Get-ReplyStatus([string]$Reply) {
    # 'ok' or 'error' from a python_server reply; $null when the reply is not a JSON object with a status.
    try {
        $obj = $Reply | ConvertFrom-Json
    } catch {
        return $null
    }
    if ($null -eq $obj -or $obj -isnot [System.Management.Automation.PSCustomObject] -or
        -not ($obj.PSObject.Properties.Name -contains 'status')) {
        return $null
    }
    return [string]$obj.status
}

function Invoke-IsaacPy {
    trap {
        Write-Output (New-ClientError "isaac_py.ps1 failed: $(Get-ErrorText $_)")
        exit 6
    }
    $allowedRoot = Get-AllowedKitRoot
    $resolved = Resolve-KitFile $CodeFile $allowedRoot
    if (-not $resolved.path) {
        Write-Output (New-ClientError "only existing files under $allowedRoot are accepted: '$CodeFile' ($($resolved.reason))")
        exit 2
    }
    $token = Read-ServerToken $ConsoleLog
    if (-not $token) {
        Write-Output (New-ClientError "no python_server token in $ConsoleLog (was Isaac started with -PythonServer?)")
        exit 4
    }
    try {
        $source = [System.IO.File]::ReadAllText($resolved.path, [System.Text.Encoding]::UTF8)
    } catch {
        Write-Output (New-ClientError "cannot read $($resolved.path): $(Get-ErrorText $_)")
        exit 2
    }
    $receiveMs = ($TimeoutS + 15) * 1000
    $codes = @($source)
    if ($Call) { $codes += $Call }
    foreach ($code in $codes) {
        $resp = Invoke-Kit $code $token $Port $Context $TimeoutS $receiveMs
        if ($null -ne $resp.error) {
            Write-Output (New-ClientError $resp.error)
            exit 3
        }
        $status = Get-ReplyStatus $resp.reply
        if ($null -eq $status) {
            $head = if ($resp.reply.Length -gt 200) { $resp.reply.Substring(0, 200) } else { $resp.reply }
            Write-Output (New-ClientError "python_server reply is not a JSON status object: '$head'")
            exit 5
        }
        if ($status -ne 'ok') { break }  # the file failed: its reply is the result, -Call is not sent
    }
    Write-Output (ConvertTo-AsciiJson ($resp.reply.Trim()))
    if ($status -eq 'ok') { exit 0 } else { exit 1 }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-IsaacPy }
