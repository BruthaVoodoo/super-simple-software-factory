"""The visualizer reads specific columns and routes — frozen by contract."""
from __future__ import annotations

import unittest

from tests.support.imports import bootstrap

bootstrap()

from adw_modules.tracer import Tracer  # noqa: E402
from tests.support.factory import ROOT, TEMPLATE  # noqa: E402

# The columns the UI depends on, per table. Additions are backward-compatible
# and allowed; REMOVALS or renames break the UI and this test.
UI_COLUMNS = {
    "sessions": {"adw_id", "adw_name", "request", "status", "engineer",
                 "started_at", "ended_at", "total_tokens", "total_cost",
                 "archived"},
    "phases": {"phase_id", "adw_id", "seq", "name", "kind", "owner",
               "description", "status", "attempt", "retries", "error",
               "started_at", "ended_at"},
    "events": {"event_id", "adw_id", "phase_id", "parent_id", "type", "name",
               "payload_json", "tokens", "started_at", "ended_at"},
    "envelopes": {"envelope_id", "adw_id", "phase_id", "agent", "output_type",
                  "payload_json", "valid", "attempt", "created_at"},
    "gate_results": {"id", "adw_id", "phase_id", "attempt", "gate", "passed",
                     "violations_json", "checks_json", "created_at"},
    "processes": {"id", "adw_id", "kind", "name", "pid", "command",
                  "started_at", "ended_at"},
    "agent_sessions": {"adw_id", "agent", "coding_agent", "model", "color",
                       "session_id", "context_tokens", "context_window",
                       "created_at", "last_used_at"},
}

DOCUMENTED_ROUTES = ("/api/health", "/api/sessions", "/api/sessions/:adw_id",
                     "/api/sessions/:adw_id/archive",
                     "/api/sessions/:adw_id/events")


class VisualizerContractTests(unittest.TestCase):
    def test_schema_columns_are_frozen(self):
        import tempfile
        db = tempfile.mkdtemp() + "/contract.db"
        tracer = Tracer(db, tempfile.mkdtemp() + "/events.jsonl")
        conn = tracer.conn
        for table, expected in UI_COLUMNS.items():
            columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            missing = expected - columns
            self.assertEqual(missing, set(), f"{table}: contract columns missing")
        tracer.conn.close()

    def test_documented_routes_exist_in_server(self):
        source = (TEMPLATE.parent / "apps" / "visualizer" / "server"
                  / "index.ts").read_text()
        for route in DOCUMENTED_ROUTES:
            self.assertIn(route, source, route)

    def test_contract_doc_exists_and_names_the_columns(self):
        doc = (ROOT / "docs" / "visualizer-contract.md").read_text()
        for table in UI_COLUMNS:
            self.assertIn(f"`{table}`", doc)
        for route in DOCUMENTED_ROUTES:
            self.assertIn(route, doc)


if __name__ == "__main__":
    unittest.main()
