"""Exit condition: no runtime path refers to Claude Code."""
from __future__ import annotations

import unittest

from tests.support.factory import TEMPLATE


class NoClaudeCodeTests(unittest.TestCase):
    def test_runtime_modules_never_mention_claude(self):
        for path in sorted((TEMPLATE / "adws").rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            self.assertNotIn("claude", text, str(path))


if __name__ == "__main__":
    unittest.main()
