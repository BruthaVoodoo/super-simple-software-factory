"""Gate behavior: artifacts, JSON, diff claims, verdict consistency, tests_pass."""
from __future__ import annotations

import json
import sys
import unittest

from tests.support.imports import bootstrap

bootstrap()
from tests.support.runtime import RuntimeTestCase

from adw_modules.data_types import BuildOutput, GenericOutput, ReviewOutput
from adw_modules.gates import (
    artifacts_exist,
    diff_matches_claims,
    files_non_empty,
    json_parses,
    tests_pass,
    verdict_consistent,
)

RUN_STUB = object()   # gates receive run but never use it


def envelope(**overrides) -> GenericOutput:
    fields = {"status": "success", "summary": "s", "artifacts": []}
    fields.update(overrides)
    return GenericOutput(**fields)


class ArtifactsExistTests(RuntimeTestCase):
    def test_existing_artifact_passes_with_size_note(self):
        (self.target / "report.json").write_text("{}")
        report = artifacts_exist(envelope(artifacts=["report.json"]), RUN_STUB)
        self.assertTrue(report.passed)
        self.assertIn("exists", report.checks[0].note)

    def test_missing_artifact_fails(self):
        report = artifacts_exist(envelope(artifacts=["absent.md"]), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertEqual(report.violations,
                         ["absent.md: declared artifact does not exist"])


class FilesNonEmptyTests(RuntimeTestCase):
    def test_zero_byte_artifact_fails(self):
        (self.target / "empty.txt").write_text("")
        report = files_non_empty(envelope(artifacts=["empty.txt"]), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertEqual(report.violations,
                         ["empty.txt: declared artifact is empty"])

    def test_missing_file_is_left_to_artifacts_exist(self):
        report = files_non_empty(envelope(artifacts=["absent.txt"]), RUN_STUB)
        self.assertTrue(report.passed)
        self.assertEqual(report.checks, [])


class JsonParsesTests(RuntimeTestCase):
    def test_valid_json_artifact_passes(self):
        (self.target / "data.json").write_text(json.dumps({"ok": True}))
        report = json_parses(envelope(artifacts=["data.json"]), RUN_STUB)
        self.assertTrue(report.passed)
        self.assertIn("dict", report.checks[0].note)

    def test_invalid_json_artifact_fails(self):
        (self.target / "bad.json").write_text("{not json")
        report = json_parses(envelope(artifacts=["bad.json"]), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertIn("does not parse", report.violations[0])


class DiffMatchesClaimsTests(RuntimeTestCase):
    def test_claimed_changed_file_must_exist(self):
        (self.target / "src.ts").write_text("// exists")
        report = diff_matches_claims(
            BuildOutput(status="success", changed_files=["src.ts"]), RUN_STUB)
        self.assertTrue(report.passed)

    def test_claimed_missing_file_fails(self):
        report = diff_matches_claims(
            BuildOutput(status="success", changed_files=["ghost.ts"]), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertEqual(report.violations,
                         ["ghost.ts: claimed changed file does not exist"])


class VerdictConsistentTests(RuntimeTestCase):
    def review(self, **overrides) -> ReviewOutput:
        fields = {"status": "success", "summary": "s"}
        fields.update(overrides)
        return ReviewOutput(**fields)

    def test_approval_with_blocking_findings_fails(self):
        report = verdict_consistent(
            self.review(approved=True, blocking=["fix X"]), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertIn("approved vs blocking", report.violations[0])

    def test_approval_with_unmet_requirements_fails(self):
        report = verdict_consistent(self.review(
            approved=True,
            findings=[{"requirement": "it builds", "met": False}]), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertIn("approved vs findings", report.violations[0])

    def test_rejection_without_a_finding_fails(self):
        report = verdict_consistent(self.review(approved=False), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertIn("rejection names a problem", report.violations[0])

    def test_supported_verdict_passes(self):
        supported = verdict_consistent(self.review(
            approved=False,
            blocking=["fix X"]), RUN_STUB)
        self.assertTrue(supported.passed)
        approved = verdict_consistent(self.review(
            approved=True,
            findings=[{"requirement": "it builds", "met": True}]), RUN_STUB)
        self.assertTrue(approved.passed)


class TestsPassTests(RuntimeTestCase):
    """The gate factory runs the command in the process cwd — the scratch target."""

    def test_failing_command_records_exit_code_and_output_tail(self):
        gate = tests_pass(f"{sys.executable} -c 'raise SystemExit(3)'")
        report = gate(envelope(), RUN_STUB)
        self.assertFalse(report.passed)
        self.assertIn("exit 3", report.checks[0].note)

    def test_passing_command_records_exit_zero(self):
        gate = tests_pass(f"{sys.executable} -c 'pass'")
        report = gate(envelope(), RUN_STUB)
        self.assertTrue(report.passed)
        self.assertEqual(report.violations, [])


if __name__ == "__main__":
    unittest.main()
