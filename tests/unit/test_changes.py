"""Deterministic change capture, exercised in scratch Git repos only."""
from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from tests.support.imports import bootstrap

bootstrap()
from tests.support.runtime import RuntimeTestCase

from adw_modules import changes
from adw_modules.data_types import ChangeCapture


def handoff_stub(directory: Path) -> SimpleNamespace:
    """changes.capture needs only the handoff dir; git state comes from cwd."""
    return SimpleNamespace(context_handoff_dir=directory)


class ResolveBaseTests(RuntimeTestCase):
    def test_missing_repo_is_an_error_never_a_silent_empty_diff(self):
        outside = self._scratch / "not-a-repo"
        outside.mkdir()
        import os
        previous = os.getcwd()
        os.chdir(outside)
        self.addCleanup(os.chdir, previous)
        with self.assertRaises(RuntimeError) as caught:
            changes.resolve_base("main")
        self.assertIn("not a git repository", str(caught.exception))

    def test_missing_ref_is_an_error_naming_the_ref(self):
        with self.assertRaises(RuntimeError) as caught:
            changes.resolve_base("no-such-ref")
        self.assertIn("no-such-ref", str(caught.exception))


class CaptureTests(RuntimeTestCase):
    def setUp(self) -> None:
        super().setUp()
        # Freeze the base branch name before any test checks out a feature
        # branch: the `branch` property reports whatever HEAD is on NOW.
        self.base_branch = self.branch

    def capture(self, **param_overrides):
        handoff = self._scratch / "handoff"
        handoff.mkdir(exist_ok=True)
        params = ChangeCapture(base=self.base_branch, **param_overrides)
        return changes.capture(handoff_stub(handoff), params)

    def test_dirty_base_branch_captures_the_uncommitted_working_tree(self):
        (self.target / "sample.txt").write_text("changed\n")
        captured = self.capture()
        self.assertEqual(captured.files, ["sample.txt"])
        self.assertEqual((captured.insertions, captured.deletions), (1, 1))
        self.assertIn("uncommitted working tree", captured.base.reason)

    def test_feature_branch_ahead_of_base_diffs_every_commit_since(self):
        git = self._git
        git(["checkout", "-b", "feature"])
        (self.target / "feature.txt").write_text("one\ntwo\nthree\n")
        git(["add", "-A"])
        git(["commit", "-m", "feature work"])
        captured = self.capture()
        self.assertIn("feature.txt", captured.files)
        self.assertEqual(captured.insertions, 3)
        self.assertIn("HEAD is ahead", captured.base.reason)
        # The base commit is the divergence point, not the feature commit.
        merge_base = self._git(["merge-base", self.base_branch, "HEAD"]).strip()
        self.assertEqual(captured.base.commit, merge_base)

    def test_clean_tree_falls_back_to_the_last_commit(self):
        (self.target / "sample.txt").write_text("committed work\n")
        self._git(["add", "-A"])
        self._git(["commit", "-m", "committed work"])
        captured = self.capture()
        head_parent = self._git(["rev-parse", "HEAD~1"]).strip()
        self.assertEqual(captured.base.commit, head_parent)
        self.assertIn("falling back to the last commit", captured.base.reason)
        # The diff answers "what was just done": the last commit's changes.
        self.assertEqual(captured.files, ["sample.txt"])

    def test_untracked_files_are_included_by_default(self):
        (self.target / "new.txt").write_text("brand new\n")
        captured = self.capture()
        self.assertIn("new.txt", captured.untracked)
        self.assertNotIn("new.txt", captured.files)

    def test_untracked_files_can_be_excluded(self):
        (self.target / "new.txt").write_text("brand new\n")
        captured = self.capture(include_untracked=False)
        self.assertEqual(captured.untracked, [])

    def test_diff_is_truncated_at_the_two_line_limit(self):
        (self.target / "sample.txt").write_text("a\nb\nc\nd\ne\n")
        captured = self.capture(max_diff_lines=2)
        self.assertTrue(captured.truncated)
        self.assertIn("[truncated at 2 lines of",
                      Path(captured.diff_path).read_text())

    def test_artifact_lands_in_the_supplied_absolute_handoff_dir(self):
        handoff = self._scratch / "explicit-handoff"
        handoff.mkdir()
        (self.target / "sample.txt").write_text("changed\n")
        params = ChangeCapture(base=self.base_branch)
        captured = changes.capture(handoff_stub(handoff), params)
        self.assertTrue(captured.diff_path.startswith(str(handoff)))
        artifact = Path(handoff / "changes.diff")
        self.assertTrue(artifact.is_file())
        contents = artifact.read_text()
        self.assertIn(f"changes since {captured.base.label}", contents)
        self.assertIn(captured.base.reason, contents)
        self.assertIn("## stat", contents)
        self.assertIn("## untracked files", contents)
        self.assertIn("## diff", contents)

    def _git(self, args: list[str]) -> str:
        from tests.support.factory import git
        return git(self.target, args, self.env)


if __name__ == "__main__":
    unittest.main()
