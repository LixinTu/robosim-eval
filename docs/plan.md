# RoboSim Eval — 执行计划与状态(唯一活计划)

> 这是项目唯一维护状态的计划。需求、验收方法、状态合同的原文在根目录 `RoboSim-Eval-Plan-and-Setup-ZH(1).md`(2026-09-29 冻结参考),其中的"当前状态"列已作废,状态只看本文件。开发流程约定见两份 harness pack(同样冻结参考)。

## 1. 状态总览

| 交付 | 状态 | 证据 | 阻塞 / 备注 |
| --- | --- | --- | --- |
| 阶段 0 · 唯一计划与入口 | 完成(2026-09-29) | 基线 commit `dbf67ce`(master);分支 `feature/d0-environment`;AGENTS.md / CLAUDE.md / docs/plan.md / docs/harness-sources.md / artifacts/README.md | — |
| D0a · 环境证据 | 完成(2026-09-29 19:02–19:04) | docs/environment.md;artifacts/d0a/(两侧探测原始输出 + commands.md) | 门槛 1→2 通过;发现:WSL 内无 ROS 2,sudo 需密码 |
| D0b · ROS 2 Jazzy + 6.1.0 示例工作区 | 完成(2026-09-29 19:16–19:30) | artifacts/d0b/commands.md(安装日志、check-ros-install、talker/listener ×2、rviz2 测试、setup-workspace.log) | 门槛 2→3 通过。工作区 `~/robotics/vendor/isaac-ros-6.1`,HEAD a9e8471…;安装脚本首跑退出码 1 是校验步骤的 `set -u` 缺陷(已修),安装本身成功 |
| D0c · Windows↔WSL 桥接 + Nova Carter 场景 | 完成(2026-09-29 19:35–20:12) | artifacts/d0c/commands.md;probe-04-playing/(/clock 25–26 Hz、/chassis/odom 25.8 Hz、/tf 25–26 Hz、/front_3d_lidar/lidar_points 2.4–2.8 Hz、tf2_echo odom→base_link);clock-continuity-01;clock-pause-test-02(暂停 29 s 时钟停、恢复后继续);bridge-check-01/02;kit-udp-endpoints-01;diag-01 | 门槛 3→4 通过。排障:Windows 防火墙阻断 WSL→kit.exe 入站(用户以管理员加一条限定规则后解决);首次 Play 后 7 s 时间线被停止(重新 Play 解决)。发现:示例场景不发布 2D 雷达扫描(params 的局部代价地图两路来源无数据,D0d 记偏差);USD 动画时间线每 ~41 s 循环但仿真时钟不受影响;显存峰值 3754 MiB |
| D0d · 一次真实 A→B | 完成(2026-09-29 20:13–20:30) | artifacts/d0d/commands.md;run-01/(nav2-launch.log、ready-check-01、map-overview、rviz-before-goal 截图);run-01/attempt-01/(goal-202437.txt、result.json、trajectory.csv、bag-info、文本流) | 目标 map (-4.0,-1.0,yaw 0) 由 CLI action client 发送:SUCCEEDED、error_code 0、8.47 s 仿真时间、终点误差 0.23–0.25 m、停稳确认 → task_outcome=reached。Nav2 用钉住默认参数;局部代价地图两路 2D 雷达无数据(记偏差);机器人零指令下 ~0.6 mm/s 缓爬(记现象) |
| D0 交付 + 独立审查 | 进行中 | docs/setup.md、docs/review/(待生成) | Codex 0.157.0 已登录;`codex exec --sandbox read-only` 可用 |
| D1 doctor / D2 单次运行 / D3 判定 / D4 批量复跑 / D5 作品交付 | 未开始 | — | D0 通过后按序进行 |

**当前任务(D0c,用户回合):** 用户正常关闭当前 Isaac GUI(PID 29036)→ 在新的普通 PowerShell 运行 `powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1` → 若弹防火墙对话框对 kit.exe 允许(含公用网络)→ Window → Examples → Robotics Examples → ROS2 → Navigation → Nova Carter → Load Sample Scene → Play → 告诉 Claude。Claude 随后运行 `scripts/windows/check_isaac_bridge.ps1`(bridge 是否加载、显存)与 `scripts/wsl/probe_topics.sh`(/clock、odom、TF、雷达)。

**D0b 结果(2026-09-29 19:16–19:30):** ROS 2 Jazzy desktop + Nav2 + 闭包依赖装好(用户执行);WSL 内 talker/listener 默认与加载 fastdds.xml 均通;rviz2 在 WSLg 下存活 20 s(OpenGL 4.5);工作区 `~/robotics/vendor/isaac-ros-6.1` @ a9e8471…,`colcon build --packages-up-to carter_navigation` 成功;launch 参数 map / params_file / use_sim_time 可查询。

**D0a 新增事实(2026-09-29 19:02–19:04,详见 docs/environment.md):** WSL 里完全没有 ROS 2(无 /opt/ros、无 apt 源、无 colcon/rosdep);`sudo -n true` 失败(需密码);WSLg 变量在非交互 shell 也存在;WSL eth0 172.28.211.14/20,网关 172.28.208.1 = Windows vEthernet (WSL);Windows 与 WSL 均无 ROS/DDS 残留配置;`extension_examples` 链接已存在;Claude 的 shell 未提权;Codex 0.157.0 已登录,`codex exec --sandbox read-only` 可用;`isaac-sim.bat` 自动调用 `setup_ros_env.bat`(默认 RMW = rmw_zenoh_cpp,仅当 ROS_DISTRO 未设时才把自带 jazzy 库加入 PATH/AMENT_PREFIX_PATH);自带前缀含 rclpy 7.1.11 与 rmw_fastrtps_cpp.dll / rmw_zenoh_cpp.dll。

**已核实的硬事实(2026-09-29):** Windows 10 Pro 10.0.19045.6466;Isaac Sim 6.1 要求页明确 "Windows 10 is not supported"、显存最低 16 GB、Windows 测试驱动 595.97(本机 591.44);官方 WSL2 路线标 deprecated 且要求 Windows 11;WSL 2.6.3.0 + WSLg 1.0.71,发行版 `Ubuntu` 与 `docker-desktop` 均在运行;`D:\isaac-sim-standalone-6.1.0-windows-x86_64\isaac-sim.bat` 与 `exts\isaacsim.ros2.core\jazzy\lib` 存在;Isaac GUI 进程 `kit`(PID 29036)自 16:22 运行中;Codex CLI 已装(npm);IsaacSim-6.1.0 标签下存在 `jazzy_ws/fastdds.xml` 与 `carter_navigation.launch.xml`(参数 map / params_file / use_sim_time)。

## 2. 决定记录

| 日期 | 决定 | 由谁 | 依据 |
| --- | --- | --- | --- |
| 2026-09-29 | 在官方不支持的配置(Windows 10 + 8 GB)上继续做完 D0,升级留到项目之后;所有记录标注 unsupported configuration | 用户 | GUI 已能开;用户明确指示 |
| 2026-09-29 | `git init` 本地仓库;master = 三份文档基线;D0 在 `feature/d0-environment` 上做 | Claude(默认做法,用户未反对) | harness pack 需要基线与可比对 diff;Codex `/review` 需要 Git |
| 2026-09-29 | fastdds.xml 放仓库内 `configs/network/`,而非计划文档建议的 `D:\robosim-assets\network` | Claude(默认做法,用户未反对) | 受版本管理、单一副本;计划文档 A2 的路径只是建议 |
| 2026-09-29 | 独立审查用 `codex exec`(新进程、只读),与 Apu 项目一致 | Claude(默认做法,用户未反对) | harness pack 默认分工 |
| 2026-09-29 | 三份文档保留带 "(1)" 的原名,不改名 | Claude | 不擅自改用户文件;入口写真实路径 |
| 2026-09-29 | 本轮不绑定 Obsidian 知识库 | Claude | 避免出现第四份计划;触发条件 = D1 之后需要跨会话知识库 |

## 3. 本轮范围

做:D0 剩余部分(D0a→D0d)+ 记录它所需的最小 harness + D0 交付 + Codex 独立审查交接。

不做:D1–D5 及 doctor/runner/recorder/evaluator/report 模块、sim_adapter、网页、persona/LLM/world model、重装 Isaac 或 Ubuntu、换驱动、Pixi/Zenoh 原生路线、mirrored networking、付费服务、push/deploy、删改用户文件、停 Docker、杀用户的 Isaac GUI、`wsl --shutdown`(改变 WSL IP 并影响 docker-desktop;确需时先征得同意)。

## 4. 执行机制(贯穿各阶段)

- 工具调用最多 10 分钟且无 tty:apt、rosdep、clone、colcon 一律后台作业(`setsid nohup bash -l <脚本> < /dev/null > <日志> 2>&1; echo $? > <步骤>.exit &`),短查询轮询 `.exit`;证据表从 `.exit` 读退出码。
- 所有 sudo 一律 `sudo -n`;若 `sudo -n true` 失败,只给用户一个合并命令块(apt 源 + 全部包 + rosdep init),阶段 2 标"等待用户"。
- WSL 命令从 PowerShell 发出,或以脚本文件方式 `bash -l /mnt/d/RoboSim-Eval/scripts/wsl/<脚本>.sh` 运行,避免 Git Bash 的 MSYS 路径改写;.ps1 用 `powershell -ExecutionPolicy Bypass -File` 运行。
- 用户回合检查点:需要 GUI 的步骤(关闭/重启 Isaac、Load Sample Scene、Play、Pause/Resume、2D Pose Estimate、Nav2 Goal)给出操作与"完成后报告什么",然后结束回合等待;不假装已点过。Windows 侧改动合并成一次重启,并在请用户重启前做完所有无 GUI 的验证。
- 常驻进程:`setsid nohup … < /dev/null`,PID 文件,`kill -INT` 停止并有界等待(SIGKILL 会丢 bag 的 metadata.yaml、留下孤儿节点),停止后 `ros2 node list` 确认无残留;限时观察的退出码 124 记为"观察满时长"。
- 记录格式见 artifacts/README.md;每条命令记 命令 | shell | cwd | 退出码 | 日志。

## 5. 最小组合(harness pack 第 C 步)

1. 已覆盖:计划文档 v2.0 已是规格、验收表和状态合同;Apu 的证据目录与审查门只借方法。
2. 真实缺口:无 Git 基线、无入口文件、无已验证的启动顺序、无证据格式。
3. 补的机制与验证方式:AGENTS.md / CLAUDE.md / docs/plan.md(阶段 5 前用一次只读 `codex exec` 让 Codex 列出它加载的说明来源与当前任务);commands.md 格式(故意记录一条失败命令,确认非零退出码被如实记下);审查交接(第一轮真实跑通)。
4. 暂缓及触发条件:R09 Codex 插件(文件交接 + codex exec 够用;两次交接丢材料再考虑)、R12/R13 规格工具(计划文档已是规格)、R14/R06/C07 Skills/Hooks/CI(同一检查漏两次再上)、R15/R16/R18 多任务调度(D1–D5 出现可并行任务再考虑)、R17 BMAD(单人工具)、C10/C11(无需求)、Obsidian 绑定(见决定记录)。

## 6. 阶段

### 阶段 0 · 唯一计划与入口
- [x] `git init`;.gitignore / .gitattributes;基线提交(三份文档原样)
- [x] 分支 `feature/d0-environment`
- [ ] AGENTS.md、CLAUDE.md、docs/plan.md、docs/harness-sources.md、artifacts/README.md、只读探测脚本;提交
- 资料阅读不阻塞探测:S1/S2/S6 在阶段 2 前、S3/S4/S7 在阶段 3 前、C02/C05/C08/C12 在阶段 5 前由主会话读全文;其余 R/C 只读入口页;台账区分 全文 / 摘录 / 仅入口页 / 不可访问。

### 阶段 1 · D0a 环境证据(只读,不装任何东西,不需要用户)
- Windows(scripts/windows/probe_env.ps1):OS/build、nvidia-smi、内存、磁盘、wsl 版本与发行版、Isaac 路径、post_install.bat 会建的链接 vs 实际存在(只查;确缺当前需要的链接才按官方说明修一次)、.wslconfig、防火墙配置文件、vEthernet (WSL) 连接配置文件与 IP、已有 kit.exe 规则、用户/系统环境变量中的 ROS/RMW/FASTRTPS/CYCLONE、执行策略、是否提权、codex 版本/登录/exec 参数、kit 日志位置。
- WSL(scripts/wsl/probe_env.sh,`bash -l` 与 `bash --noprofile --norc` 各跑一次):用户/HOME、os-release、内核、python3/git/colcon、ros2 source 前后、/opt/ros/jazzy、七个目标包逐个状态与 apt 候选、rosdep 状态、`sudo -n true`、DISPLAY/WAYLAND_DISPLAY、eth0 IP、free、磁盘、有无现成工作区、残留 ROS 环境变量与 rc 文件行。
- 输出 → artifacts/d0a/ + docs/environment.md。门槛 1→2:两个探测都有完整输出;Isaac 两个路径存在。

### 阶段 2 · D0b ROS 2 Jazzy + 官方 6.1.0 示例工作区
- 缺 /opt/ros/jazzy 才按 S6 配 noble 源;七个包逐个 `apt-cache policy` 后只补缺项;不做无关升级;后台作业 + 轮询。
- rosdep 未初始化才 init/update。talker/listener 各 `timeout 20`,只标"WSL 内部通信"。
- RViz 提前测试:`timeout 20 rviz2` 记退出码与 GL/Qt 错误;失败试 `LIBGL_ALWAYS_SOFTWARE=1` / `QT_QPA_PLATFORM=xcb`;仍失败则查 launch.xml 中 RViz 退出是否连带关 Nav2,阶段 4 改 CLI 路线并标"RViz 未验证"。
- 克隆 IsaacSim-6.1.0 标签到 `~/robotics/vendor/isaac-ros-6.1`(WSL ext4);`git rev-parse HEAD` 对照 `a9e8471ee901bc2332c1e4aca94ac580713ca3ab`,不一致先报告。已有 checkout 则查 branch/commit/dirty/submodule,干净且匹配才复用。
- jazzy_ws:`colcon list --packages-up-to carter_navigation` → rosdep 只解析这些包(先 `--simulate`)→ `colcon build --packages-up-to carter_navigation`;不改 vendor 文件;rosdep/colcon 失败查源、网络、版本,绝不改 package.xml。
- `ros2 pkg prefix`、`--show-args`;读 launch.xml 与 params,记录 map yaml/pgm、params 路径与 sha256、前后 2D 扫描 topic、amcl 的 set_initial_pose / initial_pose 设置。
- scripts/wsl/ros_env.sh 只含基础环境 + overlay(缺路径即报错退出);跑一次记退出码再提交。
- 门槛 2→3:colcon 退出码 0;`--show-args` 列出 map / params_file / use_sim_time;talker/listener 输出已存;rviz2 测试结果已记。

### 阶段 3 · D0c Windows↔WSL 桥接 + Nova Carter 场景 + 原始数据
- 无 GUI 先做完:configs/network/fastdds.xml(取自钉住版本的 jazzy_ws/fastdds.xml 与 S2;许可放注释、单根元素;两侧 XML 解析通过)→ scripts/wsl/dds_env.sh(导出 FASTRTPS_DEFAULT_PROFILES_FILE 并 `test -f`)→ scripts/windows/start_isaac_ros2.ps1(= 计划文档 B4 块,`$robosimDds` 指向仓库内文件;PowerShell 解析器语法检查,不启动)→ 无 GUI 发现预测试:若 Isaac 的 `python.bat` 加 jazzy lib 后能 `import rclpy`,在 Windows 侧跑无头 talker,从 WSL 看能否收到;不可行则记录并直接进入重启。
- 用户回合(一次性重启):保存 → 正常关闭当前 Isaac(不杀 PID 29036)→ 确认 `Get-Process kit` 为空 → 用户在新的普通 PowerShell 以 Bypass 方式跑脚本;若弹出防火墙对话框,对 kit.exe 允许(含公用网络)→ 用户报告"GUI 已起、控制台无红色错误" → 在 kit 日志确认 isaacsim.ros2.bridge 已加载并记第一条相关错误 → 用户:Window → Examples → Robotics Examples → ROS2 → Navigation → Nova Carter → Load Sample Scene → Play → 报告"已 Play"。只用普通 Nova Carter 示例。
- WSL 侧全部限时:`ros2 topic list -t`;/clock、odom、3D 点云、前后 2D 扫描、/tf 的 hz 与样本;TF 时间戳对 /clock;`ros2 topic info -v` 记 odom 发布者(是否理想里程计)与速度 topic 订阅方类型;2D 扫描 topic 对 Nav2 params;nvidia-smi + 可用内存 + 仿真速度(Δsim/Δwall)+ kit 日志首个加载错误。此时没有 /scan 属正常;不为省显存关雷达。暂停测试(用户回合):Pause → /clock 与一条数据 topic 都停 → Resume → 都恢复。
- 场景加载失败:先存 kit 日志首个错误与 nvidia-smi。OOM → Heightmap Importer(Tools → Robotics → Heightmap Importer + Nova_Carter_ROS.usd),核对分辨率/原点/尺度/碰撞/出生点//clock,地图与参数副本放 configs/,阶段 4 用 `map:=` 引用并记为偏差。
- 发现失败升级链(预算 3 次有假设的尝试或 90 分钟;每次编号记录;Windows 侧改动 = 用户重启一次):① 两侧 domain / RMW / 残留变量 / XML 是否被加载;② `ROS_AUTOMATIC_DISCOVERY_RANGE=SUBNET` + `ROS_STATIC_PEERS=<对端 IP>`(两侧;需验证 Isaac 自带 rcl 是否遵守);③ 从受版本管理的模板生成不入库的 peers XML(UDP 单播 initialPeersList,IP 取阶段 1 记录;WSL IP 每次重启会变);④ 仅一条限定到 WSL vEthernet 子网的入站 UDP 防火墙规则(确切 `New-NetFirewallRule`,经用户同意,需管理员);⑤ 最后才按 S2 官方步骤试 `netsh portproxy`(只转 TCP;计划文档不当作通用修复;只记为"官方步骤已试")。用尽即存最小复现、与 S2 限制对照、提出可验证备选(Pixi 原生)但不执行。
- 门槛 3→4:/clock 连续推进 ≥10 s;odom、TF、雷达 hz 已记;显存低于 8 GB 且稳定;bridge 加载证据已存。

### 阶段 4 · D0d Nav2 + 一次真实 A→B
- 先 `ros2 node list` 确认无已在跑的 lifecycle_manager;默认以 setsid/nohup + PID 文件 + pipefail 日志启动 `ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true`;RViz 起不来则改用户终端或 CLI 路线,谁记录退出码随之明确。
- 就绪门槛两段:初始定位前(上限 60 s):生命周期 active、/scan 与两路 2D 扫描 hz、/map(transient_local)收到、Isaac 的 odom→基座与静态 TF 新鲜、`ros2 param get` 确认 use_sim_time、地图分辨率/原点对场景、`ros2 action list -t` 取真实 action 名与类型。map→odom→基座只在初始定位后查(params 设了 set_initial_pose 则立即查),有界等待。
- 初始定位(用户回合):RViz 2D Pose Estimate 点在真实出生位置,报告"激光与地图贴合";检查 map→odom 出现。不用 odom 推 /initialpose;程序化只从 params 的 amcl 初始位姿或场景 prim 世界位姿取,并同样过贴合检查。
- 发目标前定停机方式:取消 action → 10 s 内 odom twist≈0 → 否则用户在 Isaac 按 Stop;每次尝试只有一个目标发送者(RViz 或 CLI),记录是谁。起点与目标先对照地图空闲区。
- 记录:scripts/wsl/record_d0.sh <目录>(短脚本:`ros2 bag record --include-hidden-topics` 选定 topic + action status/feedback,`timeout -s INT` 限时,无数据非零退出);也是用户验收第 2 步的入口。至少一次用 CLI action client 发目标拿 result + error_code;RViz 发的只能拿 status。
- 时限:接受 10 s;导航 120 s 仿真时间或 300 s 现实时间先到为准;取消确认 10 s。
- 失败分支:不动 → 查目标是否接受、cmd_vel 是否非零、类型是否匹配 Isaac 订阅方、Play 是否在跑,不重发目标掩盖;rejected/aborted → 保留原始状态码与 error_code,记 unknown 而非 unreachable。
- 证据(artifacts/d0d/<时间>/):目标位姿 + frame;action 接受/反馈/结果原始状态码与 error_code;trajectory.csv(每列标 frame 与来源;odom 单独标注并注明是否理想里程计);到达误差在 map 系用 map→基座 TF 计算,标"定位估计,非独立真值";停稳(线速度 <0.05 m/s、角速度 <0.1 rad/s 持续 1 s 仿真时间);仿真时钟与现实时钟;失败尝试全留;明确"碰撞/安全与独立真值未验证(D3)"。

### 阶段 5 · D0 交付与独立审查
- 更新本文件、docs/environment.md;新建 docs/setup.md(已验证的启动/关闭顺序、终端类型、必要条件);未验证清单;Conventional Commits 分阶段提交。
- 审查包 docs/review/<日期>-d0-handoff.md:需求指向、本轮验收清单、基线与被审 commit、完整 `git diff` 存 task.diff + changed-files.json + 未跟踪清单、证据目录、已知限制、AI 参与说明。
- 审查:确切只读 `codex exec` 命令写进 AGENTS.md;先提交冻结;跑 `codex exec` + Codex pack 审查提示词(含真实文件路径);记 codex 版本/模型/被审 hash;逐条核实、只修有效项、重跑受影响检查、拒绝项留依据;第二轮复核修复后的范围;最多两轮;"无发现"不等于通过;Codex 不可用标"待独立审查"并把提示词给用户。
- 最终报告按 pack 七项:完成范围与改动文件;启动命令与必要条件;diff、验证结果与证据位置;失败/未验证/剩余问题/审查状态;三步验收;关键文件与函数;审查材料位置与下次会话入口 + 已存入项目的规则。产品证据与过程证据分节。

## 7. 本轮验收清单
- [ ] D0a:环境记录与现有改动清单;GUI 截图只证明打开。
- [ ] D0b:包可发现、构建成功、launch 参数可查询;命令与退出码。
- [ ] D0c:/clock 持续推进;里程计、TF、激光有样本和频率;暂停可识别。
- [ ] D0d:Nav2 接受并完成目标,轨迹显示移动,到达且停稳;原始证据保留。
- [ ] B7 六项最低交付:环境与依赖版本记录 / 已验证启动顺序 / 一次真实 A→B 的记录 / 最小 diff 说明 / 未验证清单 / 独立审查材料。
- [ ] 用户三步验收:新终端启动看到地图与实时数据;发目标看到达并打开记录核对;暂停看数据停、恢复看数据回来。

## 8. 偏差记录
- fastdds.xml 路径:仓库内 `configs/network/` 而非 `D:\robosim-assets\network`(见决定记录)。
- 工作分支:D0 在 `feature/d0-environment`,master 只放基线;审查范围 = `master..HEAD` + 未跟踪文件。
- Windows 启动脚本将**不**预设 ROS_DISTRO(计划文档 B4 块预设了它):本机 `isaac-sim.bat` 自动调用 `setup_ros_env.bat`,该脚本只在 ROS_DISTRO 未设时才把自带 jazzy 库加入 PATH 与 AMENT_PREFIX_PATH;预设会跳过这一步。脚本只预设 RMW_IMPLEMENTATION=rmw_fastrtps_cpp、ROS_DOMAIN_ID、FASTRTPS_DEFAULT_PROFILES_FILE,并在启动后用 kit 日志核对实际生效值。
- 阶段 2 安装省略了 ROS 文档建议的整体 `apt upgrade`(项目规则:不做无关系统升级);若 apt 因依赖被 hold 而失败,再用 `--with-upgrade` 重跑并记录。
- S6(docs.ros.org)被反爬页拦截,改读计划文档允许的官方托管镜像 repo.test.ros2.org;安装脚本的命令逐条来自该镜像。

## 9. 未验证清单(交付时更新)
- 碰撞/接触、独立仿真真值、自动重置、批量运行、取消/超时处理、doctor/runner/evaluator/report 均未实现或未验证(D1–D4 范围)。

## 10. 风险
- 8 GB 显存 + Windows 10:场景可能跑不起来 → Heightmap 缩场景;仍不行则如实记硬件阻塞。
- NAT 下 DDS 发现:主要排障点;先无 GUI 预测试,配置合并成一次重启;3 次/90 分钟预算与五级升级链。
- RViz 在 WSLg 下可能起不来 → 阶段 2 提前测,失败走 CLI 路线并如实标注。
- sudo/管理员、colcon 构建时间、rosdep 网络、10 分钟工具上限(后台作业规避)。
- 总时长粗估半天到一天,并受用户在 GUI 步骤的可用时间影响。
