"""Fixture traces: deterministic, contract-conformant, five canonical shapes."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
import unittest

from tests.support.environment import child_env
from tests.support.factory import ROOT, FactoryTestCase

FIXTURE_RUNS = ("fixture-success", "fixture-gate-fail", "fixture-parse-fail",
                "fixture-not-accepted", "fixture-running")


class FixtureTraceTests(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.out_dir = self.target / "fixtures"
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "fixture-trace.py"),
             str(self.out_dir)],
            cwd=str(self.target), env=child_env(self.target / ".home"),
            capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def query(self, sql: str, params: tuple = ()) -> list[tuple]:
        with sqlite3.connect(self.out_dir / "fixture.db") as conn:
            return conn.execute(sql, params).fetchall()

    def test_all_five_runs_exist_with_expected_statuses(self):
        rows = dict(self.query(
            "SELECT adw_id, status FROM sessions WHERE adw_id LIKE 'fixture-%'"))
        self.assertEqual(rows, {
            "fixture-success": "success",
            "fixture-gate-fail": "fail",
            "fixture-parse-fail": "fail",
            "fixture-not-accepted": "fail",
            "fixture-running": "running",
        })

    def test_failure_fixture_carries_evidence_the_ui_needs(self):
        gate_rows = self.query(
            "SELECT passed, checks_json FROM gate_results "
            "WHERE adw_id='fixture-gate-fail'")
        self.assertTrue(any(row[0] == 0 for row in gate_rows))
        self.assertTrue(all(row[1] for row in gate_rows))
        failed_phase = self.query(
            "SELECT status, error FROM phases WHERE adw_id='fixture-gate-fail' "
            "AND status='fail'")
        self.assertTrue(failed_phase and failed_phase[0][1])
        summaries = self.query(
            "SELECT payload_json FROM events WHERE adw_id='fixture-gate-fail' "
            "AND name='repair_summary'")
        self.assertTrue(summaries)

    def test_not_accepted_fixture_names_the_criterion(self):
        rows = self.query(
            "SELECT payload_json FROM events WHERE adw_id='fixture-not-accepted' "
            "AND name='not_accepted'")
        self.assertTrue(rows)
        self.assertIn("reason", rows[0][0])

    def test_success_fixture_has_spanned_tool_calls_and_quality_events(self):
        spans = self.query(
            "SELECT started_at, ended_at FROM events WHERE "
            "adw_id='fixture-success' AND type='tool_call'")
        self.assertTrue(all(started and ended for started, ended in spans))
        quality = self.query(
            "SELECT name FROM events WHERE adw_id='fixture-success' "
            "AND type='tool_call' AND name LIKE 'quality:%'")
        self.assertTrue(quality)

    def test_generation_is_deterministic(self):
        first_phases = sorted(self.query("SELECT adw_id, phase_id, seq, status FROM phases"))
        first_events = dict(self.query(
            "SELECT adw_id, COUNT(*) FROM events GROUP BY adw_id"))
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "fixture-trace.py"),
             str(self.out_dir)],
            cwd=str(self.target), env=child_env(self.target / ".home"),
            capture_output=True, text=True, timeout=60)
        second_phases = sorted(self.query("SELECT adw_id, phase_id, seq, status FROM phases"))
        second_events = dict(self.query(
            "SELECT adw_id, COUNT(*) FROM events GROUP BY adw_id"))
        self.assertEqual(first_phases, second_phases)
        # Regeneration must not double-append: events dedupe by generation.
        self.assertEqual(first_events, second_events)


if __name__ == "__main__":
    unittest.main()
