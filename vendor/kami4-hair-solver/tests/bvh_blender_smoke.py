import bpy, sys, importlib.util, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "kami4_dev",
    ROOT / "extension/__init__.py",
    submodule_search_locations=[str(ROOT / "extension")],
)
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
module.register()
from kami4_dev import addon, cache

scene = bpy.context.scene
scene.render.fps = 24
data = bpy.data.hair_curves.new("SmokeHair")
data.add_curves([11, 11])
points = np.concatenate(
    [
        np.c_[np.linspace(0, 0.1, 11), np.zeros(11), np.full(11, 0.05)],
        np.c_[np.linspace(0, 0.1, 11), np.full(11, 0.1), np.full(11, 0.07)],
    ]
).astype(np.float32)
data.attributes["position"].data.foreach_set("vector", points.ravel())
hair = bpy.data.objects.new("K4SmokeInput", data)
scene.collection.objects.link(hair)
mesh = bpy.data.meshes.new("SmokeTable")
mesh.from_pydata([(-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0)], [], [(0, 1, 2), (0, 2, 3)])
body = bpy.data.objects.new("K4SmokeCollider", mesh)
scene.collection.objects.link(body)
body.keyframe_insert(data_path="location", frame=1)
body.location.z = 0.005
body.keyframe_insert(data_path="location", frame=10)
s = scene.kami4_bvh
s.source = hair
s.collider = body
s.frame_end = 10
s.cache_directory = str(ROOT / "outputs/bvh_blender_smoke_cache")
assert bpy.ops.kami4_bvh.initialize() == {"FINISHED"}
assert bpy.ops.kami4_bvh.simulate() == {"FINISHED"}
assert bpy.ops.kami4_bvh.reset() == {"FINISHED"}
assert bpy.ops.kami4_bvh.bake() == {"FINISHED"}
assert s.source == hair and s.collider == body
r = addon._runtime[scene.as_pointer()]
assert r["manifest"]["frames"] == list(range(1, 11))
expected = r["solver"].x.copy()
original = np.empty_like(points)
hair.data.attributes["position"].data.foreach_get("vector", original.ravel())
np.testing.assert_array_equal(original, points)
scene.frame_set(1)
scene.frame_set(10)
actual = np.empty_like(expected)
s.output.data.attributes["position"].data.foreach_get("vector", actual.ravel())
np.testing.assert_array_equal(actual, expected)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "outputs/bvh_blender_smoke.blend"))
(ROOT / "outputs/bvh_blender_smoke.json").write_text(
    json.dumps(
        dict(
            pass_=True,
            frames=10,
            source_unchanged=True,
            operators=["Initialize", "Simulate", "Reset", "Bake", "Replay"],
            blender=bpy.app.version_string,
            stats=r["stats"],
        ),
        indent=2,
    )
)
print("K4_BLENDER_SMOKE_OK", flush=True)
