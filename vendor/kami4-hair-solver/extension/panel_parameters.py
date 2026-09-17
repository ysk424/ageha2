"""Japanese controls backed by full-precision scene values; log controls edit exponents."""
import math
import bpy
from . import native

STORE = 'aces_parameters'


def contact_mode(settings):
    return (2 if settings.local_fk_collision else 1) if settings.whole_strand_collision else 0


def legacy_parameters(settings):
    p = native.parameters(bpy.path.abspath(settings.parameter_file) if settings.parameter_file else None)
    p.update(mesh_contact_mode=contact_mode(settings),
             minimum_dynamic_length=round(float(settings.minimum_dynamic_length), 6),
             maximum_extension_element_length=0.01, extension_length_iterations=16,
             maximum_visible_element_length=0.0, root_points=settings.root_points)
    if settings.whole_strand_collision:
        p['length_passes'] = settings.contact_passes
    return p


def values(settings):
    # Getters and panel drawing must not write Blender ID data.
    return settings[STORE].to_dict() if STORE in settings else legacy_parameters(settings)


def migrate(settings):
    if STORE not in settings:
        p = legacy_parameters(settings)
        settings[STORE] = p
        settings.contact_passes = p['length_passes']


def parameters(settings):
    p = values(settings)
    p.update(mesh_contact_mode=contact_mode(settings),
             minimum_dynamic_length=round(float(settings.minimum_dynamic_length), 6),
             maximum_visible_element_length=0.0, root_points=settings.root_points,
             length_passes=settings.contact_passes)
    return p


def write_value(settings, key, value):
    p = values(settings)
    p[key] = value
    settings[STORE] = p


def canonical(value):
    # RNA sliders supply float32 values. Keep the intended seven significant digits.
    return float(format(float(value), '.7g'))


def number(key, scale=1.0, **kwargs):
    def get(self):
        return float(values(self)[key]) * scale
    def set_value(self, value):
        write_value(self, key, canonical(value) / scale)
    return bpy.props.FloatProperty(get=get, set=set_value, options=set(), **kwargs)


def integer(key, **kwargs):
    def get(self):
        return int(values(self)[key])
    def set_value(self, value):
        write_value(self, key, int(value))
    return bpy.props.IntProperty(get=get, set=set_value, options=set(), **kwargs)


def logarithm(key, **kwargs):
    def get(self):
        return math.log10(max(float(values(self)[key]), 1e-16))
    def set_value(self, value):
        write_value(self, key, 10.0 ** round(float(value), 6))
    return bpy.props.FloatProperty(get=get, set=set_value, options=set(), **kwargs)


def get_substeps(self):
    return int(values(self)['substeps'])


def set_substeps(self, value):
    write_value(self, 'substeps', int(value))


def get_minimum_cm(self):
    return round(float(self.minimum_dynamic_length), 6) * 100


def set_minimum_cm(self, value):
    self.minimum_dynamic_length = canonical(value) / 100


def apply_parameters(settings, incoming):
    p = parameters(settings)
    p.update(incoming)
    positive = ('bending_rigidity', 'linear_density', 'guide_radius',
                'length_regularization_relative', 'maximum_extension_element_length')
    nonnegative = ('damping', 'friction', 'gravity', 'contact_tolerance', 'minimum_dynamic_length')
    for key in positive + nonnegative:
        v = float(p[key])
        if not math.isfinite(v) or v < 0 or (key in positive and v == 0):
            raise ValueError(f'設定値が不正です: {key}')
    limits = {'substeps': (2, 4, 8), 'root_points': (1, 2), 'impulse_sweeps': (2, 3, 4),
              'length_passes': tuple(range(2, 33)), 'extension_length_iterations': tuple(range(1, 17)),
              'mesh_contact_mode': (0, 1, 2)}
    for key, allowed in limits.items():
        if p[key] not in allowed:
            raise ValueError(f'設定範囲外です: {key}')
    if p['minimum_dynamic_length'] > 1 or p.get('maximum_visible_element_length', 0) != 0:
        raise ValueError('このパネルで扱えない毛の細分化設定です')
    settings[STORE] = p
    settings.minimum_dynamic_length = p['minimum_dynamic_length']
    settings.root_points = p['root_points']
    settings.contact_passes = p['length_passes']
    settings.whole_strand_collision = bool(p['mesh_contact_mode'])
    settings.local_fk_collision = p['mesh_contact_mode'] == 2


def draw_log(layout, settings, prop, key, unit=''):
    layout.prop(settings, prop, slider=True)
    value = values(settings)[key]
    layout.label(text=f'実際の値：{value:.4g} {unit}'.rstrip())


class ACES_PT_material(bpy.types.Panel):
    bl_label = '髪の性質'
    bl_idname = 'ACES_PT_material'
    bl_parent_id = 'KAMI4_BVH_PT_solver'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ACES'
    bl_order = 0

    def draw(self, context):
        s = context.scene.kami4_bvh
        col = self.layout.column(align=True)
        draw_log(col, s, 'bending_log10', 'bending_rigidity', 'N・m²')
        col.separator()
        for name in ('density_g_per_m', 'velocity_damping', 'surface_friction', 'gravity_acceleration'):
            col.prop(s, name)


class ACES_PT_contact(bpy.types.Panel):
    bl_label = '接触・毛の長さ'
    bl_idname = 'ACES_PT_contact'
    bl_parent_id = 'KAMI4_BVH_PT_solver'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ACES'
    bl_order = 1

    def draw(self, context):
        s = context.scene.kami4_bvh
        col = self.layout.column(align=True)
        for name in ('whole_strand_collision', 'local_fk_collision', 'collision_radius_mm', 'contact_margin_mm',
                     'minimum_length_cm', 'root_points', 'extension_element_cm'):
            col.prop(s, name)


class ACES_PT_accuracy(bpy.types.Panel):
    bl_label = '計算精度と速度'
    bl_idname = 'ACES_PT_accuracy'
    bl_parent_id = 'KAMI4_BVH_PT_solver'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ACES'
    bl_order = 2

    def draw(self, context):
        s = context.scene.kami4_bvh
        col = self.layout.column(align=True)
        for name in ('time_substeps', 'contact_passes', 'velocity_passes', 'extension_passes'):
            col.prop(s, name)
        col.separator()
        draw_log(col, s, 'regularization_log10', 'length_regularization_relative')


class ACES_OT_load_parameters(bpy.types.Operator):
    bl_idname = 'kami4_bvh.load_parameters'
    bl_label = '設定ファイルから読み込む'
    bl_description = '指定したJSONの値をパネルへ読み込みます。シミュレーションは実行しません'
    bl_options = {'UNDO'}

    def execute(self, context):
        s = context.scene.kami4_bvh
        try:
            if not s.parameter_file:
                raise ValueError('設定ファイルを指定してください')
            apply_parameters(s, native.parameters(bpy.path.abspath(s.parameter_file)))
            s.last_error = ''
            self.report({'INFO'}, '設定をパネルに読み込みました')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class ACES_PT_files(bpy.types.Panel):
    bl_label = '入力・キャッシュ'
    bl_idname = 'ACES_PT_files'
    bl_parent_id = 'KAMI4_BVH_PT_solver'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ACES'
    bl_options = {'DEFAULT_CLOSED'}
    bl_order = 3

    def draw(self, context):
        s = context.scene.kami4_bvh
        col = self.layout.column()
        for name in ('source', 'collider', 'collider_collection', 'parameter_file'):
            col.prop(s, name)
        col.operator('kami4_bvh.load_parameters', icon='IMPORT')
        col.prop(s, 'cache_directory')
        col.prop(s, 'preload_animation')


class ACES_PT_run(bpy.types.Panel):
    bl_label = '計算・再生'
    bl_idname = 'ACES_PT_run'
    bl_parent_id = 'KAMI4_BVH_PT_solver'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ACES'
    bl_order = 4

    def draw(self, context):
        s = context.scene.kami4_bvh
        col = self.layout.column()
        row = col.row(align=True)
        row.prop(s, 'frame_start'); row.prop(s, 'frame_end')
        row = col.row(align=True)
        row.operator('kami4_bvh.initialize'); row.operator('kami4_bvh.reset')
        row = col.row(align=True)
        row.operator('kami4_bvh.simulate'); row.operator('kami4_bvh.bake')
        col.operator('kami4_bvh.replay')
        col.prop(s, 'replay')
        col.label(text=s.status)
        if s.last_error:
            col.label(text=s.last_error, icon='ERROR')


classes = (ACES_PT_material, ACES_PT_contact, ACES_PT_accuracy, ACES_OT_load_parameters,
           ACES_PT_files, ACES_PT_run)
