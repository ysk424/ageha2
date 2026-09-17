"""All Blender reads/writes execute on the main thread, including modal Bake."""

from pathlib import Path
import json, time, hashlib
import numpy as np
import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix
from . import native, cache

_runtime = {}
_busy = False


def hair_positions(obj, scene):
    if obj is None or obj.type != "CURVES":
        raise ValueError("入力する髪に Hair Curves を指定してください")
    was_hidden, was_disabled = obj.hide_get(), obj.hide_viewport
    try:
        obj.hide_viewport = False
        obj.hide_set(False)
        bpy.context.view_layer.update()
        ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
        data = ev.data
        p = np.empty((len(data.points), 3), np.float32)
        data.attributes["position"].data.foreach_get("vector", p.ravel())
        m = np.array(ev.matrix_world)
        sizes = np.array([c.points_length for c in data.curves], np.uint32)
        return native.array((p @ m[:3, :3].T + m[:3, 3]) * scene.unit_settings.scale_length), np.r_[
            np.uint32(0), np.cumsum(sizes, dtype=np.uint32)
        ]
    finally:
        obj.hide_viewport = was_disabled
        obj.hide_set(was_hidden)


def mesh_objects(settings):
    objects = {}
    if settings.collider:
        objects[settings.collider.name] = settings.collider
    if settings.collider_collection:
        for obj in settings.collider_collection.all_objects:
            if obj.type == "MESH" and "kami4_type" not in obj:
                objects[obj.name] = obj
    return [objects[k] for k in sorted(objects)]


def mesh_positions(settings, scene, triangulate=True):
    vertices = []
    triangles = []
    hashes = []
    base = 0
    for obj in mesh_objects(settings):
        deps = bpy.context.evaluated_depsgraph_get()
        ev = obj.evaluated_get(deps)
        data = ev.to_mesh(preserve_all_data_layers=False, depsgraph=deps)
        try:
            p = np.empty((len(data.vertices), 3), np.float32)
            data.vertices.foreach_get("co", p.ravel())
            m = np.array(ev.matrix_world)
            vertices.append(
                native.array((p @ m[:3, :3].T + m[:3, 3]) * scene.unit_settings.scale_length)
            )
            loops = np.empty(len(data.loops), np.uint32)
            data.loops.foreach_get("vertex_index", loops)
            hashes.append((obj.name, len(p), hashlib.sha256(loops.tobytes()).hexdigest()))
            if triangulate:
                data.calc_loop_triangles()
                t = np.empty((len(data.loop_triangles), 3), np.uint32)
                data.loop_triangles.foreach_get("vertices", t.ravel())
                triangles.append(t + base)
            base += len(p)
        finally:
            ev.to_mesh_clear()
    return (
        np.concatenate(vertices) if vertices else None,
        np.concatenate(triangles) if triangles else None,
        hashes,
    )


def analytic_colliders(settings, scene):
    out = []
    if settings.collider_collection:
        for obj in sorted(settings.collider_collection.all_objects, key=lambda x: x.name):
            if "kami4_type" not in obj:
                continue
            m = obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world
            sc = np.abs(m.to_scale())
            unit = scene.unit_settings.scale_length
            if max(sc) - min(sc) > 1e-5:
                raise ValueError(f"{obj.name}: 解析コライダーの非均一スケールを適用してください")
            out.append(
                native.Collider(
                    int(obj["kami4_type"]),
                    len(out),
                    m.translation * unit,
                    m.to_quaternion(),
                    obj.get("kami4_radius", 0.1) * sc[0] * unit,
                    obj.get("kami4_half_length", 0) * sc[0] * unit,
                    obj.get("kami4_friction", native.parameters()["friction"]),
                )
            )
    return out


def update_output(obj, x, scene):
    if len(obj.data.points) != len(x):
        raise ValueError("結果の点数が変わりました。初期化してください")
    obj.matrix_world = Matrix.Identity(4)
    obj.data.attributes["position"].data.foreach_set(
        "vector", native.array(x / scene.unit_settings.scale_length).ravel()
    )
    obj.data.update_tag()


def output_object(settings, scene, x, offsets):
    obj = settings.output
    if obj is None or obj.get("kami4_owned") != True or len(obj.data.points) != len(x):
        data = bpy.data.hair_curves.new("Kami4_Result")
        data.add_curves(np.diff(offsets).tolist())
        for mat in settings.source.data.materials:
            data.materials.append(mat)
        if len(settings.source.data.points) == len(x):
            try:
                radius = np.empty(len(x), np.float32)
                settings.source.data.points.foreach_get("radius", radius)
                data.points.foreach_set("radius", radius)
            except (TypeError, AttributeError):
                pass
        obj = bpy.data.objects.new("Kami4_髪_計算結果", data)
        scene.collection.objects.link(obj)
        obj["kami4_owned"] = True
        settings.output = obj
    update_output(obj, x, scene)
    return obj


def get_parameters(settings):
    return native.parameters(
        bpy.path.abspath(settings.parameter_file) if settings.parameter_file else None
    )


def initialize(scene, clear_cache=True):
    global _busy
    settings = scene.kami4
    settings.replay = False
    _busy = True
    try:
        old = _runtime.pop(scene.as_pointer(), None)
        if old:
            old["solver"].close()
        scene.frame_set(settings.frame_start)
        p, offsets = hair_positions(settings.source, scene)
        fixed = np.zeros(len(p), np.uint8)
        for index in offsets[:-1]:
            fixed[index : index + settings.root_points] = 1
        params = get_parameters(settings)
        cols = analytic_colliders(settings, scene)
        solver = native.Solver(
            p,
            offsets,
            fixed,
            params,
            scene.render.fps_base / scene.render.fps,
            gravity=(0, 0, -1),
            max_colliders=len(cols),
        )
        vertices, triangles, sig = mesh_positions(settings, scene)
        cols = analytic_colliders(settings, scene)
        if vertices is not None:
            solver.set_mesh(vertices, triangles)
        solver.prepare(len(cols))
        output = output_object(settings, scene, solver.x, offsets)
        if not settings.cache_directory:
            parent = Path(bpy.path.abspath("//")) if bpy.data.filepath else Path.home()
            settings.cache_directory = str(parent / "kami4_cache" / time.strftime("%Y%m%d_%H%M%S"))
        directory = Path(bpy.path.abspath(settings.cache_directory))
        manifest = cache.create(
            directory,
            solver.x,
            offsets,
            params,
            native.parameter_hash(params),
            preserve_frames=not clear_cache,
            source=settings.source.name,
            collider=settings.collider.name if settings.collider else None,
            blender=bpy.app.version_string,
            binary_hash=hashlib.sha256(
                (native.ROOT / "bin/kami4_hair_core.dll").read_bytes()
            ).hexdigest(),
            repaired_strands=solver.repaired,
            fps=scene.render.fps / scene.render.fps_base,
        )
        if clear_cache:
            manifest["frames"] = []
            cache.save_manifest(directory, manifest)
            (directory / "stats.jsonl").write_text("", encoding="utf8")
        output["kami4_topology_hash"] = manifest["topology_hash"]
        output["kami4_parameter_hash"] = manifest["parameter_hash"]
        _runtime[scene.as_pointer()] = dict(
            solver=solver,
            offsets=offsets,
            vertices=vertices,
            signature=sig,
            colliders=cols,
            directory=directory,
            manifest=manifest,
            next_frame=settings.frame_start,
            stats=[],
        )
        settings.status = f"初期化済み {len(offsets) - 1:,}本 / {len(p):,}点 / CUDA"
        settings.last_error = ""
        return _runtime[scene.as_pointer()]
    finally:
        _busy = False


def simulate_frame(scene):
    global _busy
    settings = scene.kami4
    r = _runtime.get(scene.as_pointer()) or initialize(scene)
    frame = r["next_frame"]
    if frame > settings.frame_end:
        return False
    _busy = True
    try:
        began = time.perf_counter()
        scene.frame_set(frame)
        p, offsets = hair_positions(settings.source, scene)
        if not np.array_equal(offsets, r["offsets"]):
            raise ValueError("髪のトポロジーが変化しました")
        vertices, _, sig = mesh_positions(settings, scene, False)
        if sig != r["signature"]:
            raise ValueError("コライダーのトポロジーが変化しました")
        cols = analytic_colliders(settings, scene)
        st = r["solver"].step(p, cols, r["colliders"], r["vertices"], vertices)
        update_output(settings.output, r["solver"].x, scene)
        cache.write(r["directory"], frame, r["solver"].x, r["manifest"])
        st.update(frame=frame, total_ms=(time.perf_counter() - began) * 1000)
        r["stats"].append(st)
        r["vertices"] = vertices
        r["colliders"] = cols
        r["next_frame"] += 1
        with (r["directory"] / "stats.jsonl").open("a", encoding="utf8") as f:
            f.write(json.dumps(st) + "\n")
        cache.save_manifest(r["directory"], r["manifest"])
        settings.status = f"{frame}/{settings.frame_end}F 完了 / GPU {st['native_ms']:.1f} ms"
        settings.diagnostics = f"長さ最大 {st['max_length_error']:.2%} / p99 {st['p99_length_error']:.2%} / 移動上限超過 {st['motion_violations']}"
        return True
    finally:
        _busy = False


@persistent
def replay_handler(scene, *args):
    if _busy or not hasattr(scene, "kami4"):
        return
    s = scene.kami4
    if not s.replay or not s.output or not s.cache_directory:
        return
    try:
        directory = Path(bpy.path.abspath(s.cache_directory))
        m = cache.load(directory)
        if scene.frame_current not in m["frames"]:
            return
        current = native.parameter_hash(get_parameters(s))
        if current != m["parameter_hash"]:
            raise ValueError("再生パラメータがキャッシュと一致しません")
        x = cache.read(
            directory,
            scene.frame_current,
            s.output.get("kami4_topology_hash", ""),
            current,
            len(s.output.data.points),
        )
        update_output(s.output, x, scene)
        s.status = f"キャッシュ再生 {scene.frame_current}F"
        s.last_error = ""
    except Exception as exc:
        s.last_error = str(exc)


@persistent
def load_handler(*args):
    for r in list(_runtime.values()):
        r["solver"].close()
    _runtime.clear()


class K4Settings(bpy.types.PropertyGroup):
    source: bpy.props.PointerProperty(
        name="入力する髪", type=bpy.types.Object, poll=lambda s, o: o.type == "CURVES"
    )
    collider: bpy.props.PointerProperty(
        name="衝突メッシュ", type=bpy.types.Object, poll=lambda s, o: o.type == "MESH"
    )
    collider_collection: bpy.props.PointerProperty(name="追加コライダー", type=bpy.types.Collection)
    output: bpy.props.PointerProperty(name="計算結果", type=bpy.types.Object)
    parameter_file: bpy.props.StringProperty(name="共通パラメータ JSON", subtype="FILE_PATH")
    cache_directory: bpy.props.StringProperty(name="Kami4 キャッシュ", subtype="DIR_PATH")
    frame_start: bpy.props.IntProperty(name="開始", default=1, min=1)
    frame_end: bpy.props.IntProperty(name="終了", default=200, min=1)
    root_points: bpy.props.IntProperty(name="固定する根元点数", default=1, min=1, max=2)
    replay: bpy.props.BoolProperty(name="キャッシュを再生", default=False)
    status: bpy.props.StringProperty(default="未初期化")
    diagnostics: bpy.props.StringProperty()
    last_error: bpy.props.StringProperty()


class K4Initialize(bpy.types.Operator):
    bl_idname = "kami4.initialize"
    bl_label = "Initialize / 初期化"

    def execute(self, context):
        try:
            initialize(context.scene)
            return {"FINISHED"}
        except Exception as exc:
            context.scene.kami4.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class K4Simulate(bpy.types.Operator):
    bl_idname = "kami4.simulate"
    bl_label = "Simulate / 1フレーム計算"

    def execute(self, context):
        try:
            simulate_frame(context.scene)
            return {"FINISHED"}
        except Exception as exc:
            context.scene.kami4.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class K4Reset(bpy.types.Operator):
    bl_idname = "kami4.reset"
    bl_label = "Reset / 開始形状へ"

    def execute(self, context):
        try:
            initialize(context.scene, clear_cache=False)
            return {"FINISHED"}
        except Exception as exc:
            context.scene.kami4.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class K4Bake(bpy.types.Operator):
    bl_idname = "kami4.bake"
    bl_label = "Bake / 全フレーム計算"
    _timer = None

    def finish(self, context, cancel=False):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.scene.kami4.replay = True
        return {"CANCELLED"} if cancel else {"FINISHED"}

    def execute(self, context):
        try:
            initialize(context.scene)
            if bpy.app.background:
                while simulate_frame(context.scene):
                    pass
                context.scene.kami4.replay = True
                return {"FINISHED"}
            self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            context.scene.kami4.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

    def modal(self, context, event):
        if event.type == "ESC":
            return self.finish(context, True)
        if event.type == "TIMER":
            try:
                if not simulate_frame(context.scene):
                    return self.finish(context)
                for area in context.screen.areas:
                    area.tag_redraw()
            except Exception as exc:
                context.scene.kami4.last_error = str(exc)
                self.report({"ERROR"}, str(exc))
                return self.finish(context, True)
        return {"PASS_THROUGH"}


class K4Replay(bpy.types.Operator):
    bl_idname = "kami4.replay"
    bl_label = "Replay / キャッシュ再生"

    def execute(self, context):
        context.scene.kami4.replay = True
        replay_handler(context.scene)
        return {"FINISHED"}


class K4Panel(bpy.types.Panel):
    bl_label = "Kami4 Hair Solver"
    bl_idname = "KAMI4_PT_solver"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Kami4"

    def draw(self, context):
        layout = self.layout
        s = context.scene.kami4
        for name in (
            "source",
            "collider",
            "collider_collection",
            "parameter_file",
            "cache_directory",
        ):
            layout.prop(s, name)
        row = layout.row(align=True)
        row.prop(s, "frame_start")
        row.prop(s, "frame_end")
        layout.prop(s, "root_points")
        row = layout.row(align=True)
        row.operator("kami4.initialize")
        row.operator("kami4.reset")
        layout.operator("kami4.simulate")
        layout.operator("kami4.bake")
        layout.operator("kami4.replay")
        layout.prop(s, "replay")
        layout.label(text=s.status)
        layout.label(text=s.diagnostics)
        if s.last_error:
            layout.label(text=s.last_error, icon="ERROR")


classes = (K4Settings, K4Initialize, K4Simulate, K4Reset, K4Bake, K4Replay, K4Panel)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kami4 = bpy.props.PointerProperty(type=K4Settings)
    if replay_handler not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(replay_handler)
    if load_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(load_handler)


def unregister():
    load_handler()
    for seq, fn in (
        (bpy.app.handlers.frame_change_post, replay_handler),
        (bpy.app.handlers.load_post, load_handler),
    ):
        if fn in seq:
            seq.remove(fn)
    if hasattr(bpy.types.Scene, "kami4"):
        del bpy.types.Scene.kami4
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
