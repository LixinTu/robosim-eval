# verify.sh 记录 20261003-093557

- 模式:完整(固定输入测试 + doctor 假节点测试 + 运行器假节点测试,假节点在 ROS domain 42)
- 检出:/mnt/d/RoboSim-Eval;分支 chore/harness-cleanup;HEAD 5241837;已跟踪文件有未提交改动:否
- 环境:WSL Ubuntu;Python 3.12.3;本机是 Isaac Sim 6.1 官方不支持的配置(unsupported configuration:Windows 10 + 8 GB 显存),这些检查不需要仿真

| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 09:36:08–09:37:14(66s) | `python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | pytest.log | PASS 620 passed in 64.91s (0:01:04) |
| 09:37:14–09:38:09(55s) | `bash /mnt/d/RoboSim-Eval/scripts/wsl/test_doctor_fake.sh /mnt/d/RoboSim-Eval/artifacts/verify/20261003-093557/doctor-fake` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | doctor-fake.log、doctor-fake/ | PASS === result: PASS === |
| 09:38:09–09:41:58(229s) | `bash /mnt/d/RoboSim-Eval/scripts/wsl/test_runner_fake.sh /mnt/d/RoboSim-Eval/artifacts/verify/20261003-093557/runner-fake` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | runner-fake.log、runner-fake/ | PASS === result: PASS === |

结论:通过(3/3 项)
