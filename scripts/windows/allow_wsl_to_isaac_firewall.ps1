# allow_wsl_to_isaac_firewall.ps1 — RoboSim Eval D0c: one scoped Windows Firewall rule so WSL2 can reach Isaac Sim's
# ROS 2 / Fast DDS sockets. Requires an ELEVATED (Administrator) PowerShell:
#   powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\allow_wsl_to_isaac_firewall.ps1
# To remove later:
#   Remove-NetFirewallRule -DisplayName 'RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)'
#
# Evidence (2026-09-29, artifacts/d0c/diag-01): Isaac's DDS discovery multicast reaches WSL, but WSL's replies never
# reach kit.exe (no rule, inbound default Block, NotifyOnListen off so no prompt appeared). Scope of the rule:
# inbound only, UDP only, program kit.exe only, interface 'vEthernet (WSL)' only. Nothing global is changed.
$ErrorActionPreference = 'Stop'
$ruleName  = 'RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)'
$program   = 'D:\isaac-sim-standalone-6.1.0-windows-x86_64\kit\kit.exe'
$interface = 'vEthernet (WSL)'

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { throw 'This script must run in an elevated (Administrator) PowerShell.' }
if (-not (Test-Path $program)) { throw "kit.exe not found: $program" }
if (-not (Get-NetAdapter | Where-Object { $_.Name -eq $interface })) { throw "network adapter '$interface' not found (run Get-NetAdapter to see the actual WSL adapter name)" }

$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Output "rule already exists: $ruleName (Enabled=$($existing.Enabled), Action=$($existing.Action))"
} else {
    New-NetFirewallRule -DisplayName $ruleName `
        -Description 'RoboSim Eval D0c (2026-09-29): allow ROS 2 / Fast DDS discovery and data from WSL2 to Isaac Sim. Inbound, UDP, kit.exe, vEthernet (WSL) only.' `
        -Direction Inbound -Action Allow -Protocol UDP -Program $program -InterfaceAlias $interface -Profile Any -Enabled True | Out-Null
    Write-Output "rule created: $ruleName"
}

Write-Output '--- rule as stored ---'
$r = Get-NetFirewallRule -DisplayName $ruleName
$r | Select-Object DisplayName, Enabled, Direction, Action, Profile | Format-List | Out-String | Write-Output
$r | Get-NetFirewallApplicationFilter | Select-Object Program | Format-List | Out-String | Write-Output
$r | Get-NetFirewallInterfaceFilter | Select-Object InterfaceAlias | Format-List | Out-String | Write-Output
$r | Get-NetFirewallPortFilter | Select-Object Protocol, LocalPort, RemotePort | Format-List | Out-String | Write-Output
Write-Output "done $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
