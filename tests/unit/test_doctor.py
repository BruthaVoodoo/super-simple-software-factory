"""Doctor: bounded, credential-free environment checks."""
from __future__ import annotations

import unittest
from unittest import mock

from sssf_cli import doctor
from tests.support.runtime import RuntimeTestCase


class DoctorTests(RuntimeTestCase):
    FAKE_PI = (0, "pi 0.85.1\nprovider model context max-out thinking images\n"
                  "google gemini-3.6-flash 1M 128K yes no\n"
                  "openai gpt-5.6-luna 400K 128K yes no\n"
                  "openai gpt-5.6-terra 400K 128K yes no\n"
                  "fireworks accounts/fireworks/models/kimi-k3 256K 32K yes no")

    def checks(self) -> list:
        with mock.patch.object(doctor, "_run_pi", return_value=self.FAKE_PI):
            return doctor.run_checks(self.target)

    def test_stamped_target_passes_all_checks(self):
        checks = self.checks()
        failed = [c for c in checks if not c.ok]
        self.assertEqual(failed, [])
        names = [c.name for c in checks]
        for name in ("python", "uv", "just", "git", "pi", "catalog",
                     "models", "factory"):
            self.assertIn(name, names)
        # one models check per roster agent (multiple entries are by design)
        self.assertGreaterEqual(names.count("models"), 1)

    def test_missing_pi_fails_the_pi_checks_only(self):
        with mock.patch.dict("os.environ", {"PI_PATH": "/nonexistent/pi-missing"}), \
             mock.patch.object(doctor, "_which", return_value=None), \
             mock.patch.object(doctor, "_run_pi") as run_pi:
            checks = doctor.run_checks(self.target)
            by_name = {c.name: c for c in checks}
            self.assertFalse(by_name["pi"].ok)
            self.assertFalse(by_name["catalog"].ok)
            self.assertFalse(by_name["models"].ok)
            self.assertTrue(by_name["git"].ok)
            self.assertTrue(by_name["factory"].ok)
            run_pi.assert_not_called()   # nothing to run pi against

    def test_unstamped_target_fails_the_factory_check(self):
        import pathlib
        import tempfile
        bare = pathlib.Path(tempfile.mkdtemp())
        with mock.patch.object(doctor, "_run_pi", return_value=self.FAKE_PI):
            checks = doctor.run_checks(bare)
        by_name = {c.name: c for c in checks}
        self.assertFalse(by_name["factory"].ok)

    def test_detail_lines_stay_bounded(self):
        for check in self.checks():
            self.assertLessEqual(len(check.detail), 200)


if __name__ == "__main__":
    unittest.main()
