# D0 审查记录(review log)

被审范围:第 1 轮原定 `dbf67ce..6365dcb`;第 1 轮中止后延伸到 `dbf67ce..8bce97b`(审查包 `1d5fd48`);内部预审第 2 次审的是 `8bce97b`。修复后的新快照见本文末尾。

## 独立审查(Codex)

| 轮次 | 时间 | 命令 | 模型 / 配置 | 结果 | 证据 |
| --- | --- | --- | --- | --- | --- |
| 第 1 轮 | 2026-09-29 20:57:40 → 20:59:36(116 s) | `codex exec --sandbox read-only -C D:\RoboSim-Eval -o …\codex-round1-report.md "<读取 codex-prompt-round1.md 并执行>"`(由 temp 里的启动器以独立进程运行) | codex-cli 0.157.0;model gpt-6-astra;sandbox read-only;approval on-request;reasoning effort ultra | **未完成,无审查意见**。Codex 读完提示词、交接材料、需求原文、AGENTS.md、docs/plan.md、若干脚本后,下一条只读命令的"自动审批"调用因账户用量上限被拒("You've hit your usage limit … try again at Sep 30th, 2026 12:58 AM"),本轮中止,退出码 1,已用 82,531 tokens;第 0 步入口核对结论未输出 | codex-round1-status.txt、codex-round1-stderr.txt(原始日志)、codex-round1-stdout.txt(空) |

状态:**待独立审查**。不购买额度、不升级套餐(项目规则:不新增付费服务)。额度恢复后按 docs/review/2026-09-29-d0-handoff.md 与本目录的提示词重跑;在此之前,本轮交付不得写成"已通过独立审查"。

重跑方式:`powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\run_codex_review.ps1 -Round <轮次>`,读取本目录 `codex-prompt-<轮次>.md`,输出 `codex-<轮次>-report.md` 与 status/stdout/stderr;status 里记录真实退出码与是否撞到用量上限。

## Claude 内部预审(同模型家族,非独立审查)

四个视角(脚本健壮性、证据与主张、分析正确性、需求与流程合规),每个视角的发现再由一个对抗性核查员逐条复核。

| 次数 | 时间 | 结果 | 证据 |
| --- | --- | --- | --- |
| 第 1 次 | 2026-09-29 20:58 → 21:13(911 s) | **无结果**:4 个查找 agent 全部因 Claude 会话额度上限失败("You've hit your session limit · resets 11pm"),核查阶段未开始;共用约 110 万 token、197 次工具调用 | 工作流 wf_d45189df-159 的 journal(会话目录内,不入库) |
| 第 2 次 | 2026-09-29 21:4x → 21:55(615 s) | **完成**:4 个查找 agent + 4 个对抗核查 agent,共 38 条发现;核查确认 35 条、推翻 2 条(S9、S11)、存疑 1 条(S6);确认后仍为 Major 的 3 条(R2、S3、S4) | 工作流 wf_167105a9-653 的 journal(会话目录内,不入库);逐条处理见下表 |

### 第 2 次内部预审的逐条处理

"严重度"是对抗核查后的结论。实现者对每一条都对照代码或证据复核过;"推翻"的两条同意核查员的理由。

| ID | 严重度 | 问题(简述) | 结论 | 处理 | 验证 |
| --- | --- | --- | --- | --- | --- |
| R2 | Major | 分析脚本不核对实际发出的目标;RViz 路径没有目标记录 | 成立 | analyze_attempt.py 从转录读取发出的目标,与 --goal 不一致时退出 2 且不写结果;没有转录时目标标为未核实,结论最多 inconclusive;setup.md 标明 RViz 路径未执行 | 测试 goal_argument_must_match、without_transcript;反向回归:不一致 → 2,result.json 哈希不变 |
| S3 | Major | stop_record 永远退出 0,SIGTERM 后不复查,可能复制写到一半的 bag | 成立 | SIGINT → SIGTERM → SIGKILL 逐级升级;所有会话结束后才复制 bag;退出码 3/4/5/6 | 正向回归 0;反向回归 bag 缺失 → 5 |
| S4 | Major | send_goal 的退出码与动作客户端无关;YAW 未校验 | 成立 | 先校验 X/Y/YAW 为有限数;转录直接写文件,不经 tee;退出码 0 成功 / 5 未成功 / 6 被拒 / 其他为客户端退出码;结果后等待 6 s | 反向回归:非数字 yaw → 2;真实目标路径待用户验收时首次使用 |
| R1 | Minor | 未做 2D Pose Estimate,台账却写"初始位姿已正确" | 成立 | 更正台账;plan §8 记为偏差;setup.md 要求每次尝试前重置并尽快启动,或按真实位置做 2D Pose Estimate | 文档 |
| R3 | Minor | 记录器"无数据非零退出"未实现 | 成立 | stop_record 检查必需话题条数(无数据 → 6)与 bag 是否存在(→ 5) | 正向与反向回归 |
| R4 | Minor | .err 被忽略;attempt-01 没有记录器退出码 | 成立 | .err 纳入版本管理;台账与 plan §9 写明 attempt-01 的证据缺口 | git status 显示 .err 已跟踪 |
| R5 | Minor | execution_status 输出 A5 之外的值;分析脚本没有固定输入测试 | 成立 | 改用 completed/error/interrupted;新增 14 项固定输入测试 | pytest 14 passed;改坏检查 4/4 被抓住 |
| R6 | Minor | 计划与审查记录的范围、状态互相矛盾 | 成立 | 更新 REVIEW.md 范围、plan 状态行、阶段 0 勾选、§8 范围措辞 | 文档 |
| R7 | Minor | AGENTS.md 的命令与已验证做法不一致(缺 --spawn;Codex 命令不同) | 成立 | AGENTS.md 改为带 --spawn 的分析命令与 run_codex_review.ps1;补充测试命令 | 文档 |
| R8 | Minor | 计划承诺的两项 harness 检查未完成且未标注 | 成立 | plan §5 标明入口发现验证尚未完成(等 Codex);故意失败检查由已记录的真实失败与测试/改坏检查代替 | 文档 |
| R9 | Minor | setup_workspace 在 rosdep 失败时仍打印 "nothing to install" | 成立(潜在) | 记录 rosdep 模拟的退出码,失败即以 7 退出;不再用 `|| true` | 重跑 setup_workspace → 0(日志写到 run-05-regress) |
| A1 | Minor | 状态与反馈不按目标 ID 过滤 | 成立 | 目标 ID 取自转录,否则取录制中第一个被接受的目标;只用该 ID 的状态与反馈;其他 ID 列入结果 | 测试 stale_status_of_an_older_goal;改坏检查 M2 |
| A2 | Minor | 没有 inconclusive;数据缺失被判 fail;录制过短时会误判 | 成立 | 缺停稳窗口、数据不全、无独立来源、目标未核实、中断时给 inconclusive;send_goal 结果后等待 6 s。超时判定属 D3,仍未实现 | 测试 no_terminal、recording_too_short、without_spawn、data_gap |
| A3 | Minor | 数据完整性只看条数;停稳窗口不查断档 | 成立 | 在"接受目标到到达判定"窗口内检查最大现实时间间隔(门槛 2 s)和时间倒退;停稳窗口遇到大于 0.25 s 的断档重新计时 | 测试 data_gap;改坏检查 M4 |
| A4 | Minor | 独立来源的前提没写进 result.json;odom 未标"理想里程计" | 成立 | result.json 增加 preconditions_for_sim_state_source;轨迹与位置来源标为理想里程计 | 重算的 result.json |
| A5 | Minor | usd-inspection 不能单独证明 odom 的来源 | 成立 | inspect_usd.py 打印节点输入、连线与关系目标;新证据 usd-inspection-wiring.txt;交接材料补充引用 | usd-inspection-wiring.txt |
| A6 | Minor | 各来源的"终点"取自不同时刻,到达判定依赖停止录制的时刻 | 成立 | 到达改在停稳确认时刻判定;每个位姿带仿真时间戳;录制结束时的位姿单独列出 | 重算:0.091 m |
| A7 | Minor | 转录解析器不处理被拒;error_msg 存成两个引号 | 成立 | 解析 "Goal was rejected";去掉引号 | 测试 transcript_parser、rejected_goal |
| S1 | Minor | 节点发现失败被当作"没有节点" | 成立 | start_nav2 发现失败即拒绝启动(3);stop_nav2 记 leftover_nodes=unknown 并以 3 退出 | 正向回归 |
| S2 | Minor | stop_nav2 不核对归属 | 成立 | 启动时记录开机 ID 与包装进程启动时刻;停止时开机 ID、启动时刻、命令行都要一致,否则拒绝(5) | 反向回归:外来会话被拒且仍存活 |
| S5 | Minor | check_nav2_ready、diag_discovery 永远退出 0;前者不建目录 | 成立 | check_nav2_ready 建目录并给出就绪判定(0/1);diag_discovery 以 tee 的状态退出 | 正向 READY 0;反向 NOT READY 1 |
| S6 | Minor(存疑) | pid 文件不先删除,固定等待 | 存疑但修复成本低 | 启动前删除旧 pid 文件,改为有上限的轮询;记录会话号前校验为数字 | 正向回归 |
| S7 | Minor | map_overview 的退出码不对 | 成立 | 以渲染步骤的退出码退出 | 反向回归:畸形候选点 → 1 |
| S8 | Minor | ros_env.sh 被无参 source 时读到调用者的参数 | 成立 | 脚本内必须显式传 --full/--base-only,未知参数以 2 拒绝;所有调用处已改 | bash -n;正向回归 |
| S9 | — | 探测脚本会重启 ros2 daemon | 推翻 | 不改:ros2 CLI daemon 是按需重启的用户级缓存,脚本已写明;它不是别的工作负载的进程 | — |
| S10 | Minor | plan 里的后台作业写法只把 echo 放进了后台 | 成立 | 更正写法 | 文档 |
| S11 | — | rosdep 问题被隐藏 | 推翻 | 所述问题不成立(错误会打印);其中误导性提示已按 R9 修复 | — |
| S12 | Minor | 交接材料没说明 attempt-01 用的是修复前的脚本 | 成立 | 交接材料 §5、台账、plan §9 写明 | 文档 |
| E1 | Minor | 显存"峰值"无原始证据且被后来的读数推翻 | 成立 | 改为"几次点采样,未连续测量",列出各次读数与来源 | 文档 |
| E2 | Minor | 实时因子 0.4 是空场景值;导航时约 0.32 | 成立 | 两个值都写明;120 s 仿真 ≈ 375 s 现实,会先触发 300 s 上限 | 文档 |
| E3 | Minor | 停止路径的描述与原始日志不符 | 成立 | 按 run-01/04/05 分别写明退出方式;run-04 行措辞更正 | 文档 |
| E4 | Minor | setup.md 称全部跑通,但重置步骤与 RViz 路径未执行 | 成立 | 首句加限定;两处标"未执行";暂停描述改为"最多差一个步长" | 文档 |
| E5 | Minor | 爬行速度两种说法 | 成立 | 按位置增量 1.1 mm/仿真秒;twist 读数 0.6 mm/s 另注 | 文档 |
| E6 | Minor | 台账时间与原始文件不符 | 成立 | 更正 probe-04 时间与 odom 样本时间 | 文档 |
| E7 | Minor | odom 频率被写成稳定 25.8 Hz | 成立 | 写明窗口范围、0.695 s 间隔、导航时约 19 Hz;D1 门槛按实测设 | 文档 |
| E8 | Minor | 台账引用了不存在的文件 | 成立 | 改为 ready-201532.txt | 文档 |
| E9 | Minor | 独立来源的前提不止两条 | 成立 | 前提列入 result.json 与交接材料 §5;合成 stage 未检查仍列为限制 | 文档 |
| E10 | Minor | 版本号与登录状态只有会话输出 | 成立 | 新增 artifacts/d0a/isaac-version.txt、codex-login-status.txt;plan 状态更新 | 新证据文件 |
