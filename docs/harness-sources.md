# 资料台账(harness pack 第 B 步)

阅读状态取值:`全文(主会话)` = 主会话读了原文全文;`摘录(WebFetch,主会话)` = 主会话通过 WebFetch 拿到模型摘录,不等于读了全文;`摘录(子agent)` = 子 agent 返回的摘录;`仅入口页`;`未读`;`不可访问(原因)`。只有主会话写这个文件。

## 项目文档

| 来源 | 实际读到的页面/章节 | 阅读状态 | 用途 | 日期 |
| --- | --- | --- | --- | --- |
| RoboSim-Eval-Plan-and-Setup-ZH(1).md | 全部 499 行 | 全文(主会话) | 需求、验收、状态合同、D0 步骤 | 2026-09-29 |
| Claude-Code-Harness-Pack-ZH(1).md | 全部 | 全文(主会话) | 开发流程、审查分工、交付七项 | 2026-09-29 |
| Codex-Harness-Pack-ZH(1).md | 全部 447 行 | 全文(主会话) | Codex 审查提示词、C01–C15、审查约定 | 2026-09-29 |
| Apu 项目 AGENTS.md / CLAUDE.md / docs/references/harness-engineering.md / docs/evidence 目录 | 全部 | 全文(主会话) | 借用地图式 AGENTS.md、证据目录、codex exec 审查门 | 2026-09-29 |

## S 系列(Isaac Sim 6.1 / ROS 官方,直接决定 D0)

| 编号 | 来源 | 实际读到的内容 | 阅读状态 | 能解决的项目问题 | 采用 / 暂缓 / 不适用 | 依据与未读部分 | 日期 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| S1 | 6.1 requirements | 支持的 OS(仅 Windows 11,"Windows 10 is not supported")、显存最低 16 GB、RAM 32 GB、驱动 595.97 | 摘录(WebFetch,主会话) | 本机是否受支持 | 采用:记录为 unsupported configuration | 未读页面其余部分 | 2026-09-29 |
| S2 | 6.1 install_ros(Windows / WSL2 / Pixi) | WSL2 路线 deprecated、要求 Windows 11;env vars(ROS_DISTRO、RMW_IMPLEMENTATION=rmw_fastrtps_cpp、PATH 加 jazzy lib);启动参数 `--/isaac/startup/ros_bridge_extension=isaacsim.ros2.bridge`;fastdds.xml(UDPv4-only)与 FASTRTPS_DEFAULT_PROFILES_FILE;`netsh interface portproxy` 7400/7410/9387;Pixi + Zenoh 为推荐原生路线 | 摘录(WebFetch,主会话,两次) | 桥接配置与启动方式 | 采用 env vars、XML、启动参数;portproxy 仅作升级链最后一步;Pixi 暂缓(用户选 WSL 路线) | 阶段 3 前主会话读全文 | 2026-09-29 |
| S3 | 6.1 Nova Carter 导航教程 | 菜单路径 Window > Examples > Robotics Examples > ROS2 > Navigation > Nova Carter > Load Sample Scene;topic /tf /odom /map /point_cloud /scan;`ros2 launch carter_navigation carter_navigation.launch.xml`;RViz 2D Pose Estimate / Navigation2 Goal;初始位姿由 params 定义;WSL 部分支持、RViz2 可能打不开 | 摘录(WebFetch,主会话) | 场景加载与导航步骤 | 采用 | 阶段 3 前主会话读全文;topic 名以实际查询为准 | 2026-09-29 |
| S4 | IsaacSim-ros_workspaces @ IsaacSim-6.1.0 | 目录 dockerfiles / humble_ws / jazzy_ws;raw 文件 jazzy_ws/fastdds.xml(UDPv4-only,Apache-2.0)与 jazzy_ws/src/navigation/carter_navigation/launch/carter_navigation.launch.xml(参数 map、params_file、use_sim_time;RViz、nav2 bringup、pointcloud_to_laserscan → /scan) | 摘录(WebFetch,主会话) | 工作区版本与 launch 参数 | 采用钉住标签;commit 在克隆时用 `git rev-parse` 核对 | 标签 commit 页面上不可见 | 2026-09-29 |
| S5 | 6.1 workstation 安装 | — | 未读 | post_install 链接修复时参考 | 按需 | — | — |
| S6 | ROS 2 Jazzy Ubuntu Deb 安装 | docs.ros.org 主站返回 Anubis "Access Denied" 反爬页;改读官方托管镜像 repo.test.ros2.org 同页:locale、universe、ros2-apt-source .deb(GitHub API 取最新 tag)、`apt install ros-dev-tools` / `ros-jazzy-desktop`、`source /opt/ros/jazzy/setup.bash`、talker/listener 示例;"Deb packages for ROS 2 Jazzy Jalisco are currently available for Ubuntu Noble (24.04)";建议安装前 `apt upgrade` | 主站:不可访问(反爬);镜像:摘录(WebFetch,主会话) | WSL 内安装 Jazzy(D0a 证实未安装) | 采用:scripts/wsl/install_ros2_jazzy.sh 逐条照抄;省略整体 upgrade(见 plan.md 偏差记录) | 镜像仅作文档入口,不改软件源 | 2026-09-29 |
| S7 | Heightmap 导航场景教程 | — | 未读 | 8 GB 显存跑不动示例场景时的回退 | 仅回退时读 | — | — |

## R 系列(通用 harness 资料)

| 编号 | 来源 | 阅读状态 | 采用 / 暂缓 / 不适用 | 依据 |
| --- | --- | --- | --- | --- |
| R01 OpenAI Harness engineering | 未读(Apu 项目已有存档摘要 docs/references/harness-engineering.md,主会话读过该存档) | 已采用其"AGENTS.md 是地图"原则 | 存档非原文 |
| R02 Anthropic long-running agents | 未读 | 暂缓 | 阶段 5 前读入口页 |
| R03 Claude Code Best Practices | 未读 | 暂缓 | 阶段 5 前读入口页 |
| R04 Codex AGENTS.md | 未读 | 暂缓 | 与 C02 相同页面 |
| R05 Claude Code Common Workflows | 未读 | 暂缓 | 阶段 5 前读入口页 |
| R06 Claude Code Hooks | 未读 | 暂缓(同一检查漏两次再上) | — |
| R07 Anthropic harness design | 未读 | 暂缓 | — |
| R08 Codex Code Review | 未读 | 阶段 5 前读全文(与 C05 相同) | 决定审查范围 |
| R09 Codex plugin for Claude Code | 未读 | 暂缓(文件交接 + codex exec 够用) | 两次交接丢材料再考虑 |
| R10 插件 review 命令定义 | 未读 | 暂缓 | 同上 |
| R11 ClauDex | 未读 | 不适用 | 社区方案,未审计 |
| R12 Spec Kit / R13 OpenSpec | 未读 | 不适用 | 计划文档已是规格 |
| R14 Superpowers | 已在本机安装并使用(执行计划、写计划技能) | 采用中 | 与项目规则冲突处以项目规则为准 |
| R15 GSD / R16 Ralph / R18 Symphony | 未读 | 暂缓 | D1–D5 出现可并行任务再考虑 |
| R17 BMAD | 未读 | 不适用 | 单人工具 |
| R19 Google / R20 LangChain | 未读 | 暂缓 | harness 调整时再读 |
| R21 课程 / R22 Quickstart | 未读 | 暂缓 | — |
| R23 / R24 / R25 评测与论文 | 未读 | 不适用于本轮 | 只影响分工,分工已定 |

## C 系列(Codex 官方)

| 编号 | 来源 | 阅读状态 | 采用 / 暂缓 | 依据 |
| --- | --- | --- | --- | --- |
| C01 Best practices / C03 Customization | 未读 | 暂缓(供 Codex 会话自己读) | — |
| C02 AGENTS.md | 未读 | 阶段 5 前读全文 | 确认 Codex 如何发现 AGENTS.md |
| C04 Build skills | 未读 | 不适用 | 无重复流程需求 |
| C05 Code review | 未读 | 阶段 5 前读全文 | 审查范围与只读语义 |
| C06 Long horizon tasks | 未读 | 暂缓 | — |
| C07 Hooks | 未读 | 暂缓 | — |
| C08 Non-interactive mode | 未读 | 阶段 5 前读全文 | `codex exec` 当前参数、只读沙箱 |
| C09 Evals | 未读 | 暂缓 | — |
| C10 Subagents / C11 Docs MCP | 未读 | 不适用 | 无需求 |
| C12 Developer commands | 未读 | 阶段 5 前读全文 | 命令语法 |
| C13 Windows sandbox / C14 WSL | 未读 | 阶段 5 前读入口页 | Codex 在本机运行环境 |
| C15 GPT-6 Astra | 未读 | 不适用 | 不假定模型 |
