"""Installation of the current factory onto the pinned Inkwell example.

Application bytes always come from the pinned Git object store, never from
the live example worktree and never from a silent fetch. These tests prove
the installer stamps a real, untouched application without mutating it.
"""
from __future__ import annotations

import json
import subprocess
import tempfile
from hashlib import sha256
from pathlib import Path

from tests.install.test_justfile import recipe_names
from tests.support.environment import child_env
from tests.support.example import (
    COMMIT,
    EXAMPLE,
    export_example,
    prepare_example_target,
)
from tests.support.factory import ROOT, SKILL, FactoryTestCase, TEMPLATE, git, stamp


def _tree_hashes(root: Path) -> dict[str, str]:
    """SHA-256 of every file under root, excluding Git internals."""
    return {
        str(p.relative_to(root)): sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".git" not in p.parts
    }


def _example_blob(rel: str) -> bytes:
    """Read one file blob from the pinned example commit."""
    result = subprocess.run(
        ["git", "cat-file", "blob", f"{COMMIT}:{rel}"],
        cwd=ROOT, capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        raise AssertionError(f"cannot read {rel} at {COMMIT}: {result.stderr!r}")
    return result.stdout


class ExampleInstallTests(FactoryTestCase):
    def test_current_factory_stamps_untouched_inkwell(self):
        before = export_example(ROOT, self.target)
        self.assertIn("apps/inkwell/server.ts", before)
        self.assertFalse((self.target / "adws").exists())
        self.assertFalse((self.target / "justfile").exists())
        stamp(self.target, self.env).check_returncode()
        for path, expected in before.items():
            self.assertEqual(
                sha256((self.target / path).read_bytes()).hexdigest(), expected, path)
        self.assertEqual((self.target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())

    def test_export_rejects_a_nonempty_destination(self):
        (self.target / "occupied.txt").write_text("occupied")
        with self.assertRaises(AssertionError):
            export_example(ROOT, self.target)


class PreparedTargetTests(FactoryTestCase):
    """prepare_example_target: pinned app + current factory, committed."""

    def test_prepare_commits_app_and_current_factory_into_scratch_repo(self):
        before = prepare_example_target(self.target, self.env)
        self.assertIn("apps/inkwell/README.md", before)
        for path, expected in before.items():
            self.assertEqual(
                sha256((self.target / path).read_bytes()).hexdigest(), expected, path)
        self.assertTrue((self.target / "adws" / "adw_prompt.py").exists())
        self.assertTrue((self.target / ".claude" / "skills" / "sssf" / "SKILL.md").exists())
        log = git(self.target, ["log", "--oneline"], env=self.env)
        self.assertEqual(len(log.splitlines()), 1)
        tracked = git(self.target, ["ls-files"], env=self.env)
        self.assertIn("apps/inkwell/server.ts", tracked)
        self.assertIn("justfile", tracked)
        for path in self.target.rglob("*"):
            self.assertFalse(path.name.startswith("._"), path)
            self.assertNotEqual(path.name, ".DS_Store", path)

    def test_copied_skill_resources_match_current_source_bytes(self):
        prepare_example_target(self.target, self.env)
        source_hashes = {
            str(p.relative_to(SKILL)): sha256(p.read_bytes()).hexdigest()
            for p in sorted(SKILL.rglob("*"))
            if p.is_file() and not _excluded(p)
        }
        installed_root = self.target / ".claude" / "skills" / "sssf"
        for rel, expected in source_hashes.items():
            actual = sha256((installed_root / rel).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, rel)


class ReinstallTests(FactoryTestCase):
    def test_reinstall_preserves_every_byte_and_reports_skips(self):
        prepare_example_target(self.target, self.env)
        before = _tree_hashes(self.target)
        result = stamp(self.target, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped", result.stdout)
        self.assertEqual(_tree_hashes(self.target), before)


class OldInstallationTests(FactoryTestCase):
    def test_old_example_justfile_and_user_files_are_preserved(self):
        pinned_justfile = _example_blob("justfile")
        (self.target / "justfile").write_bytes(pinned_justfile)
        config = self.target / "adws/adw_sssf_config/sssf.config.yaml"
        config.parent.mkdir(parents=True)
        config.write_text("# operator-owned config\nuser-edit: keep me\n")
        prompt = self.target / "adws/adw_data/prompt_engineering/scout/system.md"
        prompt.parent.mkdir(parents=True)
        prompt.write_text("operator-owned prompt bytes\n")

        result = stamp(self.target, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("skipped", result.stdout)
        self.assertEqual((self.target / "justfile").read_bytes(), pinned_justfile)
        self.assertEqual(config.read_text(), "# operator-owned config\nuser-edit: keep me\n")
        self.assertEqual(prompt.read_text(), "operator-owned prompt bytes\n")

        names = recipe_names(self.target, self.env)
        self.assertNotIn("demo", names,
                         "old justfile was silently upgraded; skip policy forbids that")
        self.assertIn("cc", names)


class RecipeLineageTests(FactoryTestCase):
    def test_canonical_set_is_example_set_minus_cc_ipi_plus_demo(self):
        stamp(self.target, self.env).check_returncode()
        canonical = recipe_names(self.target, self.env)
        with tempfile.TemporaryDirectory(prefix="sssf-example-just-") as tmp:
            tmp = Path(tmp)
            (tmp / "justfile").write_bytes(_example_blob("justfile"))
            result = subprocess.run(
                ["just", "--justfile", "justfile", "--summary"],
                cwd=tmp, env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        example = set(result.stdout.split())
        self.assertEqual(EXAMPLE["example_recipes"], sorted(example))
        self.assertEqual(canonical - {"demo", "smoke-real-pi"},
                         example - {"cc", "ipi"})


class PathWithSpacesTests(FactoryTestCase):
    def test_fresh_install_works_from_a_target_path_with_spaces(self):
        target = self._scratch / "target with spaces"
        target.mkdir()
        before = export_example(ROOT, target)
        result = stamp(target, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        for path, expected in before.items():
            self.assertEqual(
                sha256((target / path).read_bytes()).hexdigest(), expected, path)
        self.assertEqual((target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())


def _excluded(path: Path) -> bool:
    """Mirror prepare_example_target's exclusion rules for the source manifest."""
    from tests.support.example import excluded_name
    return any(excluded_name(part) for part in path.parts)
