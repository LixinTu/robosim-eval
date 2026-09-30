# D4 命令记录(批量复跑与报告)

分支 `feature/d4-batch`(从 `feature/d3-verdicts` 的 `3b58422` 分出)。本机是官方不支持的配置(Windows 10 + 8 GB 显存)。Isaac 是同一个实例(`start_isaac_ros2.ps1 -PythonServer` 启动,见 artifacts/d2/commands.md),sim_control 与 Python 执行服务都已打开。

## 命令

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 01:30:10–01:57:19 | `run_batch.sh --out /mnt/d/RoboSim-Eval/artifacts/d4`(默认 normal、bypass、unreachable 各 3 次,交替进行) | wsl.exe bash -l(后台) | /mnt/d/RoboSim-Eval | 0 | batch-20260930-013010/(batch.json、每次一个 NN-情形-次序.txt、runs/ 下 9 个运行目录、report.html、summary.json) | 9 次运行退出码都是 0,评测都是 pass。第 1 次开始时仓库 HEAD 是 `4332d79`,之后两次只改文档的提交(`d33d69c`、`3b58422`)使后 8 次记录为 `3b58422`;`git diff --stat 4332d79 3b58422 -- robosim_eval scripts configs tests` 为空,9 次用的代码相同 |
| 01:58:22–01:59:56 | `stuck-start/run_rotation_response.sh --hold 20`(Nav2 未运行;每档先复位,再发 20 s 墙钟的原地转向指令,用 sim_control 真值量转角) | wsl.exe bash | /mnt/d/RoboSim-Eval | 0 | stuck-start/rotation-response-01.txt | 0.0368 rad/s:8.0 s 仿真时间转 0.0004 rad(应转 0.30 rad);0.1105:0.25 rad;0.2579:1.71 rad |
| 02:0x | 报告改进(`2b8f27c`,5 个新固定输入测试先红后绿,全部 114 passed)后,`python3 -m robosim_eval.report batch-20260930-013010/runs` 按保存的记录重新生成 | wsl.exe bash -lc | D4 worktree | 0 | runs/report.html、runs/summary.json;旧版保留为 `*.before-report-fix.*` | 旧页头只写了一个 commit、计数打印成 Python 字典、没有恢复次数列 |
| 02:0x | `stuck-start/run_bag_scans.sh`(只读:rosbag 里第一条 /plan 与 AMCL 朝向、第一条 /cmd_vel;cmd_vel.txt 开头最小转向段的长度) | wsl.exe bash | /mnt/d/RoboSim-Eval | 0 | stuck-start/bag-scans-01.txt | 覆盖 D2–D5 所有留有 bag 的真实运行 |

## 结果(真实 Isaac,9 次全部留档)

| 运行 | 评测 | 任务结果 | 安全 | 数据 | Nav2 终态 / 恢复 | 距目标(真值,m) | 接受到结果(仿真 s) | 复位误差 | 开头卡住 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| normal-20260930-013010 | pass | reached | pass | complete | SUCCEEDED / 5 | 0.235 | 52.53 | 0.07 mm | 是 |
| bypass-20260930-013406 | pass | reached | pass | complete | SUCCEEDED / 5 | 0.319 | 53.85 | 0.07 mm | 是 |
| unreachable-20260930-013807 | pass | unreachable | pass | complete | ABORTED 208 / 15 | 3.963 | 15.15 | 0.07 mm | — |
| normal-20260930-014009 | pass | reached | pass | complete | SUCCEEDED / 5 | 0.235 | 51.65 | 0.07 mm | 是 |
| bypass-20260930-014400 | pass | reached | pass | complete | SUCCEEDED / 5 | 0.273 | 54.27 | 0.07 mm | 是 |
| unreachable-20260930-014759 | pass | unreachable | pass | complete | ABORTED 208 / 15 | 3.972 | 14.92 | 0.07 mm | — |
| normal-20260930-014949 | pass | reached | pass | complete | SUCCEEDED / 5 | 0.312 | 51.82 | 0.07 mm | 是 |
| bypass-20260930-015337 | pass | reached | pass | complete | SUCCEEDED / 0 | 0.289 | 14.70 | 0.07 mm | 否 |
| unreachable-20260930-015531 | pass | unreachable | pass | complete | ABORTED 208 / 15 | 3.967 | 14.88 | 0.07 mm | — |

- 每次运行前都经 sim_control 复位,并用真值核对:9 次都在出生点 0.07 mm 以内,朝向偏差 1.1e-5 rad(每个运行目录 events.jsonl 的 reset_check)。
- 每次准备阶段的 doctor 都是 0,没有触发有限重查。
- 接触监视 9 次都在工作,没有记录到机器人与地面以外物体的接触;bypass 的箱子没有被碰到。
- 9 次都有同一条警告:AMCL 的 map→odom 间隔超过 2 s(约 2.3–2.6 s)。它是参考数据流,不影响数据完整性结论。
- 报告按情形分组,不合并成功率;平均用时只统计到达的运行并注明。normal 平均 52.00 s(3/3),bypass 40.94 s(3/3)。这两个平均值主要反映"开头卡住"(约 38 s),不是导航速度。
- 这 9 次是工程试运行,不代表导航性能。

## "开头卡住":已查明与未查明

现象:发目标后,控制器持续输出同一个很小的原地转向指令 +0.0368 rad/s(= max_vel_theta 0.7 / 19,DWB 在 [-0.7, 0.7] 上 20 个采样里绝对值最小的一档),机器人基本不动。约 104 s 墙钟(约 38 s 仿真时间)里 Nav2 进度检查触发 5 次恢复,之后正常转向、行驶并到达。本批 6 次可到达的运行中有 5 次出现。

| 环节 | 证据 | 状态 |
| --- | --- | --- |
| 起始姿态与路径方向正好相反 | bag-scans-01.txt:目标在正东的 20 次运行(unreachable 的目标在西侧,不在内),开头 AMCL 朝向都是 180.00°,第一条全局路径方向都是 0° 或 -1.5°(机器人在 (-6, -1) 朝西) | 已证实 |
| 哪些运行卡住,取决于第一条路径起点落在哪半格 | 第一条路径起点为 (-6.025, -1.025)(机器人南侧)的 16 次里,13 次 bag 中第一条 /cmd_vel 是 +0.0368,3 次是 +0.16 / +0.2579;起点为 (-6.025, -0.975)(北侧)的 4 次都立即顺时针转(-0.16 或 -0.7),没有卡住。"第一条指令"只是近似分类:cancel-012426 的文本流开头是 0.16、0.2579,随后也落进 +0.0368 段 | 已观察到;这是 16 + 4 次的统计,不是确定规律 |
| 机器人对 0.0368 rad/s 没有响应 | rotation-response-01.txt:同一复位起点,0.0368 rad/s 持续 8.0 s 仿真时间只转 0.0004 rad;0.1105 转 0.25 rad、0.2579 转 1.71 rad | 已证实(直接实验) |
| 机器人不转,状态不变,DWB 就一直选同一档,直到进度检查触发恢复 | cmd_vel.txt:卡住期间指令保持 +0.0368,每次恢复时短暂变 0 | 与数据一致 |
| DWB 为什么把最小一档打分最高 | 运行时没有记录各评分项的分数 | **未查明** |

这不是评测工具的缺陷,是这个情形的设计(目标正好在背后)与 Nav2/Isaac 行为叠加的结果。它只拉长用时、增加恢复次数,判定都正确。接触监视是否影响卡住的概率没有定论:目标在正东的运行中,开接触监视的 15 次里 12 次以 +0.0368 开头,不开的 5 次里 1 次(normal-004634,8 s 后被中断);两组的路径起点分布也不同,不能据此归因。可做但没做的缓解:让出生朝向不与路径正好相反,或调 DWB 的最小转速;都会改变情形,留待以后。
