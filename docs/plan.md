# RoboSim Eval — 执行计划与状态(唯一活计划)

> 这是项目唯一维护状态的计划。需求、验收方法、状态合同的原文在根目录 `RoboSim-Eval-Plan-and-Setup-ZH(1).md`(2026-09-29 冻结参考),其中的"当前状态"列已作废,状态只看本文件。开发流程约定见两份 harness pack(同样冻结参考)。

## 1. 状态总览

| 交付 | 状态 | 证据 | 阻塞 / 备注 |
| --- | --- | --- | --- |
| 阶段 0 · 唯一计划与入口 | 完成(2026-09-29) | 基线 commit `dbf67ce`(master);分支 `feature/d0-environment`;AGENTS.md / CLAUDE.md / docs/plan.md / docs/harness-sources.md / artifacts/README.md | — |
| D0a · 环境证据 | 完成(2026-09-29 19:02–19:04) | docs/environment.md;artifacts/d0a/(两侧探测原始输出 + commands.md) | 门槛 1→2 通过;发现:WSL 内无 ROS 2,sudo 需密码 |
| D0b · ROS 2 Jazzy + 6.1.0 示例工作区 | 完成(2026-09-29 19:16–19:30) | artifacts/d0b/commands.md(安装日志、check-ros-install、talker/listener ×2、rviz2 测试、setup-workspace.log) | 门槛 2→3 通过。工作区 `~/robotics/vendor/isaac-ros-6.1`,HEAD a9e8471…;安装脚本首跑退出码 1 是校验步骤的 `set -u` 缺陷(已修),安装本身成功 |
| D0c · Windows↔WSL 桥接 + Nova Carter 场景 | 完成(2026-09-29 19:35–20:12) | artifacts/d0c/commands.md;probe-04-playing/(/clock 25–26 Hz、/chassis/odom 25.8 Hz、/tf 25–26 Hz、/front_3d_lidar/lidar_points 2.4–2.8 Hz、tf2_echo odom→base_link);clock-continuity-01;clock-pause-test-02(暂停 29 s 时钟停、恢复后继续);bridge-check-01/02;kit-udp-endpoints-01;diag-01 | 门槛 3→4 通过。排障:Windows 防火墙阻断 WSL→kit.exe 入站(用户以管理员加一条限定规则后解决);首次 Play 后 7 s 时间线被停止(重新 Play 解决)。发现:示例场景不发布 2D 雷达扫描(params 的局部代价地图两路来源无数据,D0d 记偏差);USD 动画时间线每 ~41 s 循环但仿真时钟不受影响;显存为几次点采样(空场景 3124–3128 MiB、Play 后 5 s 3754 MiB、Nav2 运行时 Isaac 界面显示 3.9 GiB),未做连续测量 |
| D0d · 一次真实 A→B | 完成(2026-09-29 20:13–20:52) | artifacts/d0d/commands.md;run-01/(nav2-launch.log、ready-check-01、map-overview、rviz 截图、usd-inspection);run-01/attempt-01/(goal-202437.txt、result.json、trajectory.csv、bag-info、文本流);run-02/03/04-stoptest(停止路径验证) | 目标 map (-4.0,-1.0,yaw 0) 由 CLI action client 发送:SUCCEEDED、error_code 0、0 次恢复、8.47 s 仿真时间、停稳确认;**AMCL 独立来源**(理想里程计 + USD 出生位姿)在停稳确认时刻误差 0.091 m,AMCL 估计 0.231 m → validation=pass(内部预审后用新分析脚本重算)。发现见 §9 |
| D0 交付 + 独立审查 | 进行中:**待独立审查** | docs/setup.md;docs/review/2026-09-29-d0-handoff.md;docs/review/2026-09-29-d0/REVIEW.md | Codex 第 1 轮两次因账户用量上限中止、无意见(20:59 用 82,531 tokens;23:23 重跑用 102,685 tokens);同一范围已拆成 4 个分片,由排队脚本从 2026-09-30 03:38 起自动运行,见 REVIEW.md;Claude 内部预审第 2 次完成(38 条,确认 35 条),有效项已修复并回归,见 REVIEW.md |
| D1 doctor | 实现与验证完成(2026-09-29 23:3x–23:49),**待独立审查**与用户验收 | 分支 `feature/d1-doctor`;`robosim_eval/doctor*.py`、`configs/baseline.yaml`、`scripts/wsl/doctor.sh`;证据 `artifacts/d1/commands.md` | 固定输入测试 37 passed、改坏检查 7/7、假节点测试 6/6;真实 Isaac:运行时退出 0,用户按 ⏸ 后 2 s 窗口判"不推进"退出 10,恢复后退出 0 |
| D2 单次运行器 | 实现与验证完成(2026-09-30 00:1x–00:47),**待独立审查**与用户验收 | 分支 `feature/d2-runner`;`robosim_eval/runner*.py`、`sim_adapter.py`、`run_io.py`;`scripts/wsl/run_scenario.sh`、`sim.sh`;证据 `artifacts/d2/commands.md` | 固定输入测试 77 passed;运行器假节点测试 8/8;真实 Isaac:正常 A→B reached(真值误差 0.264 m),导航中 SIGINT → 取消、停车、收尾(interrupted);Isaac 由 sim_control 复位、加载场景、读真值,不再需要 GUI 点击 |
| D3 判定与失败处理 | 实现与验证完成(2026-09-30 00:5x–01:29),**待独立审查**与用户验收 | 分支 `feature/d3-verdicts`;`robosim_eval/evaluator.py`、`contacts.py`、`kit/contact_monitor.py`;证据 `artifacts/d3/commands.md`;缺陷记录 `docs/defect-record.md` | 固定输入测试 109 passed;判定模块改坏检查 8/8(含 4 种必做的坏数据);真实 Isaac:正常、绕行、不可达、取消、超时 pass,断流正确判 inconclusive,碰撞抓到轮子与矮箱子的接触判 fail;修复一个运行器缺陷(复位前 odom 残留) |
| D4 批量复跑 | 进行中(01:30 起) | `robosim_eval/batch.py`、`report.py`、`scripts/wsl/run_batch.sh` | 3 个情形 × 3 次 |
| D5 作品交付 | 未开始 | — | — |

**当前任务:** D0 交付收尾(Codex 分片审查排队中 → 逐条核实、修复有效项、重跑受影响检查 → 必要时第二轮复核 → 用户三步验收)与 D1 诊断工具并行。D0 的修复在 `feature/d0-environment` 上做,再合进 `feature/d1-doctor`。

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
| 2026-09-29 | D0 的 Codex 审查拆成 4 个分片排队(`run_codex_review_queue.ps1`);等待期间先做 D1,分支 `feature/d1-doctor` 从 `feature/d0-environment` 分出,D0 的修复之后合进来 | 用户要求加速("赶紧审查下 然后做完");具体做法由 Claude 定 | Codex 额度每个窗口约 10 万 token,两次整轮审查都没读完;分片提示词一律用 `git show 19203e0:<路径>` 读被审版本,不受后续提交影响 |

## 3. 本轮范围

做:D0 剩余部分(D0a→D0d)+ 记录它所需的最小 harness + D0 交付 + Codex 独立审查交接。

不做:D1–D5 及 doctor/runner/recorder/evaluator/report 模块、sim_adapter、网页、persona/LLM/world model、重装 Isaac 或 Ubuntu、换驱动、Pixi/Zenoh 原生路线、mirrored networking、付费服务、push/deploy、删改用户文件、停 Docker、杀用户的 Isaac GUI、`wsl --shutdown`(改变 WSL IP 并影响 docker-desktop;确需时先征得同意)。

## 4. 执行机制(贯穿各阶段)

- 工具调用最多 10 分钟且无 tty:apt、rosdep、clone、colcon 一律后台作业(`setsid nohup bash -c 'bash -l <脚本>; echo $? > <步骤>.exit' < /dev/null > <日志> 2>&1 &`;注意整条命令都要放进后台,旧写法只把 echo 放进了后台),短查询轮询 `.exit`;证据表从 `.exit` 读退出码。
- 所有 sudo 一律 `sudo -n`;若 `sudo -n true` 失败,只给用户一个合并命令块(apt 源 + 全部包 + rosdep init),阶段 2 标"等待用户"。
- WSL 命令从 PowerShell 发出,或以脚本文件方式 `bash -l /mnt/d/RoboSim-Eval/scripts/wsl/<脚本>.sh` 运行,避免 Git Bash 的 MSYS 路径改写;.ps1 用 `powershell -ExecutionPolicy Bypass -File` 运行。
- 用户回合检查点:需要 GUI 的步骤(关闭/重启 Isaac、Load Sample Scene、Play、Pause/Resume、2D Pose Estimate、Nav2 Goal)给出操作与"完成后报告什么",然后结束回合等待;不假装已点过。Windows 侧改动合并成一次重启,并在请用户重启前做完所有无 GUI 的验证。
- 常驻进程:`setsid nohup … < /dev/null`,PID 文件,`kill -INT` 停止并有界等待(SIGKILL 会丢 bag 的 metadata.yaml、留下孤儿节点),停止后 `ros2 node list` 确认无残留;限时观察的退出码 124 记为"观察满时长"。
- 记录格式见 artifacts/README.md;每条命令记 命令 | shell | cwd | 退出码 | 日志。

## 5. 最小组合(harness pack 第 C 步)

1. 已覆盖:计划文档 v2.0 已是规格、验收表和状态合同;Apu 的证据目录与审查门只借方法。
2. 真实缺口:无 Git 基线、无入口文件、无已验证的启动顺序、无证据格式。
3. 补的机制与验证方式:AGENTS.md / CLAUDE.md / docs/plan.md(让 Codex 列出它加载的说明来源与当前任务:已并入审查提示词第 0 步,第 1 轮中止前未输出,**尚未验证**);commands.md 格式(原计划故意记录一条失败命令;实际记录了多条真实失败及其非零退出码,如 `sudo -n true` 1、安装脚本 1、probe 1、stop_nav2 5,另有分析脚本的固定输入测试与改坏检查,见 REVIEW.md);审查交接(第 1 轮因额度中止,**待重跑**)。
4. 暂缓及触发条件:R09 Codex 插件(文件交接 + codex exec 够用;两次交接丢材料再考虑)、R12/R13 规格工具(计划文档已是规格)、R14/R06/C07 Skills/Hooks/CI(同一检查漏两次再上)、R15/R16/R18 多任务调度(D1–D5 出现可并行任务再考虑)、R17 BMAD(单人工具)、C10/C11(无需求)、Obsidian 绑定(见决定记录)。

## 6. 阶段

### 阶段 0 · 唯一计划与入口
- [x] `git init`;.gitignore / .gitattributes;基线提交(三份文档原样)
- [x] 分支 `feature/d0-environment`
- [x] AGENTS.md、CLAUDE.md、docs/plan.md、docs/harness-sources.md、artifacts/README.md、只读探测脚本;提交(c4fa3d8)
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
- [x] D0a:环境记录与现有改动清单;GUI 截图只证明打开。→ docs/environment.md、artifacts/d0a/
- [x] D0b:包可发现、构建成功、launch 参数可查询;命令与退出码。→ artifacts/d0b/commands.md
- [x] D0c:/clock 持续推进;里程计、TF、激光有样本和频率;暂停可识别。→ artifacts/d0c/probe-04-playing/、clock-pause-test-02.txt
- [x] D0d:Nav2 接受并完成目标,轨迹显示移动,到达且停稳;原始证据保留。→ artifacts/d0d/run-01/attempt-01/result.json
- [ ] B7 六项最低交付:环境与依赖版本记录 ✔ / 已验证启动顺序 ✔(docs/setup.md)/ 一次真实 A→B 的记录 ✔ / 最小 diff 说明 ✔(审查包)/ 未验证清单 ✔(§9)/ 独立审查材料 ✔ 但**独立审查尚未完成**(Codex 额度)
- [ ] 用户三步验收:新终端启动看到地图与实时数据;发目标看到达并打开记录核对;暂停看数据停、恢复看数据回来。(待用户)

## 8. 偏差记录
- fastdds.xml 路径:仓库内 `configs/network/` 而非 `D:\robosim-assets\network`(见决定记录)。
- 工作分支:D0 在 `feature/d0-environment`,master 只放基线;审查范围以 docs/review/2026-09-29-d0-handoff.md §1 写明的提交为准。
- Windows 启动脚本将**不**预设 ROS_DISTRO(计划文档 B4 块预设了它):本机 `isaac-sim.bat` 自动调用 `setup_ros_env.bat`,该脚本只在 ROS_DISTRO 未设时才把自带 jazzy 库加入 PATH 与 AMENT_PREFIX_PATH;预设会跳过这一步。脚本只预设 RMW_IMPLEMENTATION=rmw_fastrtps_cpp、ROS_DOMAIN_ID、FASTRTPS_DEFAULT_PROFILES_FILE,并在启动后用 kit 日志核对实际生效值。
- 阶段 2 安装省略了 ROS 文档建议的整体 `apt upgrade`(项目规则:不做无关系统升级);若 apt 因依赖被 hold 而失败,再用 `--with-upgrade` 重跑并记录。
- S6(docs.ros.org)被反爬页拦截,改读计划文档允许的官方托管镜像 repo.test.ros2.org;安装脚本的命令逐条来自该镜像。
- Nav2 用钉住版本的默认参数运行;示例场景不发布 /front_2d_lidar/scan 与 /back_2d_lidar/scan,局部代价地图这两路观测源无数据。D0 首次导航未因此受阻,所以没有改参数;D2 起若要消除,把 params 复制到 configs/nav2/ 并把局部代价地图观测源改为 /scan,用 `params_file:=` 引用。
- 到达核对使用"仿真状态里程计 + USD 出生位姿"作为 AMCL 独立来源(计划文档 A5 要求"用独立位置来源核对"),它不是单独的真值 topic,前提写在 result.json 的 notes 里。
- 首次导航目标由 CLI action client 发送(为拿到原始 result 与 error_code),未用 RViz Nav2 Goal。RViz 路径没有目标转录,分析脚本对它只能给 inconclusive,所以用户验收也用 send_goal.sh。
- 未执行计划文档 B6 第 3 步的 2D Pose Estimate:用户只做了目视贴合核对,AMCL 用参数里的出生点自动初始化。事后交叉核对显示当时 AMCL 初始位姿偏 0.324 m(机器人已缓爬离开出生点),目视没有发现;选目标时的"机器人位置 (-6.14, -1.00)"也是 AMCL 估计。到达判定不依赖 AMCL,所以结论不受影响;以后每次尝试前先重置场景并尽快启动 Nav2,或在 RViz 按真实位置做 2D Pose Estimate。
- 到达判定时刻:从"记录结束时"改为"停稳确认时刻"(内部预审 A6),attempt-01 的独立来源误差因此从 0.090 m 变为 0.091 m。

## 9. 发现、已知问题与未验证清单
**发现(影响后续交付):**
- Nav2 启动时 AMCL 初始位姿偏差 0.324 m:机器人在零指令下缓慢前爬(Play 后 505 s 仿真时间内 0.56 m),而 amcl `set_initial_pose` 固定用出生点。转身时 AMCL 自行重定位,结束时仍偏 0.160 m。→ D2/D4 每次运行前必须重置场景并尽快启动,或按实际位姿设置初始定位。
- /chassis/odom 由 `IsaacComputeOdometry` 计算(仿真底盘状态,相对 Play 起点,无轮速/噪声模型)= 理想里程计。它适合做评测侧的位置核对,但不能证明真实定位鲁棒性(计划文档 A5)。
- 仿真实时因子:空场景约 0.38–0.42,Nav2 运行并导航时约 0.32(attempt-01:8.47 s 仿真 / 25.61 s 现实;bag 中 15.03 s 仿真 / 47.72 s 现实)。按 0.32 计,120 s 仿真时间约需 375 s 现实时间,会先触发 300 s 现实上限;D2 设计超时时要按实测换算。
- 话题频率随实时因子变化:/chassis/odom 每仿真秒约 60 条,空场景约 26 Hz,导航时约 19 Hz;probe-04 中有一个窗口只有 13.9 Hz、最长间隔 0.695 s;attempt-01 中 /clock 与 odom 最长间隔 0.92 s,AMCL 的 map→odom 最长间隔 1.86 s(接近 2 s 断流门槛)。D1 的断流门槛要按各话题实测周期设。
- 零指令缓爬:按位置增量约 1.1 mm/仿真秒(0.045 m @ 40.3 s、0.378 m @ 340.3 s、0.561 m @ 505.5 s);odom twist 读数只有约 0.6 mm/s,偏低约 40%。
- USD 动画时间线每 ~41 s 循环一次(一帧 dt=0 的差速控制器警告),仿真时钟不受影响。
- 首次 Play 后 7 s 时间线曾被停止(topic 在、无数据),重新 Play 恢复。
- D1:rclpy 直接订阅测得点云约 3.0 Hz(artifacts/d1 的 real-01 与 real-02 恢复后),高于 D0 用 `ros2 topic hz` 测的 2.4–2.8 Hz,印证 topic hz 对 540 KB 的大消息读数偏低。
- D1:Isaac 暂停时话题和发布者都还在,只是没有消息;doctor 用"有发布者但 /clock 不推进"判暂停(退出 10),用"没有发布者"判关闭或断连(退出 11)。
- D2:sim_control 复位后用真值核对,机器人回到出生点(-6.001, -1.000),D0 的未验证项"⏹→▶ 回到出生点"由此验证;"出生位姿 + 理想里程计"来源与真值只差约 0.1 mm。
- D2:复位后点云发布者约 1.5–2 s 才重建,头几秒可能只有 0–1 帧;准备阶段的 doctor 对此有限重查(artifacts/d2/repro-doctor-after-reset)。
- D2:AMCL 的 map→odom 在导航中两次出现 2.3–2.5 s 的空档(D0 为 1.86 s),超过 2 s 断流门槛;D3 起把它归为"仅作参考"的数据流,判定必需的是 /clock、odom 与 Isaac 侧 TF。
- D2:Nav2 从启动到就绪 13.3–13.6 s(远低于 60 s 预算);正常通路(6 m,先转 180°)约 15–18 s 仿真时间。
- D3:Isaac 内的 PhysX 接触报告经 Python 执行服务取数可用;复位后机器人只与两个地面碰撞平面接触,由此确定地面过滤规则(artifacts/d3/contact-fetch-after-reset.json)。
- D3:"开头卡住"间歇出现(开接触监视的 3 次正常路线中 2 次),发目标后约 38 s 仿真时间不动,Nav2 恢复后到达;/scan 与正常时相同,机制未查明,见 artifacts/d3/commands.md。
- D3:不可达目标 (-10.05, -1.0) 实测 Nav2 返回 ABORTED、error_code 208,恢复 15 次(离线预测 4 次)。

**已知问题:**
- Nav2 停止时组件容器在清理阶段 SIGSEGV("Magick: abort due to signal 11",exit -6):run-01、run-04、run-05 三次都出现。rviz2 每次退出方式不同:run-01 为 -6,run-04 为 -9(launch 在 SIGINT/SIGTERM 超时后 SIGKILL),run-05 为 -11。launch 退出码 1 只在 run-04、run-05 记录到;run-01 用的是旧脚本,没有记录。三次都没有残留进程,不影响导航与记录。
- attempt-01 是用修复前的记录与停止脚本采集的:没有记录器退出码文件;4 个文本流比 bag 多跑了约 3 分钟,最后手动按会话停止。bag 本身完整,分析只用 bag。
- RViz 在 WSLg 下启动时报一次 GLSL 链接错误(`indexed_8bit_image`),地图与激光照常显示。
- 首次导航的反馈转录 goal-202437.txt 为 2.7 MB(CLI 高频反馈);以后可只保存摘要。

**未验证(D1–D4 范围或待用户):**
- 碰撞/接触(safety_status=unknown)、单独的仿真真值 topic、自动重置、批量运行、取消与超时处理、doctor/runner/evaluator/report 均未实现。
- RViz Nav2 Goal 发目标路径、`record_d0.sh` 以外的记录方式、Heightmap 回退路线未执行。
- "重置场景(⏹ 再 ▶)后机器人回到出生点、里程计归零"没有专门验证过;用户验收时首次执行。
- 修复后的记录、停止、就绪脚本在 run-05-regress 中做了正向与反向回归,但还没有用于一次真实导航尝试;用户验收的那次尝试是修复后脚本的第一次完整使用。
- Codex 独立审查与入口发现验证尚未完成(额度)。
- 只做了一次导航尝试;不据此声称任何导航性能。

## 10. 风险
- 8 GB 显存 + Windows 10:场景可能跑不起来 → Heightmap 缩场景;仍不行则如实记硬件阻塞。
- NAT 下 DDS 发现:主要排障点;先无 GUI 预测试,配置合并成一次重启;3 次/90 分钟预算与五级升级链。
- RViz 在 WSLg 下可能起不来 → 阶段 2 提前测,失败走 CLI 路线并如实标注。
- sudo/管理员、colcon 构建时间、rosdep 网络、10 分钟工具上限(后台作业规避)。
- 总时长粗估半天到一天,并受用户在 GUI 步骤的可用时间影响。

## 11. 下一项:D4 批量复跑与 D5 作品交付
- D4(计划 A4):normal、bypass、unreachable 各 3 次,每次复位并用真值核对;9 次全部留档;静态 HTML 报告按情形分组、失败尝试计入、成功时间只统计到达的运行并注明。
- D5(计划 A4、§D):README 从新终端启动;三个真实操作(正常导航并打开记录、一个失败或取消案例并解释、改一个事先说明的参数并预测、复跑对比);写明哪些来自 NVIDIA/Nav2、哪些自写、哪些由 AI 编写。
- 审查:D0–D3 的 Codex 审查在队列里(03:38 起);D4、D5 完成后加入。
