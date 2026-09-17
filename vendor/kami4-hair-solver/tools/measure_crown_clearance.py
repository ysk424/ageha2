"""Compare crown thickness from saved caches in Blender, without simulation."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension'))
import cache


def measure(reference, runs, frames, output):
    directories = [reference] + [d for d in runs if d.resolve() != reference.resolve()]
    manifests = {str(d): cache.load(d) for d in directories}
    ref_manifest = manifests[str(reference)]
    off = np.load(reference / 'offsets.npy').astype(int)
    strand = np.repeat(np.arange(len(off) - 1), np.diff(off))
    local = np.arange(off[-1]) - off[strand]
    vertices = np.load(ROOT / 'outputs/input/vertices.npy', mmap_mode='r')
    triangles = np.load(ROOT / 'outputs/input/triangles.npy')
    for directory in directories:
        m = manifests[str(directory)]
        assert m['topology_hash'] == ref_manifest['topology_hash']
        assert m['parameters']['root_points'] == 2
        np.testing.assert_array_equal(off, np.load(directory / 'offsets.npy'))
    result = dict(reference=str(reference),
                  definition='World-Z highest hair minus highest body, plus shortest distances of the SAME reference free hair points whose closest body point is within 3cm of the highest body point. Not an exact screen-space silhouette gap.',
                  frames={})
    for frame in frames:
        v = vertices[frame - 1]
        top_z = float(v[:, 2].max())
        bv = BVHTree.FromPolygons(v.tolist(), triangles.tolist(), all_triangles=True, epsilon=0)
        ref_x = cache.read(reference, frame, ref_manifest['topology_hash'], ref_manifest['parameter_hash'], ref_manifest['points'])
        candidates = np.flatnonzero(ref_x[:, 2] > top_z - .08)
        crown = []
        fixed_distances = []
        for i in candidates:
            co, normal, face, distance = bv.find_nearest(Vector(ref_x[i]))
            if co.z >= top_z - .03:
                if local[i] >= 2:
                    crown.append(i)
                elif local[i] == 1:
                    fixed_distances.append(distance)
        assert crown and fixed_distances
        row = dict(reference_free_points=len(crown), reference_strands=len(np.unique(strand[crown])),
                   fixed_second_distance_cm_max=float(max(fixed_distances) * 100), runs={})
        for directory in directories:
            m = manifests[str(directory)]
            x = cache.read(directory, frame, m['topology_hash'], m['parameter_hash'], m['points'])
            distances = np.array([bv.find_nearest(Vector(x[i]))[3] for i in crown])
            highest = int(np.argmax(x[:, 2]))
            row['runs'][str(directory)] = dict(
                bending_rigidity=m['parameters']['bending_rigidity'],
                parameter_hash=m['parameter_hash'],
                top_vertical_gap_cm=float((x[highest, 2] - top_z) * 100),
                same_free_points_distance_cm_p50=float(np.percentile(distances, 50) * 100),
                same_free_points_distance_cm_p95=float(np.percentile(distances, 95) * 100),
                same_free_points_distance_cm_max=float(distances.max() * 100),
                highest_point_strand=int(strand[highest]), highest_point_local=int(local[highest]))
        result['frames'][str(frame)] = row
        print(json.dumps(dict(frame=frame, **row)), flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding='utf8')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('reference', type=Path)
    ap.add_argument('runs', nargs='+', type=Path)
    ap.add_argument('--frames', nargs='+', type=int, default=[71])
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args(sys.argv[sys.argv.index('--') + 1:])
    measure(args.reference, args.runs, args.frames, args.output)
