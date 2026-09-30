# Codex 独立审查提示词(第 1 轮分片 round1c-d:文档与证据一致性)

背景:第 1 轮完整审查两次因账户用量上限中止(round1 用了 82,531 tokens,round1b 用了 102,685 tokens,都没有产出报告)。为在额度内完成,同一范围(基线 `dbf67ce` 到被审版本 `19203e0`)拆成 4 个分片,每片只审一组文件。内部预审的处理记录在 `docs/review/2026-09-29-d0/REVIEW.md`,请独立判断,不要只核对那张表。

你是独立审查者。只读审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `Codex-Harness-Pack-ZH(1).md` 的"默认:Codex 独立审查提示词"。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show 19203e0:<路径>` 读取。工作区可能已有后续提交,不代表被审版本。
- 只读"本片文件"列出的文件和"需求"列出的章节(用 Select-String 或 findstr 定位章节,只读那一段)。
- 不要读 `docs/review/` 下的 task.diff、changed-files.json、*-stderr.txt;不要整份读取 artifacts/ 下超过 200 行的日志,需要证据时只定位几行。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源(例如 AGENTS.md、CLAUDE.md、全局说明)。
2. 根据 docs/plan.md 写出"当前任务"。

## 本片文件(4/4:文档与证据一致性)
- `docs/setup.md`、`docs/plan.md`(§1、§7、§9)、`docs/environment.md`、`AGENTS.md`
- 核对用证据:`artifacts/d0d/commands.md`、`artifacts/d0c/commands.md`、`artifacts/d0d/run-01/attempt-01/result.json`(只定位需要的几行)

## 需求
`RoboSim-Eval-Plan-and-Setup-ZH(1).md` 的 §B5–§B7 与 §C。

## 本片审查重点
1. 按 `docs/setup.md` 能否从新终端复现启动、运行与关闭;命令和参数是否与脚本实际一致;退出码说明是否完整。
2. `docs/plan.md` 与 `docs/environment.md` 里的数字和结论,能否在所指的证据里找到;有无夸大、遗漏或自相矛盾。
3. 因果解释是否有证据支持(例如停止时的崩溃、launch 退出码、时间线停止的原因)。
4. 未验证项是否都标明了。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 19203e0、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
