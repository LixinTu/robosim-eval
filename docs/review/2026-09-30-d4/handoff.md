# D4 交接说明(给独立审查者)

## 范围

- 被审版本 `02de625`(分支 `feature/d4-batch`)。D4 的代码在 D3 分支上就已写好,但被排除在 D3 审查之外,所以本轮按**整份文件**审:`robosim_eval/batch.py`、`robosim_eval/report.py`、`scripts/wsl/run_batch.sh`、`tests/test_report.py`。D4 期间的改动见 `git diff 3b58422 02de625 -- robosim_eval tests`(报告改进 `2b8f27c`)。
- 证据:`artifacts/d4/commands.md`;批量目录 `artifacts/d4/batch-20260930-013010/`(`batch.json`、`runs/report.html`、`runs/summary.json`、9 个运行目录);"开头卡住"分析 `artifacts/d4/stuck-start/`。

## 需求

计划书 `RoboSim-Eval-Plan-and-Setup-ZH(1).md`:A4 的 D4 一行("三种场景各重复 3 次 | 每次重置;9 次尝试全部留档与汇总 | 报告、失败案例、配置、版本和重置证据");A6 的报告规则(失败尝试计入;成功时间只统计到达的运行并注明;不可达不并入成功率;9 次是工程试运行,不是性能结论)。

## 实现要点

| 文件 | 作用 |
| --- | --- |
| `robosim_eval/batch.py` | 交替运行(每个情形第 1 次、再第 2 次……),每次一个独立的运行器进程;退出 31 时中止并把余下尝试记为未运行;SIGINT/SIGTERM 在当前尝试结束后停止;最后只从保存的记录生成报告 |
| `robosim_eval/report.py` | 从运行目录读 result.json、manifest.json、events.jsonl;按情形分组;失败与 inconclusive 列理由;平均用时只算 reached;列出全部 commit;复位误差取运行器记录的 reset_check;Nav2 恢复次数;地图与真值轨迹 SVG |
| `scripts/wsl/run_batch.sh` | 加载 ROS 环境,4 h 上限,调用 batch.py |

## 主张与证据

| 主张 | 证据 |
| --- | --- |
| 9 次全部运行、全部留档、全部 pass;每次复位后真值距出生点 0.07 mm | `artifacts/d4/commands.md` 结果表、各运行目录 events.jsonl 的 reset_check |
| 9 次用的代码相同(第 1 次记录的 commit 是 4332d79,之后 3b58422,中间两次提交只改文档) | commands.md 第 1 行的 `git diff --stat` 说明;report.html 页头列出两个 commit |
| 报告改进的 5 个测试先红后绿,全部 114 passed | commands.md |
| "开头卡住"的机器人不响应一环由直接实验证实 | `artifacts/d4/stuck-start/rotation-response-01.txt` |

## 已知限制

- 每个情形 3 次,是工程试运行。
- 平均用时主要反映"开头卡住";DWB 为什么选最小转向档没有查明。
- 报告的地图叠加用了硬编码的地图原点与尺寸(钉住版本的仓库地图)。
