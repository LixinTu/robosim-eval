# Codex 独立审查提示词(D2 第 1 轮分片 round1b:仿真控制、配置与脚本)

你是本次交付的独立审查者。请对 D:\RoboSim-Eval 的 D2(单次运行器)做只读代码审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `Codex-Harness-Pack-ZH(1).md` 的"默认:Codex 独立审查提示词"。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show db5b161:<路径>` 读取;工作区可能已经在继续开发。
- 先读交接说明 `docs/review/2026-09-30-d2/handoff.md`(工作区中的文件)。
- 只读下面列出的文件和需求段落;不要整份读取 artifacts 下超过 200 行的文件,也不要读 docs/review 下其他目录。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源。
2. 根据 docs/plan.md 写出"当前任务"。

## 被审文件
- `robosim_eval/sim_adapter.py`、`robosim_eval/sim_math.py`、`robosim_eval/config.py`、`configs/baseline.yaml`、`configs/assets/box_1m.usda`
- `scripts/wsl/sim.sh`、`scripts/wsl/run_scenario.sh`、`tests/test_sim_math.py`、`tests/test_config.py`
- `git diff 293ebf1 db5b161 -- scripts/windows/start_isaac_ros2.ps1 docs/setup.md docs/plan.md AGENTS.md`
- 证据(只定位需要的几行):`artifacts/d2/commands.md`、`artifacts/d2/simctl-03/steps.log`

## 需求
计划书的 A5(配置字段、阈值冻结)、§0.2(安全与范围);AGENTS.md 硬规则 4(不杀用户的 Isaac)。

## 审查重点
1. 护栏:能否请求到退出状态、能否删除机器人或场景;实体名校验是否可被绕过。
2. 服务调用:超时、错误码处理、服务不可用时的退出码;真值位姿的坐标系与时间戳用法。
3. 配置:A5 要求的字段是否齐全,校验是否严格,阈值的依据是否写明。
4. 启动脚本:sim_control 与可选 Python 执行服务的开启方式是否安全(只监听本机、令牌不进命令行与仓库),输出复制是否可能让 Isaac 出错。
5. 文档与证据是否一致。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 db5b161、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
