"""Read-only cache comparison; never simulates or changes the reference cache."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'extension'))
import cache
from native import normalize


def compare(reference, trial, allow_binary_change=False):
    directories = [Path(reference), Path(trial)]
    manifests = [cache.load(d) for d in directories]
    before, after = [m['parameters'] for m in manifests]
    changes = {k: [before.get(k), after.get(k)] for k in before.keys() | after.keys()
               if before.get(k) != after.get(k)}
    assert manifests[0]['topology_hash'] == manifests[1]['topology_hash']
    assert allow_binary_change or manifests[0]['binary_hash'] == manifests[1]['binary_hash']
    assert manifests[0]['frames'] == manifests[1]['frames'] == list(range(1, 201))
    offsets = np.load(directories[0] / 'offsets.npy').astype(int)
    np.testing.assert_array_equal(offsets, np.load(directories[1] / 'offsets.npy'))
    raw = np.load(ROOT / 'outputs/input/raw_positions.npy')
    initial, repaired = normalize(raw, offsets)
    targets = np.load(ROOT / 'outputs/input/targets.npy', mmap_mode='r')
    fixed = np.r_[offsets[:-1], offsets[:-1] + 1]
    free = np.ones(len(initial), dtype=bool)
    free[fixed] = False
    edges = np.concatenate([np.arange(a, b - 1) for a, b in zip(offsets[:-1], offsets[1:])])
    rest = np.linalg.norm(initial[edges + 1] - initial[edges], axis=1)
    tips = offsets[1:] - 1
    lengths = np.array([np.linalg.norm(np.diff(initial[a:b], axis=0), axis=1).sum()
                        for a, b in zip(offsets[:-1], offsets[1:])])
    short_tips = tips[lengths < before['minimum_dynamic_length']]
    mapping = []
    for sid in repaired:
        a, b = offsets[sid:sid + 2]
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(raw[a:b].astype(float), axis=0), axis=1))]
        distance = arc[-1] / (b - a - 1)
        edge = min(int(np.searchsorted(arc, distance, side='right') - 1), b - a - 2)
        weight = (distance - arc[edge]) / (arc[edge + 1] - arc[edge])
        mapping.append((a + 1, a + edge, a + edge + 1, weight))
    stats = [dict(frames=0, crc_pass=True, finite=True, fixed_point_max_error_m=0.,
                  visible_length_error_max=0., visible_length_p99_max=0.,
                  frame_velocity_max_m_per_s=0.) for _ in directories]
    previous = [None, None]
    rows = []
    for f in range(1, 201):
        target = np.array(targets[f - 1], copy=True)
        for i, a, b, w in mapping:
            target[i] = targets[f - 1, a] * (1 - w) + targets[f - 1, b] * w
        positions = []
        for i, (directory, manifest) in enumerate(zip(directories, manifests)):
            x = cache.read(directory, f, manifest['topology_hash'], manifest['parameter_hash'], manifest['points'])
            st = stats[i]
            st['frames'] += 1
            st['finite'] = st['finite'] and bool(np.isfinite(x).all())
            st['fixed_point_max_error_m'] = max(st['fixed_point_max_error_m'], float(np.abs(x[fixed] - target[fixed]).max()))
            error = np.abs(np.linalg.norm(x[edges + 1] - x[edges], axis=1) / rest - 1)
            st['visible_length_error_max'] = max(st['visible_length_error_max'], float(error.max()))
            st['visible_length_p99_max'] = max(st['visible_length_p99_max'], float(np.percentile(error, 99)))
            if previous[i] is not None:
                speed = np.linalg.norm(x - previous[i], axis=1) * 24
                st['frame_velocity_max_m_per_s'] = max(st['frame_velocity_max_m_per_s'], float(speed.max()))
            previous[i] = x
            positions.append(x)
        delta = positions[1] - positions[0]
        distance = np.linalg.norm(delta[free], axis=1)
        rows.append(dict(frame=f, rms_difference_m=float(np.sqrt(np.mean(distance ** 2))),
                         p95_difference_m=float(np.percentile(distance, 95)),
                         max_difference_m=float(distance.max()),
                         mean_tip_z_difference_m=float(delta[tips, 2].mean()),
                         short_mean_tip_z_difference_m=float(delta[short_tips, 2].mean())))
    for directory, st in zip(directories, stats):
        state = np.load(directory / 'final_state.npz')
        st['final_native_velocity_finite'] = bool(np.isfinite(state['v']).all())
        st['final_native_velocity_max_m_per_s'] = float(np.linalg.norm(state['v'], axis=1).max())
    report = dict(parameter_changes=changes, binary_hashes=[m['binary_hash'] for m in manifests],
                  parameter_hashes=[m['parameter_hash'] for m in manifests],
                  reference=stats[0], trial=stats[1], shape_by_frame=rows,
                  note='Velocities from cache use 24fps finite differences including root motion; final native velocity is only the last frame. Shape differences do not by themselves prove better softness.')
    (directories[1] / 'comparison.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({k: v for k, v in report.items() if k != 'shape_by_frame'}, indent=2))
    print(json.dumps([r for r in rows if r['frame'] in (22, 23, 102, 164, 200)], indent=2))


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('reference', type=Path)
    ap.add_argument('trial', type=Path)
    ap.add_argument('--allow-binary-change', action='store_true', help='Explicit solver experiment; report both binary hashes')
    args = ap.parse_args()
    compare(args.reference, args.trial, args.allow_binary_change)
