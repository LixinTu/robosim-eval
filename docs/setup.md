# 本机启动、运行与关闭(D0–D5)

本机是 Isaac Sim 6.1 官方不支持的配置(Windows 10 + 8 GB 显存),下面的内容只表示"在本机实测可用"(D0、D1 于 2026-09-29,D2–D5 于 2026-09-30,verify.sh 与提交前检查于 2026-10-03),不表示普遍可用。2026-10-03 合并 `fix/review-round1` 之后,运行锁、终端 Ctrl-C、收尾兜底取消、地图检查、批量中止规则等新行为主要由 verify.sh 的固定输入测试和假节点测试验证(`artifacts/verify/20261003-093557`);真实 Isaac 上只跑过一次 normal(`artifacts/review-2026-10-03/commands.md`):地图检查通过、正常收尾,退出 11,因 WSL 的墙钟被往回拨、录下的消息时间戳倒退而判数据不完整,见该记录。D0–D5 每条命令的原始记录与退出码见 `artifacts/d0a..d0d`、`artifacts/d1..d5` 的 commands.md;verify.sh 每次运行自动写 `artifacts/verify/<时间>/commands.md`(默认不进 Git,入库的只有 20261003-070428、-074935、-075258、-093557 四份);提交前检查的启用和一次被它拒绝的提交见提交 2784ec5 的说明。正常使用走自动路径(`run_scenario.sh`、`run_batch.sh`);D0 时手动串脚本的流程放在文末附录,只在调试时用。

## 一次性前提(已完成,重装时才需要)

| 项目 | 状态 | 怎么做 |
| --- | --- | --- |
| Isaac Sim 6.1.0 | 已装在 `D:\isaac-sim-standalone-6.1.0-windows-x86_64` | 不重装 |
| Windows 防火墙规则 "RoboSim Eval: WSL -> Isaac Sim kit.exe (UDP)" | 已建(入站 / UDP / 仅 kit.exe / 仅 vEthernet (WSL)) | 管理员 PowerShell:`powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\allow_wsl_to_isaac_firewall.ps1`(可重复运行;删除见脚本头) |
| WSL `Ubuntu` 内 ROS 2 Jazzy + Nav2 + 依赖闭包 | 已装 | Ubuntu 终端(需 sudo 密码):`bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh` |
| 钉住工作区 `~/robotics/vendor/isaac-ros-6.1`(IsaacSim-6.1.0 @ a9e8471)+ `colcon build --packages-up-to carter_navigation` | 已建 | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/setup_workspace.sh`。可重跑:已有检出只核对、不重置(2026-09-29 重跑过一次,退出 0,见 artifacts/d0d/commands.md);退出 4 = HEAD 不是钉住的提交,5 = 检出有改动,6 = rosdep 要装新包(需 sudo,先补进 install_ros2_jazzy.sh),7 = rosdep 模拟失败。默认日志是已入库的 `artifacts/d0b/setup-workspace.log`(追加)和 `setup-workspace.exit`(覆盖),重跑前先设 `ROBOSIM_SETUP_LOG=<别处>/setup-workspace.log`,不动 D0b 证据 |
| 安装自检 | PASS | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_ros_install.sh` |
| 提交前检查(每个克隆一次) | 本克隆已设(写在 .git/config,所有工作树共用;相对路径按提交所在工作树的根目录找,检出里没有 `scripts/git-hooks/pre-commit` 的工作树提交时不跑任何检查,2026-10-03 时 master、fix/review-round1 等 7 个链接工作树都是这样) | `git config core.hooksPath scripts/git-hooks`:之后在含有该钩子的检出里,每次 `git commit` 先跑 `verify.sh --fast`,失败就拒绝提交 |

## 离线检查(不需要仿真)

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/verify.sh          # 固定输入测试 + doctor、运行器假节点测试
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/verify.sh --fast   # 只跑固定输入测试(提交前检查跑的就是它)
```

每项检查一结束就在 `artifacts/verify/<时间>/commands.md` 记一行(artifacts/README.md 的七栏:时间、命令、shell、cwd、退出码、日志/样本、备注;备注是 PASS/FAIL 和测试摘要),末行写结论;日志和假节点测试的样本目录(doctor-fake/、runner-fake/)放在同一目录。退出码:0 全部通过;1 至少一项失败(超时限的也算失败,记 124;SIGINT 后 10 s 仍不退出、被强杀的记 137);2 用法错误、记录建不起来,或另一个完整检查正在跑(只有完整模式加锁,`--fast` 不受影响)。测试有多少条、结果如何,以最近一次记录为准,本文不写死。假节点测试用 ROS domain 42,不影响正在运行的 Isaac;完整运行约 6 分钟(2026-10-03 合并后:固定输入测试约 1 分钟、doctor 假节点约 1 分钟、运行器假节点约 4 分钟);`--fast` 约 1 分钟,提交前检查也要等这么久。终端 Ctrl-C 停不下 verify.sh:每项检查在 `timeout` 自建的进程组里,SIGINT 只到 verify.sh 自己,正在跑的和后面的检查都会跑完(2026-10-03 实测)。记录默认不进 Git,要作为证据保留时 `git add -f`。检查期间 Windows 睡眠会打断假节点测试,记录里会注明,重跑即可。

## 终端约定

| 终端 | 用途 | 环境 |
| --- | --- | --- |
| Windows 普通 PowerShell(非管理员) | 启动 Isaac Sim(这个窗口一直被占着,直到 Isaac 退出);从另开的 PowerShell 窗口调用 WSL 脚本 | `start_isaac_ros2.ps1` 只在它自己的进程里给 Isaac 设置 RMW_IMPLEMENTATION=rmw_fastrtps_cpp、ROS_DOMAIN_ID=0、FASTRTPS_DEFAULT_PROFILES_FILE=`D:\RoboSim-Eval\configs\network\fastdds.xml`,并清掉 ROS_LOCALHOST_ONLY;**不预设 ROS_DISTRO**(让 isaac-sim.bat 自动调用的 setup_ros_env.bat 加载自带 jazzy 库)。这些变量不留在终端里,也不传进 WSL;WSL 脚本由 ros_env.sh、dds_env.sh 自己设置,调用它们的窗口不用预设任何变量 |
| WSL Ubuntu(从 PowerShell `wsl -d Ubuntu`,或 Windows 侧直接 `wsl -d Ubuntu -- bash -l <脚本>`) | Nav2、RViz、探测、记录 | 交互终端里先 `source /mnt/d/RoboSim-Eval/scripts/wsl/ros_env.sh --full`(`--base-only` 只加载 /opt/ros/jazzy)再 `source /mnt/d/RoboSim-Eval/scripts/wsl/dds_env.sh`;各脚本内部已用显式模式自动 source |
| 管理员 PowerShell | 仅防火墙规则 | — |

注意(2026-10-03 实测):

- 不带 `-e` 时(带不带 `--` 都一样),wsl 把后面的整行交给 WSL 默认 shell 再解析一遍:`$x`、`$?` 被提前展开,引号被重新解析(`wsl -d Ubuntu -- bash -c 'false; echo $?'` 输出 0,改用 `-e` 输出 1)。从 PowerShell 和 Git Bash 调都一样,所以一律调脚本文件;实在要内联用 `wsl -d Ubuntu -e bash -c '...'`,下面两条对 `-e` 照样适用。
- 从 Git Bash 调时还要加 `MSYS_NO_PATHCONV=1`(或者在 D:\RoboSim-Eval 下用相对路径,如 `bash -l scripts/wsl/<脚本>.sh`,WSL 的 cwd 就是 /mnt/d/RoboSim-Eval):否则以 `/` 开头的参数(脚本路径、`--out /mnt/d/...`)以及 `--out=/mnt/d/...`、`X=/path` 会被改写成 `C:/Program Files/Git/...`;一个参数里的 `"/World/..."` 也会被改,用 `-e` 也一样(D3 从 Git Bash 调 isaac_py.ps1 时 `/World/...` 就被改过,见 artifacts/d3/commands.md)。
- 从 PowerShell 内联时,双引号里的 `$?`、`$HOME` 等先被 PowerShell 展开(`"echo $? $HOME"` 变成 `echo True C:\Users\Administrator`);PowerShell 5.1 把参数传给原生程序时不转义其中的双引号,对方解析后双引号丢失,参数还会在空格处被拆开(`'echo "a  b" end'` 到对方是 `echo a`、`b end` 两个参数)。

## 自动路径

### 1. 启动 Isaac Sim(Windows,普通 PowerShell)

```powershell
powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\start_isaac_ros2.ps1 -PythonServer
```

先 `Get-Process kit` 确认没有实例在跑,再在新开的普通 PowerShell 窗口里运行(agent 用 `Start-Process` 新开窗口):脚本一直占着窗口,直到 Isaac 退出。启动后轮询 `sim.sh state`,等它退出 0 再开始运行:sim_control 服务出现之前 sim.sh 退出 3,这时开始的运行会按出错收尾(退出 30)。脚本检查路径与 XML、拒绝在已有 kit.exe 时再开一份,然后带 ROS 2 bridge 和 sim_control 扩展(ROS 2 simulation_interfaces 服务;`-NoSimControl` 可关掉)启动。`-PythonServer` 另外打开只监听 127.0.0.1、需要令牌的 Python 执行服务,运行器靠它在 Isaac 内做接触检测;不加时运行照常进行、不报错,但安全结论只能是 unknown,验证结论最多 inconclusive(退出 11),不会 pass。不需要在 GUI 里加载场景或按 Play:运行器发现场景没加载会自己加载,再通过 sim_control 复位。

核对 bridge(可选):`powershell -ExecutionPolicy Bypass -File D:\RoboSim-Eval\scripts\windows\check_isaac_bridge.ps1` → 日志应有 "ROS bridge extension isaacsim.ros2.bridge enabled successfully"。

### 2. 一次运行(D2–D3)

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh normal        # 结果默认在 artifacts/d2/runs/
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh collision --out /mnt/d/RoboSim-Eval/artifacts/d3/runs
```

`run_scenario.sh <情形> [--out <目录>] [--config <yaml>]` 依次:在钉住的 Nav2 地图上核对起点和目标在允许区域内、目标可达(不满足就按出错收尾;预设不可达情形不要求可达,改为在这里取得"无路径"证据)→(场景没加载时先加载)→ 复位场景,用真值核对机器人回到出生点,并核对 `/World/RoboSimObstacles` 下没有残留 → 放情形的障碍物并读回核对 → doctor → 启动 Nav2 并等就绪 → 开始录制 → 发目标 → 监控超时与中断 → 确认停车 → 收尾:恢复注入的暂停;发出的目标还没有终态就先取消,停车还没确认就再确认;然后取接触数据、停止录制、离线分析、停止 Nav2、写 result.json(每一步单独捕获异常,一步出错不跳过后面的步骤)。墙钟硬上限 1500 s,到时发 SIGINT,120 s 后仍在才强杀。情形与超时在 `configs/baseline.yaml` 的 `run`、`scenarios` 两节。

同一时间只跑一个 `run_scenario.sh` 或 `run_batch.sh`。运行器开始前取得按 ROS domain 的独占锁(WSL 里的 `/tmp/robosim_eval/runner-domain-<id>.lock`,记着占用者的 pid 和运行目录;进程一结束就释放,被强杀也不会留下失效的锁);锁被占时,新的运行器不建运行目录、不碰仿真,退出 2。批量自己不持锁,只有正在跑的那次尝试持锁:两次尝试之间另起的 `run_scenario.sh` 能拿到锁,批量的下一次就会被拒,批量以 2 停止,余下的不跑,所以批量期间也不要另起运行。`sim.sh` 不取锁,运行中仍不要调它的 load、play、pause、stop、reset。

中断一次运行:在运行它的终端按 Ctrl-C(`run_scenario.sh` 用 `timeout --foreground`,Ctrl-C 能到运行器;在伪终端上由 verify.sh 的运行器假节点测试 pty_ctrl_c 和 tests/test_runner_ctrl_c.py 验证过,真实 Windows 控制台没有测),或从另一个终端执行 `wsl -d Ubuntu -- pkill -INT -f robosim_eval.runner`。目标发出之前被中断,就不再发目标;已经发出时,先等 Nav2 应答,接受了就取消并确认停车(被拒绝则不用取消);收尾后退出 20。取消或停车没确认时退出 31。目标已在取消中或已有终态之后才到的中断不记为中断,运行照常走完,退出码按判定。收到中断后最多再等 120 s,仍没结束就被强杀(137)。

运行中不要关掉运行 `run_scenario.sh` 的终端窗口:关窗口(挂断)时运行器收到 SIGHUP,而它只处理 SIGINT、SIGTERM,所以会被直接结束:不取消目标(Nav2 会继续执行它)、不确认停车、不收尾,Nav2 和记录器残留,按"关闭"一节处理。这个机制 2026-10-03 用替身进程在伪终端上实测过(`artifacts/review-2026-10-03/hup_probe.py`),真实运行器没有测。批量不同:关窗口时当前这次照常跑完、收尾,然后批量停止(见第 4 节)。

每次运行一个目录 `<out>/<情形>-<时间>/`:manifest.json、config.resolved.yaml、events.jsonl、goal-*.txt、rosbag/、trajectory.csv、result.json,以及各脚本的输出。

| 退出码 | 含义 |
| --- | --- |
| 0 / 10 / 11 | 流程完整;评测结论分别为 pass / fail / inconclusive |
| 20 | 被中断,已收尾。目标发出之前被中断时不发目标;发出之后被中断时先等 Nav2 应答,接受了就取消并确认停车(被拒绝则不用取消)。取消或停车没确认时是 31,不是 20;目标已在取消中或已有终态后才到的中断不改变退出码 |
| 30 | 出错(例如复位核验或 doctor 失败、Nav2 没有就绪) |
| 31 | 出错且应中止后续批次:取消或停车没有确认(包括收尾时兜底取消已发出、还没有终态的目标)、注入的暂停没能恢复、记录器或 Nav2 没确认停下、启动前发现已有 Nav2 在跑或查不了(start_nav2.sh 退出 3) |
| 2 | 情形名不存在、参数写错、配置或环境脚本错误,或同一 ROS domain 上已有运行器在跑(锁被占:不建运行目录、不碰仿真) |
| 1 | 完全没写情形名(bash 直接退出);或运行器在受保护的流程之外抛出未捕获的异常(例如 rclpy 初始化失败、锁文件或运行目录建不了),这时可能没有 result.json。收尾各步各自捕获异常:一步出错只记为错误(退出 30;恢复注入的暂停、兜底取消、停录制、停 Nav2 这几步出错时退出 31),其余步骤照常执行 |
| 124 | 1500 s 硬上限触发,运行器在之后 120 s 内收完尾 |
| 137 | 收到 SIGINT 后 120 s 仍未结束,被 timeout 强杀,收尾没做完(见"关闭");SIGINT 可以来自 1500 s 硬上限、终端 Ctrl-C,或上文的 pkill(它同样匹配到 timeout 进程) |

### 3. 判定与失败处理(D3)

`result.json` 的五个状态字段由 `robosim_eval/evaluator.py` 给出,规则写在模块说明里,要点:

- 到达看 sim_control 真值(不是 AMCL);Nav2 报成功但真值超出 0.5 m 是"虚假成功",判 fail。
- 不可达必须同时满足:情形在配置里写了 `preset_unreachable: true`;Nav2 以 ABORTED 结束且 error_code 是规划器的无路径码 207 或 208(被拒绝、其他中止码都不算);运行器开始前的地图检查(`robosim_eval/map_check.py`,在钉住的 Nav2 地图上按机器人内切半径搜路)在目标容差内找不到可达位置;有真值且真值没到目标(没有真值不算没到);判定必需的数据完整。导航时限已触发时一律判 timeout。中止或被拒绝却缺其中任何一条时记 unknown:期望 reached 的情形因此判 fail,预设不可达的情形判 inconclusive;预设不可达而真值到了目标判 fail。情形里的 `evidence` 文字只写给人看,代码不检查。
- 安全看 Isaac 内的接触报告(需要用 `start_isaac_ros2.ps1 -PythonServer` 启动 Isaac);没测到就是 unknown,不是"没碰撞";监视器丢了接触事件、又没发现不允许的接触时,也是 unknown。与两个地面碰撞平面、机器人自身的接触不算碰撞;运行前清空时已在接触、运行中仍持续的接触照样计入。
- 判定必需的数据是 /clock、odom、Isaac 侧 TF;AMCL 估计只作参考,它的断流只记警告。必需数据流在评测窗口里没有数据、墙钟断流超过 2 s 或时间戳倒退,运行器收到的 /clock 倒退,或录制没覆盖整次运行(bag 开始晚或结束早、没录到目标的接受或终态、记录器撞上时长上限、离线分析失败),都判数据不完整。WSL 的墙钟被往回拨时,录下的数据也会因时间戳倒退判不完整(见"本机实测特性")。

情形(`configs/baseline.yaml` 的 `scenarios`):normal、bypass、unreachable、normal_slow(D5 声明的参数改动,见第 5 节),以及故障注入 cancel(目标被接受后 5 s 仿真时间取消)、dropout(目标被接受后 5 s 仿真时间暂停仿真,墙钟 6 s 后恢复)、timeout(导航的仿真时间时限压到 6 s,墙钟时限仍是 300 s)、collision(路上放一个 /scan 看不到的 0.10 m 高矮箱子)。没有 Python 执行服务时可以加 `--no-contacts` 跳过接触检测,安全字段同样是 unknown。dropout 声明 `expect_data: incomplete`、collision 声明 `expect_safety: fail`:注入的故障要被数据或安全检查抓到才算符合预期(导航结果也符合时判 pass);没抓到(数据完整、安全 pass)判 fail;没测到接触(安全 unknown),或数据除断流外还有别的问题时,判 inconclusive。

### 4. 批量复跑与报告(D4)

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_batch.sh      # normal、bypass、unreachable 各 3 次
```

`run_batch.sh [--scenarios a,b,c] [--repeats N] [--out <目录>] [--config <yaml>]`。开跑前先核对配置和情形名。每次尝试都先复位并用真值核对。某次运行的取消或停车没有确认(运行器退出 31),或运行器没有正常收尾(被信号杀掉、退出码不在 0/10/11/20/30 之内、运行目录里没有带判定的 result.json)时,中止后续批次;某次退出 20 时,批量在这次之后停止。运行器收尾时,对已发出、还没有终态的目标一律取消并确认停车,确认不了就退出 31。结果在 `artifacts/d4/batch-<时间>/`:`batch.json`、各次的输出 `NN-<情形>-<次>.txt`、`runs/<每次运行>/`、`runs/report.html`(静态页面,双击打开)、`runs/summary.json`。

报告只从已保存的记录生成,可单独重建(会覆盖该目录下的 report.html 和 summary.json;`-m` 要在仓库根目录下才找得到包,所以带 `--cd`):`wsl -d Ubuntu --cd /mnt/d/RoboSim-Eval -- python3 -m robosim_eval.report /mnt/d/RoboSim-Eval/artifacts/d4/<批次目录>/runs`。页头列出批次里出现的每个 commit 及其运行次数;"final distance to goal (m, ground truth)" 列(分情形表取最大值)是停车确认时(没确认时取收尾时)真值算的到目标距离,不可达情形也有值,不是到达误差;"Nav2 recoveries" 列只是线索,不能单凭它认定开头卡住:D4 可到达的 6 次里卡住的 5 次都是 5 次恢复、没卡住的那次是 0,但没卡住的运行也会有恢复(D5 演示的 normal 2 次、normal_slow 各 1 次),unreachable 每次 15 次;怎么判断卡住见 artifacts/d4/commands.md。

一次批量 9 次约 27 分钟墙钟,硬上限 4 h;批量直接调用运行器,没有单次 1500 s 的上限。退出码:0 每个计划的尝试都跑了并正常收尾(不看判定结果;判定看 `batch.json` 里各次的退出码和 `runs/summary.json`);31 某次取消或停车未确认,或运行器没有正常收尾,余下的不跑;20 被中断(Ctrl-C、SIGTERM、关窗口、4 h 硬上限)或某次运行器退出 20;2 用法、配置或环境错误(情形名写错在第一次尝试前就查出,一次都不跑),或某次运行器拒绝启动(例如锁被占),余下的不跑;30 报告没写成(只在本应退出 0 时);137 硬上限、Ctrl-C、关窗口或 pkill 之后 1 h 仍未结束,被强杀(batch.json 仍是 running)。终端 Ctrl-C 能到批量:批量把它转给正在跑的那次一次,那次按"中断一次运行"处理(执行中就取消目标、确认停车,收尾后退出 20),之后批量停止,余下的不跑;从另一个终端执行 `wsl -d Ubuntu -- pkill -INT -f robosim_eval.batch` 效果相同。要让当前这次跑完再停,发 SIGTERM(`wsl -d Ubuntu -- pkill -TERM -f robosim_eval.batch`);关掉窗口(SIGHUP)也是让当前这次跑完再停,batch.json 和报告照常写出。

### 5. 声明的参数改动与演示(D5)

情形可以声明 Nav2 参数改动,例如 `normal_slow` 的 `nav2_params: {controller_server.ros__parameters.FollowPath.max_vel_x: 0.4}`。运行器从 NVIDIA 原始参数文件派生 `<运行目录>/nav2_params.yaml`,只改这一行;经 `params_file:=` 启动 Nav2 后,从运行中的节点读回实际值,不符就判出错(退出 30),不发目标。对比批量:

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_batch.sh --scenarios normal,normal_slow --repeats 2 --out /mnt/d/RoboSim-Eval/artifacts/d5
wsl -d Ubuntu -- python3 /mnt/d/RoboSim-Eval/artifacts/d5/compare_speed.py /mnt/d/RoboSim-Eval/artifacts/d5/<批次目录>/runs
```

要模拟"Isaac 刚启动、场景未加载",不必重启 Isaac:`sim.sh stop`,再 `sim.sh load D:/RoboSim-Eval/tests/assets/empty_stage.usda`(一个空的 /World)。下一次运行会自己加载仓库场景。三个演示的记录见 `docs/demo.md`。

## 仿真控制:sim.sh(D2)

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh state         # stopped / playing / paused
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh load          # 加载 Nova Carter 场景(约 8 s)
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/sim.sh reset-check   # 只读真值,核对机器人在出生点(位置、朝向)且静止;本身不复位,先跑 sim.sh reset
```

子命令:state、play、pause、stop、load [<uri>]、reset、pose [<实体>]、reset-check,以及 spawn-box、delete(只能动 `/World/RoboSimObstacles` 下的直接子实体:按路径限制,不记录是谁生成的;工具生成的障碍物都放在这里,机器人和仓库不在其下)。每次在标准输出写一行 JSON;退出码 0 正常、3 服务不可用或超时或出错、4 reset-check 未通过、2 用法、配置或环境错误(子命令写错或缺失时由 argparse 在标准错误打印用法,不写 JSON)。另有 1:Python 未处理的异常(不写 JSON);124:撞上 sim.sh 的 300 s 总上限,按各服务调用的时限只有 load 可能撞上。Isaac 必须由 `start_isaac_ros2.ps1` 启动(sim_control 打开)。

复位(`sim.sh reset`、运行器的复位)调用 sim_control 的 ResetSimulation:Isaac 内依次 `timeline.stop()`、删除动态生成的实体、`timeline.play()`(`isaacsim.ros2.sim_control` 的 simulation_control.py)。**复位后回到出生点已验证**(验证走的是 ResetSimulation;GUI 的 ⏹、▶ 调用同一个 `omni.timeline` 接口的 `stop()`、`play()`,按代码推断结果相同,但没有用 GUI 按钮配真值单独核对过):D2 手动 `sim.sh reset` 结束约 3–4 s 后,`sim.sh reset-check` 读到真值 (-6.0010, -1.0000),距出生点 (-6.0, -1.0) 1.0 mm(artifacts/d2/commands.md、simctl-03/);D2–D5 的 33 次真实运行,运行器都在复位返回后约 1.1–2.1 s 用真值核对,读数每次都是 (-6.00007, -1.00000),误差 0.07 mm(各运行 events.jsonl 的 reset_check)。

## 诊断:doctor(D1)

判断仿真与 ROS 通路是否正常。按设计约 13 s 出结论(发现话题最多 5 s,观察 5 s,外加约 3 s 的 Python/rclpy 启停,这一段没有硬上限;实测最长 12.7 s,D1 假节点 lidar_missing),仿真暂停时约 4 s 就出结论;保证结束的是 doctor.sh 的 60 s 上限(超时退出 124)。运行器在每次运行前自己调用它。

```powershell
wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/doctor.sh --out /mnt/d/RoboSim-Eval/artifacts/d1/<目录>
```

| 退出码 | 含义 | 常见原因 |
| --- | --- | --- |
| 0 | 正常,并报告各路实际频率与新鲜度 | — |
| 10 | 仿真不推进 | Isaac 暂停或停止(⏸ / ⏹) |
| 11 | 仿真数据缺失 | Isaac 没开或刚启动还没加载场景(单独跑 doctor 前先 `sim.sh load`、`sim.sh play`;运行器自己会做)、ROS 2 bridge 没加载、防火墙或 DDS 发现不通、某个必需话题没有发布者 |
| 12 | 数据降级 | 某路数据过慢、陈旧或静默 |
| 13 | 环境或接口不对 | ros_env.sh / dds_env.sh 加载失败(doctor.sh 直接退出 13);某个配置话题有发布者的消息类型与配置不符(有一个就算,即使同时有类型正确的发布者);ROS 2 Python 导入失败或 rclpy 起不来;绕过 doctor.sh 直接跑 `python3 -m robosim_eval.doctor` 而没加载这两个脚本时,RMW 不是 Fast DDS 或 RMW_IMPLEMENTATION 指定的 RMW 没装、ROS_DOMAIN_ID 或 ROS_DISTRO 与配置不符、Fast DDS 配置文件未设置或不存在 |
| 2 | 用法或配置错误 | 参数写错,包括 `--window` 不是有限数、短于 clock_stall_s(2 s)或长于 50 s(doctor.sh 的 60 s 上限减去 discovery_timeout_s 和 5 s 启停余量);配置文件不存在、不是合法的 YAML、有重复键或未知键、缺项或数值非法,或给要观察的话题配了 doctor 不支持的消息类型 |
| 1 | 内部错误 | doctor 自身出现未处理的异常(例如 `--out` 目录建不起来或写不进),按失败处理 |
| 124 | 60 s 硬上限触发 | doctor 自身卡住,按失败处理 |

话题与阈值在 `configs/baseline.yaml`,依据是 D0 的实测频率。它的固定输入测试和假节点测试都包含在 verify.sh 里。

## 关闭

1. 自动路径:`run_scenario.sh`、`run_batch.sh` 自己停止录制和 Nav2;中途要停,在运行它的终端按 Ctrl-C,或用上文的 `pkill -INT`(单次见第 2 节,批量见第 4 节)。运行器被强杀(`run_scenario.sh` 退出 137:SIGINT 之后 120 s 仍未结束),或运行中关掉了 `run_scenario.sh` 的窗口时,收尾没做完,Nav2 和记录器会残留,下一次运行的 start_nav2 拒绝启动(运行器退出 31);这时对那个运行目录跑 `stop_record.sh` 和 `stop_nav2.sh`(见附录)。
2. Isaac Sim:用户在 GUI 按 ⏹ 或 File → Exit;不要从 WSL 或脚本杀 kit.exe。Claude Code 的 PreToolUse 钩子(`.claude/settings.json` → `.claude/hooks/guard_commands.py`)只看 Bash、PowerShell 工具调用的命令文本:会拦下其中结束 kit.exe 的调用(含 `wsl -d Ubuntu -- taskkill.exe /IM kit.exe`),但不读被调用的脚本文件(`bash <脚本>`、`powershell -File <脚本>` 直接放行),也管不到 Codex 和手动执行的命令。
3. 手动启动的 Nav2 与记录器怎么停,见附录。

## 本机实测特性(会影响判读)

- 仿真实时因子随会话变化:不跑 Nav2 时 D0–D4 约 0.36–0.43,D5(02:00 重新加载场景之后)只有 0.30–0.34(各运行 doctor-1.txt 的 RTF);完整导航中 D0 约 0.33,D2–D4 约 0.35–0.41,D5 约 0.28–0.32(events.jsonl 从 EXECUTING 到下一状态的仿真/墙钟时间)。按 0.32 计,120 s 仿真时间约需 375 s 现实时间,会先触发 300 s 现实上限(D3 collision:300 s 墙钟只走了 106 s 仿真)。
- 6.1 的 Nova Carter 示例只发布 3D 点云,不发布 /front_2d_lidar/scan、/back_2d_lidar/scan;钉住 params 的局部代价地图这两路无数据,全局代价地图与 collision_monitor 用的 /scan 由 pointcloud_to_laserscan 转换得到。
- 复位后点云发布者约 1.5–2 s 才重建,头几秒可能只有 0–1 帧;运行器准备阶段的 doctor 对此有限重查(artifacts/d2/repro-doctor-after-reset)。
- Nav2 从启动到就绪:D2 三次 13.3–13.6 s;D2–D5 启动了 Nav2 的 31 次真实运行 12.6–16.7 s(33 次真实运行中另 2 次在启动 Nav2 前就结束;各运行 events.jsonl 的 "nav2 ready after")。
- 机器人在零指令下缓慢前爬:按位置增量约 1.1 mm/仿真秒;odom twist 读数只有约 0.6 mm/s。都远低于停稳阈值 0.05 m/s。
- 话题偶有停顿(按接收时刻的墙钟间隔):空场景 odom 曾有 0.695 s 的间隔(D0);导航中 /clock、odom 的最长间隔 D0 为 0.92 s,D2–D5 的完整导航多为 1.16–1.32 s,D5 有一次自发卡顿 2.19 s(超过 2 s 门槛,判 inconclusive);AMCL 的 map→odom 最长间隔 D0 为 1.86 s,D2–D5 多为 2.3–2.6 s(最大 2.60 s),所以 AMCL 只作参考(各运行 result.json 的 data_integrity;D3 dropout 的约 6 s 空档是注入的暂停)。
- USD 动画时间线周期性循环:约每 16.7 s 仿真时间一次(复位后第一次在仿真约 17 s,相邻两次实测相差 16.3–17.2 s,由各运行 trajectory.csv 的仿真时间戳对照 kit 日志得出),墙钟间隔随实时因子变化:D0 约 40–43 s,9-30 当天各时段中位数 43–58 s;kit 日志每次循环出现 "resetting the animation timeline" 与一帧 differential_controller "Invalid deltaTime 0.000000"。仿真时钟不受影响(已实测 /clock 单调:D0 的 clock-continuity-01,D2–D5 有录制的 31 次运行,result.json 的 /clock 倒退次数都是 0,另 2 次在启动 Nav2 前就结束,没有录制);物理是否受影响没有单独测。
- D0 首次 Play 后约 7 s 时间线暂停(不是停止),由什么触发不明:kit 日志在那一刻与后来用户按 ⏸ 时特征相同(TF 聚合警告开始出现,紧接着同一毫秒出现 "resetting the animation timeline" 与菜单刷新),整个会话在用户关闭 Isaac 前没有停止才有的 "onStop: Cleared time samples";此后 OmniGraph 不再 tick,topic 仍在但没有数据。再按 ▶ 即恢复:日志只有 onResume,没有从停止状态播放时才有的 "Created simulation views",是从暂停处继续,场景没有重置;要回到出生点用 `sim.sh reset`。
- WSL 的 eth0 地址每次 WSL 重启可能变化;防火墙规则按接口而非 IP 限定,不受影响(2026-10-03 WSL 重启后 sim.sh state 照常退出 0)。
- 2026-10-03 一次 Windows 睡眠(07:06–07:32)之后,WSL 的 VM 时钟比真实时间快约 1.5–1.8%,WSL 里的 systemd-timesyncd(NTP)约每 32 s 校一次,每次把墙钟往回拨约 0.5 s;重启 WSL 不能消除,Windows 时钟对 NTP 不漂移(WSL 用的时钟源是 Hyper-V 提供的参考时钟)。rosbag 按接收时的墙钟给消息排序,于是录下的 /clock、odom、TF 出现倒退时间戳,评测判数据不完整、验证 inconclusive(当天合并后第一次真实 normal 就是这样)。真实运行前先跑 `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/artifacts/review-2026-10-03/clock_probe.sh 90`:报告有回拨就先处理时钟再跑(证据与排查见 `artifacts/review-2026-10-03/commands.md`)。

## 附录:D0 手动串脚本的流程(调试用)

D0(2026-09-29)用下面这些脚本手动串起一次导航。现在运行器按顺序调用其中的 start_nav2、record_d0、stop_record、analyze_attempt、stop_nav2(参数是运行目录);send_goal 不再调用,运行器用自己的 action 客户端发目标,并写同格式的 goal-*.txt 给 analyze_attempt。正常不用手动串。运行目录的例子是 `artifacts/d0d/<run_dir>`。用户的 D0 三步验收(启动看到地图与实时数据;发目标看到达并核对记录;暂停与恢复)按这里的步骤做。

下面各脚本加载 ros_env.sh / dds_env.sh 失败时都退出 2;check_nav2_ready、record_d0、send_goal、stop_record、stop_nav2 少给必需参数时由 bash 以 1 退出(analyze_attempt 的参数错误是 2)。

1. **Isaac Sim**:按上文自动路径第 1 步启动,然后在 GUI 加载场景:Window → Examples → Robotics Examples → 左树展开 **ROS2** → 点 **NAVIGATION** → 右侧卡片 **Nova Carter**(旁边的 Nova Carter Joint States 是另一个场景)→ **Load Sample Scene**(资产来自 NVIDIA 服务器,首次约 10 s–数分钟)→ 按 ▶ Play。也可以用 `sim.sh load` 和 `sim.sh play`。
2. **WSL 侧原始数据核对**:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/probe_topics.sh /mnt/d/RoboSim-Eval/artifacts/d0c/<目录>`(/clock 在推进时退出 0,否则 1;原始记录两种情况都写)。期望(空场景):/clock 约 25 Hz 推进、/chassis/odom 约 26 Hz、/tf 约 26 Hz、/front_3d_lidar/lidar_points 约 2.5 Hz、/cmd_vel 有 1 个订阅者(geometry_msgs/Twist)。Nav2 运行后 /clock、/chassis/odom 随仿真一起变慢:Nav2 空闲时 /clock 实测 21–25 Hz,导航中约 19 Hz;每仿真秒的条数不变(约 60 条,步长 1/60 s),变慢的是仿真本身。没有 /clock 数据时先看 Isaac 是否在 Play。
3. **复位并启动 Nav2 + RViz**:
   - 先在 Isaac 按 ⏹ 再按 ▶(或 `sim.sh reset`),让机器人回到出生点、里程计从 0 开始(见上文 sim.sh 一节),然后**尽快**启动 Nav2:机器人在零指令下会缓慢前爬(约 1.1 mm/仿真秒),而 AMCL 的初始位姿固定为出生点 (-6, -1, π),拖得越久初始定位偏差越大。首次导航时这一偏差为 0.324 m。
   - `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/start_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`:0 已启动;3 拒绝(已有 carter_navigation 或 Nav2 节点在跑,或无法检查);4 launch 没起来;2 环境错误。
   - 约 25 s 后:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/check_nav2_ready.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`(检查本身约 1 分钟,实测 65–70 s;完整输出同时写入 `<run_dir>/ready-<时间>.txt`)→ 就绪时退出 0,输出里有一行 `=== verdict: READY (<时间>) ===`(其后的末行是 `written <文件>`);否则在 `=== verdict: NOT READY (<时间>) ===` 下列出未就绪项并退出 1;环境脚本出错或输出文件写不了时退出 2。
   - RViz 窗口(WSLg)显示地图与激光;日志里一条 `indexed_8bit_image.vert` GLSL 错误无害。
4. **一次导航尝试**(每次只用一个目标发送者):
   - 选目标:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/map_overview.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>/map-overview.txt X,Y`(机器人位置是 AMCL 估计),以及 `send_goal.sh <attempt_dir> X Y YAW --check-only`(静态地图空闲核对 + ASCII 局部图)。
   - 记录:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/record_d0.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>/<attempt_dir> 330`(2 s 后每个记录器都在跑则退出 0,否则 1)。
   - 发目标:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/send_goal.sh <attempt_dir> X Y YAW` → 退出 0 = SUCCEEDED;2 = 参数错误(未知选项,或 x、y、yaw、--settle 不是有限数)或环境脚本出错;3 = 位姿核对没通过(不空闲、在地图外,或核对本身出错);4 = 找不到 action server;5 = 结束但未成功(ABORTED/CANCELED/未知);6 = 被拒绝;其他 = 动作客户端的退出码,原样转出(例如客户端 330 s 超时的 124)。结果出来后脚本再等 6 s(`--settle`),让记录覆盖机器人停下的过程。
   - 停止记录:`stop_record.sh <attempt_dir>`(按会话号 SIGINT → SIGTERM → SIGKILL)→ 0 = 所有记录器已停、退出码齐全、bag 已复制且必需话题有数据;1 = 目录里没有 record.pids;3 = 有记录器会话在 SIGKILL 后仍在;4 = 缺记录器退出码文件;5 = bag 缺失、`ros2 bag info` 失败或复制失败;6 = 必需话题 0 条消息。各记录器的退出码在 `<attempt_dir>/<name>.exit`:bag 为 0 或 2,四路 `ros2 topic echo`(odom、amcl_pose、cmd_vel、action_status)为 2,tf_map_base(`tf2_echo`)为 0 或 2,都表示被 SIGINT 正常停止;124 表示到了时长上限。
   - 汇总:`analyze_attempt.sh <attempt_dir> --goal X Y YAW --spawn -6.0 -1.0 3.141592653589793` → `result.json`、`trajectory.csv`;退出 0 = pass、10 = fail、11 = inconclusive;2 = 参数错误、环境脚本出错,或 `--goal` 与实际发出的目标不一致(不一致时不写结果);1 = 读不了 `<attempt_dir>/rosbag`(例如 stop_record 没把 bag 复制过来),不写结果。`--spawn` 是场景 USD 里的出生位姿,用于得到不依赖 AMCL 的位置来源,前提见 result.json 的 `preconditions_for_sim_state_source`。
   - RViz 的 **Nav2 Goal** 也能发目标,但**未执行过**,而且没有目标转录,分析结果最多是 inconclusive;验收请用 send_goal.sh。
5. **暂停/恢复核对**:`watch_clock.sh 120 <文件>` 运行时在 Isaac 按 ⏸ 再按 ▶;文件中会出现一段没有 /clock 消息的空白,空白前后的仿真时间最多相差一个步长(实测 0.017 s)。
6. **停止 Nav2**:`wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/stop_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/<run_dir>`。先核对归属:开机 ID 与包装进程的启动时刻要与 `nav2-launch.meta` 记录的一致,该进程的命令行还要包含本运行目录的 `nav2.exit` 路径,否则拒绝并以 5 退出。然后 SIGINT 只发给 `ros2 launch`(找不到 launch 进程时才发给整个会话),最多等 45 s,必要时对本会话升级 SIGTERM、SIGKILL;launch 的真实退出码写在 `<run_dir>/nav2.exit`;最后用不走 daemon 的 fresh discovery(`--no-daemon`)核对没有残留 Nav2 节点。退出 0 = 无残留(会话在调用前就已没有进程时也直接退出 0,这时既不核对归属,也不做残留检查);1 = 有残留进程或节点,或运行目录里没有 nav2.pid;3 = 残留检查本身失败;5 = 拒绝(归属对不上);2 = 环境脚本出错。从发 SIGINT 到会话全部退出,脚本记下的用时为 6–14 s(D0 的 run-04 13 s、run-05 10 s;D2–D5 的 31 次 6–14 s,都只发了 SIGINT,没有升级);之后还有残留检查(fresh discovery 至少等 3 s),整个脚本约 10–18 s 返回。launch 的退出码为 1,日志里是 launch 自己的异常 "Cannot shutdown a ROS adapter that is not running";同时 Nav2 组件容器在清理阶段段错误(日志 "Magick: abort due to signal 11 (SIGSEGV)",launch 记下的退出码是 -6,即 SIGABRT;run-04 起 33 次停止每次都有),rviz2 每次退出方式不同(run-04 起 33 次停止:-9 19 次、-15 6 次、-6 3 次、-11 2 次,正常退出 3 次)。这些都是上游组件里的现象,原因没有查,不影响导航与记录;见 docs/plan.md §4 未解决问题中的"已知问题"。
7. **Isaac Sim**:只想停仿真时在 GUI 按 ⏹(只停时间线,kit.exe 仍在运行);要关闭 Isaac,由用户在 GUI 用 File → Exit(只按 ⏹ 时,下次运行 start_isaac_ros2.ps1 会因已有 kit.exe 而拒绝启动)。
