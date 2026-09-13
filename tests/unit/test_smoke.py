"""Smoke boundaries: config derivation, gates, and trace verification."""
from __future__ import annotations

import json
import unittest
from pathlib import Path
from unittest import mock

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import agent_pi, agents, smoke  # noqa: E402
from adw_modules.data_types import (  # noqa: E402
    AgentConfig,
    EventRecord,
    GenericOutput,
    PhaseParams,
    PromptEngineering,
    SSSFConfig,
)
from tests.support.runtime import RuntimeTestCase, make_run  # noqa: E402

VALID = '{"status":"success","summary":"done"}'


def roster(**scout_overrides) -> SSSFConfig:
    scout = {"name": "scout", "model": "google/gemini-3.6-flash",
             "thinking": "low",
             "prompt_engineering": PromptEngineering(
                 system="prompts/scout-system.md", user="prompts/scout-user.md"),
             **scout_overrides}
    builder = AgentConfig(name="builder", model="openai/gpt-5.6-terra",
                          thinking="high",
                          prompt_engineering=PromptEngineering(
                              system="prompts/builder-system.md",
                              user="prompts/builder-user.md"))
    return SSSFConfig(agents=[AgentConfig(**scout), builder])


class ConfigureProbeTests(unittest.TestCase):
    def test_smoke_role_is_derived_from_the_scout(self):
        derived = smoke.configure_probe(roster())
        smoke_agent = agents.resolve(derived, "smoke")
        self.assertEqual(smoke_agent.model, "google/gemini-3.6-flash")
        self.assertEqual(smoke_agent.thinking, "low")
        self.assertEqual(smoke_agent.tools, ["read", "write"])
        self.assertEqual(smoke_agent.writes, [])
        self.assertEqual(smoke_agent.harness_engineering, [])

    def test_derived_config_leaves_non_scout_agents_untouched(self):
        before = roster()
        derived = smoke.configure_probe(before)
        self.assertEqual(len(derived.agents), len(before.agents) + 1)
        for original in before.agents:
            derived_agent = agents.resolve(derived, original.name)
            self.assertEqual(derived_agent.model, original.model)
            self.assertEqual(derived_agent.thinking, original.thinking)
            self.assertEqual(derived_agent.writes, original.writes)

    def test_configure_requires_a_scout_to_derive_from(self):
        empty = SSSFConfig(agents=[
            AgentConfig(name="builder",
                        prompt_engineering=PromptEngineering(
                            system="s", user="u"))])
        with self.assertRaises(SystemExit):
            smoke.configure_probe(empty)

    def test_missing_provider_fails_validation(self):
        derived = smoke.configure_probe(roster(model="google/does-not-exist"))
        with mock.patch.object(agent_pi, "_pi_catalog", return_value=[]):
            with self.assertRaises(SystemExit):
                agents.validate(derived, ["smoke"])


class ReceiptGateTests(RuntimeTestCase):
    def test_exact_nonempty_receipt_passes(self):
        receipt = self.target / "smoke-receipt.txt"
        receipt.write_text("SSSF smoke receipt\n")
        report = smoke.receipt_gate(receipt)(
            GenericOutput(status="success", summary="probe complete",
                          artifacts=[str(receipt)]), None)
        self.assertTrue(report.passed)

    def test_missing_receipt_fails(self):
        report = smoke.receipt_gate(self.target / "absent.txt")(
            GenericOutput(status="success", artifacts=["does not matter"]), None)
        self.assertFalse(report.passed)

    def test_empty_artifact_list_fails(self):
        receipt = self.target / "smoke-receipt.txt"
        receipt.write_text("SSSF smoke receipt\n")
        report = smoke.receipt_gate(receipt)(
            GenericOutput(status="success", artifacts=[]), None)
        self.assertFalse(report.passed)

    def test_wrong_artifact_path_fails(self):
        receipt = self.target / "smoke-receipt.txt"
        receipt.write_text("SSSF smoke receipt\n")
        other = self.target / "other.txt"
        other.write_text("not the receipt\n")
        report = smoke.receipt_gate(receipt)(
            GenericOutput(status="success", artifacts=[str(other)]), None)
        self.assertFalse(report.passed)

    def test_zero_byte_receipt_fails(self):
        receipt = self.target / "smoke-receipt.txt"
        receipt.write_text("")
        report = smoke.receipt_gate(receipt)(
            GenericOutput(status="success", artifacts=[str(receipt)]), None)
        self.assertFalse(report.passed)


class RecallGateTests(RuntimeTestCase):
    NONCE = "a1b2c3d4e5f60718293a4b5c6d7e8f90"

    def test_exact_summary_passes(self):
        report = smoke.recall_gate(self.NONCE)(
            GenericOutput(status="success", summary=self.NONCE), None)
        self.assertTrue(report.passed)

    def test_wrong_answer_fails_without_disclosing_the_nonce(self):
        report = smoke.recall_gate(self.NONCE)(
            GenericOutput(status="success", summary="was it 42?"), None)
        self.assertFalse(report.passed)
        self.assertNotIn(self.NONCE, "\n".join(report.violations))
        self.assertNotIn(self.NONCE, json.dumps(
            [check.model_dump() for check in report.checks]))


class VerifyTraceTests(RuntimeTestCase):
    """verify_trace against a real trace, with crafted evidence."""

    SESSION_ID = "sess-777"

    def setUp(self) -> None:
        super().setUp()
        self.run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(self.run.tracer.conn.close)
        self.smoke_agent = AgentConfig(
            name="smoke",
            prompt_engineering=PromptEngineering(system="s", user="u"))

    def evidence(self) -> smoke.SmokeEvidence:
        raw = smoke.raw_output_path(self.run)
        raw.parent.mkdir(parents=True, exist_ok=True)
        probe_lines = json.dumps({"type": "session", "id": self.SESSION_ID}) + "\n"
        probe_lines += json.dumps(
            {"type": "message_end",
             "message": {"role": "assistant", "content": [{"type": "text",
                                                           "text": "probe"}]}}) + "\n"
        raw.write_text(probe_lines)
        recall_lines = json.dumps(
            {"type": "message_end",
             "message": {"role": "assistant", "content": [{"type": "text",
                                                           "text": "recall"}]}}) + "\n"
        with raw.open("a") as handle:
            handle.write(recall_lines)
        sessions_dir = self.run.session_dir / "smoke" / "pi_sessions"
        sessions_dir.mkdir(parents=True, exist_ok=True)
        (sessions_dir / f"{self.SESSION_ID}.jsonl").write_text(
            probe_lines + recall_lines)
        return smoke.SmokeEvidence(
            probe_file=Path("apps/inkwell/README.md"),
            receipt_file=self.run.context_handoff_dir / "smoke-receipt.txt",
            recall_raw_offset=len(probe_lines.encode()),
            first_pi_session_id=self.SESSION_ID)

    def build_trace(self) -> None:
        with self.run.phase(PhaseParams(
                name="probe", kind="agent", owner="smoke",
                description="Read the probe file and write the receipt")) as phase:
            pass
        self.run.tracer.event(EventRecord(
            adw_id=self.run.adw_id, phase_id=phase.phase.phase_id,
            type="tool_call", name="read: apps/inkwell/README.md", payload={}))
        with self.run.phase(PhaseParams(
                name="recall", kind="agent", owner="smoke",
                description="Verify prior context without reinjecting it")) as phase:
            pass
        for phase_row in self.run.phases:
            self.run.tracer.envelope_row(phase_row, "smoke", "GenericOutput",
                                         VALID, True, 1)
        self.run.tracer.agent_session_row(self.run.adw_id, self.smoke_agent,
                                          self.SESSION_ID)

    def test_complete_evidence_passes(self):
        self.build_trace()
        report = smoke.verify_trace(self.run, self.evidence())
        self.assertEqual(report.violations, [])

    def test_tool_use_during_recall_fails(self):
        self.build_trace()
        evidence = self.evidence()
        recall_phase_id = self.run.phases[-1].phase_id
        self.run.tracer.event(EventRecord(
            adw_id=self.run.adw_id, phase_id=recall_phase_id, type="tool_call",
            name="read: agent_map.json", payload={}))
        with smoke.raw_output_path(self.run).open("a") as handle:
            handle.write(json.dumps(
                {"type": "tool_execution_end", "toolCallId": "c1",
                 "toolName": "read"}) + "\n")
        report = smoke.verify_trace(self.run, evidence)
        self.assertFalse(report.passed)
        self.assertTrue(any("recall" in violation.lower()
                            for violation in report.violations), report.violations)

    def test_changed_pi_session_identity_fails(self):
        self.build_trace()
        evidence = self.evidence()
        self.run.tracer.agent_session_row(self.run.adw_id, self.smoke_agent,
                                          "sess-888")
        report = smoke.verify_trace(self.run, evidence)
        self.assertFalse(report.passed)

    def test_wrong_trace_database_fails(self):
        self.build_trace()
        empty_run = make_run(self.target, "empty-run")
        self.addCleanup(empty_run.tracer.conn.close)
        report = smoke.verify_trace(empty_run, self.evidence())
        self.assertFalse(report.passed)


class SmokeAdwBoundaryTests(RuntimeTestCase):
    """adw_smoke validates the probe path before any session or Pi exists."""

    def run_smoke(self, *args: str):
        import os
        import subprocess
        import sys
        adw_smoke = self.target / "adws" / "adw_smoke.py"
        return subprocess.run(
            [sys.executable, str(adw_smoke), *args],
            cwd=self.target, env={**os.environ,
                                  "PYTHONDONTWRITEBYTECODE": "1"},
            capture_output=True, text=True, timeout=30)

    def test_nonexistent_probe_file_is_refused(self):
        result = self.run_smoke("--probe-file", "absent.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("regular file", result.stderr + result.stdout)

    def test_probe_path_escaping_the_repo_is_refused(self):
        result = self.run_smoke("--probe-file", "../escape.md")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self._scratch / "escape.md").exists())


if __name__ == "__main__":
    unittest.main()
