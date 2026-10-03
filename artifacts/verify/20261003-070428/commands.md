# verify.sh 记录 20261003-070428

- 模式:--fast(只跑固定输入测试)
- 检出:/mnt/d/RoboSim-Eval;分支 chore/harness-cleanup;HEAD cb7c6a4;已跟踪文件有未提交改动:是
- 环境:WSL Ubuntu;Python 3.12.3;本机是 Isaac Sim 6.1 官方不支持的配置(unsupported configuration:Windows 10 + 8 GB 显存),这些检查不需要仿真

| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 07:04:34–07:04:35(1s) | `python3 -m pytest -q -p no:cacheprovider /mnt/d/RoboSim-Eval/tests` | bash(WSL Ubuntu,verify.sh 调用) | /mnt/d/RoboSim-Eval | 1 | pytest.log | FAIL 1 failed, 220 passed in 0.66s |

结论:未通过(1/1 项失败:pytest)
