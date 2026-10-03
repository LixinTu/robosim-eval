# RoboSim Eval

基于现成机器人和 Nav2,做了仿真任务运行、数据记录、异常处理与可复跑评测。

**状态(2026-10-03)**:D0–D5 已实现,并在真实 Isaac 上运行和演示过;独立审查(Codex)与用户验收都还没有完成(11 个审查分片只出了 2 份报告),进度见 [docs/plan.md](docs/plan.md) §1。

**版本 v0.1.0(早期版本)**:这个版本的代码就是产生仓库里全部运行记录(D0–D5 的真实运行、D4 批量、D5 演示)的代码。多代理审查确认的问题正在分支 `fix/review-round1` 上修复(见 [docs/technical-overview.md](docs/technical-overview.md) §16),在真实 Isaac 上复跑通过后再发新版本。文中提到的提交号是改写作者邮箱之前的,对照表见 [docs/commit-map.tsv](docs/commit-map.tsv)。

机器人是 NVIDIA Isaac Sim 6.1 自带的 Nova Carter 仓库场景,导航用 ROS 2 Jazzy 的 Nav2。本项目自己写的是围绕它们的评测工具:运行前诊断、复位场景并用真值核对、发目标、监控超时与中断、确认停车、录制、按固定规则判定、批量复跑、生成报告。机器人控制、定位、路径规划都不是本项目实现的。

本机配置是 Isaac Sim 6.1 官方不支持的(Windows 10、8 GB 显存),仿真约以 0.3 倍实时运行。所有结果都在这个前提下得到。

## 前提

| 项 | 本机情况 | 一次性安装 |
| --- | --- | --- |
| Isaac Sim 6.1.0(Windows) | `D:\isaac-sim-standalone-6.1.0-windows-x86_64` | 官方独立包,解压即可 |
| WSL2 发行版 `Ubuntu`(24.04)+ ROS 2 Jazzy + Nav2 | 已装 | `bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh`(需 sudo) |
| carter_navigation 工作区(钉在 IsaacSim-6.1.0 @ a9e8471) | `~/robotics/vendor/isaac-ros-6.1` | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/setup_workspace.sh` |
| 防火墙:允许 WSL 到 kit.exe 的 UDP | 已建 | 管理员 PowerShell 运行 `powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\allow_wsl_to_isaac_firewall.ps1` |

细节、期望输出和失败时怎么查见 [docs/setup.md](docs/setup.md)。

## 从新终端启动

1. **Windows 普通 PowerShell**:启动 Isaac(打开 ROS 2 bridge、sim_control 仿真控制服务,以及只听本机、要令牌的 Python 执行服务,接触检测要用):

   ```powershell
   powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1 -PythonServer
   ```

   窗口出现并空闲后即可,不需要在 GUI 里点任何东西:运行器发现场景没加载会自己加载 Nova Carter 仓库场景。

2. **另开一个 PowerShell**(以下命令都从 Windows 调 WSL,脚本内部自己加载 ROS 环境):

   ```powershell
   # 诊断:0 正常;10 仿真不推进;11 缺数据;12 频率或新鲜度不够;13 环境不对
   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/doctor.sh --out /mnt/d/RoboSim-Eval/artifacts/d5/demo/doctor
   # 跑一次:复位 -> 真值核对 -> doctor -> 启动 Nav2 -> 录制 -> 发目标 -> 等结果 -> 确认停车 -> 收尾 -> 判定
   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh normal --out /mnt/d/RoboSim-Eval/artifacts/d5/demo/runs
   ```

   Isaac 刚启动、场景还没加载时,doctor 退出 11(没有 `/clock` 发布者),这是对的;`run_scenario.sh` 会先加载场景、复位,再诊断。仿真暂停时 doctor 退出 10。

   一次运行约 2–4 分钟墙钟时间("开头卡住"时约多 2 分钟,见下文已知限制)。最后一行是 JSON:`validation_status` 为 pass / fail / inconclusive;退出码 0 = pass,10 = fail,11 = inconclusive,20 = 被中断并已收尾(在终端按 Ctrl-C 到不了运行器,怎么中断、什么时候不会取消目标见下文已知限制),30 = 运行出错,31 = 取消或停车没能确认(批量会就此中止)。

3. **批量与报告**:

   ```powershell
   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_batch.sh --out /mnt/d/RoboSim-Eval/artifacts/d5/demo
   ```

   默认 normal、bypass、unreachable 各 3 次,交替进行,每次都复位。报告在 `<批次目录>/runs/report.html`,用浏览器直接打开;`summary.json` 是按情形汇总的机器可读数据,不含逐次明细(逐次结果看 report.html 的"All attempts"表或各运行目录的 `result.json`)。

4. **关闭**:运行器自己停 Nav2 和录制器。Isaac 正常关窗口即可。不要让任何工具请求仿真进入 QUITTING 状态。

可用情形(`configs/baseline.yaml`):`normal`、`normal_slow`、`bypass`、`unreachable`、`cancel`、`dropout`、`timeout`、`collision`。后四个是有意注入的故障,配置里有标注。

## 一次运行留下什么

运行目录 `<情形>-<时间>/`:

| 文件 | 内容 |
| --- | --- |
| `result.json` | 四个分项结论(任务结果、安全、数据完整性、执行状态)和总评,每条结论的理由,真值位置,Nav2 原始状态 |
| `events.jsonl` | 每个状态转换和关键事件,带单调时间、墙钟和仿真时间 |
| `trajectory.csv` | 带坐标系与来源标记的轨迹:理想里程计(odom 系)、里程计加出生位姿(map 系,不依赖 AMCL)、AMCL 估计、Nav2 反馈,用 `frame_id` 和 `source` 两列区分;速度只在里程计行 |
| `manifest.json` | git commit、是否有未提交改动、各软件版本、配置/地图/Nav2 参数的 SHA-256 |
| `config.resolved.yaml` | 本次实际使用的完整配置 |
| `nav2_params.yaml` | 只在情形声明了 Nav2 参数改动时出现:由 NVIDIA 原始参数文件派生,只改声明的那一行;作为运行证据随运行目录保存(上游许可证 Apache 2.0) |
| `rosbag/` | 原始 ROS 数据(mcap,不进 Git) |

判定规则见 [docs/setup.md](docs/setup.md) 的"判定与失败处理"一节和 `robosim_eval/evaluator.py`。

## 三个演示

正常导航并打开记录、一个取消案例的解释、一个事先说明的参数变更(DWB 前进速度上限 0.8 → 0.4 m/s)的预测与复跑对比,见 [docs/demo.md](docs/demo.md)。

## 哪些来自哪里

| 来源 | 内容 |
| --- | --- |
| NVIDIA Isaac Sim 6.1 | 仿真器、Nova Carter 机器人与仓库场景、ROS 2 bridge、sim_control 仿真控制服务、Python 执行服务、PhysX 接触报告 |
| NVIDIA carter_navigation(IsaacSim-ros_workspaces) | Nav2 launch、参数文件、地图;本项目不修改它们,参数变更在运行目录里派生 |
| ROS 2 Jazzy、Nav2 1.3 | 定位(AMCL)、全局规划(NavFn)、局部控制(DWB)、恢复行为、NavigateToPose 动作接口 |
| 本项目 | `robosim_eval/`(诊断、仿真控制适配、运行状态机、判定、报告、批量)、`scripts/`(启动、录制、停止、测试脚本)、`configs/`(阈值、情形、障碍物资产)、`tests/`、`docs/` |
| AI | 本项目的代码、脚本、测试和文档由 Claude Code(Anthropic 的 Claude 模型)在用户指挥下编写;独立审查计划由 Codex CLI(OpenAI)以只读方式完成,审查材料和已有报告在 `docs/review/`;截至 2026-10-03,11 个分片中只有 D0 的两个出了报告,其余 9 个受账户额度限制暂停,额度恢复后继续。另做过一轮 Claude 多代理审查,它与编写代码的是同一模型家族,不算独立审查。需求与验收标准来自用户提供的计划文档,关键决定(例如打开 Python 执行服务、在不受支持的配置上继续)由用户做出,记在 [docs/plan.md](docs/plan.md) |

## 测试

```powershell
wsl -d Ubuntu -- python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests      # 固定输入测试,不需要仿真
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_doctor_fake.sh <目录>        # doctor 假节点测试(ROS domain 42)
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/test_runner_fake.sh <目录>        # 运行器假节点测试(假 Nav2)
```

假节点测试用独立的 ROS domain 42,不影响正在运行的 Isaac。

## 已知限制

- v0.1.0 中,在终端里按 Ctrl-C 经 `run_scenario.sh` / `run_batch.sh` 到不了运行器(`timeout` 把它放进了后台进程组,修复在 `fix/review-round1`)。需要中断一次运行时,从另一个终端执行 `wsl -d Ubuntu -- pkill -INT -f robosim_eval.runner`:执行中被中断时,运行器会取消目标、确认停车并收尾,退出码 20。例外:从 Nav2 就绪到目标被接受之间(主要是开始录制的约 4.5 s)被中断时,目标照样发出,之后不取消、也不确认停车,退出码同样是 20,要自己核对机器人已停。
- 审查确认、尚未合入本版本的其他问题见 [docs/technical-overview.md](docs/technical-overview.md) §16.2。
- 仿真约 0.3 倍实时;一次运行的墙钟时间是仿真时间的约 3 倍。
- "开头卡住":部分运行在收到目标后,控制器持续输出最小的原地转向指令(0.7/19 ≈ 0.037 rad/s),机器人对这个指令基本不转。Nav2 的进度检查约每 30 s 墙钟报一次"Failed to make progress",前 3 次之后的恢复都没有解开;第 4 次时 behavior_server 执行原地旋转(1.57 rad),转完之后才正常转向、行驶并到达(Nav2 反馈共计 5 次恢复)。合计约 37 s 仿真时间、约 2 分钟墙钟。它拉长到达时间、增加恢复次数,不影响判定。机制大部分已查明(机器人开头正好背对全局路径,DWB 常选最小转向档,直接实验证实机器人对它不响应),DWB 为什么把这一档打分最高还没查明,见 [docs/defect-record.md](docs/defect-record.md) 与 `artifacts/d4/commands.md`。
- AMCL 的 map→odom 变换间隔常超过 2 s;它只作参考数据流,记为警告,不判数据不完整。
- 接触检测依赖 Python 执行服务;没打开时安全结论是 unknown,不是"没碰撞",验证结论最多 inconclusive(退出 11),不会 pass。
- 到达只判位置(容差 0.5 m,真值来自 Isaac),不判朝向。

## 许可证

本项目的代码和文档采用 MIT 许可证,见 [LICENSE](LICENSE)。取自 NVIDIA 的少量文件(Fast DDS 配置、运行记录里派生的 Nav2 参数文件、报告里嵌入的地图图片)保留 Apache-2.0,见 [NOTICE](NOTICE)。

## 进一步阅读

- [docs/technical-overview.md](docs/technical-overview.md):整体技术说明
- [AGENTS.md](AGENTS.md):仓库地图与规则
- [docs/plan.md](docs/plan.md):进度、决定记录、审查状态
