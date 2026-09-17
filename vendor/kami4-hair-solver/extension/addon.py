"""All Blender reads/writes execute on the main thread, including modal Bake."""

from pathlib import Path
import json, time, hashlib
import numpy as np
import bpy
from bpy.app.handlers import persistent
from mathutils import Matrix
from . import native, cache, panel_parameters

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
        obj = bpy.data.objects.new("Kami4_BVH_髪_計算結果", data)
        scene.collection.objects.link(obj)
        obj["kami4_owned"] = True
        settings.output = obj
    update_output(obj, x, scene)
    return obj


def get_parameters(settings):
    return panel_parameters.parameters(settings)


def initialize(scene, clear_cache=True, preload=False):
    global _busy
    settings = scene.kami4_bvh
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
        if preload and (cols or vertices is None):
            solver.close()
            raise ValueError('全範囲の入力準備はメッシュコライダーに対応しています')
        if not preload:
            solver.prepare(len(cols))
        output = output_object(settings, scene, solver.x, solver.offsets)
        if not settings.cache_directory:
            parent = Path(bpy.path.abspath("//")) if bpy.data.filepath else Path.home()
            settings.cache_directory = str(parent / "kami4_cache" / time.strftime("%Y%m%d_%H%M%S"))
        directory = Path(bpy.path.abspath(settings.cache_directory))
        manifest = cache.create(
            directory,
            solver.x,
            solver.offsets,
            params,
            native.parameter_hash(params),
            preserve_frames=not clear_cache,
            source=settings.source.name,
            collider=settings.collider.name if settings.collider else None,
            blender=bpy.app.version_string,
            binary_hash=hashlib.sha256(
                native.BINARY_PATH.read_bytes()
            ).hexdigest(),
            repaired_strands=solver.repaired,
            fps=scene.render.fps / scene.render.fps_base,
            root_points=settings.root_points,
            internal_points=len(solver.internal_x),
            extended_strands=len(solver.extended_strands),
            preload=preload,
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
            preload=preload, capture_index=0,
            capture_started=time.perf_counter(),
        )
        if preload:
            r = _runtime[scene.as_pointer()]
            frames = settings.frame_end - settings.frame_start + 1
            if frames <= 0:
                raise ValueError('終了フレームは開始フレーム以降にしてください')
            r['input_targets'] = np.empty((frames, len(p), 3), np.float32)
            r['input_vertices'] = np.empty((frames, len(vertices), 3), np.float32)
            r['input_triangles'] = triangles
            r['input_raw'] = p.copy()
        settings.status = f"初期化済み {len(offsets) - 1:,}本 / {len(p):,}点 / CUDA"
        settings.last_error = ""
        return _runtime[scene.as_pointer()]
    finally:
        _busy = False


def simulate_frame(scene):
    global _busy
    settings = scene.kami4_bvh
    r = _runtime.get(scene.as_pointer()) or initialize(scene)
    if native.parameter_hash(get_parameters(settings)) != r['manifest']['parameter_hash']:
        raise ValueError('設定が変わりました。新しいキャッシュ保存先で初期化してください')
    frame = r["next_frame"]
    if frame > settings.frame_end:
        return False
    _busy = True
    try:
        began = time.perf_counter()
        if r['preload'] and 'input_targets' in r:
            j = r['capture_index']
            scene.frame_set(settings.frame_start + j)
            p, offsets = hair_positions(settings.source, scene)
            vertices, _, sig = mesh_positions(settings, scene, False)
            if not np.array_equal(offsets,r['offsets']) or sig != r['signature']:
                raise ValueError('入力準備中にトポロジーが変化しました')
            r['input_targets'][j] = p
            r['input_vertices'][j] = vertices
            r['capture_index'] += 1
            count = len(r['input_targets'])
            settings.status = f'入力準備 {j+1}/{count}F'
            if j+1 == count:
                prepared = r['directory'] / 'prepared_input'
                prepared.mkdir(exist_ok=False)
                for key,name in [('input_targets','targets'),('input_vertices','vertices'),('input_triangles','triangles'),('input_raw','raw_positions')]:
                    np.save(prepared / (name+'.npy'),r[key])
                np.save(prepared/'offsets.npy',r['offsets'])
                r['solver'].set_animation(r['input_targets'],r['input_vertices'])
                r['solver'].prepare(0)
                r['input_seconds'] = time.perf_counter()-r['capture_started']
                r['manifest']['input_seconds'] = r['input_seconds']
                cache.save_manifest(r['directory'],r['manifest'])
                for key in ['input_targets','input_vertices','input_triangles','input_raw']:
                    del r[key]
                scene.frame_set(settings.frame_start)
                settings.status = '入力準備完了 / 全範囲を計算します'
            return True
        if r['preload']:
            st = r['solver'].step_animation(frame-settings.frame_start)
        else:
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
            r['vertices'],r['colliders'] = vertices,cols
        cache.write(r["directory"], frame, r["solver"].x, r["manifest"])
        st.update(frame=frame, total_ms=(time.perf_counter() - began) * 1000)
        r["stats"].append(st)
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
    if _busy or not hasattr(scene, "kami4_bvh"):
        return
    s = scene.kami4_bvh
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
    if hasattr(bpy.types.Scene, 'kami4_bvh'):
        for scene in bpy.data.scenes:
            panel_parameters.migrate(scene.kami4_bvh)


class K4BVHSettings(bpy.types.PropertyGroup):
    source: bpy.props.PointerProperty(
        name="入力する髪", type=bpy.types.Object, poll=lambda s, o: o.type == "CURVES"
    )
    collider: bpy.props.PointerProperty(
        name="衝突メッシュ", type=bpy.types.Object, poll=lambda s, o: o.type == "MESH"
    )
    collider_collection: bpy.props.PointerProperty(name="追加コライダー", type=bpy.types.Collection)
    output: bpy.props.PointerProperty(name="計算結果", type=bpy.types.Object)
    parameter_file: bpy.props.StringProperty(name="設定ファイル（JSON）", subtype="FILE_PATH")
    cache_directory: bpy.props.StringProperty(name="キャッシュ保存先", subtype="DIR_PATH")
    frame_start: bpy.props.IntProperty(name="開始", default=1, min=1)
    frame_end: bpy.props.IntProperty(name="終了", default=200, min=1)
    root_points: bpy.props.IntProperty(name="固定する根元点数", default=2, min=1, max=2)
    whole_strand_collision: bpy.props.BoolProperty(name='毛の全区間を衝突判定',default=True)
    local_fk_collision: bpy.props.BoolProperty(name='局所FKで貫通を修復',description='衝突した毛の近くに支点を探し、長さを保って毛先をつなぎ直します',default=False)
    minimum_dynamic_length: bpy.props.FloatProperty(name='シミュレーション用の最小長',description='短い毛に非表示の延長を加えます。元の表示長は変えません',default=0.2,min=0,max=1,unit='LENGTH')
    contact_passes: bpy.props.IntProperty(name='長さと接触の反復回数',default=8,min=2,max=32)
    preload_animation: bpy.props.BoolProperty(name='全範囲の入力を先に準備',description='身体と毛のアニメーションを先に評価してから計算します',default=True)
    bending_log10: panel_parameters.logarithm(
        'bending_rigidity', name='曲げ剛性（対数）',
        description='10の指数で調整します。−6は0.000001 N・m²。1増やすと剛性が10倍になります',
        min=-16, max=6, soft_min=-10, soft_max=-3, precision=3, step=10)
    regularization_log10: panel_parameters.logarithm(
        'length_regularization_relative', name='正則化（対数）',
        description='10の指数で調整します。−7は0.0000001。1増やすと値が10倍になります',
        min=-16, max=2, soft_min=-12, soft_max=-2, precision=3, step=10)
    density_g_per_m: panel_parameters.number(
        'linear_density', scale=1000, name='線密度（g/m）',
        description='毛の単位長さ当たりの質量', min=0.000001, max=10000, soft_max=1, precision=5)
    velocity_damping: panel_parameters.number(
        'damping', name='速度減衰（1/秒）', description='大きいほど揺れが早く収まります',
        min=0, max=10000, soft_max=30, precision=3)
    surface_friction: panel_parameters.number(
        'friction', name='摩擦係数', description='身体に触れた毛の滑りにくさ',
        min=0, max=100, soft_max=1, precision=3)
    gravity_acceleration: panel_parameters.number(
        'gravity', name='重力（m/秒²）', description='下向きの加速度',
        min=0, max=10000, soft_max=20, precision=5)
    collision_radius_mm: panel_parameters.number(
        'guide_radius', scale=1000, name='衝突半径（mm）',
        description='衝突判定上の毛の半径。描画の太さとは独立です',
        min=0.000001, max=10000, soft_max=1, precision=4)
    contact_margin_mm: panel_parameters.number(
        'contact_tolerance', scale=1000, name='接触マージン（mm）',
        description='区間接触で衝突半径に加える余裕距離',
        min=0, max=10000, soft_max=2, precision=4)
    minimum_length_cm: bpy.props.FloatProperty(
        name='最小計算長（cm）', description='短い毛に非表示の延長を加えます。表示する長さは変わりません',
        get=panel_parameters.get_minimum_cm, set=panel_parameters.set_minimum_cm,
        min=0, max=100, soft_max=60, precision=3, options=set())
    extension_element_cm: panel_parameters.number(
        'maximum_extension_element_length', scale=100, name='延長区間の最大長（cm）',
        description='非表示部分を分ける区間の最大長。小さくすると計算点が増えます',
        min=0.001, max=100, soft_max=5, precision=3)
    time_substeps: bpy.props.EnumProperty(
        name='時間分割数', description='1フレームを何回に分けて計算するか',
        items=[('2','2回','1フレームを2分割',2),('4','4回','1フレームを4分割',4),('8','8回','1フレームを8分割',8)],
        get=panel_parameters.get_substeps, set=panel_parameters.set_substeps, options=set())
    velocity_passes: panel_parameters.integer(
        'impulse_sweeps', name='速度・摩擦の補正回数', description='接触後の速度と摩擦を補正する回数', min=2, max=4)
    extension_passes: panel_parameters.integer(
        'extension_length_iterations', name='延長した毛の長さ補正回数',
        description='非表示延長のある毛で、長さ補正の内部計算を繰り返す回数', min=1, max=16)
    replay: bpy.props.BoolProperty(name="キャッシュを再生", default=False)
    status: bpy.props.StringProperty(default="未初期化")
    diagnostics: bpy.props.StringProperty()
    last_error: bpy.props.StringProperty()


class K4BVHInitialize(bpy.types.Operator):
    bl_idname = "kami4_bvh.initialize"
    bl_label = "初期化"

    def execute(self, context):
        try:
            initialize(context.scene)
            return {"FINISHED"}
        except Exception as exc:
            context.scene.kami4_bvh.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class K4BVHSimulate(bpy.types.Operator):
    bl_idname = "kami4_bvh.simulate"
    bl_label = "1フレーム計算"

    def execute(self, context):
        try:
            simulate_frame(context.scene)
            return {"FINISHED"}
        except Exception as exc:
            context.scene.kami4_bvh.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class K4BVHReset(bpy.types.Operator):
    bl_idname = "kami4_bvh.reset"
    bl_label = "開始形状へ戻す"

    def execute(self, context):
        try:
            initialize(context.scene, clear_cache=False)
            return {"FINISHED"}
        except Exception as exc:
            context.scene.kami4_bvh.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class K4BVHBake(bpy.types.Operator):
    bl_idname = "kami4_bvh.bake"
    bl_label = "全フレーム計算"
    _timer = None

    def finish(self, context, cancel=False):
        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None
        context.scene.kami4_bvh.replay = True
        if not cancel:
            context.scene.frame_set(context.scene.kami4_bvh.frame_end)
        return {"CANCELLED"} if cancel else {"FINISHED"}

    def execute(self, context):
        try:
            initialize(context.scene, preload=context.scene.kami4_bvh.preload_animation)
            if bpy.app.background:
                while simulate_frame(context.scene):
                    pass
                context.scene.kami4_bvh.replay = True
                context.scene.frame_set(context.scene.kami4_bvh.frame_end)
                return {"FINISHED"}
            self._timer = context.window_manager.event_timer_add(0.01, window=context.window)
            context.window_manager.modal_handler_add(self)
            return {"RUNNING_MODAL"}
        except Exception as exc:
            context.scene.kami4_bvh.last_error = str(exc)
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
                context.scene.kami4_bvh.last_error = str(exc)
                self.report({"ERROR"}, str(exc))
                return self.finish(context, True)
        return {"PASS_THROUGH"}


class K4BVHReplay(bpy.types.Operator):
    bl_idname = "kami4_bvh.replay"
    bl_label = "キャッシュ再生"

    def execute(self, context):
        context.scene.kami4_bvh.replay = True
        replay_handler(context.scene)
        return {"FINISHED"}


class K4BVHPanel(bpy.types.Panel):
    bl_label = "ACES 髪シミュレーション"
    bl_idname = "KAMI4_BVH_PT_solver"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "ACES"

    def draw(self, context):
        layout = self.layout
        s = context.scene.kami4_bvh
        layout.label(text='設定はこのシーンに保存されます')
        if s.output and s.output.get('kami4_parameter_hash'):
            try:
                changed = native.parameter_hash(get_parameters(s)) != s.output['kami4_parameter_hash']
                if changed:
                    layout.label(text='設定変更あり：反映には再計算が必要', icon='INFO')
            except Exception as exc:
                layout.label(text=str(exc), icon='ERROR')


classes = (K4BVHSettings, K4BVHInitialize, K4BVHSimulate, K4BVHReset, K4BVHBake, K4BVHReplay, K4BVHPanel) + panel_parameters.classes


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kami4_bvh = bpy.props.PointerProperty(type=K4BVHSettings)
    # Blender restricts data access while enabling an add-on at startup.
    # load_handler migrates the scenes once the blend has been loaded.
    for scene in getattr(bpy.data, 'scenes', ()):
        panel_parameters.migrate(scene.kami4_bvh)
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
    if hasattr(bpy.types.Scene, "kami4_bvh"):
        del bpy.types.Scene.kami4_bvh
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
