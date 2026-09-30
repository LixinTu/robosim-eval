# probe_env.ps1 — RoboSim Eval D0a: read-only environment probes (Windows side).
# Makes no changes. Prints one section per check with the command, its output and an EXIT marker.
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts\windows\probe_env.ps1 > artifacts\d0a\windows-probe.txt
$ErrorActionPreference = 'Continue'
$env:WSL_UTF8 = '1'   # make wsl.exe print UTF-8 instead of UTF-16 so captured output is readable
$isaac = 'D:\isaac-sim-standalone-6.1.0-windows-x86_64'

function Section([string]$title, [string]$cmd) {
    Write-Output ''
    Write-Output "===== $title ====="
    Write-Output "CMD: $cmd"
    $global:LASTEXITCODE = $null
    try {
        $out = Invoke-Expression $cmd 2>&1 | Out-String -Width 220
        Write-Output $out.TrimEnd()
        if ($null -ne $global:LASTEXITCODE) { Write-Output "EXIT: $global:LASTEXITCODE" } else { Write-Output 'EXIT: 0 (cmdlet)' }
    } catch {
        Write-Output "ERROR: $($_.Exception.Message)"
        Write-Output 'EXIT: 1'
    }
}

Write-Output "PROBE START: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')  host=$env:COMPUTERNAME"
Section 'whoami' 'whoami'
Section 'is elevated' '([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)'
Section 'powershell version' '$PSVersionTable.PSVersion.ToString()'
Section 'execution policy' 'Get-ExecutionPolicy -List | Format-Table -AutoSize'
Section 'os' 'Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber, OSArchitecture, @{n="TotalMemGB";e={[math]::Round($_.TotalVisibleMemorySize/1MB,1)}}, @{n="FreeMemGB";e={[math]::Round($_.FreePhysicalMemory/1MB,1)}} | Format-List'
Section 'nvidia-smi summary' 'nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu --format=csv'
Section 'nvidia-smi full' 'nvidia-smi'
Section 'drives' 'Get-PSDrive -PSProvider FileSystem | Select-Object Name, @{n="FreeGB";e={[math]::Round($_.Free/1GB,1)}}, @{n="UsedGB";e={[math]::Round($_.Used/1GB,1)}} | Format-Table -AutoSize'
Section 'wsl version' 'wsl --version'
Section 'wsl distros' 'wsl --list --verbose'
Section 'wsl invoke check' 'wsl -d Ubuntu -- bash -c "echo wsl-ok; id -un"'
Section 'wslconfig' 'if (Test-Path "$env:USERPROFILE\.wslconfig") { Get-Content "$env:USERPROFILE\.wslconfig" } else { "no .wslconfig" }'
Section 'isaac paths' "@('$isaac\isaac-sim.bat','$isaac\python.bat','$isaac\post_install.bat','$isaac\exts\isaacsim.ros2.core\jazzy\lib','$isaac\exts\isaacsim.ros2.core\humble\lib','$isaac\exts\isaacsim.ros2.bridge') | ForEach-Object { '{0}  {1}' -f (Test-Path `$_), `$_ }"
Section 'isaac top-level' "Get-ChildItem '$isaac' -Force | Select-Object Mode, Name | Format-Table -AutoSize"
Section 'post_install.bat link lines' "Select-String -Path '$isaac\post_install.bat' -Pattern 'mklink|symlink|link|extension_examples|junction' | ForEach-Object { `$_.LineNumber.ToString() + ': ' + `$_.Line }"
Section 'extension_examples item' "Get-Item '$isaac\extension_examples' -Force -ErrorAction SilentlyContinue | Select-Object Name, LinkType, Target, Mode | Format-List"
Section 'isaac processes' 'Get-Process | Where-Object { $_.ProcessName -match "^kit$|^omni|isaac" } | Select-Object ProcessName, Id, StartTime, @{n="WorkingSetMB";e={[math]::Round($_.WorkingSet64/1MB)}}, Path | Format-List'
Section 'kit logs (newest 5)' 'Get-ChildItem "$env:USERPROFILE\.nvidia-omniverse\logs\Kit" -Recurse -Filter *.log -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending | Select-Object -First 5 FullName, LastWriteTime, Length | Format-List'
Section 'firewall profiles' 'Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction, DefaultOutboundAction | Format-Table -AutoSize'
Section 'connection profiles' 'Get-NetConnectionProfile | Select-Object Name, InterfaceAlias, NetworkCategory, IPv4Connectivity | Format-Table -AutoSize'
Section 'ipv4 addresses' 'Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias, IPAddress, PrefixLength | Sort-Object InterfaceAlias | Format-Table -AutoSize'
Section 'firewall rules mentioning kit or isaac' 'Get-NetFirewallApplicationFilter | Where-Object { $_.Program -match "kit|isaac" } | Get-NetFirewallRule | Select-Object DisplayName, Enabled, Direction, Action, Profile | Format-Table -AutoSize'
Section 'process env ROS/DDS' 'Get-ChildItem Env: | Where-Object { $_.Name -match "ROS|RMW|FASTRTPS|CYCLONE|DDS" } | Format-Table -AutoSize'
Section 'user env ROS/DDS' '[Environment]::GetEnvironmentVariables("User").GetEnumerator() | Where-Object { $_.Key -match "ROS|RMW|FASTRTPS|CYCLONE|DDS" } | Format-Table -AutoSize'
Section 'machine env ROS/DDS' '[Environment]::GetEnvironmentVariables("Machine").GetEnumerator() | Where-Object { $_.Key -match "ROS|RMW|FASTRTPS|CYCLONE|DDS" } | Format-Table -AutoSize'
Section 'existing fastdds xml candidates' '@("$env:USERPROFILE\.ros\fastdds.xml","C:\.ros\fastdds.xml","D:\robosim-assets\network\fastdds.xml") | ForEach-Object { "{0}  {1}" -f (Test-Path $_), $_ }'
Section 'codex command' 'Get-Command codex | Select-Object Name, Source | Format-List'
Section 'codex version' 'codex --version'
Section 'codex login status' 'codex login status'
Section 'codex exec help (head)' 'codex exec --help | Select-Object -First 80'
Section 'git' 'git -C D:\RoboSim-Eval log --oneline -3; git -C D:\RoboSim-Eval status --short'
Write-Output ''
Write-Output "PROBE END: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss zzz')"
