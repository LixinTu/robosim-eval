# verify.sh 记录 20261003-075258

- 模式:完整(固定输入测试 + doctor 假节点测试 + 运行器假节点测试,假节点在 ROS domain 42)
- 检出:/mnt/d/RoboSim-Eval;分支 chore/harness-cleanup;HEAD cb7c6a4;已跟踪文件有未提交改动:是
- 环境:WSL Ubuntu;Python 3.12.3;本机是 Isaac Sim 6.1 官方不支持的配置(unsupported configuration:Windows 10 + 8 GB 显存),这些检查不需要仿真

| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 07:53:06–07:53:07(1s) | `python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | pytest.log | PASS 221 passed in 0.86s |
| 07:53:07–07:53:52(45s) | `bash /mnt/d/RoboSim-Eval/scripts/wsl/test_doctor_fake.sh /mnt/d/RoboSim-Eval/artifacts/verify/20261003-075258/doctor-fake` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | doctor-fake.log、doctor-fake/ | PASS === result: PASS === |
| 07:53:52–07:56:40(168s) | `bash /mnt/d/RoboSim-Eval/scripts/wsl/test_runner_fake.sh /mnt/d/RoboSim-Eval/artifacts/verify/20261003-075258/runner-fake` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 0 | runner-fake.log、runner-fake/ | PASS === result: PASS === |

结论:通过(3/3 项)
