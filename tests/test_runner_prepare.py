"""Runner PREPARE and entry tests without ROS (fakes in tests/test_runner_fakes.py): the start/goal map check, the
reset and obstacle checks, sim_control result codes, the one-runner lock, config exit codes, the manifest and the
topic mapping the recorder and the analysis use (plan doc A5, A6)."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

from robosim_eval import run_io
from robosim_eval import runner as runner_mod
from robosim_eval.run_io import RunLock
from robosim_eval.runner_fsm import State
from robosim_eval.sim_adapter import SimAdapter, SimControlError
from test_runner_fakes import FAKE_CFG, REPO, events, finish, make_runner, sim_config

CARTER_PARAMS = ('global_costmap:\n  global_costmap:\n    ros__parameters:\n'
                 '      footprint: "[ [0.14, 0.25], [0.14, -0.25], [-0.607, -0.25], [-0.607, 0.25] ]"\n')


def synthetic_map(tmp_path: Path, wall_x=None, goal_cell_occupied=False) -> Path:
    """12 x 4 m free area, origin (-12, -3), 0.1 m cells, border walls; optionally a closed wall at x = wall_x and an
    occupied cell under the fake scenario goal (1.0, 0.0) -> outside this map anyway."""
    w, h = 130, 40
    rows = [["." for _ in range(w)] for _ in range(h)]
    for r in range(h):
        for c in range(w):
            if r in (0, h - 1) or c in (0, w - 1) or (wall_x is not None and c == int(round((wall_x + 12.0) / 0.1))):
                rows[r][c] = "#"
    img = Image.new("L", (w, h))
    img.putdata([0 if ch == "#" else 254 for row in rows for ch in row])
    img.save(tmp_path / "map.png")
    (tmp_path / "map.yaml").write_text("image: map.png\nresolution: 0.1\norigin: [-12.0, -3.0, 0.0]\nnegate: 0\n"
                                       "occupied_thresh: 0.65\nfree_thresh: 0.196\n", encoding="utf-8")
    (tmp_path / "params.yaml").write_text(CARTER_PARAMS, encoding="utf-8")
    return tmp_path


def with_map(monkeypatch, d: Path) -> None:
    monkeypatch.setattr(runner_mod, "MAP_YAML", d / "map.yaml")
    monkeypatch.setattr(runner_mod, "NAV2_PARAMS", d / "params.yaml")


# ---- start/goal in the allowed area (doctor_config-2, docs-5) -------------------------------------------------------

def test_a_goal_outside_the_allowed_area_fails_before_the_simulator_is_touched(tmp_path, monkeypatch):
    with_map(monkeypatch, synthetic_map(tmp_path))          # the fake goal (1.0, 0.0) lies outside this map
    r, w, scripts = make_runner(tmp_path, monkeypatch, cfg_path=sim_config(tmp_path), no_sim=False)
    assert r._prepare() is False
    assert r.sim.calls == [] and scripts.names() == []
    assert any("outside the allowed area" in e and "outside the map" in e for e in r.fsm.errors)
    rc, res = finish(r)
    assert rc == 30 and res["runner"]["map_check"]["ok"] is False


def test_a_preset_unreachable_goal_gets_its_map_evidence(tmp_path, monkeypatch):
    with_map(monkeypatch, synthetic_map(tmp_path, wall_x=-9.0))   # the goal (-10.05, -1) is behind a closed wall
    r, w, scripts = make_runner(tmp_path, monkeypatch, cfg_path=sim_config(tmp_path), scenario="unreachable")
    assert r._prepare() is True and r.fsm.state is State.WAIT_READY
    mc = r.facts["map_check"]
    assert mc["ok"] and mc["path_to_goal"] is False and mc["unreachable_evidence"] is True
    assert mc["radius_m"] == pytest.approx(0.14) and "footprint" in mc["radius_source"]
    assert [e for e in events(r) if e["event"] == "map_check"][0]["unreachable_evidence"] is True


def test_an_open_path_to_a_preset_unreachable_goal_is_no_evidence(tmp_path, monkeypatch):
    with_map(monkeypatch, synthetic_map(tmp_path))
    r, w, _ = make_runner(tmp_path, monkeypatch, cfg_path=sim_config(tmp_path), scenario="unreachable")
    assert r._prepare() is True and r.facts["map_check"]["unreachable_evidence"] is False


def test_an_unreadable_map_fails_the_run(tmp_path, monkeypatch):
    monkeypatch.setattr(runner_mod, "MAP_YAML", tmp_path / "missing.yaml")
    (tmp_path / "params.yaml").write_text(CARTER_PARAMS, encoding="utf-8")
    monkeypatch.setattr(runner_mod, "NAV2_PARAMS", tmp_path / "params.yaml")
    r, w, _ = make_runner(tmp_path, monkeypatch, cfg_path=sim_config(tmp_path))
    assert r._prepare() is False and any("map check could not run" in e for e in r.fsm.errors)


def test_without_a_sim_section_the_map_check_is_skipped_and_recorded(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch)
    assert r._prepare() is True
    assert [e for e in events(r) if e["event"] == "map_check"][0]["skipped"].startswith("no sim section")


# ---- reset and obstacles (simctl-7, simctl-8) ------------------------------------------------------------------------

def reset_runner(tmp_path, monkeypatch, scenario="fake"):
    r, w, _ = make_runner(tmp_path, monkeypatch, cfg_path=sim_config(tmp_path), scenario=scenario, no_sim=False)
    return r


def test_a_robot_state_timeout_never_reloads_the_world(tmp_path, monkeypatch):
    r = reset_runner(tmp_path, monkeypatch)
    r.sim.fail["entity_state"] = SimControlError("/get_entity_state: no response within 15.0 s")
    assert r._reset_sim() is False
    assert not any(c.startswith("load_world") for c in r.sim.calls) and "reset" not in r.sim.calls
    assert any("robot state not available" in e for e in r.fsm.errors)


def test_a_robot_that_is_not_found_loads_the_world(tmp_path, monkeypatch):
    r = reset_runner(tmp_path, monkeypatch)
    calls = {"n": 0}
    orig = r.sim.entity_state

    def entity_state(entity):
        calls["n"] += 1
        if calls["n"] == 1:
            raise SimControlError("/get_entity_state: result 2 'does not exist'", code=2)
        return orig(entity)
    r.sim.entity_state = entity_state
    assert r._reset_sim() is True
    assert any(c.startswith("load_world(") for c in r.sim.calls)


def test_sim_control_errors_carry_the_result_code():
    with pytest.raises(SimControlError) as info:
        SimAdapter._require_ok("/get_entity_state", SimpleNamespace(result=4, error_message="failed"))
    assert info.value.code == 4
    assert SimControlError("/x: no response").code is None


def test_an_entity_left_after_the_reset_fails_prepare(tmp_path, monkeypatch):
    r = reset_runner(tmp_path, monkeypatch)
    r.rn.entities = ["/World/RoboSimObstacles/box_1", "/World/RoboSimObstacles/box_1/Geom"]
    assert r._reset_sim() is False and any("left entities" in e and "box_1" in e for e in r.fsm.errors)


def test_obstacles_are_read_back_and_listed(tmp_path, monkeypatch):
    r = reset_runner(tmp_path, monkeypatch, scenario="box")
    orig = r.sim.spawn_box

    def spawn_box(name, x, y, yaw, uri):
        full = orig(name, x, y, yaw, uri)
        r.rn.entities = [full, full + "/Geom"]
        return full
    r.sim.spawn_box = spawn_box
    assert r._reset_sim() is True
    checks = [e for e in events(r) if e["event"] == "obstacle_check"]
    assert len(checks) == 1 and checks[0]["ok"] is True
    assert [e for e in events(r) if e["event"] == "obstacles_listed"][0]["entities"] == ["box_1"]


def test_an_obstacle_away_from_its_scenario_pose_fails_prepare(tmp_path, monkeypatch):
    r = reset_runner(tmp_path, monkeypatch, scenario="box")
    r.sim.entities["/World/RoboSimObstacles/box_1"] = (-3.0, -1.0, 0.0)   # 0.3 m from the scenario's y = -1.3

    def spawn_box(name, x, y, yaw, uri):
        r.rn.entities = ["/World/RoboSimObstacles/box_1"]
        return "/World/RoboSimObstacles/box_1"
    r.sim.spawn_box = spawn_box
    assert r._reset_sim() is False and any("obstacle layout check failed" in e for e in r.fsm.errors)


def test_an_unexpected_entity_after_the_spawn_fails_prepare(tmp_path, monkeypatch):
    r = reset_runner(tmp_path, monkeypatch, scenario="box")
    orig = r.sim.spawn_box

    def spawn_box(name, x, y, yaw, uri):
        full = orig(name, x, y, yaw, uri)
        r.rn.entities = [full, "/World/RoboSimObstacles/low_box"]
        return full
    r.sim.spawn_box = spawn_box
    assert r._reset_sim() is False and any("expected ['box_1']" in e for e in r.fsm.errors)


# ---- one runner at a time (critic-1) and config exit codes (runner-11, critic-7) -------------------------------------

def test_the_lock_is_exclusive_and_records_its_owner(tmp_path):
    first, second = RunLock(tmp_path / "l" / "runner.lock"), RunLock(tmp_path / "l" / "runner.lock")
    assert first.acquire({"pid": 111, "run_dir": "/runs/a"}) is None
    owner = second.acquire({"pid": 222, "run_dir": "/runs/b"})
    assert owner is not None and json.loads(owner) == {"pid": 111, "run_dir": "/runs/a"}
    first.release()
    assert second.acquire({"pid": 222, "run_dir": "/runs/b"}) is None
    second.release()


def test_a_second_runner_is_refused_before_it_touches_anything(tmp_path, monkeypatch, capsys):
    lock_file = tmp_path / "runner.lock"
    monkeypatch.setattr(runner_mod, "runner_lock_path", lambda domain: lock_file)
    holder = RunLock(lock_file)
    assert holder.acquire({"pid": 4242, "run_dir": "/runs/normal-1"}) is None
    try:
        rc = runner_mod.main(["--scenario", "fake", "--config", str(FAKE_CFG), "--out", str(tmp_path / "out"),
                              "--no-sim", "--no-nav2", "--no-record", "--no-analyze"])
    finally:
        holder.release()
    assert rc == 2 and not (tmp_path / "out").exists()
    assert "4242" in capsys.readouterr().err


@pytest.mark.parametrize("mutation", [
    lambda t: t.replace("goal: {x: 1.0, y: 0.0, yaw: 0.0}\n    expect: \"depends on the fake Nav2 mode\"\n  fake_slow",
                        "goal: [1.0, 0.0\n  fake_slow"),                                  # YAML syntax error
    lambda t: t.replace("  fake:\n    goal:", "  fake:\n    inject: [5]\n    goal:"),     # a list where a map belongs
    lambda t: t.replace("odom: {name: /chassis/odom", "odom: {name: /robot/odom"),         # topic mapping differs
])
def test_config_errors_exit_2(tmp_path, mutation, capsys):
    text = FAKE_CFG.read_text(encoding="utf-8")
    changed = mutation(text)
    assert changed != text
    cfg = tmp_path / "bad.yaml"
    cfg.write_text(changed, encoding="utf-8")
    rc = runner_mod.main(["--scenario", "fake", "--config", str(cfg), "--out", str(tmp_path / "out"), "--no-sim"])
    assert rc == 2 and not (tmp_path / "out").exists() and "error" in capsys.readouterr().err


def test_the_test_fault_switch_needs_no_sim(tmp_path):
    rc = runner_mod.main(["--scenario", "fake", "--config", str(FAKE_CFG), "--out", str(tmp_path / "out"),
                          "--test-fault", "executing"])
    assert rc == 2 and not (tmp_path / "out").exists()


def test_the_recorded_topics_are_the_ones_the_tools_use():
    # critic-7: the runner refuses a mapping the recorder and the analysis cannot follow; these names must stay in sync
    record = (REPO / "scripts/wsl/record_d0.sh").read_text(encoding="utf-8")
    stop = (REPO / "scripts/wsl/stop_record.sh").read_text(encoding="utf-8")
    analyze = (REPO / "scripts/wsl/analyze_attempt.py").read_text(encoding="utf-8")
    for name, parent, child in runner_mod.RECORDED_TOPICS.values():
        assert f" {name} " in record and name in stop and f'"{name}"' in analyze
        if parent:
            assert f'("{parent}", "{child}")' in analyze
    assert runner_mod.topic_mapping_problems(__import__("robosim_eval.config", fromlist=["x"]).load_config(
        REPO / "configs" / "baseline.yaml").topics) == []


# ---- manifest (critic-6, shell-10 runner part) ------------------------------------------------------------------------

def test_the_manifest_identifies_what_the_run_loaded(tmp_path, monkeypatch):
    share = tmp_path / "share"
    (share / "maps").mkdir(parents=True)
    (share / "params").mkdir()
    (share / "maps" / "carter_warehouse_navigation.yaml").write_text("image: m.png\n", encoding="utf-8")
    (share / "maps" / "m.png").write_bytes(b"png")
    (share / "params" / "carter_navigation_params.yaml").write_text(CARTER_PARAMS, encoding="utf-8")
    monkeypatch.setattr(run_io, "NAV2_SHARE", share)
    monkeypatch.setattr(run_io, "VENDOR_PKG", share)
    asset = tmp_path / "box.usda"
    asset.write_text("#usda 1.0\n", encoding="utf-8")
    loaded = run_io.loaded_inputs("https://example.invalid/w.usd", {"box_1m": str(asset)},
                                  share / "params" / "carter_navigation_params.yaml")
    assert loaded["obstacle_assets"]["box_1m"]["sha256"] == run_io.sha256_file(asset)
    assert loaded["world"]["uri"] == "https://example.invalid/w.usd" and "no digest" in loaded["world"]["note"]
    assert loaded["nav2_params_effective"]["sha256"] and all(loaded["vendor_install_equals_source"].values())
    m = run_io.write_manifest(tmp_path, "run-1", "fake", str(FAKE_CFG), {"loaded": loaded})
    assert m["digests"]["map_image"] == run_io.sha256_file(share / "maps" / "m.png")
    assert m["digest_files"]["nav2_params"].startswith(str(share)) and "untracked_files" in m["git"]
    assert run_io.windows_to_wsl("D:/RoboSim-Eval/configs/assets/box_1m.usda") == \
        Path("/mnt/d/RoboSim-Eval/configs/assets/box_1m.usda")
    assert run_io.windows_to_wsl("https://example.invalid/x.usd") is None


def test_the_runner_manifest_names_the_code_it_ran(tmp_path, monkeypatch):
    r, w, _ = make_runner(tmp_path, monkeypatch)
    assert r._prepare() is True
    m = json.loads((r.run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert m["code"]["repo"] == str(REPO) and m["code"]["runner_module"].startswith(str(REPO))
    assert m["options"]["test_fault"] is None and "loaded" in m
