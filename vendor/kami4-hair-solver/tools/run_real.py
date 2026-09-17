import sys, json, time, argparse, hashlib, traceback
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))
from native import Solver, parameters, parameter_hash
import cache


def run(name="real_mesh", frames=200, mesh=True):
    inp = ROOT / "outputs/input"
    out = ROOT / "outputs" / name
    out.mkdir(parents=True, exist_ok=True)
    meta = json.loads((inp / "manifest.json").read_text(encoding="utf8"))
    p = parameters()
    x = np.load(inp / "positions.npy")
    off = np.load(inp / "offsets.npy")
    targets = np.load(inp / "targets.npy", mmap_mode="r")
    verts = np.load(inp / "vertices.npy", mmap_mode="r")
    tri = np.load(inp / "triangles.npy")
    fixed = np.zeros(len(x), np.uint8)
    fixed[off[:-1]] = 1
    s = Solver(x, off, fixed, p, dt=1 / meta["fps"], max_colliders=0)
    if mesh:
        s.set_mesh(verts[0], tri)
    manifest = cache.create(
        out,
        x,
        off,
        p,
        parameter_hash(p),
        input=meta,
        binary_hash=hashlib.sha256(
            (ROOT / "extension/bin/kami4_hair_core.dll").read_bytes()
        ).hexdigest(),
        backend="CUDA",
        mesh=mesh,
    )
    (out / "stats.jsonl").write_text("", encoding="utf8")
    rows = []
    begin = time.perf_counter()
    failure = None
    try:
        for f in range(frames):
            start = time.perf_counter()
            st = s.step(
                targets[f],
                mesh_previous=verts[max(0, f - 1)] if mesh else None,
                mesh_next=verts[f] if mesh else None,
            )
            st.update(frame=f + 1, total_ms=(time.perf_counter() - start) * 1000)
            cache.write(out, f + 1, s.x, manifest)
            rows.append(st)
            with (out / "stats.jsonl").open("a") as file:
                file.write(json.dumps(st) + "\n")
            if f % 10 == 0 or f == frames - 1:
                cache.save_manifest(out, manifest)
                print(name, f + 1, json.dumps(st), flush=True)
    except Exception as exc:
        failure = {"frame": len(rows) + 1, "error": str(exc), "traceback": traceback.format_exc()}
        (out / "failure.json").write_text(json.dumps(failure, indent=2))
        print(failure, flush=True)
    cache.save_manifest(out, manifest)
    report = dict(
        frames=len(rows),
        requested_frames=frames,
        seconds=time.perf_counter() - begin,
        parameter_hash=parameter_hash(p),
        failure=failure,
    )
    if rows:
        for name in (
            "max_length_error",
            "p99_length_error",
            "max_displacement",
            "friction_cone_violation",
        ):
            report[name] = max(r[name] for r in rows)
        report.update(
            min_gap=min(r["min_gap"] for r in rows),
            motion_violations=sum(r["motion_violations"] for r in rows),
            native_ms_median=float(np.median([r["native_ms"] for r in rows])),
            total_ms_median=float(np.median([r["total_ms"] for r in rows])),
        )
        report["checks"] = dict(
            completed=len(rows) == frames,
            length=report["max_length_error"] <= 0.02,
            p99=report["p99_length_error"] <= 0.005,
            penetration=report["min_gap"] >= -0.25 * p["guide_radius"],
            motion=report["motion_violations"] == 0,
            finite=not any(r["nonfinite"] or r["overflow"] for r in rows),
        )
        report["pass"] = all(report["checks"].values())
    (out / "report.json").write_text(json.dumps(report, indent=2))
    np.savez(out / "final_state.npz", x=s.x, v=s.v)
    s.close()
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="real_mesh")
    ap.add_argument("--frames", type=int, default=200)
    ap.add_argument("--no-mesh", action="store_true")
    a = ap.parse_args()
    run(a.name, a.frames, not a.no_mesh)
