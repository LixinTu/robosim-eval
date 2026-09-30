#!/usr/bin/env python3
"""analyze_attempt.py — RoboSim Eval D0d: turn one navigation attempt's raw records into result.json + trajectory.csv.

Usage (inside WSL with the ROS environment sourced; see analyze_attempt.sh):
  python3 analyze_attempt.py <attempt_dir> --goal X Y YAW [--spawn X Y YAW] [--tolerance 0.5] [--stop-lin 0.05]
                             [--stop-ang 0.1] [--stop-hold 1.0] [--max-stop-gap 0.25] [--dropout 2.0]
Inputs in <attempt_dir>: rosbag/ (record_d0.sh + stop_record.sh), goal-*.txt (send_goal.sh transcript, optional).
Exit: 0 validation pass; 10 fail; 11 inconclusive; 2 bad arguments / --goal differs from the goal actually sent;
      1 the recording could not be read.

Result contract (plan doc A5): execution_status completed|error|interrupted; task_outcome reached|canceled|unknown (this
tool never emits unreachable or timeout: aborted/rejected goals are "unknown" with the raw Nav2 status kept; timeouts are
D3 scope); safety_status is always "unknown" in D0 (contact not measured); data_status complete|incomplete;
validation_status pass|fail|inconclusive for the D0 expectation "reach the goal and come to rest".

Target goal: the goal id printed by the CLI action client (goal-*.txt); without a transcript, the first goal id that
becomes ACCEPTED/EXECUTING inside the bag. Status and feedback of any other goal id (e.g. a finished goal that is still
listed in the transient-local status array) are ignored. --goal must equal the pose recorded in the transcript's
"send_goal start" line; without a transcript the goal is operator-entered and the attempt is at best "inconclusive".

Position sources (every reported pose carries frame, source and sim stamp):
  nav2_feedback_map          NavigateToPose feedback current_pose of the target goal (map frame; AMCL-based estimate)
  tf_map_base_link           /tf map->odom (AMCL) (+) odom->base_link (Isaac odometry) (map frame; estimate)
  sim_state_odom_plus_spawn  (with --spawn) ideal odometry /chassis/odom (+) USD spawn pose; independent of AMCL, valid
                             only under PRECONDITIONS below
Arrival is evaluated at a defined event: the stop-confirmation instant, else the terminal status, else the recording end.
"""
import argparse, csv, glob, json, math, os, re

STATUS_NAMES = {0: "UNKNOWN", 1: "ACCEPTED", 2: "EXECUTING", 3: "CANCELING", 4: "SUCCEEDED", 5: "CANCELED", 6: "ABORTED"}
PRECONDITIONS = [
    "/chassis/odom is ideal odometry: isaacsim.core.nodes.IsaacComputeOdometry computes it from the simulated chassis "
    "state (its only input is the chassis prim; no wheel or noise model), expressed relative to the pose where it "
    "started (evidence: artifacts/d0d/run-01/usd-inspection.txt; odom ~0 right after Play).",
    "The odometry started at the spawn: the simulation was (re)started with Play from the authored stage and was not "
    "stopped/reset between that Play and the end of this recording.",
    "The USD-authored root pose of /World/Nova_Carter_ROS equals the chassis (base_link) pose at Play start "
    "(authored layer values; the composed stage was not inspected).",
    "The Isaac world frame equals the Nav2 map frame (supported by the map yaml origin and by the amcl initial_pose in "
    "the pinned params being equal to the USD spawn).",
]


class GoalMismatch(Exception):
    """--goal differs from the goal recorded in the send_goal transcript."""


def yaw_of(q):
    return math.atan2(2.0 * (q.w * q.z + q.x * q.y), 1.0 - 2.0 * (q.y * q.y + q.z * q.z))


def wrap(a):
    return math.atan2(math.sin(a), math.cos(a))


def pose_compose(a, b):
    """(x, y, yaw) a (+) b."""
    c, s = math.cos(a[2]), math.sin(a[2])
    return (a[0] + c * b[0] - s * b[1], a[1] + s * b[0] + c * b[1], wrap(a[2] + b[2]))


def last_at_or_before(seq, t_ns):
    """seq sorted by receive time in element 0; the last element with t <= t_ns (None if there is none)."""
    best = None
    for e in seq:
        if e[0] <= t_ns:
            best = e
        else:
            break
    return best


def read_bag(bagdir):
    """Read the topics the evaluation needs. Tuples (element 0 is always the receive time in ns):
    clock (t, sim) | odom (t, stamp, frame, child, x, y, yaw, |v|, |w|) | cmd_vel (t, v, w) | status (t, uuid, code) |
    feedback (t, uuid, stamp, frame, x, y, yaw, dist_remaining, nav_time, recoveries) | tf_* (t, stamp, x, y, yaw)."""
    from rosbag2_py import SequentialReader, StorageOptions, ConverterOptions  # ROS-only imports stay lazy for tests
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message
    reader = SequentialReader()
    reader.open(StorageOptions(uri=bagdir, storage_id=""), ConverterOptions("", ""))
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    out = {"clock": [], "odom": [], "cmd_vel": [], "status": [], "feedback": [], "tf_map_odom": [], "tf_odom_base": []}
    stamp = lambda h: h.stamp.sec + h.stamp.nanosec / 1e9
    while reader.has_next():
        topic, data, t_ns = reader.read_next()
        msg = deserialize_message(data, get_message(types[topic]))
        if topic == "/clock":
            out["clock"].append((t_ns, msg.clock.sec + msg.clock.nanosec / 1e9))
        elif topic == "/chassis/odom":
            p, o, tw = msg.pose.pose.position, msg.pose.pose.orientation, msg.twist.twist
            out["odom"].append((t_ns, stamp(msg.header), msg.header.frame_id, msg.child_frame_id, p.x, p.y, yaw_of(o),
                                math.hypot(tw.linear.x, tw.linear.y), abs(tw.angular.z)))
        elif topic == "/cmd_vel":
            out["cmd_vel"].append((t_ns, msg.linear.x, msg.angular.z))
        elif topic == "/navigate_to_pose/_action/status":
            for s in msg.status_list:
                out["status"].append((t_ns, bytes(s.goal_info.goal_id.uuid).hex(), s.status))
        elif topic == "/navigate_to_pose/_action/feedback":
            fb = msg.feedback
            p, o = fb.current_pose.pose.position, fb.current_pose.pose.orientation
            out["feedback"].append((t_ns, bytes(msg.goal_id.uuid).hex(), stamp(fb.current_pose.header),
                                    fb.current_pose.header.frame_id, p.x, p.y, yaw_of(o), fb.distance_remaining,
                                    fb.navigation_time.sec + fb.navigation_time.nanosec / 1e9, fb.number_of_recoveries))
        elif topic == "/tf":
            for tr in msg.transforms:
                key, tt = (tr.header.frame_id, tr.child_frame_id), tr.transform
                rec = (t_ns, stamp(tr.header), tt.translation.x, tt.translation.y, yaw_of(tt.rotation))
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
        if t_ns < map_odom[0][0]:
            continue  # no map->odom received yet: never apply a later transform to an earlier sample
        while j + 1 < len(map_odom) and map_odom[j + 1][0] <= t_ns:
            j += 1
        _, _, mx, my, myaw = map_odom[j]
        res.append((t_ns, st, *pose_compose((mx, my, myaw), (x, y, yaw))))
    return res


def parse_goal_transcript(att):
    """Parse the newest goal-*.txt written by send_goal.sh (the sent goal, goal id, result, errors)."""
    files = sorted(glob.glob(os.path.join(att, "goal-*.txt")))
    info = {"transcript": None, "transcripts_found": len(files), "sent_goal": None, "goal_id": None, "accepted_wall": None,
            "result_wall": None, "status_text": None, "rejected": False, "error_code": None, "error_msg": None,
            "client_exit": None}
    if not files:
        return info
    info["transcript"] = os.path.basename(files[-1])
    for line in open(files[-1], encoding="utf-8", errors="replace"):
        line = line.rstrip("\n")
        m = re.search(r"send_goal start .*?\bx=(\S+) y=(\S+) yaw=(\S+)", line)
        if m:
            info["sent_goal"] = [float(m.group(1)), float(m.group(2)), float(m.group(3))]
            continue
        m = re.search(r"send_goal end .*?action_client_exit=(\d+)", line)
        if m:
            info["client_exit"] = int(m.group(1))
            continue
        m = re.match(r"(\S+) (.*)", line)
        if not m:
            continue
        wall, rest = m.groups()
        body = rest.strip()
        if "Goal accepted with ID" in rest:
            info["accepted_wall"] = wall
            info["goal_id"] = rest.split()[-1].lower().replace("-", "")
        elif "Goal was rejected" in rest:
            info["rejected"], info["status_text"], info["result_wall"] = True, "REJECTED", wall
        elif body.startswith("error_code:"):
            info["error_code"] = int(body.split(":", 1)[1])
        elif body.startswith("error_msg:"):
            info["error_msg"] = body.split(":", 1)[1].strip().strip("'\"")
        elif "Goal finished with status" in rest:
            info["result_wall"], info["status_text"] = wall, rest.split(":")[-1].strip()
    return info


def stop_still(odom, t_end_ns, lin, ang, hold, max_gap):
    """Stop-still on the odom twist after the terminal status: |v| < lin and |w| < ang continuously for `hold` s of sim
    time; a sample gap larger than max_gap (sim s) or a backwards stamp restarts the window. States: confirmed; not_still
    (at least 2*hold s of gap-free data and never at rest for hold s); not_observed (too little or gappy data)."""
    res = {"state": "not_observed", "confirmed_at_sim": None, "confirmed_at_t_ns": None, "observed_after_end_sim_s": 0.0,
           "max_gap_after_end_sim_s": None, "max_lin_after_end": None, "max_ang_after_end": None, "samples_after_end": 0}
    if t_end_ns is None:
        return res
    after = [o for o in odom if o[0] >= t_end_ns]
    res["samples_after_end"] = len(after)
    if not after:
        return res
    res["observed_after_end_sim_s"] = after[-1][1] - after[0][1]
    res["max_lin_after_end"] = max(o[7] for o in after)
    res["max_ang_after_end"] = max(o[8] for o in after)
    gaps = [b[1] - a[1] for a, b in zip(after, after[1:])]
    res["max_gap_after_end_sim_s"] = max(gaps) if gaps else None
    start, prev = None, None
    for o in after:
        if prev is not None and (o[1] - prev[1] > max_gap or o[1] < prev[1]):
            start = None
        if o[7] < lin and o[8] < ang:
            start = start or o
            if o[1] - start[1] >= hold:
                res.update(state="confirmed", confirmed_at_sim=o[1], confirmed_at_t_ns=o[0])
                return res
        else:
            start = None
        prev = o
    if res["observed_after_end_sim_s"] >= 2 * hold and (not gaps or max(gaps) <= max_gap):
        res["state"] = "not_still"
    return res


def stream_integrity(seq, lo, hi, stamp_index=1):
    """Largest receive-time gap (s) inside [lo, hi] including the edges, and the number of backwards stamps."""
    times = [e[0] for e in seq if lo <= e[0] <= hi]
    pts = [lo] + times + [hi]
    max_gap = max((b - a) for a, b in zip(pts, pts[1:])) / 1e9 if hi > lo else 0.0
    stamps = [e[stamp_index] for e in seq]
    backwards = sum(1 for a, b in zip(stamps, stamps[1:]) if b < a)
    return {"count": len(seq), "count_in_window": len(times), "max_wall_gap_s": round(max_gap, 3), "backward_stamps": backwards}


def _pose(e, xi, yi, yawi, si, frame, goal=None):
    if e is None:
        return None
    d = {"frame": frame, "x": e[xi], "y": e[yi], "yaw": e[yawi], "sim_stamp_s": e[si], "recv_wall_ns": e[0]}
    if goal is not None:
        d["error_to_goal_m"] = math.hypot(e[xi] - goal[0], e[yi] - goal[1])
    return d


def evaluate(bag, tr, goal, spawn=None, tolerance=0.5, stop_lin=0.05, stop_ang=0.1, stop_hold=1.0, max_stop_gap=0.25,
             dropout=2.0):
    """Pure evaluation of one attempt; returns (result dict, trajectory rows). Raises GoalMismatch."""
    gx, gy, gyaw = goal
    fail_reasons, inconclusive = [], []
    sent = tr.get("sent_goal")
    if not all(math.isfinite(v) for v in goal) or (sent is not None and not all(math.isfinite(float(v)) for v in sent)):
        raise GoalMismatch(f"non-finite goal values: --goal {list(goal)}, sent {sent}")

    if tr.get("sent_goal") is not None:
        sx, sy, syaw = tr["sent_goal"]
        if abs(sx - gx) > 1e-6 or abs(sy - gy) > 1e-6 or abs(wrap(syaw - gyaw)) > 1e-6:
            raise GoalMismatch(f"--goal {list(goal)} differs from the goal sent in {tr.get('transcript')}: {tr['sent_goal']}")
        goal_source, goal_verified = f"goal sent by the CLI action client (transcript {tr.get('transcript')})", True
    else:
        goal_source, goal_verified = "operator-entered --goal (no goal transcript; not verified against the goal actually sent)", False
        inconclusive.append("goal not verified against a send_goal transcript")

    statuses = sorted(bag["status"])
    target, target_src = tr.get("goal_id"), "transcript"
    if not target:
        target_src = "first goal id that became ACCEPTED/EXECUTING in the recording"
        target = next((u for _, u, s in statuses if s in (1, 2)), None)
    if not tr.get("goal_id") and tr.get("sent_goal") is not None and not tr.get("rejected"):
        inconclusive.append("the transcript has no goal id: the target was taken from the recording and may be another goal")
    st = [e for e in statuses if target and e[1] == target]
    other_ids = sorted({u for _, u, _ in statuses if u != target})
    fb = [f for f in bag["feedback"] if target and f[1] == target]
    t_accept = next((t for t, _, s in st if s in (1, 2)), None)
    term = next(((t, s) for t, _, s in st if s in (4, 5, 6)), None)
    t_end, raw_status = term if term else (None, None)
    if t_accept is None and st:
        t_accept = st[0][0]
        inconclusive.append("the target goal's ACCEPTED/EXECUTING status was not recorded")
    rejected = bool(tr.get("rejected"))

    if t_end is not None or rejected:
        execution_status = "completed"
    elif t_accept is not None:
        execution_status = "interrupted"
        inconclusive.append("goal accepted but no terminal status before the recording ended")
    else:
        execution_status = "error"
        inconclusive.append("target goal not observed in the recording")

    odom = bag["odom"]
    stop = stop_still(odom, t_end, stop_lin, stop_ang, stop_hold, max_stop_gap)
    if stop["state"] == "confirmed":
        t_arr, arr_event = stop["confirmed_at_t_ns"], "stop_confirmed"
    elif t_end is not None:
        t_arr, arr_event = t_end, "terminal_status"
    else:
        t_arr, arr_event = (odom[-1][0] if odom else None), "recording_end"
    t_last = max((seq[-1][0] for seq in bag.values() if seq), default=None)

    tf_mb = compose_map_base(bag["tf_map_odom"], bag["tf_odom_base"])
    sim_traj = [(o[0], o[1], *pose_compose(tuple(spawn), (o[4], o[5], o[6]))) for o in odom] if spawn else []
    at = lambda seq, t: last_at_or_before(seq, t) if (seq and t is not None) else None
    positions = {
        "nav2_feedback_map": {"source": "Nav2 feedback current_pose of the target goal (map frame; AMCL-based estimate)",
                              "at_arrival": _pose(at(fb, t_arr), 4, 5, 6, 2, "map", goal),
                              "at_recording_end": _pose(fb[-1] if fb else None, 4, 5, 6, 2, "map", goal)},
        "tf_map_base_link": {"source": "/tf map->odom (AMCL) (+) odom->base_link (Isaac odometry); map frame; estimate",
                             "at_arrival": _pose(at(tf_mb, t_arr), 2, 3, 4, 1, "map", goal),
                             "at_recording_end": _pose(tf_mb[-1] if tf_mb else None, 2, 3, 4, 1, "map", goal)},
        "odom": {"source": "ideal odometry /chassis/odom (IsaacComputeOdometry; odom frame = pose at Play start)",
                 "at_arrival": _pose(at(odom, t_arr), 4, 5, 6, 1, "odom"),
                 "at_recording_end": _pose(odom[-1] if odom else None, 4, 5, 6, 1, "odom")},
    }
    if spawn:
        positions["sim_state_odom_plus_spawn"] = {
            "source": f"ideal odometry /chassis/odom (+) USD spawn {list(spawn)}; independent of AMCL; see preconditions",
            "at_arrival": _pose(at(sim_traj, t_arr), 2, 3, 4, 1, "map", goal),
            "at_recording_end": _pose(sim_traj[-1] if sim_traj else None, 2, 3, 4, 1, "map", goal)}
        arr_src = "sim_state_odom_plus_spawn"
    else:
        arr_src = "nav2_feedback_map"
        inconclusive.append("no AMCL-independent position source (--spawn not given); the Nav2 estimate is not an independent check")
    arr = positions[arr_src]["at_arrival"]
    arr_err = arr["error_to_goal_m"] if arr else None
    if arr is not None and t_arr is not None and t_arr - arr["recv_wall_ns"] > dropout * 1e9:
        inconclusive.append(f"no position sample within {dropout} s before the arrival check (the last one is "
                            f"{(t_arr - arr['recv_wall_ns']) / 1e9:.1f} s older); the position error is not judged")
        arr_err = None

    lo = t_accept if t_accept is not None else (odom[0][0] if odom else 0)
    hi = t_arr if t_arr is not None else (t_last or lo)
    integrity = {name: stream_integrity(bag[name], lo, hi) for name in ("clock", "odom", "tf_odom_base", "tf_map_odom")}
    integrity["feedback_target_goal"] = {"count": len(fb)}
    problems = [f"{n}: no messages" for n, v in integrity.items() if v["count"] == 0]
    problems += [f"{n}: no messages in the evaluation window" for n, v in integrity.items()
                 if v["count"] and v.get("count_in_window") == 0]
    problems += [f"{n}: gap of {v['max_wall_gap_s']} s wall > {dropout} s" for n, v in integrity.items()
                 if "max_wall_gap_s" in v and v["max_wall_gap_s"] > dropout]
    problems += [f"{n}: {v['backward_stamps']} backwards stamps" for n, v in integrity.items() if v.get("backward_stamps")]
    data_complete = not problems
    if not data_complete:
        inconclusive.append("data incomplete: " + "; ".join(problems))
    if raw_status == 4 and stop["state"] == "not_observed":
        inconclusive.append("stop-still could not be observed after the result (recording too short or gappy)")

    if rejected:
        task_outcome = "unknown"
        fail_reasons.append("goal rejected by the action server")
    elif raw_status == 4:
        task_outcome = "reached" if (stop["state"] == "confirmed" and arr_err is not None and arr_err <= tolerance) else "unknown"
        if stop["state"] == "not_still":
            fail_reasons.append("Nav2 reported SUCCEEDED but the robot did not come to rest")
        if arr_err is not None and arr_err > tolerance:
            fail_reasons.append(f"position error {arr_err:.3f} m > tolerance {tolerance} m ({arr_src})")
    elif raw_status == 5:
        task_outcome = "canceled"
        fail_reasons.append("goal canceled")
    else:
        task_outcome = "unknown"
        if raw_status == 6:
            fail_reasons.append("Nav2 terminal status ABORTED (kept as unknown, not interpreted as unreachable)")

    if fail_reasons:
        validation = "fail"
    elif task_outcome == "reached" and not inconclusive:
        validation = "pass"
    else:
        validation = "inconclusive"

    clock = bag["clock"]
    sim_at = lambda t: (last_at_or_before(clock, t) or (None, None))[1] if (clock and t is not None) else None
    fb_last = fb[-1] if fb else None
    crosscheck = None
    if spawn:
        crosscheck = {}
        for label, t in (("at_goal_accept", t_accept), ("at_terminal_status", t_end), ("at_arrival_check", t_arr)):
            s, m = at(sim_traj, t), at(tf_mb, t)
            if s is None:
                continue
            crosscheck[label] = {"sim_state_xy": [round(s[2], 4), round(s[3], 4)],
                                 "amcl_estimate_xy": [round(m[2], 4), round(m[3], 4)] if m else None,
                                 "amcl_minus_sim_state_m": round(math.hypot(m[2] - s[2], m[3] - s[3]), 4) if m else None}
        mo = bag["tf_map_odom"]
        crosscheck["map_to_odom_first"] = [round(v, 4) for v in mo[0][2:]] if mo else None
        crosscheck["map_to_odom_last"] = [round(v, 4) for v in mo[-1][2:]] if mo else None
        crosscheck["map_to_odom_implied_by_spawn"] = [round(v, 4) for v in spawn]

    result = {
        "schema": "robosim-eval attempt result, D0 (plan doc A5)",
        "goal": {"frame": "map", "x": gx, "y": gy, "yaw": gyaw, "source": goal_source, "verified_against_transcript": goal_verified,
                 "position_tolerance_m": tolerance, "orientation_assessed": False},
        "target_goal": {"id": target, "id_source": target_src, "other_goal_ids_in_recording": other_ids},
        "execution_status": execution_status,
        "task_outcome": task_outcome,
        "safety_status": "unknown",
        "data_status": "complete" if data_complete else "incomplete",
        "validation_status": validation,
        "verdict_reasons": {"fail": fail_reasons, "inconclusive": inconclusive},
        "arrival_check": {"source": arr_src, "event": arr_event, "sim_time_s": arr["sim_stamp_s"] if arr else None,
                          "error_to_goal_m": arr_err, "tolerance_m": tolerance},
        "nav2_raw": {"terminal_status_code": raw_status, "terminal_status_name": STATUS_NAMES.get(raw_status, "none"),
                     "rejected": rejected, "status_text_from_client": tr.get("status_text"), "error_code": tr.get("error_code"),
                     "error_msg": tr.get("error_msg"), "client_exit": tr.get("client_exit"), "transcript": tr.get("transcript"),
                     "recoveries": fb_last[9] if fb_last else None,
                     "distance_remaining_last_feedback_m": fb_last[7] if fb_last else None},
        "timing": {"accepted_wall": tr.get("accepted_wall"), "result_wall": tr.get("result_wall"),
                   "accept_to_result_wall_s": (t_end - t_accept) / 1e9 if (t_accept is not None and t_end is not None) else None,
                   "sim_time_at_accept_s": sim_at(t_accept), "sim_time_at_result_s": sim_at(t_end),
                   "accept_to_result_sim_s": (sim_at(t_end) - sim_at(t_accept)) if (sim_at(t_accept) is not None and sim_at(t_end) is not None) else None},
        "positions": positions,
        "position_source_crosscheck": crosscheck,
        "stop_still": {"rule": f"|v|<{stop_lin} m/s and |w|<{stop_ang} rad/s for {stop_hold} s sim time after the terminal "
                               f"status (/chassis/odom twist; window restarts on gaps > {max_stop_gap} s)", **stop},
        "data_integrity": {"window": "goal accept .. arrival check (receive time)", "dropout_threshold_wall_s": dropout, **integrity},
        "message_counts": {k: len(v) for k, v in bag.items()},
        "preconditions_for_sim_state_source": PRECONDITIONS if spawn else None,
        "notes": [
            "safety_status is unknown: contact/collision was not measured in D0 (D3).",
            "task_outcome never uses 'unreachable' or 'timeout' here; rejected/aborted goals stay 'unknown' with the raw status.",
            "The sim-state source is derived from Isaac odometry plus the USD spawn; it is not a separate ground-truth topic.",
        ],
    }

    rows = [["recv_wall_ns", "sim_stamp_s", "frame_id", "source", "x", "y", "yaw", "lin_speed", "ang_speed"]]
    for o in odom:
        rows.append([o[0], f"{o[1]:.3f}", o[2], "ideal odometry /chassis/odom (IsaacComputeOdometry, relative to Play start)",
                     f"{o[4]:.4f}", f"{o[5]:.4f}", f"{o[6]:.4f}", f"{o[7]:.4f}", f"{o[8]:.4f}"])
    for s in sim_traj:
        rows.append([s[0], f"{s[1]:.3f}", "map", "sim_state_odom_plus_spawn (independent of AMCL)", f"{s[2]:.4f}", f"{s[3]:.4f}", f"{s[4]:.4f}", "", ""])
    for r in tf_mb:
        rows.append([r[0], f"{r[1]:.3f}", "map", "tf map->odom (AMCL) + odom->base_link (estimate)", f"{r[2]:.4f}", f"{r[3]:.4f}", f"{r[4]:.4f}", "", ""])
    for f in fb:
        rows.append([f[0], f"{f[2]:.3f}", f[3], "nav2_feedback of the target goal (map, AMCL-based estimate)", f"{f[4]:.4f}", f"{f[5]:.4f}", f"{f[6]:.4f}", "", ""])
    return result, rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("attempt_dir")
    ap.add_argument("--goal", nargs=3, type=float, required=True, metavar=("X", "Y", "YAW"))
    ap.add_argument("--spawn", nargs=3, type=float, metavar=("X", "Y", "YAW"),
                    help="USD-authored spawn pose in the map frame; enables the AMCL-independent position source")
    ap.add_argument("--tolerance", type=float, default=0.5)
    ap.add_argument("--stop-lin", type=float, default=0.05)
    ap.add_argument("--stop-ang", type=float, default=0.1)
    ap.add_argument("--stop-hold", type=float, default=1.0)
    ap.add_argument("--max-stop-gap", type=float, default=0.25)
    ap.add_argument("--dropout", type=float, default=2.0)
    a = ap.parse_args(argv)
    att = a.attempt_dir
    try:
        bag = read_bag(os.path.join(att, "rosbag"))
    except Exception as e:  # the recording itself is unusable: report, do not guess
        print(f"ERROR: cannot read {os.path.join(att, 'rosbag')}: {type(e).__name__}: {e}")
        return 1
    tr = parse_goal_transcript(att)
    try:
        result, rows = evaluate(bag, tr, tuple(a.goal), tuple(a.spawn) if a.spawn else None, a.tolerance, a.stop_lin,
                                a.stop_ang, a.stop_hold, a.max_stop_gap, a.dropout)
    except GoalMismatch as e:
        print(f"ERROR: {e}")
        return 2
    result["attempt_dir"] = att
    with open(os.path.join(att, "result.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    with open(os.path.join(att, "trajectory.csv"), "w", newline="", encoding="utf-8") as f:
        csv.writer(f).writerows(rows)
    keys = ("execution_status", "task_outcome", "safety_status", "data_status", "validation_status", "verdict_reasons",
            "arrival_check", "nav2_raw", "timing", "stop_still", "position_source_crosscheck")
    print(json.dumps({k: result[k] for k in keys}, indent=2, ensure_ascii=False))
    print("written", os.path.join(att, "result.json"), "and trajectory.csv")
    return {"pass": 0, "fail": 10, "inconclusive": 11}[result["validation_status"]]


if __name__ == "__main__":
    raise SystemExit(main())
