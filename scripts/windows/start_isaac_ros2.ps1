# start_isaac_ros2.ps1 — RoboSim Eval: launch Isaac Sim 6.1 with the ROS 2 bridge (Jazzy, Fast DDS) for the WSL2 route.
# Run from a NEW, normal (non-admin) PowerShell window:
#   powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1
#
# Based on the plan doc B4 block with one deviation: ROS_DISTRO is NOT preset here, because isaac-sim.bat calls
# setup_ros_env.bat, which adds the bundled jazzy libraries to PATH and AMENT_PREFIX_PATH only when ROS_DISTRO is
# unset (verified 2026-09-29, see docs/environment.md). RMW_IMPLEMENTATION is preset so that script's default
# (rmw_zenoh_cpp) is not applied. Refuses to start when another Isaac (kit.exe) is already running.
#
# D2 addition: isaacsim.ros2.sim_control is switched on by default (setting ros_sim_control_extension=true, read by
# isaacsim.app.setup after the ROS bridge). It offers the ROS 2 simulation_interfaces services (/get_simulation_state,
# /set_simulation_state, /reset_simulation, /load_world, /spawn_entity, /delete_entity, /get_entity_state, ...) over the
# same Fast DDS path and firewall rule as the topics. Callers must never request state QUITTING (it closes Isaac).
#   -NoSimControl   start exactly as in D0 (bridge only)
#   -PythonServer   also enable isaacsim.code_editor.python_server (user decision 2026-09-30, needed for Kit-side contact
#                   sensing in D3). It executes Python inside Isaac, so it is limited to its default host 127.0.0.1 and
#                   require_auth=true with an empty auth_token: Isaac then generates a random token at startup and prints
#                   it to the console. The token is never passed on the command line (Kit logs its command line).
# Console output is also copied to %LOCALAPPDATA%\RoboSimEval\isaac-console.log (outside the repository), where the
# Windows-side client reads the generated token.
param(
    [switch]$NoSimControl,
    [switch]$PythonServer
)
$ErrorActionPreference = 'Stop'
# The Fast DDS profile comes from the checkout this script is in (D:\RoboSim-Eval for the main checkout).
if (-not $PSScriptRoot) { throw "Run this file with -File: the repository root is derived from its location." }
$robosimIsaac = 'D:\isaac-sim-standalone-6.1.0-windows-x86_64'
$robosimDds = [System.IO.Path]::GetFullPath([System.IO.Path]::Combine($PSScriptRoot, '..\..\configs\network\fastdds.xml'))

if (-not (Test-Path "$robosimIsaac\isaac-sim.bat")) { throw "Isaac launcher not found: $robosimIsaac\isaac-sim.bat" }
if (-not (Test-Path "$robosimIsaac\setup_ros_env.bat")) { throw "setup_ros_env.bat not found in $robosimIsaac" }
if (-not (Test-Path "$robosimIsaac\exts\isaacsim.ros2.core\jazzy\lib\rmw_fastrtps_cpp.dll")) { throw "Bundled jazzy rmw_fastrtps_cpp.dll not found under $robosimIsaac\exts\isaacsim.ros2.core\jazzy\lib" }
if (-not (Test-Path $robosimDds)) { throw "Fast DDS profile not found: $robosimDds" }
try { [xml](Get-Content -Raw $robosimDds) | Out-Null } catch { throw "Fast DDS profile is not well-formed XML: $robosimDds ($($_.Exception.Message))" }

$running = Get-Process -Name kit -ErrorAction SilentlyContinue
if ($running) { throw "An Isaac Sim instance (kit.exe) is already running: PID $($running.Id -join ', '). Close it normally first; two instances must not run at once." }
if ($env:ROS_DISTRO) { Write-Warning "ROS_DISTRO is preset to '$env:ROS_DISTRO' in this shell; setup_ros_env.bat will skip the bundled-library setup." }

$env:RMW_IMPLEMENTATION = 'rmw_fastrtps_cpp'
$env:ROS_DOMAIN_ID = '0'
$env:FASTRTPS_DEFAULT_PROFILES_FILE = $robosimDds
if (Test-Path Env:ROS_LOCALHOST_ONLY) { Remove-Item Env:ROS_LOCALHOST_ONLY }

Write-Output "RMW_IMPLEMENTATION=$env:RMW_IMPLEMENTATION ROS_DOMAIN_ID=$env:ROS_DOMAIN_ID"
Write-Output "FASTRTPS_DEFAULT_PROFILES_FILE=$env:FASTRTPS_DEFAULT_PROFILES_FILE"
Write-Output "Starting Isaac Sim with the ROS 2 bridge at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') (this window stays open while Isaac runs)"
$isaacArgs = @('--/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge')
if (-not $NoSimControl) { $isaacArgs += '--/isaac/startup/ros_sim_control_extension=true' }
if ($PythonServer) {
    $isaacArgs += @('--enable', 'isaacsim.code_editor.python_server', '--/exts/isaacsim.code_editor.python_server/require_auth=true')
}
$consoleDir = Join-Path $env:LOCALAPPDATA 'RoboSimEval'
New-Item -ItemType Directory -Force -Path $consoleDir | Out-Null
$consoleLog = Join-Path $consoleDir 'isaac-console.log'
Write-Output "isaac-sim.bat $($isaacArgs -join ' ')"
Write-Output "console copy: $consoleLog"
# Only stdout is copied (the generated token is printed there). stderr is not redirected: in Windows PowerShell 5.1 a
# 2>&1 on a native command turns stderr lines into error records, which with ErrorActionPreference=Stop would end this
# script and break Isaac's output pipe.
$ErrorActionPreference = 'Continue'
& "$robosimIsaac\isaac-sim.bat" @isaacArgs | Tee-Object -FilePath $consoleLog
$rc = $LASTEXITCODE
Write-Output "isaac-sim.bat exited with code $rc at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
exit $rc
