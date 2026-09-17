import sys, json, time, hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "extension"))
from native import Solver, parameters, parameter_hash, Collider

p = parameters()
rows = []
for size in (8, 16, 32, 64, 128, 256):
    strands = 100000 // size
    count = strands * size
    off = np.arange(strands + 1, dtype=np.uint32) * size
    j = np.tile(np.arange(size), strands)
    ids = np.repeat(np.arange(strands), size)
    x = np.c_[(ids % 100) * 0.02, (ids // 100) * 0.02, 2 - j * 0.005].astype(np.float32)
    fixed = np.zeros(count, np.uint8)
    fixed[off[:-1]] = 1
    s = Solver(x, off, fixed, p, max_colliders=1)
    cols = [Collider(0, 0, friction=0)]
    native = []
    total = []
    for f in range(80):
        start = time.perf_counter()
        st = s.step(x, cols)
        if f >= 20:
            native.append(st["native_ms"])
            total.append((time.perf_counter() - start) * 1000)
    rows.append(
        dict(
            bucket_points=size,
            points=count,
            strands=strands,
            backend="1 thread/strand"
            if size <= 32
            else "block affine prefix + parallel cyclic reduction",
            threads_per_strand=1 if size <= 32 else size,
            native_ms=float(np.median(native)),
            transfer_ms=float(np.median(total)),
            launches=st["launches"],
            nonfinite=st["nonfinite"],
        )
    )
    s.close()
report = dict(
    parameter_hash=parameter_hash(p),
    binary_hash=hashlib.sha256(
        (ROOT / "extension/bin/kami4_hair_core.dll").read_bytes()
    ).hexdigest(),
    warmup=20,
    measured=60,
    buckets=rows,
)
(ROOT / "outputs/bucket_profile.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
