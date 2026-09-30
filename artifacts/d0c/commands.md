# D0c 命令记录(Windows↔WSL 桥接 + Nova Carter 场景)

## 常驻进程

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 19:35:41 | `powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1`(用户在新的普通 PowerShell 运行;旧 GUI PID 29036 已由用户正常关闭) | kit 33104 | 19:38 bridge-check-01:kit 日志 `kit_20260929_193541.log` 第 17 行命令行含 `--/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge`,第 22016 行 "ROS bridge extension isaacsim.ros2.bridge enabled successfully";未弹防火墙对话框(用户报告);GPU 已用 1353 MiB(空场景),kit 工作集 7.5 GB,系统空闲内存 25.6 GB;4 条 Error 仍是 Documents 目录不可创建 | （运行中） | — | — |

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 19:38:12 | `powershell -ExecutionPolicy Bypass -File scripts\windows\check_isaac_bridge.ps1` | PowerShell(Claude 工具) | D:\RoboSim-Eval | 0 | bridge-check-01-after-launch.txt | 见上;日志中没有 RMW/DDS 字样,bridge 实际用的 RMW 只能靠 WSL 侧能否发现来验证 |
| 2026-09-29 19:38:1x | `wsl -d Ubuntu -- bash -l scripts/wsl/probe_topics.sh artifacts/d0c/probe-01-before-play` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 1(clock 未推进,预期) | probe-01-before-play.txt、probe-01-before-play/ | Play 之前的对照:只有 WSL 自身的 /rosout、/parameter_events;/clock 不存在;`ros2 topic hz` 退出 124 = 观察满时长 |
| 2026-09-29 19:44:05 / 19:45:38 | 用户:Robotics Examples → ROS2 → Navigation → Nova Carter → Load Sample Scene → Play | Isaac GUI(用户) | — | — | kit 日志 22053–22111 行 | 场景 `https://omniverse-content-production.s3-us-west-2.amazonaws.com/Assets/Isaac/6.1/Isaac/Samples/ROS2/Scenario/carter_warehouse_navigation.usd` 9.91 s 打开;19:45:38 timeline play。用户一度以为卡死,实为资产加载 |
| 2026-09-29 19:46:24 | `wsl -d Ubuntu -- bash -l scripts/wsl/probe_topics.sh artifacts/d0c/probe-02-after-play` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 1 | probe-02-after-play.txt、probe-02-after-play/ | Play 之后 WSL 仍只见自身两个 topic,无 /clock、无节点 |
| 2026-09-29 19:46:4x | `Get-Process kit`(Responding)、`nvidia-smi`、`check_isaac_bridge.ps1`、kit 日志 tail | PowerShell(Claude 工具) | D:\RoboSim-Eval | 0 | bridge-check-02-after-play.txt | kit Responding=True,工作集 14.5 GB,CPU 1250 s;GPU 已用 3128 MiB / 8188(场景可承载);日志每帧刷 `[isaacsim.ros2.nodes] ROS2 TF aggregation contributor '<prim>' did not submit transforms for topic '/tf' on flush cycle`(约 10 条/s);另有 camera_info fy 强制等于 fx、RTX Lidar fullScan 弃用警告;无新 Error |
| 2026-09-29 19:47 | `Get-NetUDPEndpoint -OwningProcess <kit>`、`Get-NetTCPConnection`、`Get-NetFirewallProfile`、`Get-NetAdapter` | PowerShell(Claude 工具,未提权) | D:\RoboSim-Eval | 0(`Get-NetFirewallRule` 枚举被拒:Access is denied) | kit-udp-endpoints-01.txt | kit.exe 绑定 UDP 0.0.0.0:7400(SPDP 多播)、7410–7441(16 个 participant 的 metatraffic/user 单播)、7000–7015,以及 172.28.208.1 与 192.168.1.115 上的 54162–54209 → Isaac 侧 Fast DDS 已初始化并在 domain 0 工作;防火墙三个配置文件 Enabled、入站默认 NotConfigured(=阻止)、NotifyOnListen=False(不会弹窗);vEthernet (WSL) 172.28.208.1/20 Up |
| 2026-09-29 19:49:11 | `wsl -d Ubuntu -- bash -l scripts/wsl/diag_discovery.sh artifacts/d0c/diag-01` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0(37 s) | diag-01.txt、diag-01/diag.txt | **定位证据**:WSL 被动监听 239.255.0.1:7400 12 s 收到 64 个来自 172.28.208.1 的 RTPS 包(Isaac 的 SPDP 广播到达 WSL,Windows→WSL 通);WSL→Windows:ping 172.28.208.1 100% 丢包;daemon 重启等 10 s 与 `--no-daemon --spin-time 8` 均只见自身 topic;WSL 无 ufw。结论:握手在 WSL→Windows 入站方向被 Windows 防火墙阻断(kit.exe 无放行规则),升级链①②③不适用,需第④步 |
