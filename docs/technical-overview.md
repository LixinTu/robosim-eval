# RoboSim Eval 技术说明(截至 D0,2026-09-29)

本文面向第一次接触这个项目的工程师或面试官,假设读者了解 ROS 2 的基本概念(topic、TF、action、launch)。项目里的专有名词在文末"附录:术语"里解释。

**证据约定**:文中的数字都来自仓库里的记录。原始输出在 `artifacts/`(产品证据)和 `docs/review/`(审查过程),各阶段的命令台账是 `artifacts/d0*/commands.md`。rosbag 本体只存在本机、不入库;由 bag 算出的数字可以对照入库的 `trajectory.csv`、`result.json` 和 `bag-info.txt`。少数结果只在台账里有摘要、没有单独存档,文中会注明。多数小节末尾给出证据位置。

## 0. 摘要

- **做什么**:用现成的机器人(NVIDIA Nova Carter)和现成的导航系统(ROS 2 Nav2)搭一套仿真评测工具:运行导航任务、记录数据、检查异常、给出评测结论,并能按保存的条件复跑。
- **现在到哪一步**:第一个交付 D0 的四个子项(D0a–D0d)已经完成。Windows 上的 Isaac Sim 6.1 与 WSL2 里的 ROS 2 Jazzy + Nav2 已接通,跑通了一次真实的 A→B 导航,证据已留存。按计划文档 B7 和 AGENTS.md 的审查门,D0 还要等 Codex 独立审查和用户三步验收完成才算交付,这两项都还没做完。D1–D5 没有开始。
- **关键结果**:Nav2 返回 SUCCEEDED。按一个不依赖 AMCL 定位的位置来源核对,机器人停稳时距目标 0.091 m,容差 0.5 m。
- **值得看的部分**:
  - 在官方不支持的机器上,查清并打通了 Windows 与 WSL 之间的 DDS 通信;
  - 用 Isaac 的理想里程计加场景文件里的出生位姿,构造出不依赖 AMCL 的到达核对,并用场景文件里的节点连线证明它的来源。这个核对还发现了一个真实问题:AMCL 的初始定位偏了 0.324 m;
  - 启停、记录、评测脚本如实报告退出码,评测规则有 14 个固定输入测试和改坏检查。
- **环境前提**:本机是 Windows 10、8 GB 显存(RTX 4070 Laptop)、NVIDIA 驱动 591.44。Isaac Sim 6.1 官方只支持 Windows 11,显存最低 16 GB,测试驱动为 595.97,三项本机都不满足。本文的结论只代表"在这台机器上实测可用"。

证据:`docs/plan.md` §1、§7;`docs/environment.md`;`docs/harness-sources.md` 的 S1(官方要求页摘录)。

## 1. 目标与当前范围

计划文档(根目录的 `RoboSim-Eval-Plan-and-Setup-ZH(1).md`)把产品目标定义为:使用者选择场景、起点和目标,运行一次导航,查看轨迹、任务状态和评测结果,并能按保存的条件复跑。

第一版(计划文档 A1)包括:
- 一个 Nova Carter、一个简单场景、已有地图、一个 A→B 导航任务;
- 记录激光、位置、速度指令、导航反馈和任务事件;
- 目标的发送、取消、超时、异常退出和停止确认;
- 到达、接触/碰撞和数据完整性检查;
- 三种预设情形:正常通路、可以绕行的障碍、不可达目标(计划文档称为"场景",指测试情形);
- 单次结果 JSON、轨迹文件、事件记录,以及批量 HTML 报告;
- 一次真实缺陷的复现、修复与同条件复跑记录;没有真实缺陷时明确标注为故障注入。

D0 只做其中最底层的一段:证明整条链路真的能跑,并建立"每个结论都有原始证据"的做法。它分四个子项,计划文档给每项定了验收门槛:

| 子项 | 内容 | 验收门槛(计划文档) | 状态 |
| --- | --- | --- | --- |
| D0a | 记录本机现状,不重装 | 环境记录与现有改动清单 | 完成 |
| D0b | 安装 ROS 2 Jazzy 与 Nav2,拉取钉住版本的 NVIDIA 示例工作区 | 包可发现、构建成功、launch 参数可查询,保存命令和退出码 | 完成;只构建了 carter_navigation 及其依赖,共 3 个包 |
| D0c | 加载 Nova Carter 场景,打通 Windows↔WSL 通信 | Play 后 `/clock` 持续推进;里程计、TF、激光有样本和频率 | 完成 |
| D0d | 首次导航 | Nav2 接受并完成一个可达目标,轨迹显示移动,最终到达且停稳;保留原始证据 | 完成,有两处偏差 |

D0d 的两处偏差见 `docs/plan.md` §8。计划要求在 RViz 里手动定位并给目标。实际没有手动定位,AMCL 按参数自动用出生点初始化;目标用命令行 action 客户端发出,为的是拿到原始结果和 error_code。

证据:`docs/plan.md` §1、§7、§8;`artifacts/d0a`–`d0d/commands.md`。

## 2. 系统总览

```
Windows 10 host                                   WSL2 Ubuntu 24.04 (NAT)
+----------------------------------+              +---------------------------------------------+
| Isaac Sim 6.1 (kit.exe)          |  Fast DDS    | ROS 2 Jazzy                                 |
|  Nova Carter sample scene        |  UDPv4 only  |  carter_navigation.launch.xml               |
|  OmniGraph publishes:            | -----------> |   pointcloud_to_laserscan -> /scan          |
|   /clock  /chassis/odom  /tf     |  domain 0    |   Nav2 (12 lifecycle nodes): map_server,    |
|   /front_3d_lidar/lidar_points   | <----------- |     amcl, planner (NavFn), controller (DWB),|
|  subscribes /cmd_vel (Twist)     |  inbound UDP |     bt_navigator, velocity_smoother,        |
|   -> DifferentialController      |  rule for    |     collision_monitor -> /cmd_vel, ...      |
|   -> ArticulationController      |  kit.exe     |   RViz (via WSLg)                           |
+----------------------------------+              |  project scripts: record, send goal,        |
                                                  |   analyze -> artifacts/                     |
                                                  +---------------------------------------------+
```

**Windows 侧**只跑 Isaac Sim。场景是 NVIDIA 的 Nova Carter 导航示例:一个仓库环境加一台 Nova Carter。仿真按 1/60 s 的步长推进。场景里的 OmniGraph 把仿真数据发成 ROS 2 topic:仿真时钟 `/clock`、里程计 `/chassis/odom`、坐标变换 `/tf`、前方 3D 激光点云 `/front_3d_lidar/lidar_points`。它同时订阅 `/cmd_vel`(`geometry_msgs/Twist`),经差速控制器和关节控制器驱动轮子。

**WSL 侧**跑 ROS 2 Jazzy 和 Nav2。NVIDIA 官方工作区里的 `carter_navigation.launch.xml` 一次启动三样东西:
- `pointcloud_to_laserscan`:把 3D 点云逐帧转成 2D 激光 `/scan`;
- Nav2(由 nav2_bringup 启动,共 12 个生命周期节点):地图服务、AMCL 定位、全局规划(NavFn)、路径平滑、局部控制(DWB)、恢复行为、行为树导航、航点跟随、速度平滑、碰撞监视、对接和路线服务;
- RViz,通过 WSLg 显示在 Windows 桌面。

Nav2 的速度指令链是:局部控制器 → 速度平滑(输出 `cmd_vel_smoothed`)→ 碰撞监视 → `/cmd_vel` → Isaac。对接服务器(docking_server)也会直接发布 `/cmd_vel`,但 D0 没有用到对接。Nav2 自己的到达检查按 AMCL 的定位结果判断,位置容差 0.25 m、朝向容差 0.25 rad;局部控制的最大线速度是 0.8 m/s。这些参数都来自 carter_navigation 自带的参数文件,原样未改。

**两侧通信**全部显式配置,不依赖默认值:
- 中间件固定为 Fast DDS(`RMW_IMPLEMENTATION=rmw_fastrtps_cpp`),`ROS_DOMAIN_ID=0`。Isaac 6.1 在 Windows 上的启动脚本默认用 Zenoh,所以必须显式设置。
- 两侧都用环境变量 `FASTRTPS_DEFAULT_PROFILES_FILE` 指向同一份配置 `configs/network/fastdds.xml`。它只用 UDPv4,关闭共享内存等内置传输,因为两侧不在同一个操作系统内核里,共享内存用不上。发现用 Fast DDS 默认的多播,不写死对端 IP。WSL 侧已实测加载这份配置。Isaac 侧的 kit 日志没有 RMW/DDS 记录,是否真的加载了没有直接证据,但通信本身已实测可用。
- WSL2 在 Windows 10 上只能用 NAT 网络(没有 mirrored 模式)。WSL 发给 Isaac 的包经虚拟网卡 vEthernet (WSL) 进入 Windows,对 Windows 防火墙来说是入站流量。kit.exe 没有放行规则,入站默认阻止,而且系统关闭了"监听时通知",所以不会弹窗询问。DDS 的端点发现需要双方互相可达,只通一个方向时,WSL 看不到 Isaac 的 topic。解决办法是一条最小范围的入站规则:只放行 UDP、只对 kit.exe、只在 vEthernet (WSL) 接口上。

**实测数据流**(现实时间频率;"Play 后"指示例场景在运行、Nav2 未启动):

| topic | 频率 | 测量条件 | 说明 |
| --- | --- | --- | --- |
| `/clock` | 25.2–26.6 Hz | Play 后 | 仿真时钟 |
| `/clock` | 21.0–22.3 Hz | Nav2 已启动、机器人静止 | |
| `/chassis/odom` | 约 25.8 Hz;有一个统计窗口降到 13.9 Hz,最长间隔 0.695 s | Play 后 | 每个仿真步一条,即每仿真秒约 60 条 |
| `/chassis/odom` | 约 19 Hz | 导航中(attempt-01 录制) | |
| `/tf` | 25–26 Hz | Play 后 | 含 odom→base_link |
| `/front_3d_lidar/lidar_points` | 2.4–2.8 Hz | Play 后 | PointCloud2,单帧约 540 KB |
| `/scan` | 3.54–3.60 Hz | Nav2 已启动、机器人静止 | 由点云逐帧转换得到 |

现实频率约等于"每仿真秒条数 × 实时因子"。实时因子是仿真时间与现实时间之比,本机没启动 Nav2 时约 0.4,导航时约 0.32。`/scan` 由点云一帧对一帧转换而来,所以点云的真实频率不应低于 `/scan`。点云那一行是在仿真更快时测的,读数却更低,可能是测量方法的问题,没有核实。录制数据里 `/scan` 与 `/clock` 的条数比约为 1:6(145 : 904),折合仿真时间约 10 Hz。

证据:`artifacts/d0c/probe-04-playing/`、`artifacts/d0c/commands.md`、`artifacts/d0d/run-01/ready-check-01.txt`、`artifacts/d0d/run-01/attempt-01/bag-info.txt`、`docs/environment.md`、钉住版本的 `carter_navigation/params/carter_navigation_params.yaml`。

## 3. 哪些来自上游,哪些是本项目写的

| 部分 | 来源 | 本项目怎么用 |
| --- | --- | --- |
| Isaac Sim 6.1、Nova Carter 机器人与示例场景、场景里的 OmniGraph(传感器、里程计、TF、差速控制) | NVIDIA | 直接复用;启动脚本只设置中间件与 DDS 配置 |
| `carter_navigation`(launch、Nav2 参数文件、仓库地图)与 Fast DDS 配置 `fastdds.xml` | NVIDIA IsaacSim-ros_workspaces,标签 IsaacSim-6.1.0(commit a9e8471) | 钉住版本,只构建 carter_navigation、isaac_ros_navigation_goal、isaacsim_bringup 三个包;原文件不改,参数原样使用。`fastdds.xml` 复制到 `configs/network/`,只把许可声明移进注释,让它成为合法的单根 XML |
| ROS 2 Jazzy、Nav2 1.3.13、RViz、pointcloud_to_laserscan、rosbag2 | ROS 2 / Nav2 开源社区(apt 安装) | 直接复用 |
| 环境探测、安装脚本、防火墙规则脚本、Nav2 启停、数据记录、发目标、评测分析、测试、文档与证据整理 | 本项目 | 自写(见 §5) |

机器人的定位、路径规划和速度指令来自 Nav2;把速度指令变成轮子动作的差速控制来自 Isaac 示例场景里的 OmniGraph。本项目没有实现任何导航或控制算法。

**分工与 AI 参与**:根目录的三份参考文档(项目计划书和两份开发流程说明)由用户提供。除此之外,本项目的代码、脚本和文档由 AI 编程工具 Claude Code 编写。用户执行了需要本人权限或 GUI 的操作:WSL 里的 sudo 安装、管理员权限的防火墙规则、关闭旧的 Isaac 并用启动脚本重启,以及所有 Isaac GUI 操作(加载场景、Play、暂停)。用户还在 RViz 里目视核对了激光与地图的贴合,并提供了 RViz 和防火墙的截图。独立审查交给另一个 AI 工具 Codex,以只读方式进行;第 1 轮因账户额度用完而中止,还没有完成。

证据:`configs/network/fastdds.xml` 文件头、`artifacts/d0b/setup-workspace.log`、`docs/environment.md`、`docs/review/2026-09-29-d0-handoff.md`。

## 4. 一次导航尝试怎么跑

先区分两个词。一次**运行**(run)是一次 Nav2 会话,目录是 `artifacts/d0d/run-NN/`;一次**尝试**(attempt)是其中发出的一个目标,目录是 `run-NN/attempt-NN/`。Nav2 的启停与就绪脚本写运行目录,记录、发目标、分析脚本写尝试目录。D0 唯一的导航尝试是 `run-01/attempt-01`,其余运行目录是停止路径测试和回归测试。

目前还没有自动运行器(那是 D2),一次尝试由下面这串脚本手动串起来。坐标都在 map 系,单位是米和弧度。

| 步骤 | 脚本 | 做什么 | 判为成功的条件 |
| --- | --- | --- | --- |
| 1 | `scripts/windows/start_isaac_ros2.ps1` | 设置中间件与 DDS 配置后启动 Isaac;已有 Isaac 在运行时拒绝再开 | `check_isaac_bridge.ps1` 在 kit 日志里看到 ROS 2 bridge 已加载 |
| 2 | (GUI)加载 Nova Carter 示例,按 ⏹ 再按 ▶ | ⏹ 把仿真复位到场景文件里的初始状态,▶ 开始仿真 | `/clock` 推进。机器人是否真的回到出生点还没有专门验证(见下文) |
| 3 | `start_nav2.sh <run_dir>` | 后台启动 carter_navigation,记下进程归属信息(§5.1) | 退出 0 |
| 4 | `check_nav2_ready.sh <run_dir>` | 检查 10 个 Nav2 生命周期节点、`/scan`、`/map`、导航 action 和 `/clock` | `verdict: READY`,退出 0 |
| 5 | `record_d0.sh <attempt_dir> [秒数]` | 启动 rosbag 和 5 路带时间戳的文本流 | 2 s 后 6 个记录器的会话都在运行,退出 0 |
| 6 | `send_goal.sh <attempt_dir> X Y YAW` | 核对目标在地图空闲区,发一个 NavigateToPose,保存完整转录 | Nav2 返回 SUCCEEDED,退出 0 |
| 7 | `stop_record.sh <attempt_dir>` | 停止记录器,复制 bag,检查必需话题有数据 | 退出 0 |
| 8 | `analyze_attempt.sh <attempt_dir> --goal X Y YAW --spawn -6.0 -1.0 3.141592653589793` | 加载 ROS 环境后调用 `analyze_attempt.py`,写 `result.json` 和 `trajectory.csv` | 正常结束;结论 pass 时退出 0,fail 退出 10,inconclusive 退出 11 |
| 9 | `stop_nav2.sh <run_dir>` | 核对归属后停止 Nav2,检查没有残留 | 退出 0 |

第 4 步检查的 10 个节点是 map_server、amcl、planner_server、controller_server、bt_navigator、behavior_server、smoother_server、velocity_smoother、collision_monitor、waypoint_follower,要求都处于 active。第 8 步 `--spawn` 后面是场景里的出生位姿(x、y、yaw)。

第 2 步很重要。机器人在零速度指令下会缓慢前爬,约 1.1 mm/仿真秒,原因没有查明。AMCL 的初始位姿固定为出生点,Nav2 启动得越晚,初始定位偏差越大(见 §6)。所以每次尝试前要重置场景并尽快启动 Nav2。"⏹ 再 ▶ 后机器人回到出生点"这一点还没有专门验证,会在用户验收时第一次执行;回不到出生点时,改在 RViz 用 2D Pose Estimate 按真实位置初始化定位。

attempt-01 并没有完全按这张表执行。它没有做第 2 步的重置,Play 后约 292 s 仿真时间才启动 Nav2;记录和停止用的是修复前的脚本;现在的 `result.json` 是用重构后的分析脚本对同一份数据重跑的结果。

完整命令与期望输出见 `docs/setup.md`。

## 5. 关键实现

### 5.1 Nav2 的启动与停止:`start_nav2.sh` / `stop_nav2.sh`

目标是"启动的东西能被干净地停掉,而且只停自己启动的东西"。

- **包装进程**:用 `setsid` 让 launch 进入一个新会话,会话领头是一个很小的 bash 包装进程。它在前台运行 `ros2 launch`,结束时把 launch 的真实退出码写进 `nav2.exit`。包装进程用 `trap "true" INT TERM` 挡掉信号,保证自己能活到写完退出码。
- **信号处置**:非交互 shell 用 `&` 启动的后台任务会把 SIGINT 设成"忽略",这个设置一路继承给了 `ros2 launch`,导致它对 SIGINT 毫无反应。启动时用 `env --default-signal=INT,TERM` 把两个信号恢复成默认处置,问题消失。
- **归属核对**:启动时把会话号、launch 进程号、WSL 的开机 ID 和包装进程的启动时刻(`/proc/<pid>/stat` 第 22 字段)写进 `nav2-launch.meta`。停止前核对开机 ID 和启动时刻都与记录一致,并核对这个进程当前的命令行包含本运行目录的 `nav2.exit` 路径;任一项不符就拒绝发信号(退出 5)。原因是运行目录会长期保留,而 WSL 重启后进程号会被复用。
- **停止顺序**:先只给 `ros2 launch` 发 SIGINT,由它按自己的顺序转发给子进程。stdin 不是终端时 launch 以非交互模式运行,会自己转发;如果再对整个进程组发信号,子进程会收到两次。45 s 内没结束,才对本会话升级到 SIGTERM,再到 SIGKILL。
- **残留检查**:用不走 daemon 的全新发现(`ros2 node list --no-daemon`)。daemon 会缓存已死的节点一段时间,会造成误报。发现本身失败时记为"未知"(退出 3),不当作"没有残留"。

实测停止用时 10–13 s,没有残留进程。停止时还有三个上游现象,都不影响导航和记录:
- Nav2 的组件容器在清理阶段段错误,日志为 "Magick: abort due to signal 11 (SIGSEGV)"。从前缀看,这行由 map_server 依赖的 GraphicsMagick 库打印,崩溃本身未必发生在这个库里。run-01、run-04、run-05 三次停止都出现,和发信号的方式无关(§8);原因没有查。
- rviz2 每次结束的方式不同:run-01 为 -6(abort),run-04 为 -9(launch 在 SIGINT、SIGTERM 超时后发了 SIGKILL),run-05 为 -11。
- launch 的退出码在 run-04、run-05 都是 1,对应日志末尾 launch 自身捕获的异常 "Cannot shutdown a ROS adapter that is not running"。按 launch 源码,它只在自身捕获异常或被取消时返回 1,所以这个 1 不是组件容器崩溃造成的。run-01 用的是旧脚本,没有记录退出码。

证据:`artifacts/d0d/commands.md` 的停止路径验证一节;`artifacts/d0d/run-01/`、`run-04-stoptest/`、`run-05-regress/` 的 `nav2-launch.log`;`docs/plan.md` §9。

### 5.2 数据记录:`record_d0.sh` / `stop_record.sh`

- 一次尝试启动 6 个记录器。一个是 rosbag,录 `/clock`、`/chassis/odom`、`/tf`、`/tf_static`、`/cmd_vel`、`/scan`、`/amcl_pose`、`/plan`、`/goal_pose`、`/initialpose`,以及 NavigateToPose 的状态与反馈。后两者是 action 的内部 topic(名字里带 `_action`),ROS 2 默认把它们当作隐藏话题,所以要加 `--include-hidden-topics`。另外 5 个是带现实时间戳的文本流:odom、AMCL 位姿、`/cmd_vel`、action 状态、map→base_link TF。
- 每个记录器单独一个会话,外面套 `timeout -s INT <秒数>` 作为时长上限(默认 320 s 现实时间),再套一个包装进程,把记录器的真实退出码写进 `<名字>.exit`(124 表示到了时长上限)。
- 停止时先对所有会话发 SIGINT,最多等 20 s;仍没结束的会话才升级到 SIGTERM,再等 10 s 后发 SIGKILL。对 rosbag 来说,SIGINT 和 SIGTERM 都会走正常收尾、写出 `metadata.yaml`,SIGKILL 会丢掉它。等所有会话都结束后才复制 bag,避免复制到写了一半的文件。之后检查必需话题:`/clock`、`/chassis/odom`、`/tf` 必须有消息;有目标转录时,action 的状态与反馈也必须有。
- `stop_record.sh` 的退出码:0 正常;1 找不到 `record.pids`;2 ROS 环境加载失败;3 有会话在 SIGKILL 后仍存活,这时不复制 bag;4 缺退出码文件;5 bag 目录缺失、`ros2 bag info` 失败或复制失败;6 必需话题为 0 条。多项失败时取第一个失败的退出码。

### 5.3 发目标:`send_goal.sh`

- 先校验 X、Y、YAW 都是有限数;再读取钉住版本的仓库地图(分辨率 0.05 m,原点 (-11.975, -17.975)),确认目标所在像素是空闲的,并打印目标周围的 ASCII 局部图。
- 用 ROS 2 命令行 action 客户端发一个 NavigateToPose,客户端外面套着 `timeout -s INT 330`,即 330 s 现实时间的兜底上限。客户端输出经一个 Python 小程序加上现实时间戳后写入转录 `goal-*.txt`:第一行是实际发出的目标,之后是目标 ID、全部反馈和结果,最后一行是客户端的真实退出码。退出码取管道第一段的值(`PIPESTATUS[0]`),不会被后面的时间戳程序覆盖。终端只打印摘要行。
- 结果返回后再等 6 s 现实时间,按导航时的实时因子约合 2 s 仿真时间,让记录覆盖机器人停下的过程。attempt-01 在结果后 1.15 s 仿真时间确认停稳。
- 退出码:0 SUCCEEDED;2 参数错误或 ROS 环境加载失败;3 目标不在地图空闲区;4 找不到导航 action 服务器;5 结束但不是 SUCCEEDED(ABORTED、CANCELED 或未知);6 被拒绝;其他值是客户端或外层 timeout 的退出码,例如 330 s 上限触发时 GNU timeout 返回 124。

### 5.4 评测:`analyze_attempt.sh` / `analyze_attempt.py`

`analyze_attempt.sh` 只负责加载 ROS 环境,然后调用 `analyze_attempt.py`。后者分三层:`read_bag` 读 bag(ROS 依赖延迟导入),`parse_goal_transcript` 读转录,纯函数 `evaluate` 根据这两份数据算出结论。评测逻辑是纯函数,所以能用合成数据做固定输入测试,不需要仿真器。

`evaluate` 的判定过程:

1. **核对目标**:从转录第一行取实际发出的目标,与命令行 `--goal` 比较;不一致就停止,不写任何结果(退出 2)。没有转录时,目标记为"未核实",结论最多是 inconclusive。
2. **锁定目标 ID**:ID 取自转录;转录里没有 ID 时(没有转录,或目标被拒绝),取录制中第一个进入 ACCEPTED/EXECUTING 的目标。之后只看这个 ID 的状态与反馈,其他 ID 只列在结果里备查。原因是 action 服务器会在状态数组里保留已结束的旧目标,不过滤就可能把旧目标的 SUCCEEDED 算到新尝试头上。
3. **停稳判定**:从目标终态开始,在 `/chassis/odom` 上找一段"线速度 < 0.05 m/s、角速度 < 0.1 rad/s、持续 1 s 仿真时间"的窗口。相邻两条 odom 的仿真时间戳相差超过 0.25 s 或倒退,就重新计时。结果分三种:
   - confirmed:已停稳,确认时刻是静止刚满 1 s 的那条 odom;
   - not_still:终态后有至少 2 s 仿真时间、没有断档的数据,但一直没停稳;
   - not_observed:数据太短或有断档,无法判断。
4. **到达判定**:取位置的时刻依次是停稳确认时刻、录制中收到目标终态的时刻、录制结束(最后一条 odom)。给了 `--spawn` 时,位置取自不依赖 AMCL 的仿真状态来源(§6);没给时退回 Nav2 反馈里的 AMCL 估计,并记一条 inconclusive 理由。用了哪个时刻、哪个来源,都写在 `result.json` 的 `arrival_check` 里。只比较位置,朝向不参与判定。
5. **数据完整性**:检查 `/clock`、`/chassis/odom`、odom→base_link TF、map→odom TF 四路。在"接受目标到到达判定时刻"的窗口里,相邻消息的接收间隔(现实时间)超过 2 s 就记为不完整;时间戳倒退(按整段录制统计)也记为不完整;任何一路、或目标的反馈在整段录制里一条都没有,同样记为不完整。
6. **给出结论**:输出计划文档 A5 规定的五个字段。

| 字段 | 取值规则 |
| --- | --- |
| execution_status | completed:录制中看到目标终态,或转录记录目标被拒绝。interrupted:目标被接受,但录制中没看到终态。error:录制中找不到目标 |
| task_outcome | reached:终态 SUCCEEDED、已确认停稳、到达误差 ≤ 0.5 m(`--tolerance` 默认值)。canceled:终态 CANCELED。其余情况都是 unknown,包括 ABORTED、被拒绝、SUCCEEDED 但没停稳或超出容差、没有终态。按计划文档的约定,ABORTED 和被拒绝不解释成"不可达",原始状态码和 error_code 另存 |
| safety_status | 固定为 unknown:D0 没有测量接触或碰撞 |
| data_status | complete 或 incomplete,按第 5 步 |
| validation_status | fail:有任何失败证据,即目标被拒绝、被取消、ABORTED、SUCCEEDED 但确定没停稳、到达误差超出容差;fail 优先。pass:没有失败证据,task_outcome 为 reached,且没有任何 inconclusive 理由。inconclusive:其余情况,例如数据不完整、停稳无法观察、没给 `--spawn`、目标未核实、目标被接受后没看到终态、录制中找不到目标 |

程序退出码:0 pass、10 fail、11 inconclusive;2 表示参数错误(含 ROS 环境加载失败)或 `--goal` 与转录不一致,这时不写结果;1 表示 rosbag 读不出来,也不写结果。

### 5.5 诊断与探测脚本

| 脚本 | 作用 |
| --- | --- |
| `probe_env.ps1` / `probe_env.sh` | 只读记录两侧环境:系统、显卡、WSL、ROS 安装状态、残留配置,以及能否免密 sudo(本机需要密码) |
| `probe_topics.sh` | 在 WSL 侧查看 Isaac 的 topic 列表、频率、样本、QoS、发布者 |
| `diag_discovery.sh` | 通信不通时用:被动抓 DDS 发现多播包,判断是哪个方向被挡 |
| `watch_clock.sh` | 连续记录 `/clock` 与现实时间,用于暂停/恢复测试 |
| `check_isaac_bridge.ps1` | 从 kit 日志确认 ROS 2 bridge 是否加载,并记录显存与内存 |
| `inspect_usd.py` | 用 Isaac 自带的 python.bat 运行,只读解析单个 USD 层(不合成 stage):场景文件里的出生位姿,以及机器人文件 `Nova_Carter_ROS.usd` 里 OmniGraph 节点的输入与连线 |

WSL 侧需要 ROS 环境的脚本(本表的 probe_topics、diag_discovery、watch_clock,以及 §5.1–5.4 的脚本)都用显式模式加载 `ros_env.sh`:`--base-only` 只加载 `/opt/ros/jazzy`,`--full` 再叠加构建好的 NVIDIA 工作区。原因是在脚本里无参数地 `source` 时,被 source 的文件会读到脚本自己的位置参数(例如尝试目录),`ros_env.sh` 会拒绝这种情况,而不是把它悄悄当成模式。`probe_env.sh` 有意不加载项目环境,因为它要记录的是原始状态。

## 6. 位置来源与"独立核对"

计划文档要求"到达既保存 Nav2 结果,也用独立位置来源核对",并且要写明位置来自哪里。本项目有三种位置来源,名称与 `result.json` 一致:

| 名称 | 怎么得到 | 性质 |
| --- | --- | --- |
| `nav2_feedback_map` | NavigateToPose 反馈里的 current_pose | AMCL 定位估计 |
| `tf_map_base_link` | `/tf` 的 map→odom(AMCL 给出)加 odom→base_link(Isaac 里程计) | AMCL 定位估计 |
| `sim_state_odom_plus_spawn`(下文称"仿真状态来源") | 场景文件里的出生位姿加 `/chassis/odom`(Isaac 理想里程计) | 不依赖 AMCL |

仿真状态来源只是独立于 AMCL:它和 Nav2 用的是同一份 Isaac 里程计,被替换掉的只是 AMCL 给出的 map→odom。它成立依赖下面的证据和前提:
- **里程计是理想的**:`/chassis/odom` 由 Isaac 的 `IsaacComputeOdometry` 节点计算。这个节点除了执行触发端口(接在每帧的 tick 上),唯一的数据输入是 `chassisPrim`,指向机器人的 `chassis_link`;没有轮速或噪声相关的输入。它的位置与速度输出直接连到发布 `chassis/odom` 的节点。这些连线记录在机器人文件 `Nova_Carter_ROS.usd` 里。
- **里程计从 Play 起算**:Play 后 27.5 s 仿真时间读数 0.030 m,40.3 s 为 0.045 m,340 s 为 0.378 m,505 s 为 0.561 m。每个读数与仿真时间之比都约为 1.1 mm/s,外推到 Play 时刻约为 0。
- **出生位姿可读**:场景文件里 `/World/Nova_Carter_ROS` 的位置是 (-6, -1, 0),朝向 yaw = π,与 Nav2 参数里 AMCL 的初始位姿一致。场景文件对 `chassis_link` 没有任何位姿覆盖。
- **四条前提写在结果里**(`result.json` 的 `preconditions_for_sim_state_source`):
  1. `/chassis/odom` 是相对起始位姿的理想里程计;
  2. 从场景的初始状态按 Play 开始,到录制结束之间没有停止或重置(每次尝试前的重置发生在这次 Play 之前,不违反这一条);
  3. 场景文件里 `/World/Nova_Carter_ROS` 的位姿等于 Play 时底盘(base_link)的位姿。这里只读了各层的编辑值,没有检查合成后的 stage;
  4. Isaac 的世界坐标系就是 Nav2 的 map 系。

  第 3、4 条没有单独验证。

它不是单独的仿真真值 topic。在这些前提成立时,它可以作为不依赖 AMCL 的到达核对;真正独立的到达判定和接触检测留到 D3。

**交叉核对发现的问题**:接受目标时,AMCL 的估计比仿真状态来源偏了 0.324 m。过程如下:
- 机器人在零指令下以约 1.1 mm/仿真秒的速度前爬。
- Play 后约 292 s 仿真时间才启动 Nav2。AMCL 在这一刻按出生点初始化,而机器人已经离开出生点约 0.32 m。
- 之后直到约 510 s 接受目标,AMCL 的 map→odom 一直没变,偏差保持 0.324 m。
- 原地转身时,AMCL 通过激光匹配把偏差降到约 0.09 m;随后直行时回升到约 0.17 m;停稳时为 0.160 m。

结论:每次尝试前要重置场景并尽快启动 Nav2,或者按真实位置手动初始化定位。

证据:`artifacts/d0d/run-01/usd-inspection.txt`、`usd-inspection-wiring.txt`、`nav2-launch.log`(第 100 行是 AMCL 初始化);`artifacts/d0c/probe-04-playing.txt`;`docs/plan.md` §9;`attempt-01/result.json` 的 `position_source_crosscheck` 与 `preconditions_for_sim_state_source`;`attempt-01/trajectory.csv`。

## 7. D0 首次导航结果

目标是 map 坐标 (-4.0, -1.0),朝向 0,由命令行 action 客户端发出。

接受目标时,机器人在出生点 -x 方向约 0.57 m 处:仿真状态来源为 (-6.566, -1.000),AMCL 估计为 (-6.242, -1.000)。它朝向 -x,到目标直线约 2.57 m。Nav2 先原地转了约 130–140°,再边加速边转完剩下的角度,路径向 +y 偏出约 0.18 m,最后停在 (-4.073, -1.053)。

| 项目 | 结果 |
| --- | --- |
| Nav2 终态 | SUCCEEDED(状态码 4),error_code 0,恢复行为 0 次 |
| 接受到结果 | 8.47 s 仿真时间 / 25.61 s 现实时间 |
| 停稳确认 | 结果后 1.15 s 仿真时间 |
| 停稳时的位置误差,仿真状态来源(用于判定) | 0.091 m |
| 停稳时的位置误差,AMCL 估计(TF 合成) | 0.231 m |
| 停稳时的朝向 | 约 0.07 rad(4°),不参与判定 |
| 两种来源之间的距离 | 接受目标时 0.324 m,收到结果时 0.165 m,停稳时 0.160 m |
| 数据完整性 | complete;`/clock` 与 odom 最长接收间隔 0.92 s,AMCL 的 map→odom 最长 1.86 s(门槛 2 s,现实时间) |
| 评测结论 | execution completed、task reached、data complete、validation pass;safety unknown |

"两种来源之间的距离"是两个二维位置之间的距离,不是两个误差相减。Nav2 自己判 SUCCEEDED 用的是 AMCL 估计和 0.25 m 的容差;收到结果时,AMCL 估计距目标约 0.25 m,刚好落在容差边上。

这是一次尝试。它证明链路能用,不代表导航性能,也不能据此说"Nav2 在这个场景下的成功率"。

证据:`artifacts/d0d/run-01/attempt-01/`(`result.json`、`goal-202437.txt`、`trajectory.csv`、`bag-info.txt`、`cmd_vel.txt`)。

## 8. 排障中遇到的关键问题

| 现象 | 查到的原因 | 处理 |
| --- | --- | --- |
| WSL 看不到 Isaac 的任何 topic | 在 WSL 被动监听 DDS 发现多播,12 s 内收到 64 个来自 Windows 主机的包,说明 Windows→WSL 是通的。反方向 ping(ICMP)100% 丢包,提示 WSL→Windows 入站受阻,但 ping 只是旁证。Windows 防火墙三个配置文件都开着,入站默认阻止,kit.exe 没有放行规则,"监听时通知"又是关闭的,所以没有弹窗 | 用户以管理员身份加了一条入站规则:只放行 UDP、只对 kit.exe、只在 vEthernet (WSL) 上。加规则后,其他条件不变,探测立即发现了 `/clock`、`/chassis/odom`、`/tf`,证实了原因 |
| topic 都在,却一条数据也没有 | kit 日志显示 Play 后约 7 s 时间线不再推进。日志特征和后来用户按 ⏸ 时相同;是停止还是暂停、由什么触发,没有查明 | 重新 Play;之后每次先确认 `/clock` 在推进 |
| Nav2 参数里的两路 2D 激光没有数据 | 6.1 的示例场景只发布 3D 点云,不发布 2D 激光 | 记为偏差。缺数据的只是局部代价地图的两个 2D 激光层;局部代价地图还有一个直接用 3D 点云的体素层,首次导航没有受阻。AMCL、全局代价地图和碰撞监视用的 `/scan` 由点云转换得到,不受影响 |
| `ros2 launch` 对 SIGINT 毫无反应 | 非交互 shell 的后台任务继承了"忽略 SIGINT" | 启动时用 `env --default-signal` 恢复默认处置 |
| 停止脚本把信号发给了自己的包装进程 | 包装进程的命令行也包含 "ros2 launch",按命令行匹配会误中 | 改为按父进程查找 launch |
| 每次停止 Nav2,组件容器都段错误 | 上游进程里的崩溃,和发信号方式无关。run-01 时 launch 还在忽略 SIGINT,每个子进程只收到一次 SIGINT,也崩溃了;改成只给 launch 发 SIGINT 后,run-04、run-05 照样崩溃 | 记为已知问题;没有残留进程,不影响导航和记录 |
| AMCL 初始位姿偏了 0.324 m | 零指令下缓慢前爬,而 AMCL 初始位姿固定为出生点,Nav2 启动越晚偏差越大 | 已做:到达判定改用不依赖 AMCL 的来源。已写入流程但还没验证:每次尝试前 ⏹→▶ 重置并尽快启动 Nav2 |
| 想先用 Isaac 自带的 python.bat 在 Windows 侧跑一个无界面的 rclpy talker,看 WSL 能否收到,以省掉一次 GUI 重启 | 加上 ROS 库路径后能找到 rclpy,但自带的 numpy 报 DLL 加载失败,3 次尝试都退出 1 | 判定不可行,直接用 `start_isaac_ros2.ps1` 重启 Isaac |

证据:`artifacts/d0a/commands.md` 与 `docs/environment.md`(python.bat 预测试);`artifacts/d0c/commands.md`、`diag-01.txt`、`kit-udp-endpoints-01.txt`(通信与防火墙);`artifacts/d0d/commands.md` 的停止路径验证一节,以及 run-01、run-04、run-05 的 `nav2-launch.log`;钉住版本的 `carter_navigation_params.yaml`(各模块用哪路激光)。

## 9. 怎么验证的

- **固定输入测试**:`tests/test_analyze_attempt.py` 共 14 个用例,用合成数据覆盖成功、中止、取消、中断、停稳观测不足、旧目标混入、目标不一致、数据断档、缺独立来源、被拒绝、超出容差等情况,不需要仿真器。
- **改坏检查**:在内存里依次破坏 4 条判定规则(停稳恒为确认、不按目标 ID 过滤、把 ABORTED 当成功、关闭数据完整性检查),每次恰好有一个对应的测试失败,恢复后全部通过。这项结果只记在 `artifacts/d0d/commands.md` 的台账里,输出没有单独存档。
- **真实集成证据**:D0c 的数据探测与暂停/恢复测试。暂停 29 s 期间 `/clock` 没有消息,前后仿真时间是 230.850 和 230.867,只差一个仿真步长。另有 D0d 的真实导航(§7)。
- **回归测试**:脚本修复后,在仿真运行时做了一轮正向回归:启动 Nav2、就绪判定、拒绝第二次启动、记录、停止记录、停止 Nav2,退出码都符合预期。反向回归脚本做了 9 项检查,来自 7 次调用:
  - `send_goal` 拒绝非数字 yaw;
  - `analyze` 在 `--goal` 与转录不一致时报错,且 `result.json` 没被覆盖;
  - `stop_nav2` 拒绝无法确认归属的会话,且该会话仍存活;
  - `stop_record` 在 bag 目录缺失时报错;
  - `map_overview` 拒绝畸形的候选点;
  - Nav2 未运行时,`check_nav2_ready` 判为 NOT READY;
  - 另加一次 `setup_workspace` 重跑的幂等检查。

  9 项全部符合预期。
- **审查**:Claude 内部预审(同一模型家族,不算独立审查)提出 38 条意见,核查后确认 35 条,已全部处理并记录在 `docs/review/2026-09-29-d0/REVIEW.md`。Codex 独立只读审查第 1 轮因账户额度中止,没有意见,尚待重跑。
- **证据纪律**:按 AGENTS.md 规则 5 和 `artifacts/README.md` 的格式,命令记录"命令、shell、工作目录、退出码、日志",常驻进程记录"启动、观察时段、停止方式、退出码";不用 `|| true` 之类的方式把失败写成通过。已知例外:run-01 的 Nav2 launch 和 attempt-01 的各记录器没有真实退出码(旧脚本);d0d 台账后两张表缺 shell 和工作目录两列;pytest、改坏检查和部分显存读数只有会话输出,没有单独存档。

证据:`tests/`;`artifacts/d0c/clock-pause-test-02.txt` 与 `artifacts/d0c/commands.md`(暂停/恢复);`artifacts/d0d/run-01/attempt-01/`;`artifacts/d0d/commands.md`(测试、改坏检查、正反向回归的台账);`artifacts/d0d/run-05-regress/`;`docs/review/2026-09-29-d0/REVIEW.md`。

## 10. 已知限制与未验证项

- 只做了一次导航尝试;接触和碰撞没有测量,所以 safety_status 为 unknown。
- 仿真状态来源依赖 §6 的四条前提,不是单独的真值 topic;其中合成后的 USD stage 和"世界系就是 map 系"都没有单独验证。
- "⏹ 再 ▶ 后机器人回到出生点"没有专门验证过,会在用户验收时第一次执行。
- attempt-01 用修复前的记录与停止脚本采集,没有各记录器的退出码;修复后的脚本只在回归测试里用过,还没用于真实导航。
- RViz 的 Nav2 Goal 发目标方式没有执行。用它发的目标没有转录,评测结论最多是 inconclusive。
- 计划 A5 的超时判定、主动取消与停止确认、自动重置、批量运行、HTML 报告都还没有实现。目前只有 `send_goal.sh` 给 action 客户端设的 330 s 现实时间兜底上限,分析脚本能识别 Nav2 返回的 CANCELED。
- Codex 独立审查与用户三步验收尚未完成。三步验收是:① 新终端启动,看到地图与实时数据;② 在已验证区域内发一个目标,看到机器人移动、到达并停下,打开对应记录确认目标和结果一致;③ 暂停仿真,确认时钟和数据不再推进,恢复后确认数据恢复。

**性能只有几次点采样**。显存保留原始单位:

| 状态 | 显存 | 读数来源 |
| --- | --- | --- |
| 只开 Isaac,没加载场景 | 1353 MiB | nvidia-smi |
| 加载示例并按过 Play,时间线已停 | 3124 MiB | nvidia-smi |
| 时间线运行中(Play 后 5 s) | 3754 MiB | nvidia-smi |
| Nav2 运行时 | 3.9 GiB | Isaac 界面 |

实时因子在没启动 Nav2 时为 0.38–0.42,导航时约 0.32。计划 A5 规定导航时限为 120 s 仿真时间,另有 300 s 现实时间上限。按 0.32 计,120 s 仿真时间约等于 375 s 现实时间,会先撞上 300 s 的上限,D2 要按实测重新换算。

证据:`docs/plan.md` §7、§9;`docs/environment.md`;`artifacts/d0c/bridge-check-01-after-launch.txt`、`bridge-check-02-after-play.txt`、`artifacts/d0c/commands.md`。

## 11. 目录结构与复现入口

```
RoboSim-Eval/
├── AGENTS.md / CLAUDE.md          项目地图(Claude Code 与 Codex 共用;CLAUDE.md 只转发到 AGENTS.md)
├── docs/
│   ├── plan.md                    唯一的活计划:状态、决定、偏差、发现
│   ├── setup.md                   本机启动、运行、关闭顺序(复现从这里开始)
│   ├── environment.md             本机环境证据
│   ├── technical-overview.md      本文
│   ├── harness-sources.md         参考资料台账
│   └── review/                    审查材料与记录
├── configs/network/fastdds.xml    两侧共用的 Fast DDS 配置(取自 NVIDIA 工作区)
├── scripts/windows/               Windows 侧:环境探测、启动 Isaac、检查 bridge、防火墙规则、USD 检查、Codex 审查
├── scripts/wsl/                   WSL 侧:环境、安装、探测、Nav2 启停、记录、发目标、分析
├── tests/                         分析脚本的固定输入测试
├── artifacts/README.md            证据目录约定与 commands.md 的记录格式
└── artifacts/d0a … d0d/           每一步的命令台账与原始证据(rosbag 本体不入库)
```

根目录还有三份参考文档:项目计划书和两份开发流程说明。它们是 2026-09-29 冻结的需求参考,状态以 `docs/plan.md` 为准。

复现步骤见 `docs/setup.md`;一次性前提(ROS 安装、工作区构建、防火墙规则)也在其中。

## 12. 后续路线(均未实现)

| 交付 | 计划内容 |
| --- | --- |
| D1 诊断工具 | 运行 doctor:正常时报告真实数据;暂停或关闭仿真后,在有限时间内非零退出。门槛按实测周期设 |
| D2 单次运行 | 用配置运行一次 A→B,保存接受、反馈、结果与轨迹;中断时也能收尾 |
| D3 判定与失败处理 | 跑正常、不可达、取消/断流几种情形;到达、超时、碰撞、取消分开判定;停止可验证 |
| D4 批量与复跑 | 三种预设情形各重复 3 次,每次重置,9 次尝试全部留档并汇总 |
| D5 作品交付 | 别人能照着 README 从新终端启动并演示,能定位代码和证据 |

更远的扩展在计划文档 A8,例如按用户偏好约束导航(减速、保持距离)的对比实验、实验 Agent;前提是 D0–D5 先完成。

## 13. 这个项目能证明什么、不能证明什么

有证据支持的:
- 在 Windows 10 + 8 GB 显存这种官方不支持的机器上,Isaac Sim 6.1 与 WSL2 里的 ROS 2 Jazzy + Nav2 可以接通;跨 Windows/WSL 的 DDS 通信问题已查清并解决。
- 基于现成的 Nova Carter 和 Nav2,跑通了一次真实的 A→B 导航,到达经过不依赖 AMCL 的位置来源核对。
- 记录、启停和评测脚本如实报告退出码,判定规则有固定输入测试和改坏检查。

还不能说的:
- "实现了导航或控制算法":导航来自 Nav2,差速控制来自 Isaac 示例场景;
- "验证了导航性能或成功率":只有一次尝试;
- "D0 已交付":还差独立审查和用户验收;
- "完成了可复跑的批量评测":D4 未做;
- "通过了独立审查":Codex 审查尚未完成。

介绍这个项目时,应说明代码由 AI 编程工具 Claude Code 编写,分工见 §3。

## 附录:术语

| 术语 | 含义 |
| --- | --- |
| 运行(run)、尝试(attempt) | 一次 Nav2 会话,和其中发出的一个目标(§4) |
| 仿真时间、现实时间、实时因子 | 仿真时间来自 `/clock`,现实时间是墙上时钟。实时因子 = 仿真时间 ÷ 现实时间,本机约 0.3–0.4,即仿真比现实慢 |
| 仿真步长 | Isaac 每一步推进 1/60 s 仿真时间 |
| kit.exe、kit 日志 | Isaac Sim 的主进程(基于 NVIDIA Omniverse Kit)和它的运行日志 |
| ROS 2 bridge | Isaac 里负责收发 ROS 2 消息的扩展 |
| OmniGraph | Isaac 场景里的节点图,决定发布哪些 topic、怎样把 `/cmd_vel` 变成轮子动作 |
| USD、层、stage、prim | Isaac 的场景文件格式。一个场景由多个文件层叠加合成为 stage;prim 是场景里的一个对象,例如机器人的根节点 |
| DDS、RMW、Fast DDS、Zenoh | ROS 2 的底层通信。RMW 是 ROS 2 选择通信实现的接口层;Fast DDS 是一种 DDS 实现,Zenoh 是另一种通信实现 |
| domain | `ROS_DOMAIN_ID`,同一 domain 的节点才能互相发现 |
| WSL2、WSLg、NAT、vEthernet (WSL) | Windows 里的 Linux 子系统;WSLg 让 Linux 图形程序显示在 Windows 桌面;NAT 是 WSL2 在 Windows 10 上唯一的网络模式,Windows 通过虚拟网卡 vEthernet (WSL) 与它通信 |
| AMCL | 自适应蒙特卡罗定位。用激光扫描与已知地图匹配,估计机器人在 map 系里的位置;启动时需要一个初始位姿 |
| 生命周期节点 | 有未配置、未激活、激活等状态的 ROS 2 节点。Nav2 的各个服务器都是这种节点,由 lifecycle_manager 统一激活 |
| NavigateToPose、状态码 | Nav2 的"导航到某个位姿" action。状态码 1 ACCEPTED、2 EXECUTING、4 SUCCEEDED、5 CANCELED、6 ABORTED;被拒绝的目标不会进入执行 |
| 固定输入测试、改坏检查 | 用合成数据测试评测逻辑;改坏检查即变异测试,故意改坏一条规则,看测试能否发现 |
| A1、A5、A8、B7 | 根目录计划书的章节:A1 第一版范围,A5 状态合同与判定阈值,A8 后续扩展顺序,B7 D0 的交付要求 |
| Codex | OpenAI 的 AI 编程工具,本项目用它做只读的独立审查 |
| 三步验收 | 用户亲自做的 D0 验收,内容见 §10 |
