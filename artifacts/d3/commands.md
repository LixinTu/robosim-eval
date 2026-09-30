# D3 命令记录(判定与失败处理)

分支 `feature/d3-verdicts`。本机是官方不支持的配置(Windows 10 + 8 GB 显存)。Isaac 由 `start_isaac_ros2.ps1 -PythonServer` 启动(kit.exe 20800,见 artifacts/d2/commands.md):sim_control 与只监听本机、需要令牌的 Python 执行服务都已打开(用户 2026-09-30 决定)。

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 00:5x | `isaac_py.ps1 -CodeFile robosim_eval\kit\contact_monitor.py -Call 'robosim_contacts_install("/World/Nova_Carter_ROS")'` | Git Bash → powershell.exe | D:\RoboSim-Eval | 0 | contact-install-01.json | 服务端 status ok,但没找到刚体。根因(见第 3 行):Git Bash 把参数里的 `/World/...` 改写成了 `C:/Program Files/Git/World/...` |
| 00:5x | `isaac_py.ps1 -CodeFile robosim_eval\kit\diag_stage.py -Call 'robosim_diag_bodies()'`(只读诊断) | 同上 | 同上 | 0 | diag-bodies-01.json | 机器人下有 8 个刚体(底盘、万向轮架、两个万向轮转轴、两个万向轮、两个驱动轮),都不是实例代理 |
| 00:5x | 同第 1 行 → contact-install-02.json,再加 `MSYS_NO_PATHCONV=1` → contact-install-03.json | 同上 | 同上 | 0 | contact-install-02.json、contact-install-03.json | 第 2 次的报错信息暴露了路径被改写;关掉 Git Bash 路径转换后,8 个刚体都挂上 PhysxContactReportAPI,订阅接触事件成功。从 WSL 调用不经过 Git Bash,不受影响 |
| 00:5x | `sim.sh reset`,4 s 后 `isaac_py.ps1 … -Call 'robosim_contacts_fetch(True)'` | wsl.exe + powershell.exe | 同上 | 0 | contact-fetch-after-reset.json | 复位后 14 个"开始接触"事件,全部是机器人部件与两个地面碰撞平面:`/World/warehouse_with_forklifts/GroundPlane/collisionPlane`、`/World/warehouse_with_forklifts/Warehouse_Empty_small_realtime/GroundPlane/CollisionPlane`;持续接触只计数 |
| 01:0x | `pytest.sh tests/`(判定模块、取消原因、D3 配置先写测试,红灯后实现) | wsl.exe bash -l | /mnt/d/RoboSim-Eval | 0 | 会话输出 | 96 → 98 → 101 passed;"被中断的运行"一条先失败:规则把操作员中断判成 fail,改为 inconclusive |
| 00:58:18 | `test_runner_fake.sh artifacts/d3/fake-01`(接入判定模块后) | wsl.exe bash -l | 同上 | 0 | fake-01/summary.txt | 8/8;按 D3 规则,要到达的情形里 Nav2 中止或拒绝判 fail(退出 10) |
| 01:0x | WSL → `robosim_eval.contacts`(interop → isaac_py.ps1 → python_server)`install()`、`fetch()` | wsl.exe bash -l | 同上 | 0 | 会话输出 | 8 个刚体,订阅正常 |
| 01:06:51 | `python3 artifacts/d3/mutation_check.py` | wsl.exe bash -l | 同上 | 0 | mutation-check.txt | 8 种改坏全部被抓到,包括计划要求的 4 种坏数据(虚假成功、缺接触数据、时间倒退、取消无回执) |
| 01:01–01:21 | scratchpad `d3_runs.sh`:`run_scenario.sh` 依次 normal、unreachable、cancel、dropout、timeout、collision、bypass | wsl.exe bash -l(后台) | 同上 | 0(脚本) | runs/summary.txt 与各运行目录 | 见下表。cancel、timeout 两次停车确认超时(运行器缺陷,见下两行) |
| 01:22:18 | `run_scenario.sh cancel`(加停稳诊断后重跑) | wsl.exe bash -l | 同上 | 31 | runs/cancel-20260930-012218/events.jsonl 的 timeout 事件 | 诊断:跟踪器吃进了时间戳 46.48 s 的样本,而时钟只有 15.8 s。根因:odom 缓存里还留着复位之前那条时间线的样本,之后的新样本全被跳过 |
| 01:24–01:29 | 修复(append_sample,时间戳倒退即丢弃旧时间线)后重跑 cancel、timeout | 同上 | 同上 | 0、0 | runs/cancel-20260930-012426/、runs/timeout-20260930-012837/ | cancel:CANCELED 后 1.02 s 确认停稳,pass;timeout:仿真时限 6 s 触发取消,pass |
| 01:25:48 | `run_scenario.sh normal --no-contacts`(对照) | 同上 | 同上 | 11 | runs-diagnosis/normal-20260930-012548/ | 0 次恢复,14.2 s 到达;没有接触数据,safety unknown,所以 inconclusive(符合规则) |
| 01:27 | scratchpad `scan_min.sh`:从 rosbag 统计发目标后每 2 s 的 /scan 最近距离 | 同上 | /mnt/d/RoboSim-Eval/artifacts | 0 | 会话输出 | 卡住的那次与正常的那次,开头的 /scan 最近距离都是 1.39 m @ 66°,近处没有障碍物;"开头卡住"的机制未查明 |

## D3 各情形结果(真实 Isaac)

| 运行 | 执行 | 任务结果 | 安全 | 数据 | 评测 | Nav2 终态 / 恢复次数 | 到达误差(真值,m) | 理由 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| runs/normal-20260930-010104 | completed | reached | pass | complete | **pass** | SUCCEEDED / 5 | 0.285 | 开头卡住约 38 s 仿真时间(控制器 4 次"Failed to make progress"),之后正常到达 |
| runs/unreachable-20260930-010458 | completed | unreachable | pass | complete | **pass** | ABORTED 208 / 15 | 3.975 | 预设不可达 + 离线证据 + Nav2 中止 + 真值没到 |
| runs/cancel-20260930-010644 | error | canceled | pass | complete | fail | CANCELED / 0 | 6.018 | 运行器缺陷:stop_timeout(已修复) |
| runs/dropout-20260930-010804 | completed | reached | pass | incomplete | **inconclusive** | SUCCEEDED / 5 | 0.283 | 暂停 6 s:/clock、odom、TF 断流 6.1 s,正确地不判通过 |
| runs/timeout-20260930-011202 | error | timeout | pass | complete | fail | CANCELED / 0 | 6.019 | 运行器缺陷:stop_timeout(已修复) |
| runs/collision-20260930-011323 | completed | timeout | **fail** | complete | **fail** | CANCELED / 10 | 3.535 | 两个驱动轮与 0.10 m 矮箱子接触 4 次;机器人被挡住,300 s 现实上限触发取消 |
| runs/bypass-20260930-012001 | completed | reached | pass | complete | **pass** | SUCCEEDED / 0 | 0.256 | 绕过 1 m 箱子到达 |
| runs/cancel-20260930-012218 | error | canceled | pass | complete | fail | CANCELED / 0 | 6.011 | 加诊断后复现缺陷 |
| runs/cancel-20260930-012426 | completed | canceled | pass | complete | **pass** | CANCELED / 0 | 6.015 | 修复后 |
| runs/timeout-20260930-012837 | completed | timeout | pass | complete | **pass** | CANCELED / 0 | 6.016 | 修复后 |
| runs-diagnosis/normal-20260930-012548 | completed | reached | unknown | complete | inconclusive | SUCCEEDED / 0 | 0.258 | 对照:关闭接触监视 |

## 未查明

- "开头卡住":开着接触监视的 3 次正常路线里有 2 次(normal、dropout)在发目标后约 38 s 仿真时间不动,控制器报"Failed to make progress"并做恢复;绕行那次没有;4 次不开接触监视的运行都没有。/scan 在卡住时与正常时相同。样本太少,不能断定与接触监视有因果关系;D4 批量提供更多样本。
