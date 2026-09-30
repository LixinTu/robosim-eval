# D0d 命令记录(Nav2 + 一次真实 A→B)

## 常驻进程

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 20:13:50 | `wsl -d Ubuntu -- bash -l scripts/wsl/start_nav2.sh /mnt/d/RoboSim-Eval/artifacts/d0d/run-01` → 内部 `setsid nohup ros2 launch carter_navigation carter_navigation.launch.xml use_sim_time:=true` | 56471(WSL,会话/进程组组长) | 20:14:15–20:15:21 ready-check-01:10 个生命周期节点 active,"Managed nodes are active"(启动日志第 349 行);RViz 经 WSLg 显示 | （运行中;计划用 stop_nav2.sh 以 SIGINT 结束) | — | — |

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 20:13:48 | `start_nav2.sh …/run-01` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | run-01/nav2-launch.meta、nav2-launch.log | 启动前检查:无已在跑的 Nav2 节点;env RMW=fastrtps、domain 0、DDS profile、DISPLAY=:0;overlay = …/install/carter_navigation |
| 2026-09-29 20:14:15 → 20:15:21 | `check_nav2_ready.sh …/run-01` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0(66 s) | run-01/ready-check-01.txt、run-01/ready-201532.txt(更正:此前误写为 ready-201415.txt) | 节点:amcl、bt_navigator、controller_server、planner_server、behavior_server、smoother_server、velocity_smoother、collision_monitor、waypoint_follower、map_server、docking_server、route_server、pointcloud_to_laserscan、rviz;10 个查询的生命周期均 active [3];/scan 3.54–3.60 Hz(BEST_EFFORT,1 发布 4 订阅);/front_2d_lidar/scan 无(预期);/map 480×776 收到;`use_sim_time` amcl/controller_server = True;amcl set_initial_pose=True,initial_pose (-6.0, -1.0, 3.14159);action 列表含 `/navigate_to_pose [nav2_msgs/action/NavigateToPose]`;/cmd_vel 现有 2 个发布者(Nav2 的 collision_monitor 与 behavior_server)+ 1 个订阅者(Isaac);TF:odom→base_link [0.378, 0, 0],map→odom [-5.676, -1.0, 0.001],map→base_link [-6.058, -1.0, 0];/amcl_pose 8 s 内无消息(机器人静止时 AMCL 不发布) |
| 2026-09-29 20:15:xx | 启动日志检查 `grep ERROR|WARN` | Git Bash | D:\RoboSim-Eval | 0 | run-01/nav2-launch.log | 第 176 行 pointcloud_to_laserscan:某新订阅者请求不兼容 QoS(不影响 4 个 best-effort 订阅者);第 258 行 rviz2 `[ERROR] rviz/glsl120/indexed_8bit_image.vert … active samplers with a different type refer to the same texture image unit`(WSLg/Mesa 下已知的着色器链接问题,之后 RViz 仍两次 "Trying to create a map of size 480 x 776",地图是否可见待用户确认);第 291 行 docking_server 无 dock 数据库(与 D0 无关);第 308–310 行 global_costmap 启动时等 map→base_link 超时(AMCL 发布前的正常现象) |
| 2026-09-29 20:16 | PowerShell → wsl:`ros2 topic echo --csv /cmd_vel`(6 s)、`ros2 topic hz /cmd_vel`、odom twist/position once | PowerShell(Claude 工具) | D:\RoboSim-Eval | 0 | 会话记录 | /cmd_vel 6 s 内无消息(无人在下速度指令);odom twist linear.x ≈ 0.0006 m/s;odom position x = 0.4296(20:02:3x 的 probe-04 中为 0.045,20:14 为 0.378;更正:此前误写 19:59)→ **机器人在零指令下缓慢前爬**:按位置增量约 1.1 mm/仿真秒,twist 读数只有约 0.6 mm/s(更正:此前把 twist 读数当成了爬行速度);远低于停稳阈值 0.05 m/s,记为已知现象 |
| 2026-09-29 20:17 | `send_goal.sh …/run-01 <x> <y> 3.14159 --check-only` × 6 | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | 会话记录 | 地图空闲核对(res 0.05,原点 (-11.975, -17.975)):(-6.0,-1.0) FREE 无障碍;(-8.0,-1.0) FREE 但 0.80 m 处有墙;(-9.5,-1.0) OCCUPIED;(-6.0,1.5) FREE;(-6.0,-3.5) FREE 但 0.28 m 处有障碍;(-4.0,-1.0) FREE 无障碍 |
| 2026-09-29 20:18 | `map_overview.sh …/run-01/map-overview.txt -4.0,-1.0 -6.0,1.5 -8.0,-1.0` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | run-01/map-overview.txt | 机器人 map (-6.14, -1.00) 处于开阔区(这是 AMCL 估计;事后交叉核对显示当时与独立来源相差约 0.32 m);候选 1 (-4.0,-1.0) 在 +x 方向 2 m、四周空旷 → 选为首个目标(yaw 0);候选 3 紧邻 x≈-9 的墙,放弃 |
| 2026-09-29 20:18 | 用户截图:RViz(carter_navigation.rviz)地图已显示、激光点贴合货架墙与障碍块、Nav2 面板 Navigation/Localization active;Isaac 20 FPS、GPU 3.9 GiB | 用户 | — | — | run-01/rviz-before-goal-2018.png | B6 步骤 3 的贴合核对由用户目视完成;未点 2D Pose Estimate。**更正(内部预审 R1)**:此前写的"AMCL 自动初始位姿已正确"不成立。事后交叉核对显示 AMCL 初始位姿当时偏 0.324 m(机器人在 Nav2 启动前已缓爬离开出生点),目视贴合没有发现;已记入 docs/plan.md §8 偏差 |

## 尝试 1(attempt-01):目标 map (-4.0, -1.0, yaw 0),CLI action client 发送

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 20:24:21 → 20:24:26 | `record_d0.sh …/run-01/attempt-01 330` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | attempt-01/record.meta、record.pids、bag-path.txt | 启动 bag(会话 57532)+ odom/amcl_pose/cmd_vel/action_status 文本流(会话 57539/57563/57581/57590);tf_map_base 流立即退出(tf2_echo 速率参数应为 `-r 5`,脚本已修) |
| 20:24:33 → 20:25:06 | `send_goal.sh …/attempt-01 -4.0 -1.0 0.0` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0(action client 退出 0) | attempt-01/goal-202437.txt(带现实时间戳的完整反馈与结果) | 地图核对 (-4.0,-1.0) FREE;20:24:40.495 **Goal accepted** id 8e28b7ce036f43659b4be8c71c404771;20:25:06.105 **Result: error_code 0, error_msg ''**;"Goal finished with status: SUCCEEDED";最后反馈 distance_remaining 0.235 m、number_of_recoveries 0;仿真时间 509 → 518 s |
| 20:25:07 → 20:25:12 | `stop_record.sh …/attempt-01` | Git Bash → wsl.exe(脚本文件) | /mnt/d/RoboSim-Eval | 0 | attempt-01/bag-info.txt、rosbag/(mcap 6.3 MB,不入 Git)、odom.txt、amcl_pose.txt、cmd_vel.txt、action_status.txt | bag 47.7 s、5982 条:/clock 904、/chassis/odom 904、/cmd_vel 540、feedback 2405、status 2、/plan 25、/scan 145、/tf 1049、/amcl_pose 8;action_status 文本流:20:24:40.519 status 2(EXECUTING)→ 20:25:06.131 status 4(SUCCEEDED);cmd_vel 从 -0.16/-0.32/-0.48 rad/s 的转向斜坡开始,20:25:09 起全零。**缺陷**:SIGINT 只发到原进程组,`timeout` 自建的进程组未收到,四个文本流跑到 20:27 仍在写(bag 已正常停止);20:28 用 `pkill -INT -s <会话>` 按会话结束,stop_record.sh 已改为按会话发送 |
| 20:3x | `analyze_attempt.sh …/attempt-01 --goal -4.0 -1.0 0.0` | Git Bash → wsl.exe(脚本文件,rosbag2_py) | /mnt/d/RoboSim-Eval | 0(4 s) | attempt-01/result.json、trajectory.csv | **task_outcome=reached, validation=pass, data=complete, safety=unknown(未测)**;接受→结果 8.47 s 仿真 / 25.61 s 现实;终点 map 系:Nav2 反馈 (-4.250, -1.002, yaw 0.019) 误差 0.250 m,TF 合成 (-4.229, -1.021) 误差 0.230 m(容差 0.5 m;两者都是定位估计,非独立真值);停稳(|v|<0.05, |w|<0.1 持续 1 s 仿真时间)在 sim 519.53 s 确认,结果后最大 |v| 0.168 m/s(减速尾段)、最大 |w| 0.045 rad/s;trajectory.csv 含 904 条 odom、904 条 TF 合成 map 位姿、2405 条反馈位姿,各带 frame 与来源 |

## 位置来源交叉核对(2026-09-29 20:3x–20:4x)

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 20:3x | `temp/explore_sources.sh …/attempt-01/rosbag`(探索性,temp/ 不入库;结论已并入 analyze_attempt.py) | Git Bash → wsl.exe | /mnt/d/RoboSim-Eval | 0 | 会话记录 | 原地转身期间 odom 平移仅 2.9 cm,而 AMCL 的 map→odom 从 (-5.676, -1.000, -3.141) 变到最终 (-6.152, -0.870, 3.091) |
| 20:3x | `curl` 下载场景 USD 与机器人 payload USD 到 temp/usd/;`scripts/windows/inspect_usd.py`(Isaac python.bat + omni.usd.libs 的 pxr,仅子进程设置 PYTHONPATH/PATH);读 `exts/isaacsim.core.nodes/ogn/docs/OgnIsaacComputeOdometry.rst` | PowerShell → cmd → python.bat | D:\RoboSim-Eval | 0 | run-01/usd-inspection.txt(含 URL、sha256、输出) | 场景 USD:`/World/Nova_Carter_ROS` `xformOp:translate = (-6, -1, 0)`、`xformOp:orient = (6.1e-17, 0, 0, 1)`(yaw = π),与 Nav2 参数 amcl initial_pose 一致;机器人 USD:`transform_tree_odometry/isaac_compute_odometry_node -> isaacsim.core.nodes.IsaacComputeOdometry` 供 `ros2_publish_odometry`;该节点唯一输入是 chassis prim(文档:"Usd prim reference to the articulation root or rigid body prim"),即 /chassis/odom 取自仿真底盘状态、相对 Play 起点,无轮速/噪声模型 |
| 20:4x | `analyze_attempt.sh …/attempt-01 --goal -4.0 -1.0 0.0 --spawn -6.0 -1.0 3.141592653589793`(脚本新增 AMCL 独立来源) | Git Bash → wsl.exe | /mnt/d/RoboSim-Eval | 0 | attempt-01/result.json(已覆盖)、trajectory.csv(新增 904 行独立来源位姿) | **到达核对改用 AMCL 独立来源**:仿真状态里程计 + USD 出生位姿 → 终点 (-4.072, -1.053),到目标 0.090 m;AMCL 估计 0.230 m、Nav2 反馈 0.250 m。接受目标时 AMCL 与独立来源相差 0.324 m(Nav2 启动前机器人已缓爬离开出生点,而 set_initial_pose 仍用出生点);结束时相差 0.160 m(AMCL 转身时自行重定位了大部分) |

## 停止路径验证(stop_nav2.sh / stop_record.sh)

| 时间(本地) | 命令 | 退出码 | 证据 | 备注 |
| --- | --- | --- | --- | --- |
| 20:43:08 | `stop_nav2.sh …/run-01`(旧版:SIGINT 发整个进程组) | 0 | run-01/nav2-launch.meta、nav2-launch.log 末尾 | 所有进程退出,但子进程收到两次 SIGINT(直接 + launch 转发):组件容器清理 route_server 时 "Magick: abort due to signal 11 (SIGSEGV)",exit -6;rviz2 exit -6;"残留节点"告警判断为 ros2 daemon 缓存造成的误报:随后的 pgrep 未找到任何 Nav2/RViz 进程,但这个 pgrep 结果只在会话输出里,没有存文件;launch 自身的退出码当时没有记录(旧脚本) |
| 20:45:42 → 20:47:51 | run-02-stoptest:`start_nav2.sh` → `record_d0.sh …/record-test 60` → 8 s → `stop_record.sh` → `stop_nav2.sh` | 0 / 0 / 0 / 1 | run-02-stoptest/ | 记录器链路通过:6 个会话全部结束,bag 退出 0(15 s、997 条),`ros2 topic echo` 退出 2(ros2cli 在 KeyboardInterrupt 时返回 signal.SIGINT),tf2_echo 退出 0。stop_nav2 缺陷:`pgrep -s <会话> -f "ros2 launch …"` 匹配到了包装 bash(其命令行含同一字符串),SIGINT 被包装进程 trap,45 s 后升级 SIGTERM/SIGKILL,launch 退出码 143;无残留。脚本末尾的展示用 grep 无匹配导致退出码 1(已改为只反映残留) |
| 20:48:39 → 20:50:28 | run-03-stoptest:改为按父进程取 launch PID | 0(停止结果无残留) | run-03-stoptest/ | SIGINT 发到了 launch(59041),但 launch 日志在 SIGINT 后无任何输出 → launch 忽略 SIGINT。根因:非交互 shell 的 `&` 后台命令继承 SIGINT=忽略,Python 的 ros2 launch 保持忽略;C++ 子进程自己装处理函数所以 run-01 有反应;记录器在 `timeout` 下所以不受影响。仍靠 SIGTERM/SIGKILL 结束,无残留 |
| 20:51:44 → 20:52:41 | run-04-stoptest:包装进程前加 `env --default-signal=INT,TERM`(coreutils 9.4) | 0 | run-04-stoptest/nav2-launch.meta、nav2-launch.log | **修复确认**:stop_nav2.sh 只发了 SIGINT(launch),没有升级(rviz2 的 SIGKILL 是 launch 内部做的);13 s 全部退出、无残留进程、fresh discovery 无 Nav2 节点;pointcloud_to_laserscan "finished cleanly";**已知上游问题**:组件容器清理时仍 SIGSEGV(exit -6,与 run-01 相同),rviz2 在 launch 的 SIGINT→SIGTERM 超时后被 SIGKILL(-9),launch 退出码 1。三次尝试后结束该问题的排查(预算内) |

## 内部预审后的修复验证(2026-09-29 21:5x–22:10)

attempt-01 说明:这次尝试是用修复前的 record_d0.sh / stop_record.sh / stop_nav2.sh 采集的,所以没有各记录器的 .exit 退出码文件;4 个文本流比 bag 多跑到 20:28,最后按会话手动停止(上文 20:25:07 行)。分析只用 bag;tf_map_base.err(内容 "Unknown argument: 5")现已纳入版本管理。

| 时间(本地) | 命令 | 退出码 | 证据 | 结果 |
| --- | --- | --- | --- | --- |
| 21:5x | `wsl -d Ubuntu -- python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests` | 0 | 会话输出 | 分析脚本固定输入测试 14 passed |
| 21:5x | `wsl -d Ubuntu -- python3 temp/mutation_check.py`(副本:run-05-regress/mutation_check.py) | 0 | 会话输出 | 依次改坏 4 条规则(停稳恒为确认、不按目标 ID 过滤、ABORTED 当成功、关闭数据完整性检查),每次恰好一个对应测试失败;恢复后全部通过 |
| 21:5x | `analyze_attempt.sh …/attempt-01 --goal -4.0 -1.0 0.0 --spawn -6.0 -1.0 3.141592653589793`(重构后的分析脚本) | 0 | attempt-01/result.json、trajectory.csv(已覆盖) | execution completed、task reached、data complete、validation **pass**;目标 ID 取自转录 8e28b7ce…,--goal 与转录一致;到达判定改在停稳确认时刻(仿真 519.533 s):独立来源误差 0.091 m、AMCL 估计 0.231 m;数据完整性窗口内 /clock、odom 最长间隔 0.92 s,AMCL map→odom 最长间隔 1.86 s(门槛 2.0 s) |
| 22:0x | `scripts/windows/inspect_usd.py`(扩展:打印节点输入、连线、关系目标) | 0 | run-01/usd-inspection-wiring.txt | IsaacComputeOdometry 的 inputs:chassisPrim → /nova_carter_ros2_sensors/chassis_link;ROS2PublishOdometry 的 position/orientation/速度输入全部连自该节点,topicName = chassis/odom;odom→base_link TF 同样连自该节点;场景层对 chassis_link 的 over 覆盖没有任何属性 |
| 22:04:56 → 22:07:15 | run-05-regress 正向回归:start_nav2 → check_nav2_ready → 再次 start_nav2 → record_d0(60)→ stop_record → stop_nav2 | 0 / 0 / 3 / 0 / 0 / 0 | run-05-regress/regress-positive.txt、ready-220532.txt、record-test/、nav2-launch.meta | 就绪判定 READY;第二次启动被拒(已有 carter_navigation launch);记录器 6 个会话全部停止,退出码齐全(bag 2、echo 2、tf2_echo 0),bag 12.9 s / 818 条,必需话题都有数据;stop_nav2 通过归属核对,只发 SIGINT(launch),10 s 退出,无残留;launch 退出码 1(容器 SIGSEGV,rviz2 -11) |
| 22:07:3x → 22:09:07 | `temp/regress_negative.sh`(WSL;副本:run-05-regress/regress_negative.sh) | 0(9/9 PASS) | run-05-regress/regress-negative.txt 及 neg-* 文件 | 非数字 yaw → 2;--goal 与转录不一致 → 2 且 result.json 哈希不变;stop_nav2 面对无法确认归属的会话 → 拒绝(5),该会话仍存活;bag 缺失 → stop_record 5;畸形候选点 → map_overview 1;Nav2 未运行 → check_nav2_ready 1(NOT READY);setup_workspace 重跑 → 0(rosdep 模拟退出 0,日志写到 run-05-regress,不覆盖 D0b 证据) |

## D0d 验收判定

- Nav2 接受并完成目标 ✔(原始状态码 4,error_code 0,0 次恢复)
- 轨迹显示移动 ✔(独立来源 map x -6.566 → -4.072;先原地转身约 180°,再直行约 2.5 m)
- 到达且停稳 ✔(停稳确认时刻:AMCL 独立来源误差 0.091 m;AMCL 估计 0.231 m;均 < 0.5 m;停稳规则在结果后 1.15 s 仿真时间满足)
- 原始证据保留 ✔(bag 信息、反馈转录、文本流、result.json、trajectory.csv、USD 检查)
- 未验证:碰撞/接触;独立来源依赖"Play 后未重置、里程计从出生点起算"两个前提,不是单独的真值 topic;朝向未纳入验收(独立来源 yaw 0.072 rad)
