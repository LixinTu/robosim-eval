"""Per-run files (plan doc A6): manifest.json, config.resolved.yaml, events.jsonl and the goal transcript.

The transcript uses the send_goal.sh format (first line "send_goal start ... x= y= yaw=", then wall-timestamped
"Goal accepted with ID: ...", "error_code: ...", "Goal finished with status: ...") so that the D0 analyzer
(scripts/wsl/analyze_attempt.py) verifies the goal and filters the goal id exactly as it does for CLI runs.
"""
from __future__ import annotations

import dataclasses
import datetime
import enum
import hashlib
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

import yaml

REPO = Path(__file__).resolve().parents[1]
VENDOR_PKG = Path.home() / "robotics/vendor/isaac-ros-6.1/jazzy_ws/src/navigation/carter_navigation"
ISAAC_VERSION = Path("/mnt/d/isaac-sim-standalone-6.1.0-windows-x86_64/VERSION")


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def to_plain(obj: Any) -> Any:
    """Dataclasses, enums, tuples and mappings -> plain JSON/YAML types."""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_plain(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, dict) or hasattr(obj, "items"):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_plain(v) for v in obj]
    return obj


def sha256_file(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 16), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return None


def _cmd(args) -> Optional[str]:
    try:
        return subprocess.run(args, capture_output=True, text=True, timeout=20, check=True).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def write_manifest(run_dir: Path, run_id: str, scenario: str, config_path: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    """Versions, commit, dirty flag and digests needed to reproduce the run (a seed alone is not enough, A6)."""
    status = _cmd(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"])
    map_yaml = VENDOR_PKG / "maps" / "carter_warehouse_navigation.yaml"
    manifest = {
        "schema": "robosim-eval run manifest (plan doc A6)", "run_id": run_id, "scenario": scenario,
        "created": now_iso(), "host": _cmd(["hostname"]),
        "git": {"commit": _cmd(["git", "-C", str(REPO), "rev-parse", "HEAD"]),
                "branch": _cmd(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"]),
                "dirty_tracked_files": None if status is None else bool(status)},
        "versions": {"ros_distro": os.environ.get("ROS_DISTRO"), "rmw": os.environ.get("RMW_IMPLEMENTATION"),
                     "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
                     "navigation2": _cmd(["dpkg-query", "-W", "-f=${Version}", "ros-jazzy-navigation2"]),
                     "isaac_sim": ISAAC_VERSION.read_text(encoding="utf-8").strip() if ISAAC_VERSION.exists() else None},
        "digests": {"config": sha256_file(Path(config_path)), "map_yaml": sha256_file(map_yaml),
                    "map_image": sha256_file(map_yaml.with_suffix(".png")),
                    "nav2_params": sha256_file(VENDOR_PKG / "params" / "carter_navigation_params.yaml")},
        "config_path": str(config_path), "seed": None,
        "note": "no random seed is used; the scene is reset through sim_control before the run (see events.jsonl)",
    }
    manifest.update(extra)
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def write_resolved_config(run_dir: Path, cfg: Any, scenario: Any, options: Dict[str, Any]) -> None:
    data = {"scenario": to_plain(scenario), "run": to_plain(cfg.run), "sim": to_plain(cfg.sim),
            "topics": to_plain(cfg.topics), "doctor": to_plain(cfg.doctor), "env": to_plain(cfg.env),
            "runner_options": options}
    (run_dir / "config.resolved.yaml").write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


class EventLog:
    """events.jsonl: one JSON object per line with host monotonic time, wall time and the latest simulation time."""

    def __init__(self, path: Path, sim_time: Callable[[], Optional[float]]) -> None:
        self.path, self.sim_time = path, sim_time
        self._f = open(path, "a", encoding="utf-8")

    def write(self, event: str, **fields: Any) -> None:
        row = {"t_mono": round(time.monotonic(), 6), "wall": now_iso(), "t_sim": self.sim_time(), "event": event}
        row.update(to_plain(fields))
        self._f.write(json.dumps(row) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


class Transcript:
    """goal-<time>.txt in the send_goal.sh format, read by analyze_attempt.parse_goal_transcript."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / f"goal-{time.strftime('%H%M%S')}.txt"
        self._f = open(self.path, "w", encoding="utf-8")

    def start(self, x: float, y: float, yaw: float, action: str) -> None:
        self._f.write(f"send_goal start {now_iso()} action={action} frame=map x={x} y={y} yaw={yaw} "
                      f"(robosim_eval.runner, rclpy action client)\n")
        self._f.flush()

    def line(self, text: str) -> None:
        self._f.write(f"{now_iso()} {text}\n")
        self._f.flush()

    def end(self, client_exit: int) -> None:
        self._f.write(f"send_goal end {now_iso()} action_client_exit={client_exit}\n")
        self._f.close()
