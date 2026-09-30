# D0b 命令记录(ROS 2 Jazzy + 6.1.0 示例工作区)

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 19:16:12 | `bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh`(第一次) | 用户的 Ubuntu 终端 | 用户 HOME | 未记录(脚本在步骤 0 后无后续输出;推测在 sudo 密码提示处中断) | install-jazzy.log 第 1–4 行 | 用户随后重新运行 |
| 2026-09-29 19:19:52 → 19:24:37 | `bash /mnt/d/RoboSim-Eval/scripts/wsl/install_ros2_jazzy.sh`(第二次) | 用户的 Ubuntu 终端 | 用户 HOME | **1**(见备注) | install-jazzy.log(9185 行)、install-jazzy.exit | 步骤 1–5 全部成功:17 个包 "install ok installed",rosdep init + update 完成。退出码 1 来自步骤 6 的脚本缺陷:`set -u` 下 `source /opt/ros/jazzy/setup.bash` 报 `AMENT_TRACE_SETUP_FILES: unbound variable`。脚本已修(source 前后 `set +u/-u`),未重跑(需再次 sudo);安装结果由下一行独立校验 |
| 2026-09-29 19:28:27 | `wsl -d Ubuntu -- bash -l scripts/wsl/check_ros_install.sh` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0(2 s) | check-ros-install.txt | PASS:ros2/rviz2/colcon/rosdep 在 PATH;18 个包已装;rosdep 已初始化;librmw_fastrtps_cpp.so 存在;`ros_env.sh --base-only` 首次实跑成功 |
| 2026-09-29 19:29:00 | `wsl -d Ubuntu -- bash -l scripts/wsl/test_talker_listener.sh` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | test-talker-listener-default.txt、talker-default.log、listener-default.log | PASS,仅证明 WSL 内部通信:talker 13 条 Publishing,listener 11 条 "I heard";listener `timeout 12` 退出 124(观察满时长),talker 被脚本 `kill -INT` 后退出 0 |
| 2026-09-29 19:29:14 | 同上 `--with-dds-profile` | 同上 | 同上 | 0 | test-talker-listener-dds.txt、talker-dds.log、listener-dds.log | PASS,FASTRTPS_DEFAULT_PROFILES_FILE=/mnt/d/RoboSim-Eval/configs/network/fastdds.xml 被加载(UDPv4-only)仍能通信;`dds_env.sh` 首次实跑成功 |
| 2026-09-29 19:29:31 | `wsl -d Ubuntu -- bash -l scripts/wsl/test_rviz.sh` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0(21 s) | test-rviz.txt、rviz-default.log | PASS:rviz2 在 WSLg(DISPLAY=:0)下默认 GL 存活 20 s(退出 124),日志显示 OpenGL 4.5;未用软件渲染回退 |
| 2026-09-29 19:29:51 → 19:30:13 | `wsl -d Ubuntu -- bash -l scripts/wsl/setup_workspace.sh`(后台作业) | Git Bash → wsl.exe(脚本文件,run_in_background) | /mnt/d/RoboSim-Eval | **0**(setup-workspace.exit;22 s) | setup-workspace.log(326 行) | 克隆 `IsaacSim-6.1.0` 到 `~/robotics/vendor/isaac-ros-6.1`;HEAD = `a9e8471ee901bc2332c1e4aca94ac580713ca3ab` = 计划文档钉住值,`git describe` = IsaacSim-6.1.0,树干净;闭包 = carter_navigation(ament_cmake)+ isaac_ros_navigation_goal + isaacsim_bringup(ament_python);`rosdep --simulate` 无需安装;`colcon build --packages-up-to carter_navigation` 3 个包 3.35 s 成功;`ros2 pkg prefix carter_navigation` = …/jazzy_ws/install/carter_navigation;`--show-args` 列出 map / params_file / use_sim_time(默认 True)及 nav2_bringup 透传参数;sha256:map yaml 05263f31…、map png dd2f5e38…、params 8349fe3b…、launch 7071bcad… |
| 2026-09-29 19:3x | `wsl -d Ubuntu -- bash -l temp/check_overlay.sh`(source ros_env.sh 全模式 + dds_env.sh) | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | 会话记录 | `ros_env.sh` overlay 模式首次实跑退出 0,AMENT_PREFIX_PATH 含三个工作区包 + /opt/ros/jazzy;`dds_env.sh` 退出 0 |

## 门槛 2→3 判定(通过)

- colcon 退出码 0 ✔;`--show-args` 列出 map / params_file / use_sim_time ✔;talker/listener 输出已存 ✔;rviz2 测试已记录(PASS)✔。

## 教训

- 经 Git Bash 把复杂内联命令传给 `wsl.exe -- bash -lc '...'` 会被引号/反斜杠改写(2026-09-29 19:2x 一次内联 dpkg-query 检查输出全空、`command -v ros2` 为空),不是安装问题;此后所有 WSL 检查一律写成脚本文件用 `bash -l <路径>` 运行。
- ROS 的 setup.bash 不兼容 `set -u`;所有脚本在 source 前后 `set +u` / `set -u`。
