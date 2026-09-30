本会话实际加载的项目说明来源：用户消息中提供的 AGENTS.md、指定审查提示词、`docs/plan.md`、需求文档 §0.2/§A7，以及 Harness 文档的“默认：Codex 独立审查提示词”；未另行读取 CLAUDE.md。

根据 `docs/plan.md`，当前任务是完成 D0–D5 独立审查，由实现者核实并修复有效项、重跑受影响检查，再交用户验收；本报告仅覆盖 D0 的 round1c-b 分片。

审查版本为 **`19203e0a83779fc2aa3c464328885d337a63e23c`**，基线为 `dbf67ce`。以下行号均对应冻结版本。发现如下，未修改任何文件。

**1. Major：停止录制仅凭历史 SID 发信号，可能终止无关会话**

位置：[stop_record.sh](D:/RoboSim-Eval/scripts/wsl/stop_record.sh:23)，第 23–34 行。

触发条件：旧 attempt 保留 `record.pids`，原录制已结束，记录的 SID 在进程编号重用或系统重启后属于其他会话，再执行停止命令。

预期仅停止已核实归属的 recorder；实际只用 `pgrep -s` 判断 SID 是否存在，随后向整个会话发送 SIGINT，并可能升级为 SIGTERM、SIGKILL，没有验证启动时间、boot ID 或 attempt 身份。用户其他工作负载可能被终止。

修复方向：保存可靠的进程身份信息，在发信号前验证归属；身份不符或无法确认时拒绝操作。**分类：有代码依据的问题，未实施误杀复现。**

**2. Major：录制异常退出仍可能得到停止成功的退出码 0**

位置：[stop_record.sh](D:/RoboSim-Eval/scripts/wsl/stop_record.sh:41)，第 41–44、63–67 行。

触发条件：某个文本 recorder 因错误退出，`.exit` 内容为 `1` 等异常码，但 bag 可读且必需话题有数据。

预期停止验证应报告录制失败；实际只检查 `.exit` 是否存在，其内容仅被打印。文本文件行数也只展示，不影响 `RC`，最终仍可能返回 0。录制证据缺失或截断会被当作正常完成，违反 §0.2 和 §A7 对错误状态的要求。

修复方向：校验各 recorder 的实际退出码，区分正常结束、明确的主动停止、预期时限及异常退出；空白或非法退出码也应报错。**分类：有代码依据的问题。**

**3. Major：两处管道只保留上游退出码，遗漏转录器失败**

位置：[record_d0.sh](D:/RoboSim-Eval/scripts/wsl/record_d0.sh:55) 第 55 行；[send_goal.sh](D:/RoboSim-Eval/scripts/wsl/send_goal.sh:76) 第 76–85 行。

两处均只读取 `PIPESTATUS[0]`，没有保存 Python 转录器的状态。触发条件是转录器失败，而上游正常结束，或失败后没有继续写入、因而未受到 BrokenPipe 影响。`send_goal.sh` 还不检查结束记录的追加是否成功；若已有 `SUCCEEDED` 文本，仍可能返回 0。

预期应保留原始 client 状态，同时将转录失败作为独立错误报告；实际可能留下不完整证据而没有失败状态。

内存片段已验证：上游退出 0、下游退出 7 时，同样的赋值逻辑得到 `CLIENT_RC=0`。修复应立即保存完整 `PIPESTATUS`，分别记录生产者和转录器状态，并检查首尾记录写入。**分类：有代码依据的问题；退出码丢失机制已复现，未复现真实磁盘故障。**

**4. Major：同一 attempt 再次启动录制会丢失上一轮进程登记**

位置：[record_d0.sh](D:/RoboSim-Eval/scripts/wsl/record_d0.sh:28)，第 28–29、47–56 行。

触发条件：第一轮 recorder 尚在运行时，再次使用相同 `ATT` 启动录制。

预期应拒绝重入；实际先覆盖 `bag-path.txt`、清空 `record.pids`，随后重建同名 PID、退出码及输出文件。第一轮会话仍可能运行，但停止脚本只能看到第二轮登记；两轮 wrapper 也可能写入同一 `.exit` 文件。

用户影响是进程残留、证据覆盖和不同轮次数据混用。修复方向是在任何覆盖操作前取得 attempt 互斥锁并核查状态，活动中的或已有证据的 attempt 应要求使用新目录。**分类：有代码依据的问题。**

**5. Major：PID 登记失败后，停止脚本可能复制仍在写入的 bag**

位置：[record_d0.sh](D:/RoboSim-Eval/scripts/wsl/record_d0.sh:37) 第 37–43 行；[stop_record.sh](D:/RoboSim-Eval/scripts/wsl/stop_record.sh:24) 第 24、35–54 行。

触发条件：wrapper 启动或 PID 写入超过 5 秒，登记为 `MISSING`，但随后实际开始录制。

预期无法确认 recorder 已停止时禁止复制；实际 `pgrep -s MISSING` 的错误被当作“不存在进程”。缺少 `.exit` 只产生 `RC=4`，而复制分支仅拦截 `RC=3`。若未登记的是 bag recorder，仍可能复制正在写入的数据。

这里通常最终返回 4，**并非必然假报成功**；问题是失败路径仍执行不安全复制且留下 recorder。内存片段已验证，`pgrep` 返回 2 时 `alive_any` 返回代表“不存活”的 1。

修复方向：登记失败时清理对应启动任务；严格区分查询无匹配与查询错误，只有确认全部 recorder 停止后才复制。**分类：有代码依据的问题；查询错误被误分类的机制已复现。**

**6. Major：launch 异常退出后，残留 Nav2 子进程无法通过停止脚本清理**

位置：[start_nav2.sh](D:/RoboSim-Eval/scripts/wsl/start_nav2.sh:51) 第 51 行；[stop_nav2.sh](D:/RoboSim-Eval/scripts/wsl/stop_nav2.sh:35) 第 35–42 行。

触发条件：`ros2 launch` 崩溃或被强杀，部分节点仍存活。wrapper 写完 launch 退出码后也退出。

预期应保留足够身份信息，以安全清理自己启动的残留；实际 session 仍有成员，但 `/proc/$WRAP/stat`、`cmdline` 已不存在，归属检查失败，脚本返回 5，无法清理这些节点。残留会占用资源，并可能阻止下一次启动。

修复方向：让 supervisor 存活至所属成员清理完成，或记录可用于验证残留成员的身份信息；不能简单删除归属检查。**分类：有代码依据的问题。**

**7. Major：目标空闲检查与实际加载地图可能不一致**

位置：[send_goal.sh](D:/RoboSim-Eval/scripts/wsl/send_goal.sh:29) 第 29–37 行；[map_overview.sh](D:/RoboSim-Eval/scripts/wsl/map_overview.sh:15) 第 15–23 行；关联 [start_nav2.sh](D:/RoboSim-Eval/scripts/wsl/start_nav2.sh:51) 第 51–52 行。

触发条件：通过启动脚本的额外 launch 参数加载其他地图。

预期目标检查和地图预览使用本次 Nav2 实际加载的地图；实际二者固定读取 vendor 中的 `carter_warehouse_navigation.yaml`。因此可能把实际地图中的障碍区域判为空闲，也可能错误拒绝可用目标；预览还会把当前 TF 位姿绘制到另一张地图上。

修复方向：将本次地图路径及身份写入运行记录，并让目标检查和预览使用同一地图；无法确认一致时明确失败。**分类：有代码依据的问题，未启动替代地图验证。**

**8. Minor：强杀整个 Nav2 session 会同时杀死退出码记录器**

位置：[stop_nav2.sh](D:/RoboSim-Eval/scripts/wsl/stop_nav2.sh:60) 第 60、70–87 行；关联 `start_nav2.sh:51`。

触发条件：launch 本身在 SIGINT、SIGTERM 后仍存活，进入 SIGKILL 分支。

预期记录 launch 的实际退出状态；实际整 session 被强杀，包括负责写 `nav2.exit` 的 wrapper，导致只能记录 `launch_exit=unknown`。无残留时停止脚本仍返回 0，退出码证据不完整。

修复方向：清理时保留能够收集退出状态的 supervisor，记录强制停止原因及真实状态。**分类：有代码依据的问题。**

**9. Minor：负数 `--settle` 通过校验，等待失败被忽略**

位置：[send_goal.sh](D:/RoboSim-Eval/scripts/wsl/send_goal.sh:19)，第 19、80–85 行。

触发条件：传入 `--settle -1`。有限数检查会接受该值，脚本先发送导航目标，随后 `sleep -1` 失败，但执行继续；目标成功时最终仍返回 0。

预期无效等待时间在发目标前被拒绝；实际既发生导航，又缺失要求的停稳录制窗口。内存片段确认 `sleep -1` 返回 1 后控制流继续。

修复方向：验证 settle 非负，并处理等待失败。**分类：有代码依据的问题；等待失败后的继续执行已复现。**

实际执行的检查如下；工作目录均为 `D:\RoboSim-Eval`，日志为本会话工具输出，没有创建日志文件：

| 检查 | Shell | 结果 |
|---|---|---|
| `git rev-parse 19203e0^{commit}`、限定 7 文件的 `git diff --stat dbf67ce 19203e0` | PowerShell | 退出 0；7 文件均为新增，共 501 行 |
| `git show 19203e0:<路径>` 读取全部 7 个脚本 | PowerShell | 退出 0 |
| 冻结代码经 stdin 送入 Windows Git Bash `--noprofile --norc -n` | PowerShell / Git Bash | 7 项均退出 0，仅证明语法可解析 |
| 管道状态、`pgrep` 错误分类、负数等待的内存片段 | Windows Git Bash | 驱动退出 0；观察到上述错误处理结果，不代表产品测试通过 |

未读取其他分片源码、测试、内部预审表或 artifacts 日志；未运行产品脚本、ROS 假节点测试或真实集成验证，未启动或停止 WSL、Isaac Sim、Nav2。真实信号传播、故障时序及磁盘错误仍需实现者在隔离环境中验证。本报告不代表 D0 验收通过。使用模型：Codex（GPT-6，更细型号不可见）。

额外技能说明的读取曾被自动审批拒绝，理由是超出授权范围；未绕过该拒绝，指定审查材料的读取和审查已完成。