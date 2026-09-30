# D2 命令记录(单次运行器)

分支 `feature/d2-runner`。本机是官方不支持的配置(Windows 10 + 8 GB 显存)。固定输入测试、ROS 假节点测试、真实 Isaac 集成分开记录。

## 常驻进程

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-30 00:07:39 | `start_isaac_ros2.ps1`(加 sim_control;由 D1 的一次性脚本 `restart_watch.ps1` 在用户关闭旧 Isaac 后启动) | kit.exe 31020 | 00:08–00:10:用 `ros2 service list` 确认 19 个 sim_control 服务出现,`/get_simulation_state` 返回 stopped | 用户决定打开 Python 执行服务,需要重启:核对进程启动时刻与脚本启动时刻一致后,00:10 调 `/set_simulation_state` 请求 QUITTING(state 3),返回 "Initiating simulator shutdown" | 未记录(由 Isaac 自行退出) | 正常退出(sim_control 请求) |
| 2026-09-30 00:10:51 | `start_isaac_ros2.ps1 -PythonServer`(Claude 用 Start-Process 新开窗口) | 启动器 27636;kit.exe 20800 | sim_control 服务与 `/simulate_steps` 动作出现;Python 执行服务只监听 127.0.0.1:8226,令牌行只在仓库外的控制台副本里 | 运行中 | — | — |

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 00:08–00:10 | scratchpad `sim_wait.sh`:轮询 `ros2 service list -t`,再调 `/get_simulation_state`、`/get_simulator_features`、`ros2 action list -t` | wsl.exe bash -l(非交互,后台) | /mnt/d/RoboSim-Eval | 2 | simctl-01/ | 服务出现,状态 stopped,功能列表返回;退出 2 只因 `ros2 action list` 不支持 `--no-daemon` |
| 00:11–00:12 | 同上(去掉该参数)→ simctl-02 | 同上 | 同上 | 0 | simctl-02/ | 重启带 Python 执行服务之后,服务与动作都在 |
| 00:1x | `pytest.sh tests/test_sim_math.py`(实现之前) | wsl.exe bash -l | /mnt/d/RoboSim-Eval | 2(收集错误) | 会话输出 | TDD 红灯:模块不存在 |
| 00:1x | `pytest.sh tests/` | 同上 | 同上 | 0 | 会话输出 | 47 passed |
| 00:1x | `pytest.sh tests/test_config.py`(sim 段实现之前) | 同上 | 同上 | 1 | 会话输出 | TDD 红灯:2 个新用例失败(没有 sim 属性) |
| 00:1x | `pytest.sh tests/` | 同上 | 同上 | 0 | 会话输出 | 49 passed |
| 00:14:16–00:15:02 | scratchpad `simseq.sh`:`sim.sh state/load/play/pose`、`doctor.sh`、`sim.sh reset/reset-check`、`doctor.sh` | wsl.exe bash -l(非交互) | /mnt/d/RoboSim-Eval | 全部 0 | simctl-03/steps.log 与各步输出 | 不点 GUI 完成:加载 Nova Carter 场景 8.4 s;播放后底盘真值 (-6.0012, -1.0000, yaw 3.14158);doctor healthy;复位 11.6 s(停止再播放);复位核验通过 (-6.0010, -1.0000);复位后 doctor healthy。**D0 的未验证项"⏹→▶ 后机器人回到出生点"由真值位姿验证** |
| 00:2x | `pytest.sh tests/`(状态机、停稳跟踪、运行配置先写测试,红灯后实现) | wsl.exe bash -l | /mnt/d/RoboSim-Eval | 0 | 会话输出 | 76 passed;之后加 doctor 重查策略 77 passed |
| 00:23:44 | `scripts/wsl/test_runner_fake.sh artifacts/d2/fake-01` | wsl.exe bash -l(非交互) | /mnt/d/RoboSim-Eval | 1 | fake-01/summary.txt | 7/8;succeed 用例的附加检查失败:result.json 在进入 DONE 之前写出,状态序列停在 TEARDOWN。改为先进入 DONE 再写结果 |
| 00:26:10 | 同上 → fake-02 | 同上 | 同上 | 0 | fake-02/ | 8/8 PASS |
| 00:28:44 | `run_scenario.sh normal`(真实 Isaac,第 1 次) | wsl.exe bash -l(后台) | 同上 | 30 | runs/normal-20260930-002844/ | 准备阶段失败:复位后 1.3 s 的 doctor 看到点云 0 条,退出 12,运行器按失败收尾(没有启动 Nav2)。见下两行的根因调查 |
| 00:30–00:32 | scratchpad `lidar_first2.sh`、`repro.sh`、`repro2.sh` | wsl.exe bash -l | 同上 | 0 | lidar-after-reset.txt、repro-doctor-after-reset.txt 与 repro-doctor-after-reset/ | 复位后点云发布者约 1.5–2 s 才重建,第一帧时间戳为仿真 0.30 s,之后约 3 Hz(两次一致)。按运行器的时机重复 4 次,1 次出现"1 帧后停 2.7 s"(退出 12)。结论:复位后的短暂过渡;可能与 540 KB 大消息在 UDP 上分片丢失有关,未证实。处理:准备阶段的 doctor 用 5 s 窗口,只对退出 12 有限重查 3 次,每次都记录 |
| 00:34:06 | `test_runner_fake.sh` → fake-03 | 同上 | 同上 | 0 | fake-03/ | 8/8 PASS(改动后回归) |
| 00:36:22 | `run_scenario.sh normal`(第 2 次) | wsl.exe bash -l(后台) | 同上 | 11 | runs/normal-20260930-003622/ | 流程完整:doctor 第 1 次即通过;Nav2 13.62 s 就绪;SUCCEEDED(仿真 22.5 s);真值离目标 0.264 m;停止录制 0、分析 11、停止 Nav2 0。**发现运行器的缺陷**:仿真 22.85 s 就确认停稳(结果后仅 0.35 s),因为跟踪器也吃了结果之前缓存的 odom 样本;录制随后停止,分析判"停稳无法观察" |
| 00:41:13 | `test_runner_fake.sh`(新增断言:停稳确认至少晚于终态 1 s)→ fake-04-red 的 succeed 用例失败,修复后 → fake-04 | 同上 | 同上 | 0 | fake-04-red/、fake-04/ | 修复:跟踪器只吃终态之后的样本;确认后再录 3 s。8/8 PASS |
| 00:43:43 | `run_scenario.sh normal`(第 3 次) | wsl.exe bash -l(后台) | 同上 | 11 | runs/normal-20260930-004343/ | SUCCEEDED(仿真 25.43 s),停稳确认 26.5 s(结果后 1.07 s),task_outcome **reached**,到达误差 0.264 m;真值与"出生位姿 + 理想里程计"来源相差约 0.1 mm。唯一的 inconclusive 理由:AMCL map→odom 最长间隔 2.529 s > 2 s(上一次 2.285 s);交给 D3 按"判定必需 / 仅作参考"区分数据流 |
| 00:45:57 | scratchpad `interrupt_demo.sh`(第一版) | wsl.exe bash -l | 同上 | 20 | runs/normal-20260930-004557/、interrupt-demo-runner.txt | 脚本 bug:用"最新目录"判断 EXECUTING,看到的是上一次运行,SIGINT 实际在准备阶段送达。运行器的处理正确:doctor 结束后检查到中断,直接收尾,execution interrupted |
| 00:46:34 | scratchpad `interrupt_demo2.sh`(从运行器输出取目录) | 同上 | 同上 | 20 | runs/normal-20260930-004634/、interrupt-demo2-runner.txt | **导航中中断**:进入 EXECUTING 6 s 后 SIGINT(仿真 11.17 s)→ 取消 → CANCELED(11.18 s)→ 停稳确认 12.82 s → 停止录制 0、分析 10、停止 Nav2 0 → DONE;execution interrupted,task_outcome canceled |
