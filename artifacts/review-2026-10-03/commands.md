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

## 09:44 那次运行为什么是 inconclusive

- `result.json` 的 `verdict_reasons.inconclusive`:"data incomplete: clock: 48 backward stamps; odom: 49 backward stamps; tf_odom_base: 49 backward stamps"(离线分析另记 tf_map_odom 6 次)。最大间隔只有 0.13 s,数据本身没有缺。
- 运行器自己实时订阅的 /clock 没有倒退(判定理由里没有 "/clock jumped backwards"),倒退只出现在录下的 bag 里:bag 按接收时的墙钟给消息打时间戳,读回时按这个时间排序。
- `events.jsonl` 里每个事件同时记了墙钟和单调时钟,两者之差在运行中跳了四次:−0.750 s(09:44:21→09:44:39)、−0.506 s(09:45:07→09:45:12)、**−3.714 s(09:45:28 目标被接受 → 09:48:51 停车确认,正是导航录制期间)**、−0.515 s(09:49:03→09:49:13)。墙钟每被往回拨一次,之后收到的消息就排到之前的消息中间;按每墙钟秒约 13 条计,3.7 s 约等于 48 条。
- 内核参数有 `hv_utils.timesync_implicit=1`:WSL 的时钟由 Hyper-V 时间同步定期纠正。clock_probe.sh 测得约每 30 s 往回拨 0.5 s,即 WSL 的时钟比 Windows 快约 1.8%。WSL 用的时钟源是 Hyper-V 提供的参考时钟(hyperv_clocksource_tsc_page),Windows 时钟对 NTP 不漂移,所以快的是 Hyper-V 给 VM 的参考时间。
- 2026-09-30 的 31 次真实运行(D2–D5)和 practice-01 那次 backward_stamps 都是 0。今天 07:06–07:32 Windows 睡眠过一次(系统事件:Kernel-Power 42 "The system is entering sleep";系统时间从 14:06:29Z 改为 14:32:20Z),漂移是这之后出现的;重启 WSL(10:00:42 前后)没有消除。
- 结论:环境问题,不是合并后代码的缺陷;评测按规则把乱序的数据判为不完整,行为正确。在时钟恢复之前,每次真实运行都会这样。最可能的处理是重启 Windows(会关掉 Isaac,由用户决定和执行),之后先用 clock_probe.sh 确认不再被往回拨,再重跑 normal。
