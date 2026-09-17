"""The Ageha panel defaults must reproduce Kami4 parameters without rounding."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WrapperDefaultsTest(unittest.TestCase):
    def test_defaults_equal_unmodified_kami4_json(self):
        tree = ast.parse((ROOT / "__init__.py").read_text(encoding="utf8"))
        wrapper = None
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(
                isinstance(target, ast.Name) and target.id == "KAMI4_PARAMETER_DEFAULTS"
                for target in node.targets
            ):
                wrapper = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(wrapper)
        source = json.loads(
            (ROOT / "kami4_solver" / "parameters.json").read_text(encoding="utf8")
        )
        self.assertEqual({"schema": 1, **wrapper}, source)
        canonical = json.dumps(source, sort_keys=True, separators=(",", ":")).encode()
        self.assertEqual(
            hashlib.sha256(canonical).hexdigest(),
            "1a3e001805bf7fcf2b7e95eb7f1141c14d9226c4b2bd6b40984e51a754ac92a5",
        )


if __name__ == "__main__":
    unittest.main()
