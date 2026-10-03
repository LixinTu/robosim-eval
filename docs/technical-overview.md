# RoboSim Eval 技术说明(截至 D5 与审查修复中期,2026-09-30)

本文面向第一次接触这个项目的工程师或面试官,假设读者了解 ROS 2 的基本概念(topic、TF、action、launch)。项目里的专有名词在文末"附录:术语"里解释。

**证据约定**:文中的数字都来自仓库里的记录;§0 和 §16 的审查统计来自 `docs/review/` 下的审查记录(Codex 报告在 `docs/review/2026-09-29-d0/`,Claude 多代理审查在 `docs/review/2026-09-30-claude-review/`)。原始输出在 `artifacts/`(产品证据)和 `docs/review/`(审查过程),各阶段的命令台账是 `artifacts/d0*/commands.md`。rosbag 本体只存在本机、不入库;由 bag 算出的数字可以对照入库的 `trajectory.csv`、`result.json` 和 `bag-info.txt`。少数结果只在台账里有摘要、没有单独存档,文中会注明。多数小节末尾给出证据位置。文中引用的 `docs/plan.md` §n 指 2026-09-30 的版本:2026-10-03 起 plan.md 只留状态、当前任务、决定记录与未解决问题,原各节用 `git show cb7c6a4:docs/plan.md` 查看。

## 0. 摘要

- **做什么**:用现成的机器人(NVIDIA Nova Carter)和现成的导航系统(ROS 2 Nav2)搭一套仿真评测工具:运行导航任务、记录数据、检查异常、给出评测结论,并能按保存的条件复跑。
- **现在到哪一步**:D0–D5 六个交付的主要功能都已实现,并在真实 Isaac 上跑过:环境接通(D0)、运行前诊断(D1)、单次运行器(D2)、分项判定与接触检测(D3)、批量复跑与 HTML 报告(D4)、README 与三个演示(D5)。审查发现其中一项 A5 要求(任务开始时核对起点和目标在允许区域)没有实现,另有若干缺口,见 §16。按 AGENTS.md 的审查门,每个交付还要等 Codex 独立审查和用户验收,这两项都还没完成。现在处在审查修复阶段:Codex 的 11 个审查分片出了 2 份报告(14 条发现),Claude 多代理审查确认了 80 条问题(12 条 Major),一部分已修复,其余正在修(§16)。§1–§8 记录 D0 时的做法和结果,D1–D5 见 §14–§15。
- **关键结果**:D0 首次导航到达,按不依赖 AMCL 的来源核对,距目标 0.091 m(容差 0.5 m)。D4 三个情形各 3 次,9 次全部 pass,每次复位后真值距出生点 0.07 mm。开发中在真实运行里暴露的四个评测工具缺陷都已复现、修复、同条件复跑;审查另外确认的问题见 §16。
- **值得看的部分**:
  - 在官方不支持的机器上,查清并打通了 Windows 与 WSL 之间的 DDS 通信;
  - 用 Isaac 的理想里程计加场景文件里的出生位姿,构造出不依赖 AMCL 的到达核对,并用场景文件里的节点连线证明它的来源。这个核对还发现了一个真实问题:AMCL 的初始定位偏了 0.324 m;
  - 启停、记录、评测脚本记录各进程的真实退出码,评测规则有固定输入测试和改坏检查(Codex 审查发现停止录制脚本不按记录器的退出码判失败、管道只保留上游退出码,正在修,§16.2);
  - D2 起用 Isaac 的 sim_control 服务复位场景、读真值,不再需要 GUI 操作;D3 起在 Isaac 内做 PhysX 接触检测,判定里"没测到"与"没碰撞"分开(批量报告的碰撞列还没区分,见 §16.2);
  - 把"开头卡住"追到了机器人对最小转向指令不响应这一环(§15)。
- **环境前提**:本机是 Windows 10、8 GB 显存(RTX 4070 Laptop)、NVIDIA 驱动 591.44。Isaac Sim 6.1 官方只支持 Windows 11,显存最低 16 GB,测试驱动为 595.97,三项本机都不满足。本文的结论只代表"在这台机器上实测可用"。

证据:`docs/plan.md` §1、§7;`docs/environment.md`;`docs/harness-sources.md` 的 S1(官方要求页摘录;该台账 2026-10-03 已删除,用 `git show cb7c6a4:docs/harness-sources.md` 查看)。

## 1. 目标与当前范围

计划文档(`docs/reference/RoboSim-Eval-Plan-and-Setup-ZH.md`)把产品目标定义为:使用者选择场景、起点和目标,运行一次导航,查看轨迹、任务状态和评测结果,并能按保存的条件复跑。

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

D0d 的两处偏差见 `docs/plan.md` §8。D1–D5 在 D0 之上完成,做法与结果见 §14–§15。计划要求在 RViz 里手动定位并给目标。实际没有手动定位,AMCL 按参数自动用出生点初始化;目标用命令行 action 客户端发出,为的是拿到原始结果和 error_code。

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

D2 起两侧之间还多了两条通路:sim_control 的 ROS 2 服务(同一条 Fast DDS 通路),以及 WSL 经 Windows 侧客户端调用的 Isaac Python 执行服务(只监听本机),见 §14.1。

证据:`artifacts/d0c/probe-04-playing/`、`artifacts/d0c/commands.md`、`artifacts/d0d/run-01/ready-check-01.txt`、`artifacts/d0d/run-01/attempt-01/bag-info.txt`、`docs/environment.md`、钉住版本的 `carter_navigation/params/carter_navigation_params.yaml`。

## 3. 哪些来自上游,哪些是本项目写的

| 部分 | 来源 | 本项目怎么用 |
| --- | --- | --- |
| Isaac Sim 6.1、Nova Carter 机器人与示例场景、场景里的 OmniGraph(传感器、里程计、TF、差速控制) | NVIDIA | 直接复用;启动脚本只设置中间件与 DDS 配置 |
| `carter_navigation`(launch、Nav2 参数文件、仓库地图)与 Fast DDS 配置 `fastdds.xml` | NVIDIA IsaacSim-ros_workspaces,标签 IsaacSim-6.1.0(commit a9e8471) | 钉住版本,只构建 carter_navigation、isaac_ros_navigation_goal、isaacsim_bringup 三个包;原文件不改,参数原样使用。`fastdds.xml` 复制到 `configs/network/`,只把许可声明移进注释,让它成为合法的单根 XML |
| ROS 2 Jazzy、Nav2 1.3.13、RViz、pointcloud_to_laserscan、rosbag2 | ROS 2 / Nav2 开源社区(apt 安装) | 直接复用 |
| 环境探测、安装脚本、防火墙规则脚本、Nav2 启停、数据记录、发目标、评测分析、测试、文档与证据整理 | 本项目 | 自写(见 §5) |

机器人的定位、路径规划和速度指令来自 Nav2;把速度指令变成轮子动作的差速控制来自 Isaac 示例场景里的 OmniGraph。本项目没有实现任何导航或控制算法。

**分工与 AI 参与**:根目录的三份参考文档(项目计划书和两份开发流程说明)由用户提供。除此之外,本项目的代码、脚本和文档由 AI 编程工具 Claude Code 编写。用户执行了需要本人权限或 GUI 的操作:WSL 里的 sudo 安装、管理员权限的防火墙规则、关闭旧的 Isaac 并用启动脚本重启,以及 D0 时的 Isaac GUI 操作(加载场景、Play、暂停;D2 起改由 sim_control 完成,D1 验证暂停时仍由用户按 ⏸)。用户还在 RViz 里目视核对了激光与地图的贴合,提供了 RViz 和防火墙的截图,并做了关键决定:在官方不支持的配置上继续、打开 Isaac 的 Python 执行服务、不等审查先做后续交付。独立审查交给另一个 AI 工具 Codex,以只读方式进行;D0 第 1 轮和重跑都因账户额度用完而中止,之后改成 11 个分片,已出 2 份报告(都是 D0 的分片),其余在排队,整体还没有完成(§16.1)。

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
- 停止时先对所有会话发 SIGINT,最多等 20 s;仍没结束的会话才升级到 SIGTERM,再等 10 s 后发 SIGKILL。对 rosbag 来说,SIGINT 和 SIGTERM 都会走正常收尾、写出 `metadata.yaml`,SIGKILL 会丢掉它。等登记在册的会话都结束后才复制 bag,避免复制到写了一半的文件;某个记录器的会话号没登记上时,这层保护不成立,目前仍可能复制正在写的 bag(§16.2,正在修)。之后检查必需话题:`/clock`、`/chassis/odom`、`/tf` 必须有消息;有目标转录时,action 的状态与反馈也必须有。
- `stop_record.sh` 的退出码:0 正常;1 找不到 `record.pids`;2 ROS 环境加载失败;3 有会话在 SIGKILL 后仍存活,这时不复制 bag;4 缺退出码文件;5 bag 目录缺失、`ros2 bag info` 失败或复制失败;6 必需话题为 0 条。多项失败时取第一个失败的退出码。

### 5.3 发目标:`send_goal.sh`

- 先校验 X、Y、YAW 都是有限数;再读取钉住版本的仓库地图(分辨率 0.05 m,原点 (-11.975, -17.975)),确认目标所在像素是空闲的,并打印目标周围的 ASCII 局部图。
- 用 ROS 2 命令行 action 客户端发一个 NavigateToPose,客户端外面套着 `timeout -s INT 330`:330 s 现实时间后发 SIGINT,客户端取消目标后退出;没有加 `-k`,导航服务器不再响应时客户端可能一直等下去,所以这不是硬上限(审查 shell-6,正在修)。客户端输出经一个 Python 小程序加上现实时间戳后写入转录 `goal-*.txt`:第一行是实际发出的目标,之后是目标 ID、全部反馈和结果,最后一行是客户端的真实退出码。退出码取管道第一段的值(`PIPESTATUS[0]`),不会被后面的时间戳程序覆盖。终端只打印摘要行。
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

- **审查**:Codex 只读审查与 Claude 多代理审查的范围、结果和修复进度见 §16。
- **D1–D5**:固定输入测试在 `feature/d5-demo` 上共 128 个,修复分支 `fix/review-round1` 上 136 个(审查修复还在增加用例);改坏检查中 doctor 7/7、判定模块 8/8;假节点测试中 doctor 6/6、运行器 10/10(ROS domain 42,不需要 Isaac);真实 Isaac 上的结果见 §15。以下各条是 D0 时的验证。
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
- **审查**:Claude 内部预审(同一模型家族,不算独立审查)提出 38 条意见,核查后确认 35 条,已全部处理并记录在 `docs/review/2026-09-29-d0/REVIEW.md`。Codex 独立只读审查第 1 轮和重跑(round1b)都因账户额度中止、没有意见;之后同一范围拆成 4 个分片,已出 2 份报告(共 14 条发现,评测逻辑的 5 条已在修复分支 `c132a68` 修复),其余分片在排队,见 §16。
- **证据纪律**:按 AGENTS.md 规则 5 和 `artifacts/README.md` 的格式,命令记录"命令、shell、工作目录、退出码、日志",常驻进程记录"启动、观察时段、停止方式、退出码";不用 `|| true` 之类的方式把失败写成通过。已知例外:run-01 的 Nav2 launch 和 attempt-01 的各记录器没有真实退出码(旧脚本);d0d 台账后两张表缺 shell 和工作目录两列;pytest、改坏检查和部分显存读数只有会话输出,没有单独存档。

证据:`tests/`;`artifacts/d0c/clock-pause-test-02.txt` 与 `artifacts/d0c/commands.md`(暂停/恢复);`artifacts/d0d/run-01/attempt-01/`;`artifacts/d0d/commands.md`(测试、改坏检查、正反向回归的台账);`artifacts/d0d/run-05-regress/`;`docs/review/2026-09-29-d0/REVIEW.md`。

## 10. 已知限制与未验证项

以下是截至 D5 的情况。审查已确认、正在修复的问题单独列在 §16,这里只列设计上的限制和尚未完成的事项。

- **独立审查与验收**:D0–D5 的 Codex 独立审查和用户验收都还没完成。Codex 的 11 个分片只出了 2 份报告,其余受账户额度限制在排队(§16.1)。D0 的三步验收是:① 新终端启动,看到地图与实时数据;② 在已验证区域内发一个目标,看到机器人移动、到达并停下,打开对应记录确认目标和结果一致;③ 暂停仿真,确认时钟和数据不再推进,恢复后确认数据恢复。
- **样本小、情形少**:D4 每个情形只跑 3 次,是工程试运行,不代表导航性能或成功率。只有一个场景、一个起点、两个目标位置;朝向不参与判定。
- **开头卡住**:大部分机制已查明(§15),DWB 为什么选最小转向档没有查明。批量报告里的平均用时主要反映这个现象。
- **接触检测**:依赖 Python 执行服务;没打开时安全结论是 unknown。
- **不可达的依据**:不可达情形的证据来自离线地图分析,不是在仿真里证明的。
- **时限**:仿真约 0.33 倍实时,120 s 仿真时限约合 360 s 墙钟,所以 300 s 墙钟上限先触发(约 96 s 仿真时间)。D3 的 collision 就是按墙钟上限结束的。
- **D0 时期的遗留**:仿真状态来源的前提第 3、4 条没有单独验证;D2 起判定改用 sim_control 真值,两者相差约 0.1 mm。attempt-01 用修复前的记录与停止脚本采集。
- **没执行过的路径**:RViz 的 Nav2 Goal 发目标没有执行过;用它发的目标没有转录,评测结论最多是 inconclusive。

**性能只有几次点采样**。显存保留原始单位:

| 状态 | 显存 | 读数来源 |
| --- | --- | --- |
| 只开 Isaac,没加载场景 | 1353 MiB | nvidia-smi |
| 加载示例并按过 Play,时间线已停 | 3124 MiB | nvidia-smi |
| 时间线运行中(Play 后 5 s) | 3754 MiB | nvidia-smi |
| Nav2 运行时 | 3.9 GiB | Isaac 界面 |

实时因子在没启动 Nav2 时为 0.38–0.42,导航时约 0.32–0.35(D2–D4 的运行)。

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
│   ├── reference/                 需求文档(2026-09-29 冻结;A4–A6 仍是验收依据)
│   └── review/                    审查材料与记录
├── README.md                      从新终端启动、结果文件、来源与 AI 参与(D5)
├── configs/network/fastdds.xml    两侧共用的 Fast DDS 配置(取自 NVIDIA 工作区)
├── configs/baseline.yaml          话题、doctor 门槛、仿真控制、运行时限、判定规则、情形(D1–D5)
├── configs/assets/                障碍物资产(1 m 箱子、矮箱子)
├── robosim_eval/                  doctor、仿真控制适配、运行器与状态机、判定、接触、报告、批量、Nav2 参数派生;kit/ 下是在 Isaac 内运行的代码
├── scripts/windows/               Windows 侧:环境探测、启动 Isaac、检查 bridge、防火墙规则、USD 检查、Python 执行服务客户端、Codex 审查排队
├── scripts/wsl/                   WSL 侧:环境、安装、探测、Nav2 启停、记录、发目标、分析、doctor、sim、运行、批量、假节点测试
├── tests/                         固定输入测试;ros_fake/ 下是假节点;assets/ 下是测试用的空场景
├── artifacts/README.md            证据目录约定与 commands.md 的记录格式
└── artifacts/d0a … d0d、d1 … d5/  每一步的命令台账与原始证据(rosbag 本体不入库)
```

项目计划书在 `docs/reference/`(2026-09-29 冻结的需求参考,§0 与 B 已作废),状态以 `docs/plan.md` 为准。两份开发流程说明(harness pack)已于 2026-10-03 删除,原文见 git 历史 cb7c6a4。

复现步骤见 `docs/setup.md`;一次性前提(ROS 安装、工作区构建、防火墙规则)也在其中。

## 12. 后续路线

D1–D5 已实现(§14–§15)。§16.3 和 §16.4 的修复除常驻进程脚本一区外,已于 2026-10-03 随 `fix/review-round1` 并入 `chore/harness-cleanup`(合并提交 5241837),并入后在真实 Isaac 上复跑 normal 判 pass,随后这个分支合回 master。剩下的按顺序是:决定是否合入常驻进程脚本的修复(分支 `impl/shell`);在真实 Isaac 上重跑其余预设情形(normal_slow、bypass、unreachable、cancel、timeout、dropout、collision),并从终端按 Ctrl-C 分别中断一次单次运行和一次批量;处理 Codex 其余分片的报告;用户验收;然后发新版本。v0.1.0 已于 2026-09-30 推送到 GitHub。

更远的扩展在计划文档 A8,例如按用户偏好约束导航(减速、保持距离)的对比实验、实验 Agent,都没有开始。D5 的"声明参数改动 + 事先预测 + 复跑对比"可以作为这类对比实验的起点。

## 13. 这个项目能证明什么、不能证明什么

有证据支持的:
- 在 Windows 10 + 8 GB 显存这种官方不支持的机器上,Isaac Sim 6.1 与 WSL2 里的 ROS 2 Jazzy + Nav2 可以接通;跨 Windows/WSL 的 DDS 通信问题已查清并解决。
- "基于现成机器人和 Nav2,做了仿真任务运行、数据记录、异常处理与可复跑评测":运行前诊断、复位并用真值核对、状态机、取消与停车确认、分项判定、接触检测、批量复跑和报告都已实现,主要路径在真实 Isaac 上跑过(§15);异常收尾和取消/停车确认还有审查确认的缺口,正在修(§16.2)。
- 判定规则有固定输入测试和改坏检查;开发中暴露的四个评测工具缺陷都有复现、修复和同条件复跑(审查另外确认的问题还没修完,见 §16)。

还不能说的:
- "实现了导航或控制算法":导航来自 Nav2,差速控制来自 Isaac 示例场景;
- "验证了导航性能或成功率":每个情形只有 3 次工程试运行;
- "已交付""通过了独立审查":Codex 审查和用户验收都还没完成,审查确认的问题也还没修完(§16)。

介绍这个项目时,应说明代码由 AI 编程工具 Claude Code 编写,分工见 §3。

## 14. D1–D5:自动运行、判定、批量与报告

D0 之后,§4 那串手动脚本由 Python 包 `robosim_eval/` 串起来。Nav2 启停、录制、离线分析仍复用 §5 的脚本,新增部分如下。

### 14.1 仿真控制与接触检测

- **sim_control**:`start_isaac_ros2.ps1` 默认打开 Isaac 的 `isaacsim.ros2.sim_control` 扩展。它走同一条 Fast DDS 通路,提供 ROS 2 simulation_interfaces 服务:查询和设置仿真状态、复位、加载场景、生成和删除实体、读实体状态。`robosim_eval/sim_adapter.py` 封装这些服务,命令行入口是 `scripts/wsl/sim.sh`。
- **复位与真值**:复位 = 停止 → 删除生成的实体 → Play,仿真时钟从 0 重新开始。复位后读 `chassis_link` 刚体的实时位姿和速度作为真值,核对机器人回到出生点;D4 九次都在 0.07 mm 以内。这验证了 D0 留下的"⏹→▶ 后回到出生点"。D2 起的到达判定改用这个真值,不再依赖 §6 的"出生位姿 + 理想里程计"(两者相差约 0.1 mm)。
- **边界**:障碍物只生成在 `/World/RoboSimObstacles` 下;工具从不请求 QUITTING 状态(它会关闭 Isaac)。
- **接触检测**:用户 2026-09-30 同意后,`-PythonServer` 打开 Isaac 的 Python 执行服务。它只监听 127.0.0.1,需要令牌;令牌由 Isaac 启动时随机生成,只写进本机日志,不进仓库,也不出现在命令行上。`robosim_eval/kit/contact_monitor.py` 在 Isaac 里给机器人的 8 个刚体挂 PhysX 接触报告并订阅事件。`robosim_eval/contacts.py` 从 WSL 经 Windows 侧客户端 `scripts/windows/isaac_py.ps1` 调用它;客户端只接受 `robosim_eval/kit/` 下的文件。

### 14.2 运行前诊断:doctor(D1)

订阅 `/clock`、odom、odom→base_link TF 和点云,在 5 s 窗口里测频率、最大间隔、新鲜度和仿真时间是否推进。门槛来自 D0 实测,写在 `configs/baseline.yaml`。退出码:0 正常;10 仿真不推进(暂停);11 缺数据(没有发布者,例如 Isaac 关闭或场景未加载);12 频率或新鲜度不够;13 环境不对。判定是纯函数 `doctor_checks.py`,有固定输入测试和改坏检查(7/7);假节点测试在 ROS domain 42 上进行,不影响正在运行的 Isaac。

### 14.3 单次运行器(D2)

`runner_fsm.py` 的状态机:PREPARE → WAIT_READY → SEND_GOAL → EXECUTING →(CANCELING)→ STOP_CONFIRM → TEARDOWN → DONE。时限来自计划 A5,可按情形覆盖。

| 阶段 | 做什么 | 时限 |
| --- | --- | --- |
| PREPARE | 写 manifest 和解析后的配置;场景没加载就加载;装接触监视;复位并用真值核对;生成障碍物;清掉复位与落地产生的接触事件;doctor(复位后点云约 2 s 才恢复,只对"降级"做有限重查) | — |
| WAIT_READY | 启动 Nav2,等 10 个生命周期节点 active、导航动作服务就绪;有声明的参数改动时,从运行中的节点读回核对 | 60 s 墙钟 |
| SEND_GOAL | 开始录制,发 NavigateToPose,等接受 | 10 s 墙钟 |
| EXECUTING | 等终态;检查仿真与墙钟时限;执行注入的取消或暂停;收到 SIGINT/SIGTERM 就取消目标 | 120 s 仿真 + 300 s 墙钟 |
| CANCELING | 取消并等回执 | 10 s 墙钟 |
| STOP_CONFIRM | 只用终态之后的里程计判断:线速度 < 0.05 m/s、角速度 < 0.1 rad/s,持续 1 s 仿真时间 | 10 s 墙钟 |
| TEARDOWN | 读真值、取回接触数据、多录 3 s、停录制、离线分析、停 Nav2,最后写 `result.json` | — |

任何阶段出错或被中断都会走 TEARDOWN。审查发现这里有缺口,正在修(§16.2):在发目标阶段被中断、等接受超时,或目标已接受后出现内部错误时,收尾不会取消已发出的目标(Nav2 通常几毫秒内就接受了,但运行器没有读取目标句柄),也不确认停车;收尾的某一步抛出异常会跳过后面的步骤。另外,在终端里按 Ctrl-C 经 `run_scenario.sh` 到不了运行器(`timeout` 把运行器放进了后台进程组),D2 的中断演示是由脚本直接给运行器进程发 SIGINT 完成的。退出码:0 pass、10 fail、11 inconclusive、20 被中断、30 运行出错、31 取消或停车确认超时(批量据此中止)、2 参数或配置错误。按现在的代码,20 不保证已取消目标(发目标阶段被中断也返回 20);等接受超时或接受后出现内部错误时返回 30,停车没有确认,批量也不中止;收尾某一步抛异常时进程以 1 退出,不写 result.json(§16.2,正在修)。

### 14.4 判定(D3)

`evaluator.py` 是纯函数,四个分项分开判:

- **任务结果**:按优先级依次是 timeout(运行器时限触发)、canceled(有 CANCELED 回执)、reached(SUCCEEDED、停车已确认、真值距目标 ≤ 0.5 m)、unreachable(ABORTED 或被拒绝,情形在配置里标为预设不可达,没有真值证明已到达,数据完整;配置里附的离线地图证据只是说明文字,代码不核对,缺真值时也会判不可达,见 §16.2),都不满足就是 unknown。ABORTED 不会被自动解释成不可达。
- **安全**:有实测接触数据时,排除两个地面碰撞平面和机器人自身后仍有接触就判 fail;没有实测就是 unknown,不当作"没碰撞"。
- **数据**:必需流(`/clock`、odom、Isaac 的 odom→base_link)在"接受目标到到达判定"的窗口里没有消息、断流超过 2 s 墙钟、时间戳倒退、复位后仿真时钟倒退,任一项都判 incomplete("窗口里没有消息"这一条是审查后加的,修复分支 `c132a68`);窗口两端都取自 bag,bag 缺"目标已接受"状态或提前结束时,没录到的部分不检查,这个缺口见 §16.2;AMCL 的 map→odom 只作参考,断流只记警告。
- **评测**:有失败证据就判 fail,例如碰撞、结果与情形预期不符、停不下来;结果符合预期且安全 pass、数据完整、运行完成才判 pass;其余判 inconclusive。操作员中断判 inconclusive,不判 fail。

有固定输入测试和改坏检查(8/8),覆盖计划要求的四种坏数据:虚假成功、缺接触数据、时间倒退、取消无回执。

### 14.5 批量与报告(D4)

`batch.py` 交替运行:先把每个情形各跑 1 次,再各跑第 2 次,依此类推;每次尝试是一个独立的运行器进程。遇到退出 31 就停止后面的尝试,并把它们记为未运行。`report.py` 只读已保存的记录,生成静态 HTML:
- 按情形分组,不合并成功率;
- 失败和 inconclusive 的运行列出理由;
- 平均用时只算到达的运行,并注明;
- 列出批次里的每个 commit 和各软件版本;
- 给出每次的复位误差、Nav2 恢复次数,以及地图上的轨迹(出生位姿加理想里程计,不依赖 AMCL,与真值相差约 0.1 mm)。

### 14.6 声明的参数改动(D5)

情形可以声明 Nav2 参数改动(`nav2_params`)。运行器从 NVIDIA 原始参数文件派生运行目录里的 `nav2_params.yaml`:只改声明的那一行,其余字节不变,并解析两份文本核对。Nav2 起来后,运行器从运行中的节点读回这个参数;与声明不符就判出错,不发目标。

## 15. D1–D5 的真实结果

| 交付 | 真实 Isaac 上的结果 | 证据 |
| --- | --- | --- |
| D1 | 运行中退出 0;用户按 ⏸ 后,2 s 窗口判不推进(10);Isaac 关闭时判缺数据(11) | `artifacts/d1/commands.md` |
| D2 | normal 到达,真值距目标 0.264 m;导航中由脚本给运行器进程发 SIGINT → 取消、停车、收尾,判 interrupted(终端 Ctrl-C 的路径没有测过,见 §16) | `artifacts/d2/commands.md` |
| D3 | normal、bypass、unreachable、cancel、timeout 判 pass;dropout(暂停 6 s)判 inconclusive;collision(矮箱子)抓到轮子与箱子的接触,判 fail | `artifacts/d3/commands.md` |
| D4 | normal、bypass、unreachable 各 3 次,9 次全部 pass;每次复位后真值距出生点 0.07 mm | `artifacts/d4/commands.md`、`artifacts/d4/batch-20260930-013010/runs/report.html` |
| D5 | 在新的 PowerShell 里逐字执行 README 第 2 步的两条命令(Isaac 没有重启,用加载空场景模拟"刚启动、场景未加载";第 1、3 步没有按原文执行):doctor 退出 11;normal pass(真值 0.049 m);另在同一终端跑 cancel,pass;参数改动的预测与复跑见 `docs/demo.md` | `artifacts/d5/commands.md`、`docs/demo.md` |

**开发中暴露的评测工具缺陷**:四个,都在真实 Isaac 运行中出现,都有复现、修复和同条件复跑(`docs/defect-record.md`);审查另外确认的问题见 §16,大部分还在修:
1. 停稳确认用了结果之前的样本(D2);
2. 复位前的 odom 样本留在缓存里(D3);
3. 场景未加载时接触监视装不上(D5);
4. 接受目标时的仿真时间是旧的,导航时限和注入的取消、暂停都提前约 1.5 s 触发(D5)。

**开头卡住**:不少运行在收到目标后约 37 s 仿真时间不动,Nav2 恢复 5 次后才到达。D4 查到大部分机制:
- 机器人开头正好背对全局路径(AMCL 朝向 180°、路径方向 0°);
- DWB 常选绝对值最小的转向档 +0.0368 rad/s;
- 直接实验证实,机器人对这个指令基本不转(8 s 仿真时间只转 0.0004 rad);
- 机器人不转,状态不变,控制器就一直选这一档,直到进度检查触发恢复。

DWB 为什么把这一档打分最高没有查明。它不影响判定,但让平均用时主要反映卡住,而不是导航速度。证据见 `artifacts/d4/commands.md`。

## 16. 审查与修复(截至 2026-10-03)

D0–D5 做完之后,先后有两路审查。结论还没有全部处理完,本节记录现状。2026-10-03,修复分支 `fix/review-round1`(16.3,以及 16.4 中除常驻进程脚本以外的四个区域)并入 `chore/harness-cleanup`(合并提交 5241837),并入后用这份代码(bf7f431)在真实 Isaac 上复跑 normal 判 pass(`artifacts/review-2026-10-03/`),随后这个分支合回 master。README 和 docs/setup.md 已按合并后的行为更新;本文标题、§0、§9、§13–§15 仍是修复前(2026-09-30)的描述,与本节不一致时以本节为准。

### 16.1 两路审查

| 来源 | 范围 | 结果 |
| --- | --- | --- |
| Codex 独立只读审查(OpenAI 的 Codex CLI,`--sandbox read-only`) | D0 拆成 4 个分片,D1 1 个,D2、D3 各 2 个,D4、D5 各 1 个,共 11 个;每个分片用 `git show <冻结提交>:<路径>` 读被审版本 | 账户额度每个窗口(约 5 小时)只够审 1 个分片(D0 常驻进程脚本那一片用了约 7.4 万 token)。已出 2 份报告:D0 评测逻辑(5 条,3 条 Major)和 D0 常驻进程与退出码脚本(9 条,7 条 Major);其余 9 个分片还没出报告:round1c-c 四次撞上账户额度,排队进程已停,额度恢复(Codex 提示最早 2026-10-06)后要重新启动排队 |
| Claude 多代理审查(与编写代码的是同一模型家族,不算独立审查) | D0–D5 的全部代码(提交 `7fe517e`)和主要文档,分 7 个维度(本文 §4–§8 和 docs/setup.md 中 D0 时期的内容没有系统核对) | 81 条发现;每个维度的发现再由一个复核代理尝试推翻,81 条中 74 条用固定输入复现,另 7 条只做了代码或文档核对;另有一个代理找覆盖漏洞和跨模块问题。确认 80 条(12 条 Major、68 条 Minor),推翻 1 条 |

Codex 的报告、状态文件和队列日志在 `docs/review/2026-09-29-d0/`;Claude 多代理审查的全部发现、复核记录和分区清单在 `docs/review/2026-09-30-claude-review/`,修复分支的提交说明按编号(如 shell-1、docs-3)引用它们。Codex 报告按 Harness 流程逐条核实后再修,不直接照搬。

### 16.2 主要问题

下面是审查时(2026-09-30)确认的主要问题,按影响归类;除 D0 常驻进程脚本一条外,都已修复,并在 2026-10-03 随 `fix/review-round1` 并入 `chore/harness-cleanup`、合回 master(16.3、16.4):12 条确认后仍为 Major 的都在其中,另有几条同类的 Minor,以及 Codex 报告评为 Major、尚待逐条核实的 D0 脚本问题。除了故障注入情形的评测结论(见 §16.5),它们都没有让已记录的真实运行得出错误结论,但在别的输入或故障下会。

- **收尾不完整**:在发目标阶段被中断、或等接受超时时,运行器已经发出的目标不会被取消,也不确认停车。被中断时退出码是 20(README 把 20 写成"已取消目标并收尾",在这条路径上并不成立),等接受超时时是 30;两种情况批量都会继续跑,因为批量只在退出码 31 时中止。A5 要求"停止未确认时,中止后续批次并留下错误"。同类但复核后降为 Minor 的还有两条:目标已接受后出现内部错误时同样不取消目标、不确认停车,退出码 30;收尾某一步抛异常时,其后的停录制、停 Nav2、写 result.json 会被跳过。
- **终端 Ctrl-C 无效**:`run_scenario.sh` 用 `timeout` 包住运行器,`run_batch.sh` 用 `timeout` 包住批量进程,都没有加 `--foreground`。`timeout` 会把自己和子进程放进新的进程组;在伪终端上复现,终端的 Ctrl-C 既送不到运行器,也送不到批量(真实 Windows 控制台经 wsl.exe 的路径没有测)。README 写的"20 = 被 Ctrl-C 中断(已取消目标并收尾)"和 docs/setup.md 写的"Ctrl-C 只会让它取消目标并照常收尾"都从没按终端方式验证过。
- **两个运行器可以同时跑**:第二个运行器会复位正在使用的仿真、清空共享的接触缓存,没有任何互斥。
- **数据覆盖只看 bag 自己**:D3 判数据完整性的窗口两端都取自 bag,bag 提前结束或缺少"目标已接受"的状态时,数据仍判 complete。
- **D2 起的运行器没有实现 A5 的"任务开始时验证起点和目标位于允许区域"**:运行器只用真值核对机器人回到了配置的出生点,从不对照地图检查起点和目标。D0 的 `send_goal.sh` 只检查目标所在像素是否空闲,不检查起点,运行器也不调用它。预设不可达情形也只看配置里的标签,没有核对离线证据(这一条复核后是 Minor)。
- **接触客户端在中文系统上会崩**:本机是中文 Windows(代码页 936)。`isaac_py.ps1` 遇到未捕获的 .NET 错误时(例如 Isaac 主循环卡住超过 75 s 导致读超时、连接被重置、回复被截断),stderr 是中文;客户端按严格 UTF-8 解码,抛出的 UnicodeDecodeError 不属于 ContactError,没有被捕获(空回复和连接被拒绝不走这条路径)。发生在安装接触监视时,这次运行直接判为执行错误(退出码 30);发生在收尾取接触数据时,后面的停录制、停 Nav2、写 result.json 都会被跳过。
- **报告**:接触没有实测的运行,碰撞列也显示 0;终端 Ctrl-C 同样到不了批量。
- **D0 的常驻进程脚本**(Codex 报告;以下 7 条是 Codex 自评的 Major,尚未逐条复核;其中按会话号发信号、同一目录重复启动录制、launch 异常退出后的残留三条,Claude 审查也发现了,复核后评为 Minor):停止录制只凭历史会话号发信号,没有核对归属;录制器异常退出时停止脚本仍可能返回 0;管道只保存上游退出码;同一目录重复启动录制会丢掉上一轮的进程登记;进程登记失败时仍可能复制正在写的 bag;launch 异常退出后残留的 Nav2 节点无法清理;发目标时的地图空闲检查固定读 NVIDIA 的地图,可能与本次实际加载的地图不一致。
- **审查流程自身**:Codex 审查队列判断"撞上额度上限"时搜索整份输出,而输出里含有 Codex 读过的文件原文;被审文件本身含有这句提示时(例如 D0 round1c-c 要审的 `run_codex_review.ps1`),正常完成的审查会被误判为撞上限而反复重跑,重试时刻也可能取自被引用的文字;README 把独立审查写成了已完成。

### 16.3 已修复(修复分支 `fix/review-round1`,2026-10-03 并入 `chore/harness-cleanup`,随它合回 master)

| 提交 | 内容 | 验证 |
| --- | --- | --- |
| `c132a68` | Codex D0 评测逻辑的 5 条:数据完整性要求评测窗口里有消息,离线分析和 D3 判定两处都改;转录没有目标 ID 时不再让 bag 里的其他目标通过;到达判定不使用过旧的位置样本;TF 合成不再把后来的变换套到更早的样本上;目标值为 NaN 或无穷时按参数错误拒绝 | 8 个新测试用例(6 个测试函数,其中一个参数化为 3 例),修复前全部失败(7 例断言失败,1 例因 `integrity_gap` 尚不存在而无法导入);修复后全部 136 个测试通过。用修复前后的离线分析分别在内存里重算 32 次真实运行,两份对照输出完全相同,即修复没有改变任何一次运行的结论(`artifacts/review-2026-09-30/regress-analyzer-7fe517e.txt` 与 `regress-analyzer-c132a68.txt`) |
| `7fe517e`(已在 `feature/d5-demo`)、`156c31a` | Codex 审查队列:能解析只有时刻的重试提示;只认 Codex 自己在行首输出的 `ERROR:` 行;退出码 0 且写出报告就算完成;重启队列不覆盖之前的尝试文件 | 11 个固定输入用例;对真实的成功输出和撞上限输出都判对 |
| `94be232` | 文档:README 的审查状态、测试命令、输出文件说明、"开头卡住"的描述;D5 的数字和措辞;AGENTS.md 的运行步骤;根目录加 `pytest.ini`,测试命令从任何目录都能运行 | 从 WSL 家目录运行全部测试通过 |

### 16.4 分区修复(2026-10-03 状态)

其余发现分 5 个区域,各在一个独立的 git worktree 和分支(`impl/core`、`impl/sim`、`impl/config`、`impl/report`、`impl/shell`)上并行修复。每个区域先写失败的测试再改代码,完成后由另一个代理审查 diff,按审查意见返修,最后合并,再在真实 Isaac 上重跑。前四个区域于 2026-09-30 合入 `fix/review-round1`,随它在 2026-10-03 并入 `chore/harness-cleanup`(5241837)、合回 master。常驻进程脚本一区(`impl/shell`,10 个提交)没有合入:最后两个提交是按审查意见的返修,之后有没有再审查没有记录,也没在真实 Isaac 上跑过;分支保留在 GitHub 上,是否合入待定。

| 区域 | 改动 | 状态 |
| --- | --- | --- |
| 运行器与判定 | 收尾安全网:有已接受但没有终态的目标就取消、等回执、确认停车,确认不了就中止批次;收尾每一步单独捕获异常;单实例锁;按 NVIDIA 地图检查起点和目标是否在膨胀后的空闲区,预设不可达用地图路径搜索作为证据;生成障碍物后读回核对位置;`run_scenario.sh` 改用 `timeout --foreground`,用伪终端发送 Ctrl-C 做自动化测试;取消和超时的结论也要求停车确认;接触事件有丢失时安全不判 pass;缺真值时不判不可达;故障注入情形可以声明安全与数据两项预期 | 已并入 |
| 仿真控制与接触 | 客户端按实际编码解码 PowerShell 输出;清空之前就开始、之后仍持续的接触也要上报;接触事件用仿真时间打时间戳 | 已并入 |
| 配置与 doctor | 数值、键名、障碍物资产名和重复名称的校验;接口类型检查改看发布者的类型;配置错误和环境错误按文档给出退出码 2 和 13,不再抛出 traceback | 已并入 |
| 报告与批量 | 每个计划中的尝试都在报告里有去向;接触未实测时碰撞列显示"未测量";批量能被终端 Ctrl-C 中断并收尾;运行器异常退出时按"停止未确认"中止批次;给 `batch.py` 补测试 | 已并入 |
| 常驻进程脚本 | 只对能证明是自己启动的进程发信号;检查每个录制器和转录器的真实退出码;拒绝在同一目录重复启动录制;能清理 launch 异常退出后的残留;审查队列使用原子锁 | 未合入(`impl/shell`) |

### 16.5 对已有结论的影响

- **已记录的真实运行**:用 `c132a68` 之后的离线分析在内存里重算了留有 rosbag 的 32 次真实运行,31 次与原记录一致;唯一的差别是 D2 的中断演示:原记录顶层存的是运行器的执行状态 interrupted,离线分析只看到 CANCELED 终态记 completed。修复前的离线分析给出完全相同的对照结果,所以这个差别与修复无关。也没有任何一次运行出现"窗口内缺必需数据"。重算脚本和输出:`artifacts/review-2026-09-30/regress_analyzer.sh`、`regress-analyzer-c132a68.txt`。
- **修复带来的副作用**:`run_scenario.sh` 改用 `timeout --foreground` 后,运行中关掉它所在的终端窗口会直接结束运行器,不取消目标、不收尾(机制用替身进程在伪终端上验证过,见 README 已知限制与 docs/plan.md §4)。
- **并入后的真实运行**:2026-10-03 在真实 Isaac 上用并入修复后的代码跑了一次 normal:到达、安全 pass、数据完整,验证 pass(停车确认时真值距目标 0.145 m,Nav2 0 次恢复)。同一天更早的一次因 WSL 的墙钟被往回拨、录下的时间戳倒退,数据判不完整(inconclusive),与代码无关。记录与排查见 `artifacts/review-2026-10-03/commands.md`。其余情形还没有用合并后的代码重跑。
- **修复合并后会变的(还没用真实运行验证)**:D3 的 collision 和 dropout 是故障注入情形,A5 把 validation_status 定义为"当前测试预期是否满足"。现在它们只能声明导航结果的预期:dropout 抓到断流后判 inconclusive;collision 抓到轮子与矮箱子的接触而判 fail,但那次同时因为超时(timeout)与声明的 reached 不符而判 fail。加入安全和数据两项预期之后,dropout 重跑时若只出现断流应判 pass;collision 只有撞箱后仍到达目标才会判 pass,若再次超时,除非同时改它的导航结果预期,否则仍判 fail。重跑的结论以新记录为准,旧记录保留。
- **不会变的**:判定规则的方向不变:未测量不当成安全,缺数据不当成完整,原因不明时用 unknown。除故障注入情形改为按声明的安全、数据预期判定之外(注入生效时由 fail 或 inconclusive 变为 pass,注入无效时由 pass 变为 fail),其余改动都是收紧。

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
| sim_control | Isaac 的一个扩展,用 ROS 2 服务控制仿真:复位、加载场景、生成实体、读实体的真实位姿(§14.1) |
| 真值 | 从 Isaac 物理引擎直接读出的机器人位姿,不经过定位算法 |
| 情形 | 计划文档所说的"场景",指一组测试条件:目标、障碍物、预期结果、注入的故障(`configs/baseline.yaml` 的 scenarios) |
| DWB | Nav2 的局部控制器:在速度空间采样、按几项评分挑出下一条速度指令 |
| 故障注入 | 有意制造的失败条件(取消、暂停、矮箱子、短时限),在配置里标注,不当作真实缺陷 |
