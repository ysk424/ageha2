"""Background export from the copy of the currently open Blender scene."""

import bpy, json, sys, time, hashlib
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/input"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "extension"))
from native import normalize

scene = bpy.context.scene
metadata = json.loads((ROOT / "initial_scene.json").read_text(encoding="utf8"))["result"]
source = bpy.data.objects[metadata["settings"]["kami_hair"]["hair"]]
body = bpy.data.objects[metadata["settings"]["kami_hair"]["collider"]]
source.hide_viewport = False
source.hide_set(False)
body.hide_viewport = False
body.hide_set(False)
for name in ("kami3", "kami4"):
    if hasattr(scene, name):
        settings = getattr(scene, name)
        if hasattr(settings, "replay"):
            settings.replay = False
        if hasattr(settings, "live"):
            settings.live = False


def hair():
    ev = source.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = ev.data
    p = np.empty((len(data.points), 3), np.float32)
    data.attributes["position"].data.foreach_get("vector", p.ravel())
    m = np.array(ev.matrix_world)
    sizes = np.array([c.points_length for c in data.curves], np.uint32)
    return np.ascontiguousarray(
        (p @ m[:3, :3].T + m[:3, 3]) * scene.unit_settings.scale_length, dtype=np.float32
    ), np.r_[np.uint32(0), np.cumsum(sizes, dtype=np.uint32)]


def mesh(triangulate):
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    data = ev.to_mesh(
        preserve_all_data_layers=False, depsgraph=bpy.context.evaluated_depsgraph_get()
    )
    try:
        v = np.empty((len(data.vertices), 3), np.float32)
        data.vertices.foreach_get("co", v.ravel())
        m = np.array(ev.matrix_world)
        v = np.ascontiguousarray(
            (v @ m[:3, :3].T + m[:3, 3]) * scene.unit_settings.scale_length, dtype=np.float32
        )
        loops = np.empty(len(data.loops), np.uint32)
        data.loops.foreach_get("vertex_index", loops)
        sig = hashlib.sha256(loops.tobytes()).hexdigest()
        tri = None
        if triangulate:
            data.calc_loop_triangles()
            tri = np.empty((len(data.loop_triangles), 3), np.uint32)
            data.loop_triangles.foreach_get("vertices", tri.ravel())
        return v, tri, sig
    finally:
        ev.to_mesh_clear()


scene.frame_set(1)
bpy.context.view_layer.update()
raw, off = hair()
x, repaired = normalize(raw, off)
v, tri, sig = mesh(True)
np.save(OUT / "positions.npy", x)
np.save(OUT / "raw_positions.npy", raw)
np.save(OUT / "offsets.npy", off)
np.save(OUT / "triangles.npy", tri)
targets = np.lib.format.open_memmap(
    OUT / "targets.npy", mode="w+", dtype=np.float32, shape=(200, len(x), 3)
)
vertices = np.lib.format.open_memmap(
    OUT / "vertices.npy", mode="w+", dtype=np.float32, shape=(200, len(v), 3)
)
begin = time.perf_counter()
for f in range(1, 201):
    if f > 1:
        scene.frame_set(f)
        bpy.context.view_layer.update()
    p, oo = hair()
    vv, _, ss = mesh(False)
    if not np.array_equal(oo, off) or ss != sig or vv.shape != v.shape:
        raise RuntimeError(f"Topology changed at frame {f}")
    targets[f - 1] = p
    vertices[f - 1] = vv
    if f % 10 == 0:
        print("EXPORT", f, round(time.perf_counter() - begin, 1), flush=True)
targets.flush()
vertices.flush()
report = dict(
    source=source.name,
    collider=body.name,
    original_blend=metadata["file"],
    snapshot=bpy.data.filepath,
    blender=bpy.app.version_string,
    points=len(x),
    strands=len(off) - 1,
    vertices=len(v),
    triangles=len(tri),
    repaired_strands=repaired,
    frames=200,
    fps=scene.render.fps / scene.render.fps_base,
    unit=scene.unit_settings.scale_length,
    export_seconds=time.perf_counter() - begin,
    topology_hash=hashlib.sha256(off.tobytes() + x.tobytes()).hexdigest(),
    mesh_topology_hash=sig,
)
(OUT / "manifest.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
)
print(json.dumps(report, ensure_ascii=True), flush=True)
