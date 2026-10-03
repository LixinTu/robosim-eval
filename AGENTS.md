# AGENTS.md — RoboSim Eval

> 每次会话都会加载：Codex 直接读本文件，Claude Code 经 CLAUDE.md 的 `@AGENTS.md` 导入。只写 agent 自己查不到、又必须知道的事，细节去下表的文件里按需查。

## 项目

用现成的 Nova Carter 和 ROS 2 Jazzy + Nav2 做仿真评测工具：运行前诊断、复位并用真值核对、发目标、录制、分项判定、批量复跑、报告。导航和控制算法都来自上游，本项目只写评测工具。Isaac Sim 6.1.0 跑在 Windows，ROS 跑在 WSL2 的 Ubuntu 24.04。

## 按需查

| 要知道什么 | 去哪 |
| --- | --- |
| 当前任务、状态、决定记录、未解决问题（含审查确认、还没修的缺陷） | docs/plan.md |
| 完整启动与关闭顺序、全部退出码、底层脚本、一次性安装、本机实测特性 | docs/setup.md |
| 话题、门槛、时限、情形定义 | configs/baseline.yaml |
| 需求与验收原文 | docs/reference/RoboSim-Eval-Plan-and-Setup-ZH.md 的 A4–A6（§0 和 B 是 D0 时的执行指令，已作废） |
| 本机环境快照（2026-09-29，历史证据） | docs/environment.md |
| 证据记录格式 | artifacts/README.md |
| 审查材料、提示词与报告 | docs/review/ |

README.md、docs/technical-overview.md、docs/demo.md、docs/defect-record.md 是给人看的：做任务时不用读，改了产品行为时要同步更新。

## 常用入口

从 Windows PowerShell 调用，WSL 脚本内部自己加载 ROS 环境。

```powershell
# 离线检查，不需要仿真；改完代码先跑：固定输入测试 + doctor/运行器假节点测试，任一失败即非零（完整一次约 4 分钟）
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/verify.sh            # --fast 只跑固定输入测试

# 需要 Isaac 时：先 Get-Process kit 确认没有实例在跑（已有 kit.exe 时脚本拒绝启动）；再用 Start-Process 新开普通（非管理员）PowerShell 窗口运行下面这行，
# 它一直占着窗口直到 Isaac 退出，不能在工具 shell 里直接跑；之后轮询 sim.sh state，等它退出 0 再继续。
# -PythonServer 打开 Isaac 内只听 127.0.0.1、要令牌的 Python 执行服务，运行器每次经它装接触检测；不加也照常运行，但安全只能是 unknown，验证最多 inconclusive（退出 11），不会 pass
powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1 -PythonServer

wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/doctor.sh --out <dir>               # 0 正常 / 10 不推进（如暂停）/ 11 缺数据（场景没加载也是：先 sim.sh load 再 play）/ 12 降级 / 13 环境或接口 / 2 用法、配置或环境脚本出错 / 124 撞 60 s 上限，按失败记
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh <情形> [--out <dir>]  # 自己加载场景并复位；0 pass / 10 fail / 11 inconclusive / 20 中断 / 30 出错 / 31 取消或停车未确认（批量就此中止）/ 2 情形不存在、配置或环境脚本出错 / 124 撞 1500 s 上限（120 s 内没收完被强杀则 137）
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_batch.sh [--scenarios a,b] [--repeats N] [--out <dir>]   # 0 只说明每次都执行过，不看判定（情形名写错也是 0），结果看 batch.json 各次 exit 和 runs/summary.json / 31 某次取消或停车未确认，余下不跑 / 20 中断 / 2 用法或环境脚本出错 / 124 撞 4 h 上限
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh <state|load [uri]|play|pause|stop|reset|reset-check|pose [entity]>   # 另有 spawn-box、delete（见脚本头）；0 成功 / 3 服务不可用、超时或出错 / 4 reset-check 未过 / 2 用法或配置
```

- start_nav2、record_d0、stop_record、analyze_attempt、stop_nav2 是 D0 时手动串的零件，现在由运行器按顺序调用（第一个参数是运行目录），正常不手动串。send_goal 已不再被调用：运行器用自己的 rclpy action 客户端发目标，另写一份同格式的 goal-*.txt 给 analyze_attempt。运行器没走完收尾就退出（如 137）时，用 `stop_record.sh`、`stop_nav2.sh <运行目录>` 收尾；调试见 docs/setup.md 的附录。
- 同一时间只跑一个 run_scenario 或 run_batch，运行中也不调 sim.sh 的 load/play/pause/stop/reset：这一版没有互斥，第二个运行器会复位正在用的仿真、清空共享的接触缓存（锁在 fix/review-round1）。
- 这一版经 run_scenario.sh / run_batch.sh 运行时，终端 Ctrl-C 到不了运行器（`timeout` 没加 `--foreground`，修复在 fix/review-round1）。要中断一次运行，从另一个终端执行 `wsl -d Ubuntu -- pkill -INT -f robosim_eval.runner`，退出码 20；要停批量，执行 `wsl -d Ubuntu -- pkill -INT -f robosim_eval.batch`，当前这次跑完后停。退出 20 不等于目标已取消：在等目标被接受时中断，目标不取消，也不确认停车，之后要自己核对机器人已停。

## 硬规则

1. 只做 docs/plan.md 里最靠前的任务；不先搭网页、persona、world model。
2. 本机是 Isaac Sim 6.1 官方不支持的配置（Windows 10 + 8 GB 显存），用户已决定做完再升级：记录标注 unsupported configuration，不提议升级，不重装、不换驱动、不迁移。Isaac 在 `D:\isaac-sim-standalone-6.1.0-windows-x86_64`，WSL 发行版名为 `Ubuntu`。
3. 不新增付费服务，不 push（有 remote `origin`，由用户自己 push），不部署，不删除或覆盖用户文件，不停 Docker Desktop，不杀用户的 Isaac GUI，不 `wsl --shutdown`（会断 docker-desktop、改 WSL IP）。任何工具都不请求仿真进入 QUITTING。Claude Code 有 PreToolUse 钩子（`.claude/settings.json` → `.claude/hooks/guard_commands.py`），会直接拦下 git push（含 --dry-run）、wsl --shutdown 和结束 kit.exe：被拦就停下交给用户，用户同意的这类操作也由用户自己执行；不改钩子、不换写法、不写进脚本绕过。Codex 没有这个钩子，规则照样适用。
4. 第三方工作区 `~/robotics/vendor/isaac-ros-6.1` 不改原文件；Nav2 参数改动写成情形里的 `nav2_params`，由运行器在运行目录派生。
5. 证据即事实：每条命令记 命令 | shell | cwd | 退出码 | 日志（verify.sh 的记录自动生成）；常驻进程另记 启动时间、PID、观察时段、停止方式、退出码、退出原因（两张表见 artifacts/README.md）。不用 `|| true` 掩盖失败，不吞异常，不削弱断言，不把"已启动"写成"通过"；tee 必须配 pipefail。限时观察（故意跑满的 `timeout`）的 124 记为"观察满时长"；硬上限触发的 124（verify.sh、doctor.sh、run_scenario.sh、run_batch.sh）表示没跑完，算失败。
6. 固定输入测试、假节点测试（ROS domain 42）、真实 Isaac 集成分开记录。没开仿真时，真实 Isaac 集成在记录里写"未执行"及原因（verify.sh 不写这一项）；没开仿真去跑会失败退出（doctor 10/11，运行器 30），照实记失败，不能记成通过。产品证据放 artifacts/，过程证据放 docs/review/。
7. 判定以 robosim_eval/evaluator.py 为准：ABORTED 或被拒绝时，只有情形写了 `preset_unreachable: true`、必需数据流完整、真值没显示到达（目前没有真值也算没到）才判 unreachable；导航时限已触发则判 timeout；其余是 unknown，期望 reached 的情形因此判 fail。情形里的 `evidence` 只写给人看，代码不检查。原始状态码和 error_code 都保留；没测到接触是 unknown，不是"没碰撞"。写证据和分析时，每个位置、距离和误差都标明来源（里程计 / 定位估计（AMCL）/ 仿真真值）。
8. topic、消息类型、action 名先实查（`ros2 topic list -t`、`ros2 topic info -v`、`ros2 action list -t`）再写，不凭猜测；topic 和类型写进 configs/baseline.yaml，doctor 运行时按 ROS 图核对（类型不符退出 13）；`/navigate_to_pose`、Nav2 节点表（runner.py）和录制话题表（record_d0.sh、stop_record.sh、analyze_attempt.py）仍写死在代码里，映射变了要一起改。

## 在这台机器上干活的坑

- 前台工具调用最长 10 分钟、没有 tty。colcon、clone、批量、完整 verify.sh 放后台：可以用 Claude Code 后台任务（默认 30 分钟、最长 2 小时，要显式设时限；默认批量 9 次约 27 分钟，run_batch.sh 自身上限 4 小时），也可以在脚本里把整条命令放后台：`setsid nohup bash -c 'bash -l <脚本>; echo $? > <步骤>.exit' < /dev/null > <日志> 2>&1 &`，再轮询 `.exit`（D0 踩过的坑是只有 echo 进了后台）。这条不要经 `wsl --` 内联，否则 `$?` 会被提前展开。退出码记后台任务回报的，或 `.exit` 里的。
- 调 WSL 一律用脚本文件（临时检查也写成脚本，放 temp/），不写内联命令：不带 `-e` 时，wsl 把后面整行交给 WSL 默认 shell 再解析一遍，`$?`、`$x` 被提前展开，引号被重新解析，从 PowerShell 和 Git Bash 调都一样。PowerShell 双引号里的 `$…` 还会先被 PowerShell 展开，PowerShell 5.1 还会拆掉参数里的双引号。
- 从 Git Bash 调 wsl.exe 要加 `MSYS_NO_PATHCONV=1`，或者在 D:\RoboSim-Eval 下全用相对路径（如 `bash -l scripts/wsl/<脚本>.sh`，WSL 的 cwd 就是 /mnt/d/RoboSim-Eval）；否则 `/mnt/d/...`、`--out /mnt/d/...`、`X=/path` 这类参数会被改成 `C:/Program Files/Git/...`。从 PowerShell 调没有这个问题。
- `.ps1` 用 `powershell -ExecutionPolicy Bypass -File <脚本> <参数>` 运行，退出码就是脚本的 `exit`，完整用法见各脚本开头注释。
- `sudo` 要密码（`sudo -n true` 退出 1）。自己只用 `sudo -n`，失败就停；要执行的内容合并成一个脚本或命令块，交给用户在 Ubuntu 终端运行（脚本自己把日志和 `.exit` 写进 artifacts/），并在 docs/plan.md 里标"等待用户"。
- 需要 GUI 或管理员权限的步骤：写清用户做什么、做完报告什么，然后停下等，不假装已点过。Windows 侧的改动攒成一次 Isaac 重启，先做完无 GUI 的验证。
- 常驻进程（Nav2、记录器）用 start_nav2.sh / stop_nav2.sh、record_d0.sh / stop_record.sh 起停：setsid 起、记会话号；停时 SIGINT → 有界等待 → SIGTERM → SIGKILL（SIGKILL 会丢 bag 的 metadata.yaml、留下孤儿节点）。自己发信号时：Nav2 只发给 `ros2 launch` 进程（发给整组会让子进程收到两次，打断 Nav2 自己的关闭）；记录器按会话发（`timeout` 自建进程组）；非交互 shell 里用 `&` 起的进程会忽略 SIGINT，要用 `env --default-signal=INT,TERM` 起，或在 `timeout` 下起。
- 停完查残留：`pgrep -s <会话>` 看进程，`ros2 node list --no-daemon --spin-time 3` 看节点（daemon 缓存会列出已退出的节点；`--spin-time` 默认只等 0.5 s）。stop_nav2.sh 已经做了这两项：退出 1 表示有残留，3 表示查不了。
- 批量运行期间的开发放在独立的 git worktree：主工作区不改已跟踪文件、不提交、不切分支，运行器在 manifest.json 里记录主工作区的 commit、分支和已跟踪文件有没有未提交改动。但 worktree 只隔离文件，不隔离运行：doctor.sh、sim.sh、run_scenario.sh、run_batch.sh、test_doctor_fake.sh 写死了 /mnt/d/RoboSim-Eval，从 worktree 调用时跑的仍是主工作区的代码，运行器假节点测试里的诊断也是；Codex 审查也固定在 D:\RoboSim-Eval 读提示词和交接说明。worktree 里只有 verify.sh --fast 测的完全是自己的代码；改动合回主工作区的分支后，再跑完整的 verify.sh、真实运行或审查。
- Windows 休眠会暂停 WSL：正在跑的长任务和假节点测试会被打断，verify.sh 会在该行注明，重跑即可。
- 2026-09-30 用 filter-branch 改写过全部提交的作者邮箱。在那之前写下的提交号（plan、各 REVIEW.md 和审查提示词里的 dbf67ce、19203e0、24fa308 等）都是旧号，只留在本机的 refs/original 里，origin 上没有；新旧对照见 `git show master:docs/commit-map.tsv`。剩下的 Codex 分片要 `git show <旧号>` 读被审代码，跑完前不删 refs/original，不做 reflog expire 或 gc --prune。

## 审查门

实现 → verify.sh 通过 → 提交并冻结 → Codex 新进程只读审查 → 逐条核实、只修有效项、重跑受影响的检查 → Codex 复核，最多两轮。"无发现"不等于验收通过；Codex 不可用就标"待独立审查"，不伪造跨模型审查。

每次 git commit 前，pre-commit 钩子先在 WSL 跑 verify.sh --fast，失败就挡下提交。钩子按克隆启用：`git config core.hooksPath scripts/git-hooks`（本克隆已设）。不用 --no-verify，要跳过先问用户。钩子只跑 pytest；提交冻结、交审查前仍要跑完整的 verify.sh。verify.sh 的记录写在 artifacts/verify/<时间>/commands.md，这个目录被 git 忽略；要当证据引用的那份用 `git add -f` 提交，否则冻结提交里没有，审查读不到。

审查只走 `scripts/windows/run_codex_review.ps1 -Round <轮次> -Dir D:\RoboSim-Eval\docs\review\<日期>-<交付>`（PowerShell 5.1 用管道传中文提示词会被改写，所以不要自己拼命令）。先把提示词写成该目录的 `codex-prompt-<轮次>.md`；报告 `codex-<轮次>-report.md` 和 status/stdout/stderr 写回同一目录，同名轮次重跑会覆盖，复核换新轮次名。必须传 -Dir：默认是 D0 目录，`-Round round1` 会重跑 D0 的旧提示词、覆盖已入库的记录。内部是 `codex exec --sandbox read-only -C D:\RoboSim-Eval`：Codex 读主工作区，被审版本靠提示词里的 `git show <冻结提交>:<路径>` 固定。脚本等 Codex 结束才返回（成功的两轮用了 250 s 和 377 s），放后台跑。提示词模板是 docs/review/codex-review-prompt.md。

审查材料按分片在提示词里列清单：被审文件一律用 `git -C D:\RoboSim-Eval show <冻结提交>:<路径>` 读（主工作区可能在别的分支），已有文件的改动可以只给 `git diff <上一版> <冻结提交> -- <路径>`；先读本交付的 handoff.md。artifacts 只定位几行，不读 docs/review 下其他目录、task.diff 和 stderr 记录（D0 两次整轮读 diff 都在出报告前撞了额度）。

额度不够时先把范围拆成几个分片提示词，再用 `scripts/windows/run_codex_review_queue.ps1 -Items <日期>-<交付>/<轮次>,...` 排队（不带 -Items 会排 D0 的四个旧分片；-NotBefore 写不带空格的 ISO 时间）。它会睡几个小时，按脚本开头的 Start-Process 隐藏窗口方式启动。已有报告的轮次跳过，撞上限按 Codex 给的时间等待重试；锁 `docs\review\codex-queue.lock` 记 PID（被占时退出 3），日志 `docs\review\codex-queue.log`。本分支的单轮与排队脚本在 Codex 的整份记录里搜 'hit your usage limit'，而记录里有 Codex 读过的文件原文：审查 run_codex_review.ps1 本身的 D0 round1c-c 即使成功，也会被当成撞额度、报告被挪走重跑，重启后还会覆盖旧的 attempt 记录。修复 a39147c 只在 `fix/review-round1`，合并前单轮审查和排队都用那个分支工作区里的 run_codex_review.ps1、run_codex_review_queue.ps1、codex_queue_lib.ps1（2026-09-30 起队列就是这样跑的）。

## 什么要问人

重启 WSL、防火墙规则、需要 sudo 的安装、删除或搬迁文件；官方路线与计划冲突（例如 `netsh portproxy`）；换系统或换安装路线。

## 其他

Conventional Commits，小步提交。`master` 是发布分支（从 v0.1.0 起，跟踪 origin/master，只由用户推送），不是早期的文档基线；当前工作分支、审查修复分支（fix/review-round1）和合并顺序见 docs/plan.md。回复用户用中文，技术名词保留英文；项目文档用中文。
