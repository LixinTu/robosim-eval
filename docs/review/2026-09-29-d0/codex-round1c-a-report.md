实际加载的说明来源：会话中的全局指令、用户提供的 AGENTS.md 内容、指定分片提示词、`Codex-Harness-Pack-ZH(1).md` 的独立审查章节，以及 `using-superpowers`、`code-review-excellence` 技能；未单独读取 CLAUDE.md。

根据 `docs/plan.md`，当前任务是完成 D0–D5 的独立审查、核实修复与用户验收；本次仅审查 `19203e0` 的 D0 评测逻辑。

**发现 3 项 Major、2 项 Minor，均已通过内存输入复现。** 以下行号均指提交 `19203e0` 的 [analyze_attempt.py](D:/RoboSim-Eval/scripts/wsl/analyze_attempt.py)。

1. **Major：部分转录缺少目标 ID 时，可能把其他目标的成功判给本次尝试。**  
   位置：`evaluate()`，226–242 行。转录只包含匹配的 `sent_goal`、没有 `goal_id` 时，代码先标记目标已核对，再选 bag 中首个 ACCEPTED/EXECUTING 目标，未增加归属不确定的原因。  
   复现：转录只有新目标的 `send_goal start`；同一 bag 包含另一个目标的接受、成功及停稳数据，位置恰好接近所填目标。实际得到 `completed/reached/complete/pass`，`target_goal.id` 却属于另一个目标。仅有旧 SUCCEEDED 残留不会触发，必须存在其 ACCEPTED/EXECUTING 记录。  
   预期：无法把转录目标与终态绑定时，应为 `inconclusive`。否则，新尝试可能借用旧尝试的成功。建议将坐标核对与目标 ID 归属核对分开；部分转录缺失 ID 时禁止普通通过。  
   分类：**已复现问题**。

2. **Major：评测窗口内完全缺失必需数据，仍可能判为完整并通过。**  
   位置：`stream_integrity()`，201–208 行；`evaluate()`，296–304 行。完整性判断检查整个 bag 的 `count`，没有检查已计算的 `count_in_window`。  
   复现：目标在现实时间 1 秒接受、2 秒成功、3 秒确认停稳；`/clock` 唯一一条消息位于 10 秒。实际得到 `count_in_window=0`、`data_status=complete`、`validation_status=pass`，接受和结果时刻的仿真时间均为 `null`。原因是窗口长度恰为 2 秒，没有超过默认断流阈值。  
   预期：窗口内没有必需时钟证据，应保留 `incomplete/inconclusive`，符合 §A5 的关键数据缺失约束。建议要求窗口内有效样本，并区分数据存在性与断流长度检查。  
   分类：**已复现问题**。

3. **Major：里程计断流后，以陈旧位置作出确定的到达失败判定。**  
   位置：`evaluate()`，264–272、293–318、327–328 行。未观察到停稳时，代码在终态时刻取最后一个历史位置，没有限制其新鲜度；位置超差产生的 `fail` 又优先于数据不足。  
   复现：8 秒收到 SUCCEEDED，其他数据连续，但 odom 在 3 秒停止，最后位置距目标 5 米。实际输出 `data_status=incomplete`、`stop_still=not_observed`，同时以这份早了 5 秒的位置判 `validation_status=fail`。  
   预期：终态位置和停稳情况都缺乏证据，应为 `unknown/incomplete/inconclusive`。当前行为会把记录故障误报为导航失败。建议先验证判卷位置的有效时间范围；仅在证据有效时生成位置超差失败。  
   分类：**已复现问题**。

4. **Minor：TF 合成会使用未来才收到的变换。**  
   位置：`compose_map_base()`，118–125 行。索引从第一个 `map→odom` 开始，没有处理该变换晚于当前 `odom→base_link` 的情况。  
   复现：输入 `map→odom=(接收10秒, x=100)`、`odom→base_link=(接收1秒, x=0)`，输出了“1 秒时 x=100”的合成位置。  
   预期：没有适用的历史变换时，应跳过或标记该位置不可用。当前会污染轨迹和 AMCL 交叉核对；本版本独立到达判定不直接使用此 TF 结果，因此列为 Minor。建议明确时间对齐规则，禁止无标记地向过去套用未来变换。  
   分类：**已复现问题**。

5. **Minor：NaN 朝向可绕过目标核对并得到通过。**  
   位置：`evaluate()`，226–230 行；`main()`，404–413 行。参数接受浮点 `nan`，而 `abs(wrap(NaN)) > 1e-6` 为假。  
   复现：转录目标为 `(0,0,0)`，传入目标 `(0,0,NaN)`，其他数据正常。实际得到 `verified_against_transcript=True`、`validation_status=pass`。  
   预期：无效朝向应作为参数错误拒绝，而非标记已核对；§A5 虽不独立考核朝向，仍要求有效目标朝向。建议检查参数及转录数值的有限性，返回退出码 2，并保持不写结果。  
   分类：**已复现问题**。

[现有测试](D:/RoboSim-Eval/tests/test_analyze_attempt.py)中最重要的缺失用例是：

- 上述部分转录、窗口内零消息、陈旧位置、未来 TF 和非有限数值。
- 120–124 行的“虚假成功”测试同时让所有位置来源偏离目标，不能证明独立位置核对确实有效；应增加“Nav2/AMCL 已到、odom＋spawn 未到”的反例。
- `/clock` 与 odom 分别倒退，以及停稳窗口中的断档、倒退和速度恰等阈值。
- 非零 `error_code`、非空 `error_msg` 原样保留。

实际检查记录如下；shell 均为 Windows PowerShell，cwd 均为 `D:\RoboSim-Eval`，完整命令和输出保留在本会话工具记录中，未创建日志文件。

| 检查 | 执行方式 | 退出码与结果 |
|---|---|---|
| 范围与代码 | `git show 19203e0:<路径>`；限定三文件的 `git diff --stat dbf67ce 19203e0` | 0；三文件均为新增，共 591 行 |
| 现有纯函数测试 | Windows Python `-B`，从 Git 读取后在内存加载并直接调用 | 0；13 项通过 |
| 边界反例 | Python `-B` 内存构造输入 | 0；复现上述问题 |
| `main()` 路径 | mock bag、转录及文件输出，使用 `StringIO` | 验证退出码 0/10/11；目标不匹配返回 2 且无输出写入；bag 不可读返回 1 |
| 停稳与空数据 | 内存固定输入 | 0；等阈值不确认停稳，短窗口、断档、倒退重启及空数据检查符合预期 |

另核对了 `pose_compose()` 的旋转平移与角度归一化，未发现数学错误；`analyze_attempt.sh` 完成静态审查，未执行。

未运行会写临时文件的转录解析测试；未验证真实 rosbag 反序列化、ROS 假节点或 Isaac 集成，未读取可选 `result.json`、其他分片及既有预审处理表。本机属于 **unsupported configuration**，本次固定输入检查不代表集成验收。

审查版本：`19203e0`，基线：`dbf67ce`。未修改任何文件，未启动或停止任何 WSL、Isaac Sim、Nav2 进程。建议由 Claude Code 核实上述发现并补充回归测试后复核。模型：Codex／GPT-6，具体子型号未提供。