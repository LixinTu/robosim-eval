# RoboSim Eval — 计划与状态(唯一活计划)

> 只记四样:状态、当前任务、决定记录、未解决问题。需求与验收原文在 `docs/reference/RoboSim-Eval-Plan-and-Setup-ZH.md`(2026-09-29 冻结;§0 与 B 已作废,A4–A6 仍是验收依据);做事的规则在 AGENTS.md,怎么跑在 docs/setup.md。2026-10-03 删去的旧章节(本轮范围、执行机制、最小组合、阶段计划、验收清单、偏差记录、风险)和已有结论的发现,用 `git show cb7c6a4:docs/plan.md` 查看。

## 1. 状态

| 交付 | 状态 | 证据 | 阻塞 / 备注 |
| --- | --- | --- | --- |
| 阶段 0 · 唯一计划与入口 | 完成(2026-09-29) | 基线 commit `dbf67ce`(master);分支 `feature/d0-environment`;AGENTS.md / CLAUDE.md / docs/plan.md / docs/harness-sources.md(2026-10-03 删除,见 git 历史 cb7c6a4)/ artifacts/README.md | — |
| D0a · 环境证据 | 完成(2026-09-29 19:02–19:04) | docs/environment.md;artifacts/d0a/(两侧探测原始输出 + commands.md) | 门槛 1→2 通过;发现:WSL 内无 ROS 2,sudo 需密码 |
| D0b · ROS 2 Jazzy + 6.1.0 示例工作区 | 完成(2026-09-29 19:16–19:30) | artifacts/d0b/commands.md(安装日志、check-ros-install、talker/listener ×2、rviz2 测试、setup-workspace.log) | 门槛 2→3 通过。工作区 `~/robotics/vendor/isaac-ros-6.1`,HEAD a9e8471…;安装脚本首跑退出码 1 是校验步骤的 `set -u` 缺陷(已修),安装本身成功 |
| D0c · Windows↔WSL 桥接 + Nova Carter 场景 | 完成(2026-09-29 19:35–20:12) | artifacts/d0c/commands.md;probe-04-playing/(/clock 25–26 Hz、/chassis/odom 25.8 Hz、/tf 25–26 Hz、/front_3d_lidar/lidar_points 2.4–2.8 Hz、tf2_echo odom→base_link);clock-continuity-01;clock-pause-test-02(暂停 29 s 时钟停、恢复后继续);bridge-check-01/02;kit-udp-endpoints-01;diag-01 | 门槛 3→4 通过。排障:Windows 防火墙阻断 WSL→kit.exe 入站(用户以管理员加一条限定规则后解决);首次 Play 后 7 s 时间线被停止(重新 Play 解决)。发现:示例场景不发布 2D 雷达扫描(params 的局部代价地图两路来源无数据,D0d 记偏差);USD 动画时间线每 ~41 s 循环但仿真时钟不受影响;显存为几次点采样(空场景 3124–3128 MiB、Play 后 5 s 3754 MiB、Nav2 运行时 Isaac 界面显示 3.9 GiB),未做连续测量 |
| D0d · 一次真实 A→B | 完成(2026-09-29 20:13–20:52) | artifacts/d0d/commands.md;run-01/(nav2-launch.log、ready-check-01、map-overview、rviz 截图、usd-inspection);run-01/attempt-01/(goal-202437.txt、result.json、trajectory.csv、bag-info、文本流);run-02/03/04-stoptest(停止路径验证) | 目标 map (-4.0,-1.0,yaw 0) 由 CLI action client 发送:SUCCEEDED、error_code 0、0 次恢复、8.47 s 仿真时间、停稳确认;**AMCL 独立来源**(理想里程计 + USD 出生位姿)在停稳确认时刻误差 0.091 m,AMCL 估计 0.231 m → validation=pass(内部预审后用新分析脚本重算)。当时的发现已并入 docs/setup.md 的"本机实测特性"与 §4,原文见 cb7c6a4 版的 §9 |
| D0 交付 + 独立审查 | 进行中:**待独立审查** | docs/setup.md;docs/review/2026-09-29-d0-handoff.md;docs/review/2026-09-29-d0/REVIEW.md | Codex 第 1 轮两次因账户用量上限中止、无意见(20:59 用 82,531 tokens;23:23 重跑用 102,685 tokens);同一范围拆成 4 个分片:round1c-a、round1c-b 已出报告(5 条、9 条,待逐条核实),round1c-c 撞账户用量上限、round1c-d 未跑,见 §2;Claude 内部预审第 2 次完成(38 条,确认 35 条),有效项已修复并回归,见 REVIEW.md |
| D1 doctor | 实现与验证完成(2026-09-29 23:3x–23:49),**待独立审查**与用户验收 | 分支 `feature/d1-doctor`;`robosim_eval/doctor*.py`、`configs/baseline.yaml`、`scripts/wsl/doctor.sh`;证据 `artifacts/d1/commands.md` | 固定输入测试 37 passed、改坏检查 7/7、假节点测试 6/6;真实 Isaac:运行时退出 0,用户按 ⏸ 后 2 s 窗口判"不推进"退出 10,恢复后退出 0 |
| D2 单次运行器 | 实现与验证完成(2026-09-30 00:1x–00:47),**待独立审查**与用户验收 | 分支 `feature/d2-runner`;`robosim_eval/runner*.py`、`sim_adapter.py`、`run_io.py`;`scripts/wsl/run_scenario.sh`、`sim.sh`;证据 `artifacts/d2/commands.md` | 固定输入测试 77 passed;运行器假节点测试 8/8;真实 Isaac:正常 A→B reached(真值误差 0.264 m),导航中 SIGINT → 取消、停车、收尾(interrupted);Isaac 由 sim_control 复位、加载场景、读真值,不再需要 GUI 点击 |
| D3 判定与失败处理 | 实现与验证完成(2026-09-30 00:5x–01:29),**待独立审查**与用户验收 | 分支 `feature/d3-verdicts`;`robosim_eval/evaluator.py`、`contacts.py`、`kit/contact_monitor.py`;证据 `artifacts/d3/commands.md`;缺陷记录 `docs/defect-record.md` | 固定输入测试 109 passed;判定模块改坏检查 8/8(含 4 种必做的坏数据);真实 Isaac:正常、绕行、不可达、取消、超时 pass,断流正确判 inconclusive,碰撞抓到轮子与矮箱子的接触判 fail;修复一个运行器缺陷(复位前 odom 残留) |
| D4 批量复跑 | 实现与验证完成(2026-09-30 01:30–02:0x),**待独立审查**与用户验收 | 分支 `feature/d4-batch`;`robosim_eval/batch.py`、`report.py`、`scripts/wsl/run_batch.sh`;证据 `artifacts/d4/commands.md`、`artifacts/d4/batch-20260930-013010/runs/report.html` | 9 次全部留档、全部 pass(normal 3/3 到达、bypass 3/3 到达且未碰箱子、unreachable 3/3 判不可达);每次复位后真值距出生点 0.07 mm;报告改进 1 处(列出全部 commit、恢复次数列);"开头卡住"查到大部分机制(见 §4) |
| D5 作品交付 | 实现与演示完成(2026-09-30 01:3x–02:3x),**待独立审查**与用户验收 | 分支 `feature/d5-demo`;`README.md`、`docs/demo.md`、`robosim_eval/nav2_params.py`;证据 `artifacts/d5/commands.md` | README 按新终端逐字执行通过;三个演示:正常导航并打开记录(pass)、取消案例及解释(pass)、参数改动 max_vel_x 0.8→0.4 的事先预测与复跑对比(峰值速度、平均速度、行驶段、到达误差符合预测;路程与最大角速度两条预测不成立,见 docs/demo.md);修复缺陷 3(场景未加载时接触监视装不上)与缺陷 4(接受目标时的仿真时间是旧的);固定输入测试 128 passed,运行器假节点测试 10/10 |

**尚未完成的验收**(其余各项的证据见上表):

- 独立审查:D0–D5 都没有完成,见 §2。
- 用户验收:D0 三步(新终端启动后看到地图与实时数据;发目标,看到达并打开记录核对;暂停看数据停,恢复看数据回来);D1–D5 按 README 与 docs/demo.md 的操作复现。

## 2. 当前任务

**分支做法(2026-10-03 起)**:文档整理和之后的全部审查修复都在 `chore/harness-cleanup` 上做(从 `feature/d5-demo` 分出),不再回到各交付分支改再向后合;审查与验收完成后一次合进 master(本地 `--no-ff`,推送由用户自己做)。`feature/d0-environment` … `feature/d5-demo` 不再改动,只作为被审的冻结版本:分片提示词用 `git show <冻结提交>:<路径>` 读被审代码,不受这条分支上的提交影响。

1. **独立审查(Codex 分片)**,截至 2026-10-03:
   - 已出报告:D0 round1c-a(评测逻辑 analyze_attempt.py,5 条:3 Major、2 Minor)、round1c-b(录制、Nav2 启停、发目标脚本,9 条:7 Major、2 Minor),都在 `docs/review/2026-09-29-d0/`。
   - 未出报告:D0 round1c-c(2026-09-30 四次撞账户用量上限)、round1c-d、D1、D2 a/b、D3 a/b、D4、D5。Codex 提示最早 2026-10-06 14:51 才能再用。
   - 2026-09-30 起的排队进程(pid 35156)已经不在了,`docs/review/codex-queue.lock` 是残留。额度恢复后重启队列,只排这 9 片;重启前先处理 §4 里排队脚本的额度误判。
   - 这 9 片的提示词用改写前的旧提交号读被审代码(19203e0、16aef89、c6cbdab、cfa8245、db5b161、d33d69c、02de625、24fa308),这些提交只在本机 refs/original 里:跑完前不删 refs/original,不做 reflog expire 或 gc --prune。
2. **处理报告**:逐条核实 → 只修有效项(在本分支)→ 重跑受影响的检查(verify.sh,需要时真实 Isaac)→ 记进该交付的 REVIEW.md → 交 Codex 复核修复范围,最多两轮。round1c-a 的 5 条已在 `fix/review-round1` 上修过(f618c84),还没交 Codex 复核,也没在真实 Isaac 上复跑;round1c-b 的 9 条还没逐条核实。
3. **用户验收**:见 §1。
4. **合并**:审查与验收都完成后,`chore/harness-cleanup` 一次合进 master。master 比本分支多 7 个提交(v0.1.0 发布:合并 D0–D5、文档修正、LICENSE、NOTICE、`docs/commit-map.tsv` 等),AGENTS.md、README、plan.md、technical-overview.md 两边都改过,合并时要把 master 上的内容并进来。

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
| 2026-09-30 | D5 的参数改动选 DWB `max_vel_x` 0.8→0.4,并新增情形 `normal_slow`;参数文件在运行目录派生,不复制进仓库 | Claude | 预测可证伪(峰值速度、行驶段时长);不修改 NVIDIA 文件;运行器从运行中的节点读回核对 |
| 2026-09-30 | 批量运行期间的开发改在独立的 git worktree 里做 | Claude | 批量的每次运行都会记录 git 是否有未提交改动;不能让运行器正在用的文件在批量中途变化 |
| 2026-09-29 | D0 的 Codex 审查拆成 4 个分片排队(`run_codex_review_queue.ps1`);等待期间先做 D1,分支 `feature/d1-doctor` 从 `feature/d0-environment` 分出,D0 的修复之后合进来 | 用户要求加速("赶紧审查下 然后做完");具体做法由 Claude 定 | Codex 额度每个窗口约 10 万 token,两次整轮审查都没读完;分片提示词一律用 `git show 19203e0:<路径>` 读被审版本,不受后续提交影响 |
| 2026-09-29 | `start_isaac_ros2.ps1` 不预设 ROS_DISTRO(计划文档 B4 的启动块预设了它) | Claude | 本机 `isaac-sim.bat` 自动调用的 `setup_ros_env.bat` 只在 ROS_DISTRO 未设时才把自带的 jazzy 库加入 PATH;脚本只预设 RMW_IMPLEMENTATION、ROS_DOMAIN_ID、FASTRTPS_DEFAULT_PROFILES_FILE,启动后用 kit 日志核对实际值 |
| 2026-09-29 | 安装 ROS 时不做整体 `apt upgrade` | Claude | 项目规则:不做无关的系统升级;依赖被 hold 时再带 `--with-upgrade` 重跑并记录 |
| 2026-10-03 | 整理文档与检查机制,不改产品逻辑:删除两份 harness pack 与 docs/harness-sources.md(不挪进 archive);需求文档移到 docs/reference/ 并注明 §0、B 作废;AGENTS.md 换成逐条核对过的新版,CLAUDE.md 只导入它;本文件只留四样内容;新增 verify.sh、提交前检查与 PreToolUse 拦截;改成单一的 `chore/harness-cleanup` 分支(见 §2) | 用户 | 资料包里有用的部分已提炼进 AGENTS.md 与审查提示词,原件用户手上有;archive 留在仓库里 agent 搜代码时照样会翻到,git 历史本身就是存档;叠加分支要先在各自分支修再往后合,plan.md 两头都改,容易冲突 |

## 4. 未解决问题

**审查与流程**

- Codex 审查没有完成,排队进程已停,见 §2。
- 排队脚本会把 Codex 读到的文件内容里出现的 "hit your usage limit" 也当成撞了额度:本分支的 `run_codex_review.ps1` 第 25 行就含这句,而 D0 round1c-c 要审它,成功的审查可能被当成失败而重试。修复在 `fix/review-round1` 的 a39147c,还不在本分支;2026-09-30 的队列是从那条分支的工作树跑的。
- `fix/review-round1` 上的 42 个提交(2026-09-30 内部审查与 round1c-a 的修复;固定输入测试与假节点测试通过,未在真实 Isaac 上复跑)不在本分支,怎么并入待定。
- `scripts/wsl/test_doctor_fake.sh` 写死了 `/mnt/d/RoboSim-Eval`:在别的工作树里跑 verify.sh,doctor 假节点测试测的仍是主工作区的代码(verify 记录的表头会注明)。
- Windows 休眠会打断假节点测试和 doctor 的观察窗口(2026-10-03 07:06–07:32 一次,runner-fake 的 cancel_ignored 因此失败);verify.sh 会在该行注明,重跑即可。
- D0 文档里已知、按约定留到与 Codex 意见一起改的不准确处(2026-10-03 对照代码和日志核实过的,和还没核实的分开写):
  - 已核实:`docs/environment.md:64` 把 launch 退出码 1 与容器 SIGSEGV、rviz 退出写在一起,像是因果;run-04、run-05 的 nav2-launch.log 里,launch 退出码 1 来自它自己的异常 "Cannot shutdown a ROS adapter that is not running"。`scripts/wsl/start_nav2.sh` 第 10–11 行和 `stop_nav2.sh` 第 4–6 行的注释说 nav2-launch.meta 记录了包装进程的命令行;代码只记 boot_id 和包装进程启动时刻,命令行是停止时现查(要包含 `<run_dir>/nav2.exit`)。`docs/review/2026-09-29-d0/REVIEW.md` 的 S4 列 send_goal 退出码时漏了 3(目标位姿不空闲)和 4(找不到 action server)。
  - 未核实:REVIEW.md S4 把保住退出码归功于"转录不经 tee"(另有记录说实际靠 PIPESTATUS[0]);`artifacts/d0d/commands.md` 第 42 行(20:43:08)说子进程收到两次 SIGINT。
  - D3、D4 台账里的"约 38 s 卡住""接受后 5 s 取消"以 `docs/defect-record.md` 的缺陷 4 为准。
  - `docs/setup.md` 里的同类说法已在 2026-10-03 的整理中改正。

**审查确认、本分支照旧存在的产品问题**(2026-09-30 Claude 多代理审查确认的 Major 和同类 Minor,以及 Codex 自评为 Major、待逐条复核的 D0 脚本问题;原文见 `git show master:docs/technical-overview.md` 的 §16.2,修复大多在 `fix/review-round1` 上,见上文)

- 收尾不完整:在发目标阶段被中断、或等接受超时时,已发出的目标不会被取消,也不确认停车(退出 20 或 30),批量照常继续;目标已接受后出现内部错误时同样如此(退出 30);收尾某一步抛异常时,后面的停录制、停 Nav2、写 result.json 会被跳过。
- 终端 Ctrl-C 到不了运行器和批量(`run_scenario.sh`、`run_batch.sh` 的 `timeout` 没加 `--foreground`,在伪终端上复现);中断办法见 AGENTS.md。
- 两个运行器可以同时跑,没有互斥:第二个会复位正在用的仿真、清空共享的接触缓存。
- 数据完整性只看 bag 自己:bag 提前结束或缺"目标已接受"的状态时,数据仍判 complete。
- 运行器没有实现 A5 的"任务开始时验证起点和目标位于允许区域";预设不可达只看配置里的标签,不核对离线证据。
- 接触客户端在代码页 936 下遇到未捕获的 .NET 错误时会崩(UnicodeDecodeError 没有被捕获):发生在装接触监视时,这次运行判出错(30);发生在收尾取接触数据时,后面的停录制、停 Nav2、写 result.json 被跳过。
- 报告:接触没有实测的运行,碰撞列也显示 0。
- D0 常驻进程脚本:Codex round1c-b 的 9 条(见 §2),待逐条核实。
- 文档:README.md 第 41 行把退出码 20 写成"已取消目标并收尾",上面第一条的路径上不成立;第 83 行写"独立审查由 Codex CLI 完成",实际没有完成。

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
- `/chassis/odom` 是理想里程计(`IsaacComputeOdometry`,无轮速与噪声模型):适合做评测侧的位置核对,不能证明真实定位的鲁棒性(计划文档 A5)。
- 每个情形只有少量工程试运行;不据此声称任何导航性能或成功率。
