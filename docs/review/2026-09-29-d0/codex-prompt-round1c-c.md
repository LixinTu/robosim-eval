# Codex 独立审查提示词(第 1 轮分片 round1c-c:Windows 侧、环境与安全)

背景:第 1 轮完整审查两次因账户用量上限中止(round1 用了 82,531 tokens,round1b 用了 102,685 tokens,都没有产出报告)。为在额度内完成,同一范围(基线 `dbf67ce` 到被审版本 `19203e0`)拆成 4 个分片,每片只审一组文件。内部预审的处理记录在 `docs/review/2026-09-29-d0/REVIEW.md`,请独立判断,不要只核对那张表。

你是独立审查者。只读审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `docs/review/codex-review-prompt.md`(默认 Codex 独立审查提示词)。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show 19203e0:<路径>` 读取。工作区可能已有后续提交,不代表被审版本。
- 只读"本片文件"列出的文件和"需求"列出的章节(用 Select-String 或 findstr 定位章节,只读那一段)。
- 不要读 `docs/review/` 下的 task.diff、changed-files.json、*-stderr.txt;不要整份读取 artifacts/ 下超过 200 行的日志,需要证据时只定位几行。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源(例如 AGENTS.md、CLAUDE.md、全局说明)。
2. 根据 docs/plan.md 写出"当前任务"。

## 本片文件(3/4:Windows 侧、环境与安装、安全)
- `scripts/windows/start_isaac_ros2.ps1`、`allow_wsl_to_isaac_firewall.ps1`、`check_isaac_bridge.ps1`、`probe_env.ps1`、`run_codex_review.ps1`、`inspect_usd.py`
- `scripts/wsl/ros_env.sh`、`dds_env.sh`、`install_ros2_jazzy.sh`、`setup_workspace.sh`、`probe_env.sh`、`probe_topics.sh`、`diag_discovery.sh`
- `configs/network/fastdds.xml`

## 需求
`docs/reference/RoboSim-Eval-Plan-and-Setup-ZH.md` 的 §0.2 与 §B0–§B4(文件开头注明 §0 与 B 已作废,那是对今后的工作而言;D0 就是按这些章节做的,本片仍以它们为依据)。

## 本片审查重点
1. 防火墙规则的范围是否最小(协议、程序、接口),能否重复运行,有无破坏性操作。
2. 是否修改了第三方工作区、Isaac 安装、用户的 shell 配置或全局系统设置;安装脚本是否做了无关升级。
3. 环境脚本:`set -u` 与 source 的配合、模式参数校验、失败时是否非零返回。
4. 启动脚本:中间件与 DDS 配置是否对 Isaac 子进程生效;重复启动的防护。
5. 有无硬编码的密钥、令牌或越权操作。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 19203e0、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
