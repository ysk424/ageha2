import sys, time, json, hashlib, subprocess
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))
from native import Solver, parameters, parameter_hash, Collider

p = parameters()
counts = np.r_[np.full(9090, 11), 10]
offsets = np.r_[0, np.cumsum(counts)].astype(np.uint32)
x = np.empty((100000, 3), np.float32)
for strand, (a, b) in enumerate(zip(offsets[:-1], offsets[1:])):
    x[a:b, 0] = (strand % 100) * 0.2 + np.arange(b - a) * 0.01
    x[a:b, 1] = (strand // 100) * 0.02
    x[a:b, 2] = p["guide_radius"]
fixed = np.zeros(len(x), np.uint8)
fixed[offsets[:-1]] = 1
s = Solver(x, offsets, fixed, p, dt=1 / 24, max_colliders=1)
cols = [Collider(0, 0, center=(0, 0, 0), friction=p["friction"])]
rows = []
for f in range(720):
    start = time.perf_counter()
    st = s.step(x, cols)
    st["total_ms"] = (time.perf_counter() - start) * 1000
    st["frame"] = f + 1
    if f >= 120:
        rows.append(st)
    if f % 120 == 0:
        print("BENCH", f + 1, st["native_ms"], flush=True)
out = ROOT / "outputs/benchmark"
out.mkdir(parents=True, exist_ok=True)
report = dict(
    points=len(x),
    strands=len(counts),
    warmup=120,
    measured=600,
    scenario="all free points contacting plane",
    contact_count_range=[min(r["contacts"] for r in rows), max(r["contacts"] for r in rows)],
    parameters=p,
    parameter_hash=parameter_hash(p),
    binary_hash=hashlib.sha256(
        (ROOT / "extension/bin/kami4_hair_core.dll").read_bytes()
    ).hexdigest(),
    gpu=subprocess.check_output(
        ["nvidia-smi", "--query-gpu=name,driver_version", "--format=csv,noheader"], text=True
    ).strip(),
    blender="Measured separately in Blender",
    native_median=float(np.median([r["native_ms"] for r in rows])),
    transfer_median=float(np.median([r["total_ms"] for r in rows])),
    max_length_error=max(r["max_length_error"] for r in rows),
    allocations=max(r["frame_allocations"] for r in rows),
    launch_counts=sorted(set(r["launches"] for r in rows)),
    nonfinite=sum(r["nonfinite"] for r in rows),
)
report["pass"] = (
    report["native_median"] <= 20
    and report["transfer_median"] <= 41.7
    and report["allocations"] == 0
    and len(report["launch_counts"]) == 1
    and report["nonfinite"] == 0
)
(out / "report.json").write_text(json.dumps(report, indent=2))
(out / "frames.json").write_text(json.dumps(rows))
print(json.dumps(report, indent=2))
s.close()
