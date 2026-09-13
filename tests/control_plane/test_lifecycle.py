"""Lifecycle behavior that needs a real OS process: signals to a supervised ADW."""
from __future__ import annotations

import os
import signal
import sqlite3
import time
import unittest

from tests.support.imports import bootstrap

bootstrap()

from tests.support.runtime import (  # noqa: E402
    SCENARIO_USAGE,
    RuntimeTestCase,
    make_run,
    pid_alive,
    supervised_adw,
    wait_until,
)
from adw_modules import agents, git_helper, session  # noqa: E402
from tests.support.factory import git  # noqa: E402

PARKED_ENVELOPE = '{"status":"success","summary":"parked"}'


def _parked_scenario(release_path: str) -> dict:
    return {"responses": [{
        "text": PARKED_ENVELOPE, "exit_code": 0, "usage": SCENARIO_USAGE,
        "events": [], "writes": [], "wait_for_release": release_path,
    }]}


class BranchIsolationTests(RuntimeTestCase):
    """session.ensure installs process-global signal handlers — acceptable
    here because these runs finish cleanly within the test."""

    def test_isolated_run_commits_on_its_own_branch(self):
        original_branch = self.branch
        original_sha = git(self.target, ["rev-parse", "HEAD"], self.env).strip()
        cfg = agents.load_config()
        run = session.ensure(cfg, adw_id="isol8run", isolate_branch=True)
        self.addCleanup(run.tracer.conn.close)
        self.assertEqual(git_helper.current_branch(), "sssf/isol8run")
        (self.target / "feature.txt").write_text("run work\n")
        git_helper.commit_paths(run.changed_paths(), "run work")
        # The operator's branch ref did not move.
        self.assertEqual(
            git(self.target, ["rev-parse", original_branch], self.env).strip(),
            original_sha)

    def test_read_only_runs_stay_in_place(self):
        before = self.branch
        cfg = agents.load_config()
        run = session.ensure(cfg, adw_id="inplace1")
        self.addCleanup(run.tracer.conn.close)
        self.assertEqual(git_helper.current_branch(), before)


class InterruptedChildTerminationTests(RuntimeTestCase):
    """M2-PROC-01 — interrupting an ADW must actually terminate the
    coding-agent child, not merely mark the process row ended."""

    def setUp(self) -> None:
        super().setUp()
        never = self._scratch / "release" / "never-created"
        self.handle = supervised_adw(self, "proc-run",
                                     _parked_scenario(str(never)))
        self.assertTrue(wait_until(self._double_parked, 30),
                        "the double never parked inside the supervised ADW")
        with sqlite3.connect(self.handle.db_path) as conn:
            (self.double_pid,) = conn.execute(
                "SELECT pid FROM processes WHERE adw_id=? AND kind='agent' "
                "AND ended_at IS NULL", (self.handle.adw_id,)).fetchone()
        self.handle.signal(signal.SIGTERM)
        self.exit_code = self.handle.wait(timeout=5)

    def _double_parked(self) -> bool:
        try:
            with sqlite3.connect(self.handle.db_path) as conn:
                rows = conn.execute(
                    "SELECT pid FROM processes WHERE adw_id=? AND kind='agent' "
                    "AND ended_at IS NULL", (self.handle.adw_id,)).fetchall()
        except sqlite3.OperationalError:
            return False        # the child has not created the schema yet
        return bool(rows)

    def test_interrupted_adw_child_actually_terminates(self):
        self.assertEqual(self.exit_code, 143)
        deadline = time.monotonic() + 5.0
        while pid_alive(self.double_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(pid_alive(self.double_pid),
                         "the trace says ended, but the coding-agent child is alive")


class SupervisedSignalTests(RuntimeTestCase):
    """Signal behavior lives in a supervised child because session.ensure
    installs process-global signal handlers there — not in this process."""

    def test_signal_to_controller_owned_adw_records_outcomes_separately(self):
        never = self._scratch / "release" / "never-created"
        handle = supervised_adw(self, "signal-run", _parked_scenario(str(never)))

        # A second run in the SAME database, with a live process row of its own.
        other = make_run(self.target, "other-run-1")
        self.addCleanup(other.tracer.conn.close)
        other.tracer.process_start("other-run-1", "adw", "", os.getpid(),
                                   "other in-process run")

        def double_parked() -> bool:
            with sqlite3.connect(handle.db_path) as conn:
                rows = conn.execute(
                    "SELECT pid FROM processes WHERE adw_id=? AND kind='agent' "
                    "AND ended_at IS NULL", (handle.adw_id,)).fetchall()
            return bool(rows)

        self.assertTrue(wait_until(double_parked, 30),
                        "the double never parked inside the supervised ADW")

        handle.signal(signal.SIGTERM)
        code = handle.wait(timeout=5)   # TimeoutExpired fails the test — bounded
        self.assertEqual(code, 143)     # SystemExit(128 + SIGTERM)

        with sqlite3.connect(handle.db_path) as conn:
            status = conn.execute(
                "SELECT status FROM sessions WHERE adw_id='signal-run'"
            ).fetchone()[0]
            signal_run_rows = conn.execute(
                "SELECT kind, ended_at FROM processes WHERE adw_id='signal-run'"
            ).fetchall()
            other_row = conn.execute(
                "SELECT pid, ended_at FROM processes WHERE adw_id='other-run-1'"
            ).fetchall()
        self.assertEqual(status, "fail")
        self.assertTrue(signal_run_rows)
        self.assertTrue(all(ended is not None for _, ended in signal_run_rows),
                        "every signal-run process row must be closed")

        # One run's death must not close (or signal) another run's processes.
        self.assertEqual(len(other_row), 1)
        other_pid, other_ended = other_row[0]
        self.assertIsNone(other_ended)
        self.assertTrue(pid_alive(other_pid),
                        "the other run's process was signalled or killed")


if __name__ == "__main__":
    unittest.main()
