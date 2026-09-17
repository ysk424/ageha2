"""揚羽 — 3D ビューの一体型ワークフローパネル。"""
from __future__ import annotations

import bpy
from bpy.types import Panel

from . import __version__


def _label(layout, text: str, *, icon: str = "NONE") -> None:
    layout.label(text=text, icon=icon, translate=False)


def _prop(layout, settings, name: str, *, text: str | None = None) -> None:
    kwargs = {"translate": False}
    if text is not None:
        kwargs["text"] = text
    layout.prop(settings, name, **kwargs)


class AGEHA_PT_main(Panel):
    bl_idname = "AGEHA_PT_main"
    bl_label = "揚羽"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "揚羽"

    def draw(self, context):
        layout = self.layout
        ageha = context.scene.ageha_settings
        sim = context.scene.kami4

        _label(layout, f"揚羽  v{__version__} / Kami4")

        box = layout.box()
        _label(box, "オブジェクト")
        row = box.row(align=True)
        _prop(row, sim, "source", text="髪")
        row.operator("ageha.pick_hair", text="", icon="EYEDROPPER", translate=False)
        row = box.row(align=True)
        _prop(row, sim, "collider", text="ボディ")
        row.operator("ageha.pick_body", text="", icon="EYEDROPPER", translate=False)
        _prop(box, sim, "collider_collection", text="服・追加コライダー")
        box.operator("ageha.preflight", icon="CHECKMARK", translate=False)

        box = layout.box()
        _label(box, "植え・前髪")
        column = box.column(align=True)
        column.operator("ageha.create_head_mask", icon="MESH_DATA", translate=False)
        _prop(column, ageha, "strand_count")
        _prop(column, ageha, "max_length_cm")
        row = column.row(align=True)
        row.operator("ageha.plant_hair", icon="OUTLINER_OB_CURVES", translate=False)
        row.operator("ageha.plant_z_axis", icon="MOD_ARRAY", translate=False)
        row = column.row(align=True)
        _prop(row, ageha, "bangs_side_extra_cm")
        _prop(row, ageha, "bangs_z_extra_cm")
        column.operator("ageha.trim_bangs", icon="MOD_SOLIDIFY", translate=False)
        _label(box, "入力変更時は既存キャッシュを保持して切替")

        box = layout.box()
        _label(box, "シミュレーション — Kami4 固定")
        row = box.row(align=True)
        _prop(row, sim, "frame_start")
        _prop(row, sim, "frame_end")
        _prop(box, sim, "root_points")
        _prop(box, sim, "parameter_file", text="共通パラメータ JSON")
        _prop(box, sim, "cache_directory", text="キャッシュ")
        box.operator("ageha.new_cache", icon="FILE_REFRESH", translate=False)
        row = box.row(align=True)
        row.operator("kami4.initialize", text="初期化", translate=False)
        row.operator("kami4.reset", text="開始形状へ", translate=False)
        row = box.row(align=True)
        row.operator("kami4.simulate", text="1フレーム計算", translate=False)
        row.operator("kami4.bake", text="全フレーム計算", icon="RENDER_ANIMATION", translate=False)
        box.operator("kami4.replay", text="キャッシュ再生", translate=False)
        _prop(box, sim, "replay")

        status_icon = "ERROR" if sim.last_error else "CHECKMARK"
        _label(box, sim.status, icon=status_icon)
        if sim.diagnostics:
            _label(box, sim.diagnostics)
        if sim.last_error:
            _label(box, sim.last_error, icon="ERROR")

        box = layout.box()
        _label(box, "揚羽")
        _label(box, ageha.runtime_status)
        _label(box, "ソルバー選択なし / Kami4 のみ", icon="LOCKED")


_CLASSES = (AGEHA_PT_main,)


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
