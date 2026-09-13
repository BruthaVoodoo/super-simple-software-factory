"""Envelope, phase-parameter, and prompt-rendering contracts (existing behavior)."""
from __future__ import annotations

import unittest
from pathlib import Path

from pydantic import ValidationError

from tests.support.imports import bootstrap

bootstrap()
from tests.support.runtime import RuntimeTestCase

from adw_modules.data_types import (
    BuildOutput,
    DocumentOutput,
    EnvelopeBase,
    GateCheck,
    GateReport,
    GenericOutput,
    PhaseParams,
    PlanOutput,
    ReviewOutput,
    ScoutOutput,
    VerifyOutput,
)
from adw_modules.prompts import render, save

ENVELOPE_TYPES = (GenericOutput, PlanOutput, BuildOutput, ScoutOutput,
                  ReviewOutput, DocumentOutput, VerifyOutput)


class PhaseDescriptionTests(unittest.TestCase):
    def test_phase_description_cannot_echo_name(self):
        with self.assertRaises(ValidationError):
            PhaseParams(name="build", kind="agent", owner="builder",
                        description="Build")

    def test_phase_description_is_required(self):
        with self.assertRaises(ValidationError):
            PhaseParams(name="build", kind="agent", owner="builder", description="")

    def test_earned_description_is_accepted_and_normalized(self):
        params = PhaseParams(name="build", kind="agent", owner="builder",
                             description="  Change the tested code.  ")
        self.assertEqual(params.description, "Change the tested code.")


class GateReportTests(unittest.TestCase):
    def test_gate_report_derives_violations_from_checks(self):
        report = GateReport().check("plan.md", True, "exists")
        report.check("missing.md", False, "missing")
        self.assertFalse(report.passed)
        self.assertEqual(report.violations, ["missing.md: missing"])
        self.assertEqual(len(report.checks), 2)

    def test_all_green_report_has_no_violations(self):
        report = GateReport().check("plan.md", True, "exists, 2.1KB")
        self.assertTrue(report.passed)
        self.assertEqual(report.violations, [])

    def test_check_returns_report_for_chaining(self):
        chained = GateReport().check("a", True).check("b", True)
        self.assertIsInstance(chained, GateReport)
        self.assertEqual(len(chained.checks), 2)

    def test_failed_check_without_note_defaults_to_failed(self):
        report = GateReport().check("item", False)
        self.assertEqual(report.violations, ["item: failed"])


class EnvelopeContractTests(unittest.TestCase):
    def test_status_is_required(self):
        with self.assertRaises(ValidationError):
            EnvelopeBase(summary="no status")

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            GenericOutput.model_validate({"status": "pending"})

    def test_default_artifact_lists_are_not_shared(self):
        first, second = EnvelopeBase(status="success"), EnvelopeBase(status="success")
        first.artifacts.append("shared.txt")
        self.assertEqual(second.artifacts, [])
        self.assertIsNot(first.artifacts, second.artifacts)

    def test_every_envelope_type_round_trips(self):
        sample = {
            "status": "success",
            "summary": "did the thing",
            "artifacts": ["out/report.json"],
            "notes_for_next_agent": "verify the report",
        }
        extras = {
            PlanOutput: {"commit_message": "docs: add plan"},
            BuildOutput: {"changed_files": ["src/a.ts"], "commit_message": "feat: a"},
            ScoutOutput: {"findings": [{"file": "src/a.ts", "note": "entry point"}]},
            ReviewOutput: {"approved": True,
                           "findings": [{"requirement": "it builds", "met": True}],
                           "blocking": []},
            DocumentOutput: {"document_path": "app_docs/x.md",
                             "documented_files": ["app_docs/x.md"],
                             "commit_message": "docs: x"},
            VerifyOutput: {"passed": True, "failures": []},
            GenericOutput: {},
        }
        for output_type in ENVELOPE_TYPES:
            with self.subTest(output_type=output_type.__name__):
                envelope = output_type.model_validate({**sample, **extras[output_type]})
                restored = output_type.model_validate_json(envelope.model_dump_json())
                self.assertEqual(restored, envelope)
                self.assertEqual(restored.status, "success")
                self.assertEqual(restored.summary, "did the thing")


class PromptRenderingTests(RuntimeTestCase):
    """render() replaces all three supported variables; save() is the audit copy."""

    def setUp(self) -> None:
        super().setUp()
        self.template = self.target / "template.md"
        self.template.write_text(
            "task: {{prompt}}\nbefore: {{previous_envelope}}\n"
            "handoff: {{context_handoff_dir}}\n")

    def test_all_three_variables_are_replaced(self):
        rendered = render(self.template, {
            "prompt": "build the thing",
            "previous_envelope": '{"status": "success"}',
            "context_handoff_dir": "/tmp/handoff",
        })
        self.assertEqual(rendered, "task: build the thing\n"
                                   'before: {"status": "success"}\n'
                                   "handoff: /tmp/handoff\n")

    def test_missing_variable_placeholder_survives(self):
        rendered = render(self.template, {"prompt": "only prompt"})
        self.assertIn("{{previous_envelope}}", rendered)
        self.assertIn("{{context_handoff_dir}}", rendered)

    def test_save_writes_exact_bytes(self):
        content = "exact audit copy\n"
        path = save(Path("adws/adw_data/sessions/x/prompts"), "system.md", content)
        self.assertEqual(path.read_text(), content)
        self.assertEqual(path.read_bytes(), content.encode())
