import bpy
from pathlib import Path
ROOT=Path('C:/Users/azoo/git/kami4-bvh-experiment/outputs/review_bvh_extension_200')
scene=bpy.context.scene;win=bpy.context.window_manager.windows[0];area=next(a for a in win.screen.areas if a.type=='VIEW_3D');region=next(r for r in area.regions if r.type=='WINDOW')
old=scene.kami4.output;new=scene.kami4_bvh.output
settings=(scene.frame_current,scene.render.filepath,scene.render.resolution_x,scene.render.resolution_y,scene.render.resolution_percentage,scene.render.image_settings.media_type,scene.render.image_settings.file_format)
paths=[]
try:
    scene.render.resolution_x=1280;scene.render.resolution_y=960;scene.render.resolution_percentage=100;scene.render.image_settings.media_type='IMAGE';scene.render.image_settings.file_format='PNG'
    scene.frame_set(164)
    for label in ['baseline','bvh_extension']:
        old.hide_set(label!='baseline');new.hide_set(label=='baseline')
        bpy.context.view_layer.update();path=ROOT/(label+'_164.png');scene.render.filepath=str(path)
        with bpy.context.temp_override(window=win,area=area,region=region):bpy.ops.render.opengl(write_still=True,view_context=True)
        paths.append(str(path))
finally:
    old.hide_set(True);new.hide_set(False)
    scene.frame_set(settings[0]);scene.render.filepath=settings[1];scene.render.resolution_x=settings[2];scene.render.resolution_y=settings[3];scene.render.resolution_percentage=settings[4];scene.render.image_settings.media_type=settings[5];scene.render.image_settings.file_format=settings[6]
result=dict(images=paths)
