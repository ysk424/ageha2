"""揚羽 (Ageha) — グルーミングから Kami4 シミュレーションまでの統合拡張。"""
from __future__ import annotations

import hashlib
from pathlib import Path

import bpy
from bpy.props import FloatProperty, IntProperty, PointerProperty, StringProperty
from bpy.types import Object, Operator, PropertyGroup

from . import blender_io
from .kami4_solver import addon as kami4_addon
from .kami4_solver import native as kami4_native


__version__ = "0.3.0"

MASK_OBJECT_NAME = "Ageha_HairMask"
BANGS_CUTTER_NAME = "Ageha_BangsAutoCutter"


def _poll_curves(_self, obj) -> bool:
    return obj is not None and obj.type == "CURVES"


def _poll_mesh(_self, obj) -> bool:
    return obj is not None and obj.type == "MESH"


def _simulation(context):
    return context.scene.kami4


def _set_curves_surface(curves_obj, surface_obj) -> None:
    if curves_obj is None or curves_obj.type != "CURVES":
        return
    if surface_obj is None or surface_obj.type != "MESH":
        return
    curves_obj.data.surface = surface_obj
    if surface_obj.data.uv_layers.active is not None:
        curves_obj.data.surface_uv_map = surface_obj.data.uv_layers.active.name


def _detach_simulation(context) -> None:
    """入力変更後は既存キャッシュを削除せず、新しいベイク先へ切り替える。"""
    sim = _simulation(context)
    if kami4_addon._busy:
        raise RuntimeError("シミュレーション中は実行できません。先に Esc で中止してください")
    kami4_addon.load_handler()
    sim.replay = False
    sim.cache_directory = ""
    sim.status = "入力変更済み。次回ベイクは新しいキャッシュを使用します"


def _reset_frame1_and_detach_cache(context) -> None:
    context.scene.frame_set(1)
    _detach_simulation(context)


def _remove_mesh_object(obj) -> None:
    if obj is None:
        return
    mesh = obj.data if obj.type == "MESH" else None
    bpy.data.objects.remove(obj, do_unlink=True)
    if mesh is not None and mesh.users == 0:
        bpy.data.meshes.remove(mesh)


def _mesh_world_points(obj):
    deps = bpy.context.evaluated_depsgraph_get()
    evaluated = obj.evaluated_get(deps)
    mesh = evaluated.to_mesh()
    try:
        matrix = evaluated.matrix_world.copy()
        return [matrix @ vertex.co for vertex in mesh.vertices]
    finally:
        evaluated.to_mesh_clear()


def _find_eye_source_objects():
    exact_groups = (
        ("CC_Base_EyeOcclusion",),
        ("CC_Base_TearLine",),
        ("CC_Base_Eye",),
    )
    for names in exact_groups:
        objects = [
            bpy.data.objects.get(name)
            for name in names
            if bpy.data.objects.get(name) is not None
            and bpy.data.objects.get(name).type == "MESH"
        ]
        if objects:
            return objects

    pattern_groups = (
        ("eyeocclusion", "eye_occlusion"),
        ("tearline", "tear_line"),
        ("eye",),
    )
    for patterns in pattern_groups:
        objects = []
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            name = obj.name.lower()
            if "lash" in name or "brow" in name:
                continue
            if any(pattern in name for pattern in patterns):
                objects.append(obj)
        if objects:
            return objects
    return []


def _detect_eye_opening_bounds():
    sources = _find_eye_source_objects()
    if not sources:
        raise RuntimeError("眼メッシュが見つかりません（例: CC_Base_EyeOcclusion）")
    points = []
    for obj in sources:
        points.extend(_mesh_world_points(obj))
    if not points:
        names = ", ".join(obj.name for obj in sources)
        raise RuntimeError(f"眼メッシュに評価頂点がありません: {names}")
    return {
        "source_names": [obj.name for obj in sources],
        "min_x": min(point.x for point in points),
        "max_x": max(point.x for point in points),
        "min_y": min(point.y for point in points),
        "max_y": max(point.y for point in points),
        "min_z": min(point.z for point in points),
        "max_z": max(point.z for point in points),
    }


def _material_for_bangs_cutter():
    material = bpy.data.materials.get("Ageha_BangsAutoCutter_Material")
    if material is None:
        material = bpy.data.materials.new("Ageha_BangsAutoCutter_Material")
    material.diffuse_color = (1.0, 0.45, 0.05, 0.45)
    try:
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            if "Base Color" in bsdf.inputs:
                bsdf.inputs["Base Color"].default_value = (1.0, 0.45, 0.05, 0.45)
            if "Alpha" in bsdf.inputs:
                bsdf.inputs["Alpha"].default_value = 0.45
        material.surface_render_method = "DITHERED"
    except Exception:
        pass
    return material


def _create_bangs_cutter(context, side_extra_cm, z_extra_cm):
    bounds = _detect_eye_opening_bounds()
    side_extra_m = max(0.0, float(side_extra_cm)) * 0.01
    z_extra_m = max(0.0, float(z_extra_cm)) * 0.01
    left_x = bounds["min_x"] - side_extra_m
    right_x = bounds["max_x"] + side_extra_m
    center_y = bounds["min_y"] - 0.020
    y0 = center_y - 0.050
    y1 = center_y + 0.050
    z = bounds["max_z"] + z_extra_m

    mesh = bpy.data.meshes.new("Ageha_BangsAutoCutter_Mesh")
    mesh.from_pydata(
        [(left_x, y0, z), (right_x, y0, z), (right_x, y1, z), (left_x, y1, z)],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    mesh.materials.append(_material_for_bangs_cutter())

    obj = bpy.data.objects.get(BANGS_CUTTER_NAME)
    if obj is not None and obj.type == "MESH":
        old_mesh = obj.data
        obj.data = mesh
        obj.location = (0.0, 0.0, 0.0)
        obj.rotation_euler = (0.0, 0.0, 0.0)
        obj.scale = (1.0, 1.0, 1.0)
        if old_mesh.users == 0:
            bpy.data.meshes.remove(old_mesh)
    else:
        obj = bpy.data.objects.new(BANGS_CUTTER_NAME, mesh)
        context.scene.collection.objects.link(obj)
    if not obj.users_collection:
        context.scene.collection.objects.link(obj)
    obj.hide_render = True
    obj.show_in_front = True
    obj["ageha_source"] = "auto_bangs_trim"
    obj["ageha_eye_sources"] = ",".join(bounds["source_names"])
    return obj, bounds


def _clear_auto_bangs_cutter(cutter) -> None:
    if cutter is None or bpy.data.objects.get(cutter.name) is None:
        return
    if cutter.get("ageha_source") == "auto_bangs_trim":
        _remove_mesh_object(cutter)


class AgehaSettings(PropertyGroup):
    strand_count: IntProperty(
        name="ストランド数",
        description="マスク植えの総ストランド数",
        default=4000,
        min=1,
        max=100000,
    )
    max_length_cm: FloatProperty(
        name="最大長 (cm)",
        description="黒マスクの長さ。灰は線形に短く、白は 0 cm",
        default=20.0,
        min=0.1,
        max=500.0,
        step=100,
        precision=1,
    )
    bangs_side_extra_cm: FloatProperty(
        name="横 +cm",
        description="前髪カット: 眼幅の両端に足す余白",
        default=1.0,
        min=0.0,
        max=50.0,
        step=10,
        precision=2,
    )
    bangs_z_extra_cm: FloatProperty(
        name="Z +cm",
        description="前髪カット: 検出した眼上端より上に足す高さ",
        default=3.0,
        min=0.0,
        max=50.0,
        step=10,
        precision=2,
    )
    runtime_status: StringProperty(name="状態", default="準備完了", options={"SKIP_SAVE"})


class _PickObjectBase(Operator):
    bl_options = {"INTERNAL"}
    target_property = ""
    required_type = ""

    def execute(self, context):
        active = context.active_object
        if active is None or active.type != self.required_type:
            self.report({"ERROR"}, f"アクティブオブジェクトは {self.required_type} である必要があります")
            return {"CANCELLED"}
        setattr(_simulation(context), self.target_property, active)
        return {"FINISHED"}


class AGEHA_OT_pick_hair(_PickObjectBase):
    bl_idname = "ageha.pick_hair"
    bl_label = "アクティブを髪に"
    target_property = "source"
    required_type = "CURVES"


class AGEHA_OT_pick_body(_PickObjectBase):
    bl_idname = "ageha.pick_body"
    bl_label = "アクティブをボディに"
    target_property = "collider"
    required_type = "MESH"


class AGEHA_OT_preflight(Operator):
    bl_idname = "ageha.preflight"
    bl_label = "セットアップ検証"
    bl_description = "髪・コライダーと無改変 Kami4 CUDA DLL を検証"

    def execute(self, context):
        ageha = context.scene.ageha_settings
        sim = _simulation(context)
        try:
            positions, offsets = kami4_addon.hair_positions(sim.source, context.scene)
            vertices, triangles, _signature = kami4_addon.mesh_positions(sim, context.scene)
            if vertices is None or triangles is None or len(triangles) == 0:
                raise ValueError("衝突メッシュを指定してください")
            library = kami4_native.library()
            version = library.k4_version().decode("utf8")
            dll = Path(kami4_native.ROOT) / "bin" / "kami4_hair_core.dll"
            digest = hashlib.sha256(dll.read_bytes()).hexdigest()[:12]
            ageha.runtime_status = (
                f"準備完了: {len(offsets)-1:,}本 / {len(positions):,}点 / "
                f"三角形 {len(triangles):,} / {version} / DLL {digest}"
            )
            self.report({"INFO"}, ageha.runtime_status)
            return {"FINISHED"}
        except Exception as exc:
            ageha.runtime_status = f"エラー: {exc}"
            sim.last_error = str(exc)
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class AGEHA_OT_new_cache(Operator):
    bl_idname = "ageha.new_cache"
    bl_label = "新しいキャッシュに切替"
    bl_description = "既存ファイルを削除せず、次回ベイク用の新しいキャッシュを自動作成"

    def execute(self, context):
        try:
            _detach_simulation(context)
            context.scene.ageha_settings.runtime_status = "既存キャッシュを保持して切り離しました"
            return {"FINISHED"}
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}


class AGEHA_OT_create_head_mask(Operator):
    bl_idname = "ageha.create_head_mask"
    bl_label = "ヘッドマスク作成"

    def execute(self, context):
        ageha = context.scene.ageha_settings
        sim = _simulation(context)
        try:
            _reset_frame1_and_detach_cache(context)
            if sim.source is None or sim.source.type != "CURVES":
                raise RuntimeError("髪 (Curves) を選択してください")
            if sim.collider is None or sim.collider.type != "MESH":
                raise RuntimeError("ボディ (Mesh) を選択してください")
            _set_curves_surface(sim.source, sim.collider)
            from . import _mask_plant

            mask_obj = _mask_plant.create_head_mask(sim.collider)
        except Exception as exc:
            ageha.runtime_status = f"エラー: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        for obj in context.selected_objects:
            obj.select_set(False)
        mask_obj.select_set(True)
        context.view_layer.objects.active = mask_obj
        try:
            bpy.ops.object.mode_set(mode="TEXTURE_PAINT")
            paint = context.scene.tool_settings.image_paint
            if paint.brush is not None and hasattr(paint.brush, "color"):
                paint.brush.color = (0.0, 0.0, 0.0)
        except RuntimeError:
            pass
        ageha.runtime_status = f"{MASK_OBJECT_NAME} を作成（白=0 cm, 黒=最大長）"
        self.report({"INFO"}, ageha.runtime_status)
        return {"FINISHED"}


class AGEHA_OT_plant_hair(Operator):
    bl_idname = "ageha.plant_hair"
    bl_label = "髪を植える"

    def execute(self, context):
        ageha = context.scene.ageha_settings
        sim = _simulation(context)
        try:
            _reset_frame1_and_detach_cache(context)
            curves_obj = sim.source
            if curves_obj is None or curves_obj.type != "CURVES":
                raise RuntimeError("髪 (Curves) を選択してください")
            ref_obj = bpy.data.objects.get(MASK_OBJECT_NAME)
            if ref_obj is None or ref_obj.type != "MESH":
                raise RuntimeError(f"先に {MASK_OBJECT_NAME} を作成してください")
            from . import _mask_plant

            if len(curves_obj.data.curves) or len(curves_obj.data.points):
                _mask_plant.remove_all_hair(curves_obj)
            _set_curves_surface(curves_obj, sim.collider)
            result = _mask_plant.plant_mask_hair(
                ref_obj,
                strand_count=ageha.strand_count,
                max_length_cm=ageha.max_length_cm,
                curves_obj=curves_obj,
            )
        except Exception as exc:
            ageha.runtime_status = f"エラー: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        ageha.runtime_status = (
            f"植え完了: {result['n_added']} 本 / {result['total_points']} 点, "
            f"平均長 {result['mean_length_cm']:.1f} cm"
        )
        self.report({"INFO"}, ageha.runtime_status)
        return {"FINISHED"}


class AGEHA_OT_plant_z_axis(Operator):
    bl_idname = "ageha.plant_z_axis"
    bl_label = "Z列植え"

    def execute(self, context):
        ageha = context.scene.ageha_settings
        sim = _simulation(context)
        try:
            _reset_frame1_and_detach_cache(context)
            curves_obj = sim.source
            if curves_obj is None or curves_obj.type != "CURVES":
                raise RuntimeError("髪 (Curves) を選択してください")
            ref_obj = bpy.data.objects.get(MASK_OBJECT_NAME)
            if ref_obj is None or ref_obj.type != "MESH":
                raise RuntimeError(f"先に {MASK_OBJECT_NAME} を作成してください")
            from . import _mask_plant

            if len(curves_obj.data.curves) or len(curves_obj.data.points):
                _mask_plant.remove_all_hair(curves_obj)
            _set_curves_surface(curves_obj, sim.collider)
            result = _mask_plant.plant_z_slice_hair(
                ref_obj,
                strand_count=ageha.strand_count,
                max_length_cm=ageha.max_length_cm,
                curves_obj=curves_obj,
            )
        except Exception as exc:
            ageha.runtime_status = f"エラー: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        ageha.runtime_status = (
            f"Z列植え: {result['n_added']} 本 / {result['rows']} 行 "
            f"({result['spacing_mm']:.1f} mm), 平均長 {result['mean_length_cm']:.1f} cm"
        )
        self.report({"INFO"}, ageha.runtime_status)
        return {"FINISHED"}


class AGEHA_OT_trim_bangs(Operator):
    bl_idname = "ageha.trim_bangs"
    bl_label = "前髪カット"

    def execute(self, context):
        ageha = context.scene.ageha_settings
        sim = _simulation(context)
        source = sim.source
        cutter = None
        bounds = {"source_names": []}
        try:
            if kami4_addon._busy:
                raise RuntimeError("シミュレーション中は実行できません")
            if source is None or source.type != "CURVES":
                raise RuntimeError("髪 (Curves) を選択してください")
            measured = sim.output if sim.output is not None else source
            if not len(measured.data.curves):
                raise RuntimeError("髪にストランドがありません")
            from . import _groom_ops

            cutter, bounds = _create_bangs_cutter(
                context,
                ageha.bangs_side_extra_cm,
                ageha.bangs_z_extra_cm,
            )
            cuts = _groom_ops.measure_bangs_cut_lengths(measured, cutter)
        except Exception as exc:
            ageha.runtime_status = f"エラー: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        finally:
            _clear_auto_bangs_cutter(cutter)

        try:
            _reset_frame1_and_detach_cache(context)
            from . import _groom_ops

            count = _groom_ops.apply_strand_lengths(source, cuts)
            blender_io.force_viewport_refresh()
        except Exception as exc:
            ageha.runtime_status = f"エラー: {exc}"
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        eyes = "+".join(bounds["source_names"])
        ageha.runtime_status = f"前髪カット: {count} 本を短縮。眼={eyes}"
        self.report({"INFO"}, ageha.runtime_status)
        return {"FINISHED"}


_CLASSES = (
    AgehaSettings,
    AGEHA_OT_pick_hair,
    AGEHA_OT_pick_body,
    AGEHA_OT_preflight,
    AGEHA_OT_new_cache,
    AGEHA_OT_create_head_mask,
    AGEHA_OT_plant_hair,
    AGEHA_OT_plant_z_axis,
    AGEHA_OT_trim_bangs,
)

_KAMI4_CLASSES = tuple(
    cls for cls in kami4_addon.classes if cls is not kami4_addon.K4Panel
)


def _register_kami4_without_its_panel() -> None:
    for cls in _KAMI4_CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.kami4 = PointerProperty(type=kami4_addon.K4Settings)
    if kami4_addon.replay_handler not in bpy.app.handlers.frame_change_post:
        bpy.app.handlers.frame_change_post.append(kami4_addon.replay_handler)
    if kami4_addon.load_handler not in bpy.app.handlers.load_post:
        bpy.app.handlers.load_post.append(kami4_addon.load_handler)


def _unregister_kami4_without_its_panel() -> None:
    kami4_addon.load_handler()
    for sequence, function in (
        (bpy.app.handlers.frame_change_post, kami4_addon.replay_handler),
        (bpy.app.handlers.load_post, kami4_addon.load_handler),
    ):
        if function in sequence:
            sequence.remove(function)
    if hasattr(bpy.types.Scene, "kami4"):
        del bpy.types.Scene.kami4
    for cls in reversed(_KAMI4_CLASSES):
        bpy.utils.unregister_class(cls)


def register():
    from . import ui

    _register_kami4_without_its_panel()
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ageha_settings = PointerProperty(type=AgehaSettings)
    ui.register()


def unregister():
    from . import ui

    ui.unregister()
    if hasattr(bpy.types.Scene, "ageha_settings"):
        del bpy.types.Scene.ageha_settings
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
    _unregister_kami4_without_its_panel()
