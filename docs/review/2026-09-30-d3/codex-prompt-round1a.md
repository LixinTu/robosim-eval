# Codex 独立审查提示词(D3 第 1 轮分片 round1a:判定规则与运行器接入)

你是本次交付的独立审查者。请对 D:\RoboSim-Eval 的 D3(判定与失败处理)做只读代码审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程,不连接 127.0.0.1:8226。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `docs/review/codex-review-prompt.md`(默认 Codex 独立审查提示词)。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show d33d69c:<路径>` 读取;工作区可能已经在继续开发。
- 先读交接说明 `docs/review/2026-09-30-d3/handoff.md`(工作区中的文件)。
- 只读下面列出的文件和需求段落;不要整份读取 artifacts 下超过 200 行的文件,也不要读 docs/review 下其他目录。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源。
2. 根据 docs/plan.md 写出"当前任务"。

## 被审文件
- `robosim_eval/evaluator.py`、`tests/test_evaluator.py`、`artifacts/d3/mutation_check.py`
- `git diff cfa8245 d33d69c -- robosim_eval/runner.py robosim_eval/runner_fsm.py robosim_eval/config.py tests/test_runner_fsm.py tests/test_config.py configs/baseline.yaml`
- 证据(只定位需要的几行):`artifacts/d3/commands.md`(结果表)、`docs/defect-record.md`

## 需求
计划书 A4 的 D3 一行、A5 的判定规则与必做坏数据测试、A1 的真实缺陷记录。

## 审查重点
1. 判定规则是否符合 A5:到达、超时、碰撞、取消是否真的分开判定;有无把中止当成不可达、把缺接触数据当成安全、把断流当成完整的路径;"与情形预期比较"是否会掩盖问题。
2. 四种坏数据测试是否真的约束住规则;改坏检查是否可信。
3. 运行器接入:注入取消与暂停是否可能让仿真停在暂停状态、让目标留在运行;接触数据取不到时是否如实记为未测量;复位前 odom 的修复是否完整。
4. 缺陷记录与证据是否一致。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 d33d69c、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
