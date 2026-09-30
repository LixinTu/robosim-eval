# artifacts/ — 运行证据(产品证据)

这里只放本机真实运行留下的证据;它证明"机器人/仿真/ROS 做了什么",不证明开发流程是否合规(过程证据在 docs/review/)。

## 目录约定

- `d0a/`、`d0b/`、`d0c/`、`d0d/`:按 D0 子项分目录,在该子项第一条命令执行时才创建,不预建空目录。
- 每个目录一个 `commands.md`,加上被引用的日志与样本文件。
- D0d 每次导航尝试一个时间戳子目录,失败的尝试也保留。
- rosbag 原始数据体积大,不入 Git(见 .gitignore);目录里记录 bag 的实际路径与 `ros2 bag info` 输出。

## commands.md 的记录格式

普通命令一行一条:

| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |

shell 取值:`PowerShell` / `wsl.exe bash -lc(非交互)` / `wsl.exe bash -ic` / `用户的 Ubuntu 终端` / `后台作业(setsid nohup)`。

常驻进程(Isaac、Nav2 launch、bag record、talker/listener)按进程记录:

| 启动时间 | 命令 | PID | 观察时段与检查内容 | 停止方式与操作者 | 退出码 | 退出原因 |
| --- | --- | --- | --- | --- | --- | --- |

退出原因取值:`normal` / `timeout(124,观察满时长)` / `kill -INT(自己停止)` / `crash` / `用户关闭`。

规则:退出码来自命令本身(重定向到文件,或 `set -o pipefail` 后再 tee),不来自 tee;`timeout` 的 124 不记为失败;没跑的检查写"未执行"及原因,不留空。
