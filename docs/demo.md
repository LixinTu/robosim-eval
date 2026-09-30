# D5 演示记录:三个真实操作

计划 §D 要求三个真实操作:正常导航并打开记录;一个失败或取消案例并解释;改一个事先说明的参数、先预测再复跑对比。本文件先写预测(提交时间早于复跑),复跑结果写在后面,预测不回改。

## 操作 1:从新终端启动,正常导航并打开记录

条件:Isaac 已由 `start_isaac_ros2.ps1 -PythonServer` 启动(同一实例,见 artifacts/d2/commands.md)。为了等同于"Isaac 刚启动、场景还没加载",先经 sim_control 停止仿真并载入空场景 `tests/assets/empty_stage.usda`(`sim.sh stop`、`sim.sh load D:/RoboSim-Eval/tests/assets/empty_stage.usda`,之后 `sim.sh pose` 报机器人不存在)。然后在新的 PowerShell 里逐字执行 README 第 2 步的两条命令。

| 步骤 | 结果 |
| --- | --- |
| `doctor.sh --out …/artifacts/d5/demo/doctor` | 退出 11:`/clock` 没有发布者(场景没加载,仿真没在跑),与 README 写的一致 |
| `run_scenario.sh normal --out …/artifacts/d5/demo/runs` | 退出 0,约 2 分钟;运行目录 `artifacts/d5/demo/runs/normal-20260930-021122` |

打开记录(`events.jsonl`,括号里是仿真时间):

1. 准备:仿真状态 stopped → 发现机器人不存在,加载仓库场景 → 装接触监视(8 个刚体)→ sim_control 复位 → 真值核对:距出生点 0.07 mm、朝向偏差 1.1e-5 rad → 清掉复位与落地产生的 48 个接触事件 → doctor 退出 0。
2. 就绪:启动 Nav2,13.35 s 墙钟后 10 个生命周期节点都 active、动作服务就绪。
3. 执行:开始录制,发目标 (0, -1),被接受(5.92 s);Nav2 在 20.35 s 返回 SUCCEEDED,2 次恢复。
4. 停车确认:21.48 s 确认静止满 1 s,读真值 (0.032, -1.037)。
5. 收尾:取回接触数据(0 个事件)、停止录制、离线分析、停止 Nav2。

`result.json`:执行 completed、任务 reached、安全 pass(有实测,没有与地面以外物体的接触)、数据 complete、评测 **pass**;真值距目标 0.049 m(容差 0.5 m),接受到结果 13.33 s 仿真时间,没有警告。这次运行同时是缺陷 3 修复后的同条件复跑(见 docs/defect-record.md)。

## 操作 2:取消案例及解释

命令:`run_scenario.sh cancel --out …/artifacts/d5/demo/runs`,退出 0。运行目录 `artifacts/d5/demo/runs/cancel-20260930-021343`。

cancel 是有意注入的故障:`configs/baseline.yaml` 里这个情形的 `inject: {cancel_after_sim_s: 5.0}`,预期结果 canceled。

下表的仿真时间是运行器记录的。这次演示时,运行器记的接受时刻比 bag 里的实际接受时刻(7.33 s)早 1.35 s,这是后来发现的缺陷 4,见下文。

| 仿真时间(运行器记录) | 事件 | 解释 |
| --- | --- | --- |
| 5.98 s | 目标被接受,进入 EXECUTING | 与 normal 相同的起点和目标 |
| 10.98 s | `inject_cancel`,状态 CANCELING,发出取消请求 | 运行器按配置在"接受后 5 s"取消,但接受时刻是旧的,实际是真实接受后 3.65 s;取消原因记为 injected,不算操作员中断 |
| 10.98 s | Nav2 回 CANCELED,状态 STOP_CONFIRM | 有终态回执;如果 10 s 墙钟内没有回执,运行器会判出错并中止批次(退出 31) |
| 12.45 s | 确认静止满 1 s,读真值,进入收尾 | 只用终态之后的里程计判断停稳(缺陷 1 的修复) |

`result.json`:任务 canceled、安全 pass、数据 complete、评测 **pass**。评测通过的依据是"结果与情形预期一致,而且取消有回执、停车已确认",不是"导航成功";此时真值距目标 5.89 m,机器人确实没到。如果同样的取消发生在一个预期 reached 的情形里,评测会是 fail。

**这个案例还暴露了缺陷 4**:核对运行器与 bag 的接受时刻时发现,运行器在同步启动录制器的约 4 s 墙钟里没有处理 `/clock`,发目标时手里的仿真时间是旧的。D3 以来每次真实运行的接受时刻都晚记了 1.1–2.1 s(按仿真时间),所以导航时限和注入的取消、暂停都提前约 1.5 s 触发。修复(`9ae722b`)后同条件复跑 `artifacts/d5/defect4-after/cancel-20260930-023111`:运行器与 bag 的接受时刻只差 0.033 s,取消在真实接受后 4.97 s 发出,评测 pass。见 docs/defect-record.md 缺陷 4。

## 操作 3:参数变更的预测(复跑前写定)

### 改什么

只改一个参数:Nav2 DWB 控制器 `controller_server.ros__parameters.FollowPath.max_vel_x`,0.8 → 0.4 m/s(机器人前进速度上限减半)。

- 情形 `normal_slow`(`configs/baseline.yaml`)与 `normal` 相同:同一起点、同一目标 (0, -1)、无障碍、同样的时限和判定门槛;唯一差别是 `nav2_params` 这一项。
- 参数文件不复制进仓库:运行器每次从 NVIDIA carter_navigation 的原始参数文件生成 `<运行目录>/nav2_params.yaml`,只改这一行(`robosim_eval/nav2_params.py`,其余字节不变,并用解析结果核对),经 `params_file:=` 传给 launch。
- Nav2 起来后,运行器通过 `/controller_server/get_parameters` 读回实际值;不是 0.4 就判运行出错、不发目标(`robosim_eval/runner.py`)。
- 对照组:同一批次里交替运行 `normal` 与 `normal_slow`,同一代码、同一 Isaac 会话。

### 已有基线(max_vel_x = 0.8,真实运行)

| 运行 | 开头卡住 | 接受后开始移动(仿真 s) | 行驶段(仿真 s) | 峰值线速度 m/s | 移动时平均线速度 m/s | 路程 m |
| --- | --- | --- | --- | --- | --- | --- |
| d3/runs-diagnosis/normal-012548 | 否 | 2.4 | 13.3 | 0.803 | 0.495 | 5.90 |
| d3/runs/normal-010104 | 是 | 38.0 | 17.3 | 0.808 | 0.434 | 6.12 |
| d4/…/normal-013010 | 是 | 37.9 | 16.2 | 0.809 | 0.428 | 6.13 |
| d4/…/normal-014009 | 是 | 38.5 | 14.9 | 0.806 | 0.439 | 6.02 |

"行驶段"= 里程计线速度首次超过 0.05 m/s 到 Nav2 返回结果;"开头卡住"见 `docs/defect-record.md` 末节,与本参数无关(卡住期间线速度指令为 0)。数据来自各运行目录的 `trajectory.csv` 与 `result.json`。

### 预测

| 量 | 基线 | 预测(max_vel_x = 0.4) | 依据 |
| --- | --- | --- | --- |
| Nav2 结果、任务结果、安全、评测 | SUCCEEDED、reached、pass、pass | 不变 | 只限速,路径和目标容差不变 |
| 到达误差(真值) | 0.23–0.29 m | 仍 ≤ 0.5 m,量级不变 | 目标检查器 0.25 m 未改 |
| 峰值线速度 | 0.80–0.81 m/s | ≤ 0.42 m/s,且 ≥ 0.35 m/s | DWB 只在 [0, 0.4] 采样前进速度 |
| 移动时平均线速度 | 0.43–0.50 m/s | ≤ 0.40 m/s | 同上 |
| 路程 | 5.9–6.1 m | 5.8–6.3 m | 全局规划器与地图未变 |
| 行驶段时长 | 13.3–17.3 s | 19–30 s,即基线的约 1.3–1.9 倍,不到 2 倍 | 约 6 m 巡航从约 7.5 s 变约 15 s;原地转向和末段减速不受此参数影响 |
| 开头卡住 | 4 次中 3 次 | 不因本参数改变,可能出现也可能不出现 | 卡住时前进速度指令本来就是 0 |
| 最大角速度 | ≤ 0.7 rad/s | 不变 | max_vel_theta 未改 |

预测不成立的判读:峰值速度超过 0.42 m/s 说明参数没有生效或另有速度来源;行驶段短于 19 s 或长于 30 s 说明巡航段在总时长里的占比与上面估计不符。两种情况都照实记录,不改预测。

## 复跑结果

批次 `artifacts/d5/batch-20260930-021530`(02:15:30 开始,在预测提交之后),`run_batch.sh --scenarios normal,normal_slow --repeats 2`,交替运行,同一代码(`12a1544`,没有未提交改动)、同一 Isaac 会话。4 次都在复位后开始,真值核对通过。normal_slow 两次都从运行中的 controller_server 读回 `FollowPath.max_vel_x = 0.4`。对比表由 `artifacts/d5/compare_speed.py` 只从保存的记录算出,见 `artifacts/d5/compare-speed-01.md`:

| 运行 | 评测 | Nav2 / 恢复 | 距目标(真值,m) | 接受后开始移动(s) | 行驶段(s) | 峰值线速度 | 移动时平均线速度 | 峰值角速度(rad/s) | 路程(m) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| normal-021530 | pass | SUCCEEDED / 0 | 0.213 | 0.5 | 15.7 | 0.801 | 0.522 | 1.008 | 6.71 |
| normal-022017 | pass | SUCCEEDED / 0 | 0.298 | 0.6 | 14.2 | 0.802 | 0.582 | 1.022 | 6.88 |
| normal_slow-021734 | inconclusive | SUCCEEDED / 1 | 0.173 | 1.0 | 23.2 | 0.411 | 0.318 | 0.688 | 6.49 |
| normal_slow-022225 | pass | SUCCEEDED / 1 | 0.095 | 1.0 | 23.0 | 0.414 | 0.320 | 0.724 | 6.57 |

逐条对照预测:

| 预测 | 结果 | 判断 |
| --- | --- | --- |
| Nav2 结果、任务结果、安全、评测都不变 | 4 次都是 SUCCEEDED、reached、安全 pass。评测:normal 两次 pass;normal_slow 一次 pass,一次 inconclusive | **部分成立**。那次 inconclusive 的原因与参数无关:导航中 Isaac 自发卡住,`/clock`、odom、TF 三路同时停了 2.19 s 墙钟(超过 2 s 门槛),期间仿真时间只前进 0.017 s(一个步长)。评测按规则判数据不完整。D4 的 9 次没有出现过这种卡顿,原因没查 |
| 到达误差 ≤ 0.5 m,量级不变 | 0.173、0.095 m(同批 normal 0.213、0.298) | 成立 |
| 峰值线速度 ≤ 0.42 且 ≥ 0.35 m/s | 0.411、0.414(normal 0.801、0.802) | 成立 |
| 移动时平均线速度 ≤ 0.40 m/s | 0.318、0.320(normal 0.522、0.582) | 成立 |
| 路程 5.8–6.3 m | 6.49、6.57 m | **不成立**。预测范围取自基线里以"开头卡住"为主的运行:那些运行先原地转身、再直线行驶。本批 4 次都没有卡住,机器人边转边走,路程更长,normal 也是 6.71、6.88 m,同样超出。同批比较,慢速组略短 |
| 行驶段 19–30 s,约为基线的 1.3–1.9 倍 | 23.2、23.0 s;同批 normal 15.7、14.2 s,约 1.55 倍 | 成立 |
| 开头卡住不因参数改变 | 本批 4 次都没有出现 | 无法检验 |
| 最大角速度 ≤ 0.7 rad/s,不变 | normal 1.008、1.022;normal_slow 0.688、0.724 | **不成立**。预测表里的基线值是按参数 max_vel_theta = 0.7 推出来的,没有实测。里程计实测的角速度在 0.8 m/s 时会超过 0.7,限速后回到 0.7 附近,所以角速度也随 max_vel_x 改变 |
| (没有预测)恢复次数 | normal 0、0;normal_slow 1、1 | 预测外。两次恢复都出现在转向阶段:NavFn 重新规划时报 "Failed to create a plan from potential when a legal potential was found",规划失败触发了一次恢复。同批 normal 没有出现;原因没查 |

说明:
- "接受后开始移动"用的是离线分析从 bag 取的接受时刻。运行器自己记的接受时刻在这次复跑时还有缺陷 4(旧的仿真时间,见 docs/defect-record.md),已在 `9ae722b` 修复。行驶段、峰值、路程不依赖接受时刻。
- 上面"已有基线"表中的"接受后开始移动"一列用的是运行器的旧接受时刻,比实际大约 1.1–1.7 s。预测不回改,在这里说明。
- 每组只有 2 次,只能说明方向和量级,不是统计结论。
