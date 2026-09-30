# D5 交接说明(给独立审查者)

## 范围

- 基线 `02de625`(D4 分支末端),被审版本 `24fa308`(分支 `feature/d5-demo`)。
- `git diff 02de625 24fa308 -- . ':(exclude)artifacts' ':(exclude)docs/review'`。
- 证据:`artifacts/d5/commands.md`;演示记录 `docs/demo.md`;缺陷记录 `docs/defect-record.md` 的缺陷 3。

## 需求

计划书 `RoboSim-Eval-Plan-and-Setup-ZH(1).md`:A4 的 D5 一行("按 README 从新终端启动并演示 | 别人能照着运行;用户能定位代码和证据 | README、短演示、diff、审查记录");§D(三个真实操作:正常导航并打开记录;一个失败/取消案例并解释原因;改变一个事先说明的参数,预测行为,再复跑对比;明确哪些来自 NVIDIA/Nav2、哪些自己实现、哪些得到 AI 辅助;不把现成控制器说成自己实现)。

## 实现要点

| 文件 | 作用 |
| --- | --- |
| `README.md` | 从新终端启动、结果文件、三个演示入口、来源与 AI 参与、已知限制 |
| `robosim_eval/nav2_params.py` | 从 NVIDIA 原始参数文件派生运行目录里的参数文件:只改声明的叶子值所在的那一行,其余字节不变,并解析两份文本核对 |
| `robosim_eval/runner.py`、`robosim_eval/runner_fsm.py`(D5 部分) | 情形声明 `nav2_params` 时派生参数文件、以 `params_file:=` 启动 Nav2、从运行中的节点读回核对,不符就判出错且不发目标;先加载场景再装接触监视(缺陷 3);发目标前刷新仿真时间(`refresh_clock`,缺陷 4) |
| `robosim_eval/config.py`、`configs/baseline.yaml` | `nav2_params` 字段与校验;情形 `normal_slow` |
| `tests/ros_fake/fake_nav2.py`、`scripts/wsl/test_runner_fake.sh`、`tests/ros_fake/runner_fake.yaml` | 假 controller_server 参数;"参数生效 / 不生效"两例;脚本改为用自身所在的检出目录 |
| `docs/demo.md`、`artifacts/d5/compare_speed.py` | 三个演示的记录;参数对比表只从保存的记录计算 |
| `tests/assets/empty_stage.usda` | 空场景,用来模拟"Isaac 刚启动、场景未加载" |

## 主张与证据

| 主张 | 证据 |
| --- | --- |
| 固定输入测试 128 passed;运行器假节点测试 10/10;"参数不生效"一例的改坏检查成立 | `artifacts/d5/commands.md`、`artifacts/d5/fake-01/summary.txt` |
| README 第 2 步的命令在新的 PowerShell 里逐字执行通过 | commands.md;`artifacts/d5/demo/` |
| 预测写在复跑之前 | `git log --format='%h %ad' e7c7e92`(作者时间 01:44:54);复跑批次从 02:15:30 开始 |
| 缺陷 3、缺陷 4 复现、修复、同条件复跑 | `docs/defect-record.md` 缺陷 3、4 |

## 已知限制

- 参数对比每组只有 2 次;normal_slow 第 1 次遇到一次自发的 Isaac 卡顿(三路数据同时停 2.19 s 墙钟),评测按规则判 inconclusive。
- 缺陷 3 的修复没有固定输入测试,回归证据是真实复跑。
- Isaac 没有真正重启;"场景未加载"用 sim_control 载入空场景模拟。
