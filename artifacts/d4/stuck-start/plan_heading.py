"""Scratch: from each run's rosbag, the first /plan after the goal and the robot heading (AMCL) at that time."""
import glob, math, os, sys
import rosbag2_py
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.utilities import get_message

def yaw(q): return math.atan2(2 * (q.w * q.z + q.x * q.y), 1 - 2 * (q.y * q.y + q.z * q.z))

for bagdir in sys.argv[1:]:
    mcap = glob.glob(os.path.join(bagdir, "rosbag", "**", "*.mcap"), recursive=True)
    if not mcap:
        print(bagdir, "no bag"); continue
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=os.path.dirname(mcap[0]), storage_id="mcap"), rosbag2_py.ConverterOptions("", ""))
    types = {t.name: t.type for t in reader.get_all_topics_and_types()}
    reader.set_filter(rosbag2_py.StorageFilter(topics=["/plan", "/amcl_pose", "/cmd_vel"]))
    amcl = None; plans = 0; out = []; cmds = []
    while reader.has_next():
        topic, data, t = reader.read_next()
        msg = deserialize_message(data, get_message(types[topic]))
        if topic == "/amcl_pose":
            p = msg.pose.pose; amcl = (p.position.x, p.position.y, yaw(p.orientation))
        elif topic == "/plan" and plans < 1 and len(msg.poses) > 5:
            plans += 1
            ps = msg.poses
            p0, p5, p20 = ps[0].pose.position, ps[min(5, len(ps)-1)].pose.position, ps[min(20, len(ps)-1)].pose.position
            d5 = math.atan2(p5.y - p0.y, p5.x - p0.x); d20 = math.atan2(p20.y - p0.y, p20.x - p0.x)
            out.append(f"plan0=({p0.x:.3f},{p0.y:.3f}) dir5={math.degrees(d5):.1f} dir20={math.degrees(d20):.1f} n={len(ps)}")
            if amcl:
                out.append(f"amcl=({amcl[0]:.3f},{amcl[1]:.3f},{math.degrees(amcl[2]):.2f}deg) heading-minus-dir20={math.degrees(math.atan2(math.sin(amcl[2]-d20), math.cos(amcl[2]-d20))):.2f}deg")
        elif topic == "/cmd_vel" and len(cmds) < 1:
            cmds.append(f"first cmd w={msg.angular.z:.4f}")
    print(os.path.basename(bagdir), " | ".join(out + cmds))
