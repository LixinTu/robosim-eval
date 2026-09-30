"""Fixed-input tests for the Kit-side contact monitor (robosim_eval/kit/contact_monitor.py) without Isaac.

The real file is executed the way isaacsim.code_editor.python_server runs it (one context dict used as globals and
locals, re-sent by isaac_py.ps1 on every call), against stand-ins for the omni, pxr and isaacsim modules. PhysX contact
report callbacks are driven by hand with fake event headers.
"""
from __future__ import annotations

import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any, Callable, Dict, List, Optional

import pytest

KIT_FILE = Path(__file__).resolve().parents[1] / "robosim_eval" / "kit" / "contact_monitor.py"
ROBOT = "/World/Nova_Carter_ROS"
GROUND = "/World/warehouse_with_forklifts/GroundPlane/collisionPlane"
BOX = "/World/RoboSimObstacles/low_box"
FOUND, LOST, PERSIST = 0, 1, 2


class FakeSub:
    """carb.Subscription stand-in: unsubscribe() (or dropping it) ends the subscription."""

    def __init__(self, fn: Callable) -> None:
        self.fn, self.active = fn, True

    def unsubscribe(self) -> None:
        self.active = False


class FakeKit:
    """Clocks and subscriptions the fake omni/isaacsim modules expose to the monitor."""

    def __init__(self) -> None:
        self.timeline_t = 0.0
        self.sim_time = 0.0
        self.steps = 0
        self.clock_error: Optional[Exception] = None
        self.subs: List[FakeSub] = []

    def active(self) -> List[FakeSub]:
        return [s for s in self.subs if s.active]

    def contact(self, *headers) -> None:
        """PhysX delivering one step's contact report to every active subscriber."""
        for s in self.active():
            s.fn([NS(type=k, actor0=a0, actor1=a1, collider0=a0 + "/c", collider1=a1 + "/c") for k, a0, a1 in headers],
                 [])

    def simulation_time(self) -> float:
        if self.clock_error:
            raise self.clock_error
        return self.sim_time


class Prim:
    def __init__(self, path: str, rigid: bool = True) -> None:
        self.path, self.rigid = path, rigid

    def IsValid(self) -> bool:  # noqa: N802 (USD API name)
        return True

    def GetPath(self) -> str:  # noqa: N802
        return self.path

    def GetAppliedSchemas(self) -> List[str]:  # noqa: N802
        return ["PhysicsRigidBodyAPI"] if self.rigid else []


@pytest.fixture
def kit(monkeypatch) -> FakeKit:
    k = FakeKit()
    omni = types.ModuleType("omni")
    physx, timeline, usd = (types.ModuleType(f"omni.{n}") for n in ("physx", "timeline", "usd"))
    timeline.get_timeline_interface = lambda: NS(get_current_time=lambda: k.timeline_t)

    def subscribe(fn: Callable) -> FakeSub:
        k.subs.append(FakeSub(fn))
        return k.subs[-1]

    physx.get_physx_simulation_interface = lambda: NS(subscribe_contact_report_events=subscribe)
    bodies = [Prim(ROBOT, rigid=False), Prim(f"{ROBOT}/chassis_link"), Prim(f"{ROBOT}/wheel_left")]
    usd.get_context = lambda: NS(get_stage=lambda: NS(GetPrimAtPath=lambda p: Prim(p, rigid=False)))
    omni.physx, omni.timeline, omni.usd = physx, timeline, usd
    pxr = types.ModuleType("pxr")
    pxr.PhysicsSchemaTools = NS(intToSdfPath=lambda i: i)
    pxr.PhysxSchema = NS(PhysxContactReportAPI=NS(Apply=lambda prim: NS(
        CreateThresholdAttr=lambda: NS(Set=lambda v: None))))
    pxr.Usd = NS(PrimRange=lambda root: list(bodies))
    sim_manager = types.ModuleType("isaacsim.core.simulation_manager")
    sim_manager.SimulationManager = NS(get_simulation_time=k.simulation_time, get_num_physics_steps=lambda: k.steps)
    for name, mod in {"omni": omni, "omni.physx": physx, "omni.timeline": timeline, "omni.usd": usd, "pxr": pxr,
                      "isaacsim": types.ModuleType("isaacsim"), "isaacsim.core": types.ModuleType("isaacsim.core"),
                      "isaacsim.core.simulation_manager": sim_manager}.items():
        monkeypatch.setitem(sys.modules, name, mod)
    return k


def send(ctx: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """isaac_py.ps1 sending the file: python_server runs it in the named context (Executor(ctx, ctx))."""
    ctx = {} if ctx is None else ctx
    exec(compile(KIT_FILE.read_text(encoding="utf-8"), "<string>", "exec"), ctx, ctx)  # noqa: S102
    return ctx


def call(ctx: Dict[str, Any], expr: str) -> Dict[str, Any]:
    """The -Call expression evaluated in the same context; the monitor returns JSON text."""
    return json.loads(eval(expr, ctx, ctx))  # noqa: S307


# ---- simctl-5: events carry the simulation time -----------------------------------------------------------------------

def test_events_are_stamped_with_simulation_time_and_physics_step(kit):
    ctx = send()
    assert call(ctx, "robosim_contacts_install()")["ok"]
    kit.sim_time, kit.steps, kit.timeline_t = 12.5, 750, 3.2
    kit.contact((FOUND, f"{ROBOT}/chassis_link", BOX))
    out = call(ctx, "robosim_contacts_fetch()")
    (ev,) = out["events"]
    assert ev["t_sim"] == 12.5 and ev["physics_step"] == 750 and ev["timeline_t"] == 3.2
    assert "t" not in ev  # the old ambiguous name is gone; its value is timeline_t
    assert out["sim_time"] == 12.5 and out["physics_step"] == 750 and out["timeline_time"] == 3.2


def test_sim_time_stays_ordered_when_the_animation_timeline_loops(kit):
    # D3 collision run: timeline times 5.38, 5.42, 1.15, 3.85 in append order; the simulation clock keeps increasing
    ctx = send()
    call(ctx, "robosim_contacts_install()")
    for sim_t, tl_t, kind in ((45.4, 5.38, FOUND), (45.5, 5.42, FOUND), (82.2, 1.15, LOST), (84.9, 3.85, FOUND)):
        kit.sim_time, kit.timeline_t = sim_t, tl_t
        kit.contact((kind, f"{ROBOT}/wheel_left", BOX))
    events = call(ctx, "robosim_contacts_fetch()")["events"]
    assert [e["t_sim"] for e in events] == [45.4, 45.5, 82.2, 84.9]


def test_unavailable_sim_clock_is_reported_and_never_breaks_the_callback(kit):
    ctx = send()
    call(ctx, "robosim_contacts_install()")
    kit.clock_error = RuntimeError("simulation manager interface not acquired")
    kit.contact((FOUND, f"{ROBOT}/chassis_link", BOX))
    out = call(ctx, "robosim_contacts_fetch()")
    assert out["events"][0]["t_sim"] is None and out["events"][0]["actor1"] == BOX
    assert "not acquired" in out["sim_clock_error"]


def test_missing_simulation_manager_extension_is_reported(kit, monkeypatch):
    monkeypatch.setitem(sys.modules, "isaacsim.core.simulation_manager", None)  # import fails
    ctx = send()
    call(ctx, "robosim_contacts_install()")
    kit.contact((FOUND, f"{ROBOT}/chassis_link", BOX))
    out = call(ctx, "robosim_contacts_fetch()")
    assert out["events"][0]["t_sim"] is None and out["sim_time"] is None
    assert "ImportError" in out["sim_clock_error"] or "ModuleNotFoundError" in out["sim_clock_error"]


# ---- the live Kit keeps state and subscriptions across re-sends of the file ------------------------------------------

def test_install_replaces_a_subscription_made_by_older_monitor_code(kit):
    # state left in the server context by the previous monitor version (commit 156c31a): its callback stamps only 't'
    def old_callback(headers, _data):
        for h in headers:
            ctx["ROBOSIM_CONTACTS"]["events"].append({"t": kit.timeline_t, "type": "found", "actor0": h.actor0,
                                                      "actor1": h.actor1})
    old = FakeSub(old_callback)
    kit.subs.append(old)
    ctx: Dict[str, Any] = {"ROBOSIM_CONTACTS": {"events": [], "persist": {}, "sub": old, "bodies": [], "dropped": 0}}
    send(ctx)
    assert call(ctx, "robosim_contacts_install()")["subscribed"]
    assert not old.active and len(kit.active()) == 1
    call(ctx, "robosim_contacts_fetch()")
    kit.sim_time = 7.0
    kit.contact((FOUND, f"{ROBOT}/chassis_link", BOX))
    (ev,) = call(ctx, "robosim_contacts_fetch()")["events"]
    assert ev["t_sim"] == 7.0


def test_install_and_resend_keep_a_single_subscription(kit):
    ctx = send()
    call(ctx, "robosim_contacts_install()")
    send(ctx)  # every isaac_py.ps1 call re-sends the file
    call(ctx, "robosim_contacts_install()")
    assert len(kit.subs) == 1 and len(kit.active()) == 1
    kit.contact((FOUND, f"{ROBOT}/chassis_link", BOX))
    assert len(call(ctx, "robosim_contacts_fetch()")["events"]) == 1


# ---- simctl-2, monitor side: completeness signals ---------------------------------------------------------------------

def test_contact_found_before_the_clear_still_shows_as_persisting(kit):
    ctx = send()
    call(ctx, "robosim_contacts_install()")
    kit.contact((FOUND, f"{ROBOT}/wheel_left", BOX), (FOUND, f"{ROBOT}/wheel_left", GROUND))
    cleared = call(ctx, "robosim_contacts_fetch()")  # the runner's pre-run clear
    assert len(cleared["events"]) == 2
    for _ in range(3):
        kit.contact((PERSIST, f"{ROBOT}/wheel_left", BOX), (PERSIST, f"{ROBOT}/wheel_left", GROUND))
    out = call(ctx, "robosim_contacts_fetch()")
    assert out["events"] == [] and out["dropped"] == 0
    assert out["persist_counts"] == {f"{ROBOT}/wheel_left|{BOX}": 3, f"{ROBOT}/wheel_left|{GROUND}": 3}


def test_full_buffer_counts_dropped_events_until_the_next_clear(kit):
    ctx = send()
    call(ctx, "robosim_contacts_install()")
    cap = ctx["BUFFER_CAP"]
    kit.contact(*[(FOUND if i % 2 == 0 else LOST, f"{ROBOT}/wheel_left", GROUND) for i in range(cap)])
    kit.contact((FOUND, f"{ROBOT}/chassis_link", BOX), (LOST, f"{ROBOT}/chassis_link", BOX),
                (PERSIST, f"{ROBOT}/chassis_link", BOX))
    out = call(ctx, "robosim_contacts_fetch()")
    assert len(out["events"]) == cap and out["dropped"] == 2  # the obstacle FOUND/LOST were lost: data incomplete
    assert out["persist_counts"] == {f"{ROBOT}/chassis_link|{BOX}": 1}  # persist counts are never capped
    assert call(ctx, "robosim_contacts_fetch()")["dropped"] == 0


def test_fetch_without_clear_keeps_the_buffer(kit):
    ctx = send()
    call(ctx, "robosim_contacts_install()")
    kit.contact((FOUND, f"{ROBOT}/chassis_link", BOX))
    assert len(call(ctx, "robosim_contacts_fetch(clear=False)")["events"]) == 1
    assert len(call(ctx, "robosim_contacts_fetch()")["events"]) == 1
    assert call(ctx, "robosim_contacts_fetch()")["events"] == []
