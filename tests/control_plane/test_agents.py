"""Orchestrator behavior: retries, gates, permissions, usage — real code, double Pi."""
from __future__ import annotations

import json

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import agents as agents_module  # noqa: E402
from adw_modules import permissions  # noqa: E402
from adw_modules.data_types import GenericOutput  # noqa: E402
from adw_modules.gates import artifacts_exist  # noqa: E402
from tests.support.runtime import (  # noqa: E402
    RuntimeTestCase,
    SCENARIO_USAGE,
    ScenarioOptions,
    execute_scenario,
    pid_alive,
    responses,
)

VALID = '{"status":"success","summary":"done"}'
MISSING_ARTIFACT = '{"status":"success","summary":"plan written","artifacts":["report.md"]}'


class AgentRetryTests(RuntimeTestCase):
    def test_bad_json_is_corrected_in_the_same_session(self):
        result = execute_scenario(self, responses("not-json", '{"status":"success"}'),
                                  ScenarioOptions())
        self.assertIsNone(result.error)
        requests = result.requests()
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["session_id"], requests[1]["session_id"])
        self.assertIn("not valid JSON", requests[1]["prompt"])
        self.assertEqual(result.envelope_validity(), [0, 1])


class BehaviorTableTests(RuntimeTestCase):
    """One row of the plan's behavior table per test."""

    def test_valid_first_envelope_sends_once_and_records_handoff(self):
        result = execute_scenario(self, responses(VALID), ScenarioOptions())
        self.assertIsNone(result.error)
        self.assertEqual(len(result.requests()), 1)
        self.assertEqual(result.envelope_validity(), [1])
        types = [event_type for event_type, *_ in result.events()]
        self.assertIn("handoff", types)
        self.assertIn("agent_end", types)
        self.assertEqual(result.phases()[0][2], "success")

    def test_always_malformed_sends_exactly_three_times_and_fails(self):
        result = execute_scenario(self, responses("nope", "nope", "nope"),
                                  ScenarioOptions())
        self.assertIn("never produced valid GenericOutput JSON",
                      str(result.error))
        self.assertEqual(len(result.requests()), 3)   # JSON_FIX_ATTEMPTS + 1
        self.assertEqual(result.envelope_validity(), [0, 0, 0])
        self.assertEqual(result.phases()[0][2], "fail")
        self.assertEqual(result.session_row()[0], "fail")

    def test_missing_artifact_then_created_on_correction_with_retries(self):
        missing = {"text": MISSING_ARTIFACT, "exit_code": 0,
                   "usage": SCENARIO_USAGE, "events": [], "writes": []}
        created = {**missing,
                   "writes": [{"path": "report.md", "text": "the report"}]}
        result = execute_scenario(
            self, {"responses": [missing, created]},
            ScenarioOptions(gates=(artifacts_exist,), retries=1,
                            writes=["report.md"]))
        self.assertIsNone(result.error)
        self.assertEqual(len(result.requests()), 2)
        self.assertEqual([(attempt, passed) for attempt, passed, _, _ in
                          result.gates()], [(1, 0), (2, 1)])
        checks = json.loads(result.gates()[1][3])
        self.assertEqual(len(checks), 1)
        self.assertTrue(checks[0]["ok"])
        self.assertTrue((self.target / "report.md").exists())
        self.assertIn("failed validation", result.requests()[1]["prompt"])

    def test_gate_failure_with_zero_retries_stops_after_one_send(self):
        result = execute_scenario(self, responses(MISSING_ARTIFACT),
                                  ScenarioOptions(gates=(artifacts_exist,),
                                                  retries=0))
        self.assertIsInstance(result.error, agents_module.GateFailure)
        self.assertEqual(len(result.requests()), 1)
        self.assertEqual([(attempt, passed) for attempt, passed, _, _ in
                          result.gates()], [(1, 0)])
        self.assertEqual(len(result.phases()), 1, "no downstream phase may run")

    def test_envelope_status_fail_fails_the_run(self):
        result = execute_scenario(
            self, responses('{"status":"fail","summary":"cannot proceed"}'),
            ScenarioOptions())
        self.assertIsNotNone(result.error)
        self.assertIn("status='fail'", str(result.error))
        self.assertEqual(result.envelope_validity(), [1])   # parsed and stored

    def test_unauthorized_clean_file_edit_breaches_and_restores(self):
        vandal = {"text": VALID, "exit_code": 0, "usage": SCENARIO_USAGE,
                  "events": [], "writes": [{"path": "sample.txt",
                                            "text": "vandalized"}]}
        result = execute_scenario(self, {"responses": [vandal]},
                                  ScenarioOptions(writes=[]))
        self.assertIsInstance(result.error, permissions.PermissionBreach)
        self.assertEqual((self.target / "sample.txt").read_text(), "original\n")
        types = [event_type for event_type, *_ in result.events()]
        self.assertNotIn("handoff", types, "no accepted handoff after a breach")

    def test_allowed_handoff_file_write_succeeds_for_read_only_agent(self):
        options = ScenarioOptions(writes=[], adw_id="handoff-run")
        allowed = {"text": VALID, "exit_code": 0, "usage": SCENARIO_USAGE,
                   "events": [],
                   "writes": [{"path": "adws/adw_data/sessions/handoff-run"
                                       "/context_handoff/notes.md",
                               "text": "captured"}]}
        result = execute_scenario(self, {"responses": [allowed]}, options)
        self.assertIsNone(result.error, result.error)
        self.assertTrue((self.target / "adws/adw_data/sessions/handoff-run"
                         / "context_handoff/notes.md").exists())

    def test_repeated_calls_for_one_agent_rejoin_the_session(self):
        result = execute_scenario(self, responses(VALID, VALID),
                                  ScenarioOptions(calls=2, adw_id="repeat-run"))
        self.assertIsNone(result.error)
        requests = result.requests()
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["session_id"], requests[1]["session_id"])
        self.assertEqual([seq for seq, *_ in result.phases()], [1, 2])

    def test_three_sends_accumulate_session_usage_and_reconcile(self):
        result = execute_scenario(self, responses("nope", "nope", VALID),
                                  ScenarioOptions(adw_id="usage-run"))
        self.assertIsNone(result.error)
        self.assertEqual(len(result.requests()), 3)
        status, tokens, cost, _ = result.session_row()
        self.assertEqual(tokens, 36)          # 3 sends x 12 tokens
        self.assertAlmostEqual(cost, 0.036)   # 3 x 0.012
        agent_end = [event for event in result.events()
                     if event[0] == "agent_end"]
        self.assertEqual(len(agent_end), 1)
        self.assertEqual(agent_end[0][3], 36)  # final agent_end reconciles

    def test_normal_child_completion_ends_the_process_row_and_the_child(self):
        result = execute_scenario(self, responses(VALID), ScenarioOptions())
        agent_rows = [row for row in result.processes() if row[0] == "agent"]
        self.assertEqual(len(agent_rows), 1)
        _, _, pid, ended_at = agent_rows[0]
        self.assertIsNotNone(ended_at)
        self.assertFalse(pid_alive(pid),
                         "process row says ended but the child is still alive")


if __name__ == "__main__":
    import unittest
    unittest.main()
