"""Declared Nav2 parameter changes (D5): derive a params file from the vendor one by editing named leaf values only.

The vendor file (NVIDIA carter_navigation) is not copied into the repository and not reformatted: each change rewrites
the value on exactly one line, every other byte stays the same, and the result is checked by parsing both texts.

A change is addressed as <node>.ros__parameters.<parameter>. <node> is the node's YAML keys joined with '.', namespace
first ('local_costmap.local_costmap' for the costmap node /local_costmap/local_costmap). <parameter> is the ROS 2
parameter name: nested YAML keys joined with '.', so 'FollowPath.PathAlign.scale' finds the literal key
'PathAlign.scale' under 'FollowPath' as the vendor file writes it. The new value must have the vendor value's ROS type
(bool, integer, double or string): ROS 2 parameters are statically typed, and an integer override of a double parameter
makes the node fail to configure.
"""
from __future__ import annotations

import copy
import hashlib
import re
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Tuple

import yaml

__all__ = ["apply_changes", "node_and_param", "write_params"]

_KEY_LINE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z0-9_.\-/]+):(?P<sep>\s*)(?P<value>[^#]*?)(?P<tail>\s*(#.*)?)$")
_NAME_TOKEN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PARAMS = "ros__parameters"
_ROS_TYPES = ((bool, "bool"), (int, "integer"), (float, "double"), (str, "string"))  # bool first: it is an int


def node_and_param(path: str) -> Tuple[str, str]:
    """'controller_server.ros__parameters.FollowPath.max_vel_x' -> ('controller_server', 'FollowPath.max_vel_x');
    'local_costmap.local_costmap.ros__parameters.inflation_layer.inflation_radius' ->
    ('local_costmap/local_costmap', 'inflation_layer.inflation_radius'). Raises ValueError for any other shape."""
    node, sep, param = path.partition(f".{_PARAMS}.")
    tokens = node.split(".")
    if not sep or not all(_NAME_TOKEN.match(t) for t in tokens) or not param or not all(param.split(".")):
        raise ValueError(f"nav2 parameter {path!r}: expected <node>.ros__parameters.<parameter>, where <node> is ROS "
                         "name tokens joined with '.' (namespace first) and <parameter> has no empty part")
    return "/".join(tokens), param


def _ros_type(value: Any) -> str:
    for cls, name in _ROS_TYPES:
        if isinstance(value, cls):
            return name
    return type(value).__name__


def _parse(text: str, what: str) -> Any:
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{what} is not valid YAML: {' '.join(str(exc).split())}") from exc


def _spellings(mapping: Any, name: str, prefix: Tuple[str, ...]) -> Iterator[Tuple[str, ...]]:
    """Every YAML key path under `mapping` whose keys, joined with '.', give the parameter name `name`."""
    if not isinstance(mapping, dict):
        return
    for key, value in mapping.items():
        keys = prefix + (str(key),)
        joined = ".".join(keys)
        if joined == name:
            yield keys
        elif name.startswith(joined + "."):
            yield from _spellings(value, name, keys)


def _resolve(data: Any, path: str) -> Tuple[str, ...]:
    """YAML key path of the parameter `path` in the parsed params file; ValueError names what is missing."""
    node, param = node_and_param(path)
    keys = tuple(node.split("/")) + (_PARAMS,)
    where = data
    for i, key in enumerate(keys):
        if not isinstance(where, dict) or key not in where:
            missing = f"node {node!r} not found" if i < len(keys) - 1 else f"node {node!r} has no {_PARAMS}"
            raise ValueError(f"nav2 parameter {path!r}: {missing} in the params file")
        where = where[key]
    found = list(_spellings(where, param, ()))
    if not found:
        raise ValueError(f"nav2 parameter {path!r}: {param!r} not found under {'.'.join(keys)} in the params file")
    if len(found) > 1:
        raise ValueError(f"nav2 parameter {path!r} is ambiguous: the params file spells it as "
                         f"{[list(f) for f in found]} under {'.'.join(keys)}")
    return keys + found[0]


def _at(data: Any, keys: Tuple[str, ...]) -> Any:
    for key in keys:
        data = data[key]
    return data


def apply_changes(text: str, changes: Mapping[str, Any]) -> Tuple[str, List[Dict[str, Any]]]:
    """Return (new_text, [{path, old, new}]) with each parameter `path` (module docstring) set to its new scalar value.

    Raises ValueError when there is no change, the params file is not valid YAML, a path is malformed, missing,
    ambiguous or not a scalar, the ROS type would change, the leaf is not written as 'key: value' on exactly one line,
    or the parsed result differs from the original anywhere else."""
    if not changes:
        raise ValueError("no change declared")
    original = _parse(text, "the params file")
    applied: List[Dict[str, Any]] = []
    target: Dict[str, Tuple[str, ...]] = {}
    for path, value in changes.items():
        target[path] = _resolve(original, path)
        old = _at(original, target[path])
        if isinstance(old, (dict, list)) or not isinstance(value, (bool, int, float, str)):
            raise ValueError(f"nav2 parameter {path!r} is not a scalar leaf (or the new value is not a scalar)")
        if _ros_type(old) != _ros_type(value):
            hint = f"; write {float(value)!r}" if (_ros_type(old), _ros_type(value)) == ("double", "integer") else ""
            raise ValueError(f"nav2 parameter {path!r}: type mismatch, params file {old!r} ({_ros_type(old)}), change "
                             f"{value!r} ({_ros_type(value)}); ROS 2 parameters keep their declared type{hint}")
        applied.append({"path": path, "old": old, "new": value})

    lines = text.splitlines(keepends=True)
    stack: List[Tuple[int, str]] = []
    by_keys = {keys: path for path, keys in target.items()}
    hits: Dict[str, List[int]] = {path: [] for path in changes}
    for i, line in enumerate(lines):
        m = _KEY_LINE.match(line.rstrip("\r\n"))
        if not m:
            continue  # blank, comment, list item or flow continuation: not a mapping key
        indent = len(m.group("indent"))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack.append((indent, m.group("key")))
        keys = tuple(k for _, k in stack)
        if keys in by_keys and m.group("value"):
            hits[by_keys[keys]].append(i)
    for path, where in hits.items():
        if not where:
            raise ValueError(f"nav2 parameter {path!r} is not written as 'key: value' on a line of its own in the params "
                             "file (for example inside a flow mapping); refusing to edit it")
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
        _at(expected, target[path][:-1])[target[path][-1]] = value
    if _parse(new_text, "the edited params file") != expected:
        raise ValueError("the edited params file differs from the declared change elsewhere; refusing to use it")
    return new_text, applied


def write_params(source: Path, run_dir: Path, changes: Mapping[str, Any]) -> Dict[str, Any]:
    """Write <run_dir>/nav2_params.yaml = source with the declared changes; return what was done, for the run record.
    Every check runs before the file is written, so a refused change leaves no file behind."""
    text = Path(source).read_text(encoding="utf-8")
    new_text, applied = apply_changes(text, changes)
    for a in applied:
        a["node"], a["param"] = node_and_param(a["path"])
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "nav2_params.yaml"
    out.write_text(new_text, encoding="utf-8")
    return {"file": str(out), "sha256": hashlib.sha256(new_text.encode("utf-8")).hexdigest(), "source": str(source),
            "source_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "changes": applied}
