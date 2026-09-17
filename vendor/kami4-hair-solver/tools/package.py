"""Produce an installable extension without build/test/cache files."""

from pathlib import Path
import zipfile, shutil, hashlib, json

ROOT = Path(__file__).resolve().parents[1]
shutil.copyfile(ROOT / "LICENSE", ROOT / "extension/LICENSE")
dest = ROOT / "dist/kami4_hair_solver-0.1.0-windows-x64.zip"
dest.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
    for path in sorted((ROOT / "extension").rglob("*")):
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc":
            z.write(path, path.relative_to(ROOT / "extension"))
print(
    json.dumps(
        dict(
            package=str(dest),
            sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
            bytes=dest.stat().st_size,
        ),
        indent=2,
    )
)
