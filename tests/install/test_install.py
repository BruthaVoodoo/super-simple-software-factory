"""Installer behavior: fresh stamping and non-destructive re-install."""
from __future__ import annotations

from tests.support.factory import TEMPLATE, FactoryTestCase, stamp


class InstallTests(FactoryTestCase):
    def test_fresh_justfile_is_template_bytes(self):
        result = stamp(self.target, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())

    def test_existing_justfile_is_preserved(self):
        path = self.target / "justfile"
        before = b"owned-by-project:\n    @echo keep-me\n"
        path.write_bytes(before)
        result = stamp(self.target, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertIn("skipped", result.stdout)

    def test_config_and_prompts_are_preserved(self):
        self.assertEqual(stamp(self.target, self.env).returncode, 0)
        config = self.target / "adws" / "adw_sssf_config" / "sssf.config.yaml"
        prompt = (self.target / "adws" / "adw_data" / "prompt_engineering"
                  / "scout" / "system.md")
        config_before = b"# user roster\n"
        prompt_before = prompt.read_bytes()
        config.write_bytes(config_before)
        second = stamp(self.target, self.env)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(config.read_bytes(), config_before)
        self.assertEqual(prompt.read_bytes(), prompt_before)

    def test_gitignore_entries_land_exactly_once(self):
        self.assertEqual(stamp(self.target, self.env).returncode, 0)
        self.assertEqual(stamp(self.target, self.env).returncode, 0)
        text = (self.target / ".gitignore").read_text()
        for entry in ("adws/adw_data/sessions/", "adws/adw_data/sssf.db*",
                      ".env", "__pycache__/", "*.pyc"):
            self.assertEqual(text.count(entry), 1, entry)

    def test_no_env_file_and_no_runtime_db_from_install(self):
        self.assertEqual(stamp(self.target, self.env).returncode, 0)
        self.assertFalse((self.target / ".env").exists())
        self.assertFalse((self.target / "adws" / "adw_data" / "sssf.db").exists())
        self.assertFalse((self.target / "adws" / "adw_data" / "sessions").exists())

    def test_every_template_file_lands_with_identical_bytes(self):
        self.assertEqual(stamp(self.target, self.env).returncode, 0)
        mapping = [
            (TEMPLATE / "adws", self.target / "adws"),
            (TEMPLATE / "prompt_engineering",
             self.target / "adws" / "adw_data" / "prompt_engineering"),
            (TEMPLATE / "harness_engineering",
             self.target / "adws" / "adw_data" / "harness_engineering"),
            (TEMPLATE / "sssf.config.yaml",
             self.target / "adws" / "adw_sssf_config" / "sssf.config.yaml"),
            (TEMPLATE / "env.sample", self.target / ".env.sample"),
            (TEMPLATE / "justfile", self.target / "justfile"),
        ]
        for source_root, target_root in mapping:
            if source_root.is_file():
                self.assertEqual(source_root.read_bytes(), target_root.read_bytes(),
                                 str(target_root))
                continue
            for source in source_root.rglob("*"):
                if source.is_dir() or "__pycache__" in source.parts:
                    continue
                # macOS AppleDouble junk regenerates next to freshly written
                # files on this volume; the installer skips it, so must we.
                if source.name.startswith("._") or source.name == ".DS_Store":
                    continue
                stamped = target_root / source.relative_to(source_root)
                self.assertTrue(stamped.exists(), str(stamped))
                self.assertEqual(source.read_bytes(), stamped.read_bytes(),
                                 str(stamped))
