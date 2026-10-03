# practice-01:2026-09-30 13:47 的一次真实 normal 运行

这个目录是 2026-10-03 整理仓库时发现的未跟踪文件,当时没有写命令记录。下表全部取自运行目录里的 `manifest.json`、`events.jsonl`、`result.json`;执行的命令、由谁执行、已跟踪文件里改了什么,都无从核实。本机是 Isaac Sim 6.1 官方不支持的配置(unsupported configuration:Windows 10 + 8 GB 显存)。

| 项 | 内容 | 出处 |
| --- | --- | --- |
| 情形 | normal | manifest.json `scenario` |
| 时间 | 2026-09-30 13:47:32–13:50:35(墙钟) | events.jsonl 第一条与最后一条 |
| 代码 | cb7c6a4(`feature/d5-demo`,修复前的 D5 版本),已跟踪文件有未提交改动,改了什么没有记录 | manifest.json `git` |
| 环境 | WIN-THIV01L0JAE;Isaac Sim 6.1.0-rc.26;ROS 2 Jazzy,Nav2 1.3.13;rmw_fastrtps_cpp,ROS_DOMAIN_ID 0 | manifest.json `host`、`versions` |
| 选项 | 仿真、Nav2、录制、离线分析、接触检测全部开启 | manifest.json `options` |
| 结论 | completed / reached / safety pass / data complete → validation pass;停车确认时真值距目标 0.350 m(容差 0.5 m) | result.json |
| 命令(推断) | `wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/run_scenario.sh normal --out /mnt/d/RoboSim-Eval/artifacts/practice-01/runs`:按目录结构推断,没有记录,退出码也没有记录(validation pass 对应 0) | — |

用途:修复前代码的一次通过记录。它不能作为合并 `fix/review-round1` 之后代码(5241837 起)的证据,合并后的真实运行见 `artifacts/review-2026-10-03/`。rosbag 按 `.gitignore` 不入库。
