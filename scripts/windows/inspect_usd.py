"""inspect_usd.py — RoboSim Eval: read-only inspection of a USD layer (robot spawn transform, OmniGraph node types).

Run with Isaac Sim's bundled Python and its pxr package (set only for the child process), e.g. from PowerShell:
  $ext = 'D:\\isaac-sim-standalone-6.1.0-windows-x86_64\\extscache\\omni.usd.libs-1.0.3+00c488ae.wx64.r.cp312'
  cmd /c "set PYTHONPATH=$ext && set PATH=$ext\\bin;%PATH% && D:\\isaac-sim-standalone-6.1.0-windows-x86_64\\python.bat D:\\RoboSim-Eval\\scripts\\windows\\inspect_usd.py <file.usd> [/World/Nova_Carter_ROS]"
The USD files themselves are downloaded to temp/ (git-ignored) with curl from the NVIDIA asset server.
Only the given layer is read (Sdf); references/payloads are listed, not resolved.
"""
import sys
from pxr import Sdf

path = sys.argv[1]
robot_path = sys.argv[2] if len(sys.argv) > 2 else "/World/Nova_Carter_ROS"
layer = Sdf.Layer.FindOrOpen(path)
print("layer opened:", bool(layer), path)
if not layer:
    sys.exit(1)
root = layer.GetPrimAtPath("/World")
print("children of /World:", [c.name for c in root.nameChildren] if root else None)

robot = layer.GetPrimAtPath(robot_path)
if robot:
    refs = list(robot.referenceList.prependedItems) + list(robot.referenceList.explicitItems) + list(robot.referenceList.addedItems)
    pays = list(robot.payloadList.prependedItems) + list(robot.payloadList.explicitItems)
    print(f"{robot_path} type:", robot.typeName)
    print("  references:", [f"{r.assetPath} {r.primPath}" for r in refs])
    print("  payloads:", [str(p.assetPath) for p in pays])
    for name, attr in robot.attributes.items():
        if name.startswith("xformOp") or name == "xformOpOrder":
            print("  ", name, "=", attr.default)
    print("  child specs:", [c.name for c in robot.nameChildren][:40])

hits = []


def visit(p):
    s = layer.GetPrimAtPath(p)
    if not s:
        return
    a = s.attributes.get("node:type")
    if a is not None and a.default:
        hits.append((str(p), str(a.default)))


layer.Traverse(Sdf.Path.absoluteRootPath, visit)
print("omnigraph node specs in this layer:", len(hits))
for p, t in hits:
    print("  ", p, "->", t)
