"""Commit scope: only the run's own paths are staged. Scratch repos only."""
from __future__ import annotations

import unittest

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import git_helper  # noqa: E402
from adw_modules.permissions import snapshot  # noqa: E402
from tests.support.factory import git  # noqa: E402
from tests.support.runtime import RuntimeTestCase, make_run  # noqa: E402


def git_helper_snapshot(run):
    return snapshot(run)


class CommitScopeTests(RuntimeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(self.run.tracer.conn.close)

    def test_pre_existing_dirty_file_is_never_committed(self):
        (self.target / "sample.txt").write_text("operator's uncommitted work\n")
        self.run.tree_baseline = git_helper_snapshot(self.run)   # run starts
        (self.target / "feature.txt").write_text("the run's work\n")
        sha = git_helper.commit_paths(self.run.changed_paths(), "run work")
        self.assertTrue(sha)
        staged = git(self.target, ["show", "--name-only", "--format=", "HEAD"],
                     self.env)
        self.assertIn("feature.txt", staged)
        self.assertNotIn("sample.txt", staged)
        self.assertEqual((self.target / "sample.txt").read_text(),
                         "operator's uncommitted work\n")

    def test_pre_existing_untracked_file_is_never_committed(self):
        (self.target / "loose.txt").write_text("pre-existing untracked\n")
        self.run.tree_baseline = git_helper_snapshot(self.run)   # run starts
        (self.target / "feature.txt").write_text("the run's work\n")
        git_helper.commit_paths(self.run.changed_paths(), "run work")
        staged = git(self.target, ["show", "--name-only", "--format=", "HEAD"],
                     self.env)
        self.assertNotIn("loose.txt", staged)

    def test_commit_with_no_run_changes_is_refused(self):
        self.run.tree_baseline = git_helper_snapshot(self.run)
        with self.assertRaises(RuntimeError) as caught:
            git_helper.commit_paths(self.run.changed_paths(), "nothing")
        self.assertIn("nothing to commit", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
