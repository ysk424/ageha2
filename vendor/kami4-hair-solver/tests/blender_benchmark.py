import bpy, sys, importlib.util, json, time, hashlib, subprocess
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
from kami4_dev import native, addon

p = native.parameters()
counts = np.r_[np.full(9090, 11), 10]
off = np.r_[0, np.cumsum(counts)].astype(np.uint32)
x = np.empty((100000, 3), np.float32)
for strand, (a, b) in enumerate(zip(off[:-1], off[1:])):
    x[a:b, 0] = (strand % 100) * 0.2 + np.arange(b - a) * 0.01
    x[a:b, 1] = (strand // 100) * 0.02
    x[a:b, 2] = p["guide_radius"]
data = bpy.data.hair_curves.new("K4Benchmark")
data.add_curves(counts.tolist())
obj = bpy.data.objects.new("K4Benchmark", data)
bpy.context.scene.collection.objects.link(obj)
fixed = np.zeros(len(x), np.uint8)
fixed[off[:-1]] = 1
s = native.Solver(x, off, fixed, p, dt=1 / 24, max_colliders=1)
cols = [native.Collider(0, 0, center=(0, 0, 0), friction=p["friction"])]
rows = []
for f in range(720):
    start = time.perf_counter()
    st = s.step(x, cols)
    addon.update_output(obj, s.x, bpy.context.scene)
    bpy.context.view_layer.update()
    st["blender_total_ms"] = (time.perf_counter() - start) * 1000
    st["frame"] = f + 1
    if f >= 120:
        rows.append(st)
report = dict(
    points=100000,
    strands=len(counts),
    warmup=120,
    frames=600,
    scenario="all free points contacting plane",
    contact_count_range=[min(r["contacts"] for r in rows), max(r["contacts"] for r in rows)],
    blender=bpy.app.version_string,
    gpu=subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], text=True
    ).strip(),
    binary_hash=hashlib.sha256((native.ROOT / "bin/kami4_hair_core.dll").read_bytes()).hexdigest(),
    parameter_hash=native.parameter_hash(p),
    parameters=p,
    native_median=float(np.median([r["native_ms"] for r in rows])),
    blender_total_median=float(np.median([r["blender_total_ms"] for r in rows])),
    fixed_launch_counts=sorted(set(r["launches"] for r in rows)),
    frame_allocations=max(r["frame_allocations"] for r in rows),
    nonfinite=sum(r["nonfinite"] for r in rows),
)
report["pass"] = (
    report["native_median"] <= 20
    and report["blender_total_median"] <= 41.7
    and report["nonfinite"] == 0
)
(ROOT / "outputs/blender_benchmark.json").write_text(json.dumps(report, indent=2))
(ROOT / "outputs/blender_benchmark_frames.json").write_text(json.dumps(rows))
print(json.dumps(report, indent=2))
s.close()
