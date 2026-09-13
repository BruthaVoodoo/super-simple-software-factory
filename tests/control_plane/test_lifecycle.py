"""Lifecycle behavior that needs a real OS process: signals to a supervised ADW."""
from __future__ import annotations

import os
import signal
import sqlite3
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

PARKED_ENVELOPE = '{"status":"success","summary":"parked"}'


def _parked_scenario(release_path: str) -> dict:
    return {"responses": [{
        "text": PARKED_ENVELOPE, "exit_code": 0, "usage": SCENARIO_USAGE,
        "events": [], "writes": [], "wait_for_release": release_path,
    }]}


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
