"""Markdown prose must remain auditable Japanese."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRECTORIES = {".git", "dist", "test_runs", "__pycache__"}
PROTECTED = re.compile(r"`[^`]*`|\$[^$]*\$|\]\([^)]*\)|https?://\S+")
ENGLISH_WORD = re.compile(r"[A-Za-z]{2,}")


class MarkdownLanguageTest(unittest.TestCase):
    def test_prose_is_japanese(self):
        violations: list[str] = []
        for path in sorted(ROOT.rglob("*.md")):
            if any(part in EXCLUDED_DIRECTORIES for part in path.parts):
                continue
            fenced = False
            math = False
            for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = raw.lstrip()
                if stripped.startswith("```"):
                    fenced = not fenced
                    continue
                if fenced:
                    continue
                if stripped.startswith("$$"):
                    math = not math
                    continue
                if math:
                    continue
                prose = PROTECTED.sub("", raw)
                if ENGLISH_WORD.search(prose):
                    violations.append(f"{path.relative_to(ROOT)}:{number}: {raw}")
        self.assertEqual(violations, [], "英語の説明文が残っています:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
