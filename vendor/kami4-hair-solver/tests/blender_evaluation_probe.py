"""Read-only geometry-equivalence/performance probe in an isolated Blender process."""

import bpy, importlib, time, json, hashlib
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
a = importlib.import_module("bl_ext.user_default.kami4_hair_solver.addon")
scene = bpy.context.scene
s = scene.kami4
s.replay = False
expected = np.load(ROOT / "outputs/input/targets.npy", mmap_mode="r")
expected_mesh = np.load(ROOT / "outputs/input/vertices.npy", mmap_mode="r")
saved = [(o, o.hide_get(), o.hide_viewport) for o in scene.objects]
rows = []
try:
    for mode in ("original", "hide_unrelated", "direct_evaluated_mesh"):
        for o, h, d in saved:
            o.hide_set(h)
            o.hide_viewport = d
        if mode != "original":
            for o, h, d in saved:
                if o.type in ("MESH", "CURVES") and o not in (s.source, s.collider):
                    o.hide_set(True)
        measurements = []
        for frame in range(1, 16):
            t0 = time.perf_counter()
            scene.frame_set(frame)
            t1 = time.perf_counter()
            points, off = a.hair_positions(s.source, scene)
            t2 = time.perf_counter()
            if mode == "direct_evaluated_mesh":
                ev = s.collider.evaluated_get(bpy.context.evaluated_depsgraph_get())
                mesh = ev.data
                vertices = np.empty((len(mesh.vertices), 3), np.float32)
                mesh.vertices.foreach_get("co", vertices.ravel())
                m = np.array(ev.matrix_world)
                verts = np.ascontiguousarray(
                    (vertices @ m[:3, :3].T + m[:3, 3]) * scene.unit_settings.scale_length,
                    np.float32,
                )
                loops = np.empty(len(mesh.loops), np.uint32)
                mesh.loops.foreach_get("vertex_index", loops)
                signature = hashlib.sha256(loops.tobytes()).hexdigest()
            else:
                verts, _, sig = a.mesh_positions(s, scene, False)
            t3 = time.perf_counter()
            np.testing.assert_allclose(points, expected[frame - 1], rtol=0, atol=2e-7)
            np.testing.assert_array_equal(verts, expected_mesh[frame - 1])
            measurements.append(
                [1000 * (t1 - t0), 1000 * (t2 - t1), 1000 * (t3 - t2), 1000 * (t3 - t0)]
            )
        rows.append(
            dict(
                mode=mode,
                median_frame_hair_mesh_total_ms=np.median(measurements[1:], axis=0).tolist(),
                geometry_matches=True,
            )
        )
finally:
    for o, h, d in saved:
        o.hide_set(h)
        o.hide_viewport = d
(ROOT / "outputs/blender_evaluation_probe.json").write_text(json.dumps(rows, indent=2))
print(json.dumps(rows, indent=2))
