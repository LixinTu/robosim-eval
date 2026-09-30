# 本机环境证据(D0a)

探测日期:2026-09-29 19:02–19:04(America/Los_Angeles)。全部为只读探测,未安装、未修改任何东西。原始输出:`artifacts/d0a/windows-probe.txt`、`artifacts/d0a/wsl-probe-login.txt`、`artifacts/d0a/wsl-probe-clean.txt`;命令与退出码见 `artifacts/d0a/commands.md`。

**结论:本机是 Isaac Sim 6.1 官方不支持的配置(Windows 10、8 GB 显存、驱动低于测试版本)。用户已决定在此配置上做完项目再升级;所有后续记录标注 unsupported configuration。**

## Windows 侧

| 项目 | 实测 | 对 D0 的影响 |
| --- | --- | --- |
| 操作系统 | Microsoft Windows 10 专业版 10.0.19045(build 19045.6466),64 位 | 6.1 要求页明确不支持 Windows 10;WSL mirrored networking 不可用,保持默认 NAT |
| 内存 | 总计 63.7 GB,空闲 31.2 GB(Isaac 空场景运行中) | 充足 |
| GPU | NVIDIA GeForce RTX 4070 Laptop GPU,驱动 591.44,CUDA 13.1,显存 8188 MiB,当前已用 1313 MiB(空场景 GUI),利用率 22% | 低于官方最低 16 GB;驱动低于官方测试版 595.97;阶段 3 实测场景显存 |
| 磁盘 | C: 空闲 1421 GB;D: 空闲 1524 GB | 充足 |
| PowerShell | 5.1.19041.6456;执行策略 CurrentUser=RemoteSigned(本地 .ps1 可直接运行) | 启动脚本无需 Bypass,但给用户的命令仍写 `-ExecutionPolicy Bypass` 以防其他作用域 |
| 提权 | 当前 Claude 的 shell 未提权(IsInRole Administrator = False),账户为 administrator | 防火墙规则等管理员操作需用户在管理员窗口执行 |
| WSL | 2.6.3.0,内核 6.6.87.2-1,WSLg 1.0.71;发行版 `Ubuntu`(Running,v2)、`docker-desktop`(Running,v2);无 `.wslconfig`(默认 NAT) | `wsl -d Ubuntu -- bash -c` 从 PowerShell 可用,WSL 用户为 administrator |
| 网络 | WLAN 192.168.1.115/24(Public);vEthernet (WSL) 172.28.208.1/20(无连接配置文件条目);防火墙三个配置文件均启用,入站默认 NotConfigured;没有任何 kit/isaac 相关防火墙规则 | 首次让 kit.exe 监听时可能弹出防火墙对话框;若被忽略会静默阻断,阶段 3 需提醒用户"允许" |
| Isaac Sim | `D:\isaac-sim-standalone-6.1.0-windows-x86_64`,VERSION `6.1.0-rc.26+release.49347.2d230af4.gl`;isaac-sim.bat、python.bat、post_install.bat、setup_ros_env.bat 均存在;`exts\isaacsim.ros2.core\jazzy\lib` 与 `humble\lib` 存在;`exts\isaacsim.ros2.bridge` 存在 | 复用,不重装 |
| post_install 链接 | `extension_examples` 已是 SymbolicLink → `exts\isaacsim.examples.interactive\isaacsim\examples\interactive` | 旧的 "Symlink extension_examples not created" 报错已不成立,无需修复 |
| 运行中的 Isaac | `kit` PID 29036(16:22 启动,工作集 801 MB)、`omni.telemetry.transmitter` PID 19988 | 未带 ROS 环境变量启动;阶段 3 需用户正常关闭后重启 |
| kit 日志 | `C:\Users\Administrator\.nvidia-omniverse\logs\Kit\Isaac-Sim Full\6.1\kit_20260929_162201.log`(5.2 MB);ROS 2 扩展(isaacsim.ros2.bridge 5.1.4、isaacsim.ros2.core 1.11.0 等)仅 "registered",未见启用;4 条 Error 均为无法在 `C:\Users\Administrator\Documents\...` 下创建目录 | 阶段 3 用同目录最新日志核对 bridge 加载;Documents 目录问题暂不影响 D0 |
| setup_ros_env.bat | 默认 ROS_DISTRO=jazzy、默认 RMW_IMPLEMENTATION=**rmw_zenoh_cpp**;仅当 ROS_DISTRO 未设时把 `exts\isaacsim.ros2.core\jazzy\lib` 前置到 PATH 并设 AMENT_PREFIX_PATH;仅当 RMW_IMPLEMENTATION 未设时才设为 zenoh | 启动前显式设 RMW_IMPLEMENTATION=rmw_fastrtps_cpp 会被尊重;isaac-sim.bat 是否自动调用此文件见阶段 3 记录 |
| ROS/DDS 残留 | 进程、用户、系统环境变量均无 ROS_* / RMW_* / FASTRTPS_* / CYCLONE* / DDS;`%USERPROFILE%\.ros\fastdds.xml`、`C:\.ros\fastdds.xml`、`D:\robosim-assets\network\fastdds.xml` 均不存在 | 无冲突配置 |
| Codex CLI | codex-cli 0.157.0(`C:\Users\Administrator\AppData\Roaming\npm\codex.ps1`),`codex login status` → "Logged in using ChatGPT";`codex exec` 支持 `--sandbox read-only`、`-C <dir>`、`exec review` 子命令 | 阶段 5 审查用 `codex exec --sandbox read-only -C D:\RoboSim-Eval ...` |

## WSL(Ubuntu)侧

| 项目 | 实测 | 对 D0 的影响 |
| --- | --- | --- |
| 发行版 | Ubuntu 24.04.4 LTS(noble),内核 6.6.87.2-microsoft-standard-WSL2 | 与 ROS 2 Jazzy 匹配 |
| 用户 | uid 1000 administrator,组含 sudo、docker;HOME=/home/administrator | — |
| sudo | `sudo -n true` → "sudo: a password is required"(退出码 1) | 安装必须由用户在 Ubuntu 终端执行;Claude 只准备命令块 |
| Python / Git | Python 3.12.3;git 2.43.0 | 满足 |
| ROS 2 | 无 `/opt/ros`;`ros-jazzy-*` 已装包 0 个;无 ROS apt 源(仅 ubuntu.sources);无 colcon、无 rosdep、无 rviz2 | 阶段 2 需完整安装 Jazzy 及导航相关包 |
| WSLg | DISPLAY=:0,WAYLAND_DISPLAY=wayland-0,XDG_RUNTIME_DIR=/run/user/1000/,在非交互 `bash -lc` 与 `bash --noprofile --norc` 下均已设置;/mnt/wslg 存在 | RViz 有显示通道;能否真正渲染在阶段 2 用 `timeout 20 rviz2` 实测 |
| 网络 | eth0 172.28.211.14/20,MTU 1428,默认网关 172.28.208.1(= Windows 的 vEthernet (WSL));github.com 与 packages.ros.org 可解析 | NAT 模式;WSL IP 每次重启可能变化,阶段 3 的 peers 配置不能写死 |
| 内存 / 磁盘 | 31 GiB(WSL 默认上限)+ 8 GiB swap;`/` 空闲 948 GB;`/mnt/d` 空闲 1.5 TB | 工作区放 `~/robotics/vendor`(ext4) |
| 已有工作区 | `~/robotics` 不存在;`~` 与 `/mnt/d`(深度 2)内无 IsaacSim-ros_workspaces / jazzy_ws | 阶段 2 需克隆 |
| ROS 残留 | env、~/.bashrc、~/.profile、/etc/environment、/etc/profile.d 均无 ROS/RMW/FASTRTPS 行;`~/.ros/*.xml` 不存在 | 无冲突配置 |
| 登录 vs 干净 shell | 两次探测除内存数字外逐行一致 | 非交互 `bash -lc` 的结论可信 |

## 门槛 1→2 判定

- 两侧探测均有完整输出、退出码 0;Isaac 两个关键路径存在 → 通过。
- 阶段 2 前置条件缺口:ROS 2 Jazzy 全套未安装,且 sudo 需要密码 → 阶段 2 以"等待用户执行安装块"开始。

## 未确认项(留给后续阶段)

- ~~isaac-sim.bat 是否自动调用 setup_ros_env.bat~~ 已确认:`isaac-sim.bat` 与 `python.bat` 都会自动 `call setup_ros_env.bat`,除非传 `--no-ros-env`。
- ~~Isaac 自带 `python.bat` 能否 `import rclpy`~~ 已测(2026-09-29 19:1x,两次):加 `PYTHONPATH=exts\isaacsim.ros2.core\jazzy\rclpy` 后能定位 rclpy,但 `import numpy`(自带 site 的 numpy 2.5.1)报 "DLL load failed while importing _multiarray_umath",无论 jazzy lib 前置还是追加到 PATH 末尾都一样;退出码 1。结论:无 GUI 的 Windows 侧 rclpy 发现预测试**不可行**,阶段 3 直接走 GUI 重启路线;不再花时间修 python.bat 环境。
- 8 GB 显存能否承载 Nova Carter 示例场景(阶段 3 实测)。
- WSLg 下 rviz2 能否渲染(阶段 2 实测)。
- Windows Defender 对 kit.exe 的首次监听是否弹窗(阶段 3 观察)。
