"""Fixed-input tests for scripts/wsl/analyze_attempt.py (plan doc A7: offline checks, no simulator, no ROS needed).

Run (WSL):  python3 -m pytest -q /mnt/d/RoboSim-Eval/tests
Each case builds a synthetic recording: the robot starts at odom (0, 0, 0), drives along +x to `final_x` until sim
t = 4.0 s, then stands still. Receive time = 3 x sim time (RTF ~0.33, as measured with Nav2 running). Spawn (0, 0, 0)
makes the AMCL-independent pose equal to odom; map->odom is identity, so the AMCL estimate equals it too.
"""
import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts", "wsl"))
import analyze_attempt as aa  # noqa: E402

UUID = "aa" * 16
OLD = "bb" * 16
NS = 3_000_000_000  # receive ns per sim second
GOAL = (2.0, 0.0, 0.0)
SPAWN = (0.0, 0.0, 0.0)


def make_run(final_x=2.0, rec_after=3.0, status_seq=((0.5, 2), (4.0, 4)), uuid=UUID, gap=None, feedback=True):
    bag = {k: [] for k in ("clock", "odom", "cmd_vel", "status", "feedback", "tf_map_odom", "tf_odom_base")}
    t_move_end = 4.0
    for i in range(int((t_move_end + rec_after) * 60) + 1):
        s = i / 60.0
        if gap and gap[0] <= s < gap[1]:
            continue
        t = int(s * NS)
        moving = s < t_move_end
        x = final_x * s / t_move_end if moving else final_x
        v = final_x / t_move_end if moving else 0.0
        bag["clock"].append((t, s))
        bag["odom"].append((t, s, "odom", "base_link", x, 0.0, 0.0, abs(v), 0.0))
        bag["tf_odom_base"].append((t, s, x, 0.0, 0.0))
        if i % 3 == 0:
            bag["tf_map_odom"].append((t, s, 0.0, 0.0, 0.0))
        if feedback and 0.5 <= s <= t_move_end and i % 2 == 0:
            bag["feedback"].append((t, uuid, s, "map", x, 0.0, 0.0, max(0.0, final_x - x), s - 0.5, 0))
    for s, code in status_seq:
        bag["status"].append((int(s * NS), uuid, code))
    return bag


def transcript(goal=GOAL, uuid=UUID, rejected=False, status="SUCCEEDED"):
    return {"transcript": "goal-test.txt", "sent_goal": list(goal) if goal else None, "goal_id": uuid, "rejected": rejected,
            "status_text": status, "error_code": 0, "error_msg": "", "accepted_wall": "w0", "result_wall": "w1", "client_exit": 0}


def test_success_is_reached_and_pass():
    r, rows = aa.evaluate(make_run(), transcript(), GOAL, SPAWN)
    assert (r["execution_status"], r["task_outcome"], r["data_status"], r["validation_status"]) == ("completed", "reached", "complete", "pass")
    assert r["stop_still"]["state"] == "confirmed"
    assert r["arrival_check"]["event"] == "stop_confirmed" and r["arrival_check"]["error_to_goal_m"] < 1e-6
    assert r["safety_status"] == "unknown" and rows[0][0] == "recv_wall_ns"


def test_aborted_is_unknown_not_unreachable_and_fails():
    r, _ = aa.evaluate(make_run(status_seq=((0.5, 2), (4.0, 6))), transcript(status="ABORTED"), GOAL, SPAWN)
    assert r["nav2_raw"]["terminal_status_name"] == "ABORTED"
    assert r["task_outcome"] == "unknown" and r["validation_status"] == "fail"


def test_canceled_goal():
    r, _ = aa.evaluate(make_run(status_seq=((0.5, 2), (4.0, 5))), transcript(status="CANCELED"), GOAL, SPAWN)
    assert (r["task_outcome"], r["validation_status"]) == ("canceled", "fail")


def test_no_terminal_status_is_interrupted_and_inconclusive():
    r, _ = aa.evaluate(make_run(status_seq=((0.5, 2),)), transcript(), GOAL, SPAWN)
    assert (r["execution_status"], r["task_outcome"], r["validation_status"]) == ("interrupted", "unknown", "inconclusive")


def test_recording_too_short_after_result_is_inconclusive_not_fail():
    r, _ = aa.evaluate(make_run(rec_after=0.3), transcript(), GOAL, SPAWN)
    assert r["stop_still"]["state"] == "not_observed"
    assert r["validation_status"] == "inconclusive"


def test_stale_status_of_an_older_goal_is_ignored():
    bag = make_run(status_seq=((0.5, 2),))
    bag["status"] = [(int(0.1 * NS), OLD, 4)] + bag["status"] + [(int(5.0 * NS), OLD, 4)]
    r, _ = aa.evaluate(bag, transcript(), GOAL, SPAWN)
    assert r["nav2_raw"]["terminal_status_code"] is None
    assert r["target_goal"]["other_goal_ids_in_recording"] == [OLD]
    assert (r["execution_status"], r["validation_status"]) == ("interrupted", "inconclusive")


def test_without_transcript_the_goal_is_unverified_and_target_comes_from_the_bag():
    tr = transcript(goal=None, uuid=None)
    r, _ = aa.evaluate(make_run(), tr, GOAL, SPAWN)
    assert r["target_goal"]["id"] == UUID and r["goal"]["verified_against_transcript"] is False
    assert r["task_outcome"] == "reached" and r["validation_status"] == "inconclusive"


def test_goal_argument_must_match_the_sent_goal():
    with pytest.raises(aa.GoalMismatch):
        aa.evaluate(make_run(), transcript(goal=(3.0, 0.0, 0.0)), GOAL, SPAWN)


def test_data_gap_longer_than_dropout_makes_data_incomplete():
    r, _ = aa.evaluate(make_run(gap=(2.0, 3.0)), transcript(), GOAL, SPAWN)  # 1 sim s = 3 s wall > 2 s dropout
    assert r["data_status"] == "incomplete" and r["validation_status"] == "inconclusive"


def test_without_spawn_there_is_no_independent_source():
    r, _ = aa.evaluate(make_run(), transcript(), GOAL, None)
    assert r["arrival_check"]["source"] == "nav2_feedback_map" and r["validation_status"] == "inconclusive"


def test_rejected_goal_fails_and_keeps_the_reason():
    bag = make_run(status_seq=())
    r, _ = aa.evaluate(bag, transcript(uuid=None, rejected=True, status="REJECTED"), GOAL, SPAWN)
    assert r["nav2_raw"]["rejected"] is True
    assert (r["execution_status"], r["task_outcome"], r["validation_status"]) == ("completed", "unknown", "fail")


def test_position_error_above_tolerance_fails():
    goal = (2.8, 0.0, 0.0)
    r, _ = aa.evaluate(make_run(), transcript(goal=goal), goal, SPAWN)
    assert r["arrival_check"]["error_to_goal_m"] == pytest.approx(0.8)
    assert (r["task_outcome"], r["validation_status"]) == ("unknown", "fail")


def test_transcript_parser(tmp_path):
    (tmp_path / "goal-202437.txt").write_text(
        "send_goal start 2026-09-29T20:24:37-07:00 action=/navigate_to_pose frame=map x=-4.0 y=-1.0 yaw=0.0 qz=0.0 qw=1.0\n"
        "2026-09-29T20:24:40.495 Goal accepted with ID: 8e28b7ce036f43659b4be8c71c404771\n"
        "2026-09-29T20:25:06.105     error_code: 0\n"
        "2026-09-29T20:25:06.105 error_msg: ''\n"
        "2026-09-29T20:25:06.105 Goal finished with status: SUCCEEDED\n"
        "send_goal end 2026-09-29T20:25:06-07:00 action_client_exit=0 settle_s=6\n", encoding="utf-8")
    tr = aa.parse_goal_transcript(str(tmp_path))
    assert tr["sent_goal"] == [-4.0, -1.0, 0.0] and tr["goal_id"] == "8e28b7ce036f43659b4be8c71c404771"
    assert (tr["status_text"], tr["error_code"], tr["error_msg"], tr["client_exit"]) == ("SUCCEEDED", 0, "", 0)


def test_pose_compose_with_the_real_spawn():
    x, y, yaw = aa.pose_compose((-6.0, -1.0, math.pi), (0.5, 0.0, 0.0))
    assert (x, y) == (pytest.approx(-6.5), pytest.approx(-1.0))


def test_stream_with_no_message_inside_the_window_makes_data_incomplete():
    # Codex D0 round1c-a #2: completeness was judged on the whole-bag count; a stream present only outside the
    # accept..arrival window passed whenever the window itself was not longer than the dropout threshold.
    bag = make_run()
    bag["clock"] = [(bag["clock"][-1][0] + 10 * NS, 99.0)]      # the only /clock message arrives after the window
    r, _ = aa.evaluate(bag, transcript(), GOAL, SPAWN, dropout=100.0)   # a large threshold isolates the in-window rule
    assert r["data_status"] == "incomplete" and r["validation_status"] == "inconclusive"
    assert "clock: no messages in the evaluation window" in " ".join(r["verdict_reasons"]["inconclusive"])


def test_transcript_without_goal_id_does_not_let_a_bag_goal_pass():
    # Codex D0 round1c-a #1: with the sent goal but no goal id in the transcript, the first accepted goal in the bag
    # was taken as the target and could pass although it may belong to another attempt.
    r, _ = aa.evaluate(make_run(), transcript(uuid=None), GOAL, SPAWN)
    assert r["validation_status"] == "inconclusive"
    assert any("goal id" in s for s in r["verdict_reasons"]["inconclusive"])


def test_stale_arrival_position_is_not_a_navigation_failure():
    # Codex D0 round1c-a #3: odometry stops at sim 1 s (x = 0.5), the result comes at 4 s; the last odometry sample is
    # far older than the arrival check and must not produce a position-error failure.
    bag = make_run(final_x=2.0)
    bag["odom"] = [o for o in bag["odom"] if o[1] <= 1.0]
    r, _ = aa.evaluate(bag, transcript(), GOAL, SPAWN)
    assert r["validation_status"] == "inconclusive" and not r["verdict_reasons"]["fail"]
    assert r["data_status"] == "incomplete"
    assert any("position sample" in s for s in r["verdict_reasons"]["inconclusive"])


def test_map_base_composition_never_uses_a_later_map_odom_transform():
    # Codex D0 round1c-a #4: an odom->base_link sample received before the first map->odom must not be composed with it.
    out = aa.compose_map_base([(10 * NS, 10.0, 100.0, 0.0, 0.0)],
                              [(1 * NS, 1.0, 0.0, 0.0, 0.0), (11 * NS, 11.0, 0.0, 0.0, 0.0)])
    assert [p[0] for p in out] == [11 * NS] and out[0][2] == 100.0


@pytest.mark.parametrize("goal, sent", [((2.0, 0.0, float("nan")), GOAL), (GOAL, (2.0, float("nan"), 0.0)),
                                        ((2.0, float("inf"), 0.0), None)])
def test_non_finite_goal_values_are_rejected(goal, sent):
    # Codex D0 round1c-a #5: NaN compares false, so a NaN goal passed the transcript check.
    with pytest.raises(aa.GoalMismatch):
        aa.evaluate(make_run(), transcript(goal=sent), goal, SPAWN)
