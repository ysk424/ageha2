"""Versioned K4 caches: topology/parameter hashes and CRC checked on every read."""

from pathlib import Path
import hashlib, json, struct, zlib, os
import numpy as np

HEADER = struct.Struct("<4sIII32s32sI")


def topology_hash(positions, offsets):
    return hashlib.sha256(
        np.asarray(offsets, dtype="<u4").tobytes() + np.asarray(positions, dtype="<f4").tobytes()
    ).hexdigest()


def create(
    directory, positions, offsets, parameters, parameter_hash, preserve_frames=False, **extra
):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    manifest = dict(
        schema=1,
        points=len(positions),
        strands=len(offsets) - 1,
        topology_hash=topology_hash(positions, offsets),
        parameter_hash=parameter_hash,
        parameters=parameters,
        frames=[],
        **extra,
    )
    if (directory / "manifest.json").exists():
        old = load(directory)
        if (
            old["topology_hash"] != manifest["topology_hash"]
            or old["parameter_hash"] != parameter_hash
        ):
            raise ValueError(
                "Cache directory belongs to different input/parameters; select a new directory"
            )
        if preserve_frames:
            return old
    np.save(directory / "offsets.npy", offsets)
    save_manifest(directory, manifest)
    return manifest


def save_manifest(directory, manifest):
    path = Path(directory) / "manifest.json"
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf8")
    os.replace(tmp, path)


def load(directory):
    return json.loads((Path(directory) / "manifest.json").read_text(encoding="utf8"))


def write(directory, frame, positions, manifest):
    raw = np.asarray(positions, dtype="<f4").tobytes()
    head = HEADER.pack(
        b"K4C1",
        1,
        frame,
        len(positions),
        bytes.fromhex(manifest["topology_hash"]),
        bytes.fromhex(manifest["parameter_hash"]),
        zlib.crc32(raw),
    )
    path = Path(directory) / f"frame_{frame:06d}.k4c"
    tmp = path.with_suffix(".k4c.tmp")
    tmp.write_bytes(head + raw)
    os.replace(tmp, path)
    if frame not in manifest["frames"]:
        manifest["frames"].append(frame)


def read(directory, frame, topology, parameter, points):
    data = (Path(directory) / f"frame_{frame:06d}.k4c").read_bytes()
    if len(data) < HEADER.size:
        raise ValueError("Truncated K4 cache header")
    magic, schema, f, n, t, p, crc = HEADER.unpack_from(data)
    raw = data[HEADER.size :]
    if (magic, schema, f, n) != (b"K4C1", 1, frame, points):
        raise ValueError("K4 cache frame/schema/count mismatch")
    if t.hex() != topology or p.hex() != parameter:
        raise ValueError("K4 cache topology/parameter mismatch")
    if len(raw) != points * 12 or zlib.crc32(raw) != crc:
        raise ValueError("K4 cache CRC/size mismatch")
    return np.frombuffer(raw, dtype="<f4").reshape(points, 3).copy()
