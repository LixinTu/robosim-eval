# verify.sh 记录 20261003-120328

- 模式:完整(固定输入测试 + doctor 假节点测试 + 运行器假节点测试,假节点在 ROS domain 42)
- 检出:/mnt/d/RoboSim-Eval;分支 chore/harness-cleanup;HEAD d35d7ad;已跟踪文件有未提交改动:否
- 环境:WSL Ubuntu;Python 3.12.3;本机是 Isaac Sim 6.1 官方不支持的配置(unsupported configuration:Windows 10 + 8 GB 显存),这些检查不需要仿真

| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 12:03:30–12:04:38(68s) | `python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | pytest.log | PASS 620 passed in 67.92s (0:01:07) |
| 12:04:38–12:05:35(57s) | `bash /mnt/d/RoboSim-Eval/scripts/wsl/test_doctor_fake.sh /mnt/d/RoboSim-Eval/artifacts/verify/20261003-120328/doctor-fake` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | doctor-fake.log、doctor-fake/ | PASS === result: PASS === |
| 12:05:35–12:09:36(241s) | `bash /mnt/d/RoboSim-Eval/scripts/wsl/test_runner_fake.sh /mnt/d/RoboSim-Eval/artifacts/verify/20261003-120328/runner-fake` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | runner-fake.log、runner-fake/ | PASS === result: PASS === |

结论:通过(3/3 项)
