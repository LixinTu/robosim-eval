# 本机已验证的启动、运行与关闭顺序(D0,2026-09-29 实测)

所有命令都在 2026-09-29 于本机跑通;每条的原始记录与退出码见 `artifacts/d0a..d0d/commands.md`。本机是 Isaac Sim 6.1 官方不支持的配置(Windows 10 + 8 GB 显存),以下只表示"在本机实测可用",不表示普遍可用。

## 一次性前提(已完成,重装时才需要)

| 项目 | 状态 | 怎么做 |
| --- | --- | --- |
| Isaac Sim 6.1.0 | 已装在 `D:\isaac-sim-standalone-6.1.0-windows-x86_64` | 不重装 |
| Windows 防火墙规则 "RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)" | 已建(入站 / UDP / 仅 kit.exe / 仅 vEthernet (WSL)) | 管理员 PowerShell:`powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\allow_wsl_to_isaac_firewall.ps1`(可重复运行;删除见脚本头) |
| WSL `Ubuntu` 内 ROS 2 Jazzy + Nav2 + 依赖闭包 | 已装 | Ubuntu 终端(需 sudo 密码):`bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh` |
| 钉住工作区 `~/robotics/vendor/isaac-ros-6.1`(IsaacSim-6.1.0 @ a9e8471)+ `colcon build --packages-up-to carter_navigation` | 已建 | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/setup_workspace.sh` |
| 安装自检 | PASS | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_ros_install.sh` |

## 终端约定

| 终端 | 用途 | 环境 |
| --- | --- | --- |
| Windows 普通 PowerShell(非管理员) | 启动 Isaac Sim | 由 `start_isaac_ros2.ps1` 设置:RMW_IMPLEMENTATION=rmw_fastrtps_cpp、ROS_DOMAIN_ID=0、FASTRTPS_DEFAULT_PROFILES_FILE=`D:\RoboSim-Eval\configs\network\fastdds.xml`;**不预设 ROS_DISTRO**(让 isaac-sim.bat 自动调用的 setup_ros_env.bat 加载自带 jazzy 库) |
| WSL Ubuntu(从 PowerShell `wsl -d Ubuntu`,或 Windows 侧直接 `wsl -d Ubuntu -- bash -l <脚本>`) | Nav2、RViz、探测、记录 | 每个终端先 `source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh`(需要 overlay;`--base-only` 只加载 /opt/ros/jazzy)再 `source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh`;各脚本内部已自动 source |
| 管理员 PowerShell | 仅防火墙规则 | — |

注意:从 Git Bash 调 `wsl.exe` 时必须用脚本文件(`bash -l /mnt/d/...`),内联命令会被引号/反斜杠改写;从 PowerShell 内联时 `$?` 等会被 PowerShell 先展开。

## 启动顺序

1. **Isaac Sim(Windows,普通 PowerShell)**
   `powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1`
   脚本检查路径与 XML、拒绝在已有 kit.exe 时再开一份,然后带 `--/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge` 启动;窗口保持打开。
   GUI:Window → Examples → Robotics Examples → 左树点 **NAVIGATION** → 右侧卡片 **Nova Carter** → **Load Sample Scene**(资产来自 NVIDIA 服务器,首次约 10 s–数分钟)→ 按 ▶ Play。**别按 ⏹ Stop**(会停掉所有 ROS 发布;暂停 ⏸ 可以)。
   核对(Windows):`powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\check_isaac_bridge.ps1` → 日志应有 "ROS bridge extension isaacsim.ros2.bridge enabled successfully"。
2. **WSL 侧原始数据核对**
   `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/probe_topics.sh /mnt/d/RoboSim-Eval/artifacts/d0c/<目录>`
   期望:/clock 约 25 Hz 推进、/chassis/odom 约 26 Hz、/tf 约 26 Hz、/front_3d_lidar/lidar_points 约 2.5 Hz、/cmd_vel 有 1 个订阅者(geometry_msgs/Twist)。没有 /clock 数据时先看 Isaac 是否在 Play。
3. **Nav2 + RViz(WSL)**
   `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/start_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`
   约 25 s 后:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_nav2_ready.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`
   期望:10 个生命周期节点 active、/scan 约 3.5 Hz、/map 480×776、amcl 自动初始位姿 (-6.0, -1.0, π)、`/navigate_to_pose [nav2_msgs/action/NavigateToPose]`、TF map→base_link 有值。RViz 窗口(WSLg)显示地图与激光;日志里一条 `indexed_8bit_image.vert` GLSL 错误无害。
4. **一次导航尝试**
   - 选目标:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/map_overview.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>/map-overview.txt X,Y`,以及 `send_goal.sh <attempt_dir> X Y YAW --check-only`(静态地图空闲核对 + ASCII 局部图)。
   - 记录:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/record_d0.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>/<attempt_dir> 330`
   - 发目标(二选一,每次只用一个发送者):
     - 命令行:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/send_goal.sh <attempt_dir> X Y YAW`(拿到原始 result 与 error_code)
     - RViz:顶部工具栏 **Nav2 Goal**,在地图空闲处按下并拖出朝向(只能记录到 status 主题,拿不到 error_code)
   - 停止记录并汇总:`stop_record.sh <attempt_dir>`,然后 `analyze_attempt.sh <attempt_dir> --goal X Y YAW --spawn -6.0 -1.0 3.141592653589793` → `result.json`、`trajectory.csv`。`--spawn` 是场景 USD 里的出生位姿,用于得到不依赖 AMCL 的位置来源;前提是本次 Play 之后没有重置过场景。
   - **每次尝试前先重置**:在 Isaac 按 ⏹ 再按 ▶,机器人回到出生点、里程计从 0 开始;然后尽快启动 Nav2。机器人在零指令下会缓慢前爬(约 1 mm/仿真秒),而 AMCL 的初始位姿固定为出生点,拖得越久初始定位偏差越大。
5. **暂停/恢复核对**(可选):`watch_clock.sh 120 <文件>` 运行时在 Isaac 按 ⏸ 再按 ▶,文件中会出现消息断档且断档前后仿真时间相等。

## 关闭顺序

1. `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`:SIGINT 只发给 `ros2 launch`(由它转发给子进程),最多等 45 s,必要时对本会话升级 SIGTERM、SIGKILL;launch 真实退出码写在 `<run_dir>/nav2.exit`;最后用不走 daemon 的 fresh discovery 核对没有残留 Nav2 节点。脚本退出码只反映是否有残留(0 = 无)。实测约 13 s 结束;launch 退出码为 1,因为 Nav2 组件容器在清理阶段 SIGSEGV、rviz2 被 SIGKILL(上游已知问题,见 docs/plan.md §9)。
2. 若有未停的记录器:`stop_record.sh <attempt_dir>`(按会话号发 SIGINT;各记录器的退出码写在 `<attempt_dir>/<name>.exit`,bag 为 0,`ros2 topic echo` 为 2 = 被 SIGINT 正常停止)。
3. Isaac Sim:用户在 GUI 按 ⏹ 或 File → Exit;不要从 WSL 或脚本杀 kit.exe。

## 本机实测特性(会影响判读)

- 仿真实时因子约 0.4(20 FPS 视口 + 全部传感器),所以"120 s 仿真时间"约等于 300 s 现实时间。
- 6.1 的 Nova Carter 示例只发布 3D 点云,不发布 /front_2d_lidar/scan、/back_2d_lidar/scan;钉住 params 的局部代价地图这两路无数据,全局代价地图与 collision_monitor 用的 /scan 由 pointcloud_to_laserscan 转换得到。
- 机器人在零指令下以约 0.6 mm/s 缓慢前爬(远低于停稳阈值 0.05 m/s)。
- USD 动画时间线每 ~41 s 循环一次,kit 日志出现 "resetting the animation timeline" 与一帧 differential_controller "Invalid deltaTime 0.000000";仿真时钟与物理不受影响(已实测 /clock 单调)。
- 首次 Play 后若手滑按到 ⏹,topic 仍在但没有数据;重新 Play 即可。
- WSL 的 eth0 地址每次 WSL 重启可能变化;防火墙规则按接口而非 IP 限定,不受影响。
