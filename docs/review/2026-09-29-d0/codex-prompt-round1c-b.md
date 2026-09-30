# Codex 独立审查提示词(第 1 轮分片 round1c-b:常驻进程与退出码)

背景:第 1 轮完整审查两次因账户用量上限中止(round1 用了 82,531 tokens,round1b 用了 102,685 tokens,都没有产出报告)。为在额度内完成,同一范围(基线 `dbf67ce` 到被审版本 `19203e0`)拆成 4 个分片,每片只审一组文件。内部预审的处理记录在 `docs/review/2026-09-29-d0/REVIEW.md`,请独立判断,不要只核对那张表。

你是独立审查者。只读审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `Codex-Harness-Pack-ZH(1).md` 的"默认:Codex 独立审查提示词"。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show 19203e0:<路径>` 读取。工作区可能已有后续提交,不代表被审版本。
- 只读"本片文件"列出的文件和"需求"列出的章节(用 Select-String 或 findstr 定位章节,只读那一段)。
- 不要读 `docs/review/` 下的 task.diff、changed-files.json、*-stderr.txt;不要整份读取 artifacts/ 下超过 200 行的日志,需要证据时只定位几行。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源(例如 AGENTS.md、CLAUDE.md、全局说明)。
2. 根据 docs/plan.md 写出"当前任务"。

## 本片文件(2/4:常驻进程与退出码)
- `scripts/wsl/start_nav2.sh`、`scripts/wsl/stop_nav2.sh`、`scripts/wsl/check_nav2_ready.sh`
- `scripts/wsl/record_d0.sh`、`scripts/wsl/stop_record.sh`
- `scripts/wsl/send_goal.sh`、`scripts/wsl/map_overview.sh`

## 需求
`RoboSim-Eval-Plan-and-Setup-ZH(1).md` 的 §0.2 与 §A7。

## 本片审查重点
1. 退出码是否如实:有没有 `|| true`、被吞掉的错误、把"已启动"当成"通过";`pipefail` 与 `PIPESTATUS` 的用法。
2. 进程归属:是否可能误杀不属于自己的进程(PID 复用、会话判断、命令行匹配);停止升级顺序是否会留下进程。
3. 失败路径:中途失败时是否清理自己启动的东西;残留检查失败时是否报"未知"而不是"无残留"。
4. 竞态:PID 文件、会话 ID 的获取与等待;记录器停止前复制 bag 的可能。
5. `send_goal.sh` 的参数校验、地图空闲检查、超时与转录完整性。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 19203e0、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
