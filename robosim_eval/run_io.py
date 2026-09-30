"""Per-run files (plan doc A6): manifest.json, config.resolved.yaml, events.jsonl and the goal transcript; the runner lock.

The transcript uses the send_goal.sh format (first line "send_goal start ... x= y= yaw=", then wall-timestamped
"Goal accepted with ID: ...", "error_code: ...", "Goal finished with status: ...") so that the D0 analyzer
(scripts/wsl/analyze_attempt.py) verifies the goal and filters the goal id exactly as it does for CLI runs.
"""
from __future__ import annotations

import dataclasses
import datetime
import enum
import fcntl
import hashlib
import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

import yaml

REPO = Path(__file__).resolve().parents[1]
_VENDOR_WS = Path.home() / "robotics/vendor/isaac-ros-6.1/jazzy_ws"
VENDOR_PKG = _VENDOR_WS / "src/navigation/carter_navigation"               # the vendor source tree (never edited)
NAV2_SHARE = _VENDOR_WS / "install/carter_navigation/share/carter_navigation"  # what $(find-pkg-share) resolves: loaded
ISAAC_VERSION = Path("/mnt/d/isaac-sim-standalone-6.1.0-windows-x86_64/VERSION")
LOCK_DIR = Path("/tmp/robosim_eval")


def read_exit_file(path: Path) -> Optional[int]:
    """The integer exit code a wrapper wrote to `path` (e.g. <run_dir>/nav2.exit); None when absent or unreadable."""
    try:
        return int(path.read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        return None


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


def windows_to_wsl(path: str) -> Optional[Path]:
    """D:/x/y.usda or D:\\x\\y.usda -> /mnt/d/x/y.usda; a POSIX absolute path as is; None for anything else (URLs)."""
    m = re.match(r"^([A-Za-z]):[\\/](.*)$", path)
    if m:
        return Path("/mnt") / m.group(1).lower() / m.group(2).replace("\\", "/")
    return Path(path) if path.startswith("/") else None


def map_files(map_yaml: Path) -> Dict[str, Optional[Path]]:
    """The map YAML and the image it names (resolved relative to the YAML, as map_server does)."""
    try:
        image = str((yaml.safe_load(map_yaml.read_text(encoding="utf-8")) or {}).get("image", ""))
    except (OSError, yaml.YAMLError):
        image = ""
    img = None if not image else (Path(image) if Path(image).is_absolute() else map_yaml.parent / image)
    return {"yaml": map_yaml, "image": img}


def loaded_inputs(world_uri: Optional[str], assets: Mapping[str, str], nav2_params_file: Path) -> Dict[str, Any]:
    """What the run actually loads (A6 asset/map/config digests): the world USD, the obstacle asset files, the Nav2
    params file Nav2 starts with, and whether the installed vendor files Nav2 loads still equal the source tree."""
    out: Dict[str, Any] = {
        "world": {"uri": world_uri, "sha256": None,
                  "note": "remote USD resolved by Isaac; no digest is available from WSL (the versioned URI is kept)"},
        "obstacle_assets": {}, "nav2_params_effective": {"file": str(nav2_params_file),
                                                         "sha256": sha256_file(nav2_params_file)}}
    for name, uri in sorted(assets.items()):
        local = windows_to_wsl(uri)
        out["obstacle_assets"][name] = {"uri": uri, "file": str(local) if local else None,
                                        "sha256": sha256_file(local) if local else None}
    installed, source = map_files(NAV2_SHARE / "maps" / "carter_warehouse_navigation.yaml"), \
        map_files(VENDOR_PKG / "maps" / "carter_warehouse_navigation.yaml")
    pairs = {"map_yaml": (installed["yaml"], source["yaml"]), "map_image": (installed["image"], source["image"]),
             "nav2_params": (NAV2_SHARE / "params" / "carter_navigation_params.yaml",
                             VENDOR_PKG / "params" / "carter_navigation_params.yaml")}
    out["vendor_install_equals_source"] = {k: (sha256_file(a) == sha256_file(b)) if a and b and sha256_file(a) else None
                                           for k, (a, b) in pairs.items()}
    return out


def write_manifest(run_dir: Path, run_id: str, scenario: str, config_path: str, extra: Dict[str, Any]) -> Dict[str, Any]:
    """Versions, commit, dirty flag and digests needed to reproduce the run (a seed alone is not enough, A6). The map and
    Nav2 params digests are of the installed files Nav2 loads ($(find-pkg-share carter_navigation))."""
    status = _cmd(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=no"])
    untracked = _cmd(["git", "-C", str(REPO), "status", "--porcelain", "--untracked-files=normal"])
    mapf = map_files(NAV2_SHARE / "maps" / "carter_warehouse_navigation.yaml")
    manifest = {
        "schema": "robosim-eval run manifest (plan doc A6)", "run_id": run_id, "scenario": scenario,
        "created": now_iso(), "host": _cmd(["hostname"]),
        "git": {"commit": _cmd(["git", "-C", str(REPO), "rev-parse", "HEAD"]),
                "branch": _cmd(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"]),
                "dirty_tracked_files": None if status is None else bool(status),
                "untracked_files": None if untracked is None else
                [ln[3:] for ln in untracked.splitlines() if ln.startswith("??")]},
        "versions": {"ros_distro": os.environ.get("ROS_DISTRO"), "rmw": os.environ.get("RMW_IMPLEMENTATION"),
                     "ros_domain_id": os.environ.get("ROS_DOMAIN_ID", "0"),
                     "navigation2": _cmd(["dpkg-query", "-W", "-f=${Version}", "ros-jazzy-navigation2"]),
                     "isaac_sim": ISAAC_VERSION.read_text(encoding="utf-8").strip() if ISAAC_VERSION.exists() else None},
        "digests": {"config": sha256_file(Path(config_path)), "map_yaml": sha256_file(mapf["yaml"]),
                    "map_image": sha256_file(mapf["image"]) if mapf["image"] else None,
                    "nav2_params": sha256_file(NAV2_SHARE / "params" / "carter_navigation_params.yaml")},
        "digest_files": {"map_yaml": str(mapf["yaml"]), "map_image": str(mapf["image"]),
                         "nav2_params": str(NAV2_SHARE / "params" / "carter_navigation_params.yaml")},
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


def runner_lock_path(domain_id: str) -> Path:
    """One runner at a time per ROS domain: the simulator's sim_control services live on the domain, and the fake-node
    tests use their own domains."""
    return LOCK_DIR / f"runner-domain-{domain_id}.lock"


class RunLock:
    """Exclusive host-wide lock (fcntl.flock on a fixed file); the owner's pid and run dir are written into the file.
    The kernel releases it when the process ends, so a killed runner never leaves a stale lock behind."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: Optional[int] = None

    def acquire(self, owner: Dict[str, Any]) -> Optional[str]:
        """None when the lock is now held; otherwise the current owner's record (text) and the lock is not held."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                return os.read(fd, 4096).decode("utf-8", "replace").strip() or "(no owner recorded)"
            finally:
                os.close(fd)
        os.ftruncate(fd, 0)
        os.write(fd, json.dumps(owner).encode("utf-8"))
        self._fd = fd
        return None

    def release(self) -> None:
        if self._fd is not None:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            os.close(self._fd)
            self._fd = None


class EventLog:
    """events.jsonl: one JSON object per line with host monotonic time, wall time and the latest simulation time."""

    def __init__(self, path: Path, sim_time: Callable[[], Optional[float]]) -> None:
        self.path, self.sim_time = path, sim_time
        self._f = open(path, "a", encoding="utf-8")

    def write(self, event: str, **fields: Any) -> None:
        row = {"t_mono": round(time.monotonic(), 6), "wall": now_iso(), "t_sim": self.sim_time(), "event": event}
        row.update(to_plain(fields))
        self._f.write(json.dumps(row, default=str) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


class Transcript:
    """goal-<time>.txt in the send_goal.sh format, read by analyze_attempt.parse_goal_transcript."""

    def __init__(self, run_dir: Path) -> None:
        self.path = run_dir / f"goal-{time.strftime('%H%M%S')}.txt"
        self._f = open(self.path, "w", encoding="utf-8")

    @property
    def closed(self) -> bool:
        return self._f.closed

    def start(self, x: float, y: float, yaw: float, action: str) -> None:
        self._f.write(f"send_goal start {now_iso()} action={action} frame=map x={x} y={y} yaw={yaw} "
                      f"(robosim_eval.runner, rclpy action client)\n")
        self._f.flush()

    def line(self, text: str) -> None:
        self._f.write(f"{now_iso()} {text}\n")
        self._f.flush()

    def end(self, client_exit: Optional[int]) -> None:
        """client_exit 0 when the runner received the goal's terminal result; None (written 'none') otherwise."""
        shown = "none (no terminal result received)" if client_exit is None else str(client_exit)
        self._f.write(f"send_goal end {now_iso()} action_client_exit={shown}\n")
        self._f.close()
