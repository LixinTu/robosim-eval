"""Start/goal area check on the pinned Nav2 map (plan doc A5: "任务开始时必须验证起点和目标位于允许区域"; an unreachable
verdict needs evidence, not just Nav2's abort).

Pure functions (no ROS) on the map_server YAML + image that Nav2 loads (carter_warehouse_navigation.yaml in the
carter_navigation install share). Reading follows nav2_map_server's map_io for mode trinary: the pixel shade is the mean
of R, G, B (and the alpha channel as brightness when the image has one), occ = 1 - shade (shade with negate), cells
above occupied_thresh are occupied, below free_thresh free, the rest unknown; image row 0 is the top of the map; the
origin is the lower-left corner. Rotated origins and the scale/raw modes are refused rather than misread.

Robot radius: the largest disk around base_link inside the footprint of the pinned Nav2 params (global_costmap
footprint [[0.14, 0.25], [0.14, -0.25], [-0.607, -0.25], [-0.607, 0.25]] -> 0.14 m; footprint_padding and inflation are
planner safety margins, not the robot). Every placement of the robot contains that disk, so "the disk does not fit" is a
sound reason to refuse a pose and "the disk has no path" is sound evidence that the robot has none. Cells are blocked when
their centre is closer than radius - half a cell diagonal to an occupied cell, so the grid never blocks a position the
disk could take; the path search is 8-connected and treats unknown space as passable (the planner runs with
allow_unknown: true), which keeps a "no path" answer on the conservative side.

check_scenario: the start must be inside the map, on a free cell and clear by the radius; the goal must be inside the
map and on a free cell, and, unless the scenario is preset unreachable, clear by the radius and reachable (a reachable
cell within tolerance). For a preset-unreachable scenario the result carries unreachable_evidence = no reachable cell
within tolerance (+ half a cell diagonal) of the goal.
"""
from __future__ import annotations

import collections
import dataclasses
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import yaml

__all__ = ["FREE", "UNKNOWN", "OCCUPIED", "OccupancyMap", "MapCheck", "classify", "load_map", "cell_of", "clearance",
           "inscribed_radius", "robot_radius", "blocked_grid", "check_scenario"]

FREE, UNKNOWN, OCCUPIED = 0, 1, 2
CLASS_NAMES = {FREE: "free", UNKNOWN: "unknown", OCCUPIED: "occupied"}
_NEIGHBOURS = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))


@dataclass(frozen=True)
class OccupancyMap:
    width: int
    height: int
    resolution: float
    origin: Tuple[float, float]
    cells: bytes          # row-major, row 0 = lowest y of the map frame; FREE / UNKNOWN / OCCUPIED
    source: str

    def cell_class(self, i: int, j: int) -> int:
        return self.cells[j * self.width + i]


@dataclass(frozen=True)
class MapCheck:
    ok: bool
    problems: Tuple[str, ...]
    start: Dict[str, Any]
    goal: Dict[str, Any]
    radius_m: float
    tolerance_m: float
    path_to_goal: Optional[bool]              # None when the start is not usable
    nearest_reachable_m: Optional[float]      # distance from the goal to the nearest cell reachable from the start
    unreachable_evidence: Optional[bool]      # no reachable cell within tolerance of the goal (None = not established)
    map_source: str

    def to_dict(self) -> Dict[str, Any]:
        return dataclasses.asdict(self)


def classify(values: Sequence[int], negate: bool, occupied_thresh: float, free_thresh: float) -> int:
    """map_server trinary classification of one pixel (R, G, B[, A]); A is averaged in as brightness."""
    shade = sum(values) / len(values) / 255.0
    occ = shade if negate else 1.0 - shade
    if occ > occupied_thresh:
        return OCCUPIED
    return FREE if occ < free_thresh else UNKNOWN


def load_map(yaml_path: Union[str, Path]) -> OccupancyMap:
    """Read a map_server YAML and its image. Raises OSError (missing file) or ValueError (unsupported or invalid)."""
    from PIL import Image
    yaml_path = Path(yaml_path)
    meta = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    try:
        image, res = str(meta["image"]), float(meta["resolution"])
        ox, oy, oyaw = (float(v) for v in meta["origin"])
        negate = bool(int(meta.get("negate", 0)))
        occ_t, free_t = float(meta.get("occupied_thresh", 0.65)), float(meta.get("free_thresh", 0.25))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{yaml_path}: incomplete or invalid map YAML ({exc})") from exc
    mode = str(meta.get("mode", "trinary"))
    if mode != "trinary":
        raise ValueError(f"{yaml_path}: map mode {mode!r} is not supported by the map check (trinary only)")
    if abs(oyaw) > 1e-9:
        raise ValueError(f"{yaml_path}: a rotated map origin ({oyaw} rad) is not supported by the map check")
    if not all(math.isfinite(v) for v in (res, ox, oy)) or res <= 0:
        raise ValueError(f"{yaml_path}: resolution/origin must be finite and the resolution > 0")
    img_path = Path(image) if Path(image).is_absolute() else yaml_path.parent / image
    with Image.open(img_path) as im:
        has_alpha = "A" in im.getbands() or (im.mode == "P" and "transparency" in im.info)
        rgb = im.convert("RGBA" if has_alpha else "RGB")
        w, h = rgb.size
        pixels = list(rgb.getdata())
    cache: Dict[Tuple[int, ...], int] = {}
    cells = bytearray(w * h)
    for r in range(h):
        row = pixels[r * w:(r + 1) * w]
        base = (h - 1 - r) * w
        for i, px in enumerate(row):
            c = cache.get(px)
            if c is None:
                c = cache[px] = classify(px, negate, occ_t, free_t)
            cells[base + i] = c
    return OccupancyMap(w, h, res, (ox, oy), bytes(cells), str(yaml_path))


def cell_of(m: OccupancyMap, x: float, y: float) -> Optional[Tuple[int, int]]:
    """(column, row) of the cell containing (x, y), or None outside the map or for a non-finite point."""
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    i, j = math.floor((x - m.origin[0]) / m.resolution), math.floor((y - m.origin[1]) / m.resolution)
    return (i, j) if 0 <= i < m.width and 0 <= j < m.height else None


def _square_distance(m: OccupancyMap, x: float, y: float, i: int, j: int) -> float:
    x0, y0 = m.origin[0] + i * m.resolution, m.origin[1] + j * m.resolution
    dx = max(x0 - x, 0.0, x - (x0 + m.resolution))
    dy = max(y0 - y, 0.0, y - (y0 + m.resolution))
    return math.hypot(dx, dy)


def clearance(m: OccupancyMap, x: float, y: float, limit: float) -> float:
    """Distance from (x, y) to the nearest occupied cell (its square), capped at `limit`."""
    c = cell_of(m, x, y)
    if c is None:
        return 0.0
    k = int(math.ceil(limit / m.resolution)) + 1
    best = limit
    for j in range(max(c[1] - k, 0), min(c[1] + k + 1, m.height)):
        for i in range(max(c[0] - k, 0), min(c[0] + k + 1, m.width)):
            if m.cells[j * m.width + i] == OCCUPIED:
                best = min(best, _square_distance(m, x, y, i, j))
    return best


def inscribed_radius(footprint: Sequence[Sequence[float]]) -> float:
    """Distance from base_link (the origin) to the nearest footprint edge; base_link must lie inside the polygon."""
    pts = [(float(p[0]), float(p[1])) for p in footprint]
    if len(pts) < 3:
        raise ValueError(f"footprint needs at least 3 points, got {pts}")
    inside = False
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        if (y1 > 0) != (y2 > 0) and 0 < x1 + (0 - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    if not inside:
        raise ValueError(f"base_link (0, 0) is not inside the footprint {pts}")
    dist = []
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        vx, vy = x2 - x1, y2 - y1
        t = max(0.0, min(1.0, -(x1 * vx + y1 * vy) / (vx * vx + vy * vy))) if (vx or vy) else 0.0
        dist.append(math.hypot(x1 + t * vx, y1 + t * vy))
    return min(dist)


def robot_radius(params_path: Union[str, Path]) -> Tuple[float, str]:
    """(radius, how it was derived) from the global costmap of a Nav2 params file: the inscribed radius of the
    footprint about base_link, or robot_radius for a circular robot. Raises OSError or ValueError."""
    params = yaml.safe_load(Path(params_path).read_text(encoding="utf-8")) or {}
    gc = (((params.get("global_costmap") or {}).get("global_costmap") or {}).get("ros__parameters") or {})
    fp = gc.get("footprint")
    if isinstance(fp, str):
        fp = yaml.safe_load(fp)
    if fp:
        return inscribed_radius(fp), f"inscribed radius about base_link of global_costmap footprint {fp} ({params_path})"
    if "robot_radius" in gc:
        r = float(gc["robot_radius"])
        if math.isfinite(r) and r > 0:
            return r, f"global_costmap robot_radius ({params_path})"
    raise ValueError(f"{params_path}: global_costmap has neither a footprint nor a positive robot_radius")


def blocked_grid(m: OccupancyMap, radius: float) -> bytearray:
    """1 for occupied cells and for cells whose centre is closer than `radius` to an occupied cell's square."""
    w, h, res = m.width, m.height, m.resolution
    k = int(math.ceil(radius / res)) + 1
    offsets = [(di, dj) for di in range(-k, k + 1) for dj in range(-k, k + 1)
               if math.hypot(max(abs(di) * res - res / 2, 0.0), max(abs(dj) * res - res / 2, 0.0)) < radius]
    cells = m.cells
    blocked = bytearray(w * h)
    for j in range(h):
        for i in range(w):
            if cells[j * w + i] != OCCUPIED:
                continue
            blocked[j * w + i] = 1
            border = any(not (0 <= i + di < w and 0 <= j + dj < h) or cells[(j + dj) * w + i + di] != OCCUPIED
                         for di, dj in _NEIGHBOURS)
            if not border:  # an interior obstacle cell adds nothing beyond its border cells
                continue
            for di, dj in offsets:
                ii, jj = i + di, j + dj
                if 0 <= ii < w and 0 <= jj < h:
                    blocked[jj * w + ii] = 1
    return blocked


def _reachable(m: OccupancyMap, blocked: bytearray, start: Tuple[int, int]) -> List[int]:
    w, h = m.width, m.height
    first = start[1] * w + start[0]
    if blocked[first]:
        return []
    seen = bytearray(w * h)
    seen[first] = 1
    queue, out = collections.deque([first]), []
    while queue:
        idx = queue.popleft()
        out.append(idx)
        i, j = idx % w, idx // w
        for di, dj in _NEIGHBOURS:
            ii, jj = i + di, j + dj
            if 0 <= ii < w and 0 <= jj < h:
                n = jj * w + ii
                if not seen[n] and not blocked[n]:
                    seen[n] = 1
                    queue.append(n)
    return out


def _pose(m: OccupancyMap, name: str, x: float, y: float, radius: float, need_clear: bool) -> Tuple[Dict[str, Any], List[str]]:
    info: Dict[str, Any] = {"x": x, "y": y, "cell": None, "class": None, "clearance_m": None, "clearance_ok": None}
    if not (math.isfinite(x) and math.isfinite(y)):
        return info, [f"{name} ({x}, {y}) is not finite"]
    c = cell_of(m, x, y)
    if c is None:
        return info, [f"{name} ({x:.3f}, {y:.3f}) is outside the map"]
    cls = m.cell_class(*c)
    cl = clearance(m, x, y, 2 * radius + m.resolution)
    info.update(cell=list(c), **{"class": CLASS_NAMES[cls]}, clearance_m=round(cl, 4), clearance_ok=cl >= radius)
    problems = []
    if cls != FREE:
        problems.append(f"{name} ({x:.3f}, {y:.3f}) is on {'an occupied map cell' if cls == OCCUPIED else 'unknown map space'}")
    elif need_clear and cl < radius:
        problems.append(f"{name} ({x:.3f}, {y:.3f}) has {cl:.3f} m clearance to the nearest occupied cell, less than "
                        f"the robot radius {radius} m")
    return info, problems


def check_scenario(m: OccupancyMap, radius_m: float, start: Tuple[float, float], goal: Tuple[float, float],
                   tolerance_m: float, preset_unreachable: bool) -> MapCheck:
    """Allowed-area and reachability check of one scenario (see the module docstring)."""
    s_info, problems = _pose(m, "start", float(start[0]), float(start[1]), radius_m, need_clear=True)
    g_info, g_problems = _pose(m, "goal", float(goal[0]), float(goal[1]), radius_m, need_clear=not preset_unreachable)
    problems += g_problems
    path = nearest = evidence = None
    if not any(p.startswith("start") for p in problems) and g_info["cell"] is not None:
        half_diag = m.resolution * math.sqrt(2) / 2
        blocked = blocked_grid(m, max(radius_m - half_diag, 0.0))
        reach = _reachable(m, blocked, cell_of(m, float(start[0]), float(start[1])))
        gx, gy, w = float(goal[0]), float(goal[1]), m.width
        ox, oy, res = m.origin[0] + m.resolution / 2, m.origin[1] + m.resolution / 2, m.resolution
        nearest = min((math.hypot(ox + (idx % w) * res - gx, oy + (idx // w) * res - gy) for idx in reach),
                      default=math.inf)
        path = nearest <= tolerance_m + half_diag
        evidence = not path
        if not path and not preset_unreachable:
            problems.append(f"goal ({gx:.3f}, {gy:.3f}) is not reachable from the start on the static map with the "
                            f"robot radius {radius_m} m: the nearest reachable point is {nearest:.2f} m away "
                            f"(tolerance {tolerance_m} m)")
        nearest = round(nearest, 4) if math.isfinite(nearest) else None
    return MapCheck(ok=not problems, problems=tuple(problems), start=s_info, goal=g_info, radius_m=radius_m,
                    tolerance_m=tolerance_m, path_to_goal=path, nearest_reachable_m=nearest,
                    unreachable_evidence=evidence, map_source=m.source)
