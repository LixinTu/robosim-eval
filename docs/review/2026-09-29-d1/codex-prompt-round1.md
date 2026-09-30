# Codex 独立审查提示词(D1 第 1 轮)

你是本次交付的独立审查者。请对 D:\RoboSim-Eval 的 D1(doctor 诊断工具)做只读代码审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `Codex-Harness-Pack-ZH(1).md` 的"默认:Codex 独立审查提示词"。

**额度很紧,请严格控制阅读量:**
- 被审代码一律用 `git -C D:\RoboSim-Eval show c6cbdab:<路径>` 读取。工作区可能已经在别的分支继续开发,不代表被审版本。
- 先读交接说明 `git show c6cbdab:docs/review/2026-09-29-d1/handoff.md`(它随下一个提交入库;如果 c6cbdab 里没有,就读工作区的 `docs/review/2026-09-29-d1/handoff.md`)。
- 只读下面列出的文件和需求段落;不要读 `docs/review/2026-09-29-d0/` 下的大文件,不要整份读取 artifacts 下超过 200 行的文件。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源(例如 AGENTS.md、CLAUDE.md、全局说明)。
2. 根据 docs/plan.md 写出"当前任务"。

## 被审文件
- `robosim_eval/doctor_checks.py`、`robosim_eval/doctor.py`、`robosim_eval/config.py`、`configs/baseline.yaml`
- `scripts/wsl/doctor.sh`、`scripts/wsl/test_doctor_fake.sh`、`scripts/wsl/doctor_watch_pause.sh`
- `tests/test_doctor_checks.py`、`tests/test_config.py`、`tests/ros_fake/fake_isaac.py`、`tests/ros_fake/doctor_fake.yaml`
- 文档中 D1 相关的改动:`git diff 16aef89 c6cbdab -- docs/setup.md docs/plan.md AGENTS.md`
- 证据(只定位需要的几行):`artifacts/d1/commands.md`、`artifacts/d1/fake-03/summary.txt`、`artifacts/d1/real-02-pause/paused/doctor.txt`、`artifacts/d1/real-02-pause/resumed/doctor.txt`

## 需求
`RoboSim-Eval-Plan-and-Setup-ZH(1).md` 的 A3(doctor.py 一行)、A4(D1 一行)、A5(断流规则与主机时间一句);基线提交里 `docs/plan.md` 的 §11:`git show 16aef89:docs/plan.md` 中"## 11."一节。

## 审查重点
1. 判定是否正确:暂停、关闭或断连、降级、环境错误能否被区分;有没有会把异常判成正常(假阴性)或在导航负载下误报(假阳性)的路径;优先级是否合理。
2. 有限时间:所有路径是否都有上限(发现、窗口、提前结束、rclpy 初始化与退出),60 s 硬上限是否真的兜底;时间基准(现实时间与仿真时间)是否用对。
3. 采样实现:QoS 是否与 Isaac 的发布者兼容;订阅与发现的先后;TF 过滤 odom→base_link 的写法;窗口前的样本是否被正确丢弃;异常时 rclpy 是否正确关闭。
4. 退出码与输出:是否如实;配置错误、ROS 环境缺失、内部错误是否各自有明确退出码;JSON 报告是否完整。
5. 测试是否有效:固定输入测试是否真的约束了规则;假节点测试是否只停止自己启动的进程,是否可能与 domain 0 的真实数据混在一起;改坏检查是否可信。
6. 文档与证据:setup.md、plan.md、commands.md 的说法能否在证据里找到。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 c6cbdab、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
