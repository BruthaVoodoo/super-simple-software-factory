"""Tracer persistence: schema, additive migrations, and record semantics."""
from __future__ import annotations

import json
import unittest

from tests.support.imports import bootstrap

bootstrap()

from adw_modules.data_types import EventRecord, GateReport, Phase, PhaseParams  # noqa: E402
from adw_modules.tracer import Tracer  # noqa: E402
from tests.support.factory import FactoryTestCase  # noqa: E402

ALL_TABLES = {"sessions", "phases", "events", "envelopes", "gate_results",
              "processes", "agent_sessions"}

# Literal pre-migration DDL, written out by hand on purpose: the fixture must
# not be derived from SCHEMA, so a schema mistake cannot redefine its own
# test input. These are the tables as they shipped BEFORE the six columns in
# MIGRATIONS existed.
LEGACY_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
  adw_id        TEXT PRIMARY KEY,
  request       TEXT,
  status        TEXT,
  engineer      TEXT,
  started_at    TEXT, ended_at TEXT,
  total_tokens  INTEGER DEFAULT 0, total_cost REAL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS agent_sessions (
  adw_id        TEXT,
  agent         TEXT,
  coding_agent  TEXT, model TEXT,
  session_id    TEXT,
  created_at    TEXT, last_used_at TEXT,
  PRIMARY KEY (adw_id, agent)
);
CREATE TABLE IF NOT EXISTS gate_results (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  adw_id        TEXT,
  phase_id      TEXT,
  attempt       INTEGER,
  gate          TEXT,
  passed        INTEGER,
  violations_json TEXT,
  created_at    TEXT
);
"""


def columns_of(conn, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


class SchemaTests(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = self._scratch / "trace" / "sssf.db"
        self.tracer = Tracer(self.db, self._scratch / "trace" / "events.jsonl")
        self.addCleanup(self.tracer.conn.close)

    def test_all_seven_runtime_tables_exist(self):
        rows = self.tracer.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        self.assertEqual({name for (name,) in rows} & ALL_TABLES, ALL_TABLES)

    def test_pragmas_are_wal_normal_5000ms(self):
        mode = self.tracer.conn.execute("PRAGMA journal_mode").fetchone()[0]
        sync = self.tracer.conn.execute("PRAGMA synchronous").fetchone()[0]
        timeout = self.tracer.conn.execute("PRAGMA busy_timeout").fetchone()[0]
        self.assertEqual(mode, "wal")
        self.assertEqual(sync, 1)          # NORMAL (2 would be FULL)
        self.assertEqual(timeout, 5000)

    def test_declared_migrations_are_present_in_a_fresh_database(self):
        from adw_modules.tracer import MIGRATIONS
        for table, column, _decl in MIGRATIONS:
            self.assertIn(column, columns_of(self.tracer.conn, table), table)


class MigrationTests(FactoryTestCase):
    """A db from an older SSSF opens: columns are added, data survives."""

    def setUp(self) -> None:
        super().setUp()
        self.db = self._scratch / "legacy" / "sssf.db"
        self.events = self._scratch / "legacy" / "events.jsonl"
        self.tracer = None

    def open_legacy(self) -> None:
        import sqlite3
        self.db.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db)
        conn.executescript(LEGACY_DDL)
        conn.execute("INSERT INTO sessions (adw_id, request, status, engineer) "
                     "VALUES ('legacy-run', 'legacy request', 'fail', 'engineer-x')")
        conn.execute("INSERT INTO agent_sessions (adw_id, agent, coding_agent, model,"
                     " session_id, created_at, last_used_at) VALUES"
                     " ('legacy-run', 'scout', 'pi', 'google/gemini-3.6-flash',"
                     " 'sess-123', 't0', 't1')")
        conn.execute("INSERT INTO gate_results (adw_id, phase_id, attempt, gate,"
                     " passed, violations_json, created_at) VALUES"
                     " ('legacy-run', 'legacy-run_01_p', 1, 'artifacts_exist', 1,"
                     " '[]', 't0')")
        conn.commit()
        conn.close()

    def test_migration_adds_columns_and_preserves_sentinels(self):
        self.open_legacy()
        self.tracer = Tracer(self.db, self.events)
        self.addCleanup(self.tracer.conn.close)

        session_columns = columns_of(self.tracer.conn, "sessions")
        self.assertIn("adw_name", session_columns)
        self.assertIn("archived", session_columns)
        agent_columns = columns_of(self.tracer.conn, "agent_sessions")
        self.assertIn("color", agent_columns)
        self.assertIn("context_tokens", agent_columns)
        self.assertIn("context_window", agent_columns)
        self.assertIn("checks_json", columns_of(self.tracer.conn, "gate_results"))

        request, status = self.tracer.conn.execute(
            "SELECT request, status FROM sessions WHERE adw_id='legacy-run'"
        ).fetchone()
        self.assertEqual((request, status), ("legacy request", "fail"))
        session_id, color = self.tracer.conn.execute(
            "SELECT session_id, color FROM agent_sessions WHERE adw_id='legacy-run'"
        ).fetchone()
        self.assertEqual(session_id, "sess-123")
        self.assertIsNone(color)
        passed, checks = self.tracer.conn.execute(
            "SELECT passed, checks_json FROM gate_results WHERE adw_id='legacy-run'"
        ).fetchone()
        self.assertEqual(passed, 1)
        self.assertIsNone(checks)

    def test_reopening_migrates_idempotently(self):
        self.open_legacy()
        first = Tracer(self.db, self.events)
        first.conn.close()
        second = Tracer(self.db, self.events)
        self.addCleanup(second.conn.close)
        from adw_modules.tracer import MIGRATIONS
        for table, column, _decl in MIGRATIONS:
            names = [row[1] for row in
                     second.conn.execute(f"PRAGMA table_info({table})")]
            self.assertEqual(names.count(column), 1, f"{table}.{column}")
        remaining = second.conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE adw_id='legacy-run'").fetchone()[0]
        self.assertEqual(remaining, 1)


class RecordPersistenceTests(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.db = self._scratch / "trace" / "sssf.db"
        self.jsonl = self._scratch / "trace" / "events.jsonl"
        self.tracer = Tracer(self.db, self.jsonl)
        self.addCleanup(self.tracer.conn.close)
        self.phase = Phase(phase_id="run-01_inspect", adw_id="run-01", seq=1,
                           params=PhaseParams(name="inspect", kind="agent",
                                              owner="scout",
                                              description="Record evidence"))

    def test_event_jsonl_and_db_share_id_and_payload(self):
        event_id = self.tracer.event(EventRecord(
            adw_id="run-01", phase_id=self.phase.phase_id, type="log",
            name="note", payload={"k": "v"}, tokens=5))
        line = json.loads(self.jsonl.read_text().splitlines()[0])
        self.assertEqual(line["event_id"], event_id)
        self.assertEqual(line["payload"], {"k": "v"})
        self.assertIn("ts", line)
        row = self.tracer.conn.execute(
            "SELECT event_id, type, name, payload_json, tokens FROM events "
            "WHERE event_id=?", (event_id,)).fetchone()
        self.assertEqual(row, (event_id, "log", "note", json.dumps({"k": "v"}), 5))

    def test_tool_span_start_and_end_are_preserved(self):
        self.tracer.event(EventRecord(
            adw_id="run-01", phase_id=self.phase.phase_id, type="tool_call",
            name="bash: ls", payload={}, started_at="S", ended_at="E"))
        started, ended = self.tracer.conn.execute(
            "SELECT started_at, ended_at FROM events WHERE type='tool_call'"
        ).fetchone()
        self.assertEqual((started, ended), ("S", "E"))

    def test_invalid_and_valid_envelope_rows_retain_attempts(self):
        self.tracer.envelope_row(self.phase, "scout", "GenericOutput",
                                 '{"raw": "not json"}', False, 1)
        self.tracer.envelope_row(self.phase, "scout", "GenericOutput",
                                 '{"status": "success"}', True, 2)
        rows = self.tracer.conn.execute(
            "SELECT valid, attempt FROM envelopes ORDER BY attempt").fetchall()
        self.assertEqual(rows, [(0, 1), (1, 2)])

    def test_gate_rows_persist_checks_and_violations(self):
        report = GateReport().check("plan.md", True, "exists")
        report.check("missing.md", False, "missing")
        self.tracer.gate_row(self.phase, "artifacts_exist", report, 1)
        passed, violations, checks = self.tracer.conn.execute(
            "SELECT passed, violations_json, checks_json FROM gate_results"
        ).fetchone()
        self.assertEqual(passed, 0)
        self.assertEqual(json.loads(violations), ["missing.md: missing"])
        self.assertEqual(len(json.loads(checks)), 2)

    def test_process_row_is_closed_exactly_once(self):
        self.tracer.process_start("run-01", "adw", "", 111, "adw_scout.py")
        self.tracer.process_end("run-01", 111)
        ended_first = self.tracer.conn.execute(
            "SELECT ended_at FROM processes WHERE pid=111").fetchone()[0]
        self.assertIsNotNone(ended_first)
        self.tracer.process_end("run-01", 111)
        ended_second = self.tracer.conn.execute(
            "SELECT ended_at FROM processes WHERE pid=111").fetchone()[0]
        rows = self.tracer.conn.execute(
            "SELECT COUNT(*) FROM processes WHERE pid=111").fetchone()[0]
        self.assertEqual((ended_first, ended_second, rows),
                         (ended_first, ended_first, 1))


if __name__ == "__main__":
    unittest.main()
