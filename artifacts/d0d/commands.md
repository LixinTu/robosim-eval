# D0d 命令记录(Nav2 + 一次真实 A→B)

## 常驻进程

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 20:13:50 | `wsl -d Ubuntu -- bash -l scripts/wsl/start_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/run-01` → 内部 `setsid nohup ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true` | 56471(WSL,会话/进程组组长) | 20:14:15–20:15:21 ready-check-01:10 个生命周期节点 active,"Managed nodes are active"(启动日志第 349 行);RViz 经 WSLg 显示 | （运行中;计划用 stop_nav2.sh 以 SIGINT 结束) | — | — |

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 20:13:48 | `start_nav2.sh …/run-01` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | run-01/nav2-launch.meta、nav2-launch.log | 启动前检查:无已在跑的 Nav2 节点;env RMW=fastrtps、domain 0、DDS profile、DISPLAY=:0;overlay = …/install/carter_navigation |
| 2026-09-29 20:14:15 → 20:15:21 | `check_nav2_ready.sh …/run-01` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0(66 s) | run-01/ready-check-01.txt、run-01/ready-201415.txt | 节点:amcl、bt_navigator、controller_server、planner_server、behavior_server、smoother_server、velocity_smoother、collision_monitor、waypoint_follower、map_server、docking_server、route_server、pointcloud_to_laserscan、rviz;10 个查询的生命周期均 active [3];/scan 3.54–3.60 Hz(BEST_EFFORT,1 发布 4 订阅);/front_2d_lidar/scan 无(预期);/map 480×776 收到;`use_sim_time` amcl/controller_server = True;amcl set_initial_pose=True,initial_pose (-6.0, -1.0, 3.14159);action 列表含 `/navigate_to_pose [nav2_msgs/action/NavigateToPose]`;/cmd_vel 现有 2 个发布者(Nav2 的 collision_monitor 与 behavior_server)+ 1 个订阅者(Isaac);TF:odom→base_link [0.378, 0, 0],map→odom [-5.676, -1.0, 0.001],map→base_link [-6.058, -1.0, 0];/amcl_pose 8 s 内无消息(机器人静止时 AMCL 不发布) |
| 2026-09-29 20:15:xx | 启动日志检查 `grep ERROR|WARN` | Git Bash | D:\RoboSim-Eval | 0 | run-01/nav2-launch.log | 第 176 行 pointcloud_to_laserscan:某新订阅者请求不兼容 QoS(不影响 4 个 best-effort 订阅者);第 258 行 rviz2 `[ERROR] rviz/glsl120/indexed_8bit_image.vert … active samplers with a different type refer to the same texture image unit`(WSLg/Mesa 下已知的着色器链接问题,之后 RViz 仍两次 "Trying to create a map of size 480 x 776",地图是否可见待用户确认);第 291 行 docking_server 无 dock 数据库(与 D0 无关);第 308–310 行 global_costmap 启动时等 map→base_link 超时(AMCL 发布前的正常现象) |
| 2026-09-29 20:16 | PowerShell → wsl:`ros2 topic echo --csv /cmd_vel`(6 s)、`ros2 topic hz /cmd_vel`、odom twist/position once | PowerShell(Claude 工具) | D:\RoboSim-Eval | 0 | 会话记录 | /cmd_vel 6 s 内无消息(无人在下速度指令);odom twist linear.x ≈ 0.0006 m/s;odom position x = 0.4296(19:59 为 0.045,20:14 为 0.378)→ **机器人在零指令下以约 0.6 mm/s 缓慢前爬**(物理/驱动保持特性);远低于停稳阈值 0.05 m/s,记为已知现象 |
| 2026-09-29 20:17 | `send_goal.sh …/run-01 <x> <y> 3.14159 --check-only` × 6 | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | 会话记录 | 地图空闲核对(res 0.05,原点 (-11.975, -17.975)):(-6.0,-1.0) FREE 无障碍;(-8.0,-1.0) FREE 但 0.80 m 处有墙;(-9.5,-1.0) OCCUPIED;(-6.0,1.5) FREE;(-6.0,-3.5) FREE 但 0.28 m 处有障碍;(-4.0,-1.0) FREE 无障碍 |
| 2026-09-29 20:18 | `map_overview.sh …/run-01/map-overview.txt -4.0,-1.0 -6.0,1.5 -8.0,-1.0` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | run-01/map-overview.txt | 机器人 map (-6.14, -1.00) 处于开阔区;候选 1 (-4.0,-1.0) 在 +x 方向 2 m、四周空旷 → 选为首个目标(yaw 0);候选 3 紧邻 x≈-9 的墙,放弃 |
| 2026-09-29 20:18 | 用户截图:RViz(carter_navigation.rviz)地图已显示、激光点贴合货架墙与障碍块、Nav2 面板 Navigation/Localization active;Isaac 20 FPS、GPU 3.9 GiB | 用户 | — | — | run-01/rviz-before-goal-2018.png | B6 步骤 3 的贴合核对由用户目视完成;未点 2D Pose Estimate(AMCL 自动初始位姿已正确) |

## 尝试 1(attempt-01):目标 map (-4.0, -1.0, yaw 0),CLI action client 发送

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 20:24:21 → 20:24:26 | `record_d0.sh …/run-01/attempt-01 330` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | attempt-01/record.meta、record.pids、bag-path.txt | 启动 bag(会话 57532)+ odom/amcl_pose/cmd_vel/action_status 文本流(会话 57539/57563/57581/57590);tf_map_base 流立即退出(tf2_echo 速率参数应为 `-r 5`,脚本已修) |
| 20:24:33 → 20:25:06 | `send_goal.sh …/attempt-01 -4.0 -1.0 0.0` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0(action client 退出 0) | attempt-01/goal-202437.txt(带现实时间戳的完整反馈与结果) | 地图核对 (-4.0,-1.0) FREE;20:24:40.495 **Goal accepted** id 8e28b7ce036f43659b4be8c71c404771;20:25:06.105 **Result: error_code 0, error_msg ''**;"Goal finished with status: SUCCEEDED";最后反馈 distance_remaining 0.235 m、number_of_recoveries 0;仿真时间 509 → 518 s |
| 20:25:07 → 20:25:12 | `stop_record.sh …/attempt-01` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | attempt-01/bag-info.txt、rosbag/(mcap 6.3 MB,不入 Git)、odom.txt、amcl_pose.txt、cmd_vel.txt、action_status.txt | bag 47.7 s、5982 条:/clock 904、/chassis/odom 904、/cmd_vel 540、feedback 2405、status 2、/plan 25、/scan 145、/tf 1049、/amcl_pose 8;action_status 文本流:20:24:40.519 status 2(EXECUTING)→ 20:25:06.131 status 4(SUCCEEDED);cmd_vel 从 -0.16/-0.32/-0.48 rad/s 的转向斜坡开始,20:25:09 起全零。**缺陷**:SIGINT 只发到原进程组,`timeout` 自建的进程组未收到,四个文本流跑到 20:27 仍在写(bag 已正常停止);20:28 用 `pkill -INT -s <会话>` 按会话结束,stop_record.sh 已改为按会话发送 |
| 20:3x | `analyze_attempt.sh …/attempt-01 --goal -4.0 -1.0 0.0` | Git Bash → wsl.exe(脚本文件,rosbag2_py) | /mnt/d/RoboSim-Eval | 0(4 s) | attempt-01/result.json、trajectory.csv | **task_outcome=reached, validation=pass, data=complete, safety=unknown(未测)**;接受→结果 8.47 s 仿真 / 25.61 s 现实;终点 map 系:Nav2 反馈 (-4.250, -1.002, yaw 0.019) 误差 0.250 m,TF 合成 (-4.229, -1.021) 误差 0.230 m(容差 0.5 m;两者都是定位估计,非独立真值);停稳(|v|<0.05, |w|<0.1 持续 1 s 仿真时间)在 sim 519.53 s 确认,结果后最大 |v| 0.168 m/s(减速尾段)、最大 |w| 0.045 rad/s;trajectory.csv 含 904 条 odom、904 条 TF 合成 map 位姿、2405 条反馈位姿,各带 frame 与来源 |

## D0d 验收判定

- Nav2 接受并完成目标 ✔(原始状态码 4,error_code 0)
- 轨迹显示移动 ✔(odom x 0.56 → -1.97;map x -6.24 → -4.25;先转向后直行)
- 到达且停稳 ✔(误差 0.23–0.25 m < 0.5 m;停稳规则满足)
- 原始证据保留 ✔(bag、反馈转录、文本流、result.json、trajectory.csv)
- 未验证:碰撞/接触、独立仿真真值、朝向考核(记录 yaw 0.019 rad,未纳入验收)
