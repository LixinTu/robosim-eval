# 本机启动、运行与关闭顺序(D0,2026-09-29)

除明确标注"未执行"的步骤外,下列命令都在 2026-09-29 于本机跑通;每条的原始记录与退出码见 `artifacts/d0a..d0d/commands.md`。本机是 Isaac Sim 6.1 官方不支持的配置(Windows 10 + 8 GB 显存),以下只表示"在本机实测可用",不表示普遍可用。

## 一次性前提(已完成,重装时才需要)

| 项目 | 状态 | 怎么做 |
| --- | --- | --- |
| Isaac Sim 6.1.0 | 已装在 `D:\isaac-sim-standalone-6.1.0-windows-x86_64` | 不重装 |
| Windows 防火墙规则 "RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)" | 已建(入站 / UDP / 仅 kit.exe / 仅 vEthernet (WSL)) | 管理员 PowerShell:`powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\allow_wsl_to_isaac_firewall.ps1`(可重复运行;删除见脚本头) |
| WSL `Ubuntu` 内 ROS 2 Jazzy + Nav2 + 依赖闭包 | 已装 | Ubuntu 终端(需 sudo 密码):`bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh` |
| 钉住工作区 `~/robotics/vendor/isaac-ros-6.1`(IsaacSim-6.1.0 @ a9e8471)+ `colcon build --packages-up-to carter_navigation` | 已建 | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/setup_workspace.sh`(可重跑;rosdep 模拟失败时以 7 退出) |
| 安装自检 | PASS | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_ros_install.sh` |
| 分析脚本的固定输入测试(不需要仿真) | 14 passed | `wsl -d Ubuntu -- python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests` |

## 终端约定

| 终端 | 用途 | 环境 |
| --- | --- | --- |
| Windows 普通 PowerShell(非管理员) | 启动 Isaac Sim | 由 `start_isaac_ros2.ps1` 设置:RMW_IMPLEMENTATION=rmw_fastrtps_cpp、ROS_DOMAIN_ID=0、FASTRTPS_DEFAULT_PROFILES_FILE=`D:\RoboSim-Eval\configs\network\fastdds.xml`;**不预设 ROS_DISTRO**(让 isaac-sim.bat 自动调用的 setup_ros_env.bat 加载自带 jazzy 库) |
| WSL Ubuntu(从 PowerShell `wsl -d Ubuntu`,或 Windows 侧直接 `wsl -d Ubuntu -- bash -l <脚本>`) | Nav2、RViz、探测、记录 | 交互终端里先 `source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full`(`--base-only` 只加载 /opt/ros/jazzy)再 `source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh`;各脚本内部已用显式模式自动 source |
| 管理员 PowerShell | 仅防火墙规则 | — |

注意:从 Git Bash 调 `wsl.exe` 时必须用脚本文件(`bash -l /mnt/d/...`),内联命令会被引号/反斜杠改写;从 PowerShell 内联时 `$?` 等会被 PowerShell 先展开。

## 启动顺序

1. **Isaac Sim(Windows,普通 PowerShell)**
   `powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1`
   脚本检查路径与 XML、拒绝在已有 kit.exe 时再开一份,然后带 `--/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge` 启动;窗口保持打开。
   GUI:Window → Examples → Robotics Examples → 左树点 **NAVIGATION** → 右侧卡片 **Nova Carter** → **Load Sample Scene**(资产来自 NVIDIA 服务器,首次约 10 s–数分钟)→ 按 ▶ Play。
   核对(Windows):`powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\check_isaac_bridge.ps1` → 日志应有 "ROS bridge extension isaacsim.ros2.bridge enabled successfully"。
2. **WSL 侧原始数据核对**
   `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/probe_topics.sh /mnt/d/RoboSim-Eval/artifacts/d0c/<目录>`
   期望(空场景):/clock 约 25 Hz 推进、/chassis/odom 约 26 Hz、/tf 约 26 Hz、/front_3d_lidar/lidar_points 约 2.5 Hz、/cmd_vel 有 1 个订阅者(geometry_msgs/Twist)。Nav2 运行时这些频率约降到 19 Hz(仿真变慢,每仿真秒条数不变)。没有 /clock 数据时先看 Isaac 是否在 Play。
3. **重置并启动 Nav2 + RViz(WSL)**
   - 先在 Isaac 按 ⏹ 再按 ▶,让机器人回到出生点、里程计从 0 开始,然后**尽快**启动 Nav2:机器人在零指令下会缓慢前爬(约 1.1 mm/仿真秒),而 AMCL 的初始位姿固定为出生点 (-6, -1, π),拖得越久初始定位偏差越大。首次导航时这一偏差为 0.324 m。(⏹→▶ 能让机器人回到出生点这一点尚未专门验证,用户验收时首次执行;若回不到出生点,改在 RViz 用 2D Pose Estimate 按真实位置初始化。)
   - `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/start_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`(已有 carter_navigation 或 Nav2 节点、或无法检查时拒绝启动,退出 3)
   - 约 25 s 后:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_nav2_ready.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>` → 退出 0 且末行 `verdict: READY`;否则列出未就绪项并退出 1。
   - RViz 窗口(WSLg)显示地图与激光;日志里一条 `indexed_8bit_image.vert` GLSL 错误无害。
4. **一次导航尝试**(每次只用一个目标发送者)
   - 选目标:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/map_overview.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>/map-overview.txt X,Y`(机器人位置是 AMCL 估计),以及 `send_goal.sh <attempt_dir> X Y YAW --check-only`(静态地图空闲核对 + ASCII 局部图)。
   - 记录:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/record_d0.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>/<attempt_dir> 330`
   - 发目标:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/send_goal.sh <attempt_dir> X Y YAW` → 退出 0 = SUCCEEDED;5 = 结束但未成功;6 = 被拒绝;2 = 参数错误;其他 = 动作客户端退出码。结果出来后脚本再等 6 s,让记录覆盖机器人停下的过程。
   - 停止记录:`stop_record.sh <attempt_dir>` → 0 = 所有记录器已停、退出码齐全、bag 已复制且必需话题有数据;3/4/5/6 见脚本头。
   - 汇总:`analyze_attempt.sh <attempt_dir> --goal X Y YAW --spawn -6.0 -1.0 3.141592653589793` → `result.json`、`trajectory.csv`;退出 0 = pass、10 = fail、11 = inconclusive、2 = `--goal` 与实际发出的目标不一致(不写结果)。`--spawn` 是场景 USD 里的出生位姿,用于得到不依赖 AMCL 的位置来源,前提见 result.json 的 `preconditions_for_sim_state_source`。
   - RViz 的 **Nav2 Goal** 也能发目标,但**未执行过**,而且没有目标转录,分析结果最多是 inconclusive;验收请用 send_goal.sh。
5. **暂停/恢复核对**(可选):`watch_clock.sh 120 <文件>` 运行时在 Isaac 按 ⏸ 再按 ▶;文件中会出现一段没有 /clock 消息的空白,空白前后的仿真时间最多相差一个步长(实测 0.017 s)。

## 诊断:doctor(D1)

判断仿真与 ROS 通路是否正常,约 13 s 内一定结束(发现话题最多 5 s,观察 5 s,外加 Python 启停;仿真暂停时约 4 s 就出结论):

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/doctor.sh --out /mnt/d/RoboSim-Eval/artifacts/d1/<目录>
```

| 退出码 | 含义 | 常见原因 |
| --- | --- | --- |
| 0 | 正常,并报告各路实际频率与新鲜度 | — |
| 10 | 仿真不推进 | Isaac 暂停或停止(⏸ / ⏹) |
| 11 | 仿真数据缺失 | Isaac 没开、ROS 2 bridge 没加载、防火墙或 DDS 发现不通、某个必需话题没有发布者 |
| 12 | 数据降级 | 某路数据过慢、陈旧或静默 |
| 13 | 环境或接口不对 | 没加载 ros_env.sh / dds_env.sh、RMW 不是 Fast DDS、话题类型不符 |
| 2 | 用法或配置错误 | 配置文件缺项或数值非法 |
| 124 | 60 s 硬上限触发 | doctor 自身卡住,按失败处理 |

话题与阈值在 `configs/baseline.yaml`,依据是 D0 的实测频率。不需要仿真的检查:`python3 -m pytest tests`(在仓库根目录);假节点测试:`scripts/wsl/test_doctor_fake.sh <目录>`,用 ROS domain 42,不影响正在运行的 Isaac。

## 仿真控制与单次运行(D2)

`start_isaac_ros2.ps1` 默认打开 Isaac 的 sim_control 扩展(ROS 2 simulation_interfaces 服务);加 `-PythonServer` 还会打开只监听本机、需要令牌的 Python 执行服务(D3 接触检测用)。打开后不需要点 GUI:

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh state         # stopped / playing / paused
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh load          # 加载 Nova Carter 场景(约 8 s)
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh play          # 也有 pause、stop、reset、pose、reset-check
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh normal   # 一次完整的 A→B 运行
```

`run_scenario.sh <情形>` 依次:复位场景并用真值核对机器人回到出生点 → doctor → 启动 Nav2 并等就绪 → 开始录制 → 发目标 → 监控超时与中断 → 确认停车 → 停止录制、离线分析、停止 Nav2。Ctrl-C 只会让它取消目标并照常收尾。情形与超时在 `configs/baseline.yaml` 的 `run`、`scenarios` 两节。

每次运行一个目录 `artifacts/d2/runs/<情形>-<时间>/`:manifest.json、config.resolved.yaml、events.jsonl、goal-*.txt、rosbag/、trajectory.csv、result.json,以及各脚本的输出。

| 退出码 | 含义 |
| --- | --- |
| 0 / 10 / 11 | 流程完整;评测结论分别为 pass / fail / inconclusive |
| 20 | 被中断(已取消目标、确认停车并收尾) |
| 30 | 出错(例如复位核验或 doctor 失败、Nav2 没有就绪) |
| 31 | 出错且应中止后续批次(取消或停车没有确认) |
| 2 | 用法或配置错误 |

## 判定与失败处理(D3)

`result.json` 的五个状态字段由 `robosim_eval/evaluator.py` 给出,规则写在模块说明里,要点:

- 到达看 sim_control 真值(不是 AMCL);Nav2 报成功但真值超出 0.5 m 是"虚假成功",判 fail。
- 不可达必须同时满足:情形在配置里预设为不可达并写明离线证据、Nav2 中止或拒绝、真值没到。只有中止记 unknown。
- 安全看 Isaac 内的接触报告(需要用 `start_isaac_ros2.ps1 -PythonServer` 启动 Isaac);没测到就是 unknown,不是"没碰撞"。与两个地面碰撞平面、机器人自身的接触不算碰撞。
- 判定必需的数据是 /clock、odom、Isaac 侧 TF;AMCL 估计只作参考,它的断流只记警告。

情形(`configs/baseline.yaml` 的 `scenarios`):normal、bypass、unreachable,以及故障注入 cancel(发目标 5 s 后取消)、dropout(中途暂停仿真 6 s)、timeout(导航时限压到 6 s)、collision(路上放一个激光看不到的 0.10 m 矮箱子)。

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh collision --out /mnt/d/RoboSim-Eval/artifacts/d3/runs
```

没有 Python 执行服务时加 `--no-contacts`,安全字段会是 unknown。

## 批量复跑与报告(D4)

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_batch.sh      # normal、bypass、unreachable 各 3 次
```

每次尝试都先复位并用真值核对;停车没确认会中止后续批次。结果在 `artifacts/d4/batch-<时间>/`:`batch.json`、`runs/<每次运行>/`、`runs/report.html`(静态页面,双击打开)、`runs/summary.json`。报告只从已保存的记录生成,可单独重建:`python3 -m robosim_eval.report <runs 目录>`。页头列出批次里出现的每个 commit 及其运行次数;"距目标"是真值算的最终距离(不可达情形也有值,不是到达误差);"Nav2 恢复"列能看出开头卡住(见 artifacts/d4/commands.md)。一次批量 9 次约 27 分钟墙钟。

## 关闭顺序

1. `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`:先核对归属(开机 ID、包装进程启动时刻、命令行都要与启动时记录的一致,否则拒绝并以 5 退出),然后 SIGINT 只发给 `ros2 launch`,最多等 45 s,必要时对本会话升级 SIGTERM、SIGKILL;launch 真实退出码写在 `<run_dir>/nav2.exit`;最后用不走 daemon 的 fresh discovery 核对没有残留 Nav2 节点。退出 0 = 无残留;1 = 有残留;3 = 残留检查本身失败。实测 10–13 s 结束;launch 退出码为 1,因为 Nav2 组件容器在清理阶段 SIGSEGV、rviz2 以 -9 或 -11 退出(上游已知问题,见 docs/plan.md §9)。
2. 若有未停的记录器:`stop_record.sh <attempt_dir>`(按会话号 SIGINT → SIGTERM → SIGKILL;各记录器的退出码写在 `<attempt_dir>/<name>.exit`:bag 为 0 或 2,`ros2 topic echo` 为 2,都表示被 SIGINT 正常停止;124 表示到达时长上限)。
3. Isaac Sim:用户在 GUI 按 ⏹ 或 File → Exit;不要从 WSL 或脚本杀 kit.exe。

## 本机实测特性(会影响判读)

- 仿真实时因子:空场景约 0.38–0.42;Nav2 运行并导航时约 0.32。按 0.32 计,120 s 仿真时间约需 375 s 现实时间,会先触发 300 s 现实上限。
- 6.1 的 Nova Carter 示例只发布 3D 点云,不发布 /front_2d_lidar/scan、/back_2d_lidar/scan;钉住 params 的局部代价地图这两路无数据,全局代价地图与 collision_monitor 用的 /scan 由 pointcloud_to_laserscan 转换得到。
- 机器人在零指令下缓慢前爬:按位置增量约 1.1 mm/仿真秒;odom twist 读数只有约 0.6 mm/s。都远低于停稳阈值 0.05 m/s。
- 话题偶有停顿:空场景 odom 曾有 0.695 s 的间隔;导航时 /clock、odom 最长间隔 0.92 s,AMCL 的 map→odom 最长间隔 1.86 s。
- USD 动画时间线每 ~41 s 循环一次,kit 日志出现 "resetting the animation timeline" 与一帧 differential_controller "Invalid deltaTime 0.000000";仿真时钟与物理不受影响(已实测 /clock 单调)。
- 首次 Play 后若手滑按到 ⏹,topic 仍在但没有数据;重新 Play 即可(这也会把场景重置回初始状态)。
- WSL 的 eth0 地址每次 WSL 重启可能变化;防火墙规则按接口而非 IP 限定,不受影响。
