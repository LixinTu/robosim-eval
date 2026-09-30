#!/usr/bin/env python3
"""analyze_attempt.py — RoboSim Eval D0d: turn one navigation attempt's raw records into result.json + trajectory.csv.

Usage (inside WSL with the ROS environment sourced):
  python3 analyze_attempt.py <attempt_dir> --goal X Y YAW [--tolerance 0.5]
                             [--stop-lin 0.05] [--stop-ang 0.1] [--stop-hold 1.0]

Inputs in <attempt_dir>: rosbag/ (recorded by record_d0.sh), goal-*.txt (action client transcript).
Position sources and their labels (plan doc A5/A6: every pose carries frame + source; none is independent ground truth):
  - "nav2_feedback_map": NavigateToPose feedback current_pose, map frame = Nav2's TF map->base_link (AMCL estimate)
  - "tf_map_base_link":  composed from /tf map->odom (AMCL) and odom->base_link (Isaac odometry), map frame
  - "odom":              /chassis/odom published by Isaac Sim (odometry from the simulator; not verified as noisy or ideal)
Stop-still rule (candidate values, plan doc A5): |linear| < stop_lin and |angular| < stop_ang for stop_hold seconds of
simulation time, measured on the odom twist after the terminal action status.
"""
import argparse, csv, glob, json, math, os, re, sys
from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

STATUS_NAMES = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING", 4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def stamp_s(h):
    return h.stamp.sec + h.stamp.nanosec / 1e9


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


def compose(map_odom, odom_base):
    """map->base_link = map->odom (+) odom->base_link, pairing each odom->base sample with the latest map->odom."""
    res, j = [], 0
    for t_ns, st, x, y, yaw in odom_base:
        while j + 1 < len(map_odom) and map_odom[j + 1][0] <= t_ns:
            j += 1
        if not map_odom:
            break
        _, _, mx, my, myaw = map_odom[j]
        c, s = math.cos(myaw), math.sin(myaw)
        res.append((t_ns, st, mx + c * x - s * y, my + s * x + c * y, myaw + yaw))
    return res


def sim_time_at(clock, t_ns):
    best = None
    for c_ns, sim in clock:
        if c_ns <= t_ns:
            best = sim
        else:
            break
    return best


def parse_goal_transcript(att):
    files = sorted(glob.glob(os.path.join(att, "goal-*.txt")))
    info = {"transcript": None, "accepted_wall": None, "result_wall": None, "status_text": None, "error_code": None, "error_msg": None, "goal_id": None}
    if not files:
        return info
    info["transcript"] = os.path.basename(files[-1])
    for line in open(files[-1], encoding="utf-8", errors="replace"):
        m = re.match(r"(\S+) (.*)", line.rstrip())
        if not m:
            continue
        wall, rest = m.groups()
        if "Goal accepted with ID" in rest:
            info["accepted_wall"] = wall; info["goal_id"] = rest.split()[-1]
        elif rest.strip().startswith("error_code:"):
            info["error_code"] = int(rest.split(":")[1])
        elif rest.strip().startswith("error_msg:"):
            info["error_msg"] = rest.split(":", 1)[1].strip()
        elif "Goal finished with status" in rest:
            info["result_wall"] = wall; info["status_text"] = rest.split(":")[-1].strip()
    return info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("attempt_dir"); ap.add_argument("--goal", nargs=3, type=float, required=True, metavar=("X", "Y", "YAW"))
    ap.add_argument("--tolerance", type=float, default=0.5); ap.add_argument("--stop-lin", type=float, default=0.05)
    ap.add_argument("--stop-ang", type=float, default=0.1); ap.add_argument("--stop-hold", type=float, default=1.0)
    a = ap.parse_args()
    att = a.attempt_dir; gx, gy, gyaw = a.goal
    bag = read_bag(os.path.join(att, "rosbag"))
    tr = parse_goal_transcript(att)
    clock = bag["clock"]

    # terminal status from the recorded status topic (raw Nav2 status codes)
    terminal = [s for s in bag["status"] if s[2] in (4, 5, 6)]
    accepted = [s for s in bag["status"] if s[2] in (1, 2)]
    t_accept_ns = accepted[0][0] if accepted else None
    t_end_ns = terminal[-1][0] if terminal else None
    raw_status = terminal[-1][2] if terminal else None

    # final pose in the goal frame (map) from the last feedback and from composed TF
    fb_last = bag["feedback"][-1] if bag["feedback"] else None
    tf_mb = compose(bag["tf_map_odom"], bag["tf_odom_base"])
    tf_last = tf_mb[-1] if tf_mb else None
    err_fb = math.hypot(fb_last[3] - gx, fb_last[4] - gy) if fb_last else None
    err_tf = math.hypot(tf_last[2] - gx, tf_last[3] - gy) if tf_last else None

    # stop-still on odom twist after the terminal status (sim time from the odom header)
    stop = {"confirmed": False, "confirmed_at_sim": None, "max_lin_after_end": None, "max_ang_after_end": None, "samples_after_end": 0}
    if t_end_ns is not None:
        after = [o for o in bag["odom"] if o[0] >= t_end_ns]
        stop["samples_after_end"] = len(after)
        if after:
            stop["max_lin_after_end"] = max(o[7] for o in after); stop["max_ang_after_end"] = max(o[8] for o in after)
            start = None
            for o in after:
                if o[7] < a.stop_lin and o[8] < a.stop_ang:
                    start = start or o
                    if o[1] - start[1] >= a.stop_hold:
                        stop["confirmed"] = True; stop["confirmed_at_sim"] = o[1]; break
                else:
                    start = None

    # timing
    sim_accept = sim_time_at(clock, t_accept_ns) if t_accept_ns else None
    sim_end = sim_time_at(clock, t_end_ns) if t_end_ns else None
    wall_s = (t_end_ns - t_accept_ns) / 1e9 if (t_accept_ns and t_end_ns) else None

    # data completeness: the fields D0 needs
    counts = {k: len(v) for k, v in bag.items()}
    data_complete = all(counts[k] > 0 for k in ("clock", "odom", "status", "feedback", "tf_map_odom", "tf_odom_base"))
    reached = raw_status == 4 and err_fb is not None and err_fb <= a.tolerance and stop["confirmed"]
    if raw_status == 4:
        outcome = "reached" if reached else "unknown"
    elif raw_status == 5:
        outcome = "canceled"
    else:
        outcome = "unknown"   # aborted/rejected are NOT interpreted as unreachable (plan doc A5)

    result = {
        "attempt_dir": att,
        "goal": {"frame": "map", "x": gx, "y": gy, "yaw": gyaw, "position_tolerance_m": a.tolerance, "orientation_assessed": False},
        "execution_status": "completed" if (t_accept_ns and t_end_ns) else "incomplete",
        "task_outcome": outcome,
        "safety_status": "unknown (contact/collision not measured in D0)",
        "data_status": "complete" if data_complete else "incomplete",
        "validation_status": "pass" if reached else "fail",
        "nav2_raw": {"terminal_status_code": raw_status, "terminal_status_name": STATUS_NAMES.get(raw_status, "none"),
                     "error_code": tr["error_code"], "error_msg": tr["error_msg"], "goal_id": tr["goal_id"],
                     "status_text_from_client": tr["status_text"], "recoveries": fb_last[8] if fb_last else None,
                     "distance_remaining_last_feedback_m": fb_last[6] if fb_last else None},
        "timing": {"accepted_wall": tr["accepted_wall"], "result_wall": tr["result_wall"], "accept_to_result_wall_s": wall_s,
                   "sim_time_at_accept_s": sim_accept, "sim_time_at_result_s": sim_end,
                   "accept_to_result_sim_s": (sim_end - sim_accept) if (sim_accept and sim_end) else None},
        "final_pose": {
            "nav2_feedback_map": {"x": fb_last[3], "y": fb_last[4], "yaw": fb_last[5], "error_to_goal_m": err_fb,
                                  "source": "Nav2 feedback current_pose (map frame; localization estimate, not ground truth)"} if fb_last else None,
            "tf_map_base_link": {"x": tf_last[2], "y": tf_last[3], "yaw": tf_last[4], "error_to_goal_m": err_tf,
                                 "source": "/tf map->odom (AMCL) composed with odom->base_link (Isaac odometry)"} if tf_last else None,
        },
        "stop_still": {"rule": f"|v|<{a.stop_lin} m/s and |w|<{a.stop_ang} rad/s for {a.stop_hold} s sim time after terminal status, on /chassis/odom twist", **stop},
        "message_counts": counts,
        "notes": [
            "Positions come from Nav2/AMCL estimates and Isaac odometry; independent simulation ground truth was not recorded (D3).",
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
            w.writerow([o[0], f"{o[1]:.3f}", o[2], "odom(Isaac /chassis/odom)", f"{o[4]:.4f}", f"{o[5]:.4f}", f"{o[6]:.4f}", f"{o[7]:.4f}", f"{o[8]:.4f}"])
        for r in tf_mb:
            w.writerow([r[0], f"{r[1]:.3f}", "map", "tf map->odom(AMCL)+odom->base_link(Isaac)", f"{r[2]:.4f}", f"{r[3]:.4f}", f"{r[4]:.4f}", "", ""])
        for fb in bag["feedback"]:
            w.writerow([fb[0], f"{fb[1]:.3f}", fb[2], "nav2_feedback(map, localization estimate)", f"{fb[3]:.4f}", f"{fb[4]:.4f}", f"{fb[5]:.4f}", "", ""])

    print(json.dumps({k: result[k] for k in ("task_outcome", "validation_status", "data_status", "nav2_raw", "timing", "final_pose", "stop_still", "message_counts")}, indent=2, ensure_ascii=False))
    print("written", os.path.join(att, "result.json"), "and trajectory.csv")


if __name__ == "__main__":
    main()
