"""Kami4 runtime must remain byte-for-byte identical to the accepted source."""
from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "__init__.py": "A64A8924F6BBEE3E1CA94694277A6A44D68D703ED422AE7FAB0F1DC3AF33CC47",
    "addon.py": "4DB98A9B9718E1145271EC730BF724333198F13CF1E06BA494464653A690681A",
    "bin/kami4_hair_core_bvh1.dll": "1CD10BD1BCD301F798D7394E30AEF8D30E156BC0E7026C59500BAAEEDAF4D9BE",
    "bin/kami4_hair_core_fk1.dll": "0C5DB7C3CC80CA80B86394D25E4FF5541BB7E1AF5362EFD9C2245A86962A221E",
    "cache.py": "8E3CE0F3568894814FFB65AEE558214C7528E0FD60A0B7583C2EF66BA730069D",
    "native.py": "361304DB3CA03B1C77FD72314542B87817633DF27C6901273C0F486EC192ED54",
    "panel_parameters.py": "2C29AF675068C50E11D4189AD5D5CDEA14315C24C41B4F3E23F9461B267C6C7C",
    "parameters.json": "6BE93853179BD3D06E19CAB3476245528DB0BD12C6F4CC2F37D081F58FED79A2",
    "topology.py": "1C5FB128652B46C4B0A0ADE075C35D545BCE1B571ADC7E385B72C0594A365EB5",
}


class VendorIntegrityTest(unittest.TestCase):
    def test_kami4_runtime_hashes(self):
        for relative, expected in EXPECTED.items():
            with self.subTest(path=relative):
                data = (ROOT / "kami4_solver" / relative).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest().upper(), expected)


if __name__ == "__main__":
    unittest.main()
