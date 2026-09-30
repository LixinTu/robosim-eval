# D1 命令记录(doctor 诊断工具)

分支 `feature/d1-doctor`。本机是官方不支持的配置(Windows 10 + 8 GB 显存)。三类验证分开记录:固定输入测试、ROS 假节点测试(不需要 Isaac)、真实 Isaac 集成。

## 常驻进程

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 23:38–23:42(三次运行) | `test_doctor_fake.sh` 内部 `setsid python3 tests/ros_fake/fake_isaac.py --duration 40 …`,每个用例一个,ROS_DOMAIN_ID=42 | 每次由脚本记录会话号,见各 `fake-*.log` | 每个用例启动后 1.5 s 运行一次 doctor | 脚本按会话号 `pkill -INT -s`,2 s 内未退出再 `-KILL` | 未单独记录(假节点只是测试夹具) | kill -INT(自己停止) |

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 23:3x | `pytest.sh tests/test_doctor_checks.py`(实现之前) | wsl.exe bash -l(非交互,脚本在 scratchpad) | /mnt/d/RoboSim-Eval | 2(收集错误) | 会话输出 | TDD 红灯:`ModuleNotFoundError: robosim_eval`,功能尚不存在 |
| 23:3x | `pytest.sh tests/`(实现判定逻辑之后) | 同上 | 同上 | 0 | 会话输出 | 29 passed(原 14 + doctor 15) |
| 23:3x | `pytest.sh tests/test_config.py`(实现之前) | 同上 | 同上 | 2(收集错误) | 会话输出 | TDD 红灯:`No module named robosim_eval.config` |
| 23:3x | `pytest.sh tests/` | 同上 | 同上 | 0 | 会话输出 | 37 passed |
| 23:38:16 | `scripts/wsl/test_doctor_fake.sh artifacts/d1/fake-01` | wsl.exe bash -l(非交互) | /mnt/d/RoboSim-Eval | 1 | fake-01/doctor-*.txt、fake-*.log | 6 个用例的退出码全部符合预期;`lidar_missing` 用时 12.7 s,超过当时设的 12 s。原因是上限设得比设计值紧:发现超时 5 s + 窗口 5 s + Python/rclpy 启停约 3 s。上限改为 15 s 并写进 doctor 说明 |
| 23:39:45 | 同上 → `fake-02` | 同上 | 同上 | 0 | fake-02/ | 6/6 PASS;结果表只在会话输出,随后让脚本把表写进 summary.txt |
| 23:40:41 | `scripts/wsl/doctor.sh --out artifacts/d1/real-01`(真实 Isaac,domain 0) | wsl.exe bash -l(非交互) | /mnt/d/RoboSim-Eval | 0 | real-01/doctor-20260929-234041.json | **healthy**。/clock 124 条、24.78 Hz、仿真 +2.050 s、RTF 0.41;odom 与 odom→base_link TF 各 24.38 Hz,最长间隔 0.065 s;点云 3.00 Hz,最长间隔 0.742 s,时间戳落后 /clock 0.267 s。Nav2 未运行 |
| 23:41:46 | `python3 artifacts/d1/mutation_check.py` | wsl.exe bash -l(非交互) | /mnt/d/RoboSim-Eval | 0 | mutation-check.txt | 7 种改坏(不判陈旧、不判过慢、缺发布者当静默、忽略时钟停滞、冻结时钟算推进、忽略环境错误、倒退算推进)各被至少一个测试抓到;恢复后 0 失败 |
| 23:42 | `pytest -v tests`(存档) | 同上 | 同上 | 0 | pytest.txt | 37 passed |
| 23:42:13 | `scripts/wsl/test_doctor_fake.sh artifacts/d1/fake-03` | 同上 | 同上 | 0 | fake-03/summary.txt 与各用例日志 | 6/6 PASS:healthy 0(5.8 s)、paused 10(2.8 s)、closed 11(5.8 s)、lidar_missing 11(10.7 s)、lidar_slow 12(5.8 s)、rmw_unset 13(5.7 s) |

## 未执行

- 真实 Isaac 的暂停测试(计划 D1 的验收操作)与关闭仿真测试:需要暂停或关闭用户的 Isaac,还没做。假节点测试已覆盖这两种情形的判定。
