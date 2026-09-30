"""Nav2's own exit is recorded apart from the stop script's cleanup result, and a Nav2 launch that ends by itself
during the run is an execution error (release review, focus 3: failures are kept, not merged into 'cleaned up')."""
from __future__ import annotations

from robosim_eval.runner_fsm import State
from test_runner_fakes import FakeWorld, finish, make_runner, to_send_goal


def test_the_launch_exit_code_is_recorded_apart_from_the_cleanup(tmp_path, monkeypatch):
    r, w, scripts = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=1.0), no_nav2=False)
    r.started.update(nav2=True)
    # the requested stop ends the launch with 1 (upstream shutdown noise): recorded, not an error
    scripts.effects["stop_nav2.sh"] = lambda d: (d / "nav2.exit").write_text("1\n")
    to_send_goal(r)
    assert r._send_goal() and r._execute() and r.fsm.state is State.TEARDOWN
    rc, res = finish(r)
    assert res["runner"]["nav2"] == {"stop_script_exit": 0, "launch_exit": 1, "launch_exited_before_stop": False}
    assert not any("Nav2 launch" in e for e in res["runner"]["errors"])


def test_a_launch_that_exits_during_navigation_is_an_execution_error(tmp_path, monkeypatch):
    r, w, scripts = make_runner(tmp_path, monkeypatch, world=FakeWorld(finish_after=30.0), no_nav2=False)
    r.started.update(nav2=True)
    to_send_goal(r)
    assert r._send_goal()
    orig = r.rn.spin

    def spin(seconds: float = 0.05) -> None:   # the launch dies 1 s into EXECUTING; its wrapper writes the exit code
        orig(seconds)
        exit_file = r.run_dir / "nav2.exit"
        if r.fsm.state is State.EXECUTING and r.rn.world.t - r.fsm.entered.t_wall >= 1.0 and not exit_file.exists():
            exit_file.write_text("134\n")
    r.rn.spin = spin
    r._execute()
    rc, res = finish(r)
    assert res["execution_status"] == "error" and rc in (30, 31)
    assert any("Nav2 launch exited during the run (exit 134)" in e for e in res["runner"]["errors"])
    assert res["runner"]["nav2"]["launch_exited_before_stop"] is True and res["runner"]["nav2"]["launch_exit"] == 134
