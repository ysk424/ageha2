"""Attach the review cache beside the preserved baseline extension; save under a new name."""
import bpy,importlib,json,hashlib
from pathlib import Path
import numpy as np
ROOT=Path('C:/Users/azoo/git/kami4-bvh-experiment')
RUN=ROOT/'outputs/review_bvh_extension_200'
scene=bpy.context.scene
before=dict(filepath=bpy.data.filepath,frame=scene.frame_current)
bpy.ops.wm.save_as_mainfile(filepath=str(RUN/'before_review.blend'),copy=True)
module='bl_ext.user_default.kami4_bvh_hair_solver'
if module not in bpy.context.preferences.addons:
    status=bpy.ops.extensions.package_install_files(filepath=str(ROOT/'dist/kami4_bvh_hair_solver-0.2.0-windows-x64.zip'),repo='user_default',enable_on_install=True)
    assert 'FINISHED' in status,status
addon=importlib.import_module(module+'.addon');native=importlib.import_module(module+'.native');cache=importlib.import_module(module+'.cache')
s=scene.kami4_bvh;old=scene.kami4
s.source=old.source;s.collider=old.collider;s.collider_collection=old.collider_collection
s.frame_start=1;s.frame_end=200;s.root_points=2;s.minimum_dynamic_length=.2;s.contact_passes=8;s.whole_strand_collision=True;s.preload_animation=True;s.replay=False
m=cache.load(RUN)
(RUN/'parameters.json').write_text(json.dumps(m['parameters'],indent=2),encoding='utf8')
s.parameter_file=str(RUN/'parameters.json');s.cache_directory=str(RUN)
assert native.parameter_hash(addon.get_parameters(s))==m['parameter_hash']
binary_hash=hashlib.sha256((native.ROOT/'bin/kami4_hair_core_bvh1.dll').read_bytes()).hexdigest()
assert binary_hash==m['binary_hash']
version=native.library().k4_version().decode()
x=cache.read(RUN,164,m['topology_hash'],m['parameter_hash'],m['points']);offsets=np.load(RUN/'offsets.npy')
out=addon.output_object(s,scene,x,offsets)
out['kami4_topology_hash']=m['topology_hash'];out['kami4_parameter_hash']=m['parameter_hash'];out['kami4_review']='BVH + invisible extension; remaining late-frame crossings, review before adoption'
if old.output:old.output.hide_set(True);old.output.hide_render=True
out.hide_set(False);out.hide_render=False
s.replay=True;scene.frame_set(164);addon.replay_handler(scene)
for obj in bpy.context.selected_objects:obj.select_set(False)
out.select_set(True);bpy.context.view_layer.objects.active=out
for window in bpy.context.window_manager.windows:
    for area in window.screen.areas:
        if area.type=='VIEW_3D':area.spaces.active.region_3d.view_perspective='PERSP'
s.status='確認用 / 200F 計算済み';s.diagnostics='23Fの交差0 / 後半には残りあり';s.last_error=''
bpy.ops.wm.save_as_mainfile(filepath=str(RUN/'kami4_bvh_extension_review.blend'))
bpy.ops.wm.save_userpref()
result=dict(before=before,blend=bpy.data.filepath,frame=scene.frame_current,output=out.name,source=s.source.name,collider=s.collider.name,binary_hash=binary_hash,loaded_version=version,parameter_hash=m['parameter_hash'])
(RUN/'installed_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
