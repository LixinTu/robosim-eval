# 本机环境证据(D0a)

探测日期:2026-09-29 19:02–19:04(America/Los_Angeles)。全部为只读探测,未安装、未修改任何东西。原始输出:`artifacts/d0a/windows-probe.txt`、`artifacts/d0a/wsl-probe-login.txt`、`artifacts/d0a/wsl-probe-clean.txt`;命令与退出码见 `artifacts/d0a/commands.md`。

**结论:本机是 Isaac Sim 6.1 官方不支持的配置(Windows 10、8 GB 显存、驱动低于测试版本)。用户已决定在此配置上做完项目再升级;所有后续记录标注 unsupported configuration。**

## Windows 侧

| 项目 | 实测 | 对 D0 的影响 |
| --- | --- | --- |
| 操作系统 | Microsoft Windows 10 专业版 10.0.19045(build 19045.6466),64 位 | 6.1 要求页明确不支持 Windows 10;WSL mirrored networking 不可用,保持默认 NAT |
| 内存 | 总计 63.7 GB,空闲 31.2 GB(Isaac 空场景运行中) | 充足 |
| GPU | NVIDIA GeForce RTX 4070 Laptop GPU,驱动 591.44,CUDA 13.1,显存 8188 MiB,当前已用 1313 MiB(空场景 GUI),利用率 22% | 低于官方最低 16 GB;驱动低于官方测试版 595.97;阶段 3 实测场景显存 |
| 磁盘 | C: 空闲 1421 GB;D: 空闲 1524 GB | 充足 |
| PowerShell | 5.1.19041.6456;执行策略 CurrentUser=RemoteSigned(本地 .ps1 可直接运行) | 启动脚本无需 Bypass,但给用户的命令仍写 `-ExecutionPolicy Bypass` 以防其他作用域 |
| 提权 | 当前 Claude 的 shell 未提权(IsInRole Administrator = False),账户为 administrator | 防火墙规则等管理员操作需用户在管理员窗口执行 |
| WSL | 2.6.3.0,内核 6.6.87.2-1,WSLg 1.0.71;发行版 `Ubuntu`(Running,v2)、`docker-desktop`(Running,v2);无 `.wslconfig`(默认 NAT) | `wsl -d Ubuntu -- bash -c` 从 PowerShell 可用,WSL 用户为 administrator |
| 网络 | WLAN 192.168.1.115/24(Public);vEthernet (WSL) 172.28.208.1/20(无连接配置文件条目);防火墙三个配置文件均启用,入站默认 NotConfigured;没有任何 kit/isaac 相关防火墙规则 | 首次让 kit.exe 监听时可能弹出防火墙对话框;若被忽略会静默阻断,阶段 3 需提醒用户"允许" |
| Isaac Sim | `D:\isaac-sim-standalone-6.1.0-windows-x86_64`,VERSION `6.1.0-rc.26+release.49347.2d230af4.gl`;isaac-sim.bat、python.bat、post_install.bat、setup_ros_env.bat 均存在;`exts\isaacsim.ros2.core\jazzy\lib` 与 `humble\lib` 存在;`exts\isaacsim.ros2.bridge` 存在 | 复用,不重装 |
| post_install 链接 | `extension_examples` 已是 SymbolicLink → `exts\isaacsim.examples.interactive\isaacsim\examples\interactive` | 旧的 "Symlink extension_examples not created" 报错已不成立,无需修复 |
| 运行中的 Isaac | `kit` PID 29036(16:22 启动,工作集 801 MB)、`omni.telemetry.transmitter` PID 19988 | 未带 ROS 环境变量启动;阶段 3 需用户正常关闭后重启 |
| kit 日志 | `C:\Users\Administrator\.nvidia-omniverse\logs\Kit\Isaac-Sim Full\6.1\kit_20260929_162201.log`(5.2 MB);ROS 2 扩展(isaacsim.ros2.bridge 5.1.4、isaacsim.ros2.core 1.11.0 等)仅 "registered",未见启用;4 条 Error 均为无法在 `C:\Users\Administrator\Documents\...` 下创建目录 | 阶段 3 用同目录最新日志核对 bridge 加载;Documents 目录问题暂不影响 D0 |
| setup_ros_env.bat | 默认 ROS_DISTRO=jazzy、默认 RMW_IMPLEMENTATION=**rmw_zenoh_cpp**;仅当 ROS_DISTRO 未设时把 `exts\isaacsim.ros2.core\jazzy\lib` 前置到 PATH 并设 AMENT_PREFIX_PATH;仅当 RMW_IMPLEMENTATION 未设时才设为 zenoh | 启动前显式设 RMW_IMPLEMENTATION=rmw_fastrtps_cpp 会被尊重;isaac-sim.bat 是否自动调用此文件见阶段 3 记录 |
| ROS/DDS 残留 | 进程、用户、系统环境变量均无 ROS_* / RMW_* / FASTRTPS_* / CYCLONE* / DDS;`%USERPROFILE%\.ros\fastdds.xml`、`C:\.ros\fastdds.xml`、`D:\robosim-assets\network\fastdds.xml` 均不存在 | 无冲突配置 |
| Codex CLI | codex-cli 0.157.0(`C:\Users\Administrator\AppData\Roaming\npm\codex.ps1`),`codex login status` → "Logged in using ChatGPT";`codex exec` 支持 `--sandbox read-only`、`-C <dir>`、`exec review` 子命令 | 阶段 5 审查用 `codex exec --sandbox read-only -C D:\RoboSim-Eval ...` |

## WSL(Ubuntu)侧

| 项目 | 实测 | 对 D0 的影响 |
| --- | --- | --- |
| 发行版 | Ubuntu 24.04.4 LTS(noble),内核 6.6.87.2-microsoft-standard-WSL2 | 与 ROS 2 Jazzy 匹配 |
| 用户 | uid 1000 administrator,组含 sudo、docker;HOME=/home/administrator | — |
| sudo | `sudo -n true` → "sudo: a password is required"(退出码 1) | 安装必须由用户在 Ubuntu 终端执行;Claude 只准备命令块 |
| Python / Git | Python 3.12.3;git 2.43.0 | 满足 |
| ROS 2 | 无 `/opt/ros`;`ros-jazzy-*` 已装包 0 个;无 ROS apt 源(仅 ubuntu.sources);无 colcon、无 rosdep、无 rviz2 | 阶段 2 需完整安装 Jazzy 及导航相关包 |
| WSLg | DISPLAY=:0,WAYLAND_DISPLAY=wayland-0,XDG_RUNTIME_DIR=/run/user/1000/,在非交互 `bash -lc` 与 `bash --noprofile --norc` 下均已设置;/mnt/wslg 存在 | RViz 有显示通道;能否真正渲染在阶段 2 用 `timeout 20 rviz2` 实测 |
| 网络 | eth0 172.28.211.14/20,MTU 1428,默认网关 172.28.208.1(= Windows 的 vEthernet (WSL));github.com 与 packages.ros.org 可解析 | NAT 模式;WSL IP 每次重启可能变化,阶段 3 的 peers 配置不能写死 |
| 内存 / 磁盘 | 31 GiB(WSL 默认上限)+ 8 GiB swap;`/` 空闲 948 GB;`/mnt/d` 空闲 1.5 TB | 工作区放 `~/robotics/vendor`(ext4) |
| 已有工作区 | `~/robotics` 不存在;`~` 与 `/mnt/d`(深度 2)内无 IsaacSim-ros_workspaces / jazzy_ws | 阶段 2 需克隆 |
| ROS 残留 | env、~/.bashrc、~/.profile、/etc/environment、/etc/profile.d 均无 ROS/RMW/FASTRTPS 行;`~/.ros/*.xml` 不存在 | 无冲突配置 |
| 登录 vs 干净 shell | 两次探测除内存数字外逐行一致 | 非交互 `bash -lc` 的结论可信 |

## ROS 2 与第三方工作区(D0b 之后,2026-09-29 19:30)

| 项目 | 实测 |
| --- | --- |
| ROS 2 | Jazzy,`ros-jazzy-desktop 0.11.0`、`ros-jazzy-navigation2 1.3.13`、`ros-jazzy-nav2-bringup 1.3.13`、`ros-jazzy-pointcloud-to-laserscan 2.0.2`、`ros-jazzy-rmw-fastrtps-cpp 8.4.4`、`ros-dev-tools 1.0.3`;rosdep 已初始化并更新 |
| 环境脚本 | `scripts/wsl/ros_env.sh`(`--base-only` 与 overlay 模式均实跑退出 0)、`scripts/wsl/dds_env.sh`(退出 0);RMW_IMPLEMENTATION=rmw_fastrtps_cpp,ROS_DOMAIN_ID=0 |
| WSL 内通信 | talker/listener 默认配置与加载 `configs/network/fastdds.xml` 均收到消息(仅证明 WSL 内部) |
| RViz | rviz2 在 WSLg 下默认 GL 存活 20 s,OpenGL 4.5 |
| 第三方工作区 | `~/robotics/vendor/isaac-ros-6.1`(WSL ext4),tag IsaacSim-6.1.0,HEAD `a9e8471ee901bc2332c1e4aca94ac580713ca3ab`,树干净;构建闭包 carter_navigation + isaacsim_bringup + isaac_ros_navigation_goal;overlay `jazzy_ws/install/setup.bash` |
| carter_navigation 关键配置(钉住版本) | launch 参数 map / params_file / use_sim_time(默认 True);地图 `carter_warehouse_navigation.yaml`(分辨率 0.05,原点 [-11.975, -17.975, 0]);amcl `set_initial_pose: true`,initial_pose x=-6.0 y=-1.0 yaw=3.14159;bt_navigator odom_topic `/chassis/odom`;局部代价地图用 `/front_2d_lidar/scan` 与 `/back_2d_lidar/scan`,全局代价地图与碰撞监视用 `/scan`(由 pointcloud_to_laserscan 从 `/front_3d_lidar/lidar_points` 转换,target_frame front_3d_lidar);collision_monitor 输出 `cmd_vel`(输入 `cmd_vel_smoothed`);params 未设置 enable_stamped_cmd_vel(Jazzy 默认为 geometry_msgs/Twist,须在 D0c 用 `ros2 topic info -v` 与 Isaac 订阅方核对) |

## 运行时实测(D0c/D0d,2026-09-29 19:35–20:30)

| 项目 | 实测 |
| --- | --- |
| Isaac + Nova Carter 示例场景 | 显存只有几次点采样,未连续测量:空场景 3124–3128 MiB,Play 后 5 s 3754 MiB / 8188(均为会话输出,未存文件),Nav2 运行时 Isaac 界面显示 3.9 GiB(截图 artifacts/d0d/run-01/rviz-before-goal-2018.png);GPU 利用率 80%;视口 20 FPS;kit 工作集 14.7 GB;仿真实时因子空场景约 0.4、导航时约 0.32 |
| Windows↔WSL 通信 | Fast DDS,domain 0,UDPv4-only profile;需要防火墙规则 "RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)"(入站/UDP/kit.exe/vEthernet (WSL));Isaac 的 SPDP 多播本来就能到 WSL,缺的是 WSL→Windows 入站 |
| Isaac 发布的 topic | (空场景)/clock 25–26 Hz、/chassis/odom 约 25.8 Hz(一个窗口 13.9 Hz,最长间隔 0.695 s;导航时约 19 Hz)、/tf 25–26 Hz、/front_3d_lidar/lidar_points 2.4–2.8 Hz、前双目 image_raw/camera_info、5 路 IMU;订阅 /cmd_vel(geometry_msgs/Twist);无 2D LaserScan、无 /tf_static |
| Nav2(钉住默认参数) | 10 个生命周期节点 active;/scan 3.5 Hz;/map 480×776;amcl 自动初始位姿;RViz 经 WSLg 显示(OpenGL 4.5) |
| 首次导航 | 目标 (-4.0,-1.0) SUCCEEDED,8.47 s 仿真时间,停稳确认;停稳确认时刻的终点误差:AMCL 独立来源(理想里程计 + USD 出生位姿)0.091 m,AMCL 估计 0.231 m;validation=pass(artifacts/d0d/run-01/attempt-01/result.json) |
| 位置来源 | 场景 USD `/World/Nova_Carter_ROS` 出生位姿 translate (-6, -1, 0)、yaw π(= amcl initial_pose);/chassis/odom 由 `isaacsim.core.nodes.IsaacComputeOdometry` 从底盘仿真状态计算,相对 Play 起点(理想里程计);机器人零指令下缓爬约 1 mm/仿真秒,Nav2 启动时 AMCL 初始位姿因此偏 0.324 m(证据:artifacts/d0d/run-01/usd-inspection.txt、attempt-01/result.json) |
| Nav2 停止 | SIGINT 只发给 ros2 launch 时 10–13 s 全部退出(run-04、run-05);组件容器清理阶段 SIGSEGV,rviz2 以 -9 或 -11 退出,launch 退出码 1(上游已知问题,无残留) |
| 版本证据 | Isaac VERSION `6.1.0-rc.26+release.49347.2d230af4.gl` 与 ROS 2 扩展版本见 artifacts/d0a/isaac-version.txt(bridge 5.1.4、core 1.11.0 的启动行另见 artifacts/d0c/bridge-check-01-after-launch.txt);Codex 登录状态见 artifacts/d0a/codex-login-status.txt |

## 门槛 1→2 判定

- 两侧探测均有完整输出、退出码 0;Isaac 两个关键路径存在 → 通过。
- 阶段 2 前置条件缺口:ROS 2 Jazzy 全套未安装,且 sudo 需要密码 → 阶段 2 以"等待用户执行安装块"开始。

## 未确认项(留给后续阶段)

- ~~isaac-sim.bat 是否自动调用 setup_ros_env.bat~~ 已确认:`isaac-sim.bat` 与 `python.bat` 都会自动 `call setup_ros_env.bat`,除非传 `--no-ros-env`。
- ~~Isaac 自带 `python.bat` 能否 `import rclpy`~~ 已测(2026-09-29 19:1x,两次):加 `PYTHONPATH=exts\isaacsim.ros2.core\jazzy\rclpy` 后能定位 rclpy,但 `import numpy`(自带 site 的 numpy 2.5.1)报 "DLL load failed while importing _multiarray_umath",无论 jazzy lib 前置还是追加到 PATH 末尾都一样;退出码 1。结论:无 GUI 的 Windows 侧 rclpy 发现预测试**不可行**,阶段 3 直接走 GUI 重启路线;不再花时间修 python.bat 环境。
- 8 GB 显存能否承载 Nova Carter 示例场景(阶段 3 实测)。
- WSLg 下 rviz2 能否渲染(阶段 2 实测)。
- Windows Defender 对 kit.exe 的首次监听是否弹窗(阶段 3 观察)。
