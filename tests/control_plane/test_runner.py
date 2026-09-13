"""Run persistence and outcome semantics against a real stamped target."""
from __future__ import annotations

import json
import sqlite3
import unittest

from tests.support.imports import bootstrap

bootstrap()

from adw_modules.data_types import EventRecord, PhaseParams  # noqa: E402
from tests.support.runtime import RuntimeTestCase, make_run  # noqa: E402


def inspect_phase(description: str = "Record evidence before finishing") -> PhaseParams:
    return PhaseParams(name="inspect", kind="code", owner="test",
                       description=description)


class RunnerTests(RuntimeTestCase):
    def test_phase_is_visible_to_an_independent_reader(self):
        run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(run.tracer.conn.close)
        with run.phase(inspect_phase()):
            with sqlite3.connect(run.tracer.db_path) as reader:
                status = reader.execute(
                    "SELECT status FROM phases WHERE adw_id=?", (run.adw_id,)
                ).fetchone()[0]
            self.assertEqual(status, "running")
        self.assertEqual(run.finish(), 0)

    def test_finished_session_is_success_and_reopenable(self):
        run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(run.tracer.conn.close)
        with run.phase(inspect_phase()):
            pass
        self.assertEqual(run.finish(), 0)
        # A fresh reader can open the db independently.
        with sqlite3.connect(run.tracer.db_path) as reader:
            status = reader.execute(
                "SELECT status FROM sessions WHERE adw_id=?", (run.adw_id,)
            ).fetchone()[0]
        self.assertEqual(status, "success")

    def test_joining_a_completed_run_appends_the_phase_sequence(self):
        first = make_run(self.target, "a1b2c3d4")
        self.addCleanup(first.tracer.conn.close)
        with first.phase(inspect_phase("first ADW")):
            pass
        first.finish()

        second = make_run(self.target, "a1b2c3d4")
        with second.phase(inspect_phase("second ADW joins")):
            pass
        second.finish()
        rows = second.tracer.conn.execute(
            "SELECT seq, phase_id, name FROM phases WHERE adw_id=? ORDER BY seq",
            ("a1b2c3d4",)).fetchall()
        self.assertEqual([seq for seq, _, _ in rows], [1, 2])
        self.assertEqual(len({phase_id for _, phase_id, _ in rows}), 2)

    def test_not_accepted_run_returns_one_and_records_why(self):
        run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(run.tracer.conn.close)
        with run.phase(inspect_phase()):
            pass
        code = run.finish(accepted=False, reason="the suite was red")
        self.assertEqual(code, 1)
        status = run.tracer.conn.execute(
            "SELECT status FROM sessions WHERE adw_id=?", (run.adw_id,)
        ).fetchone()[0]
        self.assertEqual(status, "fail")
        events = run.tracer.conn.execute(
            "SELECT name, payload_json FROM events WHERE type='error'").fetchall()
        self.assertIn(("not_accepted", json.dumps({"reason": "the suite was red"})),
                      events)

    def test_raising_inside_a_phase_records_phase_and_session_fail(self):
        run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(run.tracer.conn.close)
        with self.assertRaises(RuntimeError):
            with run.phase(inspect_phase()):
                raise RuntimeError("exploded during work")
        phase_status, phase_error = run.tracer.conn.execute(
            "SELECT status, error FROM phases WHERE adw_id=?",
            (run.adw_id,)).fetchone()
        self.assertEqual(phase_status, "fail")
        self.assertIn("exploded during work", phase_error)
        session_status = run.tracer.conn.execute(
            "SELECT status FROM sessions WHERE adw_id=?", (run.adw_id,)
        ).fetchone()[0]
        self.assertEqual(session_status, "fail")

    def test_session_add_usage_accumulates_across_calls(self):
        run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(run.tracer.conn.close)
        run.add_usage(10, 0.01)
        run.add_usage(2, 0.002)
        tokens, cost = run.tracer.conn.execute(
            "SELECT total_tokens, total_cost FROM sessions WHERE adw_id=?",
            (run.adw_id,)).fetchone()
        self.assertEqual((tokens, cost), (12, 0.012))


if __name__ == "__main__":
    unittest.main()
