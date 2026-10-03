# Codex 独立审查提示词(D3 第 1 轮分片 round1b:接触监视与 Python 执行服务)

你是本次交付的独立审查者。请对 D:\RoboSim-Eval 的 D3(判定与失败处理)做只读代码审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程,不连接 127.0.0.1:8226。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `docs/review/codex-review-prompt.md`(默认 Codex 独立审查提示词)。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show d33d69c:<路径>` 读取;工作区可能已经在继续开发。
- 先读交接说明 `docs/review/2026-09-30-d3/handoff.md`(工作区中的文件)。
- 只读下面列出的文件和需求段落;不要整份读取 artifacts 下超过 200 行的文件,也不要读 docs/review 下其他目录。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源。
2. 根据 docs/plan.md 写出"当前任务"。

## 被审文件
- `robosim_eval/contacts.py`、`robosim_eval/kit/contact_monitor.py`、`robosim_eval/kit/diag_stage.py`、`scripts/windows/isaac_py.ps1`
- `git diff cfa8245 d33d69c -- scripts/windows/start_isaac_ros2.ps1`,以及 D2 版本的该文件(`git show cfa8245:scripts/windows/start_isaac_ros2.ps1`)
- `configs/assets/low_box.usda`
- 证据(只定位需要的几行):`artifacts/d3/commands.md` 的前 5 行、`artifacts/d3/contact-fetch-after-reset.json`

## 需求
计划书 §0.2(安全与范围);AGENTS.md 硬规则 4;用户在 2026-09-30 决定打开 Python 执行服务(记录在 `artifacts/d2/commands.md` 与启动脚本注释)。

## 审查重点
1. 安全:Python 执行服务是否只监听本机、是否强制令牌;令牌是否可能进入命令行、日志、仓库或输出;客户端的文件白名单能否被绕过(路径大小写、相对路径、链接);失败时是否不泄露令牌。
2. 接触监视:接触报告 API 的挂载范围、事件缓冲的上限与丢弃计数、持续接触只计数的做法是否会漏掉碰撞;安装、清空、取回的时序与运行器是否一致。
3. 过滤规则:地面前缀是否可能把真实碰撞过滤掉;机器人自身接触的判断。
4. WSL 到 Windows 的调用:引号与参数传递、超时、返回值解析是否稳妥。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 d33d69c、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
