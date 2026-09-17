import bpy, importlib, json, hashlib
from pathlib import Path
import numpy as np
addon = importlib.import_module('bl_ext.user_default.kami4_bvh_hair_solver.addon')
native = importlib.import_module('bl_ext.user_default.kami4_bvh_hair_solver.native')
cache = importlib.import_module('bl_ext.user_default.kami4_bvh_hair_solver.cache')
assert addon.replay_handler in bpy.app.handlers.frame_change_post
assert addon.load_handler in bpy.app.handlers.load_post
assert 'aces_parameters' in bpy.context.scene.kami4_bvh
assert not addon._runtime
native.Solver = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('No simulation allowed'))
s = bpy.context.scene.kami4_bvh
d = Path(bpy.path.abspath(s.cache_directory))
m = cache.load(d)
assert addon.get_parameters(s) == m['parameters']
assert native.parameter_hash(addon.get_parameters(s)) == m['parameter_hash']
assert m['binary_hash'] == hashlib.sha256((native.ROOT / 'bin/kami4_hair_core_bvh1.dll').read_bytes()).hexdigest()
for frame in (1, 23, 102, 164, 200):
    bpy.context.scene.frame_set(frame)
    # Verify the real registered handler replayed the cache; do not call it manually.
    assert not s.last_error, s.last_error
    actual = np.empty((len(s.output.data.points), 3), np.float32)
    s.output.data.attributes['position'].data.foreach_get('vector', actual.ravel())
    expected = cache.read(d, frame, m['topology_hash'], m['parameter_hash'], m['points'])
    np.testing.assert_array_equal(actual * bpy.context.scene.unit_settings.scale_length, expected)
result = dict(startup_registration_pass=True, automatic_replay_pass=True, frames=[1, 23, 102, 164, 200],
              solver_executed=False, parameter_hash=m['parameter_hash'], binary_hash=m['binary_hash'])
(d.parent / 'portable_verification.json').write_text(json.dumps(result, indent=2), encoding='utf8')
print('PORTABLE_TRIAL2_OK', json.dumps(result), flush=True)
