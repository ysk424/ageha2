import bpy, json, importlib, hashlib
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
module = "bl_ext.user_default.kami4_hair_solver"
addon = importlib.import_module(module + ".addon")
cache = importlib.import_module(module + ".cache")
native = importlib.import_module(module + ".native")
scene = bpy.context.scene
s = scene.kami4
directory = Path(bpy.path.abspath(s.cache_directory))
m = cache.load(directory)
assert s.source.name == "カーブ" and s.collider.name == "CC_Base_Body"
assert len(m["frames"]) == 200
hashes = []
for frame in range(1, 201):
    x = cache.read(directory, frame, m["topology_hash"], m["parameter_hash"], m["points"])
    assert np.isfinite(x).all()
    hashes.append(hashlib.sha256(x.tobytes()).hexdigest())
samples = []
for frame in (1, 7, 100, 200, 1):
    scene.frame_set(frame)
    addon.replay_handler(scene)
    assert not s.last_error, s.last_error
    x = np.empty((len(s.output.data.points), 3), np.float32)
    s.output.data.attributes["position"].data.foreach_get("vector", x.ravel())
    expected = cache.read(directory, frame, m["topology_hash"], m["parameter_hash"], m["points"])
    np.testing.assert_array_equal(x, expected)
    samples.append(frame)
report = dict(
    pass_=True,
    verified_crc_frames=200,
    blender_replay_samples=samples,
    source=s.source.name,
    collider=s.collider.name,
    blender=bpy.app.version_string,
    parameter_hash=m["parameter_hash"],
    frame_hashes=hashes,
)
(ROOT / "outputs/restart_replay.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8"
)
print("K4_RESTART_REPLAY_OK", flush=True)
