"""Run the bundled, unmodified Kami4 solver in the Blender session on MCP 9876."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vendor" / "kami4-hair-solver" / "tools"))
from blender_mcp import execute  # noqa: E402


run_directory = ROOT / "test_runs" / datetime.now().strftime("mcp9876_%Y%m%d_%H%M%S")
code = f'''import bpy
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

root = {str(ROOT.parent)!r}
cache_directory = {str(run_directory)!r}
if root not in sys.path:
    sys.path.insert(0, root)
import ageha2

if not hasattr(bpy.context.scene, "kami4"):
    ageha2.register()

scene = bpy.context.scene
settings = scene.kami4
source = bpy.data.objects.get("\\u30ab\\u30fc\\u30d6")
collider = bpy.data.objects.get("CC_Base_Body")
if source is None or source.type != "CURVES":
    raise RuntimeError("test source カーブ was not found")
if collider is None or collider.type != "MESH":
    raise RuntimeError("test collider CC_Base_Body was not found")

original_filepath = bpy.data.filepath
original_mtime_ns = Path(original_filepath).stat().st_mtime_ns
settings.source = source
settings.collider = collider
settings.collider_collection = None
settings.parameter_file = ""
settings.cache_directory = cache_directory
settings.frame_start = 1
settings.frame_end = 200
settings.root_points = 2
settings.replay = False

total_started = time.perf_counter()
initialize_started = time.perf_counter()
runtime = ageha2.kami4_addon.initialize(scene)
initialize_seconds = time.perf_counter() - initialize_started
simulation_started = time.perf_counter()
frames = 0
while ageha2.kami4_addon.simulate_frame(scene):
    frames += 1
simulation_seconds = time.perf_counter() - simulation_started
total_seconds = time.perf_counter() - total_started
settings.replay = True
ageha2.kami4_addon.replay_handler(scene)

manifest = runtime["manifest"]
parameter_hash = manifest["parameter_hash"]
topology_hash = manifest["topology_hash"]
points = int(manifest["points"])
verified = 0
verify_started = time.perf_counter()
for frame in range(1, 201):
    ageha2.kami4_addon.cache.read(
        cache_directory, frame, topology_hash, parameter_hash, points
    )
    verified += 1
verification_seconds = time.perf_counter() - verify_started

stats = runtime["stats"]
native_ms = [float(item["native_ms"]) for item in stats]
frame_total_ms = [float(item["total_ms"]) for item in stats]
dll = Path(ageha2.kami4_native.ROOT) / "bin" / "kami4_hair_core.dll"
result = {{
    "source_blend": original_filepath,
    "source_blend_saved": False,
    "source_blend_mtime_unchanged": Path(original_filepath).stat().st_mtime_ns == original_mtime_ns,
    "cache_directory": cache_directory,
    "frames": frames,
    "root_points": int(settings.root_points),
    "strands": int(manifest["strands"]),
    "points": points,
    "initialize_seconds": initialize_seconds,
    "simulation_seconds": simulation_seconds,
    "total_seconds": total_seconds,
    "average_seconds_per_frame": simulation_seconds / frames,
    "effective_fps": frames / simulation_seconds,
    "native_ms_mean": statistics.fmean(native_ms),
    "native_ms_median": statistics.median(native_ms),
    "full_frame_ms_mean": statistics.fmean(frame_total_ms),
    "full_frame_ms_median": statistics.median(frame_total_ms),
    "verification_seconds": verification_seconds,
    "crc_verified_frames": verified,
    "parameter_hash": parameter_hash,
    "binary_hash": hashlib.sha256(dll.read_bytes()).hexdigest(),
    "final_status": settings.status,
    "final_diagnostics": settings.diagnostics,
    "final_frame": int(scene.frame_current),
    "nonfinite_total": sum(int(item["nonfinite"]) for item in stats),
    "max_length_error": max(float(item["max_length_error"]) for item in stats),
    "max_p99_length_error": max(float(item["p99_length_error"]) for item in stats),
    "minimum_gap": min(float(item["min_gap"]) for item in stats),
    "motion_violations_total": sum(int(item["motion_violations"]) for item in stats),
}}
'''

response = execute(code, port=9876, timeout=600)
print(json.dumps(response, ensure_ascii=False, indent=2))
