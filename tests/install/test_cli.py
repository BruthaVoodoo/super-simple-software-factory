"""The sssf CLI entry point, invoked through uv like an operator would."""
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sssf_cli import manifest  # noqa: E402

from tests.support.environment import child_env  # noqa: E402
from tests.support.factory import ROOT, SKILL, TEMPLATE, FactoryTestCase, stamp  # noqa: E402


def run_cli(*args: str, cwd=None) -> subprocess.CompletedProcess[str]:
    cwd_path = Path(cwd) if cwd else ROOT
    # HOME must never land inside the target: some tests assert on the
    # target's exact tree, and child_env() creates the home it is given.
    home = Path(tempfile.mkdtemp(prefix="sssf-cli-home-"))
    return subprocess.run(
        ["uv", "run", "--locked", "--project", str(ROOT), "sssf", *args],
        cwd=str(cwd_path), env=child_env(home), capture_output=True,
        text=True, timeout=60)


class CliEntryPointTests(FactoryTestCase):
    def test_version_prints_and_exits_zero(self):
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().startswith("sssf "))

    def test_unknown_command_exits_two_with_usage(self):
        result = run_cli("nonsense")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr.lower())

    def test_subcommands_exist_in_usage(self):
        result = run_cli("--help")
        for command in ("init", "update", "doctor", "install-skill"):
            self.assertIn(command, result.stdout)


class InitTests(FactoryTestCase):
    def test_init_stamps_and_writes_the_manifest(self):
        result = run_cli("init", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())
        loaded = manifest.load(self.target)
        self.assertIsNotNone(loaded)
        self.assertIn("justfile", loaded.entries)
        self.assertEqual(loaded.entries["justfile"].target_hash,
                         sha256((TEMPLATE / "justfile").read_bytes()).hexdigest())
        self.assertEqual(loaded.entries["justfile"].source_hash,
                         sha256((TEMPLATE / "justfile").read_bytes()).hexdigest())

    def test_init_matches_the_direct_installer_byte_for_byte(self):
        """Spec: direct installer and sssf init produce equivalent files."""
        direct = self.target / "direct"
        cli = self.target / "cli"
        direct.mkdir()
        cli.mkdir()
        stamp(direct, child_env(direct / ".home"))
        result = run_cli("init", cwd=str(cli))
        self.assertEqual(result.returncode, 0, result.stderr)
        for path in ("justfile", "adws/adw_prompt.py",
                     "adws/adw_sssf_config/sssf.config.yaml", ".env.sample"):
            self.assertEqual((direct / path).read_bytes(),
                             (cli / path).read_bytes(), path)
        self.assertTrue((cli / ".sssf" / "manifest.json").is_file())

    def test_direct_installer_still_works_and_writes_no_manifest(self):
        result = stamp(self.target, self.env)          # the M1 helper
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(manifest.load(self.target))


class InitDryRunTests(FactoryTestCase):
    def test_dry_run_reports_writes_and_skips_without_touching_anything(self):
        (self.target / "justfile").write_bytes(b"operator-owned\n")
        before = sorted(str(p.relative_to(self.target))
                        for p in self.target.rglob("*"))
        result = run_cli("init", "--dry-run", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would stamp", result.stdout.lower())
        self.assertIn("would skip", result.stdout.lower())
        self.assertIn("justfile", result.stdout)   # listed as a would-skip
        self.assertIsNone(manifest.load(self.target))   # nothing was written
        self.assertFalse((self.target / "adws").exists())
        self.assertEqual(
            sorted(str(p.relative_to(self.target)) for p in self.target.rglob("*")),
            before)


class InstallSkillTests(FactoryTestCase):
    def test_skill_copies_with_exclusions_and_matches_source_bytes(self):
        result = run_cli("install-skill", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.target / ".claude" / "skills" / "sssf"
        self.assertTrue((installed / "SKILL.md").is_file())
        self.assertEqual((installed / "SKILL.md").read_bytes(),
                         (SKILL / "SKILL.md").read_bytes())
        for path in installed.rglob("*"):
            self.assertFalse(path.name.startswith("._"), path)
            self.assertNotIn("__pycache__", path.parts)

    def test_existing_skill_is_skipped_without_force(self):
        installed = self.target / ".claude" / "skills" / "sssf" / "SKILL.md"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"operator-owned skill\n")
        result = run_cli("install-skill", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(installed.read_bytes(), b"operator-owned skill\n")
        self.assertIn("skip", result.stdout.lower())

    def test_force_overwrites_the_skill(self):
        installed = self.target / ".claude" / "skills" / "sssf" / "SKILL.md"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"operator-owned skill\n")
        result = run_cli("install-skill", "--force", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(installed.read_bytes(), (SKILL / "SKILL.md").read_bytes())


if __name__ == "__main__":
    unittest.main()
