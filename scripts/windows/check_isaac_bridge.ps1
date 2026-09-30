# check_isaac_bridge.ps1 — RoboSim Eval D0c: read-only check of the running Isaac Sim and its ROS 2 bridge.
#   powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\check_isaac_bridge.ps1 [-LogPath <kit log>]
# Reports: kit.exe process(es), GPU memory (nvidia-smi), free RAM, the newest kit log, whether isaacsim.ros2.bridge /
# isaacsim.ros2.core were started, which RMW / profile file the bridge reports, and the first [Error]/[Fatal] lines.
param([string]$LogPath = '')
$ErrorActionPreference = 'Continue'
Write-Output "=== check_isaac_bridge.ps1 $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ==="

Write-Output '--- kit processes ---'
$procs = Get-Process | Where-Object { $_.ProcessName -match '^kit$' }
if ($procs) { $procs | Select-Object Id, StartTime, @{n='WorkingSetMB';e={[math]::Round($_.WorkingSet64/1MB)}} | Format-Table -AutoSize | Out-String -Width 120 | Write-Output } else { Write-Output 'no kit.exe running' }

Write-Output '--- gpu ---'
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu --format=csv
Write-Output '--- ram ---'
Get-CimInstance Win32_OperatingSystem | Select-Object @{n='FreeMemGB';e={[math]::Round($_.FreePhysicalMemory/1MB,1)}}, @{n='TotalMemGB';e={[math]::Round($_.TotalVisibleMemorySize/1MB,1)}} | Format-Table -AutoSize | Out-String | Write-Output

if (-not $LogPath) {
    $LogPath = Get-ChildItem "$env:USERPROFILE\.nvidia-omniverse\logs\Kit\Isaac-Sim Full\6.1" -Filter 'kit_*.log' -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName
}
Write-Output "--- kit log: $LogPath ---"
if (-not $LogPath -or -not (Test-Path $LogPath)) { Write-Output 'no kit log found'; exit 2 }
$item = Get-Item $LogPath
Write-Output ("lastWrite={0} sizeMB={1}" -f $item.LastWriteTime, [math]::Round($item.Length/1MB,1))
$lines = Get-Content $LogPath

Write-Output '--- ros2 bridge / core startup lines ---'
$bridge = $lines | Select-String -Pattern 'isaacsim\.ros2\.(bridge|core)' | Where-Object { $_.Line -match 'startup|enabled|loading|Loading|error|Error|failed|Failed|rmw|RMW|fastrtps|zenoh|profile' } | Select-Object -First 40
if ($bridge) { $bridge | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line.Trim() } | Write-Output } else { Write-Output 'no bridge/core startup lines found (bridge not enabled?)' }

Write-Output '--- rmw / dds mentions ---'
$rmw = $lines | Select-String -Pattern 'RMW_IMPLEMENTATION|rmw_fastrtps|rmw_zenoh|FASTRTPS_DEFAULT_PROFILES_FILE|fastdds|Fast-?DDS|ROS_DOMAIN_ID' | Select-Object -First 20
if ($rmw) { $rmw | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line.Trim() } | Write-Output } else { Write-Output 'none' }

Write-Output '--- first errors ---'
$errs = $lines | Select-String -Pattern '\[Error\]|\[Fatal\]' | Select-Object -First 15
Write-Output ("error/fatal lines total: {0}" -f ($lines | Select-String -Pattern '\[Error\]|\[Fatal\]').Count)
if ($errs) { $errs | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line.Trim() } | Write-Output }

Write-Output '--- ros2-related warnings (first 15) ---'
$warn = $lines | Select-String -Pattern '\[Warning\].*(ros2|ROS|rmw|dds|DDS)' | Select-Object -First 15
if ($warn) { $warn | ForEach-Object { "{0}: {1}" -f $_.LineNumber, $_.Line.Trim() } | Write-Output } else { Write-Output 'none' }
Write-Output '=== end ==='
