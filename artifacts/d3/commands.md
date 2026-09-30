# D3 命令记录(判定与失败处理)

分支 `feature/d3-verdicts`。本机是官方不支持的配置(Windows 10 + 8 GB 显存)。Isaac 由 `start_isaac_ros2.ps1 -PythonServer` 启动(kit.exe 20800,见 artifacts/d2/commands.md):sim_control 与只监听本机、需要令牌的 Python 执行服务都已打开(用户 2026-09-30 决定)。

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 00:5x | `isaac_py.ps1 -CodeFile robosim_eval\kit\contact_monitor.py -Call 'robosim_contacts_install("/World/Nova_Carter_ROS")'` | Git Bash → powershell.exe | D:\RoboSim-Eval | 0 | contact-install-01.json | 服务端 status ok,但没找到刚体。根因(见第 3 行):Git Bash 把参数里的 `/World/...` 改写成了 `C:/Program Files/Git/World/...` |
| 00:5x | `isaac_py.ps1 -CodeFile robosim_eval\kit\diag_stage.py -Call 'robosim_diag_bodies()'`(只读诊断) | 同上 | 同上 | 0 | diag-bodies-01.json | 机器人下有 8 个刚体(底盘、万向轮架、两个万向轮转轴、两个万向轮、两个驱动轮),都不是实例代理 |
| 00:5x | 同第 1 行 → contact-install-02.json,再加 `MSYS_NO_PATHCONV=1` → contact-install-03.json | 同上 | 同上 | 0 | contact-install-02.json、contact-install-03.json | 第 2 次的报错信息暴露了路径被改写;关掉 Git Bash 路径转换后,8 个刚体都挂上 PhysxContactReportAPI,订阅接触事件成功。从 WSL 调用不经过 Git Bash,不受影响 |
| 00:5x | `sim.sh reset`,4 s 后 `isaac_py.ps1 … -Call 'robosim_contacts_fetch(True)'` | wsl.exe + powershell.exe | 同上 | 0 | contact-fetch-after-reset.json | 复位后 14 个"开始接触"事件,全部是机器人部件与两个地面碰撞平面:`/World/warehouse_with_forklifts/GroundPlane/collisionPlane`、`/World/warehouse_with_forklifts/Warehouse_Empty_small_realtime/GroundPlane/CollisionPlane`;持续接触只计数 |
