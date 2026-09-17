"""T1/T2/T3 use the same 3D CUDA implementation and one material JSON."""

import sys, json, time, argparse
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))
from native import Solver, Collider, parameters, parameter_hash


def scene_colliders(p, cylinder=True, mu=None):
    # A +90 degree rotation about X maps local Z to -Y; -90 maps it to +Y.
    table = Collider(0, 0, rotation=(2**-0.5, -(2**-0.5), 0, 0), friction=0)
    return [table] + (
        [
            Collider(
                3, 1, center=(0, 0.12, 0), radius=0.12, friction=p["friction"] if mu is None else mu
            )
        ]
        if cylinder
        else []
    )


def initial_t1(radius):
    # The polyline has unit arc length, with a smooth 0.02 m central seed.
    def points(width):
        x = np.linspace(-width / 2, width / 2, 10001)
        y = (
            np.where(np.abs(x) < 0.1, 0.01 * (1 + np.cos(np.pi * np.clip(x / 0.1, -1, 1))), 0)
            + radius
        )
        return np.c_[x, y, np.zeros(len(x))]

    low, high = 0.9, 1.0
    for _ in range(40):
        mid = (low + high) / 2
        q = points(mid)
        length = np.linalg.norm(np.diff(q, axis=0), axis=1).sum()
        if length > 1:
            high = mid
        else:
            low = mid
    q = points((low + high) / 2)
    s = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
    return np.column_stack(
        [np.interp(np.linspace(0, s[-1], 101), s, q[:, j]) for j in range(3)]
    ).astype(np.float32)


def shape_metrics(x, p):
    r = p["guide_radius"]
    edge = np.linalg.norm(np.diff(x, axis=0), axis=1)
    a = x[:-1, 0]
    b = x[1:, 0]
    fraction = np.where(
        (a < 0) & (b < 0),
        1.0,
        np.where(
            (a >= 0) & (b >= 0),
            0.0,
            np.where(a < 0, -a / np.where(b != a, b - a, 1), -b / np.where(a != b, a - b, 1)),
        ),
    )
    left = float((edge * fraction).sum())
    right = float(edge.sum() - left)
    return dict(
        height=float(x[:, 1].max()),
        peak_x=float(x[x[:, 1].argmax(), 0]),
        left_material=float(left),
        right_material=float(right),
        symmetry=float(abs(left - right)),
        left_tip=x[0].tolist(),
        right_tip=x[-1].tolist(),
    )


def run(output, fps=240, t1_seconds=8, t2_seconds=5, t3_seconds=8):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    p = parameters()
    off = np.array([0, 101], np.uint32)
    report = {"parameters": p, "parameter_hash": parameter_hash(p), "fps": fps}
    all_stats = []

    def save_run(name, solver, frames, targets, cols):
        rows = []
        states = []
        for f in range(frames):
            st = solver.step(targets(f), cols)
            st.update(
                frame=f + 1,
                test=name,
                time=(f + 1) / fps,
                mean_speed=float(np.linalg.norm(solver.v, axis=1).mean()),
                **shape_metrics(solver.x, p),
            )
            contact = solver.contact_data()[:, 1, :] if len(cols) > 1 else None
            if contact is not None:
                active = contact[:, 0] >= 0
                relative = solver.v - contact[:, 10:13]
                normal = contact[:, 7:10]
                tangent = relative - normal * np.sum(relative * normal, axis=1)[:, None]
                speed = np.linalg.norm(tangent, axis=1)
                jt = np.linalg.norm(contact[:, 4:7], axis=1)
                cap = contact[:, 3] * contact[:, 1]
                valid = active & (contact[:, 1] > 1e-12)
                st.update(
                    cylinder_tangent_speed=float(speed[active].mean()) if active.any() else 0.0,
                    cylinder_max_tangent_speed=float(speed[active].max()) if active.any() else 0.0,
                    cylinder_saturated=int(np.sum(valid & (jt >= 0.99 * cap))),
                    cylinder_contacts=int(active.sum()),
                )
            rows.append(st)
            if f % max(1, fps // 24) == 0 or f == frames - 1:
                states.append(solver.x.copy())
        np.savez_compressed(
            output / f"{name}.npz", positions=states, final=solver.x, velocity=solver.v
        )
        (output / f"{name}.json").write_text(json.dumps(rows, indent=2))
        all_stats.extend(rows)
        return rows

    x = initial_t1(p["guide_radius"])
    rest = np.c_[np.linspace(-0.5, 0.5, 101), np.zeros(101), np.zeros(101)].astype(np.float32)
    fixed = np.zeros(101, np.uint8)
    fixed[[0, -1]] = 1
    s = Solver(rest, off, fixed, p, 1 / fps, (0, -1, 0), plane_axis=2)
    s.set_state(x, np.zeros_like(x))
    frames = round(t1_seconds * fps)

    def target1(f):
        q = x.copy()
        q[0, 0] += 0.18 * (f + 1) / frames
        q[-1, 0] -= 0.18 * (f + 1) / frames
        return q

    rows = save_run("T1", s, frames, target1, scene_colliders(p, False))
    final = rows[-1]
    air = s.x[:, 1] > p["guide_radius"] + 0.001
    regions = []
    start = None
    for i, a in enumerate(np.r_[air, False]):
        if a and start is None:
            start = i
        if not a and start is not None:
            regions.append([start, i - 1])
            start = None
    major = [r for r in regions if max(s.x[r[0] : r[1] + 1, 1]) >= 0.05]
    checks = dict(
        central_region=len(major) == 1 and major[0][0] <= 50 <= major[0][1],
        central_peak=abs(final["peak_x"]) <= 0.08,
        height=final["height"] >= 0.1,
        length=max(r["max_length_error"] for r in rows) <= 0.01,
        p99=max(r["p99_length_error"] for r in rows) <= 0.005,
        penetration=min(r["min_gap"] for r in rows) >= -0.001,
        finite=not any(r["nonfinite"] for r in rows),
    )
    report["T1"] = {
        "checks": checks,
        "pass": all(checks.values()),
        "final": final,
        "airborne_regions": regions,
    }
    s.close()
    print("T1", json.dumps(report["T1"]), flush=True)
    x = np.c_[np.linspace(-0.5, 0.5, 101), np.full(101, 0.36), np.zeros(101)].astype(np.float32)
    s = Solver(x, off, p=p, dt=1 / fps, gravity=(0, -1, 0), plane_axis=2)
    cols = scene_colliders(p)
    rows = save_run("T2", s, round(t2_seconds * fps), lambda f: x, cols)
    final = rows[-1]
    checks = dict(
        symmetry=final["symmetry"] <= 0.03,
        drape=final["left_tip"][0] < 0 < final["right_tip"][0]
        and max(final["left_tip"][1], final["right_tip"][1]) < 0.12,
        top=abs(final["height"] - (0.24 + p["guide_radius"])) <= 0.02,
        penetration=min(r["min_gap"] for r in rows) >= -0.001,
        chord=final["chord_bound"] <= p["contact_tolerance"],
        settled=bool(np.mean([r["mean_speed"] for r in rows[-round(0.5 * fps) :]]) <= 0.01),
        length=max(r["max_length_error"] for r in rows) <= 0.01,
        finite=not any(r["nonfinite"] for r in rows),
    )
    report["T2"] = {"checks": checks, "pass": all(checks.values()), "final": final}
    print("T2", json.dumps(report["T2"]), flush=True)
    x2 = s.x.copy()
    v2 = s.v.copy()
    s.close()
    for name, mu in [("T3", p["friction"]), ("T3_mu0", 0)]:
        fixed = np.zeros(101, np.uint8)
        fixed[-1] = 1
        s = Solver(x, off, fixed, p, 1 / fps, (0, -1, 0), plane_axis=2)
        s.set_state(x2, v2)
        frames = round(t3_seconds * fps)

        # Start targets at the actual T2 end state; replace the root interpolation origin.
        # set_state also updates the previous kinematic targets.
        def target3(f):
            q = x2.copy()
            q[-1, 0] += 0.18 * (f + 1) / frames
            return q

        rows = save_run(name, s, frames, target3, scene_colliders(p, True, mu))
        final = rows[-1]
        checks = dict(
            material_transfer=report["T2"]["final"]["left_material"] - final["left_material"]
            >= 0.05,
            cone=max(r["friction_cone_violation"] for r in rows) <= 1e-9,
            length=max(r["max_length_error"] for r in rows) <= 0.01,
            penetration=min(r["min_gap"] for r in rows) >= -0.001,
            finite=not any(r["nonfinite"] for r in rows),
        )
        slip = None
        for k in range(len(rows) - 4):
            if all(
                r["cylinder_tangent_speed"] > 0.001 and (mu == 0 or r["cylinder_saturated"] > 0)
                for r in rows[k : k + 5]
            ):
                slip = k + 1
                break
        report[name] = {
            "checks": checks,
            "pass": all(checks.values()),
            "final": final,
            "slip_frame": slip,
            "initial_tangent_speed": float(
                np.mean([r["cylinder_tangent_speed"] for r in rows[: round(0.5 * fps)]])
            ),
        }
        print(name, json.dumps(report[name]), flush=True)
        s.close()
    report["T3"]["checks"]["initial_resistance"] = (
        report["T3"]["initial_tangent_speed"] < report["T3_mu0"]["initial_tangent_speed"]
    )
    report["T3"]["checks"]["slip_delayed"] = (
        report["T3"]["slip_frame"] is not None
        and report["T3_mu0"]["slip_frame"] is not None
        and report["T3"]["slip_frame"] > report["T3_mu0"]["slip_frame"]
    )
    report["T3"]["checks"]["starts_from_passing_T2"] = report["T2"]["pass"]
    report["T3"]["pass"] = all(report["T3"]["checks"].values())
    report["pass"] = all(report[t]["pass"] for t in ["T1", "T2", "T3"])
    (output / "report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default=str(ROOT / "outputs/protocols"))
    ap.add_argument("--fps", type=int, default=240)
    args = ap.parse_args()
    run(args.output, args.fps)
