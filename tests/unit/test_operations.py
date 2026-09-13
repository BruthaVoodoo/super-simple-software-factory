"""Unit tests for no-agent operations and conservative process control."""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import unittest
from pathlib import Path
from unittest import mock

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import operations, process_control  # noqa: E402
from tests.support.factory import TEMPLATE, FactoryTestCase, stamp  # noqa: E402

_TRACER = TEMPLATE / "adws" / "adw_modules" / "tracer.py"


class _TwoRuns(FactoryTestCase):
    """Two isolated trace dbs, each with one session and two process rows."""

    def setUp(self) -> None:
        super().setUp()
        stamp(self.target, self.env).check_returncode()
        # Relative db paths in rosters resolve against the process cwd —
        # the same contract the ADW runtime uses from a target root.
        self._old_cwd = Path.cwd()
        os.chdir(self.target)
        self.addCleanup(os.chdir, self._old_cwd)
        self.dbs = {}
        for name, adw_id in (("first", "run-1a2b3c4d"), ("second", "run-9e8d7c6b")):
            db_dir = self.target / name / "adw_data"
            db_dir.mkdir(parents=True)
            db_path = db_dir / "sssf.db"
            connection = sqlite3.connect(db_path)
            connection.executescript(
                Path(_TRACER).read_text().split('SCHEMA = """')[1].split('"""')[0])
            connection.execute(
                "INSERT INTO sessions (adw_id, status, request, started_at) "
                "VALUES (?, 'running', 'inspect me', '2026-01-01T00:00:00')", (adw_id,))
            connection.execute(
                "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, "
                "status) VALUES (?, ?, 1, 'request', 'engineer', 'eng', 'success')",
                (f"{adw_id}_01_request", adw_id))
            connection.execute(
                "INSERT INTO events (event_id, adw_id, type, name, started_at) "
                "VALUES (?, ?, 'phase_start', 'request', '2026-01-01T00:00:00')",
                (f"evt_{name}", adw_id))
            connection.execute(
                "INSERT INTO processes (adw_id, kind, name, pid, command, started_at) "
                "VALUES (?, 'adw', '', 424242, 'adw_fake_target', '2026-01-01T00:00:00')",
                (adw_id,))
            connection.commit()
            connection.close()
            self.dbs[name] = db_path

    def _config_for(self, name: str) -> str:
        config = self.target / f"{name}.yaml"
        config.write_text(
            f"observability:\n  db: '{name}/adw_data/sssf.db'\n")
        return str(config)


class QueryViewTests(_TwoRuns):
    def test_selected_config_selects_the_right_db(self):
        first = operations.query_view(self._config_for("first"), "sessions", None)
        self.assertEqual([row["adw_id"] for row in first], ["run-1a2b3c4d"])
        second = operations.query_view(self._config_for("second"), "sessions", None)
        self.assertEqual([row["adw_id"] for row in second], ["run-9e8d7c6b"])

    def test_quote_in_adw_id_is_data_not_sql(self):
        weird = "run-1a'; drop table phases; --"
        config = self._config_for("first")
        db_path = self.dbs["first"]
        connection = sqlite3.connect(db_path)
        connection.execute(
            "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, status) "
            "VALUES ('p1', ?, 2, 'x', 'code', 'eng', 'success')", (weird,))
        connection.commit()
        connection.close()
        rows = operations.query_view(config, "phases", weird)
        self.assertEqual([row["name"] for row in rows], ["x"])
        still = sqlite3.connect(db_path).execute(
            "SELECT count(*) FROM phases").fetchone()[0]
        self.assertEqual(still, 2, "the quoted id must not execute as SQL")

    def test_missing_db_is_an_error_not_an_empty_database(self):
        config = self.target / "missing.yaml"
        config.write_text("observability:\n  db: 'nope/sssf.db'\n")
        with self.assertRaises(FileNotFoundError):
            operations.query_view(str(config), "sessions", None)
        self.assertFalse((self.target / "nope").exists())

    def test_reads_issue_zero_writes(self):
        config = self._config_for("first")
        before = self.dbs["first"].read_bytes()
        for view, adw_id in (("sessions", None), ("phases", "run-1a2b3c4d"),
                             ("tail", "run-1a2b3c4d"), ("procs", "run-1a2b3c4d")):
            operations.query_view(config, view, adw_id)
        # WAL means physical bytes may change (checkpointing); rows may not.
        connection = sqlite3.connect(self.dbs["first"])
        counts = connection.execute(
            "SELECT (SELECT count(*) FROM sessions), (SELECT count(*) FROM phases), "
            "(SELECT count(*) FROM events), (SELECT count(*) FROM processes)"
        ).fetchone()
        connection.close()
        self.assertEqual(counts, (1, 1, 1, 1))


class RostersTests(FactoryTestCase):
    def test_inherited_and_overridden_models_without_pi(self):
        directory = self.target / "rosters"
        directory.mkdir()
        (directory / "one.yaml").write_text(
            "defaults:\n"
            "  model: google/gemini-3.6-flash\n"
            "agents:\n"
            "  - name: planner\n"
            "    model: fireworks/kimi-k3\n"
            "  - name: builder\n")
        with mock.patch.object(operations, "_", create=True):
            rows = operations.rosters(directory)
        (row,) = rows
        self.assertEqual(row["agents"][0]["model"], "fireworks/kimi-k3")
        self.assertEqual(row["agents"][1]["model"], "google/gemini-3.6-flash")


class StopRunTests(FactoryTestCase):
    """Safety tests run with mocked inspection and os.kill — never real signals."""

    def setUp(self) -> None:
        super().setUp()
        stamp(self.target, self.env).check_returncode()
        db_dir = self.target / "adw_data"
        db_dir.mkdir(exist_ok=True)
        self.db_path = db_dir / "sssf.db"
        connection = sqlite3.connect(self.db_path)
        connection.executescript(
            Path(_TRACER).read_text().split('SCHEMA = """')[1].split('"""')[0])
        connection.close()
        self.config = str(self.target / "adws" / "adw_sssf_config" / "sssf.config.yaml")
        (self.target / "adws" / "adw_sssf_config").mkdir(parents=True, exist_ok=True)
        self.config = str(self.target / "adws" / "adw_sssf_config" / "sssf.config.yaml")
        (self.target / "adws" / "adw_sssf_config" / "sssf.config.yaml").write_text(
            "observability:\n  db: 'adw_data/sssf.db'\n")

    def _seed(self, adw_id: str, kind: str, pid: int, command: str) -> None:
        connection = sqlite3.connect(self.db_path)
        connection.execute(
            "INSERT INTO processes (adw_id, kind, name, pid, command, started_at) "
            "VALUES (?, ?, '', ?, ?, '2026-01-01T00:00:00')", (adw_id, kind, pid, command))
        connection.commit()
        connection.close()

    def _patch(self, ps_output: str):
        return (mock.patch.object(process_control, "_ps_command", return_value=ps_output),
                mock.patch.object(process_control, "_live_rows",
                                  return_value=[{"kind": "agent", "pid": 424242,
                                                 "command": "pi --session-id s"}]),
                mock.patch.object(process_control, "input", return_value="run-1a2b3c4d"),
                mock.patch.object(process_control.os, "kill", return_value=None))

    def test_wrong_session_dir_is_refused(self):
        self._seed("run-1a2b3c4d", "agent", 424242, "pi --session-id x")
        patch_ps, patch_rows, _patch_input, patch_kill = self._patch(
            "pi --session-dir /somewhere/else --session-id sssf-run-1a2b3c4d-scout")
        with patch_ps, patch_rows, patch_kill as fake_kill:
            code = process_control.stop_run(self.config, "run-1a2b3c4d")
        self.assertNotEqual(code, 0)
        fake_kill.assert_not_called()

    def test_wrong_repo_script_path_is_refused(self):
        self._seed("run-1a2b3c4d", "adw", 424242,
                   "/other/repo/adws/adw_scout.py --adw-id run-1a2b3c4d")
        patch_ps, patch_rows, _patch_input, patch_kill = self._patch(
            "/other/repo/adws/adw_scout.py --adw-id run-1a2b3c4d")
        with patch_ps, patch_rows, patch_kill as fake_kill:
            code = process_control.stop_run(self.config, "run-1a2b3c4d")
        self.assertNotEqual(code, 0)
        fake_kill.assert_not_called()

    def test_changed_identity_is_refused(self):
        self._seed("run-1a2b3c4d", "agent", 424242,
                   f"--session-dir {(self.target / 'adws/adw_data/sessions/run-1a2b3c4d').resolve()}")
        patch_ps, patch_rows, _patch_input, patch_kill = self._patch(
            "/bin/innocent-process --flag")
        with patch_ps, patch_rows, patch_kill as fake_kill:
            code = process_control.stop_run(self.config, "run-1a2b3c4d")
        self.assertNotEqual(code, 0)
        fake_kill.assert_not_called()

    def test_failed_confirmation_signals_nothing(self):
        session_dir = (self.target / "adws/adw_data/sessions/run-1a2b3c4d").resolve()
        self._seed("run-1a2b3c4d", "agent", 424242, f"--session-dir {session_dir}")
        patch_ps, patch_rows, patch_input, patch_kill = self._patch(
            f"pi --session-dir {session_dir}")
        with patch_ps, patch_rows, patch_kill as fake_kill, \
                mock.patch.object(process_control, "input", return_value="nope"):
            code = process_control.stop_run(self.config, "run-1a2b3c4d")
        self.assertNotEqual(code, 0)
        fake_kill.assert_not_called()

    def test_confirmed_kill_terms_agents_before_parent(self):
        session_dir = (self.target / "adws/adw_data/sessions/run-1a2b3c4d").resolve()
        self._seed("run-1a2b3c4d", "adw", 111,
                   f"{self.target / 'adws/adw_scout.py'} --adw-id run-1a2b3c4d")
        self._seed("run-1a2b3c4d", "agent", 424242, f"--session-dir {session_dir}")
        signals: list[int] = []

        def fake_kill(pid, sig, *_a, **_k):
            """TERM marks the pid dead; a later 0-probe sees it gone."""
            if sig == signal.SIGTERM:
                signals.append(pid)
            elif sig == 0 and pid in signals:
                raise ProcessLookupError(pid)

        def fake_ps(pid):
            return (f"--session-dir {session_dir}" if pid == 424242 else
                    f"{self.target / 'adws/adw_scout.py'} --adw-id run-1a2b3c4d")

        with mock.patch.object(process_control, "_ps_command", side_effect=fake_ps), \
             mock.patch.object(process_control, "_live_rows",
                               return_value=[{"kind": "agent", "pid": 424242,
                                              "command": f"--session-dir {session_dir}"},
                                             {"kind": "adw", "pid": 111,
                                              "command": f"{self.target / 'adws/adw_scout.py'} --adw-id run-1a2b3c4d"}]), \
             mock.patch.object(process_control, "input", return_value="run-1a2b3c4d"), \
             mock.patch.object(process_control.os, "kill", side_effect=fake_kill), \
             mock.patch.object(process_control.time, "sleep", return_value=None):
            code = process_control.stop_run(self.config, "run-1a2b3c4d")
        self.assertEqual(code, 0)
        self.assertEqual(signals, [424242, 111])   # child before parent


if __name__ == "__main__":
    unittest.main()
