import bpy
from pathlib import Path

root = Path("C:/Users/azoo/git/kami4-hair-solver/outputs")
destination = root / "input_snapshot.blend"
if destination.exists():
    raise RuntimeError("Snapshot already exists; refusing to overwrite")
bpy.ops.wm.save_as_mainfile(filepath=str(destination), copy=True)
result = dict(snapshot=str(destination), original=bpy.data.filepath, binary=bpy.app.binary_path)
