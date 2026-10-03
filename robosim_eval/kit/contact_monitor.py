# contact_monitor.py - RoboSim Eval D3: Kit-side contact reporting for the robot, executed INSIDE Isaac Sim through
# isaacsim.code_editor.python_server (scripts/windows/isaac_py.ps1, context "robosim"). Not imported by the WSL tools.
# Defines, in the persistent server context:
#   robosim_contacts_install(robot_root) -> JSON: applies PhysxContactReportAPI (threshold 0) to every rigid body under
#       robot_root and subscribes once to PhysX contact report events. Idempotent.
#   robosim_contacts_fetch(clear) -> JSON: contact FOUND/LOST events recorded since the last clear; PERSIST events are
#       only counted per body pair (wheels touch the floor on every physics step). At most BUFFER_CAP events are kept;
#       later FOUND/LOST events are counted in "dropped" (the batch is then incomplete).
# Event times: t_sim is Isaac's simulation time (isaacsim.core.simulation_manager, the source the clock graph's
# IsaacReadSimulationTime publishes on /clock; reset by stop/reset) and physics_step the physics step count, both read
# when PhysX delivers the report after a step. timeline_t is the USD animation timeline time, which loops about every
# 41 s (docs/setup.md), so it cannot place an event on the run timeline; records made before this change carry it
# under the name "t". t_sim/physics_step are null when the simulation manager is unavailable (sim_clock_error says why).
# Filtering (ground, robot self contacts) is decided on the WSL side from these raw events (robosim_eval/evaluator.py).
import json

import omni.physx
import omni.timeline
import omni.usd
from pxr import PhysicsSchemaTools, PhysxSchema, Usd

try:
    from isaacsim.core.simulation_manager import SimulationManager as _SIM_MANAGER
    _SIM_MANAGER_ERROR = None
except ImportError as _exc:
    _SIM_MANAGER, _SIM_MANAGER_ERROR = None, f"{type(_exc).__name__}: {_exc}"

BUFFER_CAP = 5000
# The server context outlives this file: isaac_py.ps1 re-sends the file on every call, but a subscription made by an
# older version keeps calling that version's callback. install() replaces any subscription not made through the
# current _dispatch; bump this when _dispatch itself changes (changes to _on_contact take effect on the next send).
SUBSCRIPTION_VERSION = 2

ROBOSIM_CONTACTS = globals().setdefault("ROBOSIM_CONTACTS", {})
for _key, _default in (("events", []), ("persist", {}), ("sub", None), ("bodies", []), ("dropped", 0),
                       ("sub_version", None), ("clock_error", None)):
    ROBOSIM_CONTACTS.setdefault(_key, _default)


def _path(i):
    return str(PhysicsSchemaTools.intToSdfPath(i))


def _sim_clock():
    """(simulation time in s, physics steps) from Isaac's SimulationManager; (None, None) when unavailable."""
    if _SIM_MANAGER is None:
        ROBOSIM_CONTACTS["clock_error"] = _SIM_MANAGER_ERROR
        return None, None
    try:
        return float(_SIM_MANAGER.get_simulation_time()), int(_SIM_MANAGER.get_num_physics_steps())
    except (AttributeError, RuntimeError, TypeError, ValueError) as exc:  # never break the PhysX callback
        ROBOSIM_CONTACTS["clock_error"] = f"{type(exc).__name__}: {exc}"
        return None, None


def _on_contact(headers, _data):
    st = ROBOSIM_CONTACTS
    t_sim, step = _sim_clock()
    timeline_t = omni.timeline.get_timeline_interface().get_current_time()
    for h in headers:
        kind = int(h.type)
        a0, a1 = _path(h.actor0), _path(h.actor1)
        if kind == 2:  # CONTACT_PERSIST: count only
            key = f"{a0}|{a1}"
            st["persist"][key] = st["persist"].get(key, 0) + 1
            continue
        if len(st["events"]) >= BUFFER_CAP:
            st["dropped"] += 1
            continue
        st["events"].append({"t_sim": t_sim, "physics_step": step, "timeline_t": timeline_t,
                             "type": {0: "found", 1: "lost"}.get(kind, str(kind)), "actor0": a0, "actor1": a1,
                             "collider0": _path(h.collider0), "collider1": _path(h.collider1)})


def _dispatch(headers, data):
    _on_contact(headers, data)  # looked up at call time: always the latest definition sent to the context


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
    if st["sub"] is not None and st["sub_version"] != SUBSCRIPTION_VERSION:
        old, st["sub"] = st["sub"], None
        if hasattr(old, "unsubscribe"):
            old.unsubscribe()
    if st["sub"] is None:
        st["sub"] = omni.physx.get_physx_simulation_interface().subscribe_contact_report_events(_dispatch)
        st["sub_version"] = SUBSCRIPTION_VERSION
    return json.dumps({"ok": bool(bodies), "bodies": bodies, "subscribed": st["sub"] is not None,
                       "subscription_version": st["sub_version"]})


def robosim_contacts_fetch(clear=True):
    st = ROBOSIM_CONTACTS
    sim_time, step = _sim_clock()
    out = {"ok": True, "events": list(st["events"]), "persist_counts": dict(st["persist"]), "dropped": st["dropped"],
           "bodies": st["bodies"], "subscribed": st["sub"] is not None, "sim_time": sim_time, "physics_step": step,
           "timeline_time": omni.timeline.get_timeline_interface().get_current_time(),
           "sim_clock_error": st["clock_error"], "subscription_version": st["sub_version"]}
    if clear:
        st["events"].clear()
        st["persist"].clear()
        st["dropped"] = 0
    return json.dumps(out)
