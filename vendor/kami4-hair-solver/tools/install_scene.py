"""Run on port 9876. Attach the verified cache and save ONLY under a new name."""

import bpy, importlib, json, hashlib
from pathlib import Path
import numpy as np

ROOT = Path("C:/Users/azoo/git/kami4-hair-solver")
module_name = "bl_ext.user_default.kami4_hair_solver"
if module_name not in bpy.context.preferences.addons:
    status = bpy.ops.extensions.package_install_files(
        filepath=str(ROOT / "dist/kami4_hair_solver-0.1.0-windows-x64.zip"),
        repo="user_default",
        enable_on_install=True,
    )
    if "FINISHED" not in status:
        raise RuntimeError(str(status))
addon = importlib.import_module(module_name + ".addon")
cache = importlib.import_module(module_name + ".cache")
native = importlib.import_module(module_name + ".native")
scene = bpy.context.scene
legacy = scene.kami_hair
s = scene.kami4
expected = json.loads((ROOT / "initial_scene.json").read_text(encoding="utf8"))["result"]
assert legacy.hair.name == expected["settings"]["kami_hair"]["hair"]
assert legacy.collider.name == expected["settings"]["kami_hair"]["collider"]
s.source = legacy.hair
s.collider = legacy.collider
s.frame_start = 1
s.frame_end = 200
s.root_points = 1
s.parameter_file = str(ROOT / "extension/parameters.json")
s.cache_directory = str(ROOT / "outputs/real_final")
s.replay = False
m = cache.load(s.cache_directory)
offsets = np.load(ROOT / "outputs/input/offsets.npy")
positions = cache.read(s.cache_directory, 1, m["topology_hash"], m["parameter_hash"], m["points"])
output = addon.output_object(s, scene, positions, offsets)
output["kami4_topology_hash"] = m["topology_hash"]
output["kami4_parameter_hash"] = m["parameter_hash"]
output["kami4_cache_directory"] = s.cache_directory
output["kami4_source"] = s.source.name
output["kami4_collider"] = s.collider.name
output["kami4_acceptance"] = (
    "200 CUDA frames complete; research acceptance FAIL: motion bound and isolated mesh node penetration. See RESULTS_JA.md."
)
if legacy.result:
    legacy.result.hide_set(True)
    legacy.result.hide_render = True
    if "髪キャッシュ" in legacy.result:
        legacy.result["kami4_preserved_legacy_cache"] = legacy.result["髪キャッシュ"]
        del legacy.result["髪キャッシュ"]
s.source.hide_set(True)
s.source.hide_render = True
output.hide_set(False)
output.hide_render = False
s.replay = True
scene.frame_start = 1
scene.frame_end = 200
scene.use_preview_range = False
scene.frame_set(1)
addon.replay_handler(scene)
for o in bpy.context.selected_objects:
    o.select_set(False)
output.select_set(True)
bpy.context.view_layer.objects.active = output
txt = bpy.data.texts.get("KAMI4_README") or bpy.data.texts.new("KAMI4_README")
txt.clear()
txt.write(
    "Kami4 Hair Solver\n\n入力は元の kami-hair-solver と同じ「カーブ」「CC_Base_Body」です。\n元の髪を編集せず、結果オブジェクトにCUDA計算を表示しています。\n1～200Fを計算済み。Kami4パネルのReplayを有効にするとキャッシュ再生します。\n\n仕様の全受入条件を満たした認定版ではありません。\n元アニメーションの毛根移動は、最大8substepsでも移動上限を超えます。\n離散メッシュ接触に一部約0.032mmの侵入が残りました。\n\nレポート: "
    + str(ROOT / "docs/RESULTS_JA.md")
    + "\nパラメータ: "
    + s.parameter_file
    + "\nキャッシュ: "
    + s.cache_directory
    + "\n"
)
s.status = "200F 計算済み / キャッシュ再生"
s.diagnostics = "長さ基準内 / 移動上限・一部接触基準は未達"
s.last_error = ""
destination = ROOT / "outputs/kami4_current_scene.blend"
assert destination.resolve() != Path(expected["file"]).resolve()
bpy.ops.wm.save_as_mainfile(filepath=str(destination))
bpy.ops.wm.save_userpref()
result = dict(
    blend=bpy.data.filepath,
    source=s.source.name,
    collider=s.collider.name,
    output=output.name,
    cache=s.cache_directory,
    frames=len(m["frames"]),
    extension=module_name,
    original=expected["file"],
)
(ROOT / "outputs/installed_scene.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2), encoding="utf8"
)
