# Codex 独立审查 Harness 参考与执行资料包

整理与核对日期：2026-09-29（America/Los_Angeles）

适用入口：能够读取当前项目文件的 Codex，例如 VS Code 中的 Codex 或 Codex CLI。客户端与版本的具体能力以实际环境为准。

这是一份可以单独交给 Codex 的资料包。它保留此前的通用启动、交接和独立审查提示词，以及 R01–R25 参考目录，并补充 C01–C15 的 Codex 官方资料。无需为了使用本包再下载 Claude Code 版本。

此前文件中已经包含 OpenAI 的 harness 文章、AGENTS.md、Codex 审查和协作插件；此前交接入口主要写给 Claude Code。本版将执行入口调整为 Codex 的独立审查，并明确默认流程是 Claude Code 主实现、Codex 独立只读审查、Claude Code 核实并修复。只有用户明确要求时，才把 Codex 切换为主实现者。

本包是参考资料与原创工作约定，不代表已在你的项目中安装或验证任何框架。原文链接提供方法依据；下方的任务选择、证据格式、审查轮数等是本包建议，不是所有工具的统一规定。

## 本版默认分工（性能比较后的更新）

截至 2026-09-29，本包默认采用下面的三步协作流程。它是结合公开评测、当前工具可用性和“独立视角 + 可验证修复”的需要做出的工作约定，不是对所有模型或项目的永久排名。

| 阶段 | 默认工具 | 主要职责 | 明确边界 |
| --- | --- | --- | --- |
| 主实现 | Claude Code | 理解需求、设计与实现、运行检查、准备交接材料 | 不把自己的自审当作独立审查 |
| 独立审查 | Codex（新会话） | 只读检查固定代码范围，给出有位置、触发条件和证据的问题 | 不直接修改被审查源码，不把疑点自动当成缺陷 |
| 核实与修复 | Claude Code | 逐条复现或依据代码确认，修复有效问题并重跑受影响检查 | 不照单全改；对不成立的意见留下依据 |

公开信号的含义需要谨慎解释：

- Scale 在 2026-09-22 的 SWE-Bench Pro V2 公开榜单中，Claude Code + Opus 5 排在 Codex + GPT-6 Astra 前面；该榜单没有覆盖 GPT-6.1，且推理配置不同，不能据此断言 Claude 全面领先。
- MacroscopeBench 的当前结果更像是“召回率与精确率的取舍”：Claude Opus 5.5 找出已知 Bug 的比例为 80.6%、有效报告比例为 84.0%；GPT-6 Sol 为 73.8% / 88.0%；GPT-6 Astra 为 67.8% / 91.7%。这是代码审查服务商在特定环境中的评测，不等同于两个客户端的整体能力。
- 一项比较审查顺序的研究使用 Opus 4.7 与 GPT-5.5，并要求审查者直接输出修改后的程序且不能运行测试：Codex 写、Claude 检查修改为 71.6% → 89.7%；Claude 写、Codex 检查修改为 91.4% → 82.8%。这支持“第二个模型的意见需要核实”，但不能直接推广到完整项目。

因此，Codex 在本包中的默认职责是独立只读审查：Claude Code 先实现并验证，Codex 形成有证据的审查报告，Claude Code 再核实、修复和重跑测试。只有用户明确要求、实际模型更合适，或项目约束改变时才交换角色，并记录交换原因、实际工具和模型。

## 交给 Codex 的方法

1. 下载本文件，放到 VS Code 当前打开的项目根目录或审查工作区，保持文件名 Codex-Harness-Pack-ZH.md。
2. 在该项目的 Codex 新会话中发送下方提示词。它找不到文件时，给出你电脑上的实际完整路径。
3. 同时提供 Claude Code 的交接材料、原始需求、验收条件、代码范围和验证证据；Codex 不能仅凭本包读到你在其他应用中的完整聊天。
4. 只有明确要求 Codex 主实现时，才使用后文标注的“Codex 主实现提示词”。

### 一次性交接提示词

请读取当前项目根目录的 Codex-Harness-Pack-ZH.md，作为本次交付的独立审查者，结合原始需求、现有计划、实际代码、本机环境和 Claude Code 的交接材料执行。

先确认本次审查的代码范围和基线，直接阅读需求、验收条件、实际 diff、相关完整代码、测试及运行证据，再按资料包的阅读顺序查阅真正相关的官方原文。简短说明审查范围和无法验证的部分，然后形成独立报告。

本轮保持源码只读，不直接实现或修复；不要修改 AGENTS.md、测试或配置来让结果通过。需要运行检查时使用不改变源码的命令、临时目录或隔离副本。不要把 Claude Code 的完成总结当成事实证明，也不要把每个疑点自动当成有效缺陷。

每条问题必须给出真实文件、函数或行号，触发条件、影响、复现步骤或代码依据，以及建议修复方向。区分已复现问题、有代码依据的问题和待确认疑点；没有发现也如实说明。把报告交回 Claude Code，由它逐条核实、修复有效问题并重跑受影响检查；必要时再由你复核修复后的固定范围。

最终提供实际审查版本、审查范围、执行过的检查、未验证部分、剩余风险和下次复核入口。审查报告不能替代测试结果或三步人工验收。

## 先明确：哪些是提示词，哪些是项目的 harness

启动提示词描述你要求建立的工作方式。将需求、工具、可运行检查、运行反馈和进度记录组织起来，并在真实任务中不断使用和修正，才形成项目的开发 harness。

Codex 与 Claude Code 是编码工具／Agent 产品名称；它们使用的具体模型需以当前会话为准。“跨工具审查”要记录实际运行了什么，不能仅凭角色名称认定换了模型。

本包讨论开发过程。若项目本身是教学、聊天或机器人 Agent，还需要另行定义产品行为评测；开发流程通过不等于产品效果已被证明。

## 阅读顺序与最小落地

### 第一步：确认实际项目

检查当前目标、正在使用的计划、相关代码入口、项目说明、启动和测试方式，以及已有暂存、未暂存、未跟踪改动。无需每次修改都遍历整个仓库；先读能确定当前任务和依赖的内容。

按实际操作系统和 Shell 选择命令。保留已有改动；没有代码访问、Git 或所需工具时如实记录。常规本地调查、实现、必要验证和修复自主完成；不新增付费服务，不推送或部署。

### 第二步：按问题读资料

首次设置时，先读 C01、C02、C03 的相关正文；需要审查时读 C05，复杂长任务再读 C06。浏览本包其余条目的用途，准备采用某项机制时再读对应原文的当前配置与限制。

R 系列保留完整参考目录，按问题深入。Claude Code 专属配置用于协作端，不能直接当作 Codex 的配置文件或命令执行。

在现有计划或记录中简记“实际读过的页面/章节—解决什么问题—采用或暂缓及理由”。无法访问的链接标注即可，不得把摘要、目录页或搜索片段记成读完全文。资料阅读不应无限推迟真实任务。

### 第三步：准备审查并跑必要的非破坏性检查

优先建立可用的启动方式、明确的验收条件和必要的检查；复用已有脚本、计划和目录。暂时没有需要时，不新建 Skills、Hooks、多 Agent 编排或 CI。

固定本次交付的代码范围，独立检查最靠前且依赖已满足的小任务，运行不改变源码的必要检查，形成报告后交给 Claude Code 核实和修复。修复后的版本再按需要复核；已有流程足够时，直接使用它。

## 项目文件各自承担什么

下表是安排建议，已有等价文件时继续使用。

| 内容 | 放在哪里 | 用法 |
| --- | --- | --- |
| 跨项目的个人偏好 | 可选的全局 AGENTS.md | 只放通用沟通或工作偏好；不要加入某一个项目的路径和命令。按 C02 确认实际配置目录，不要求本轮修改全局文件。 |
| 此项目的持久说明 | 项目 AGENTS.md | 保留简短规则、真实启动与验证命令，以及相关文档入口；已有内容应合并维护。 |
| 两个工具共享的事实 | 现有需求、架构、计划和验证记录 | 两端入口指向同一套文件；避免各维护一份不同的“当前计划”。 |
| Claude Code 的入口 | 已有或确有需要的 CLAUDE.md | 写入指向共享事实的简短说明；不要假定两工具会自动读取完全相同的入口。 |
| 重复且稳定的具体流程 | 可选的项目 Skill | 先证明重复需求存在，再按 C04 组织；不要把全部资料改造成常驻技能。 |
| 可重复执行的检查 | 项目现有脚本和测试 | 先能手动运行并正确报告失败，再按需求连接 Hook 或 CI。 |
| 本文件 | 根目录或现有参考资料目录 | 作为初始化和改进时的参考，日常按需读取。移动后更新入口路径。 |

项目初始化完成后，后续会话主要沿着 AGENTS.md 找到当前任务和相关文档；无需每次重新发送整份资料包。新项目仍应核实自己的实际目标、环境、命令和验收条件。

## Codex 方法速查

| 真实问题 | 优先考虑 | 原始资料 |
| --- | --- | --- |
| 每次重说项目规则 | 简短 AGENTS.md 与共享事实 | C01–C03 |
| 重复执行同类工作 | 按需加载的 Skills | C04 |
| 漏掉必要检查 | 可靠检查脚本，再选择合适的触发事件 | C07 |
| 长任务忘记状态 | 小里程碑、验收与持久进度记录 | C06、R02 |
| 希望独立检查改动 | Codex /review 或下文跨工具审查 | C05、R09–R11 |
| 已有可靠流程要批量运行 | codex exec、事件记录与结构化结果 | C08 |
| 提示词或 Skills 改动效果不明 | 历史任务回放、触发与结果评测 | C09、R19、R20 |
| 有可独立拆分的工作 | 在授权和能力允许时使用子 Agent，必要时隔离工作区 | C10 |
| 实际用起来失败，测试却通过 | 真实产品入口、日志与端到端验收 | R01、R07 |
| 缺少最新接口或工具文档 | 官方资料，必要时连接 Docs MCP | C11 |
| 命令在另一台机器才有效 | 核对客户端、版本、Shell 和路径 | C12–C14 |

## Codex 官方资料

以下 C 系列页面在本次整理中读取了相关正文，并未声称完整运行每个示例。参数可能随版本变化，应结合本机帮助与当前官方文档。

### C01 · 先读：Codex Best practices

- 原文：[先读：Codex Best practices](https://learn.chatgpt.com/guides/best-practices)
- 阅读目标：如何给出明确任务、相关上下文与完成条件；复杂任务怎样规划，成功的工作方式怎样保留。按实际改动复杂度使用，不把每次小修都变成完整立项。

### C02 · 先读：AGENTS.md

- 原文：[先读：AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- 阅读目标：全局、项目和子目录说明怎样被发现、组合和覆盖。项目中的简短规则可以持续生效；首次设置或规则更新后，核对新会话加载了哪些来源。

### C03 · 先读：Customization

- 原文：[先读：Customization](https://learn.chatgpt.com/docs/customization/overview)
- 阅读目标：区分项目说明、Skills、MCP 和子 Agent 的用途。先识别项目缺少的能力，再决定补哪一层。

### C04 · 按需：Build skills

- 原文：[按需：Build skills](https://learn.chatgpt.com/docs/build-skills)
- 阅读目标：把重复工作整理成 SKILL.md、参考资料和必要脚本，并按需加载。当前文档中的项目级本地技能入口是 .agents/skills；旧文章使用其他路径时，以当前版本文档和实际发现结果为准。

### C05 · 先读相关章节：Code review

- 原文：[先读相关章节：Code review](https://learn.chatgpt.com/docs/code-review)
- 阅读目标：本地 /review、未提交变更、基线分支和审查结果。当前 CLI 与 IDE 文档均描述只读审查；IDE 的 /review 需要打开的项目处于 Git 仓库内。先明确范围，不能把仓库全部未提交内容都算作本轮改动。

### C06 · 复杂任务先读：Run long horizon tasks with Codex

- 原文：[复杂任务先读：Run long horizon tasks with Codex](https://developers.openai.com/blog/run-long-horizon-tasks-with-codex)
- 阅读目标：以需求、里程碑、执行约定和状态文件维持长任务，并持续验证、修复、更新记录。参考其结构即可，复用已有文件名；不照搬实验时长、模型、用量或权限设置。

### C07 · 按需：Hooks

- 原文：[按需：Hooks](https://learn.chatgpt.com/docs/hooks)
- 阅读目标：在 Codex 生命周期事件触发脚本或 MCP 工具。当前文档有项目级 .codex/hooks.json 等入口；要理解具体事件、返回值和信任要求。先确认脚本成功与失败都能正确报告，再考虑接入；不绕过信任检查。

### C08 · 按需：Non-interactive mode

- 原文：[按需：Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode?translationFallback=ja-JP)
- 阅读目标：通过 codex exec 把已验证的流程接入脚本；--json 用于事件记录，--output-schema 用于结构化最终结果。当前正文将 --full-auto 标为兼容且弃用，新增脚本应核对当前参数；本包不要求自动化或修改权限。链接带站点回退参数，本次成功读取的是英文正文。

### C09 · 按需：Testing Agent Skills Systematically with Evals

- 原文：[按需：Testing Agent Skills Systematically with Evals](https://developers.openai.com/blog/eval-skills)
- 阅读目标：用小批真实案例检查技能是否正确触发、是否执行关键步骤，以及产物是否满足目标。区分执行过程与最终结果。文章中的 CLI 示例须与 C08 当前命令文档核对。

### C10 · 按需：Subagents

- 原文：[按需：Subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents)
- 阅读目标：将范围明确的独立工作交给子 Agent，并回收结果。支持情况以本机客户端、版本和会话能力为准。Codex 内部子 Agent 与外部 Claude Code 审查是不同的执行路径，记录时要写清。

### C11 · 按需：Docs MCP

- 原文：[按需：Docs MCP](https://learn.chatgpt.com/learn/docs-mcp)
- 阅读目标：让 Codex 或 Claude Code 查询官方 OpenAI 文档；该服务提供文档检索，不替你执行 OpenAI API 请求。已有可用官方文档访问方式时，按需决定是否增加连接。

### C12 · 按需：Developer commands

- 原文：[按需：Developer commands](https://learn.chatgpt.com/docs/developer-commands)
- 阅读目标：核对 /init、/review、/skills、/hooks 和 codex exec 等命令的客户端、语法与用途。斜杠命令输入编码工具的会话框；终端命令在匹配的 Shell 中运行。

### C13 · 按环境：Windows sandbox

- 原文：[按环境：Windows sandbox](https://learn.chatgpt.com/docs/windows/windows-sandbox)
- 阅读目标：了解 Windows 原生运行的边界与问题定位。先查实际环境，不为了套用教程就迁移项目、关闭沙箱或重装工具。

### C14 · 按环境：WSL

- 原文：[按环境：WSL](https://learn.chatgpt.com/docs/windows/wsl)
- 阅读目标：确有 Linux 工具链需求或项目已在 WSL2 时，检查 VS Code 窗口、运行环境、项目路径和工具安装是否一致。Windows 与 WSL 的路径及安装状态不能混用。

### C15 · 进阶：Rethinking skills and prompts for GPT-6 Astra

- 原文：[进阶：Rethinking skills and prompts for GPT-6 Astra](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra)
- 阅读目标：理解模型变化后为什么要重新评估旧规则、技能描述和强制阅读步骤。它是面向标题所述模型的指导；不据此假定用户正使用该模型，也不自动更换模型。


## Codex 与 Claude Code 互相检查

这套交接约定适用于两个方向，但默认使用第一行。先把手动交接跑通，再判断是否需要自动编排。

| 实现者 | 独立审查者 | 交接方式 |
| --- | --- | --- |
| Claude Code（默认） | Codex | Claude Code 先实现并验证；Codex 新会话只读审查；Claude Code 核实有效问题、修复并重跑检查；必要时 Codex 复核。 |
| Codex（仅明确切换时） | Claude Code | Codex 先实现并准备同类材料；Claude Code 新会话只读审查；Codex 核实并修复。 |

执行约定：
1. 同一工作目录同一时刻只有一个实现者写源码。审查期间固定范围并暂停相关修改，或提供准确的隔离快照。仅有提交哈希不能证明未提交改动也被包含，应记录对应文件清单与可比对版本。
2. 审查者读取原始需求、验收条件、实际 diff、相关完整代码和测试；包含新增文件，区分用户已有改动。先独立形成判断，不只复述实现者总结。
3. 每条问题提供位置、触发条件、影响与复现或代码依据。实现者逐条核实；只修复有效问题，重跑受影响检查，再让审查者复核变更后的版本。
4. 默认最多两轮审查—修复—复核；仍有争议时留下证据和未解决项。该轮数是本包的可调整约定。
5. 双工具均表示“未发现问题”也不等于实际验收通过；运行证据与审查结果分别保留。
6. 另一工具不可用时先完成能做的任务与交接材料，标记待审查；可以由用户把后文独立审查提示词发到另一工具。不得伪造跨模型审查记录。

官方 Codex plugin for Claude Code（R09）提供的是在 Claude Code 中使用 Codex 的入口。不能据此推断已经存在、安装或配置了“Codex 内反向调用 Claude Code”的同名插件。反向调用应以本机真实可用工具和当前文档为依据；无自动连接时使用上述文件交接即可。

## 少量命令提示

这些是用法索引，不要求现在执行。先确认客户端和当前版本。

| 场景 | 输入位置 | 可查的命令 |
| --- | --- | --- |
| 起草项目 AGENTS.md | Codex CLI 会话框 | /init；已有说明时优先编辑合并，避免覆盖。 |
| 审查当前项目改动 | 支持的 Codex 会话框 | /review；明确选择本次范围。 |
| 查看并选择技能 | Codex CLI 或 IDE 会话框 | /skills |
| 检查 Hook 配置与信任 | Codex CLI 会话框 | /hooks |
| 非交互脚本运行 | 实际项目所用终端 | codex exec；详见 C08。 |

AGENTS.md、Skill 与检查脚本是不同的东西：写下“测试必须通过”并不会自动建立有效测试；脚本自身需要能够识别失败并返回正确状态。

## R 系列：此前讨论的通用方法与 Claude Code 协作资料

### R01 · 通用参考 · OpenAI：Harness engineering

- 原文：[OpenAI：Harness engineering](https://openai.com/index/harness-engineering/)
- 阅读目的：重点：项目知识入口、运行中的产品、日志、结构约束和持续维护。思考当前仓库缺的是哪一种反馈能力。

### R02 · 通用参考 · Anthropic：Effective harnesses for long-running agents

- 原文：[Anthropic：Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- 阅读目的：重点：初始化与后续开发分工、功能清单、增量交付、进度记录和跨会话续接。借鉴方法时沿用本机命令，不直接套用示例环境。

### R03 · 通用参考 · Claude Code Best Practices

- 原文：[Claude Code Best Practices](https://code.claude.com/docs/en/best-practices)
- 阅读目的：重点：真实验证、按需读取上下文、Writer/Reviewer 分工和实际使用中的反馈。

### R04 · 通用参考 · Codex：AGENTS.md

- 原文：[Codex：AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
- 阅读目的：核对项目说明的发现和作用范围；与 CLAUDE.md 共享项目事实，按当前文档确认具体机制。

### R05 · 通用参考 · Claude Code Common Workflows

- 原文：[Claude Code Common Workflows](https://code.claude.com/docs/en/common-workflows)
- 阅读目的：重点：读代码、修复、重构、测试和工作目录操作。用于核对可在当前工具中执行的步骤。

### R06 · 按问题深入 · Claude Code Hooks

- 原文：[Claude Code Hooks](https://code.claude.com/docs/en/hooks-guide)
- 阅读目的：重点：在指定事件触发命令，理解退出状态、阻塞语义与局限。先验证检查脚本，再决定触发时机；模型判断型 hook 与确定性脚本检查要区分。

### R07 · 按问题深入 · Anthropic：Harness design for long-running application development

- 原文：[Anthropic：Harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- 阅读目的：重点：规划、实现、独立验收；通过运行中的页面、接口和数据验证成果。文中也讨论随模型能力变化删减流程组件。

### R08 · 通用参考 · Codex：Code Review

- 原文：[Codex：Code Review](https://learn.chatgpt.com/docs/code-review)
- 阅读目的：核对本地审查范围和结果使用方式。分清未提交、提交和分支范围，不把其他已有改动混成本次交付。

### R09 · 双工具协作 · OpenAI：Codex plugin for Claude Code

- 原文：[OpenAI：Codex plugin for Claude Code](https://github.com/openai/codex-plugin-cc)
- 阅读目的：在 Claude Code 内调用 Codex 审查或委派任务。实际安装前核对依赖、CLI、登录及当前用量方式；本包不自动授权安装或付费。

### R10 · 双工具协作 · 官方插件的 review 命令定义

- 原文：[官方插件的 review 命令定义](https://github.com/openai/codex-plugin-cc/blob/main/plugins/codex/commands/review.md)
- 阅读目的：核对只读审查、参数和目标选择的真实实现。先确定代码范围，再执行审查；普通 review 与自定义关注点的支持范围以当前定义为准。

### R11 · 社区示例 · ClauDex

- 原文：[ClauDex](https://github.com/hamza-ali-shahjahan/claudex)
- 阅读目的：作者 README 描述跨模型独立审查和有限修复循环。它是社区方案，本包整理者未安装或审计；用于比较自动编排设计。

### R12 · 规格与计划 · GitHub Spec Kit

- 原文：[GitHub Spec Kit](https://github.com/github/spec-kit)
- 阅读目的：把目标整理为规格、技术计划与任务，再围绕它们实现和核对。考察现有需求/计划是否已经覆盖，不重复创建一套。

### R13 · 规格与计划 · OpenSpec

- 原文：[OpenSpec](https://github.com/Fission-AI/OpenSpec)
- 阅读目的：按一次变更组织提案、规格、设计与任务，适合考察需求变更如何保留依据。与其他规格工具比较后选择适合的一个。

### R14 · 开发步骤 · Superpowers

- 原文：[Superpowers](https://github.com/obra/superpowers)
- 阅读目的：用 Skills 组织设计、计划、TDD、调试、审查等步骤。核对其流程约束与当前项目已有规则是否兼容，特别是保留已有代码和用户确认方式。

### R15 · 分阶段交接 · GSD Core（当前仓库）

- 原文：[GSD Core（当前仓库）](https://github.com/open-gsd/gsd-core)
- 阅读目的：侧重阶段化推进、新上下文执行与状态文件交接。旧 gsd-build/get-shit-done README 已指向此仓库；不要照搬旧教程命令。

### R16 · 持续执行 · Ralph（snarktank 实现）

- 原文：[Ralph（snarktank 实现）](https://github.com/snarktank/ralph)
- 阅读目的：用小任务清单、检查和持久记录推动多轮执行；此实现每轮新上下文并设轮数上限。Ralph 有不同实现，参数与行为不能混用。

### R17 · 完整产品流程 · BMAD Method

- 原文：[BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)
- 阅读目的：组织产品、架构、UX、开发、测试视角与决策记录。考察项目是否确实需要这些角色和流程。

### R18 · 任务调度 · OpenAI Symphony

- 原文：[OpenAI Symphony](https://github.com/openai/symphony)
- 阅读目的：隔离运行开发任务并收集工作证据。仓库标注工程预览；先确认项目已有可靠启动、测试与验收能力，再考虑调度层。

### R19 · 开发过程评测 · Google：The Anatomy of Harness Engineering

- 原文：[Google：The Anatomy of Harness Engineering](https://developers.googleblog.com/the-anatomy-of-harness-engineering-how-to-evaluate-iterate-and-guard-ai-coding-agents/)
- 阅读目的：检查可观察的开发行为，例如是否执行必要验证；和最终结果评测配合。复杂任务避免强制唯一工具调用顺序。

### R20 · 基于失败改进 · LangChain：Improving Deep Agents with harness engineering

- 原文：[LangChain：Improving Deep Agents with harness engineering](https://www.langchain.com/blog/improving-deep-agents-with-harness-engineering)
- 阅读目的：分析运行轨迹中的失败，针对性调整提示词、工具和执行机制；包括漏验证、时间预算和反复无效修改。其基准表现不等同于本项目收益。

### R21 · 学习课程 · Claude Code in Action

- 原文：[Claude Code in Action](https://academy.claude.com/courses/claude-code-in-action)
- 阅读目的：课程入口。本次核对了课程介绍和章节目录，未在此包中复制课程内容，也不声称看完视频。需要时阅读对应公开章节。

### R22 · 长期执行代码示例 · Anthropic Autonomous Coding Quickstart

- 原文：[Anthropic Autonomous Coding Quickstart](https://github.com/anthropics/claude-quickstarts/blob/main/autonomous-coding/README.md)
- 阅读目的：查看初始化、连续工作及进度记录如何写成代码。运行前自行核对当前依赖、认证与费用；只参考结构不要求运行整套示例。

### R23 · 实现能力参考 · Scale SWE-Bench Pro V2

- 原文：[SWE-Bench Pro V2 公开榜单](https://labs.scale.com/leaderboard/swe_bench_pro_public_v2)
- 阅读目的：作为实现角色选择的有限参考。2026-09-22 的榜单中 Claude Code + Opus 5 位于 Codex + GPT-6 Astra 之前；榜单未覆盖 GPT-6.1，且模型与推理配置不同，不据此推导全面优劣。

### R24 · 审查能力参考 · MacroscopeBench

- 原文：[MacroscopeBench 基准结果](https://macroscope.com/benchmark)；[方法说明](https://macroscope.com/blog/macroscopebench)
- 阅读目的：参考独立代码审查中的召回率与精确率取舍。公开结果显示 Opus 5.5 的已知 Bug 找出比例较高，而 GPT-6 Sol / GPT-6 Astra 的有效报告比例较高；这是特定服务环境的结果，不等同于客户端整体表现。

### R25 · 顺序效应研究 · Codex 与 Claude 的协作顺序

- 原文：[arXiv 论文 HTML](https://arxiv.org/html/2607.21656v1)
- 阅读目的：提醒审查者不能直接修改并要求实现者照单全收。该研究的设置是算法题、审查者直接输出修改后程序且不能运行测试；它不直接证明完整项目中的工具分工，但支持“只读审查—实现者核实—再修复”的约定。


## 通用执行与交接提示词

以下以“Claude Code 主实现、Codex 独立审查”为默认。项目背景优先复用用户当前明确需求和现有文件；方括号没有填写时，先查项目资料，仅对真正影响当前工作的问题提问。后面的“Codex 主实现提示词”只在用户明确要求交换角色时使用。

### Codex 主实现提示词（仅在明确切换角色时）

请在当前项目中建立最小、可验证、可交接的 AI 开发流程（development harness），并用第一项或下一项真实小任务跑通。

项目背景：
- 项目目标与主要使用者：[填写，或指向现有需求文档]
- 最重要的使用流程：[用户做什么，希望得到什么结果]
- 本次优先目标：[填写；留空时根据现有计划和依赖选择]
- 已确认的技术、平台、预算与其他约束：[填写；未知就写未确定]

请直接执行。常规调查、实现、测试和修复自主推进。只有明显影响产品方向、费用、数据或不可逆操作的问题才需要我决定；影响当前任务的产品问题集中提出，最多三个。默认沿用现有资源，不新增付费服务，不推送或部署，保留已有改动。

一、确认真实起点
检查实际项目目录、操作系统、Shell、已安装工具与依赖，以及现有 README、AGENTS.md、CLAUDE.md、计划、测试和启动配置。记录 Git 基线及已有暂存、未暂存和未跟踪文件；没有 Git 或历史提交时如实说明起点。保留已有改动，并让本次改动可以单独识别。
区分：已实现且有验证证据、已实现但未验证、尚未实现。不要仅凭文档中的“完成”判断。
空项目先建立符合目标的最小结构；已有项目优先复用。无法访问实际项目时，明确缺少的访问或文件，不用示例项目冒充执行。

二、明确需求和下一项交付
维护正在使用的计划；没有计划时才建立一份简短计划。区分已确认需求、实现假设、待决定问题。
将当前阶段拆成小交付，每项列出：用户操作、预期结果、关键异常和验证方法。按真实进度与依赖选择最靠前的未完成项，先写本次验收条件，再实现。
尊重已确认的阶段顺序。对明显影响体验的假设，用具体操作场景说明并给出推荐；普通实现细节自行决定。

三、补齐最小配置
精简项目说明，只保留必要约束、代码入口、真实启动与验证命令、当前计划和文档链接。详细知识按任务读取，不把本提示词全文复制成常驻规则。
若同时使用 Claude Code 和 Codex，让各自说明入口指向同一套项目事实，并确认入口可被找到；避免两套冲突文档。
根据实际技术栈和系统复用验证工具，仅补缺项。不预设必须用某种语言、构建工具、目录结构、MCP 或多 Agent 框架。暂不为尚未出现的问题堆叠 Skills、Hooks 和 CI。

四、实现并取得运行证据
先检查现状，再修改相关代码。运行与改动有关的必要检查，并检查实际用户入口：按项目类型选择页面、接口、命令行、应用或仿真流程。
验证入口必须保留失败退出状态。不能吞掉错误、削弱断言或跳过必要检查来获得通过结果。
修复缺陷时，尽可能保留同一案例修复前失败、修复后通过的证据，并按风险保留回归检查。简单改动使用相称的验证，避免无意义的测试。
记录实际命令、执行环境、退出码、关键结果和证据位置；说明失败项、未执行项及原因。涉及模型或外部服务时，分开记录固定回复／模拟测试与真实集成测试。
受环境限制的部分如实标注，继续完成不受影响的工作。

五、准备并执行独立审查
为本次交付准备原始需求、验收条件、基线版本、本次实际 diff、相关代码与测试、运行证据及已知限制。包含新增未跟踪文件，并区分已有改动与本次改动；同一文件混有两类改动时保留可比对依据。
如另一工具已可用且当前环境允许调用，可以让 Claude Code 与 Codex 分别承担实现和审查。审查者使用新的上下文，直接检查真实代码和测试；不要只依据实现者总结判断。
同一时刻只让一个实现者修改该工作目录。审查阶段保持源码只读，并固定代码快照或在审查期间暂停修改；测试产物使用临时目录。记录实际审查工具、模型（可确认时）和代码版本。
审查意见必须提供具体位置、触发条件、影响与复现办法或明确代码依据。先核实，再修复有效问题，随后重跑受影响的验证。
默认最多进行两轮“审查—修复—复核”；仍有问题或分歧时列明证据、状态和下一步，不强行宣称通过。这里的轮数是本项目流程约定。
另一工具不可用时，完成交接材料并标注“待独立审查”。单工具的新会话审查应如实命名；不能冒充跨模型审查。审查调用失败或没有发现问题，都不能替代测试结果。

六、交付并留下进度
完成最小配置和一个小任务后，更新同一份计划，简洁提供：
1. 完成范围、计划更新及实际改动文件。
2. 启动命令、必要条件、实际访问地址或执行入口。
3. 本次 diff、验证结果和证据位置。
4. 失败、未验证、剩余问题及独立审查状态。
5. 我能亲自完成的三步验收，每步包含操作与预期结果。
6. 两三个关键文件与函数，解释入口、状态变化和失败处理。
7. 审查材料位置，以及下个会话从哪里继续。

先给出简短现状、所选小任务和验收条件，再继续执行。完成后明确哪些规则已保存在项目中，供后续会话复用。

### 默认：Codex 独立审查提示词

请作为本次交付的独立审查者，对当前项目的指定交付做独立代码审查。本轮保持源码只读，不直接修复；完成后将报告交回 Claude Code，由 Claude Code 核实和修复。

审查材料：[填写实现者给出的交接文件或目录]
代码范围：[填写基线版本、目标版本或明确的改动清单]

先核对代码范围，直接阅读原始需求、验收条件、实际 diff、相关完整代码和测试。覆盖新增未跟踪文件，并区分已有改动。不要只依据实现者的完成总结判断。

检查用户可观察行为、边界条件、异常处理、回归和测试有效性。需要运行检查时使用临时目录或隔离副本，避免修改被审查源码。无法运行的检查明确标注。

每个发现写清：
- 严重程度及真实文件、函数或行号；
- 触发条件、预期行为与实际行为；
- 复现步骤、失败测试或明确的代码依据；
- 用户影响与建议修复方向。

区分已复现问题、有代码依据的问题和待确认疑点。不设最低问题数量；没有发现也如实说明。避免纯风格偏好和没有证据的大规模重构建议。

最后记录实际审查版本、执行过的检查、未验证部分和剩余风险。无法访问代码或范围不清时指出缺失材料，不根据摘要给出通过结论。

### 日常继续提示词

请先读取本项目说明和当前计划，核对现有进度与未提交改动，继续完成最靠前且依赖已满足的小任务。沿用既定验证与审查流程，完成后更新进度并提供运行证据。只询问会影响本次交付的关键产品问题。

### 根据审查修复的提示词

请逐条核实这份审查意见，复现或根据实际代码确认有效后，再修复本次范围内的问题；对不成立的意见给出依据。修复后重跑受影响的检查，更新 diff、证据和计划，并准备交给原审查者复核。保留已有无关改动，遵守本项目权限与费用约束。

## 完成后的最小证据

- 计划与实际进度一致，来源采用决定能查到。
- 一条真实用户流程可运行；有启动入口与操作步骤。
- 检查记录包含实际命令、退出结果和对应代码范围。
- 已有改动与本次改动能区分，新增文件也在审查范围内。
- 审查工具和阅读范围如实记录；调用失败与待审查不会被写成通过。
- 下个会话能从现有说明和记录继续，无需再次复制整份参考资料。
