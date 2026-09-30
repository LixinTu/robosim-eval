# AGENTS.md — RoboSim Eval 的地图

> 这是目录,不是百科全书。每轮都进上下文,只放 agent 猜不到又必须知道的东西;细节下沉到 docs/。
> Claude Code 与 Codex 共用这一份;CLAUDE.md 只转发到这里。

## 这是什么

用现成机器人(Nova Carter)与导航系统(ROS 2 Jazzy + Nav2)做机器人仿真评测工具:运行任务、记录数据、检查异常、解释结果、复跑。仿真在 Windows 上的 Isaac Sim 6.1.0,ROS 在 WSL2 的 Ubuntu 24.04。

当前阶段:D0(一次真实 A→B 导航跑通并留证据)。D1–D5 未开始。

## 先读什么

| 问题 | 去哪 |
| --- | --- |
| 现在做到哪、下一步、阻塞、决定记录 | [docs/plan.md](docs/plan.md)(唯一活计划) |
| 需求、验收、状态合同(冻结参考) | [RoboSim-Eval-Plan-and-Setup-ZH(1).md](RoboSim-Eval-Plan-and-Setup-ZH(1).md) 的 §0.2、A4、A5、B |
| 开发流程与审查约定(冻结参考) | [Claude-Code-Harness-Pack-ZH(1).md](Claude-Code-Harness-Pack-ZH(1).md)、[Codex-Harness-Pack-ZH(1).md](Codex-Harness-Pack-ZH(1).md) |
| 本机环境证据 | [docs/environment.md](docs/environment.md)(阶段 1 生成) |
| 已验证的启动/关闭顺序 | [docs/setup.md](docs/setup.md)(验证通过后才存在) |
| 资料台账(读过什么、采用什么) | [docs/harness-sources.md](docs/harness-sources.md) |
| 运行证据与记录格式 | [artifacts/README.md](artifacts/README.md) |
| 审查材料与报告 | docs/review/ |

优先级:根目录三份 ZH 文档是 2026-09-29 冻结的需求参考,它们里面的"当前状态"列已作废;状态只看 docs/plan.md。文件名保留下载时的 "(1)" 后缀,引用时写真实路径。

## 跑起来(2026-09-29 本机实测;完整顺序与期望值见 docs/setup.md)

```powershell
# Windows 普通 PowerShell:启动 Isaac Sim + ROS 2 bridge(然后在 GUI 加载 Nova Carter 示例并 Play)
powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1
powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\check_isaac_bridge.ps1   # bridge 是否加载、显存
# WSL(从 Windows 调用;脚本内部自动 source ros_env.sh + dds_env.sh)
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_ros_install.sh                    # 安装自检,PASS/FAIL
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/probe_topics.sh <out_dir>                # Isaac 数据是否到达(/clock 等)
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/start_nav2.sh <run_dir>                  # Nav2 + RViz,独立进程组
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_nav2_ready.sh <run_dir>            # 就绪判定:0 READY / 1 NOT READY
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/record_d0.sh <attempt_dir> 330           # bag + 文本流
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/send_goal.sh <attempt_dir> X Y YAW       # 地图空闲核对 + 发一个目标;0 = SUCCEEDED
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_record.sh <attempt_dir>             # 0 = 已停、bag 完整、必需话题有数据
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/analyze_attempt.sh <attempt_dir> --goal X Y YAW --spawn -6.0 -1.0 3.141592653589793   # 0 pass / 10 fail / 11 inconclusive
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh <run_dir>                   # 先核对归属;0 = 无残留
wsl -d Ubuntu -- python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests              # 分析脚本固定输入测试(不需要仿真)
```

每次导航尝试前先在 Isaac 按 ⏹ 再按 ▶ 重置场景,然后尽快启动 Nav2(原因见 docs/setup.md)。

一次性安装(需 sudo 密码,用户在 Ubuntu 终端运行):`bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh`,然后 `setup_workspace.sh`;防火墙规则(管理员):`scripts\windows\allow_wsl_to_isaac_firewall.ps1`。

## 硬规则(来自计划文档 §0.2 与两份 harness pack)

1. 只做当前计划中最靠前的小交付;不先搭框架、网页、persona、world model。
2. 复用现有安装:Isaac Sim 6.1.0 在 `D:\isaac-sim-standalone-6.1.0-windows-x86_64`;WSL 发行版名为 `Ubuntu`。不重装、不换驱动、不迁移。
3. 本机是 6.1 官方不支持的配置(Windows 10 + 8 GB 显存);用户已决定先做完项目再升级。所有记录标注 unsupported configuration,不承诺可用,不再提议升级。
4. 不新增付费服务,不 push,不部署,不删除或覆盖用户文件,不停止 Docker Desktop,不杀用户自己开的 Isaac GUI,不 `wsl --shutdown`(会影响 docker-desktop 并改变 WSL IP;确需时先说明并征得同意)。
5. 证据即事实:每条验证记录 命令 | shell | cwd | 退出码 | 日志;常驻进程记 启动、观察时段、停止方式、退出码、退出原因。不用 `|| true`、不吞异常、不削弱断言、不把"已启动"写成"通过";用 tee 必须配 pipefail。`timeout` 的退出码 124 记为"观察满时长"。
6. 固定输入测试、ROS 假节点测试、真实 Isaac 集成分开记录;没开仿真时集成验证必须显示未执行或失败。产品证据(artifacts/)与过程证据(docs/review/)分开存放,互不推导。
7. 需要 GUI 操作时只给用户当前必需的步骤并说明完成后检查什么;不假装已点过。Windows 侧每次改动都意味着用户要重启 Isaac,所以先做完无 GUI 的验证再请用户重启。
8. 第三方工作区(WSL 的 `~/robotics/vendor/isaac-ros-6.1`)不改原文件;改参数复制到 configs/ 并通过 launch 参数引用。
9. Nav2 的 rejected/aborted 记 unknown 而非 unreachable,保留原始状态码与 error_code;位置来源必须标注(里程计 / 定位估计 / 仿真真值)。
10. 消息类型、topic、action 映射由实际查询确定(`ros2 topic list -t`、`ros2 topic info -v`、`ros2 action list -t`),不硬编码。

## 审查门

默认:Claude Code 主实现 → Codex 新会话只读审查 → Claude Code 逐条核实、只修有效项、重跑受影响检查 → Codex 复核修复后的范围。最多两轮。"无发现"不等于验收通过;Codex 不可用时标"待独立审查",不伪造跨模型审查。审查前先提交并冻结,审查期间不改动源码。

只读审查的实际运行方式(codex-cli 0.157.0;内部执行 `codex exec --sandbox read-only -C D:\RoboSim-Eval -o <报告>`,短提示词让 Codex 去读 UTF-8 提示词文件,避免 PowerShell 5.1 管道改写中文;记录真实退出码与是否撞到用量上限):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\run_codex_review.ps1 -Round <轮次>   # 读 docs/review/2026-09-29-d0/codex-prompt-<轮次>.md
```

审查材料与报告放在 docs/review/;提示词模板是 Codex-Harness-Pack-ZH(1).md 的"默认:Codex 独立审查提示词"。

## 什么要问人

- 影响费用、数据、不可逆操作的事:重启 WSL、防火墙规则、需要密码的 sudo 安装块、删除或搬迁文件。
- 官方路线与计划文档冲突需要取舍时(例如 `netsh portproxy`)。
- 换系统、换安装路线、放弃 WSL 路线。

## 其他

- 本仓库纯本地、无 remote;不要建议或执行 `git push`。
- Conventional Commits;小步提交,每步可独立验证与回退。`master` = 基线,`feature/*` = 当前交付。
- 回复用户用中文;技术名词保留英文;项目文档用中文。
