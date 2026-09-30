# D0a 命令记录(只读探测)

| 时间(本地) | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| 2026-09-29 18:1x | `Get-Command codex; wsl --list --verbose; wsl --version; Test-Path <isaac 路径>; Get-Process kit/omni` | PowerShell(Claude 工具) | D:\RoboSim-Eval | 0 | 会话记录 | 计划阶段的预查,结果与下方脚本一致 |
| 2026-09-29 19:02:17 | `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\windows\probe_env.ps1 *> artifacts\d0a\windows-probe.txt` | PowerShell(Claude 工具) | D:\RoboSim-Eval | 0(耗时 4 s,382 行) | windows-probe.txt | 其中 "codex exec help" 段的 EXIT -1 来自 `Select-Object -First 80` 提前关闭管道,非命令失败 |
| 2026-09-29 19:0x | `cmd /c "codex login status 2>&1"` | PowerShell(Claude 工具) | D:\RoboSim-Eval | 0 | 输出 "Logged in using ChatGPT" | 脚本内同命令输出为空,单独确认 |
| 2026-09-29 19:03:30 | `wsl.exe -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/probe_env.sh` | Git Bash → wsl.exe(MSYS_NO_PATHCONV=1, WSL_UTF8=1) | /mnt/d/RoboSim-Eval | 0(耗时 1 s,217 行) | wsl-probe-login.txt | 登录 shell(login_shell=yes, interactive=no) |
| 2026-09-29 19:03:31 | `wsl.exe -d Ubuntu -- bash --noprofile --norc /mnt/d/RoboSim-Eval/scripts/wsl/probe_env.sh` | Git Bash → wsl.exe | /mnt/d/RoboSim-Eval | 0(耗时 1 s,217 行) | wsl-probe-clean.txt | 干净 shell;与登录 shell 仅内存数字不同 |
| 2026-09-29 19:03 | `cat D:\isaac-sim-standalone-6.1.0-windows-x86_64\setup_ros_env.bat`;`cat VERSION`;`grep -i -E 'ros2|rmw|fastrtps|zenoh' <kit 日志>`;`grep -E '\[Error\]|\[Fatal\]' <kit 日志>` | Git Bash | D:\RoboSim-Eval | 0 | 会话记录;结论写入 docs/environment.md | 只读 |

脚本内各段的单条退出码见对应 `*-probe*.txt` 中的 `EXIT:` 行。`sudo -n true` 的退出码 1("a password is required")是本次探测最重要的结果之一。
