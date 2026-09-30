# RoboSim Eval：项目执行计划与 Claude Code 接手说明

版本：v2.0 · 2026-09-29 · 基于现有安装进度修订

目标：用现成机器人与导航系统，交付一套能运行任务、记录数据、检查异常、解释结果并复跑的机器人仿真工具。

本版替换旧版的安装路线。继续使用已经打开的 **Isaac Sim Full 6.1.0**、D 盘安装目录和现有 **Ubuntu 24.04 / WSL2**。不再寻找 Isaac Sim 4.5、不另装 Ubuntu 22.04，也不安排方块掉落等独立练习。下一项成果是现成机器人的一次真实导航。

## 0. 当前进度与接手指令

### 0.1 已完成、已观察与待验证

以下“已观察”来自本次对话中的截图和用户反馈，不代表编写计划时远程执行了检查。Claude Code 接手后补充当前命令输出，不重复安装。

| 项目 | 当前证据 / 状态 | 接下来做什么 |
| --- | --- | --- |
| Isaac Sim | Full 6.1.0 已启动到主界面 | 复用安装，验证机器人场景及 ROS Bridge |
| 安装目录 | `D:\isaac-sim-standalone-6.1.0-windows-x86_64` | 检查目录和启动脚本，不迁移或覆盖 |
| GPU / 显存 | RTX 4070 Laptop GPU，约 8GB 显存 | 测量实际导航场景的显存与运行情况 |
| 内存 | 约 64GB | 记录当前可用内存 |
| 驱动 | 已展示的版本为 591.44 | 重新记录实际版本；没有具体故障不先更换驱动 |
| Windows | 可以运行 Isaac GUI；具体版本和 build 未确认 | 查询 Windows 版本，不能直接写“Windows 11 已通过” |
| WSL | 已有 WSL2，发行版名为 `Ubuntu`；Ubuntu 24.04.4 LTS / noble | 用 `wsl -d Ubuntu` 进入；不另装发行版 |
| Docker | WSL 列表曾显示 `docker-desktop` 正在运行 | 不停止或删除；涉及 WSL 重启时先说明影响 |
| post_install | 曾报权限不足及 `Symlink extension_examples not created.`；后续 GUI 已打开 | 成功修复输出未提供，链接是否正常仍待核对；不把旧错误直接判定为当前阻塞 |
| ROS 2 / Nav2 / RViz | 没有安装成功与运行证据 | 先检测，再只补缺项 |
| Git / VS Code / 项目仓库 | 当前配置与代码进度未核对 | 先检查已有目录、规则文件、Git 状态和未提交改动 |
| 机器人、传感器、导航 | 尚无真实运行证据 | 当前优先任务 D0：完成一次 A→B |
| doctor / runner / evaluator / report | 未核对是否已有实现 | 先查现状，不能宣称不存在，也不能直接重写 |

**进度结论：安装与 GUI 启动已取得进展，D0 仍在进行中。D0 完成不等于 D1–D5 已完成。**

### 0.2 给 Claude Code 的执行指令

请在用户电脑上按本计划继续 RoboSim Eval。先读本节、A2、A4、A7 和 B；其余按当前任务读取。

1. 先确定自己的执行位置是 Windows 还是 WSL，并定位项目仓库。读取现有 `CLAUDE.md`、`AGENTS.md`、计划、启动脚本、测试和 `git status`。保留所有未提交改动。不要把 Isaac Sim 安装目录当成自己的项目仓库。
2. 复用现有安装与代码。将本计划合并进项目唯一的执行计划，写清已完成证据、当前任务与阻塞；不要同时维护多份相互矛盾的计划。常驻说明仅保留约束、入口和真实验证命令。
3. **当前只先完成 D0 剩余部分：ROS 环境检查 → 6.1 对应示例工作区 → Windows/WSL 通信 → Nova Carter 场景 → 一次真实 A→B 导航。** 不先搭大型框架、网页平台、persona 或 world model。
4. 按 B 部分核对真实接口、消息类型、地图和启动参数。常规检查、必要安装、代码修改与验证自行推进；不要每步停下来等批准。需要本机 GUI 操作而你无法执行时，只给用户当前必需的具体操作，并说明完成后检查什么；不要假装已经点过。
5. 只补当前需要的最小开发流程：简短说明、可复用启动方式、实际执行记录。先检查相关工具是否存在，再整理验证入口。不要求在机器人尚未运行时生成整套空模块。
6. 固定输入测试、ROS 假节点测试与真实 Isaac 集成分开。记录命令、工作目录、退出码、日志和未执行项；有超时或进程中断就如实记录。不能用 `|| true`、吞异常、削弱断言或将必要检查设为跳过来制造“通过”。
7. D0 完成后提交本地交付说明，再按顺序做 D1；D0 阻塞时先排查、保存最小复现和证据，不以 mock 代替 D0。常规实现不需要逐步确认；涉及换系统、换安装路线、删除数据、停止其他工作负载时说明具体影响。
8. 沿用现有资源，不新增付费服务、不推送、不部署、不删除或覆盖用户文件。不购买模型 API；此阶段不需要 LLM 参与导航。
9. 交付时给出实际 diff、验证结果、未验证部分、启动方式、关键文件与函数，以及用户可以操作的三步验收。准备可供独立只读审查的材料；确认意见有效后再修复并重跑相关验证。

本次优先交付不是“安装说明写完”，而是“真实导航已经跑通并有证据”；若受硬件或通信阻塞，则准确交付阻塞定位和可复现记录，不能宣称完成。

## A. 项目计划

### A1. 产品目标与首版范围

使用者可以选择一个场景、起点和目标，运行一次导航任务，查看轨迹、任务状态和评测结果，并按保存的条件复跑。

第一版包含：

- 一个 Nova Carter 机器人、一个简单场景、已有地图、一个 A→B 导航任务。
- 激光扫描、机器人位置、速度指令、导航反馈和任务事件记录。
- 目标发送、取消、超时、异常退出、停止确认。
- 到达检查、接触/碰撞检查、数据完整性检查。
- 三种预设场景：正常通路、可以绕行的障碍、不可达目标。
- 单次结果 JSON、轨迹文件、事件记录，以及批量 HTML 报告。
- 一次真实缺陷的复现、修复与同条件复跑记录；没有发现真实缺陷时，明确标注故障注入，不编造缺陷。

后续再加入相机、SLAM、自然语言请求、persona、自动实验 Agent。项目首版不需要模型 API、GPU 租赁或训练服务。

Apu 与本项目使用独立目录和仓库。可以复用记录与验证的方法；暂时不抽象成跨领域框架。

### A2. 当前环境、路径和兼容性边界

| 位置 | 选定软件 / 路径 | 职责与状态 |
| --- | --- | --- |
| Windows | 已安装 Isaac Sim Full 6.1.0 | 机器人、物理、传感器；GUI 已打开 |
| Windows | `D:\isaac-sim-standalone-6.1.0-windows-x86_64` | 保留现有安装 |
| WSL2 `Ubuntu` | 已有 Ubuntu 24.04.4 LTS | 复用发行版，不重装 |
| WSL2 `Ubuntu` | ROS 2 Jazzy、Nav2、RViz2 | 安装情况待查；负责通信与现成导航 |
| WSL2 `Ubuntu` | 系统 Python、Git、colcon、pytest | 按实际依赖补齐，不照旧版锁 Python 3.10 |
| 示例依赖 | `IsaacSim-ros_workspaces` 的 `IsaacSim-6.1.0` 标签 | 使用 `jazzy_ws`，固定并记录实际 commit |
| 通信 | 两侧 ROS 2 Jazzy + Fast DDS | 本计划的 WSL 路线；显式设置 RMW，避免混用默认值 |
| 开发 | 现有 Claude Code / Codex / 编辑器 | 可从 Windows 调用 WSL；不为此重装开发工具 |

**路径约定：**已有项目就复用并将实际位置记录下来。没有项目时建议新建 `D:\RoboSim-Eval`（WSL 为 `/mnt/d/RoboSim-Eval`）。第三方 colcon 工作区建议放在 WSL 的 `~/robotics/vendor/isaac-ros-6.1`，降低跨文件系统编译开销。Windows 侧补充配置可放 `D:\robosim-assets\network`。这些是建议的新目录，不代表已经创建；不迁移现有 WSL 磁盘。

**8GB 显存是需要实测的限制：**6.1 官方最低配置表列出 16GB 显存，本机低于该项要求。空 GUI 能打开并不能证明机器人场景可运行。继续测试一个机器人、必要激光雷达、小场景；记录显存、运行稳定性与仿真速度。资源不足时先按 B5 缩小场景，不承诺一定可用，也不自动降级版本或购买硬件。[S1]

**WSL 路线有明确边界：**6.1 文档仍给出 Ubuntu 24.04 + Jazzy 的 WSL 接法，但 WSL 支持已被标为弃用，Windows 导航为部分支持；WSL 自定义 ROS 接口和 `isaacsim_bringup` 启动仿真器也有限制。当前先复用已有 WSL，用标准消息与导航 action，在 Windows 手动启动 Isaac。官方新推荐的 Windows 原生 Pixi + Jazzy + Zenoh 作为有明确阻塞后的备选，不在本次开工时自动另装一整套。[S2][S3]

Isaac 6.1 Windows 的默认中间件可能是 Zenoh；当前 WSL 方案必须在两侧显式设置 `RMW_IMPLEMENTATION=rmw_fastrtps_cpp`。ROS 库目录是 **`exts\isaacsim.ros2.core\jazzy\lib`**；桥扩展名称仍是 **`isaacsim.ros2.bridge`**。目录和扩展名不要混淆。[S2][S5]

### A3. 最小代码结构

以下是目标结构，不代表已核对本机文件。先检查已有实现，再按当前交付补齐，不批量生成空壳。

| 路径（相对新仓库） | 职责 |
| --- | --- |
| `AGENTS.md` | 简短的公共项目约束、入口和真实验证命令 |
| `CLAUDE.md` | 提醒读取 AGENTS.md 与当前计划，避免复制两套规则 |
| `docs/plan.md` | 本文件的项目执行版本、当前状态与下一项任务 |
| `docs/setup.md` | 本机实际启动方式、终端类型和依赖版本 |
| `docs/environment.md` | 已检测环境、证据位置、未确认项与阻塞 |
| `scripts/` | 当前确有需要的启动与验证入口；Windows/WSL 职责明确 |
| `configs/baseline.yaml` | 场景、目标、主题映射、阈值、超时 |
| `robosim_eval/doctor.py` | 环境、ROS 数据与接口检查 |
| `robosim_eval/runner.py` | 任务状态机、发送目标、取消、收尾 |
| `robosim_eval/recorder.py` | 事件、轨迹和元数据记录 |
| `robosim_eval/evaluator.py` | 固定规则计算结果 |
| `robosim_eval/report.py` | 从已有记录生成报告 |
| `sim_adapter/` | 逐步实现重置、真实位置及接触事件接入 |
| `tests/` | 状态、超时、判定、报告的必要测试 |
| `artifacts/` | 本地运行证据，原始大文件不默认纳入 Git |

先用一个 Python 项目。ROS 包、Web 服务和独立数据库仅在确有需要时增加。HTML 报告可以是本地静态文件，首版不用搭网页控制台。

### A4. 六个可独立验收的交付

| 编号 | 用户操作 | 预期行为 | 验证证据 | 当前状态 |
| --- | --- | --- | --- | --- |
| D0 环境接通 | 启动仿真、打开 RViz、发一个目标 | 机器人移动、到达并停下；真实消息持续更新 | 版本、启动命令、消息样本、action 结果、移动与停稳记录 | 进行中：仅安装与 GUI 已有证据 |
| D1 诊断工具 | 运行 doctor；暂停或关闭仿真后再运行 | 正常时报告真实数据；异常时在有限时间内非零退出 | 正常与异常输出、退出码、消息频率和新鲜度 | 本机实现与完成情况待核对 |
| D2 单次运行 | 用配置运行一次 A→B | 保存接受、反馈、结果与轨迹；中断也收尾 | 单次运行目录、日志、状态机验证 | 本机实现与完成情况待核对 |
| D3 判定与失败处理 | 跑正常、不可达、取消/断流场景 | 到达、超时、碰撞、取消分开判定；停止可验证 | 原始数据、判定理由、必要回归测试 | 本机实现与完成情况待核对 |
| D4 批量与复跑 | 三种场景各重复 3 次 | 每次重置；9 次尝试全部留档与汇总 | 报告、失败案例、配置、版本和重置证据 | 本机实现与完成情况待核对 |
| D5 作品交付 | 按 README 从新终端启动并演示 | 别人能照着运行；用户能定位代码和证据 | README、短演示、diff、审查记录 | 待完成 |

**D0 的剩余工作进一步拆小：**

| 子项 | 操作与预期行为 | 验收方法 |
| --- | --- | --- |
| D0a 记录现状 | 读取现有安装与项目，不重装 | 环境记录与现有改动清单；GUI 截图只证明打开 |
| D0b ROS 与示例依赖 | 复用或补齐 Jazzy，构建对应示例依赖 | 包可发现、构建成功、launch 参数可查询，保存命令和退出码 |
| D0c 场景与通信 | 加载 Nova Carter，Play 后 ROS 收到数据 | `/clock` 持续推进；实际里程计、TF、激光数据有样本和频率 |
| D0d 首次导航 | 在 RViz 定位并给一个可达目标 | Nav2 接受并完成该目标，轨迹显示移动，最终到达且停稳；保留原始证据 |

D0d 不要求提前完成批量框架。可用 ROS 自带工具和短小脚本采集证据；不能只凭机器人截图或 topic 名称就判完成。D0 尚未验证独立真值和接触时，明确“安全与独立评测未验证”，留给 D3。

D0 通过后优先 D1，再 D2。D4 的 9 次运行只是工程试运行，不能据此宣传普遍导航性能。后续扩大实验前先冻结比较配置、条件与指标。

### A5. 状态与结果合同

运行器的基本状态为：准备 → 等待就绪 → 执行 → 必要时取消 → 收尾 → 结束。

等待就绪、接受目标、导航执行、取消确认、停止确认各自有超时。检查取消请求已发出还不够，需要观察目标结束状态和机器人速度。停止未确认时，中止后续批次并留下错误。

每次运行必须分别记录：

| 字段 | 含义与例子 |
| --- | --- |
| `execution_status` | 运行流程是否完整：completed / error / interrupted |
| `task_outcome` | 导航结果：reached / unreachable / timeout / canceled / unknown |
| `safety_status` | 接触规则结果：pass / fail / unknown |
| `data_status` | 必需数据：complete / incomplete |
| `validation_status` | 当前测试预期是否满足：pass / fail / inconclusive |

例如：一个预设不可达目标被验证为不可达、日志完整，导航任务可以是 unreachable，而“不可达目标处理”测试通过。不能把所有拒绝或 aborted 一律解释成不可达：必须保留 Nav2 原始状态、错误码和判定理由；原因不明时用 unknown。实际到达但接触数据丢失，不能写成安全通过。

配置初稿必须含：目标所用坐标系、坐标单位、到达位置容差、朝向是否考核、停稳条件、导航仿真时限、现实等待上限、传感器断流阈值、接触对象过滤规则。具体数值在测量正常频率和场景尺度后确定，并在正式比较前冻结。

首轮调试可从下面的候选值开始；它们是项目起点，不是行业标准。调整必须记录原因，不能跑完后为提高通过率移动门槛。

| 参数 | 首轮候选值 |
| --- | --- |
| 到达位置容差 | 0.5 米，参考点为明确配置的机器人基座坐标系 |
| 朝向检查 | 首轮不纳入独立验收；仍向 Nav2 提供有效目标朝向并记录其配置 |
| 停稳 | 线速度低于 0.05 m/s、角速度低于 0.1 rad/s，持续 1 秒仿真时间 |
| 就绪/目标接受/取消确认 | 分别最多等待 60/10/10 秒现实时间 |
| 导航时限 | 120 秒仿真时间；另有 300 秒现实时间上限 |
| 停止确认 | 取消后最多等待 10 秒现实时间，未停稳就终止批次 |
| 关键数据断流 | 按各主题正常周期配置；初值为 max(5 个正常周期，2 秒现实时间) |

目标坐标必须从实际场景确认，不能把文档示例数字当作可行目标。任务开始时必须验证起点和目标位于允许区域。

以下规则作为首版验收约束：

- 到达既保存 Nav2 结果，也用独立位置来源核对。明确这是仿真真实位置还是导航估计位置。
- 用仿真真实位置判卷时，避免把额外真实位置暗中提供给被测导航。若官方示例使用理想里程计，要如实记录，不能称为已验证真实定位鲁棒性。
- 接触检测过滤地面、允许接触和机器人自身正常接触。未测量不能当零碰撞。
- 同时记录仿真时钟与主机单调时钟；主机时间用于防止暂停/断连后无限等待。
- 日志只有订阅数据，不应与 Nav2 争抢速度控制。停机使用明确的单一控制权方案，不能同时让多个节点不断发相反指令。
- 记录丢失数、缺失区间或完整性标志；缺失关键数据就保留 unknown/incomplete。
- 用固定坏数据验证评测器：虚假成功、缺接触数据、时间倒退、取消无回执，不能被判为普通通过。

### A6. 数据与复跑

每次生成独立 `run_id`。最低保存以下内容：

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 实际软件版本、Git commit、dirty 标志、运行时间、资产/地图/配置摘要、seed |
| `config.resolved.yaml` | 真正生效的参数、起点、目标、障碍布局、主题映射 |
| `events.jsonl` | 带时间的状态转换、目标 ID、异常和取消事件 |
| `trajectory.csv` | 带坐标系和来源标记的机器人轨迹 |
| `result.json` | 分开的运行、任务、安全、数据与验收结果 |
| `rosbag/`（按需） | 实际主题列表中选定的关键数据，限制记录范围 |

`seed` 只是复现信息之一，还需要保存实际随机生成的布局、初始状态、导航参数、地图和资产版本。固定 seed 不承诺多线程物理仿真逐帧一致。

批量开始前验证重置：机器人位姿与速度、障碍物、Nav2 目标、定位状态、代价地图和本轮记录均正确初始化。仿真时钟重置后，不能把上一轮 TF 或反馈归到下一轮。

区分两种操作：回放已有日志用于观察；恢复场景重新导航用于复跑。回放 rosbag 本身不能证明修复后的机器人行为。

失败的尝试保留在总次数中。平均完成时间注明是否仅统计成功任务。不可达场景与正常通路分组报告，不合并成误导性的总成功率。

### A7. AI 开发流程

每个交付都按照：确认现状 → 写清验收 → 最小实现 → 必要测试 → 实际运行 → 检查 diff → 审查与修复。

常驻说明只保留真正的约束与入口；详细文档按任务读取。验证脚本在相关代码和测试存在后建立，不能用一个打印“PASS”的脚本代替检查。

验证至少区分两类：

- 离线测试：固定输入、假 action server 或录制片段，验证状态机与判定规则。
- 仿真集成：真实 Isaac Sim + ROS 2 + Nav2，验证通信、移动、取消与记录。

机器没有启动仿真时，集成验证应显示未执行或失败，不能变成成功。每项验证记录命令、工作目录、退出码与日志位置。常驻进程记录启动状态、观察时段、退出原因和实际退出码，不能把“已启动”写成“测试通过”。通过 tee 保存日志时要保留原命令的失败状态，必要时使用 pipefail；不得吞掉错误。

每项交付最后给出：改了什么、实际 diff、通过/失败/未执行项、启动命令、关键函数，以及你能亲自操作的三步验收。三步验收是产品操作，不安排额外学习作业。

审查材料包含原始需求、验收条件、明确变更范围、代码与测试。审查必须检查实际代码；意见确认有效后再修复。修复后重跑受影响的检查，不为无关改动反复跑全部耗时实验。

保持现有未提交文件；不使用 reset --hard 清理用户工作。首版不推送、不部署、不新增付费服务。默认一个 AI 写代码，另开会话做只读审查即可。审查材料记录基线 commit、当前 diff 与未跟踪文件列表；没有 Git 基线时给出准确文件范围和内容快照，不虚构 commit。对关键代码指出实际文件、函数、状态变化和失败处理，不用泛泛描述替代。

### A8. 后续扩展顺序

1. 明确用户偏好的约束实验：例如请求减速、保留距离。先用虚构需求卡，不根据年龄自动推断需求。
2. 基础导航与接收约束的导航，在同一套事先定义的要求下配对比较。只换评分门槛不构成个性化能力证据。
3. MatrAIx 适配：使用实际接口生成请求或交互情境；逐项验证其输出，不能假定有现成机器人插件。
4. 实验 Agent：把需求变成受校验配置，调用已有工具，引用记录写解释。成功率与碰撞数由程序计算。
5. 新感知/学习模块：只有任务需要时才加相机、SLAM 或模型。结果预测器不自动等于 world model；导航工具交付不自动等于策略训练经验。

## B. 从当前进度继续：先跑通 D0

下面是给本机执行者的步骤。编写计划时没有在用户电脑执行这些命令；每步需由 Claude Code 根据实际输出继续。普通检查与安装缺项可直接推进，涉及管理员操作只在确实需要时使用管理员终端。

### B0. 终端与目录

| 终端 | 进入方式 | 做什么 |
| --- | --- | --- |
| Windows PowerShell | 现有 PowerShell | 检查 Windows、启动本机 Isaac、设置 Windows 侧环境变量 |
| Ubuntu Bash | PowerShell 运行 `wsl -d Ubuntu` | Jazzy、colcon、Nav2、RViz、项目 Python |
| 第二个 Ubuntu Bash | 另开终端，再进入同一 `Ubuntu` | 启动导航或采集数据；每个新终端都加载所需环境 |

不要把 Bash 的 `source/export` 粘到 PowerShell，也不要把 Windows 路径直接当 Linux 路径。长期运行的 Isaac、Nav2 进程单独留终端，避免误开多份。处理已有进程时仅停止自己确认拥有的进程，不清空所有 Python、ROS 或 WSL 进程。

### B1. 补齐环境证据，不重装

Windows PowerShell：

```powershell
Get-CimInstance Win32_OperatingSystem | Select-Object Caption, Version, BuildNumber
nvidia-smi
Get-PSDrive -PSProvider FileSystem | Select-Object Name, Free, Used
wsl --version
wsl --list --verbose
Test-Path 'D:\isaac-sim-standalone-6.1.0-windows-x86_64\isaac-sim.bat'
Test-Path 'D:\isaac-sim-standalone-6.1.0-windows-x86_64\exts\isaacsim.ros2.core\jazzy\lib'
```

Ubuntu Bash：

```bash
cat /etc/os-release
uname -r
python3 --version
git --version
command -v ros2
command -v colcon
ls -ld /opt/ros /opt/ros/jazzy
```

各命令逐条记录结果；命令不存在或路径不存在是待补信息，不能隐藏。先确认当前 shell 是否加载环境；`command -v ros2` 为空不一定表示未安装。检查已有 `/opt/ros/jazzy/setup.bash`、包数据库与项目脚本后再判断。

查看项目目录的规则文件和 `git status --short`。尚无仓库才创建新项目；已有仓库不能重新初始化覆盖。VS Code 缺失不阻塞命令行检查，可按用户已有编辑器继续。

`post_install.bat` 的旧权限错误单独核对：若确实缺少当前需要的链接，再记录并按官方说明执行一次必要修复。不要因为历史报错反复以管理员身份启动整个开发环境。

### B2. ROS 2 Jazzy：只补缺项

1. 若已有 Jazzy，先 `source /opt/ros/jazzy/setup.bash` 并验证包和基本通信。若没有，按 [ROS 官方 Jazzy 的 Ubuntu Deb 安装说明][S6] 配置 **noble / Ubuntu 24.04** 软件源与 `ros2-apt-source`，再安装。不要照旧计划添加 jammy 源。
2. 基础需求为 `ros-jazzy-desktop` 与 `ros-dev-tools`；导航通常需要 `ros-jazzy-navigation2`、`ros-jazzy-nav2-bringup`、`ros-jazzy-nav2-simple-commander`、`ros-jazzy-pointcloud-to-laserscan` 和 `ros-jazzy-rmw-fastrtps-cpp`。先检查 apt 候选版本、已装状态和示例实际依赖，再补缺项，不将此列表视为完整依赖锁文件。
3. 不为了教程执行无关的系统大升级。依赖解析失败先检查源、网络和版本，不能删除 package.xml 中的依赖来强行构建。
4. 使用 Jazzy 自带 talker/listener 做一次有时限的 WSL 内通信检查。它只证明 WSL 内 ROS 通信，不证明已连接 Isaac；保留输出并清理自己启动的测试进程。
5. 第一次 rosdep 配置先检查是否已经初始化；已有配置不重复覆盖。缺什么装什么，真实失败单独记录。

当前路线各 Ubuntu 终端的基础环境：

```bash
source /opt/ros/jazzy/setup.bash
export ROS_DISTRO=jazzy
export RMW_IMPLEMENTATION=rmw_fastrtps_cpp
export ROS_DOMAIN_ID=0
```

先只在当前终端设置，验证通过后再整理可重复的启动脚本；不反复往 `.bashrc` 追加相同或冲突配置。

### B3. 使用 6.1 对应的官方示例工作区

本次核对的官方标签为 `IsaacSim-6.1.0`，其 commit 是：

```text
a9e8471ee901bc2332c1e4aca94ac580713ca3ab
```

接手时记录实际拉取的 commit；如果标签指向发生变化，说明差异，不静默采用不明版本。[S4]

仅在目标目录不存在、且没有可复用的正确版本工作区时执行：

```bash
mkdir -p ~/robotics/vendor
git clone --branch IsaacSim-6.1.0 --depth 1 --recurse-submodules \
  https://github.com/isaac-sim/IsaacSim-ros_workspaces.git \
  ~/robotics/vendor/isaac-ros-6.1
cd ~/robotics/vendor/isaac-ros-6.1
git rev-parse HEAD
git status --short
cd jazzy_ws
source /opt/ros/jazzy/setup.bash
colcon list --packages-up-to carter_navigation
```

已有 checkout 先检查 branch、commit、dirty 和 submodule；不在有用户改动的目录里强制 checkout 或清理。

根据实际 `package.xml` 用 rosdep 解析依赖，并构建 `carter_navigation` 所需的依赖闭包。优先只构建当前需要的包，保留完整依赖；不默认构建无关的整套示例。构建命令和结果必须保存。不要因某个依赖名字包含 bringup 就误用它从 WSL 启动 Windows Isaac。

构建成功后，在该工作区执行：

```bash
source install/setup.bash
ros2 pkg prefix carter_navigation
ros2 launch carter_navigation carter_navigation.launch.xml --show-args
```

**6.1 的启动文件是 `.launch.xml`。** 本次核对的参数包括 `map`、`params_file`、`use_sim_time`。不要沿用旧计划的 `.launch.py`。

默认地图是包内 `maps/carter_warehouse_navigation.yaml`，参数是 `params/carter_navigation_params.yaml`。后续需要修改参数时复制到项目受版本管理的配置中，通过 launch 参数引用；不要静默改第三方工作区的原文件。

### B4. Windows ↔ WSL 的 ROS 通信

先读取现有 WSL 网络模式、Windows build、环境变量和 Fast DDS 配置。复用能够工作的配置；不要先修改全局网络。

- 两端统一 Jazzy、Fast DDS 和 `ROS_DOMAIN_ID`。检查是否残留 `ROS_LOCALHOST_ONLY`、接口白名单、旧 domain 或不同 RMW。
- 按 6.1 官方 WSL 说明设置 Fast DDS UDP 配置。可参考固定版本工作区的 `jazzy_ws/fastdds.xml`；最终使用文件必须通过 XML 解析检查。若整理上游文件，保留许可内容于注释，确保只有一个根元素。
- Windows 路径可用 `D:\robosim-assets\network\fastdds.xml`，WSL 对应 `/mnt/d/robosim-assets/network/fastdds.xml`。该文件需先创建并验证；不是仅设置一个不存在的路径。
- 若采用 mirrored networking，先核对 Windows 与 WSL 版本支持，并保存现有 `.wslconfig`。只改必要项，不覆盖用户其他设置。重启 WSL 会影响运行中的 Docker；确需重启时先处理现有工作。
- 防火墙按必要接口、网络范围和协议最小调整，不能全局关闭；不能把 TCP portproxy 当作 DDS UDP 发现的通用修复。

在全新的普通 Windows PowerShell 中，确认上述配置文件存在后启动：

```powershell
$robosimIsaac = 'D:\isaac-sim-standalone-6.1.0-windows-x86_64'
$robosimDds = 'D:\robosim-assets\network\fastdds.xml'
if (-not (Test-Path "$robosimIsaac\isaac-sim.bat")) { throw 'Isaac 启动文件不存在' }
if (-not (Test-Path "$robosimIsaac\exts\isaacsim.ros2.core\jazzy\lib")) { throw 'Jazzy 库目录不存在' }
if (-not (Test-Path $robosimDds)) { throw 'Fast DDS 配置不存在' }
$env:ROS_DISTRO = 'jazzy'
$env:RMW_IMPLEMENTATION = 'rmw_fastrtps_cpp'
$env:ROS_DOMAIN_ID = '0'
$env:FASTRTPS_DEFAULT_PROFILES_FILE = $robosimDds
$env:PATH = "$env:PATH;$robosimIsaac\exts\isaacsim.ros2.core\jazzy\lib"
& "$robosimIsaac\isaac-sim.bat" --/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge
```

当前 GUI 若已经打开，先保存需要的场景，正常关闭后再按新环境启动，避免打开两份；不能假定运行中的进程会读到后来设置的变量。

WSL 终端在 B2 基础环境和 B3 overlay 之外设置：

```bash
export FASTRTPS_DEFAULT_PROFILES_FILE=/mnt/d/robosim-assets/network/fastdds.xml
test -f "$FASTRTPS_DEFAULT_PROFILES_FILE"
```

若桥扩展加载失败，先保存 Isaac 日志中的第一个相关错误，再检查库目录、RMW 和依赖。以实际消息验证通信，不以“扩展已启用”代替。

### B5. 加载一个 Nova Carter，先看原始数据

根据 6.1 官方导航教程，GUI 入口为：[S3]

1. `Window → Examples → Robotics Examples`。
2. 选择 `ROS2 → Navigation → Nova Carter`。
3. 点击 `Load Sample Scene`，等资源加载完毕后 Play。

优先普通 Nova Carter 示例，不额外切到需要另一套机器人描述配置的 JointStates 变体。不添加多机器人、相机、SLAM 或大型资源包。

Play 后在 WSL 核查实际 topic 名称与类型，再用有时限的订阅确认：

| 检查项 | 要拿到的证据 |
| --- | --- |
| 仿真时钟 | `/clock` 多条时间戳持续前进；暂停时能够识别不再推进 |
| 里程计 | 实际里程计 topic 有新消息、合理 frame 与位姿；记录来源 |
| TF | 机器人、雷达、odom 的关系存在，时间戳与仿真时钟一致 |
| 3D 雷达 | `/front_3d_lidar/lidar_points` 或现场核实后的映射有真实点云 |
| 2D 雷达 | 前后雷达的实际 topic 与参数相符，并有真实扫描数据 |
| 资源 | 场景运行时显存、内存、加载错误与仿真是否持续推进 |

**此时不能因为没有 `/scan` 就直接判桥失败。** 固定版本的导航 launch 会将前方点云转换为 `/scan`，这通常在下一步启动后出现。默认导航参数还使用 `/front_2d_lidar/scan` 与 `/back_2d_lidar/scan`，不能为省显存把导航需要的雷达关掉。[S4]

若仓库示例场景确实因资源不足无法运行，保留 OOM/显存证据后，采用 6.1 官方 Heightmap Importer 路线制作更小的实际导航场景：`Tools → Robotics → Heightmap Importer`，使用匹配的占据地图与 `Nova_Carter_ROS.usd`。核对地图分辨率、原点、场景尺度、碰撞几何、机器人出生点及 `/clock`。不要沿用旧 Block World 菜单或跳去做方块练习。[S7]

资源降到必要范围后仍无法运行，记录硬件阻塞和已尝试措施。不要反复盲改参数，也不把空 GUI 作为通过证据。

### B6. 启动 Nav2，完成一次真实 A→B

从新 Ubuntu 终端加载 B2 环境、B3 overlay 与 B4 的 DDS 配置后：

```bash
ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true
```

该 launch 自带 RViz、Nav2 和点云转扫描。不要同时再启动一套同名 Nav2，也不要启动官方随机目标程序与自己的目标发送器争抢控制。

按顺序检查：

1. 地图加载正常，并与当前场景几何、分辨率、原点对应。`use_sim_time` 对相关节点生效。
2. Nav2 关键生命周期节点进入 active；`/scan`、前后 2D 扫描真实更新。TF 能连通导航需要的 `map → odom → 机器人基座`，不将过期或上一轮 TF 当作就绪。
3. 在 RViz 用 `2D Pose Estimate` 给出与实际出生点一致的初始定位，观察激光与地图匹配。不能任意点一个位置只求节点不报错。
4. 选地图中一个明确可达的近目标，用 RViz 的 Nav2 Goal 工具发出，确认 action 被接受、反馈更新、机器人实际移动。
5. 留存 Nav2 最终结果、目标坐标、实际轨迹或位姿序列、到达误差与停稳记录。仅有“SUCCEEDED”字符串或静止截图不够。消息类型与 topic 映射由实际查询确定，不硬编码速度是 `Twist` 还是 `TwistStamped`。

D0 首次到达可使用已明确来源的里程计/定位信息配合场景观察核对；必须标注其不是独立仿真真值。独立到达判定和接触安全验证在 D3 补齐。

所有等待要有上限。机器人不动时检查目标接受、控制器输出、速度输入映射和仿真 Play 状态；不连续发送新目标掩盖原问题。出现失控、断连或资源错误时执行已明确的停止方式，确认停下后再继续。

### B7. 本次 D0 交付与用户三步验收

最低交付：

- 当前环境与依赖版本记录；官方工作区 commit、地图与资产来源。
- 本机已验证的启动顺序，明确 Windows/WSL、目录、环境变量和关闭方式。
- 一次真实 A→B 的命令/操作记录、消息样本、结果、轨迹或位姿序列、停稳证据；失败尝试也保留。
- 最小代码或配置 diff；若本阶段只补配置，准确说明没有实现完整 runner/evaluator。
- 未验证清单，包括接触、独立真值、自动重置、批量、异常取消等尚未完成项。
- 供独立审查的需求、验收条件、变更范围、相关文件、实际验证记录。

用户亲自验收：

1. 按实际启动说明，从新终端打开 Nova Carter 与 RViz；看到地图和实时数据。
2. 在已验证区域内发一个目标，看到机器人移动、到达并停下；打开对应记录确认目标和结果一致。
3. 暂停仿真，观察时钟/数据不再推进；恢复后确认数据恢复。D0 只展示原始证据；D1 才要求 doctor 自动识别异常并非零退出。

交付结束明确告诉用户：现在在哪里运行、打开哪几个真实文件、下一项是 D1 的哪个小验收。不能把后续 roadmap 写成已实现能力。

## C. 按具体证据排障

| 现象 | 优先检查 | 不采用的捷径 |
| --- | --- | --- |
| GUI 可打开但场景崩溃 | 显存峰值、资源加载、首个错误、必要传感器 | 宣称整机兼容通过；直接要求回退旧版 |
| ROS 命令找不到 | 是否安装 Jazzy、是否 source、终端是否在正确 Ubuntu | 新装另一个 Ubuntu 掩盖环境问题 |
| Bridge 加载失败 | `ros2.core\jazzy\lib`、扩展日志、RMW 与依赖 | 照抄旧 `ros2.bridge\humble\lib` 路径 |
| 两端发现不了节点 | domain、RMW、DDS XML、WSL 网络模式、接口与防火墙 | 关闭全部防火墙；TCP 转发代替 UDP 排障 |
| 有 topic 但无消息 | 发布者、QoS、Play、实际频率与时间戳 | 仅用 `ros2 topic list` 判通过 |
| 原始点云有、`/scan` 无 | 点云转换节点是否已启动、frame、remap 和 QoS | 在 Nav2 launch 前就判桥失败 |
| 找不到导航 launch | overlay 是否 source，包路径、版本，`.launch.xml` | 继续调用旧 `.launch.py` |
| Nav2 启动但不动 | 生命周期、action 接受、地图/初始定位/TF、传感器、速度映射 | 将 goal rejected/aborted 全部叫不可达 |
| RViz 打不开 | WSLg / 图形环境、显示变量、RViz 原始错误 | 把纯离线测试当作界面验证 |
| 取消后仍移动 | 目标状态、单一控制权、实际速度和停止上限 | 只凭 cancel 请求发出就继续下一轮 |
| WSL 路线经定位仍阻塞 | 保存最小复现，与官方限制对照，提出可验证备选 | 未说明影响就切 Pixi、改系统或删环境 |

## D. 最终演示与能力表述

D5 时用三个真实操作展示：正常导航并打开记录；运行一个失败/取消案例并解释原因；改变一个事先说明的参数，预测行为，再复跑对比。

关键代码讲清楚实际入口、任务状态转换、数据记录、失败收尾和评测依据。明确哪些能力来自 NVIDIA / Nav2，哪些工具由自己实现，哪些得到 AI 辅助。

可以表述为：“我基于现成机器人和 Nav2，做了仿真任务运行、数据记录、异常处理与可复跑评测。”只有完成对应交付后才说“做了”。不要把采用现成控制器描述为自己实现了机器人控制或训练了策略。

## E. 本次修订的验证边界与官方资料

### E1. 这次修改了什么

- 保留原来的项目目标、D0–D5、状态合同、数据与复跑要求、开发 harness 和后续 persona/agent 路线。
- 将旧安装路线替换为本机已选择的 Isaac Sim 6.1 + Ubuntu 24.04 + ROS 2 Jazzy。
- 写入实际 D 盘路径、GUI 已打开与尚未证实的项目，避免重复安装或虚报进度。
- 固定 6.1 示例标签及本次核对的 commit，修正 ROS 库路径和 XML launch，调整传感器检查顺序。
- 将 Claude Code 当前任务限定为 D0 剩余部分，提供用户三步验收与排障边界。

### E2. 文档验证与尚未执行项

编写时核对了 NVIDIA 6.1 文档、官方 Git 标签和该版本的 launch、package、导航参数文件；这验证的是计划与已公开接口的一致性。本次文档检查已完成：6 个 Bash 代码块逐个通过 `bash -n`（退出码均为 0）；版本、D 盘路径、工作区标签、引用定义与代码围栏检查通过。PowerShell 未在本环境执行或做语法解析。

**未在用户 Windows/WSL 执行：**软件安装、PowerShell 启动、colcon 构建、ROS 通信、地图加载、机器人导航、性能测量和产品集成测试。文档检查通过不代表 D0 已通过。接手者必须用本机运行证据更新状态。

### E3. 资料入口

[S1]: https://docs.isaacsim.omniverse.nvidia.com/6.1.0/installation/requirements.html
[S2]: https://docs.isaacsim.omniverse.nvidia.com/6.1.0/installation/install_ros.html
[S3]: https://docs.isaacsim.omniverse.nvidia.com/6.1.0/ros2_tutorials/robot_control/tutorial_ros2_navigation.html
[S4]: https://github.com/isaac-sim/IsaacSim-ros_workspaces/tree/IsaacSim-6.1.0
[S5]: https://docs.isaacsim.omniverse.nvidia.com/6.1.0/installation/install_workstation.html
[S6]: https://docs.ros.org/en/jazzy/Installation/Ubuntu-Install-Debs.html
[S7]: https://docs.isaacsim.omniverse.nvidia.com/6.1.0/ros2_tutorials/robot_control/tutorial_ros2_navigation_heightmap.html

- [S1 · Isaac Sim 6.1 硬件与系统要求][S1]
- [S2 · Isaac Sim 6.1 ROS 安装与 WSL 连接][S2]
- [S3 · Isaac Sim 6.1 Nova Carter 导航教程][S3]
- [S4 · 与 6.1 对应的官方 ROS 工作区][S4]
- [S5 · Isaac Sim 6.1 工作站安装与启动][S5]
- [S6 · ROS 2 Jazzy 的 Ubuntu Deb 安装][S6]
- [S7 · Heightmap 导航场景教程][S7]

ROS 官方主站若触发浏览器验证，可参阅 [ROS 官方托管的同页镜像](https://repo.test.ros2.org/en/jazzy/Installation/Ubuntu-Install-Debs.html)；镜像仅作为文档入口，不表示应改装测试软件源。
