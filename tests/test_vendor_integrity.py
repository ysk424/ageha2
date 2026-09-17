"""Kami4 runtime must remain byte-for-byte identical to the accepted source."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "__init__.py": "FDE09F23590C514B7B17C52E7916D88C41E70D3183A3AB7533C187609C23B6F3",
    "addon.py": "0F0CE58C4A907212C5BE93BECA11EFEEEF81EB648B1CAC3210888B8E149F4CA9",
    "bin/kami4_hair_core.dll": "EA2D71F02A40EE0DB6820C097784C8795132EDEA0DEE097B70DBDD445650F0C2",
    "blender_manifest.toml": "8F619A0B9C469A32F59C6072B88D0901EB7A23FE312974493E858AD7DC79ED66",
    "cache.py": "8E3CE0F3568894814FFB65AEE558214C7528E0FD60A0B7583C2EF66BA730069D",
    "LICENSE": "3972DC9744F6499F0F9B2DBF76696F2AE7AD8AF9B23DDE66D6AF86C9DFB36986",
    "native.py": "A73D7253F52645C70BBA0B1F2ECBF959E4E16EF5838D7E4E167A75A5DD797F20",
    "parameters.json": "F41C110B2DFA62539E5560D2D9C82BF5464AA5055E788DA9E801240987875B9C",
    "README.md": "0C867D12EF630CF3CFBE991F7DFCD12B6BAC9B434056AECBC3E55C7D09D2891B",
}


class VendorIntegrityTest(unittest.TestCase):
    def test_kami4_runtime_hashes(self):
        for relative, expected in EXPECTED.items():
            with self.subTest(path=relative):
                data = (ROOT / "kami4_solver" / relative).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest().upper(), expected)


if __name__ == "__main__":
    unittest.main()
