#!/usr/bin/env python3
"""analyze_attempt.py — RoboSim Eval D0d: turn one navigation attempt's raw records into result.json + trajectory.csv.

Usage (inside WSL with the ROS environment sourced; see analyze_attempt.sh):
  python3 analyze_attempt.py <attempt_dir> --goal X Y YAW [--spawn X Y YAW] [--tolerance 0.5]
                             [--stop-lin 0.05] [--stop-ang 0.1] [--stop-hold 1.0]

Inputs in <attempt_dir>: rosbag/ (recorded by record_d0.sh), goal-*.txt (action client transcript).

Position sources (plan doc A5/A6: every pose carries frame + source):
  - "nav2_feedback_map":  NavigateToPose feedback current_pose, map frame (Nav2's AMCL-based localization estimate)
  - "tf_map_base_link":   /tf map->odom (AMCL) composed with odom->base_link (Isaac odometry), map frame (estimate)
  - "sim_state_odom_plus_spawn" (only with --spawn): /chassis/odom composed with the USD-authored spawn pose.
    In the 6.1 Nova Carter sample /chassis/odom comes from isaacsim.core.nodes.IsaacComputeOdometry, whose only input
    is the chassis prim, i.e. it reports the simulated chassis state relative to where it was when Play started (no
    wheel/noise model). Composed with the spawn pose this is independent of AMCL/Nav2 localization. It is NOT a
    separate ground-truth topic and assumes the odometry started at the spawn (Play after a reset, no reset since).
Arrival rule: Nav2 terminal status SUCCEEDED, position error to the goal <= tolerance using the independent source when
--spawn is given (otherwise the Nav2 estimate, flagged), and stop-still confirmed.
Stop-still rule (candidate values, plan doc A5): |linear| < stop_lin and |angular| < stop_ang for stop_hold seconds of
simulation time, measured on the odom twist after the terminal action status.
Rejected/aborted goals are reported as task_outcome "unknown", never "unreachable" (plan doc A5).
"""
import argparse, csv, glob, json, math, os, re
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

STATUS_NAMES = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING", 4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def pose_compose(a, b):
    """(x, y, yaw) a (+) b."""
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], wrap(a[2] + b[2]))


def stamp_s(h):
    return h.stamp.sec + h.stamp.nanosec / 1e9


def last_at_or_before(seq, t_ns):
    """seq sorted by receive time in element 0; returns the last element with t <= t_ns (or the first element)."""
    best = None
    for e in seq:
        if e[0] <= t_ns:
            best = e
        else:
            break
    return best if best is not None else (seq[0] if seq else None)


def read_bag(bagdir):
    reader = SequentialReader()
    reader.open(StorageOptions(uri=bagdir, storage_id=""), ConverterOptions("", ""))
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    out = {"clock": [], "odom": [], "cmd_vel": [], "status": [], "feedback": [], "tf_map_odom": [], "tf_odom_base": []}
    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        msg = deserialize_message(data, get_message(types[topic]))
        if topic == "/clock":
            out["clock"].append((t_ns, msg.clock.sec + msg.clock.nanosec / 1e9))
        elif topic == "/chassis/odom":
            p, o, tw = msg.pose.pose.position, msg.pose.pose.orientation, msg.twist.twist
            out["odom"].append((t_ns, stamp_s(msg.header), msg.header.frame_id, msg.child_frame_id, p.x, p.y, yaw_of(o),
                                math.hypot(tw.linear.x, tw.linear.y), abs(tw.angular.z)))
        elif topic == "/cmd_vel":
            out["cmd_vel"].append((t_ns, msg.linear.x, msg.angular.z))
        elif topic == "/navigate_to_pose/_action/status":
            for s in msg.status_list:
                out["status"].append((t_ns, bytes(s.goal_info.goal_id.uuid).hex(), s.status))
        elif topic == "/navigate_to_pose/_action/feedback":
            fb = msg.feedback
            p, o = fb.current_pose.pose.position, fb.current_pose.pose.orientation
            out["feedback"].append((t_ns, stamp_s(fb.current_pose.header), fb.current_pose.header.frame_id, p.x, p.y, yaw_of(o),
                                    fb.distance_remaining, fb.navigation_time.sec + fb.navigation_time.nanosec / 1e9,
                                    fb.number_of_recoveries))
        elif topic == "/tf":
            for tr in msg.transforms:
                key = (tr.header.frame_id, tr.child_frame_id)
                tt = tr.transform
                rec = (t_ns, stamp_s(tr.header), tt.translation.x, tt.translation.y, yaw_of(tt.rotation))
                if key == ("map", "odom"):
                    out["tf_map_odom"].append(rec)
                elif key == ("odom", "base_link"):
                    out["tf_odom_base"].append(rec)
    return out


def compose_map_base(map_odom, odom_base):
    """map->base_link = latest map->odom (+) each odom->base_link sample; returns (t_ns, stamp, x, y, yaw)."""
    res, j = [], 0
    if not map_odom:
        return res
    for t_ns, st, x, y, yaw in odom_base:
        while j + 1 < len(map_odom) and map_odom[j + 1][0] <= t_ns:
            j += 1
        _, _, mx, my, myaw = map_odom[j]
        px, py, pyaw = pose_compose((mx, my, myaw), (x, y, yaw))
        res.append((t_ns, st, px, py, pyaw))
    return res


def sim_time_at(clock, t_ns):
    e = last_at_or_before(clock, t_ns)
    return e[1] if e else None


def parse_goal_transcript(att):
    files = sorted(glob.glob(os.path.join(att, "goal-*.txt")))
    info = {"transcript": None, "accepted_wall": None, "result_wall": None, "status_text": None, "error_code": None,
            "error_msg": None, "goal_id": None}
    if not files:
        return info
    info["transcript"] = os.path.basename(files[-1])
    for line in open(files[-1], encoding="utf-8", errors="replace"):
        m = re.match(r"(\S+) (.*)", line.rstrip())
        if not m:
            continue
        wall, rest = m.groups()
        if "Goal accepted with ID" in rest:
            info["accepted_wall"] = wall
            info["goal_id"] = rest.split()[-1]
        elif rest.strip().startswith("error_code:"):
            info["error_code"] = int(rest.split(":")[1])
        elif rest.strip().startswith("error_msg:"):
            info["error_msg"] = rest.split(":", 1)[1].strip()
        elif "Goal finished with status" in rest:
            info["result_wall"] = wall
            info["status_text"] = rest.split(":")[-1].strip()
    return info


def stop_still(odom, t_end_ns, lin, ang, hold):
    stop = {"confirmed": False, "confirmed_at_sim": None, "max_lin_after_end": None, "max_ang_after_end": None,
            "samples_after_end": 0}
    if t_end_ns is None:
        return stop
    after = [o for o in odom if o[0] >= t_end_ns]
    stop["samples_after_end"] = len(after)
    if not after:
        return stop
    stop["max_lin_after_end"] = max(o[7] for o in after)
    stop["max_ang_after_end"] = max(o[8] for o in after)
    start = None
    for o in after:
        if o[7] < lin and o[8] < ang:
            start = start or o
            if o[1] - start[1] >= hold:
                stop["confirmed"] = True
                stop["confirmed_at_sim"] = o[1]
                break
        else:
            start = None
    return stop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("attempt_dir")
    ap.add_argument("--goal", nargs=3, type=float, required=True, metavar=("X", "Y", "YAW"))
    ap.add_argument("--spawn", nargs=3, type=float, metavar=("X", "Y", "YAW"),
                    help="USD-authored spawn pose in the map frame; enables the AMCL-independent position source")
    ap.add_argument("--tolerance", type=float, default=0.5)
    ap.add_argument("--stop-lin", type=float, default=0.05)
    ap.add_argument("--stop-ang", type=float, default=0.1)
    ap.add_argument("--stop-hold", type=float, default=1.0)
    a = ap.parse_args()
    att = a.attempt_dir
    gx, gy, gyaw = a.goal
    bag = read_bag(os.path.join(att, "rosbag"))
    tr = parse_goal_transcript(att)
    clock = bag["clock"]
    err_to_goal = lambda x, y: math.hypot(x - gx, y - gy)

    terminal = [s for s in bag["status"] if s[2] in (4, 5, 6)]
    accepted = [s for s in bag["status"] if s[2] in (1, 2)]
    t_accept_ns = accepted[0][0] if accepted else None
    t_end_ns = terminal[-1][0] if terminal else None
    raw_status = terminal[-1][2] if terminal else None

    fb_last = bag["feedback"][-1] if bag["feedback"] else None
    tf_mb = compose_map_base(bag["tf_map_odom"], bag["tf_odom_base"])
    tf_last = tf_mb[-1] if tf_mb else None

    final_pose = {
        "nav2_feedback_map": {"x": fb_last[3], "y": fb_last[4], "yaw": fb_last[5], "error_to_goal_m": err_to_goal(fb_last[3], fb_last[4]),
                              "source": "Nav2 feedback current_pose (map frame; AMCL-based localization estimate)"} if fb_last else None,
        "tf_map_base_link": {"x": tf_last[2], "y": tf_last[3], "yaw": tf_last[4], "error_to_goal_m": err_to_goal(tf_last[2], tf_last[3]),
                             "source": "/tf map->odom (AMCL) composed with odom->base_link (Isaac odometry); estimate"} if tf_last else None,
    }

    sim_traj, cross = [], None
    if a.spawn:
        sp = tuple(a.spawn)
        sim_traj = [(o[0], o[1], *pose_compose(sp, (o[4], o[5], o[6]))) for o in bag["odom"]]
        sim_last = sim_traj[-1]
        final_pose["sim_state_odom_plus_spawn"] = {
            "x": sim_last[2], "y": sim_last[3], "yaw": sim_last[4], "error_to_goal_m": err_to_goal(sim_last[2], sim_last[3]),
            "yaw_error_rad": wrap(sim_last[4] - gyaw),
            "source": f"/chassis/odom (IsaacComputeOdometry: simulated chassis state relative to Play start) composed with USD spawn {list(sp)}; independent of AMCL"}
        cross = {}
        for label, t in (("at_goal_accept", t_accept_ns), ("at_terminal_status", t_end_ns), ("at_bag_end", sim_last[0])):
            if t is None:
                continue
            s = last_at_or_before(sim_traj, t)
            m = last_at_or_before(tf_mb, t) if tf_mb else None
            cross[label] = {"sim_state_xy": [round(s[2], 4), round(s[3], 4)],
                            "amcl_estimate_xy": [round(m[2], 4), round(m[3], 4)] if m else None,
                            "amcl_minus_sim_state_m": round(math.hypot(m[2] - s[2], m[3] - s[3]), 4) if m else None}
        mo = bag["tf_map_odom"]
        cross["map_to_odom_first"] = [round(v, 4) for v in mo[0][2:]] if mo else None
        cross["map_to_odom_last"] = [round(v, 4) for v in mo[-1][2:]] if mo else None
        cross["map_to_odom_implied_by_spawn"] = [round(v, 4) for v in sp]
        cross["interpretation"] = ("If the odometry started at the spawn, the true map->odom equals the spawn pose; "
                                   "the difference between map_to_odom_first and the spawn is AMCL's initial error, "
                                   "and its evolution shows AMCL re-localizing during the attempt.")

    stop = stop_still(bag["odom"], t_end_ns, a.stop_lin, a.stop_ang, a.stop_hold)
    sim_accept = sim_time_at(clock, t_accept_ns) if t_accept_ns else None
    sim_end = sim_time_at(clock, t_end_ns) if t_end_ns else None
    wall_s = (t_end_ns - t_accept_ns) / 1e9 if (t_accept_ns and t_end_ns) else None

    counts = {k: len(v) for k, v in bag.items()}
    data_complete = all(counts[k] > 0 for k in ("clock", "odom", "status", "feedback", "tf_map_odom", "tf_odom_base"))
    if "sim_state_odom_plus_spawn" in final_pose:
        check_src, check_err = "sim_state_odom_plus_spawn", final_pose["sim_state_odom_plus_spawn"]["error_to_goal_m"]
    else:
        check_src = "nav2_feedback_map (no --spawn given: localization estimate only)"
        check_err = final_pose["nav2_feedback_map"]["error_to_goal_m"] if fb_last else None
    reached = raw_status == 4 and check_err is not None and check_err <= a.tolerance and stop["confirmed"]
    outcome = ("reached" if reached else "unknown") if raw_status == 4 else ("canceled" if raw_status == 5 else "unknown")

    result = {
        "attempt_dir": att,
        "goal": {"frame": "map", "x": gx, "y": gy, "yaw": gyaw, "position_tolerance_m": a.tolerance, "orientation_assessed": False},
        "execution_status": "completed" if (t_accept_ns and t_end_ns) else "incomplete",
        "task_outcome": outcome,
        "safety_status": "unknown (contact/collision not measured in D0)",
        "data_status": "complete" if data_complete else "incomplete",
        "validation_status": "pass" if reached else "fail",
        "arrival_check": {"source": check_src, "error_to_goal_m": check_err, "tolerance_m": a.tolerance},
        "nav2_raw": {"terminal_status_code": raw_status, "terminal_status_name": STATUS_NAMES.get(raw_status, "none"),
                     "error_code": tr["error_code"], "error_msg": tr["error_msg"], "goal_id": tr["goal_id"],
                     "status_text_from_client": tr["status_text"], "recoveries": fb_last[8] if fb_last else None,
                     "distance_remaining_last_feedback_m": fb_last[6] if fb_last else None},
        "timing": {"accepted_wall": tr["accepted_wall"], "result_wall": tr["result_wall"], "accept_to_result_wall_s": wall_s,
                   "sim_time_at_accept_s": sim_accept, "sim_time_at_result_s": sim_end,
                   "accept_to_result_sim_s": (sim_end - sim_accept) if (sim_accept and sim_end) else None},
        "final_pose": final_pose,
        "position_source_crosscheck": cross,
        "stop_still": {"rule": f"|v|<{a.stop_lin} m/s and |w|<{a.stop_ang} rad/s for {a.stop_hold} s sim time after terminal status, on /chassis/odom twist", **stop},
        "message_counts": counts,
        "notes": [
            "The AMCL-independent source is derived from Isaac's IsaacComputeOdometry output plus the USD spawn; it is not a separate ground-truth topic (D3).",
            "safety_status is unknown because contact/collision data was not measured (D3).",
            "rejected/aborted goals would be reported as unknown, not unreachable (plan doc A5).",
        ],
    }
    with open(os.path.join(att, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    with open(os.path.join(att, "trajectory.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["recv_wall_ns", "sim_stamp_s", "frame_id", "source", "x", "y", "yaw", "lin_speed", "ang_speed"])
        for o in bag["odom"]:
            w.writerow([o[0], f"{o[1]:.3f}", o[2], "odom (Isaac /chassis/odom, relative to Play start)", f"{o[4]:.4f}", f"{o[5]:.4f}", f"{o[6]:.4f}", f"{o[7]:.4f}", f"{o[8]:.4f}"])
        for s in sim_traj:
            w.writerow([s[0], f"{s[1]:.3f}", "map", "sim_state_odom_plus_spawn (independent of AMCL)", f"{s[2]:.4f}", f"{s[3]:.4f}", f"{s[4]:.4f}", "", ""])
        for r in tf_mb:
            w.writerow([r[0], f"{r[1]:.3f}", "map", "tf map->odom (AMCL) + odom->base_link (estimate)", f"{r[2]:.4f}", f"{r[3]:.4f}", f"{r[4]:.4f}", "", ""])
        for fb in bag["feedback"]:
            w.writerow([fb[0], f"{fb[1]:.3f}", fb[2], "nav2_feedback (map, AMCL-based estimate)", f"{fb[3]:.4f}", f"{fb[4]:.4f}", f"{fb[5]:.4f}", "", ""])

    keys = ("task_outcome", "validation_status", "data_status", "arrival_check", "nav2_raw", "timing", "final_pose",
            "position_source_crosscheck", "stop_still", "message_counts")
    print(json.dumps({k: result[k] for k in keys}, indent=2, ensure_ascii=False))
    print("written", os.path.join(att, "result.json"), "and trajectory.csv")


if __name__ == "__main__":
    main()
