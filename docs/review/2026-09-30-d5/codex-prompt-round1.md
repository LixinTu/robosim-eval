# Codex 独立审查提示词(D5 第 1 轮:README、演示、参数改动与两个运行器修复)

你是本次交付的独立审查者。请对 D:\RoboSim-Eval 的 D5(作品交付)做只读审查:不修改任何文件,不启动或停止 Isaac Sim、Nav2 或任何 WSL 进程,不连接 127.0.0.1:8226。审查完把报告交回 Claude Code,由它核实和修复。流程约定见 `docs/review/codex-review-prompt.md`(默认 Codex 独立审查提示词)。

**额度很紧,请严格控制阅读量:**
- 被审内容一律用 `git -C D:\RoboSim-Eval show 24fa308:<路径>` 读取;工作区可能已经在继续开发。
- 先读交接说明 `docs/review/2026-09-30-d5/handoff.md`(工作区中的文件)。
- 只读下面列出的文件和需求段落;不要整份读取 artifacts 下超过 200 行的文件,也不要读 docs/review 下其他目录。

## 第 0 步(各一句话,写在报告开头)
1. 列出本会话实际加载的项目说明来源。
2. 根据 docs/plan.md 写出"当前任务"。

## 被审文件
- `robosim_eval/nav2_params.py`、`tests/test_nav2_params.py`(整份)
- `git diff 02de625 24fa308 -- robosim_eval/runner.py robosim_eval/runner_fsm.py robosim_eval/config.py configs/baseline.yaml tests/test_runner_fsm.py tests/test_config.py tests/ros_fake scripts/wsl/test_runner_fake.sh`
- `README.md`、`docs/demo.md`(整份);`docs/defect-record.md` 的缺陷 3、缺陷 4 两节
- 证据(只定位需要的几行):`artifacts/d5/commands.md`、`artifacts/d5/compare-speed-01.md`

## 需求
计划书 A4 的 D5 一行;§D(三个真实操作;来源与 AI 参与的表述;不把现成控制器说成自己实现)。

## 审查重点
1. 参数派生是否只改声明的那一行、其余不变;路径解析在 YAML 注释、列表、同名叶子等情况下是否可靠;"参数不在运行中的节点生效就不发目标"是否真的能挡住。
2. 缺陷 3、4 的修复是否完整:先加载场景再装接触监视;`refresh_clock` 是否真的保证发目标时的仿真时间是新的,有没有在仿真暂停或卡住时让运行卡死或误报的路径。
3. README 能否让别人从新终端照着跑:命令、前提、退出码、结果文件是否与代码一致;来源与 AI 参与的表述是否准确、没有夸大。
4. docs/demo.md 的预测是否确实写在复跑之前(对照提交的作者时间与批次开始时间),结果对照是否如实(包括不成立的条目)。
5. 证据与主张是否一致。

## 报告格式(中文)
每个发现写清:严重程度(Blocker / Major / Minor);文件、函数或行号;触发条件;预期行为与实际行为;依据(代码行、可复现命令或失败用例);用户影响与修复方向;分类(已复现问题 / 有代码依据的问题 / 待确认疑点)。不设最低数量,没有发现就如实说明;不写纯风格偏好。

最后记录:审查版本 24fa308、实际执行过的检查、没读或没验证的部分、剩余风险、使用的模型名称(若可见)。
