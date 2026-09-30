"""Declared Nav2 parameter changes (D5): derive a params file from the vendor one by editing named leaf values only.

The vendor file (NVIDIA carter_navigation) is not copied into the repository and not reformatted: each change rewrites
the value on exactly one line, every other byte stays the same, and the result is checked by parsing both texts.
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, List, Mapping, Tuple

import yaml

__all__ = ["apply_changes", "node_and_param", "write_params"]

_KEY_LINE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_.\-/]+):(?P<sep>\s*)(?P<value>[^#]*?)(?P<tail>\s*(#.*)?)$")


def _lookup(data: Any, path: str) -> Any:
    node = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise ValueError(f"nav2 parameter {path!r} not found in the params file")
        node = node[part]
    return node


def _same_kind(old: Any, new: Any) -> bool:
    if isinstance(old, bool) or isinstance(new, bool):
        return isinstance(old, bool) and isinstance(new, bool)
    if isinstance(old, (int, float)):
        return isinstance(new, (int, float))
    return type(old) is type(new)


def apply_changes(text: str, changes: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Return (new_text, [{path, old, new}]) with each dotted `path` leaf set to its new scalar value.

    Raises ValueError when there is no change, a path is missing or not a scalar, the value type would change, the
    leaf is not on exactly one line, or the parsed result differs from the original anywhere else."""
    if not changes:
        raise ValueError("no change declared")
    original = yaml.safe_load(text)
    applied: List[Dict[str, Any]] = []
    for path, value in changes.items():
        old = _lookup(original, path)
        if isinstance(old, (dict, list)) or not isinstance(value, (bool, int, float, str)):
            raise ValueError(f"nav2 parameter {path!r} is not a scalar leaf (or the new value is not a scalar)")
        if not _same_kind(old, value):
            raise ValueError(f"nav2 parameter {path!r}: type would change from {type(old).__name__} "
                             f"to {type(value).__name__}")
        applied.append({"path": path, "old": old, "new": value})

    lines = text.splitlines(keepends=True)
    stack: List[Tuple[int, str]] = []
    hits: Dict[str, List[int]] = {path: [] for path in changes}
    for i, line in enumerate(lines):
        m = _KEY_LINE.match(line.rstrip("\r\n"))
        if not m:
            continue  # blank, comment, list item or flow continuation: not a mapping key
        indent = len(m.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, m.group("key")))
        path = ".".join(k for _, k in stack)
        if path in hits and m.group("value"):
            hits[path].append(i)
    for path, where in hits.items():
        if len(where) != 1:
            raise ValueError(f"nav2 parameter {path!r} found on {len(where)} lines, need exactly 1")
        i = where[0]
        body, eol = lines[i].rstrip("\r\n"), lines[i][len(lines[i].rstrip("\r\n")):]
        m = _KEY_LINE.match(body)
        new_value = yaml.safe_dump(changes[path], default_flow_style=True).strip().removesuffix("...").strip()
        lines[i] = f"{m.group('indent')}{m.group('key')}:{m.group('sep')}{new_value}{m.group('tail')}{eol}"
    new_text = "".join(lines)

    expected = copy.deepcopy(original)
    for path, value in changes.items():
        parent, leaf = path.rsplit(".", 1)
        _lookup(expected, parent)[leaf] = value
    if yaml.safe_load(new_text) != expected:
        raise ValueError("the edited params file differs from the declared change elsewhere; refusing to use it")
    return new_text, applied


def node_and_param(path: str) -> Tuple[str, str]:
    """'controller_server.ros__parameters.FollowPath.max_vel_x' -> ('controller_server', 'FollowPath.max_vel_x')."""
    parts = path.split(".")
    if len(parts) < 3 or parts[1] != "ros__parameters":
        raise ValueError(f"nav2 parameter {path!r}: expected <node>.ros__parameters.<name>")
    return parts[0], ".".join(parts[2:])


def write_params(source: Path, run_dir: Path, changes: Mapping[str, Any]) -> Dict[str, Any]:
    """Write <run_dir>/nav2_params.yaml = source with the declared changes; return what was done, for the run record."""
    text = Path(source).read_text(encoding="utf-8")
    new_text, applied = apply_changes(text, changes)
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "nav2_params.yaml"
    out.write_text(new_text, encoding="utf-8")
    for a in applied:
        a["node"], a["param"] = node_and_param(a["path"])
    return {"file": str(out), "sha256": hashlib.sha256(new_text.encode("utf-8")).hexdigest(), "source": str(source),
            "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "changes": applied}
