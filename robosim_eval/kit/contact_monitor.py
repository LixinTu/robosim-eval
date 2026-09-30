# contact_monitor.py - RoboSim Eval D3: Kit-side contact reporting for the robot, executed INSIDE Isaac Sim through
# isaacsim.code_editor.python_server (scripts/windows/isaac_py.ps1, context "robosim"). Not imported by the WSL tools.
# Defines, in the persistent server context:
#   robosim_contacts_install(robot_root) -> JSON: applies PhysxContactReportAPI (threshold 0) to every rigid body under
#       robot_root and subscribes once to PhysX contact report events. Idempotent.
#   robosim_contacts_fetch(clear) -> JSON: contact FOUND/LOST events recorded since the last clear, with the timeline
#       time; PERSIST events are only counted per body pair (wheels touch the floor on every physics step).
# Filtering (ground, robot self contacts) is decided on the WSL side from these raw events (robosim_eval/evaluator.py).
import json

import omni.physx
import omni.timeline
import omni.usd
from pxr import PhysicsSchemaTools, PhysxSchema, Usd

ROBOSIM_CONTACTS = globals().setdefault(
    "ROBOSIM_CONTACTS", {"events": [], "persist": {}, "sub": None, "bodies": [], "dropped": 0})


def _path(i):
    return str(PhysicsSchemaTools.intToSdfPath(i))


def _on_contact(headers, _data):
    st = ROBOSIM_CONTACTS
    t = omni.timeline.get_timeline_interface().get_current_time()
    for h in headers:
        kind = int(h.type)
        a0, a1 = _path(h.actor0), _path(h.actor1)
        if kind == 2:  # CONTACT_PERSIST: count only
            key = f"{a0}|{a1}"
            st["persist"][key] = st["persist"].get(key, 0) + 1
            continue
        if len(st["events"]) >= 5000:
            st["dropped"] += 1
            continue
        st["events"].append({"t": t, "type": {0: "found", 1: "lost"}.get(kind, str(kind)), "actor0": a0, "actor1": a1,
                             "collider0": _path(h.collider0), "collider1": _path(h.collider1)})


def robosim_contacts_install(robot_root="/World/Nova_Carter_ROS"):
    stage = omni.usd.get_context().get_stage()
    if stage is None:
        return json.dumps({"ok": False, "error": "no stage"})
    root = stage.GetPrimAtPath(robot_root)
    if not root.IsValid():
        return json.dumps({"ok": False, "error": f"{robot_root} not found"})
    bodies = []
    for prim in Usd.PrimRange(root):  # the robot subtree only
        if "PhysicsRigidBodyAPI" in prim.GetAppliedSchemas():
            api = PhysxSchema.PhysxContactReportAPI.Apply(prim)
            api.CreateThresholdAttr().Set(0.0)
            bodies.append(str(prim.GetPath()))
    st = ROBOSIM_CONTACTS
    st["bodies"] = bodies
    if st["sub"] is None:
        st["sub"] = omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(_on_contact)
    return json.dumps({"ok": bool(bodies), "bodies": bodies, "subscribed": st["sub"] is not None})


def robosim_contacts_fetch(clear=True):
    st = ROBOSIM_CONTACTS
    out = {"ok": True, "events": list(st["events"]), "persist_counts": dict(st["persist"]), "dropped": st["dropped"],
           "bodies": st["bodies"], "subscribed": st["sub"] is not None,
           "timeline_time": omni.timeline.get_timeline_interface().get_current_time()}
    if clear:
        st["events"].clear()
        st["persist"].clear()
        st["dropped"] = 0
    return json.dumps(out)
