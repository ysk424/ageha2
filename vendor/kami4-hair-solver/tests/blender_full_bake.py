import bpy, json, importlib, time
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
addon = importlib.import_module("bl_ext.user_default.kami4_hair_solver.addon")
scene = bpy.context.scene
s = scene.kami4
s.cache_directory = str(ROOT / "outputs/blender_bake_final")
s.replay = False
s.frame_start = 1
s.frame_end = 200
start = time.perf_counter()
assert bpy.ops.kami4.bake() == {"FINISHED"}, s.last_error
r = addon._runtime[scene.as_pointer()]
rows = r["stats"]
assert len(rows) == 200 and len(r["manifest"]["frames"]) == 200
source, offsets = addon.hair_positions(s.source, scene)
expected = np.load(ROOT / "outputs/input/targets.npy", mmap_mode="r")[-1]
np.testing.assert_allclose(source, expected, rtol=0, atol=2e-7)
reference = np.load(ROOT / "outputs/real_final/final_state.npz")["x"]
difference = float(np.max(np.abs(reference - r["solver"].x)))
report = dict(
    frames=200,
    seconds=time.perf_counter() - start,
    source_unchanged=True,
    source=s.source.name,
    collider=s.collider.name,
    points=len(source),
    strands=len(offsets) - 1,
    max_difference_from_exported_run=difference,
    native_ms_median=float(np.median([x["native_ms"] for x in rows])),
    full_blender_frame_ms_median=float(np.median([x["total_ms"] for x in rows])),
    parameter_hash=r["manifest"]["parameter_hash"],
    binary_hash=r["manifest"]["binary_hash"],
    contact_slots=r["solver"].slots,
    native_graph_prepared=r["solver"].prepared_count is not None,
)
(ROOT / "outputs/blender_full_bake.json").write_text(json.dumps(report, indent=2), encoding="utf8")
scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(ROOT / "outputs/kami4_verified_bake.blend"))
print("K4_FULL_BAKE", json.dumps(report), flush=True)
