# D2 交接说明(给独立审查者)

## 范围

- 基线 `293ebf1`(D1 分支含审查材料的提交),被审版本 `db5b161`(分支 `feature/d2-runner`)。
- `git diff 293ebf1 db5b161 -- . ':(exclude)artifacts'`。其中 `scripts/windows/isaac_py.ps1` 与 `robosim_eval/kit/contact_monitor.py` 是 D3 的准备,还没在 Isaac 里运行过,不在本轮范围。
- 证据:`artifacts/d2/`(不属于被审代码)。

## 需求

计划书 `docs/reference/RoboSim-Eval-Plan-and-Setup-ZH.md`:A4 的 D2 一行("用配置运行一次 A→B | 保存接受、反馈、结果与轨迹;中断也收尾 | 单次运行目录、日志、状态机验证");A5(状态字段、各段超时、停稳、断流、停车未确认时中止批次);A6(每次运行的文件)。

## 实现要点

| 文件 | 作用 |
| --- | --- |
| `robosim_eval/runner_fsm.py` | 纯状态机:允许的转换、各段期限、最终执行状态;停稳跟踪器;准备阶段 doctor 的重查策略 |
| `robosim_eval/runner.py` | 运行器:准备(清单、生效配置、复位与真值核对、障碍、doctor)→ 等 Nav2 就绪 → 录制与发目标 → 执行、超时、中断、取消 → 停车确认与真值 → 收尾(停止录制、离线分析、停止 Nav2、合并 result.json) |
| `robosim_eval/run_io.py` | manifest.json、config.resolved.yaml、events.jsonl、与 D0 分析脚本兼容的发目标转录 |
| `robosim_eval/sim_adapter.py`、`sim_math.py` | Isaac sim_control(simulation_interfaces)客户端;护栏:不请求退出状态,只删除本工具生成的实体 |
| `robosim_eval/config.py`、`configs/baseline.yaml` | sim、run、scenarios 三节 |
| `scripts/wsl/run_scenario.sh`、`sim.sh`、`test_runner_fake.sh`,`tests/ros_fake/fake_nav2.py` | 入口脚本与假节点测试 |
| `scripts/windows/start_isaac_ros2.ps1` | 默认打开 sim_control;`-PythonServer`(用户决定)打开只监听本机、需要令牌的 Python 执行服务 |

## 主张与证据

| 主张 | 证据 |
| --- | --- |
| 固定输入测试 77 个全部通过 | 会话输出(见 `artifacts/d2/commands.md`) |
| 运行器假节点测试 8/8:成功、中止、导航超时、被拒、中断、取消无回执、停不下来、没有 action server | `artifacts/d2/fake-04/summary.txt` |
| 真实正常 A→B:reached,真值离目标 0.264 m | `artifacts/d2/runs/normal-20260930-004343/` |
| 真实导航中中断:取消、CANCELED、停车确认、收尾,exit 20 | `artifacts/d2/runs/normal-20260930-004634/` |
| 复位后真值核对回到出生点 | `artifacts/d2/simctl-03/` |

## 已知限制

- 正常运行的评测结论仍是 inconclusive:沿用的 D0 分析脚本把 AMCL map→odom 的 2.3–2.5 s 空档算作数据不完整;D3 会区分判定必需与仅作参考的数据流。
- 接触未测量(safety unknown);超时只在假节点测试里触发过。
- 运行器调用 D0 的 bash 脚本(start_nav2、record_d0、stop_record、analyze_attempt、stop_nav2)。
