# D5 命令记录(作品交付:README、三个演示、参数改动)

分支 `feature/d5-demo`(在 `feature/d4-batch` 之上)。本机是官方不支持的配置(Windows 10 + 8 GB 显存)。Isaac 是同一个实例(`start_isaac_ros2.ps1 -PythonServer` 启动,见 artifacts/d2/commands.md)。

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 01:3x–01:44 | `pytest tests/test_nav2_params.py`(先红:模块不存在)→ 实现 `robosim_eval/nav2_params.py` → 7、9 passed;`tests/test_config.py` 新增 3 个(先红)→ 通过 | wsl.exe bash -lc | D5 worktree | 0 | 会话输出 | 在批量运行期间用独立 worktree 开发,不改主工作区里运行器正在用的文件 |
| 01:4x | 对真实的 NVIDIA 参数文件做一次派生并 `diff` | wsl.exe bash | D5 worktree | diff 1 | 会话输出 | 只有第 192 行 `max_vel_x: 0.8` → `0.4` 不同 |
| 01:44:54 | 提交 `67a8ffa`(功能)与 `e7c7e92`(预测,docs/demo.md) | Git Bash | D5 worktree | 0 | git log(作者时间) | 预测写在复跑之前;变基后提交号变了,作者时间不变 |
| 02:00–02:04 | `sim.sh stop`、`sim.sh load <空场景>`,再用修复前的代码(`3b58422`)跑 `run_scenario.sh normal --out artifacts/d5/defect3-before` | wsl.exe bash -l | /mnt/d/RoboSim-Eval | 11 | defect3-before/normal-20260930-020110/、runner.txt | 缺陷 3 复现:`contacts_unavailable`(机器人不存在)在 `load_world` 之前;安全 unknown,评测 inconclusive,而机器人已到达 |
| 02:06:49 | 提交 `12a1544`(先加载场景再装接触监视) | Git Bash | D5 worktree | 0 | — | 见 docs/defect-record.md 缺陷 3 |
| 02:07:01 | `test_runner_fake.sh artifacts/d5/fake-01` | wsl.exe bash -l | /mnt/d/RoboSim-Eval | 0 | fake-01/summary.txt | 10/10,新增"声明参数生效 / 不生效"两例;全部固定输入测试 126 passed |
| 02:10 | 改坏检查:把"参数不符就报错"改成 `if False`,只跑"不生效"一例;再还原重跑 | wsl.exe bash | /mnt/d/RoboSim-Eval | 11 → 30 | 会话输出 | 改坏后运行照常进行(11),还原后报错并不发目标(30) |
| 02:10–02:11 | `sim.sh stop`、`sim.sh load D:/RoboSim-Eval/tests/assets/empty_stage.usda`、`sim.sh pose` | wsl.exe bash -l | 同上 | 0、0、3 | 会话输出 | 等同于 Isaac 刚启动、场景未加载;pose 报机器人不存在 |
| 02:11:06 | README 第 2 步:`wsl -d Ubuntu -- bash -l …/doctor.sh --out …/artifacts/d5/demo/doctor` | 新的 PowerShell | D:\RoboSim-Eval | 11 | demo/doctor/doctor-20260930-021108.json | 没有 /clock 发布者,与 README 一致 |
| 02:11:21–02:13:26 | README 第 2 步:`run_scenario.sh normal --out …/artifacts/d5/demo/runs` | 新的 PowerShell | 同上 | 0 | demo/run-normal.txt、demo/runs/normal-20260930-021122/ | 演示 1,也是缺陷 3 的同条件复跑:先加载场景,再装接触监视(8 个刚体);pass,真值距目标 0.049 m |
| 02:13:43–02:15:06 | `run_scenario.sh cancel --out …/artifacts/d5/demo/runs` | 新的 PowerShell | 同上 | 0 | demo/run-cancel.txt、demo/runs/cancel-20260930-021343/ | 演示 2:注入的取消在接受后 5 s,同一时刻收到 CANCELED 回执,1.47 s 后确认停车;pass |
| 02:15:30–02:25 | `run_batch.sh --scenarios normal,normal_slow --repeats 2 --out …/artifacts/d5` | wsl.exe bash -l(后台) | /mnt/d/RoboSim-Eval | 0 | batch-20260930-021530/(batch.json、runs/report.html) | 演示 3:4 次都到达;normal 2 pass,normal_slow 1 pass、1 inconclusive(自发卡顿 2.19 s 墙钟) |
| 02:2x | `python3 artifacts/d5/compare_speed.py batch-20260930-021530/runs` | wsl.exe bash -lc | /mnt/d/RoboSim-Eval | 0 | compare-speed-01.md | 与预测逐条对照见 docs/demo.md |
| 02:2x | 核对 26 次真实运行里运行器与 bag 的接受时刻 | Git Bash(只读 result.json) | D:\RoboSim-Eval\artifacts | 0 | 会话输出 | 25 次偏差 1.1–2.1 s,1 次 0.07 s:缺陷 4 |
| 02:2x | `pytest tests/test_runner_fsm.py`(先红:refresh_clock 不存在)→ 实现 → 128 passed;`test_runner_fake.sh artifacts/d5/fake-02` | wsl.exe bash -l | /mnt/d/RoboSim-Eval | 0 | fake-02/summary.txt | 10/10;提交 `9ae722b` |
| 02:31:09–02:32:42 | `run_scenario.sh cancel --out …/artifacts/d5/defect4-after` | 新的 PowerShell | D:\RoboSim-Eval | 0 | defect4-after/cancel-20260930-023111/、defect4-after-cancel.txt | 缺陷 4 修复后复跑:接受时刻与 bag 差 0.033 s;取消在真实接受后 4.97 s;pass |
