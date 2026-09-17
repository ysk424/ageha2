"""Refresh unloaded native bindings and helper methods without losing scene pointers."""

import importlib, ast
from pathlib import Path

ROOT = Path("C:/Users/azoo/git/kami4-hair-solver")
native = importlib.import_module("bl_ext.user_default.kami4_hair_solver.native")
addon = importlib.import_module("bl_ext.user_default.kami4_hair_solver.addon")
cache = importlib.import_module("bl_ext.user_default.kami4_hair_solver.cache")
if native._lib is not None or addon._runtime:
    raise RuntimeError("A native session is loaded; restart Blender before replacing its DLL")
importlib.reload(native)
importlib.reload(cache)
tree = ast.parse(Path(addon.__file__).read_text(encoding="utf8"))
fn = next(x for x in tree.body if isinstance(x, ast.FunctionDef) and x.name == "initialize")
exec(compile(ast.Module(body=[fn], type_ignores=[]), addon.__file__, "exec"), addon.__dict__)
cls = next(x for x in tree.body if isinstance(x, ast.ClassDef) and x.name == "K4Reset")
fn = next(x for x in cls.body if isinstance(x, ast.FunctionDef) and x.name == "execute")
namespace = dict(addon.__dict__)
exec(compile(ast.Module(body=[fn], type_ignores=[]), addon.__file__, "exec"), namespace)
addon.K4Reset.execute = namespace["execute"]
exec((ROOT / "tools/install_scene.py").read_text(encoding="utf8"))
