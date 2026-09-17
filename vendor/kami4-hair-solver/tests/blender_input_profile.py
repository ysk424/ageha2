import bpy, importlib, time, json
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
a = importlib.import_module("bl_ext.user_default.kami4_hair_solver.addon")
scene = bpy.context.scene
s = scene.kami4
s.replay = False
expected = np.load(ROOT / "outputs/input/targets.npy", mmap_mode="r")
rows = []
hidden = s.source.hide_get()
disabled = s.source.hide_viewport
try:
    for visible in (False, True):
        s.source.hide_set(not visible)
        s.source.hide_viewport = False
        bpy.context.view_layer.update()
        measurements = []
        for frame in range(1, 21):
            t0 = time.perf_counter()
            scene.frame_set(frame)
            t1 = time.perf_counter()
            points, off = a.hair_positions(s.source, scene)
            t2 = time.perf_counter()
            verts, _, sig = a.mesh_positions(s, scene, False)
            t3 = time.perf_counter()
            np.testing.assert_allclose(points, expected[frame - 1], atol=2e-7, rtol=0)
            measurements.append(
                [1000 * (t1 - t0), 1000 * (t2 - t1), 1000 * (t3 - t2), 1000 * (t3 - t0)]
            )
        rows.append(
            dict(
                source_kept_visible=visible,
                median_frame_hair_mesh_total_ms=np.median(measurements[1:], axis=0).tolist(),
            )
        )
finally:
    s.source.hide_set(hidden)
    s.source.hide_viewport = disabled
(ROOT / "outputs/blender_input_profile.json").write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
