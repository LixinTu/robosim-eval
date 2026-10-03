"""Fixed-input tests for robosim_eval.map_check (plan doc A5: start and goal in the allowed area at task start; an
'unreachable' verdict needs evidence). Maps are small synthetic PNG + YAML pairs written to tmp_path; one test uses the
pinned vendor map when it is installed (skipped otherwise)."""
from __future__ import annotations

import math
from pathlib import Path

import pytest
from PIL import Image

from robosim_eval import map_check as mc

VENDOR_SHARE = Path.home() / "robotics/vendor/isaac-ros-6.1/jazzy_ws/install/carter_navigation/share/carter_navigation"
CARTER_FOOTPRINT = [(0.14, 0.25), (0.14, -0.25), (-0.607, -0.25), (-0.607, 0.25)]
SHADE = {"#": 0, ".": 254, "?": 205}   # occupied, free, unknown (map_server trinary defaults)


def write_map(tmp_path: Path, rows, resolution=0.1, origin=(0.0, 0.0, 0.0), negate=0, extra="", name="m",
              image_dir=None) -> Path:
    """rows[0] is the TOP image row (highest y), as in a map_server image."""
    h, w = len(rows), len(rows[0])
    img = Image.new("L", (w, h))
    img.putdata([SHADE[c] if not negate else 255 - SHADE[c] for row in rows for c in row])
    img_dir = tmp_path / (image_dir or "")
    img_dir.mkdir(parents=True, exist_ok=True)
    img.save(img_dir / f"{name}.png")
    image = f"{image_dir}/{name}.png" if image_dir else f"{name}.png"
    y = tmp_path / f"{name}.yaml"
    y.write_text(f"image: {image}\nresolution: {resolution}\norigin: [{origin[0]}, {origin[1]}, {origin[2]}]\n"
                 f"negate: {negate}\noccupied_thresh: 0.65\nfree_thresh: 0.196\n{extra}", encoding="utf-8")
    return y


def room(w=40, h=20):
    return ["#" * w] + ["#" + "." * (w - 2) + "#" for _ in range(h - 2)] + ["#" * w]


def test_load_map_classifies_cells_and_flips_rows(tmp_path):
    m = mc.load_map(write_map(tmp_path, ["#.?", "..."], resolution=0.5, origin=(-1.0, 2.0, 0.0), image_dir="img"))
    assert (m.width, m.height, m.resolution, m.origin) == (3, 2, 0.5, (-1.0, 2.0))
    # the top image row is the highest map row
    assert m.cell_class(0, 1) == mc.OCCUPIED and m.cell_class(1, 1) == mc.FREE and m.cell_class(2, 1) == mc.UNKNOWN
    assert all(m.cell_class(i, 0) == mc.FREE for i in range(3))
    assert mc.cell_of(m, -1.0 + 0.25, 2.0 + 0.75) == (0, 1)
    assert mc.cell_of(m, -1.01, 2.1) is None and mc.cell_of(m, 0.6, 3.0) is None
    assert mc.cell_of(m, float("nan"), 2.1) is None


def test_negate_inverts_the_shades(tmp_path):
    m = mc.load_map(write_map(tmp_path, ["#.?"], negate=1))
    assert [m.cell_class(i, 0) for i in range(3)] == [mc.OCCUPIED, mc.FREE, mc.UNKNOWN]


def test_alpha_is_averaged_in_trinary_mode_as_map_server_does():
    # map_server averages (255 - opacity) with R, G, B in trinary mode: an opaque grey 127 is unknown, a black pixel
    # occupied, a fully transparent white pixel still free (shade (3*255 + 0) / 4 / 255 = 0.75, occ 0.25 -> unknown)
    assert mc.classify((0, 0, 0, 255), False, 0.65, 0.196) == mc.OCCUPIED
    assert mc.classify((127, 127, 127, 255), False, 0.65, 0.196) == mc.UNKNOWN
    assert mc.classify((255, 255, 255, 255), False, 0.65, 0.196) == mc.FREE
    assert mc.classify((255, 255, 255, 0), False, 0.65, 0.196) == mc.UNKNOWN


def test_unsupported_map_features_are_refused(tmp_path):
    with pytest.raises(ValueError, match="mode"):
        mc.load_map(write_map(tmp_path, ["..."], extra="mode: raw\n"))
    with pytest.raises(ValueError, match="origin"):
        mc.load_map(write_map(tmp_path, ["..."], origin=(0.0, 0.0, 0.3), name="rot"))
    with pytest.raises(OSError):
        mc.load_map(tmp_path / "missing.yaml")


def test_inscribed_radius_of_the_carter_footprint():
    # base_link sits 0.14 m behind the front edge of the 0.747 x 0.5 m footprint
    assert mc.inscribed_radius(CARTER_FOOTPRINT) == pytest.approx(0.14)
    with pytest.raises(ValueError):
        mc.inscribed_radius([(1.0, 1.0), (2.0, 1.0), (2.0, 2.0)])   # base_link outside the footprint


def test_robot_radius_from_nav2_params(tmp_path):
    p = tmp_path / "params.yaml"
    p.write_text('global_costmap:\n  global_costmap:\n    ros__parameters:\n      footprint_padding: 0.25\n'
                 '      footprint: "[ [0.14, 0.25], [0.14, -0.25], [-0.607, -0.25], [-0.607, 0.25] ]"\n',
                 encoding="utf-8")
    r, how = mc.robot_radius(p)
    assert r == pytest.approx(0.14) and "footprint" in how
    p.write_text("global_costmap:\n  global_costmap:\n    ros__parameters:\n      robot_radius: 0.3\n", encoding="utf-8")
    assert mc.robot_radius(p)[0] == pytest.approx(0.3)
    p.write_text("global_costmap: {}\n", encoding="utf-8")
    with pytest.raises(ValueError):
        mc.robot_radius(p)


def test_free_goal_in_an_open_room_is_allowed_and_reachable(tmp_path):
    m = mc.load_map(write_map(tmp_path, room()))
    res = mc.check_scenario(m, 0.14, (0.5, 0.5), (3.5, 1.5), 0.5, preset_unreachable=False)
    assert res.ok and not res.problems
    assert res.path_to_goal is True and res.unreachable_evidence is False and res.nearest_reachable_m < 0.1


@pytest.mark.parametrize("goal,words", [((3.95, 1.0), "occupied"), ((10.0, 1.0), "outside the map"),
                                        ((float("nan"), 1.0), "not finite"), ((0.12, 1.0), "clearance")])
def test_goal_outside_the_allowed_area_fails(tmp_path, goal, words):
    m = mc.load_map(write_map(tmp_path, room()))
    res = mc.check_scenario(m, 0.14, (0.5, 0.5), goal, 0.5, preset_unreachable=False)
    assert not res.ok and any(p.startswith("goal") and words in p for p in res.problems), res.problems


def test_goal_on_unknown_space_fails(tmp_path):
    rows = room()
    rows[5] = rows[5][:30] + "???" + rows[5][33:]
    m = mc.load_map(write_map(tmp_path, rows))
    res = mc.check_scenario(m, 0.14, (0.5, 0.5), (3.15, 1.45), 0.5, preset_unreachable=False)
    assert not res.ok and any("unknown" in p for p in res.problems)


def test_start_outside_the_allowed_area_fails_and_gives_no_evidence(tmp_path):
    m = mc.load_map(write_map(tmp_path, room()))
    res = mc.check_scenario(m, 0.14, (0.05, 0.5), (3.5, 1.5), 0.5, preset_unreachable=True)
    assert not res.ok and any(p.startswith("start") for p in res.problems)
    assert res.path_to_goal is None and res.unreachable_evidence is None


def slot_map():
    # a room split by a wall at x = 2.0 m; the goal pocket on the right is entered only through a 0.2 m slot
    rows = room()
    for r in range(len(rows)):
        if 0 < r < len(rows) - 1 and r != 10 and r != 11:
            rows[r] = rows[r][:20] + "#" + rows[r][21:]
    return rows


def test_a_slot_narrower_than_the_robot_gives_no_path(tmp_path):
    m = mc.load_map(write_map(tmp_path, slot_map()))
    reach = mc.check_scenario(m, 0.14, (0.5, 1.0), (3.0, 1.0), 0.5, preset_unreachable=False)
    assert not reach.ok and reach.path_to_goal is False
    assert any("not reachable" in p for p in reach.problems)
    preset = mc.check_scenario(m, 0.14, (0.5, 1.0), (3.0, 1.0), 0.5, preset_unreachable=True)
    assert preset.ok and preset.unreachable_evidence is True and preset.nearest_reachable_m > 0.5


def test_a_slot_wide_enough_for_the_robot_gives_a_path(tmp_path):
    m = mc.load_map(write_map(tmp_path, slot_map()))
    res = mc.check_scenario(m, 0.05, (0.5, 1.0), (3.0, 1.0), 0.5, preset_unreachable=True)
    assert res.path_to_goal is True and res.unreachable_evidence is False


def test_a_goal_within_tolerance_of_the_reachable_space_is_reachable(tmp_path):
    m = mc.load_map(write_map(tmp_path, slot_map()))
    res = mc.check_scenario(m, 0.14, (0.5, 1.0), (2.25, 1.0), 0.5, preset_unreachable=True)   # 0.4 m past the wall
    assert res.path_to_goal is True and res.unreachable_evidence is False


def test_a_goal_near_a_wall_is_allowed_for_a_preset_unreachable_scenario(tmp_path):
    m = mc.load_map(write_map(tmp_path, room()))
    res = mc.check_scenario(m, 0.14, (0.5, 0.5), (0.12, 1.0), 0.5, preset_unreachable=True)
    assert res.ok and res.goal["clearance_ok"] is False


def test_clearance_is_measured_to_the_occupied_cell_edges(tmp_path):
    m = mc.load_map(write_map(tmp_path, room()))
    assert mc.clearance(m, 0.5, 0.5, 1.0) == pytest.approx(0.4)          # walls occupy [0, 0.1] on both axes
    assert mc.clearance(m, 2.0, 1.0, 0.3) == pytest.approx(0.3)          # capped at the limit


@pytest.mark.skipif(not (VENDOR_SHARE / "maps" / "carter_warehouse_navigation.yaml").exists(),
                    reason="vendor carter_navigation install not present")
def test_the_pinned_warehouse_map():
    m = mc.load_map(VENDOR_SHARE / "maps" / "carter_warehouse_navigation.yaml")
    r, _ = mc.robot_radius(VENDOR_SHARE / "params" / "carter_navigation_params.yaml")
    assert r == pytest.approx(0.14)
    normal = mc.check_scenario(m, r, (-6.0, -1.0), (0.0, -1.0), 0.5, preset_unreachable=False)
    assert normal.ok and normal.path_to_goal is True
    unreachable = mc.check_scenario(m, r, (-6.0, -1.0), (-10.05, -1.0), 0.5, preset_unreachable=True)
    assert unreachable.ok and unreachable.path_to_goal is False and unreachable.unreachable_evidence is True
    assert unreachable.nearest_reachable_m > 1.0 and math.isfinite(unreachable.nearest_reachable_m)
