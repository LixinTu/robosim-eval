#!/usr/bin/env bash
# verify.sh - RoboSim Eval: the offline checks to run after a change and before a commit or a review (no Isaac Sim,
# no Nav2). Full mode: fixed-input tests (pytest), then the doctor and the runner fake-node tests (ROS domain 42);
# --fast: pytest only (what the git pre-commit hook runs).
#   wsl -d Ubuntu -- bash -l /mnt/d/RoboSim-Eval/scripts/wsl/verify.sh [--fast]
# Every check is one row "时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注" (artifacts/README.md format) in
# artifacts/verify/<YYYYmmdd-HHMMSS>/commands.md, written as soon as the check ends; its output goes to a log next to it.
# Exit: 0 every check passed; 1 at least one failed (a check stopped by its time limit counts as failed: 124, or 137
# when it was still running 10 s after the INT and was killed); 2 usage error, the record could not be created, or
# another full run holds the lock.
# A terminal Ctrl-C does not stop a run: each check runs in timeout's own process group, so the INT only reaches this
# bash, and the current and the remaining checks run to their end (tested 2026-10-03).
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"   # the checkout this script is in

usage() { sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
FAST=0
for arg in "$@"; do
  case "$arg" in
    --fast) FAST=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "verify.sh: unknown argument '$arg'" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ $FAST -eq 0 ]]; then
  # Two full runs at once would start their fake nodes on the same ROS domain 42 and disturb each other.
  exec 9> /tmp/robosim-verify.lock || exit 2
  flock -n 9 || { echo "verify.sh: another full verify.sh run holds /tmp/robosim-verify.lock" >&2; exit 2; }
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
mkdir -p "$ROOT/artifacts/verify" || exit 2
OUT="$ROOT/artifacts/verify/$STAMP"
n=2
while ! mkdir "$OUT" 2>/dev/null; do   # two runs in the same second get -2, -3, ...
  [[ $n -gt 20 ]] && { echo "verify.sh: cannot create a record directory under $ROOT/artifacts/verify" >&2; exit 2; }
  OUT="$ROOT/artifacts/verify/$STAMP-$n"; n=$((n + 1))
done
REC="$OUT/commands.md"
SHELL_DESC="bash(WSL ${WSL_DISTRO_NAME:-?},verify.sh 调用)"

git_info() {  # the same git facts the runner records in manifest.json
  local head branch status
  head=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null) || head="未知(git 失败)"
  branch=$(git -C "$ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null) || branch="未知"
  if status=$(git -C "$ROOT" status --porcelain --untracked-files=no 2>/dev/null); then
    [[ -n "$status" ]] && status="是" || status="否"
  else
    status="未知"
  fi
  printf '分支 %s;HEAD %s;已跟踪文件有未提交改动:%s' "$branch" "$head" "$status"
}

{
  echo "# verify.sh 记录 $STAMP"
  echo
  if [[ $FAST -eq 1 ]]; then
    echo "- 模式:--fast(只跑固定输入测试)"
  else
    echo "- 模式:完整(固定输入测试 + doctor 假节点测试 + 运行器假节点测试,假节点在 ROS domain 42)"
  fi
  echo "- 检出:$ROOT;$(git_info)"
  echo "- 环境:WSL ${WSL_DISTRO_NAME:-?};$(python3 --version 2>&1);本机是 Isaac Sim 6.1 官方不支持的配置(unsupported configuration:Windows 10 + 8 GB 显存),这些检查不需要仿真"
  echo
  echo "| 时间 | 命令 | shell | cwd | 退出码 | 日志/样本 | 备注 |"
  echo "| --- | --- | --- | --- | --- | --- | --- |"
} > "$REC" || { echo "verify.sh: cannot write $REC" >&2; exit 2; }

FAILED=()
TOTAL=0
uptime_s() { local u; read -r u _ < /proc/uptime; echo "${u%%.*}"; }

run_check() {  # run_check <name> <time limit s> <summary grep pattern> <extra log/sample> -- <command...>
  local name="$1" limit="$2" pattern="$3" extra="$4"; shift 5
  local log="$name.log" t0 t1 s0 s1 u0 u1 rc note verdict shown slept
  TOTAL=$((TOTAL + 1))
  shown=$(printf '%q ' "$@"); shown="${shown% }"
  t0=$(date +%H:%M:%S); s0=$(date +%s); u0=$(uptime_s)
  echo "verify.sh: [$name] $shown"
  (cd "$ROOT" && PYTHONDONTWRITEBYTECODE=1 timeout -s INT -k 10 "$limit" "$@") > "$OUT/$log" 2>&1
  rc=$?
  t1=$(date +%H:%M:%S); s1=$(date +%s); u1=$(uptime_s)
  note=$(grep -E "$pattern" "$OUT/$log" | tail -n 1)
  if [[ $rc -eq 0 ]]; then
    verdict="PASS"
  else
    verdict="FAIL"; FAILED+=("$name")
    if [[ $rc -eq 124 ]]; then
      note="超过 ${limit} s 时限,检查未完成;$note"
    elif [[ $rc -eq 137 && $((u1 - u0)) -ge $limit ]]; then
      # KILLed 10 s after the INT: the test script's EXIT trap did not run, so fake nodes it started with setsid may
      # still be publishing on domain 42 until their --duration ends.
      note="超过 ${limit} s 时限,INT 之后 10 s 仍未结束被强杀,检查未完成,它起的假节点可能还在跑;$note"
    fi
  fi
  # A sleeping Windows host pauses the WSL VM: the wall clock jumps on resume, the VM's uptime does not. The fake
  # nodes and the doctor's observation window are then cut, so a failure in such a check says nothing about the code.
  slept=$(( (s1 - s0) - (u1 - u0) ))
  [[ $slept -gt 30 ]] && note="$note;期间墙钟比 WSL 运行时间多走 ${slept} s(Windows 睡眠或 WSL 暂停),结果可能受影响,应重跑"
  printf '| %s–%s(%ss) | `%s` | %s | %s | %s | %s%s | %s %s |\n' "$t0" "$t1" "$((s1 - s0))" "$shown" "$SHELL_DESC" \
    "$ROOT" "$rc" "$log" "${extra:+、$extra}" "$verdict" "${note//|/\\|}" >> "$REC"
  echo "verify.sh: [$name] exit $rc $verdict${note:+ ($note)}"
}

run_check pytest 600 '(passed|failed|error|no tests ran)' "" -- \
  python3 -m pytest -q -p no:cacheprovider "$ROOT/tests"
if [[ $FAST -eq 0 ]]; then
  run_check doctor-fake 300 '^=== result:' "doctor-fake/" -- \
    bash "$ROOT/scripts/wsl/test_doctor_fake.sh" "$OUT/doctor-fake"
  run_check runner-fake 900 '^=== result:' "runner-fake/" -- \
    bash "$ROOT/scripts/wsl/test_runner_fake.sh" "$OUT/runner-fake"
fi

if [[ ${#FAILED[@]} -eq 0 ]]; then
  RESULT="结论:通过($TOTAL/$TOTAL 项)"
else
  RESULT="结论:未通过(${#FAILED[@]}/$TOTAL 项失败:${FAILED[*]})"
fi
printf '\n%s\n' "$RESULT" >> "$REC"
echo "verify.sh: $RESULT; record ${REC#"$ROOT"/}"
[[ ${#FAILED[@]} -eq 0 ]]
