"""The offline Pi protocol double: wire surface, streaming, folding, failure.

The double is a fixture process that speaks exactly the surface
`adw_modules.agent_pi` consumes. It never imports or shells out to real Pi
and has no network client. Live acceptance (Task 8/9) rejects it explicitly.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
import time
import unittest
from unittest import mock

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import agent_pi  # noqa: E402
from adw_modules.agent_pi import ToolCallTracker  # noqa: E402
from adw_modules.data_types import PiRequest  # noqa: E402
from tests.support.factory import ROOT  # noqa: E402
from tests.support.processes import install_python_entrypoint  # noqa: E402
from tests.support.runtime import RuntimeTestCase  # noqa: E402

USAGE = {"input": 10, "output": 2, "cacheRead": 0, "cacheWrite": 0,
         "totalTokens": 12,
         "cost": {"input": 0.01, "output": 0.002, "cacheRead": 0,
                  "cacheWrite": 0, "total": 0.012}}

ENVELOPE_TEXT = '{"status":"success","summary":"synthetic response"}'

MINIMAL_SCENARIO = {"responses": [
    {"text": ENVELOPE_TEXT, "exit_code": 0, "usage": USAGE,
     "events": [], "writes": []},
]}

DOUBLE_SCRIPT = ROOT / "tests" / "fixtures" / "pi-double.py"


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


class DoubleTestCase(RuntimeTestCase):
    """Patches agent_pi's transport to the fixture double for one test."""

    def setUp(self) -> None:
        super().setUp()
        self.shim = install_python_entrypoint(
            self._scratch / "bin" / "pi", DOUBLE_SCRIPT)
        models_json = self._scratch / "models.json"
        models_json.write_text('{"providers": {}}')
        for patch in (mock.patch.object(agent_pi, "PI_PATH", str(self.shim)),
                      mock.patch.object(agent_pi, "MODELS_JSON",
                                        str(models_json))):
            patch.start()
            self.addCleanup(patch.stop)
        agent_pi._pi_catalog.cache_clear()
        self.addCleanup(agent_pi._pi_catalog.cache_clear)
        self.scenario_path = self._scratch / "scenario.json"

    def _use_scenario(self, scenario: dict) -> None:
        self.scenario_path.write_text(json.dumps(scenario))
        os.environ["SSSF_TEST_DOUBLE"] = "1"
        os.environ["SSSF_PI_SCENARIO"] = str(self.scenario_path)
        self.addCleanup(os.environ.pop, "SSSF_TEST_DOUBLE", None)
        self.addCleanup(os.environ.pop, "SSSF_PI_SCENARIO", None)

    def _request(self, **overrides) -> PiRequest:
        agent_dir = self.target / "adws/adw_data/sessions/test-agent"
        fields = {
            "prompt": "do the thing",
            "system_prompt": "you are talking to a test harness",
            "model": "fixture/fixture-model",
            "thinking": "medium",
            "session_id": "sssf-double-session",
            "session_dir": str(agent_dir / "pi_sessions"),
            "raw_output_path": str(agent_dir / "raw_output.jsonl"),
            "cwd": str(self.target),
        }
        fields.update(overrides)
        return PiRequest(**fields)

    def _run(self, scenario: dict, **kwargs):
        self._use_scenario(scenario)
        return agent_pi.run(self._request(), **kwargs)


class DoubleTransportTests(DoubleTestCase):
    def test_transport_returns_exact_tokens_cost_text_and_raw_file(self):
        pids, exits = [], []
        result = self._run(MINIMAL_SCENARIO, on_spawn=pids.append,
                           on_exit=exits.append)
        self.assertEqual(result.tokens, 12)
        self.assertAlmostEqual(result.cost, 0.012)
        self.assertEqual(result.text, ENVELOPE_TEXT)
        self.assertEqual(result.usage.total_tokens, 12)
        self.assertEqual(result.usage.input_tokens, 10)
        self.assertEqual(result.usage.output_tokens, 2)
        self.assertEqual(result.context_window, 32000)
        self.assertEqual(result.context_tokens, 12)
        self.assertEqual(pids, exits, "spawn/exit callbacks must bracket the child")
        self.assertGreater(pids[0], 1)
        raw = (self.target / "adws/adw_data/sessions/test-agent/raw_output.jsonl"
               ).read_text()
        self.assertIn("synthetic_pi", raw)
        final = json.loads(raw.splitlines()[-1])
        self.assertEqual(
            final["message"]["content"][0]["text"], ENVELOPE_TEXT)

    def test_double_refuses_to_run_without_its_env_key(self):
        result = subprocess.run(
            [str(self.shim), "--list-models"], env={"PATH": "/usr/bin:/bin"},
            capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 64)

    def test_catalog_query_lists_fixture_model_without_consuming_scenario(self):
        self._use_scenario({"responses": []})
        result = subprocess.run(
            [str(self.shim), "--list-models"],
            env={**os.environ, "SSSF_TEST_DOUBLE": "1",
                 "SSSF_PI_SCENARIO": str(self.scenario_path)},
            capture_output=True, text=True, timeout=10, cwd=self.target)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("provider model context max-out thinking images", result.stdout)
        columns = result.stdout.splitlines()[1].split()
        self.assertEqual(columns[:3], ["fixture", "fixture-model", "32K"])
        self.assertFalse(
            (self.target / "adws/adw_data/sessions/test-double").exists(),
            "catalog query consumed or created scenario state")

    def test_session_header_carries_the_synthetic_marker(self):
        events: list[dict] = []
        self._run(MINIMAL_SCENARIO, on_event=events.append)
        self.assertEqual(events[0].get("type"), "session")
        self.assertIn("synthetic_pi", json.dumps(events[0]))

    def test_scenario_writes_land_beneath_the_target(self):
        scenario = {"responses": [{**MINIMAL_SCENARIO["responses"][0],
                                   "writes": [{"path": "out/notes.md",
                                               "text": "fixture bytes"}]}]}
        self._run(scenario)
        self.assertEqual((self.target / "out/notes.md").read_text(),
                         "fixture bytes")

    def test_scenario_write_escaping_the_target_is_refused(self):
        scenario = {"responses": [{**MINIMAL_SCENARIO["responses"][0],
                                   "writes": [{"path": "../escape.txt",
                                               "text": "nope"}]}]}
        with self.assertRaises(RuntimeError) as caught:
            self._run(scenario)
        self.assertIn("exited 71", str(caught.exception))
        self.assertFalse((self._scratch / "escape.txt").exists())

    def test_unexpected_extra_send_is_an_error_not_a_success(self):
        self._run(MINIMAL_SCENARIO)
        with self.assertRaises(RuntimeError) as caught:
            self._run(MINIMAL_SCENARIO)
        self.assertIn("exited 70", str(caught.exception))

    def test_nonzero_exit_without_assistant_text_raises(self):
        scenario = {"responses": [{"text": "", "exit_code": 3, "events": [],
                                   "writes": []}]}
        with self.assertRaises(RuntimeError) as caught:
            self._run(scenario)
        self.assertIn("exited 3", str(caught.exception))

    def test_malformed_line_does_not_erase_the_next_valid_event(self):
        scenario = {"responses": [{**MINIMAL_SCENARIO["responses"][0],
                                   "events": ["definitely not json"]}]}
        events: list[dict] = []
        result = self._run(scenario, on_event=events.append)
        self.assertEqual(result.text, ENVELOPE_TEXT)
        self.assertEqual(len(events), 2)   # session header + valid message_end

    def test_unicode_text_survives_the_transport(self):
        unicode_text = '{"status":"success","summary":"成功 — ünïcode ✓"}'
        scenario = {"responses": [{**MINIMAL_SCENARIO["responses"][0],
                                   "text": unicode_text}]}
        result = self._run(scenario)
        self.assertEqual(result.text, unicode_text)
        raw = (self.target / "adws/adw_data/sessions/test-agent/raw_output.jsonl"
               ).read_text()
        self.assertIn("成功 — ünïcode ✓", raw)

    def test_announce_start_end_folds_into_exactly_one_tool_call(self):
        start = {"type": "tool_execution_start", "toolCallId": "call-9",
                 "toolName": "bash", "args": {"command": "echo hi"}}
        end = {"type": "tool_execution_end", "toolCallId": "call-9",
               "toolName": "bash", "args": {"command": "echo hi"},
               "isError": False,
               "result": {"content": [{"type": "text", "text": "hi\n"}]}}
        scenario = {"responses": [{**MINIMAL_SCENARIO["responses"][0],
                                   "events": [start, end]}]}
        events: list[dict] = []
        self._run(scenario, on_event=events.append)
        tracker = ToolCallTracker()
        records = [record for event in events
                   if (record := tracker.observe(event))]
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["tool_call_id"], "call-9")
        self.assertEqual(record["tool"], "bash")
        self.assertEqual(record["args"], {"command": "echo hi"})
        self.assertEqual(record["result_snippet"], "hi\n")
        self.assertTrue(record["ok"])


class StreamingHandshakeTests(DoubleTestCase):
    """The double parks after a completed tool event until a release file lands."""

    def test_tool_record_observable_while_child_waits_for_release(self):
        release = self._scratch / "release" / "go"
        release.parent.mkdir(parents=True, exist_ok=True)
        start = {"type": "tool_execution_start", "toolCallId": "call-stream",
                 "toolName": "read", "args": {"path": "sample.txt"}}
        end = {"type": "tool_execution_end", "toolCallId": "call-stream",
               "toolName": "read", "args": {"path": "sample.txt"},
               "isError": False,
               "result": {"content": [{"type": "text", "text": "original"}]}}
        scenario = {"responses": [{**MINIMAL_SCENARIO["responses"][0],
                                   "events": [start, end],
                                   "wait_for_release": str(release)}]}
        self._use_scenario(scenario)

        events: list[dict] = []
        pids: list[int] = []
        holder: dict = {}

        def transport() -> None:
            holder["result"] = agent_pi.run(self._request(),
                                            on_event=events.append,
                                            on_spawn=pids.append)

        thread = threading.Thread(target=transport, daemon=True)
        thread.start()
        observed = False
        deadline = time.monotonic() + 5.0
        try:
            while time.monotonic() < deadline:
                if any(event.get("type") == "tool_execution_end"
                       for event in events):
                    observed = True
                    break
                time.sleep(0.05)
            self.assertTrue(observed, "forwarded tool record not seen in 5s")
            self.assertTrue(_alive(pids[0]),
                            "child exited before its release file was created")
        finally:
            release.write_text("go")   # bounded: never leave the child parked
        thread.join(timeout=30)
        self.assertFalse(thread.is_alive(), "transport thread hung past release")

        result = holder["result"]
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.text, ENVELOPE_TEXT)
        tracker = ToolCallTracker()
        records = [record for event in events
                   if (record := tracker.observe(event))]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["tool_call_id"], "call-stream")


class CatalogResolutionTests(unittest.TestCase):
    """resolve_model against a fixed catalog — no subprocess, no fixtures."""

    CATALOG = [("fixture", "fixture-model", 32000)]

    def test_explicit_provider_pattern_is_selected(self):
        with mock.patch.object(agent_pi, "_pi_catalog", return_value=self.CATALOG):
            self.assertEqual(agent_pi.resolve_model("fixture/fixture-model"),
                             ("fixture", "fixture-model"))

    def test_unique_bare_pattern_resolves(self):
        with mock.patch.object(agent_pi, "_pi_catalog", return_value=self.CATALOG):
            self.assertEqual(agent_pi.resolve_model("fixture-model"),
                             ("fixture", "fixture-model"))

    def test_ambiguous_bare_pattern_is_rejected(self):
        catalog = self.CATALOG + [("other", "fixture-model", 32000)]
        with mock.patch.object(agent_pi, "_pi_catalog", return_value=catalog):
            with self.assertRaises(ValueError) as caught:
                agent_pi.resolve_model("fixture-model")
        self.assertIn("ambiguous", str(caught.exception))

    def test_unknown_pattern_is_rejected(self):
        with mock.patch.object(agent_pi, "_pi_catalog", return_value=[]):
            with self.assertRaises(ValueError) as caught:
                agent_pi.resolve_model("fixture/fixture-model")
        self.assertIn("not found", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
