# Codex 独立审查提示词(D2 第 1 轮分片 round1a:运行器与状态机)

你是本次交付的独立审查者。请对 D:\RoboSim-Eval 的 D2(单次运行器)做只读代码审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `docs/review/codex-review-prompt.md`(默认 Codex 独立审查提示词)。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show db5b161:<路径>` 读取;工作区可能已经在继续开发。
- 先读交接说明 `docs/review/2026-09-30-d2/handoff.md`(工作区中的文件)。
- 只读下面列出的文件和需求段落;不要整份读取 artifacts 下超过 200 行的文件,也不要读 docs/review 下其他目录。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源。
2. 根据 docs/plan.md 写出"当前任务"。

## 被审文件
- `robosim_eval/runner.py`、`robosim_eval/runner_fsm.py`、`robosim_eval/run_io.py`
- `tests/test_runner_fsm.py`、`scripts/wsl/test_runner_fake.sh`、`tests/ros_fake/fake_nav2.py`、`tests/ros_fake/runner_fake.yaml`
- 证据(只定位需要的几行):`artifacts/d2/fake-04/summary.txt`、`artifacts/d2/runs/normal-20260930-004343/events.jsonl`、`artifacts/d2/runs/normal-20260930-004634/events.jsonl`

## 需求
计划书的 A4(D2 一行)、A5(状态合同与超时,停车未确认时中止批次)、A6(每次运行的文件)。

## 审查重点
1. 状态机:转换是否完整、期限是否都能触发、最终执行状态与中止批次的规则是否符合 A5。
2. 运行器:任何异常或中断是否都会走到收尾;是否可能留下 Nav2、记录器或目标在跑;取消与停车确认是否真的观察了终态和速度;信号处理与 rclpy 的配合。
3. 结果合并:result.json 中运行器的结论与分析脚本的结论如何合并,有无把失败写成通过的路径。
4. 测试是否有效:假节点测试能否区分正确与错误的实现;有无遗漏的关键路径。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 db5b161、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
