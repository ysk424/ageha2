"""Replay the saved one-strand failure without Blender or the full input scene."""

import sys, json, argparse
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))
from native import Solver

parser = argparse.ArgumentParser()
parser.add_argument("--fixture", default=str(ROOT / "outputs/minimal_mesh_failure/fixture.npz"))
args = parser.parse_args()
path = Path(args.fixture)
data = np.load(path)
report = json.loads(path.with_name("report.json").read_text())
s = Solver(
    data["positions"], data["offsets"], data["fixed"], p=report["parameters"], max_colliders=0
)
s.set_mesh(data["vertices"][0], data["triangles"])
minimum = 1.0
for f, target in enumerate(data["targets"]):
    st = s.step(
        target, mesh_previous=data["vertices"][max(0, f - 1)], mesh_next=data["vertices"][f]
    )
    minimum = min(minimum, st["min_gap"])
    print(f + 1, st["min_gap"])
s.close()
assert minimum < -report["allowed_penetration"], (
    "The recorded failure no longer reproduces; investigate the changed binary/algorithm"
)
print("REPRODUCED", -minimum, ">", report["allowed_penetration"])
