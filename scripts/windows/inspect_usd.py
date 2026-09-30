"""inspect_usd.py — RoboSim Eval: read-only inspection of one USD layer (robot spawn transform, OmniGraph node wiring).

Run with Isaac Sim's bundled Python and its pxr package (set only for the child process), e.g. from PowerShell:
  $ext = 'D:\\isaac-sim-standalone-6.1.0-windows-x86_64\\extscache\\omni.usd.libs-1.0.3+00c488ae.wx64.r.cp312'
  cmd /c "set PYTHONPATH=$ext && set PATH=$ext\\bin;%PATH% && D:\\isaac-sim-standalone-6.1.0-windows-x86_64\\python.bat D:\\RoboSim-Eval\\scripts\\windows\\inspect_usd.py <file.usd> [/World/Nova_Carter_ROS]"
The USD files themselves are downloaded to temp/ (git-ignored) with curl from the NVIDIA asset server.
Only the given layer is read (Sdf): references/payloads are listed, not resolved, and nothing is composed. For OmniGraph
node specs whose type concerns odometry, transforms, clock or driving, every authored input value, relationship target
and attribute connection is printed, so the data path from the chassis prim to the published topic can be traced.
"""
import sys
from pxr import Sdf

path = sys.argv[1]
robot_path = sys.argv[2] if len(sys.argv) > 2 else "/World/Nova_Carter_ROS"
layer = Sdf.Layer.FindOrOpen(path)
print("layer opened:", bool(layer), path)
if not layer:
    sys.exit(1)
print("defaultPrim:", layer.defaultPrim or "(none)")
root = layer.GetPrimAtPath("/World")
print("children of /World:", [c.name for c in root.nameChildren] if root else None)


def items(listop):
    out = []
    for attr in ("explicitItems", "prependedItems", "addedItems", "appendedItems"):
        out += [str(x) for x in getattr(listop, attr, [])]
    return out


def dump_spec(spec, indent="   "):
    for name, attr in sorted(spec.attributes.items()):
        conns = items(attr.connectionPathList)
        if attr.default is not None or conns:
            print(f"{indent}{name} = {attr.default!r}" + (f"  <- connected from {conns}" if conns else ""))
    for name, rel in sorted(spec.relationships.items()):
        print(f"{indent}{name} (relationship) -> {items(rel.targetPathList)}")


robot = layer.GetPrimAtPath(robot_path)
if robot:
    refs = items(robot.referenceList)
    pays = [str(p.assetPath) for p in list(robot.payloadList.prependedItems) + list(robot.payloadList.explicitItems)]
    print(f"{robot_path} type: {robot.typeName!r} references: {refs} payloads: {pays}")
    dump_spec(robot)
    print("  child specs:", [c.name for c in robot.nameChildren][:40])
    for child in robot.nameChildren:
        if child.name == "chassis_link":
            print(f"  override spec {child.path} (specifier {child.specifier}):")
            dump_spec(child, indent="     ")
            print("     child specs:", [c.name for c in child.nameChildren][:20])

KEYWORDS = ("odom", "transform", "clock", "twist", "differential", "articulation", "context", "simulationtime")
nodes = []


def visit(p):
    s = layer.GetPrimAtPath(p)
    if not s:
        return
    a = s.attributes.get("node:type")
    if a is not None and a.default:
        nodes.append((s, str(a.default)))


layer.Traverse(Sdf.Path.absoluteRootPath, visit)
print("omnigraph node specs in this layer:", len(nodes))
for s, t in nodes:
    print("  ", s.path, "->", t)
for s, t in nodes:
    if any(k in t.lower() for k in KEYWORDS):
        print(f"\n== {s.path} ({t})")
        dump_spec(s)
