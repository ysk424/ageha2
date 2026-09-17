"""Ageha must start from the complete user-adopted ACES profile."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WrapperDefaultsTest(unittest.TestCase):
    def test_complete_adopted_profile(self):
        profile = json.loads(
            (ROOT / "presets" / "local-fk-contact-20260917.json").read_text(encoding="utf8")
        )
        self.assertEqual(profile["minimum_dynamic_length"], 0.3)
        self.assertEqual(profile["maximum_extension_element_length"], 0.01)
        self.assertEqual(profile["extension_length_iterations"], 16)
        self.assertEqual(profile["maximum_visible_element_length"], 0.0)
        self.assertEqual(profile["root_points"], 2)
        self.assertEqual(profile["mesh_contact_mode"], 2)
        canonical = json.dumps(profile, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "f9473015f35d7d081ab5be07e23fe2b100288552af3a35456e039f6888fcd29b",
        )


if __name__ == "__main__":
    unittest.main()
