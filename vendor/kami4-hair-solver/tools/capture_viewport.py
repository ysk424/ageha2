import bpy, json
from pathlib import Path

ROOT = Path("C:/Users/azoo/git/kami4-hair-solver")
scene = bpy.context.scene
window = bpy.context.window_manager.windows[0]
area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
region = next(r for r in area.regions if r.type == "WINDOW")
old = (
    scene.frame_current,
    scene.render.filepath,
    scene.render.resolution_x,
    scene.render.resolution_y,
    scene.render.resolution_percentage,
    scene.render.image_settings.file_format,
    scene.render.image_settings.media_type,
)
paths = []
try:
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 960
    scene.render.resolution_percentage = 100
    scene.render.image_settings.media_type = "IMAGE"
    scene.render.image_settings.file_format = "PNG"
    for frame in (1, 100, 200):
        scene.frame_set(frame)
        bpy.context.view_layer.update()
        path = ROOT / f"outputs/viewport_{frame:03d}.png"
        scene.render.filepath = str(path)
        with bpy.context.temp_override(window=window, area=area, region=region):
            bpy.ops.render.opengl(write_still=True, view_context=True)
        paths.append(str(path))
finally:
    scene.frame_set(old[0])
    scene.render.filepath = old[1]
    scene.render.resolution_x = old[2]
    scene.render.resolution_y = old[3]
    scene.render.resolution_percentage = old[4]
    scene.render.image_settings.media_type = old[6]
    scene.render.image_settings.file_format = old[5]
result = dict(images=paths)
