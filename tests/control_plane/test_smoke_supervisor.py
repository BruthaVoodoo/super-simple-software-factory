"""The smoke supervisor: live observation, failure, timeout — synthetic children.

These tests exercise the launcher's owned-process supervision with synthetic
child processes. They are NOT live-acceptance evidence: no real Pi, no model.
"""
from __future__ import annotations

import importlib.util
import os
import signal
import subprocess
import sys
import unittest
from pathlib import Path

from tests.support.imports import bootstrap

bootstrap()

from tests.support.factory import ROOT, TEMPLATE  # noqa: E402
from tests.support.runtime import (  # noqa: E402
    RuntimeTestCase,
    pid_alive,
)

LAUNCHER = ROOT / "scripts" / "smoke-real-pi.py"
TEMPLATE_ADWS = TEMPLATE / "adws"


def load_launcher():
    spec = importlib.util.spec_from_file_location("smoke_real_pi", LAUNCHER)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module   # dataclasses resolves __module__ at class time
    spec.loader.exec_module(module)
    return module


class SuperviseTests(RuntimeTestCase):
    """The supervision core, driven with synthetic children."""

    def setUp(self) -> None:
        super().setUp()
        self.launcher = load_launcher()

    def _synthetic_child(self, db: Path, release: Path) -> Path:
        """Creates a real trace schema, emits one tool_call, parks for release."""
        child = self._scratch / "synthetic-child.py"
        child.write_text(f"""
import sys, time
from pathlib import Path
sys.path.insert(0, {str(TEMPLATE_ADWS)!r})
from adw_modules.tracer import Tracer
from adw_modules.data_types import EventRecord
t = Tracer({str(db)!r}, {str(db.parent / 'events.jsonl')!r})
t.conn.execute(
    "INSERT INTO phases (phase_id, adw_id, seq, name, kind, owner, description,"
    " status) VALUES ('synth-run_01_probe', 'synth-run', 1, 'probe', 'agent',"
    " 'smoke', 'synthetic probe phase', 'running')")
t.event(EventRecord(adw_id='synth-run', phase_id='synth-run_01_probe',
                    type='tool_call', name='read: README.md', payload={{}}))
# Park until released, but never unboundedly: self-release after 5s.
deadline = time.monotonic() + 5.0
while not Path({str(release)!r}).exists() and time.monotonic() < deadline:
    time.sleep(0.05)
""")
        return child

    def test_live_style_observation_happens_before_the_child_release(self):
        db = self._scratch / "synth" / "sssf.db"
        release = self._scratch / "release" / "go"
        release.parent.mkdir(parents=True, exist_ok=True)
        child = self._synthetic_child(db, release)
        result = self.launcher.supervise(
            [sys.executable, str(child)], target=self._scratch, db_path=db,
            adw_id="synth-run", timeout=60, poll=0.05)
        self.assertEqual(result.returncode, 0)
        self.assertIsNotNone(result.live_event_id,
                             "the tool_call must be observed while the probe "
                             "phase is running and the child is alive")
        self.assertIsNotNone(result.live_observed_at)

    def test_child_failure_before_db_creation_is_reported_unverified(self):
        result = self.launcher.supervise(
            [sys.executable, "-c", "raise SystemExit(7)"],
            target=self._scratch,
            db_path=self._scratch / "never" / "sssf.db",
            adw_id="synth-run", timeout=30, poll=0.05)
        self.assertEqual(result.returncode, 7)
        self.assertIsNone(result.live_event_id,
                          "a missing observation is reported unverified, "
                          "never inferred from final counts")

    def test_timeout_kills_the_owned_group_and_leaves_others_alive(self):
        sleeper = self._scratch / "sleeper.py"
        sleeper.write_text("import time; time.sleep(30)\n")
        other_sleeper = self._scratch / "other-sleeper.py"
        other_sleeper.write_text("import time; time.sleep(30)\n")
        unrelated = subprocess.Popen([sys.executable, str(other_sleeper)],
                                     stdin=subprocess.DEVNULL)
        try:
            result = self.launcher.supervise(
                [sys.executable, str(sleeper)], target=self._scratch,
                db_path=self._scratch / "never" / "sssf.db",
                adw_id="synth-run", timeout=2, poll=0.05)
            self.assertTrue(result.timed_out)
            self.assertEqual(result.returncode, 124)
            self.assertFalse(pid_alive(result.pid),
                             "the owned child survived its own timeout cleanup")
            self.assertTrue(pid_alive(unrelated.pid),
                            "an unrelated process must never be touched")
        finally:
            try:
                unrelated.kill()
            except ProcessLookupError:
                pass
            unrelated.wait(timeout=5)


class LauncherPreflightTests(RuntimeTestCase):
    """Refusals happen before any target is created or any process launched."""

    def _run_launcher(self, **env_overrides) -> subprocess.CompletedProcess:
        env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1"}
        env.pop("SSSF_SMOKE_MODEL", None)
        env.pop("SSSF_TEST_DOUBLE", None)
        env.update(env_overrides)
        return subprocess.run([sys.executable, str(LAUNCHER)], env=env,
                              capture_output=True, text=True, timeout=30)

    def test_missing_explicit_model_is_refused(self):
        result = self._run_launcher()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SSSF_SMOKE_MODEL", result.stderr)

    def test_test_double_environment_is_refused(self):
        result = self._run_launcher(SSSF_SMOKE_MODEL="fixture/fixture-model",
                                    SSSF_TEST_DOUBLE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refus", (result.stderr + result.stdout).lower())

    def test_fake_executable_path_is_refused(self):
        fake = self._scratch / "bin" / "pi-double"
        fake.parent.mkdir(parents=True, exist_ok=True)
        fake.write_text("#!/bin/sh\ntrue\n")
        fake.chmod(0o755)
        result = self._run_launcher(SSSF_SMOKE_MODEL="fixture/fixture-model",
                                    PI_PATH=str(fake))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("refus", (result.stderr + result.stdout).lower())


if __name__ == "__main__":
    unittest.main()
