# D1 交接说明(给独立审查者)

## 范围

- 基线 `16aef89`(D0 分支 `feature/d0-environment` 的最新提交),被审版本 `c6cbdab`(分支 `feature/d1-doctor`)。
- 代码与文档:`git diff 16aef89 c6cbdab -- . ':(exclude)artifacts'`,15 个文件,约 1100 行新增。
- 证据:`artifacts/d1/`(不属于被审代码,用来核对主张)。

## 需求

- 计划书 `RoboSim-Eval-Plan-and-Setup-ZH(1).md`:A3 表中 `robosim_eval/doctor.py` 一行("环境、ROS 数据与接口检查");A4 的 D1 一行("运行 doctor;暂停或关闭仿真后再运行 | 正常时报告真实数据;异常时在有限时间内非零退出 | 正常与异常输出、退出码、消息频率和新鲜度");A5 的断流规则("按各主题正常周期配置;初值为 max(5 个正常周期,2 秒现实时间)";主机时间用于防止暂停或断连后无限等待)。
- `docs/plan.md` 在基线提交里的 §11(D1 第一个小验收)。

## 实现要点

| 文件 | 作用 |
| --- | --- |
| `robosim_eval/doctor_checks.py` | 纯判定逻辑,不导入 ROS。退出码:0 正常;10 仿真不推进;11 数据缺失;12 降级;13 环境或接口错误。优先级写在模块说明里 |
| `robosim_eval/doctor.py` | rclpy 采样与命令行入口:先建订阅再做发现;best-effort QoS;/clock 停滞满 `clock_stall_s` 就提前结束窗口;没有 /clock 发布者时跳过窗口;可写 JSON 报告 |
| `robosim_eval/config.py`、`configs/baseline.yaml` | 话题映射、期望环境、阈值;阈值依据 D0 实测频率,写在文件注释里 |
| `scripts/wsl/doctor.sh` | 加载 ROS 与 DDS 环境,60 s 硬上限 |
| `scripts/wsl/test_doctor_fake.sh`、`tests/ros_fake/` | 假节点集成测试:ROS domain 42 上的假 Isaac 发布者,6 个用例 |
| `scripts/wsl/doctor_watch_pause.sh` | 真实暂停验收的辅助脚本:循环运行 doctor,抓暂停时与恢复后各一次 |

## 主张与证据

| 主张 | 证据 |
| --- | --- |
| 固定输入测试 37 个全部通过(D0 原有 14 个 + D1 新增 23 个) | `artifacts/d1/pytest.txt` |
| 判定规则被测试约束:7 种改坏各被至少一个测试抓到 | `artifacts/d1/mutation-check.txt`、`artifacts/d1/mutation_check.py` |
| 假节点测试 6/6 符合预期,每次运行不超过 15 s | `artifacts/d1/fake-03/summary.txt` |
| 真实 Isaac 运行时 healthy,退出 0 | `artifacts/d1/real-01/` |
| 用户按暂停后判"不推进",退出 10;恢复后退出 0 | `artifacts/d1/real-02-pause/` |

## 已知限制

- 真实"关闭 Isaac"的情形只在假节点测试里验证过(没有关闭用户的 Isaac)。
- 时间上限约 13 s:发现最多 5 s、窗口 5 s、Python 与 rclpy 启停约 3 s。
- 仿真控制扩展没有启用,暂停由用户在 GUI 操作。
