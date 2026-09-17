"""Reduce the isolated mesh-contact failure to one original 11-point strand."""

import sys, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))
from native import Solver, parameters
import cache

inp = ROOT / "outputs/input"
base = ROOT / "outputs/real_graph"
out = ROOT / "outputs/minimal_mesh_failure"
out.mkdir(parents=True, exist_ok=True)
offsets = np.load(inp / "offsets.npy")
sid = 5396
a, b = offsets[sid : sid + 2]
x = np.load(inp / "positions.npy")[a:b]
targets = np.load(inp / "targets.npy", mmap_mode="r")[:8, a:b].copy()
allv = np.load(inp / "vertices.npy", mmap_mode="r")[:8]
tri = np.load(inp / "triangles.npy")
m = cache.load(base)
path = np.concatenate(
    [x]
    + [
        cache.read(base, f, m["topology_hash"], m["parameter_hash"], m["points"])[a:b]
        for f in range(1, 9)
    ]
)
low = path.min(0) - 0.03
high = path.max(0) + 0.03
keep = np.zeros(len(tri), bool)
for verts in allv:
    tv = verts[tri]
    keep |= ((tv.max(axis=1) >= low) & (tv.min(axis=1) <= high)).all(axis=1)
picked = tri[keep]
indices = np.unique(picked)
mapping = np.full(len(allv[0]), -1, np.int32)
mapping[indices] = np.arange(len(indices))
smalltri = mapping[picked].astype(np.uint32)
smallv = np.asarray(allv[:, indices], np.float32)
fixed = np.zeros(len(x), np.uint8)
fixed[0] = 1
s = Solver(x, [0, len(x)], fixed, p=parameters(), max_colliders=0)
s.set_mesh(smallv[0], smalltri)
rows = []
states = []
for f in range(8):
    st = s.step(targets[f], mesh_previous=smallv[max(0, f - 1)], mesh_next=smallv[f])
    st["frame"] = f + 1
    rows.append(st)
    states.append(s.x.copy())
np.savez_compressed(
    out / "fixture.npz",
    positions=x,
    targets=targets,
    vertices=smallv,
    triangles=smalltri,
    offsets=np.array([0, len(x)], np.uint32),
    fixed=fixed,
    result=states,
)
report = dict(
    original_strand=sid,
    original_points=[int(a), int(b)],
    points=len(x),
    triangles=len(smalltri),
    vertices=len(indices),
    frames=8,
    parameters=parameters(),
    maximum_penetration=-min(r["min_gap"] for r in rows),
    allowed_penetration=0.25 * parameters()["guide_radius"],
    reproduced=min(r["min_gap"] for r in rows) < -0.25 * parameters()["guide_radius"],
    stats=rows,
)
(out / "report.json").write_text(json.dumps(report, indent=2))
print(json.dumps({k: v for k, v in report.items() if k != "stats"}, indent=2))
s.close()
