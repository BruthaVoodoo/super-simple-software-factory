"""Permission policy boundaries and enforcement against a real scratch repo."""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from tests.support.imports import bootstrap

bootstrap()
from tests.support.runtime import RuntimeTestCase

from adw_modules import permissions
from adw_modules.data_types import AgentConfig, PromptEngineering, SSSFConfig


def agent(name: str = "scout", writes=None) -> AgentConfig:
    return AgentConfig(name=name, writes=writes,
                       prompt_engineering=PromptEngineering(
                           system="prompts/system.md", user="prompts/user.md"))


def config(**default_overrides) -> SSSFConfig:
    return SSSFConfig(defaults={"data_dir": "adws/adw_data", **default_overrides})


class PermittedPathTests(unittest.TestCase):
    """policy table: writes None/[]/exact/prefix/glob/protected/runtime-dir."""

    def test_writes_none_is_unrestricted_away_from_protected_paths(self):
        cfg = config()
        self.assertTrue(permissions.permitted("src/anything.ts",
                                              agent(writes=None), cfg))

    def test_writes_none_still_cannot_touch_protected_paths(self):
        cfg = config()
        self.assertFalse(permissions.permitted("adws/adw_prompt.py",
                                               agent(writes=None), cfg))

    def test_writes_empty_list_is_read_only(self):
        cfg = config()
        self.assertFalse(permissions.permitted("sample.txt", agent(writes=[]), cfg))

    def test_exact_path_grant(self):
        cfg = config()
        self.assertTrue(permissions.permitted("sample.txt",
                                              agent(writes=["sample.txt"]), cfg))
        self.assertFalse(permissions.permitted("other.txt",
                                               agent(writes=["sample.txt"]), cfg))

    def test_trailing_slash_grants_a_directory_prefix(self):
        cfg = config()
        scout = agent(writes=["docs/"])
        self.assertTrue(permissions.permitted("docs/a/b.md", scout, cfg))
        self.assertFalse(permissions.permitted("docsitory/x", scout, cfg))

    def test_single_star_does_not_cross_separators(self):
        cfg = config()
        scout = agent(writes=["src/*.ts"])
        self.assertTrue(permissions.permitted("src/a.ts", scout, cfg))
        self.assertFalse(permissions.permitted("src/deep/a.ts", scout, cfg))

    def test_double_star_crosses_directories(self):
        cfg = config()
        scout = agent(writes=["src/**"])
        self.assertTrue(permissions.permitted("src/a.ts", scout, cfg))
        self.assertTrue(permissions.permitted("src/deep/a.ts", scout, cfg))
        self.assertFalse(permissions.permitted("lib/a.ts", scout, cfg))

    def test_naming_a_protected_path_unlocks_exactly_it(self):
        cfg = config()
        machinery = agent(name="builder", writes=["adws/adw_modules/operations.py"])
        self.assertTrue(permissions.permitted("adws/adw_modules/operations.py",
                                              machinery, cfg))
        self.assertFalse(permissions.permitted("adws/adw_modules/tracer.py",
                                               machinery, cfg))

    def test_runtime_directory_is_always_writable(self):
        cfg = config()
        for writer in (agent(writes=[]), agent(writes=["unrelated/"]),
                       agent(writes=None)):
            with self.subTest(writes=writer.writes):
                self.assertTrue(permissions.permitted(
                    "adws/adw_data/sessions/x/envelope.json", writer, cfg))
                self.assertTrue(permissions.permitted(
                    "adws/adw_data/anything", writer, cfg))

    def test_changed_paths_report_every_difference(self):
        before = {"dirty.txt": "1,2", "gone.txt": "0,1", "same.txt": "3,0",
                  "untracked": "untracked"}
        after = {"dirty.txt": "5,2", "same.txt": "3,0", "new.txt": "untracked"}
        self.assertEqual(
            permissions.changed_paths(before, after),
            ["dirty.txt", "gone.txt", "new.txt", "untracked"])


class EnforcementTests(RuntimeTestCase):
    """enforce() against the real scratch repo: detect, restore, then raise."""

    def setUp(self) -> None:
        super().setUp()
        self.cfg = config()
        self.run_stub = SimpleNamespace(repo_root=self.target, cfg=self.cfg)

    def snapshot(self) -> dict[str, str]:
        return permissions.snapshot(self.run_stub)

    def test_clean_read_only_agent_passes_with_no_touched_paths(self):
        before = self.snapshot()
        scout = agent(writes=[])
        touched = permissions.enforce(self.run_stub, None, scout, before)
        self.assertEqual(touched, [])

    def test_read_only_agent_editing_clean_file_breaches_and_restores(self):
        before = self.snapshot()
        scout = agent(writes=[])
        (self.target / "sample.txt").write_text("vandalized\n")
        with self.assertRaises(permissions.PermissionBreach) as caught:
            permissions.enforce(self.run_stub, None, scout, before)
        self.assertIn("read-only", str(caught.exception))
        self.assertEqual((self.target / "sample.txt").read_text(), "original\n")

    def test_granted_write_is_reported_not_rejected(self):
        before = self.snapshot()
        writer = agent(name="builder", writes=["sample.txt"])
        (self.target / "sample.txt").write_text("rewritten by builder\n")
        touched = permissions.enforce(self.run_stub, None, writer, before)
        self.assertEqual(touched, ["sample.txt"])

    def test_untracked_authorized_write_is_kept(self):
        before = self.snapshot()
        writer = agent(name="builder", writes=["notes/"])
        (self.target / "notes").mkdir()
        (self.target / "notes/idea.md").write_text("captured\n")
        touched = permissions.enforce(self.run_stub, None, writer, before)
        self.assertEqual(touched, ["notes/idea.md"])


if __name__ == "__main__":
    unittest.main()
