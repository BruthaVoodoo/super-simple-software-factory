"""Quality blocks are configured commands — nothing ships as a placeholder."""
from __future__ import annotations

import sys
import unittest

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import quality  # noqa: E402
from adw_modules.data_types import PhaseParams  # noqa: E402
from tests.support.runtime import RuntimeTestCase, make_run  # noqa: E402

HEADER = """
defaults:
  model: fixture/fixture-model
  data_dir: adws/adw_data
agents:
  - name: scout
    prompt_engineering:
      system: adws/adw_data/prompt_engineering/scout/system.md
      user: adws/adw_data/prompt_engineering/scout/user.md
"""


class QualityBlockTests(RuntimeTestCase):
    def write_config(self, quality_yaml: str) -> None:
        body = HEADER + (f"quality:\n{quality_yaml}" if quality_yaml else "")
        (self.target / "adws/adw_sssf_config/sssf.config.yaml").write_text(body)

    def make_run(self, adw_id: str):
        run = make_run(self.target, adw_id)
        self.addCleanup(run.tracer.conn.close)
        return run


    def run_quality_in_phase(self, run, name="test"):
        """Quality blocks execute inside a code phase, as every ADW does."""
        with run.phase(PhaseParams(name=name, kind="code", owner="quality",
                                   description="Run the configured quality command")):
            if name == "test":
                return quality.run_tests(run)
            return quality.run_quality(run)

    def test_unconfigured_block_raises_with_guidance(self):
        self.write_config("")
        run = self.make_run("qual-1")
        with self.assertRaises(quality.QualityNotConfigured) as caught:
            self.run_quality_in_phase(run)
        self.assertIn("quality:", str(caught.exception))
        self.assertIn("test", str(caught.exception))

    def test_configured_block_runs_traces_and_passes(self):
        self.write_config(f"  test:\n"
                          f"    argv: [{sys.executable!r}, '-c', 'pass']\n")
        run = self.make_run("qual-2")
        result = self.run_quality_in_phase(run)
        self.assertTrue(result.passed)
        self.assertEqual(result.checks[0].returncode, 0)
        events = run.tracer.conn.execute(
            "SELECT type, name FROM events WHERE type='tool_call' AND "
            "name LIKE 'quality:%'").fetchall()
        self.assertEqual([(t, n) for t, n in events],
                         [("tool_call", "quality:test")])

    def test_failing_block_collects_the_verbatim_tail(self):
        self.write_config(f"  test:\n"
                          f"    argv: [{sys.executable!r}, '-c',"
                          f" 'print(\"suite failed\"); raise SystemExit(3)']\n")
        run = self.make_run("qual-3")
        result = self.run_quality_in_phase(run)
        self.assertFalse(result.passed)
        self.assertIn("suite failed", result.failures[0])
        self.assertIn("exited 3", result.failures[0])

    def test_timeout_is_exit_124_and_missing_binary_is_127(self):
        self.write_config(f"  test:\n"
                          f"    argv: [{sys.executable!r}, '-c',"
                          f" 'import time; time.sleep(30)']\n"
                          f"    timeout_seconds: 1\n")
        run = self.make_run("qual-4")
        self.assertEqual(self.run_quality_in_phase(run).checks[0].returncode, 124)
        self.write_config("  test:\n    argv: [definitely-not-a-binary-xyz]\n")
        run = self.make_run("qual-5")
        self.assertEqual(self.run_quality_in_phase(run).checks[0].returncode, 127)

    def test_run_quality_runs_only_configured_blocks_and_fails_loudly_when_none(self):
        self.write_config(f"  lint:\n    argv: [{sys.executable!r}, '-c', 'pass']\n")
        run = self.make_run("qual-6")
        result = self.run_quality_in_phase(run, name="all")
        self.assertEqual([c.name for c in result.checks], ["lint"])
        self.write_config("")
        run = self.make_run("qual-7")
        with self.assertRaises(quality.QualityNotConfigured):
            self.run_quality_in_phase(run, name="all")


if __name__ == "__main__":
    unittest.main()
