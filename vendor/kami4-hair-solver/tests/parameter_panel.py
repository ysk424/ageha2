"""Check UI conversion and persistence without creating or stepping a solver."""
import bpy,sys,importlib.util,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('aces_panel_test',ROOT/'extension/__init__.py',submodule_search_locations=[str(ROOT/'extension')])
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module);module.register()
from aces_panel_test import addon,native,panel_parameters as pp

def forbidden(*args,**kwargs):
    raise AssertionError('UI verification must not run a solver')
native.Solver=forbidden
s=bpy.context.scene.kami4_bvh
p=json.loads((ROOT/'presets/min-dynamic-length-30cm-20260917.json').read_text(encoding='utf8'))
pp.apply_parameters(s,p)
assert addon.get_parameters(s)==p
assert s.bending_log10==-6 and s.regularization_log10==-7
assert s.minimum_length_cm==30 and abs(s.density_g_per_m-.1)<1e-7
before=native.parameter_hash(p)
# Reading controls must preserve the existing full-precision cache hash.
for name in ['bending_log10','regularization_log10','density_g_per_m','velocity_damping','surface_friction','gravity_acceleration','collision_radius_mm','contact_margin_mm','minimum_length_cm','extension_element_cm','time_substeps','velocity_passes','extension_passes']:
    getattr(s,name)
assert native.parameter_hash(addon.get_parameters(s))==before
s.bending_log10=-5;s.regularization_log10=-6;s.density_g_per_m=.2;s.collision_radius_mm=.08;s.contact_margin_mm=.25;s.extension_element_cm=.5;s.time_substeps='8';s.velocity_passes=4;s.extension_passes=12
q=addon.get_parameters(s)
assert q['bending_rigidity']==1e-5 and q['length_regularization_relative']==1e-6
assert q['linear_density']==.0002 and q['guide_radius']==.00008 and q['contact_tolerance']==.00025
assert q['maximum_extension_element_length']==.005 and q['substeps']==8 and q['impulse_sweeps']==4 and q['extension_length_iterations']==12
assert q['minimum_dynamic_length']==.3 and q['root_points']==2
pp.apply_parameters(s,p)
fk=dict(p,mesh_contact_mode=2)
pp.apply_parameters(s,fk)
assert s.local_fk_collision and addon.get_parameters(s)==fk
s.whole_strand_collision=False
assert addon.get_parameters(s)['mesh_contact_mode']==0
pp.apply_parameters(s,p)
assert not s.local_fk_collision and addon.get_parameters(s)==p
out=ROOT/'outputs/parameter_panel';out.mkdir(exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out/'ui_values.blend'))
bpy.ops.wm.open_mainfile(filepath=str(out/'ui_values.blend'))
assert addon.get_parameters(bpy.context.scene.kami4_bvh)==p
result=dict(pass_=True,solver_executed=False,old_parameter_hash=before,new_parameter_hash=native.parameter_hash(addon.get_parameters(bpy.context.scene.kami4_bvh)),logarithmic_conversion=True,display_units=True,persistence=True)
(out/'verification.json').write_text(json.dumps(result,indent=2))
print('PARAMETER_PANEL_OK',json.dumps(result),flush=True)
