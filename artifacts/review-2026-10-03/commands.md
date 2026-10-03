# 2026-10-03 命令记录(fix/review-round1 合入清理分支之后的检查)

分支 `chore/harness-cleanup`,合并提交 5241837(代码以 fix/review-round1 为准)。本机是官方不支持的配置(unsupported configuration:Windows 10 + 8 GB 显存)。固定输入测试、假节点测试、真实 Isaac 集成分开记录;时间是本机时间(UTC−7)。

## 常驻进程

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-03 09:42:14 | `start_isaac_ros2.ps1 -PythonServer`(Claude 用 `Start-Process powershell -NoExit … -File …` 新开窗口;启动前 `Get-Process kit` 为空) | 启动器 44844;kit.exe 33268(09:42:15) | 09:42–09:44 轮询 `sim.sh state`,第 4 次(09:44:06)退出 0,`{"state": "stopped"}`;WSL 重启之后 10:20:17 再查,退出 0,`{"state": "playing"}` | 截至本记录仍在运行,由用户从界面关闭 | — | — |

## 命令

| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 09:36:08–09:41:58 | `verify.sh`(完整) | wsl.exe bash -l(非交互,经 PowerShell) | /mnt/d/RoboSim-Eval | 0 | `artifacts/verify/20261003-093557/`(未入库) | pytest 620 passed;doctor 假节点 PASS;运行器假节点 14/14 PASS(含伪终端 Ctrl-C 一例,退出 20) |
| 09:42:14–09:44:06 | PowerShell 循环:每 15 s `wsl -d Ubuntu -- bash -l …/sim.sh state`,最多 10 分钟 | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | 第 4 次退出 0,state stopped(场景未加载,由运行器加载) |
| 09:44:20–09:49:29 | `run_scenario.sh normal --out /mnt/d/RoboSim-Eval/artifacts/review-2026-10-03/runs` | wsl.exe bash -l(经 PowerShell,后台任务) | D:\RoboSim-Eval | 11 | `runs/normal-20261003-094420/` | completed / reached / safety pass / **data incomplete** → validation inconclusive。原因见下 |
| 09:51:34–09:52:40 | PowerShell 循环 4 次:`wsl -d Ubuntu -e date +%s%3N` 对照 Windows UTC 毫秒 | PowerShell → wsl.exe -e | D:\RoboSim-Eval | 0 | — | WSL 比 Windows 快 +0.3 至 +1.4 s;每次调用本身 1.7–4.0 s,只作粗测 |
| 09:53:22–09:54:54 | `bash -l …/clock_probe.sh 90`(当时在 scratchpad,内容与本目录的相同) | wsl.exe bash -l(经 PowerShell) | D:\RoboSim-Eval | 0 | — | 90 s 内墙钟被往回拨 2 次:09:53:56 −0.550 s,09:54:27 −0.569 s |
| 10:00:58–10:01:00 | `wsl -d Ubuntu -- bash -n …/scripts/wsl/verify.sh`;`… verify.sh --help` | PowerShell → wsl.exe | D:\RoboSim-Eval | 0;0 | — | 改 verify.sh 之后的语法检查 |
| 10:01:04–10:01:05 | `wsl -d Ubuntu -- cat /proc/uptime` | PowerShell → wsl.exe | D:\RoboSim-Eval | 0 | — | 22.98 s:WSL 的 VM 在 10:00:42 前后重新启动,比上一行早约 16 s,不是这里的命令拉起的;由谁重启没有记录(此前请用户执行过 `wsl --shutdown`)。10:20:17 `wsl -l -v`:Ubuntu、docker-desktop 都是 Stopped(空闲时自动停),Docker Desktop 没在运行 |
| 10:01:16–10:02:46 | `bash -l …/artifacts/review-2026-10-03/clock_probe.sh 90` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | 重启后的新 VM 照样被往回拨 2 次:10:01:48 −0.465 s,10:02:20 −0.582 s。重启 WSL 不能消除 |
| 10:03:23–10:03:26 | `bash -l …/artifacts/review-2026-10-03/clock_source.sh` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | clocksource 是 `hyperv_clocksource_tsc_page`(可选 hyperv_clocksource_msr、acpi_pm);内核日志 "tsc: Marking TSC unstable due to running on Hyper-V";内核参数含 `hv_utils.timesync_implicit=1`;CPU i9-13900HX,TSC 2419.202 MHz |
| 10:03:49–10:04:12 | `w32tm /stripchart /computer:time.windows.com /samples:12 /dataonly`;接着 `w32tm /query /status /verbose` | PowerShell | D:\RoboSim-Eval | 0;整条命令退出 38 | — | 12 个样本(每 2 s)Windows 比 NTP 慢 0.480–0.494 s,22 s 内不漂移:Windows 时钟是准的。后一条退出 38、没有可用输出,原因没查 |
| 10:17:06–10:17:39 | `bash …/test_run_check_kill.sh <verify.sh> <out>`,分别取 HEAD 和改过的 verify.sh 的 run_check | PowerShell → wsl.exe | D:\RoboSim-Eval | 0;0 | — | 改前:超过时限、忽略 INT 被强杀的一项记 137,备注为空;改后:备注"超过 2 s 时限,INT 之后 10 s 仍未结束被强杀…"。124 一项两版相同 |
| 10:19:18–10:19:45 | `python3 …/hup_probe.py fg`;`python3 …/hup_probe.py bg` | PowerShell → wsl.exe | D:\RoboSim-Eval | 0;0 | — | 伪终端挂断(相当于关窗口):`timeout --foreground`(现在的 run_scenario.sh)下,只处理 SIGINT/SIGTERM 的替身进程被直接结束,日志只有 "started";不加 `--foreground`(v0.1.0)时它活下来并正常结束 |
| 10:20:17–10:20:23 | `wsl -l -v`;`Get-Process kit`;`wsl -d Ubuntu -- bash -l …/sim.sh state` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | kit.exe 33268 仍在;WSL 重启后仍能连上 sim_control,state playing |
| 10:22:35–10:22:53 | `python3 …/verify_ctrlc_probe.py` | PowerShell → wsl.exe | D:\RoboSim-Eval | 0 | — | 按 verify.sh 的方式在 `timeout` 下跑两项检查,第 2 s 在终端按 Ctrl-C:第一项没收到 SIGINT、照常跑完,第二项接着跑,共 12.1 s。即终端 Ctrl-C 停不下 verify.sh |
| 10:34:01–10:34:06 | `bash -l …/artifacts/review-2026-10-03/timesync_param.sh` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | `/sys/module/hv_utils/parameters/timesync_implicit` 为 Y(root 可写);WSL 里在跑 **systemd-timesyncd**,NTP=yes、NTPSynchronized=yes;有 /dev/ptp_hyperv,但没有 chrony 之类用它 |
| 10:34:30–10:34:34 | `bash -l …/artifacts/review-2026-10-03/timesync_log.sh` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | timesyncd 对 ntp.ubuntu.com 做了初次同步,轮询间隔最短 32 s;日志显示 Ubuntu 发行版空闲后自动停掉、下一条命令又重新启动(10:34:05、10:34:32 各一次) |
| 10:35:20–10:37:31 | `bash -l …/artifacts/review-2026-10-03/clock_who_steps.sh 130` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | 130 s 里墙钟被往回拨 4 次(10:35:53 −0.523 s、10:36:25 −0.494 s、10:36:57 −0.486 s、10:37:28 −0.494 s),每次都紧跟 timesyncd 的一次 NTP 校时(包计数 1→2→3→4→5,约 32 s 一次)。往回拨的是 timesyncd,不是 Hyper-V 时间同步 |

## Windows 重启之后(用户 11:21 重启)

重启前在 Isaac 里由用户关闭(kit 33268)。系统启动时间 11:21:24(`Win32_OperatingSystem.LastBootUpTime`)。

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-10-03 11:26:01 | `start_isaac_ros2.ps1 -PythonServer`(Claude 用 `Start-Process powershell -NoExit … -File …` 新开窗口;启动前 `Get-Process kit` 为空) | 启动器 6716;kit.exe 7444(11:26:01) | 11:26:30–11:35:44 轮询 sim.sh state 17 次都退出 3;防火墙规则重新绑定网卡后 11:41:28 退出 0;11:41:38–11:43:33 跑 normal | 截至本记录仍在运行,由用户从界面关闭 | — | — |

| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 11:23:10–11:25:27 | `bash -l …/clock_who_steps.sh 130` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | 重启没有消除漂移,只是方向反了:4 次都是**往前**拨(11:23:47 +0.625 s、11:24:21 +0.668 s、11:24:53 +0.589 s、11:25:26 +0.712 s),每次紧跟 timesyncd 的一次校时,即 VM 时钟现在慢约 2%。往前拨不会让 bag 乱序,只会让一次接收间隔变长 |
| 11:26:01–11:26:24 | `w32tm /stripchart /computer:time.windows.com /samples:12 /dataonly` | PowerShell | D:\RoboSim-Eval | 0 | — | Windows 比 NTP 快 0.586–0.635 s,不漂移 |
| 11:26:30–11:35:44 | PowerShell 循环:每 15 s `sim.sh state`,最多 9 分钟 | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 3(17 次) | — | 每次都是 "/get_simulation_state: service not available within 15.0 s";今早同样的启动 2 分钟就通 |
| 11:36:06–11:37:43 | `check_isaac_bridge.ps1`;读 kit 日志 `kit_20261003_112602.log`;`Get-NetFirewallRule`、`Get-NetAdapter` | PowerShell(未提权) | D:\RoboSim-Eval | 0;0;Get-NetFirewallRule 拒绝访问 | — | Isaac 正常:18:27:03Z "ROS bridge extension isaacsim.ros2.bridge enabled successfully",18:27:05Z sim_control 启动,和今早的日志一致。vEthernet (WSL) 在,ifIndex 23,172.28.208.1/20。防火墙规则未提权读不了 |
| 11:38:18–11:38:39 | `bash -l …/artifacts/review-2026-10-03/ros_graph_probe.sh` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | WSL eth0 172.28.211.14/20,网关 172.28.208.1;看不到 Isaac 的任何节点和服务 |
| 11:38:58–11:39:38 | `bash -l …/scripts/wsl/diag_discovery.sh …/artifacts/review-2026-10-03/diag-after-reboot` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | `diag-after-reboot/diag.txt` | Isaac 的发现广播能到 WSL(12 s 收到 5 个来自 172.28.208.1 的 RTPS 包),ping Windows 100% 丢包,话题只有 WSL 自己的 /parameter_events、/rosout:与 2026-09-29 D0c 没有防火墙规则时的症状相同(artifacts/d0c/commands.md)。判断:那条规则按网卡限定,Windows 重启时 vEthernet (WSL) 被重新创建,规则不再生效 |
| 约 11:40–11:41 | 用户在管理员 PowerShell 执行:规则存在则 `Set-NetFirewallRule -DisplayName 'RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)' -InterfaceAlias 'vEthernet (WSL)'`,否则运行 `allow_wsl_to_isaac_firewall.ps1`;再 `Get-NetFirewallRule … \| Get-NetFirewallInterfaceFilter` | 用户,管理员 PowerShell | — | 未回传 | — | 用户报告"运行了";之后不用重启 Isaac 就通了(下一行) |
| 11:41:28 | `wsl -d Ubuntu -- bash -l …/sim.sh state` | PowerShell → wsl.exe bash -l | D:\RoboSim-Eval | 0 | — | `{"state": "stopped"}` |
| 11:41:38–11:43:33 | `run_scenario.sh normal --out /mnt/d/RoboSim-Eval/artifacts/review-2026-10-03/runs` | wsl.exe bash -l(经 PowerShell,后台任务) | D:\RoboSim-Eval | 0 | `runs/normal-20261003-114140/` | **validation pass**:completed / reached / safety pass / data complete,没有警告。代码 bf7f431(chore/harness-cleanup,已跟踪文件无改动)。停车确认时真值距目标 0.145 m(容差 0.5 m;AMCL 估计 0.237 m,Nav2 反馈 0.248 m);Nav2 SUCCEEDED、error_code 0、0 次恢复,接受到结果 13.7 s 仿真时间;接触已测,只有轮子与地面,丢失 0;倒退时间戳全为 0,最长接收间隔 clock/odom 0.743 s、tf_odom_base 0.774 s、tf_map_odom 0.985 s;运行中两次往前拨(+0.641 s、+1.41 s)。收尾:停录制 0、分析 0、停 Nav2 0(launch 自身退出码 1,即已知的 "Cannot shutdown a ROS adapter") |

## 09:44 那次运行为什么是 inconclusive

- `result.json` 的 `verdict_reasons.inconclusive`:"data incomplete: clock: 48 backward stamps; odom: 49 backward stamps; tf_odom_base: 49 backward stamps"(离线分析另记 tf_map_odom 6 次)。最大间隔只有 0.13 s,数据本身没有缺。
- 运行器自己实时订阅的 /clock 没有倒退(判定理由里没有 "/clock jumped backwards"),倒退只出现在录下的 bag 里:bag 按接收时的墙钟给消息打时间戳,读回时按这个时间排序。
- `events.jsonl` 里每个事件同时记了墙钟和单调时钟,两者之差在运行中跳了四次:−0.750 s(09:44:21→09:44:39)、−0.506 s(09:45:07→09:45:12)、**−3.714 s(09:45:28 目标被接受 → 09:48:51 停车确认,正是导航录制期间)**、−0.515 s(09:49:03→09:49:13)。墙钟每被往回拨一次,之后收到的消息就排到之前的消息中间;按每墙钟秒约 13 条计,3.7 s 约等于 48 条。
- 往回拨的是 WSL 里的 systemd-timesyncd(NTP,ntp.ubuntu.com):10:35–10:37 的 4 次回拨都紧跟它的一次校时(clock_who_steps.sh)。它最短约 32 s 校一次;VM 时钟快约 1.5–1.8%(每次回拨 0.47–0.58 s),超出它能慢慢调的范围(内核频率校正上限 500 ppm,即 0.05%),所以每次直接往回拨。WSL 用的时钟源是 Hyper-V 提供的参考时钟(hyperv_clocksource_tsc_page),Windows 时钟对 NTP 不漂移,所以快的是 Hyper-V 给 VM 的参考时间。内核参数 `hv_utils.timesync_implicit=1` 的 Hyper-V 隐式时间同步在这期间没有观察到回拨。(本节和本目录提交 cd7a490 的说明里原先写的"Hyper-V 时间同步往回拨"是错的,10:37 的实验之后改正。)
- 2026-09-30 的 31 次真实运行(D2–D5)和 practice-01 那次 backward_stamps 都是 0。今天 07:06–07:32 Windows 睡眠过一次(系统事件:Kernel-Power 42 "The system is entering sleep";系统时间从 14:06:29Z 改为 14:32:20Z),漂移是这之后出现的;重启 WSL(10:00:42 前后)没有消除。
- 结论:环境问题,不是合并后代码的缺陷;评测按规则把乱序的数据判为不完整,行为正确。在时钟恢复之前,每次真实运行都会这样。处理办法都由用户决定和执行:最可能有效的是重启 Windows(会关掉 Isaac);不重启的话,可以在 WSL 里停掉 timesyncd(`sudo systemctl disable --now systemd-timesyncd`,用完 `enable --now`),墙钟就不再被往回拨,代价是 WSL 墙钟每小时比 Windows 快约 1 分钟,Hyper-V 隐式时间同步在差得多时会不会往回拨没测过(没试过)。之后先用 clock_probe.sh 确认不再被往回拨,再重跑 normal。
- 重启之后(11:23):漂移还在,方向反了:VM 时钟慢约 2%,timesyncd 每次往**前**拨约 0.6 s。往前拨不让 bag 乱序,只让一次接收间隔变长(这次最长 0.74 s,门槛 2 s),所以合并后的代码在 11:41 的 normal 判 pass。漂移方向每次启动可能不同;只有往回拨(VM 时钟快)会让数据判不完整。2026-09-30 的运行多半处在往前拨的状态,所以都是 0。
