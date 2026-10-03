# RoboSim Eval — 计划与状态(唯一活计划)

> 只记四样:状态、当前任务、决定记录、未解决问题。需求与验收原文在 `docs/reference/RoboSim-Eval-Plan-and-Setup-ZH.md`(2026-09-29 冻结;§0 与 B 已作废,A4–A6 仍是验收依据);做事的规则在 AGENTS.md,怎么跑在 docs/setup.md。2026-10-03 删去的旧章节(本轮范围、执行机制、最小组合、阶段计划、验收清单、偏差记录、风险)和已有结论的发现,用 `git show cb7c6a4:docs/plan.md` 查看。

## 1. 状态

| 交付 | 状态 | 证据 | 阻塞 / 备注 |
| --- | --- | --- | --- |
| 阶段 0 · 唯一计划与入口 | 完成(2026-09-29) | 基线 commit `dbf67ce`(master);分支 `feature/d0-environment`;AGENTS.md / CLAUDE.md / docs/plan.md / docs/harness-sources.md(2026-10-03 删除,见 git 历史 cb7c6a4)/ artifacts/README.md | — |
| D0a · 环境证据 | 完成(2026-09-29 19:02–19:04) | docs/environment.md;artifacts/d0a/(两侧探测原始输出 + commands.md) | 门槛 1→2 通过;发现:WSL 内无 ROS 2,sudo 需密码 |
| D0b · ROS 2 Jazzy + 6.1.0 示例工作区 | 完成(2026-09-29 19:16–19:30) | artifacts/d0b/commands.md(安装日志、check-ros-install、talker/listener ×2、rviz2 测试、setup-workspace.log) | 门槛 2→3 通过。工作区 `~/robotics/vendor/isaac-ros-6.1`,HEAD a9e8471…;安装脚本首跑退出码 1 是校验步骤的 `set -u` 缺陷(已修),安装本身成功 |
| D0c · Windows↔WSL 桥接 + Nova Carter 场景 | 完成(2026-09-29 19:35–20:12) | artifacts/d0c/commands.md;probe-04-playing/(/clock 25–26 Hz、/chassis/odom 25.8 Hz、/tf 25–26 Hz、/front_3d_lidar/lidar_points 2.4–2.8 Hz、tf2_echo odom→base_link);clock-continuity-01;clock-pause-test-02(暂停 29 s 时钟停、恢复后继续);bridge-check-01/02;kit-udp-endpoints-01;diag-01 | 门槛 3→4 通过。排障:Windows 防火墙阻断 WSL→kit.exe 入站(用户以管理员加一条限定规则后解决);首次 Play 后约 7 s 时间线暂停(当时记为"被停止";2026-10-03 对照 kit 日志改正,触发原因不明,重新 Play 从暂停处恢复,见 docs/setup.md 本机实测特性)。发现:示例场景不发布 2D 雷达扫描(params 的局部代价地图两路来源无数据,D0d 记偏差);USD 动画时间线每 ~41 s 墙钟循环一次(约 16.7 s 仿真时间)但仿真时钟不受影响;显存为几次点采样(空场景 3124–3128 MiB、Play 后 5 s 3754 MiB、Nav2 运行时 Isaac 界面显示 3.9 GiB),未做连续测量 |
| D0d · 一次真实 A→B | 完成(2026-09-29 20:13–20:52) | artifacts/d0d/commands.md;run-01/(nav2-launch.log、ready-check-01、map-overview、rviz 截图、usd-inspection);run-01/attempt-01/(goal-202437.txt、result.json、trajectory.csv、bag-info、文本流);run-02/03/04-stoptest(停止路径验证) | 目标 map (-4.0,-1.0,yaw 0) 由 CLI action client 发送:SUCCEEDED、error_code 0、0 次恢复、8.47 s 仿真时间、停稳确认;**AMCL 独立来源**(理想里程计 + USD 出生位姿)在停稳确认时刻误差 0.091 m,AMCL 估计 0.231 m → validation=pass(内部预审后用新分析脚本重算)。当时的发现已并入 docs/setup.md 的"本机实测特性"与 §4,原文见 cb7c6a4 版的 §9 |
| D0 交付 + 独立审查 | 进行中:**待独立审查** | docs/setup.md;docs/review/2026-09-29-d0-handoff.md;docs/review/2026-09-29-d0/REVIEW.md | Codex 第 1 轮两次因账户用量上限中止、无意见(20:59 用 82,531 tokens;23:23 重跑用 102,685 tokens);同一范围拆成 4 个分片:round1c-a、round1c-b 已出报告(5 条、9 条,待逐条核实),round1c-c 撞账户用量上限、round1c-d 未跑,见 §2;Claude 内部预审第 2 次完成(38 条,确认 35 条),有效项已修复并回归,见 REVIEW.md |
| D1 doctor | 实现与验证完成(2026-09-29 23:3x–23:49),**待独立审查**与用户验收 | 分支 `feature/d1-doctor`;`robosim_eval/doctor*.py`、`configs/baseline.yaml`、`scripts/wsl/doctor.sh`;证据 `artifacts/d1/commands.md` | 固定输入测试 37 passed、改坏检查 7/7、假节点测试 6/6;真实 Isaac:运行时退出 0,用户按 ⏸ 后 2 s 窗口判"不推进"退出 10,恢复后退出 0 |
| D2 单次运行器 | 实现与验证完成(2026-09-30 00:1x–00:47),**待独立审查**与用户验收 | 分支 `feature/d2-runner`;`robosim_eval/runner*.py`、`sim_adapter.py`、`run_io.py`;`scripts/wsl/run_scenario.sh`、`sim.sh`;证据 `artifacts/d2/commands.md` | 固定输入测试 77 passed;运行器假节点测试 8/8;真实 Isaac:正常 A→B reached(真值误差 0.264 m),导航中 SIGINT → 取消、停车、收尾(interrupted);Isaac 由 sim_control 复位、加载场景、读真值,不再需要 GUI 点击 |
| D3 判定与失败处理 | 实现与验证完成(2026-09-30 00:5x–01:29),**待独立审查**与用户验收 | 分支 `feature/d3-verdicts`;`robosim_eval/evaluator.py`、`contacts.py`、`kit/contact_monitor.py`;证据 `artifacts/d3/commands.md`;缺陷记录 `docs/defect-record.md` | 固定输入测试 109 passed;判定模块改坏检查 8/8(含 4 种必做的坏数据);真实 Isaac:正常、绕行、不可达、取消、超时 pass,断流正确判 inconclusive,碰撞抓到轮子与矮箱子的接触判 fail;修复一个运行器缺陷(复位前 odom 残留) |
| D4 批量复跑 | 实现与验证完成(2026-09-30 01:30–02:0x),**待独立审查**与用户验收 | 分支 `feature/d4-batch`;`robosim_eval/batch.py`、`report.py`、`scripts/wsl/run_batch.sh`;证据 `artifacts/d4/commands.md`、`artifacts/d4/batch-20260930-013010/runs/report.html` | 9 次全部留档、全部 pass(normal 3/3 到达、bypass 3/3 到达且未碰箱子、unreachable 3/3 判不可达);每次复位后真值距出生点 0.07 mm;报告改进 1 处(列出全部 commit、恢复次数列);"开头卡住"查到大部分机制(见 §4) |
| D5 作品交付 | 实现与演示完成(2026-09-30 01:3x–02:3x),**待独立审查**与用户验收 | 分支 `feature/d5-demo`;`README.md`、`docs/demo.md`、`robosim_eval/nav2_params.py`;证据 `artifacts/d5/commands.md` | README 第 2 步的两条命令在新的 PowerShell 里逐字执行通过(用空场景模拟"刚启动、场景未加载";Isaac 没有真正重启,第 1 步和第 3 步没有按原文执行);三个演示:正常导航并打开记录(pass)、取消案例及解释(pass)、参数改动 max_vel_x 0.8→0.4 的事先预测与复跑对比(峰值速度、平均速度、行驶段、到达误差成立;"判定不变"部分成立,一次因自发卡顿判 inconclusive;路程与最大角速度不成立;"开头卡住不因参数改变"无法检验,见 docs/demo.md);修复缺陷 3(场景未加载时接触监视装不上)与缺陷 4(接受目标时的仿真时间是旧的);固定输入测试 128 passed,运行器假节点测试 10/10 |
| 审查修复(`fix/review-round1`) | 已并入 `chore/harness-cleanup`(2026-10-03,5241837),真实 Isaac 复跑 normal **pass**;合入 master 见 §2 | 合并提交 5241837;完整 verify `artifacts/verify/20261003-093557`(620 passed,doctor 与运行器假节点测试 PASS);真实运行 `artifacts/review-2026-10-03/runs/normal-20261003-114140` | 2026-09-30 Claude 多代理审查确认的问题和 Codex D0 round1c-a 的修复,共 42 个提交。合并后第一次真实 normal(09:44)因 WSL 墙钟被往回拨判 inconclusive,与代码无关;Windows 重启后(11:41)pass:真值距目标 0.145 m,0 次恢复,接触已测,倒退时间戳 0(§4)。`impl/shell` 没有并入(§4) |

**尚未完成的验收**(其余各项的证据见上表):

- 合并后的代码只在真实 Isaac 上跑过 normal;其余情形(normal_slow、bypass、unreachable、cancel、timeout、dropout、collision)和终端 Ctrl-C 还没用它重跑。
- 独立审查:D0–D5 都没有完成,见 §2。
- 用户验收:D0 三步(新终端启动后看到地图与实时数据;发目标,看到达并打开记录核对;暂停看数据停,恢复看数据回来);D1–D5 按 README 与 docs/demo.md 的操作复现。

## 2. 当前任务

**分支做法(2026-10-03 起)**:文档整理和审查修复都在 `chore/harness-cleanup` 上做(从 `feature/d5-demo` 的 cb7c6a4 分出),不再回到各交付分支改再向后合。`feature/d0-environment` … `feature/d5-demo` 不再改动,只作为被审的冻结版本:分片提示词用 `git show <冻结提交>:<路径>` 读被审代码,这部分不受本分支的提交影响;提示词本身、需求文档和 docs/plan.md 是从工作区读的,本分支改过提示词里的需求文档路径。推送由用户自己做(PreToolUse 钩子会拦下 agent 的 git push)。

1. **合并**(2026-10-03 用户定的顺序,不再等审查与验收;争取在 2026-10-06 14:51 Codex 额度恢复前合完,之后排队直接从合好的分支跑):
   - ① 把 `fix/review-round1` 并进来,代码以 fix 分支为准、文档结构以本分支为准:完成(5241837);完整 verify.sh 通过(2026-10-03 09:36–09:42,`artifacts/verify/20261003-093557`)。AGENTS.md、setup.md、本文件已按合并后的代码改过(2026-10-03 逐条对照代码核实)。
   - ② 在真实 Isaac 上跑一次 normal:完成。09:44 那次录下的 clock、odom、tf_odom_base 各有 48–49 个倒退时间戳,数据判 incomplete、验证 inconclusive(退出 11),原因是 WSL 的墙钟被 NTP 往回拨(§4)。用户重启 Windows、重新绑定防火墙规则后,11:41 那次 pass(退出 0,`artifacts/review-2026-10-03/runs/normal-20261003-114140`,代码 bf7f431)。
   - ③ 把 master 上的提交并进来:完成(37ea5cf)。并入前 master 比本分支多 8 个提交:6108b21、c2c195d、dae9412、09ed399、5a0cbf8 与已并入的 a3f28a3、4c6ebce、7f065f7、67f2562、8c0cd7f 内容相同(`docs/commit-map.tsv` 已在本分支);bad1ca4 是 D0–D5 合进 master 的合并提交;带来新内容的只有 7b73dcb(LICENSE、NOTICE,以及 AGENTS.md、README、plan.md、technical-overview.md 的发布说明)和 7f9c719(2026-10-03 的 README 修正,origin/master 仍是 v0.1.0 的 5a0cbf8)。AGENTS.md、README、plan.md、technical-overview.md 两边都改过:README 的审查状态取 7f9c719 的写法,但 master 版 README 里只对 v0.1.0 成立的说法(第 7 行版本说明、第 45 行和第 101–102 行"终端 Ctrl-C 到不了运行器"及其例外)按合并后的代码改写;technical-overview.md §16 还写着"进行中、尚未合入",一起更新。
   - ④ 一次合回 master(本地 `--no-ff`,在 master 的工作树里做;`git merge` 无冲突自动生成的合并提交不跑提交前检查,先自己跑 verify.sh),推送由用户做(`git push origin master chore/harness-cleanup`)。合并提交见 `git log master`。
2. **独立审查(Codex 分片)**,截至 2026-10-03:
   - 已出报告:D0 round1c-a(评测逻辑 analyze_attempt.py,5 条:3 Major、2 Minor)、round1c-b(录制、Nav2 启停、发目标脚本,9 条:7 Major、2 Minor),都在 `docs/review/2026-09-29-d0/`。
   - 未出报告:D0 round1c-c(2026-09-30 四次撞账户用量上限)、round1c-d、D1、D2 a/b、D3 a/b、D4、D5。Codex 提示最早 2026-10-06 14:51 才能再用。
   - 2026-09-30 起的排队进程(pid 35156)已经不在了,`docs/review/codex-queue.lock`(内容 35156)是残留:重启时 35156 若没被别的进程占用,队列直接接管;若被占用,队列以 3 拒绝启动,确认那个进程不是队列后再删掉这把锁。额度误判已随 `fix/review-round1` 并入本分支(a39147c),用本分支或合并后 master 的脚本启动即可。只排这 9 片,round1c-c 放到最后或再拆小:9/30 它三次都在额度刚恢复时开始,分别用了 101,577、67,191、70,720 tokens 仍没审完(round1c-a、round1c-b 审完只用了 80,134、74,234);同一片连续撞额度满 MaxAttempts 次(默认 4),整个队列就停下(退出 2),排在它后面的分片都不会跑。
   - 这 9 片的提示词用改写前的旧提交号读被审代码(19203e0、16aef89、c6cbdab、cfa8245、db5b161、d33d69c、02de625、24fa308),这些提交只在本机 refs/original 里:跑完前不删 refs/original,不做 reflog expire 或 gc --prune。
3. **处理报告**:逐条核实 → 只修有效项(在本分支)→ 重跑受影响的检查(verify.sh,需要时真实 Isaac)→ 记进该交付的 REVIEW.md → 交 Codex 复核修复范围,最多两轮。round1c-a 的 5 条已修(f618c84,随 `fix/review-round1` 并入本分支),还没记进 D0 的 REVIEW.md,也还没交 Codex 复核。round1c-b 的 9 条还没在 REVIEW.md 里逐条记录;修复在未合并的 `impl/shell`(见 §4),不在本分支。
4. **用户验收**:见 §1。

## 3. 决定记录

| 日期 | 决定 | 由谁 | 依据 |
| --- | --- | --- | --- |
| 2026-09-29 | 在官方不支持的配置(Windows 10 + 8 GB)上继续做完 D0,升级留到项目之后;所有记录标注 unsupported configuration | 用户 | GUI 已能开;用户明确指示 |
| 2026-09-29 | `git init` 本地仓库;master = 三份文档基线;D0 在 `feature/d0-environment` 上做 | Claude(默认做法,用户未反对) | harness pack 需要基线与可比对 diff;Codex `/review` 需要 Git |
| 2026-09-29 | fastdds.xml 放仓库内 `configs/network/`,而非计划文档建议的 `D:\robosim-assets\network` | Claude(默认做法,用户未反对) | 受版本管理、单一副本;计划文档 A2 的路径只是建议 |
| 2026-09-29 | 独立审查用 `codex exec`(新进程、只读),与 Apu 项目一致 | Claude(默认做法,用户未反对) | harness pack 默认分工 |
| 2026-09-29 | 三份文档保留带 "(1)" 的原名,不改名 | Claude | 不擅自改用户文件;入口写真实路径 |
| 2026-09-29 | 本轮不绑定 Obsidian 知识库 | Claude | 避免出现第四份计划;触发条件 = D1 之后需要跨会话知识库 |
| 2026-09-30 | 打开 Isaac 的 Python 执行服务(只监听 127.0.0.1、需要令牌),用于在 Isaac 内做接触检测 | 用户("要打开") | 计划 A5 要求碰撞判定;自动模式分类器曾拦下这项改动,用户明确同意后才做 |
| 2026-09-30 | 不等审查,D1–D5 连续做完;每个交付一个叠加分支,各自一份审查材料进队列 | 用户("先做D1吧 等审查太拖慢效率了""然后做完");分支与排队做法由 Claude 定 | Codex 额度窗口有限;各分片用 `git show <冻结提交>:<路径>` 读被审版本,不受后续提交影响 |
| 2026-09-30 | D5 的参数改动选 DWB `max_vel_x` 0.8→0.4,并新增情形 `normal_slow`;参数文件在运行目录派生,仓库里不维护改过的副本(派生文件随运行目录作为证据保存) | Claude | 预测可证伪(峰值速度、行驶段时长);不修改 NVIDIA 文件;运行器从运行中的节点读回核对 |
| 2026-09-30 | 批量运行期间的开发改在独立的 git worktree 里做 | Claude | 批量的每次运行都会记录 git 是否有未提交改动;不能让运行器正在用的文件在批量中途变化 |
| 2026-09-29 | D0 的 Codex 审查拆成 4 个分片排队(`run_codex_review_queue.ps1`);等待期间先做 D1,分支 `feature/d1-doctor` 从 `feature/d0-environment` 分出,D0 的修复之后合进来 | 用户要求加速("赶紧审查下 然后做完");具体做法由 Claude 定 | Codex 额度每个窗口约 10 万 token,两次整轮审查都没读完;分片提示词一律用 `git show 19203e0:<路径>` 读被审版本,不受后续提交影响 |
| 2026-09-29 | `start_isaac_ros2.ps1` 不预设 ROS_DISTRO(计划文档 B4 的启动块预设了它) | Claude | 本机 `isaac-sim.bat` 自动调用的 `setup_ros_env.bat` 只在 ROS_DISTRO 未设时才把自带的 jazzy 库加入 PATH;脚本只预设 RMW_IMPLEMENTATION、ROS_DOMAIN_ID、FASTRTPS_DEFAULT_PROFILES_FILE,启动后用 kit 日志核对实际值 |
| 2026-09-29 | 安装 ROS 时不做整体 `apt upgrade` | Claude | 项目规则:不做无关的系统升级;依赖被 hold 时再带 `--with-upgrade` 重跑并记录 |
| 2026-09-30 | 先发布 v0.1.0,审查修复暂停、之后再更新;代码用 MIT 许可证,NVIDIA 的部分按 Apache-2.0 写入 NOTICE;三份参考文档一起上传;提交作者邮箱改写为 GitHub noreply 地址并附提交号对照表;推送由用户执行 | 用户 | 用户要求"先别修了先发吧之后再更新" |
| 2026-10-03 | 整理文档与检查机制,不改产品逻辑:删除两份 harness pack 与 docs/harness-sources.md(不挪进 archive);需求文档移到 docs/reference/ 并注明 §0、B 作废;AGENTS.md 换成逐条核对过的新版,CLAUDE.md 只导入它;本文件只留四样内容;新增 verify.sh、提交前检查与 PreToolUse 拦截;改成单一的 `chore/harness-cleanup` 分支(见 §2) | 用户 | 资料包里有用的部分已提炼进 AGENTS.md 与审查提示词,原件用户手上有;archive 留在仓库里 agent 搜代码时照样会翻到,git 历史本身就是存档;叠加分支要先在各自分支修再往后合,plan.md 两头都改,容易冲突 |
| 2026-10-03 | 先把 `fix/review-round1` 并入 `chore/harness-cleanup`(代码以 fix 分支为准,文档结构以本分支为准);verify 通过、在真实 Isaac 上跑一次 normal 之后,把 master 的提交并进来,再一次合回 master;争取在 2026-10-06 14:51 额度恢复前合完,之后排队从合好的分支跑 | 用户 | 排队时不再纠结用哪条分支的脚本 |
| 2026-10-03 | README 的审查状态与退出码 20 的说明直接在 master 上改正(7f9c719),由用户推送 | 用户 | v0.1.0 已公开。核对后:已推送的 README 第 5 行本来就写明审查未完成,不实的是第 45 行"20 = 被 Ctrl-C 中断(已取消目标并收尾)",与它自己第 101 行"终端 Ctrl-C 到不了运行器"矛盾 |
| 2026-10-03 | 审查过程记录(codex-queue.log 新增的行、round1c-c 第 2–4 次尝试)单独提交(5947179);所有改动都提交,包括 practice-01(修复前代码的一次运行,05ba155) | 用户("所有改动都提交到github") | practice-01 的来源没有记录,`artifacts/practice-01/commands.md` 写明了能确认和不能确认的部分 |
| 2026-10-03 | 为 WSL 时钟问题重启 Windows(不停 timesyncd);重启后防火墙规则失效,由用户在管理员 PowerShell 重新绑定到 vEthernet (WSL);之后用合并后的代码跑真实 normal,pass | 用户("重启吧";执行管理员命令) | 重启后漂移方向反转为往前拨,不影响判定;真实复跑是合回 master 之前用户要求的一步 |

## 4. 未解决问题

**环境**

- WSL 的墙钟会被 NTP 拨动(2026-10-03 查明):WSL 的 VM 时钟比真实时间快或慢约 1.5–2%,方向每次 Windows 启动或睡眠醒来可能不同(07:06–07:32 睡眠醒来后快,11:21 重启后慢);WSL 里的 systemd-timesyncd(NTP,ntp.ubuntu.com)最短 32 s 校一次,快出或慢下的部分超出它能慢慢调的范围,每次直接把墙钟拨回约 0.5–0.7 s。Windows 时钟对 NTP 不漂移;WSL 的时钟源是 Hyper-V 提供的参考时钟,所以偏的是 Hyper-V 给 VM 的时间;重启 WSL 不能消除。rosbag 按接收时的墙钟排序:往回拨时,之后收到的消息排到前面的消息中间,录下的 /clock、odom、TF 出现倒退时间戳,数据判 incomplete(09:44 那次);往前拨只让一次接收间隔变长(11:41 那次最长 0.74 s,门槛 2 s),不影响判定。2026-09-30 的 31 次真实运行倒退时间戳都是 0,多半处在往前拨的状态。真实运行前先跑 `artifacts/review-2026-10-03/clock_probe.sh 90`:出现负值(往回拨)就先不跑,由用户决定处理办法(重启 Windows 可能翻转方向但不保证;或用 sudo 停掉 timesyncd,没试过)。证据与排查:`artifacts/review-2026-10-03/commands.md`。
- Windows 重启后 WSL 连不上 Isaac(2026-10-03 查明):防火墙规则 "RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)" 按 vEthernet (WSL) 网卡限定,Windows 重启会重建这块网卡,规则随之失效。症状:Isaac 正常(bridge 与 sim_control 都已启动),Isaac 的发现广播能到 WSL,但 WSL 看不到 Isaac 的话题和服务,sim.sh state 一直退出 3。处理:用户在管理员 PowerShell 执行 `Set-NetFirewallRule -DisplayName 'RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)' -InterfaceAlias 'vEthernet (WSL)'`,立即生效,不用重启 Isaac。每次重启都要做;改成不依赖网卡的规则(例如按 WSL 的地址段限定)待用户决定。agent 未提权读不了防火墙规则。

**审查与流程**

- Codex 审查没有完成,排队进程已停,见 §2。
- `impl/shell`(10 个提交,a51d041…4ff810e,2026-09-30 08:20–09:52)没有并入 `fix/review-round1`,也不在本分支。内容:Codex round1c-b 9 条的修复(提交说明按 codex-b-1…b-9 引用)、其余 D0 脚本按自身位置找检出(a51d041)、发目标按本次加载的地图核对、只停能证明是自己的录制器、stop_nav2 清理残留并保住退出码、队列原子锁(7b94a90)。最后两个提交是对复核意见 shell-rev-1、shell-rev-2 的返修,之后有没有再复核没有记录,也没有在真实 Isaac 上跑过。是否并入、何时并入待用户决定;并入后要重跑完整 verify.sh 和真实 Isaac。合并提交 5241837 的说明写着 "merged through … impl/shell",不对(不改写历史,以这里为准)。
- 从 worktree 运行时仍有两处用主工作区的文件:`dds_env.sh` 默认的 Fast DDS 配置是 `/mnt/d/RoboSim-Eval/configs/network/fastdds.xml`(假节点测试也用它,可用 `ROBOSIM_DDS_PROFILE` 指定);运行器调用的 `start_nav2.sh`、`stop_nav2.sh`、`record_d0.sh`、`stop_record.sh` 写死从 `/mnt/d/RoboSim-Eval` 加载 `ros_env.sh`(前三个还加载 `dds_env.sh`)。改成随检出的修复在未合并的 `impl/shell`(a51d041)。从 Windows 侧建的 worktree 运行时,WSL 里的 git 读不出检出信息,manifest.json 的 git 各项是 null,只有 code.repo 可用。
- verify.sh 用终端 Ctrl-C 停不下:每项检查在 `timeout` 自建的进程组里,SIGINT 只到 verify.sh 自己,正在跑的和后面的检查都会跑完(2026-10-03 实测,`artifacts/review-2026-10-03/verify_ctrlc_probe.py`)。要改得让检查只收到一次 SIGINT,还没做。
- Windows 睡眠(S3)会暂停 WSL,打断假节点测试和 doctor 的观察窗口(2026-10-03 07:06–07:32 一次,系统日志 Kernel-Power 42、130/131;runner-fake 的 cancel_ignored 因此失败);现在的 verify.sh 会在该行注明墙钟比 WSL 运行时间多走的秒数,重跑即可。
- D0 文档里已知、按约定留到与 Codex 意见一起改的不准确处(2026-10-03 对照代码和日志核实):
  - `docs/environment.md:64` 把 launch 退出码 1 与容器 SIGSEGV、rviz 退出写在一起,像是因果;run-04、run-05 的 nav2-launch.log 里,launch 退出码 1 来自它自己的异常 "Cannot shutdown a ROS adapter that is not running"。`scripts/wsl/start_nav2.sh` 第 10–11 行和 `stop_nav2.sh` 第 4–6 行的注释说 nav2-launch.meta 记录了包装进程的命令行;代码只记 boot_id 和包装进程启动时刻,命令行是停止时现查(要包含 `<run_dir>/nav2.exit`)。`docs/review/2026-09-29-d0/REVIEW.md` 的 S4 列 send_goal 退出码时漏了 3(目标位姿不空闲)和 4(找不到 action server)。
  - REVIEW.md S4 的"转录直接写文件,不经 tee"不准确:转录仍经一个加时间戳的 Python 管道追加到文件(去掉的是原来包住整段的 `| tee`),脚本靠 `CLIENT_RC=${PIPESTATUS[0]}` 取动作客户端的退出码(send_goal.sh 第 76–79、84 行)。
  - `artifacts/d0d/commands.md` 第 42 行(20:43:08)"子进程收到两次 SIGINT(直接 + launch 转发)"没有日志支持:run-01 的 nav2-launch.log 里每个子进程只有一条 signal_handler(第 386–389 行),没有 launch 的 "user interrupted with ctrl-c"(run-04 第 357 行有);launch 只在 rviz2 退出后向组件容器发过一次 SIGINT(第 524 行),容器在第 522 行已经 SIGSEGV,与第 44 行 run-03 查到的"launch 忽略 SIGINT"一致。`stop_nav2.sh` 第 7–8 行的注释沿用了这个说法;AGENTS.md 里同样的理由已在 2026-10-03 删去。
  - D3、D4 台账里的"约 38 s 卡住""接受后 5 s 取消"以 `docs/defect-record.md` 的缺陷 4 为准。

**审查确认的产品问题**(2026-09-30 Claude 多代理审查确认的 Major 和同类 Minor,原文见 docs/technical-overview.md §16.2):已由 `fix/review-round1` 修复并随 5241837 并入(收尾安全网、终端 Ctrl-C、按 ROS domain 的运行器锁、录制覆盖与运行器时刻核对、A5 起点终点检查与不可达的地图证据、接触客户端解码、报告的"未测量");固定输入测试与假节点测试通过,真实 Isaac 只跑过一次 normal(见 §2)。仍未解决的:

- 单次运行中关掉 `run_scenario.sh` 所在的终端窗口,运行器会被直接结束:不取消目标(Nav2 继续把机器人开向目标)、不确认停车、不收尾,Nav2 和记录器残留。这是终端 Ctrl-C 的修复(`timeout --foreground`)带来的:运行器留在终端的前台进程组,挂断时收到 SIGHUP,而它只处理 SIGINT、SIGTERM。2026-10-03 用替身进程在伪终端上实测过机制(`artifacts/review-2026-10-03/hup_probe.py`;不加 `--foreground` 时替身活了下来),真实运行器没有测。批量处理了 SIGHUP,不受影响。
- D0 常驻进程脚本:Codex round1c-b 的 9 条所指的代码在本分支照旧(record_d0.sh、stop_record.sh、start_nav2.sh、stop_nav2.sh、send_goal.sh、map_overview.sh 自被审版本 19203e0 起没改过),还没逐条记进 REVIEW.md;修复在未合并的 `impl/shell`(见上文)。
- 文档:本分支 README 第 43 行"20 = 被 Ctrl-C 中断(已取消目标并收尾)"与合并后的代码一致;第 85 行已不说审查完成,但"其余分片…仍在排队"已过时(排队进程已不在,见 §2),合并 master 时取 7f9c719 的写法。technical-overview.md §16 还写着"进行中、尚未合入"。已推送的 v0.1.0(origin/master = 5a0cbf8)没有"独立审查已完成"的说法(第 5 行写明未完成),不实的是第 45 行"已取消目标并收尾";本地 master 的 7f9c719 已改正,等用户推送。

**已知问题**

- Nav2 停止时组件容器在清理阶段 SIGSEGV("Magick: abort due to signal 11",exit -6):run-01、run-04、run-05 三次都出现。rviz2 每次退出方式不同:run-01 为 -6,run-04 为 -9(launch 在 SIGINT/SIGTERM 超时后 SIGKILL),run-05 为 -11。launch 退出码 1 只在 run-04、run-05 记录到;run-01 用的是旧脚本,没有记录。三次都没有残留进程,不影响导航与记录。
- attempt-01 是用修复前的记录与停止脚本采集的:没有记录器退出码文件;4 个文本流比 bag 多跑了约 3 分钟,最后手动按会话停止。bag 本身完整,分析只用 bag。
- RViz 在 WSLg 下启动时报一次 GLSL 链接错误(`indexed_8bit_image`),地图与激光照常显示。
- 首次导航的反馈转录 goal-202437.txt 为 2.7 MB(CLI 高频反馈);以后可只保存摘要。

**机制未查明**

- "开头卡住":D3 开接触监视的 3 次正常路线中 2 次、D4 可到达的 6 次中 5 次,发目标后约 37 s 仿真时间不动,Nav2 恢复后到达。机器人开头正好背对全局路径;DWB 常选最小转向档 +0.0368 rad/s,直接实验证实机器人对它基本不转;DWB 为何把它打分最高未查明(运行时没有记录各评分项)。因此平均用时主要反映卡住,不是导航速度。见 artifacts/d3/commands.md、artifacts/d4/commands.md。
- 接触监视是否改变"开头卡住"出现的概率:开与不开两组的样本和路径起点分布都不同,无法归因。
- D5 的 normal_slow 两次开头各有一次 NavFn 规划失败("Failed to create a plan from potential when a legal potential was found"),各触发一次恢复。
- D5:里程计的角速度在 max_vel_x 0.8 m/s 时会超过 max_vel_theta 0.7(实测 1.01–1.02 rad/s)。
- D5 normal_slow 第 1 次出现一次自发的 Isaac 卡顿:三路数据同时停 2.19 s 墙钟,仿真时间只前进一步;评测按规则判 inconclusive,原因未查;D4 的 9 次没有出现。

**未验证**

- RViz 的 Nav2 Goal 发目标路径、`record_d0.sh` 以外的记录方式、Heightmap 回退路线都没有执行过。
- 终端 Ctrl-C 只在伪终端上测过(tests/test_runner_ctrl_c.py、tests/test_batch.py、test_runner_fake.sh 的 pty_ctrl_c),经 wsl.exe 的 Windows 控制台没有实测。
- `/chassis/odom` 是理想里程计(`IsaacComputeOdometry`,无轮速与噪声模型):适合做评测侧的位置核对,不能证明真实定位的鲁棒性(计划文档 A5)。
- 每个情形只有少量工程试运行;不据此声称任何导航性能或成功率。
