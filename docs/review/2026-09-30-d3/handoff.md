# D3 交接说明(给独立审查者)

## 范围

- 基线 `cfa8245`(D2 分支含审查材料的提交),被审版本 `d33d69c`(分支 `feature/d3-verdicts`)。
- `git diff cfa8245 d33d69c -- . ':(exclude)artifacts'`。其中 `robosim_eval/report.py`、`robosim_eval/batch.py`、`scripts/wsl/run_batch.sh`、`tests/test_report.py` 属于 D4,不在本轮范围。
- 证据:`artifacts/d3/`;缺陷记录 `docs/defect-record.md`。

## 需求

计划书 `docs/reference/RoboSim-Eval-Plan-and-Setup-ZH.md`:A4 的 D3 一行("跑正常、不可达、取消/断流场景 | 到达、超时、碰撞、取消分开判定;停止可验证 | 原始数据、判定理由、必要回归测试");A5 的判定规则(不能把中止一律解释成不可达;实际到达但接触数据丢失不能写成安全通过;接触过滤地面与自身接触;未测量不能当零碰撞;必做的坏数据测试:虚假成功、缺接触数据、时间倒退、取消无回执);A1(真实缺陷的复现、修复与同条件复跑)。

## 实现要点

| 文件 | 作用 |
| --- | --- |
| `robosim_eval/evaluator.py` | 纯判定:到达看真值、不可达需预设标记加离线证据、超时与取消来自运行器、接触安全、必需与参考数据流、与情形预期比较 |
| `robosim_eval/runner.py`(D3 部分) | 复位前装接触监视、放障碍后清空、收尾时取回;注入取消与暂停;按情形覆盖超时;复位后计时钟倒退;结果改用判定模块 |
| `robosim_eval/runner_fsm.py`(D3 部分) | 计划内取消(不算操作员中断)、取消原因、按时间线丢弃复位前的 odom 样本 |
| `robosim_eval/contacts.py`、`robosim_eval/kit/contact_monitor.py`、`robosim_eval/kit/diag_stage.py`、`scripts/windows/isaac_py.ps1` | 接触监视:Isaac 内的 PhysX 接触报告,经用户同意打开的 Python 执行服务取数(只监听 127.0.0.1,需要令牌;客户端只接受 robosim_eval/kit 下的文件) |
| `robosim_eval/config.py`、`configs/baseline.yaml`、`configs/assets/low_box.usda` | 接触过滤、数据流分级、七个情形(含预设不可达的证据与四个故障注入) |

## 主张与证据

| 主张 | 证据 |
| --- | --- |
| 固定输入测试 109 个全部通过;判定模块改坏检查 8/8 | 会话输出、`artifacts/d3/mutation-check.txt` |
| 真实各情形:normal、bypass、unreachable、cancel、timeout 评测 pass;dropout 判 inconclusive(断流);collision 判 fail(轮子与矮箱子接触) | `artifacts/d3/commands.md` 的结果表与各运行目录 |
| 运行器缺陷(复位前 odom 残留)已复现、修复、同条件复跑通过 | `docs/defect-record.md` |

## 已知限制

- "开头卡住"间歇出现,机制未查明(见 commands.md)。
- 接触监视依赖 Python 执行服务;没有它时安全字段为 unknown。
- 预设不可达的证据来自离线地图分析,不是在仿真里证明的。
