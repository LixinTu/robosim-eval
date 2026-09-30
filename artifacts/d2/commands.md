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
