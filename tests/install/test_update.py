"""Manifest-driven update: untouched targets update, user-modified conflict."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tests.support.environment import child_env  # noqa: E402
from tests.support.example import prepare_example_target  # noqa: E402
from tests.support.factory import ROOT, TEMPLATE, FactoryTestCase  # noqa: E402


def run_cli(*args: str, cwd=None) -> subprocess.CompletedProcess[str]:
    cwd_path = Path(cwd) if cwd else ROOT
    home = Path(tempfile.mkdtemp(prefix="sssf-cli-home-"))
    return subprocess.run(
        ["uv", "run", "--locked", "--project", str(ROOT), "sssf", *args],
        cwd=str(cwd_path), env=child_env(home), capture_output=True,
        text=True, timeout=60)


class UpdateTests(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.before_hashes = prepare_example_target(self.target, self.env)
        # Rewrite one template to simulate a new factory version; restored via
        # addCleanup so even a crashing test cannot leave the source modified.
        self.template_copy = TEMPLATE / "env.sample"
        self.original = self.template_copy.read_bytes()
        self.template_copy.write_bytes(self.original + b"\n# updated upstream\n")
        self.addCleanup(self.template_copy.write_bytes, self.original)

    def test_untouched_target_updates(self):
        result = run_cli("update", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / ".env.sample").read_bytes(),
                         self.original + b"\n# updated upstream\n")
        self.assertIn("update", result.stdout.lower())

    def test_user_modified_file_conflicts_and_is_untouched(self):
        (self.target / ".env.sample").write_bytes(b"# user's own edits\n")
        result = run_cli("update", cwd=str(self.target))
        self.assertEqual(result.returncode, 3)
        self.assertIn("conflict", result.stdout.lower())
        self.assertIn(".env.sample", result.stdout)
        self.assertEqual((self.target / ".env.sample").read_bytes(),
                         b"# user's own edits\n")

    def test_force_overwrites_conflicts(self):
        (self.target / ".env.sample").write_bytes(b"# user's own edits\n")
        result = run_cli("update", "--force", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / ".env.sample").read_bytes(),
                         self.original + b"\n# updated upstream\n")

    def test_dry_run_classifies_without_writing(self):
        (self.target / ".env.sample").write_bytes(b"# user's own edits\n")
        before = (self.target / ".env.sample").read_bytes()
        result = run_cli("update", "--dry-run", cwd=str(self.target))
        self.assertEqual(result.returncode, 3)       # conflict reported, nothing written
        self.assertEqual((self.target / ".env.sample").read_bytes(), before)
        self.assertEqual((self.target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())

    def test_app_files_are_never_touched_by_update(self):
        result = run_cli("update", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, expected in self.before_hashes.items():
            self.assertEqual(
                sha256((self.target / path).read_bytes()).hexdigest(), expected, path)

    def test_update_without_manifest_is_refused(self):
        bare = self.target / "bare"
        bare.mkdir()
        result = run_cli("update", cwd=str(bare))
        self.assertEqual(result.returncode, 2)
        self.assertIn("init", result.stderr)


if __name__ == "__main__":
    unittest.main()
