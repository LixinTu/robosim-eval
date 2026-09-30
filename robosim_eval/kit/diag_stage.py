# diag_stage.py - RoboSim Eval D3: read-only stage diagnostics, executed inside Isaac through python_server.
import json

import omni.usd
from pxr import Usd, UsdPhysics


def robosim_diag_bodies(root="/World/Nova_Carter_ROS", limit=40):
    stage = omni.usd.get_context().get_stage()
    out = {"root_valid": stage.GetPrimAtPath(root).IsValid(), "children": [], "rigid": [], "instance_proxy_rigid": []}
    rp = stage.GetPrimAtPath(root)
    out["children"] = [str(c.GetPath()) for c in rp.GetChildren()][:limit]
    for prim in Usd.PrimRange(rp, Usd.TraverseInstanceProxies()):
        schemas = list(prim.GetAppliedSchemas())
        if "PhysicsRigidBodyAPI" in schemas or prim.HasAPI(UsdPhysics.RigidBodyAPI):
            (out["instance_proxy_rigid"] if prim.IsInstanceProxy() else out["rigid"]).append(
                {"path": str(prim.GetPath()), "schemas": schemas[:8]})
    return json.dumps(out)
