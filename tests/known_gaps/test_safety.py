"""M2-PERM known-gap reproductions: what permission enforcement misses today.

Each setUp runs the reproduction once and registers cleanup; the test method
holds ONLY the desired invariant. A failing assertion here is the defect —
that is why these tests are expected failures, recorded in docs/known-gaps.md.
"""
from __future__ import annotations

import unittest
from types import SimpleNamespace

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import permissions  # noqa: E402
from adw_modules.data_types import (  # noqa: E402
    AgentConfig,
    PromptEngineering,
)
from tests.support.runtime import (  # noqa: E402
    RuntimeTestCase,
    SCENARIO_USAGE,
    ScenarioOptions,
    execute_scenario,
    responses,
)

VALID = '{"status":"success","summary":"done"}'


def read_only_agent() -> AgentConfig:
    return AgentConfig(name="scout", writes=[],
                       prompt_engineering=PromptEngineering(
                           system="prompts/system.md", user="prompts/user.md"))


class NumstatIdenticalRewriteReproduction(RuntimeTestCase):
    """M2-PERM-01 — numstat fingerprints cannot see same-shape rewrites."""

    def setUp(self) -> None:
        super().setUp()
        self.run_stub = SimpleNamespace(repo_root=self.target, cfg=None)
        (self.target / "sample.txt").write_text("line one\nline two\n")
        self.before = permissions.snapshot(self.run_stub)
        # Different bytes, identical numstat (+2 -1 both times).
        (self.target / "sample.txt").write_text("line ONE\nline TWO\n")
        self.after = permissions.snapshot(self.run_stub)

    @unittest.expectedFailure
    def test_identical_numstat_rewrites_are_reported(self):
        self.assertIn("sample.txt",
                      permissions.changed_paths(self.before, self.after))


class UntrackedChangeReproduction(RuntimeTestCase):
    """M2-PERM-02 — an untracked file's content change is invisible."""

    def setUp(self) -> None:
        super().setUp()
        self.run_stub = SimpleNamespace(repo_root=self.target, cfg=None)
        (self.target / "notes.txt").write_text("version one\n")
        self.before = permissions.snapshot(self.run_stub)
        (self.target / "notes.txt").write_text("version two\n")
        self.after = permissions.snapshot(self.run_stub)

    @unittest.expectedFailure
    def test_changed_untracked_file_is_reported(self):
        self.assertIn("notes.txt",
                      permissions.changed_paths(self.before, self.after))


class IgnoredFileEnforcementReproduction(RuntimeTestCase):
    """M2-PERM-03 — enforcement cannot see gitignored paths at all."""

    def setUp(self) -> None:
        super().setUp()
        self.run_stub = SimpleNamespace(repo_root=self.target, cfg=None)
        with (self.target / ".gitignore").open("a") as gitignore:
            gitignore.write("\nignored.txt\n")
        (self.target / "ignored.txt").write_text("version one\n")
        self.before = permissions.snapshot(self.run_stub)
        (self.target / "ignored.txt").write_text("version two\n")
        self.after = permissions.snapshot(self.run_stub)

    @unittest.expectedFailure
    def test_ignored_file_modification_is_caught(self):
        with self.assertRaises(permissions.PermissionBreach):
            permissions.enforce(self.run_stub, None, read_only_agent(),
                                self.before)


class EnforcementAfterParseExhaustionReproduction(RuntimeTestCase):
    """M2-PERM-04 — a write that happened before a parse exhaustion is
    never audited, because enforcement runs only after a clean parse."""

    def setUp(self) -> None:
        super().setUp()
        # Every send is malformed, but the FIRST send already wrote outside
        # the read-only allowlist: enforcement must run even when parsing
        # exhausts. Today the RuntimeError from parsing preempts it entirely.
        first = {"text": "nope", "exit_code": 0, "usage": SCENARIO_USAGE,
                 "events": [], "writes": [{"path": "sample.txt",
                                           "text": "vandalized"}]}
        scenario = {"responses": [first,
                                  *responses("nope", "nope")["responses"]]}
        self.result = execute_scenario(self, scenario,
                                       ScenarioOptions(writes=[]))

    @unittest.expectedFailure
    def test_enforcement_still_runs_after_exhausted_json_parsing(self):
        self.assertIsInstance(self.result.error, permissions.PermissionBreach)
        self.assertEqual((self.target / "sample.txt").read_text(), "original\n")
