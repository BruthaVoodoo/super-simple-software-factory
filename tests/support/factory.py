"""Scratch targets and real-installer invocation for installation tests.

Scratch directories live OUTSIDE the source checkout; teardown removes only
what a test created. No helper here reimplements the installer — tests run
the real `scripts/install.py`.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support.environment import child_env

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / ".claude" / "skills" / "sssf"
TEMPLATE = SKILL / "templates"


class FactoryTestCase(unittest.TestCase):
    """Base for tests that need a disposable target repo and scratch HOME."""

    def setUp(self) -> None:
        super().setUp()
        self._scratch = Path(tempfile.mkdtemp(prefix="sssf-test-"))
        self.addCleanup(self._cleanup_scratch)
        self.target = self._scratch / "target"
        self.target.mkdir()
        self.env = child_env(self._scratch / "home")

    def _cleanup_scratch(self) -> None:
        """Remove only the scratch directory this test owns."""
        shutil.rmtree(self._scratch, ignore_errors=True)


def stamp(target: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the real installer against a scratch target."""
    return subprocess.run(
        [sys.executable, str(SKILL / "scripts" / "install.py")],
        cwd=target, env=env, capture_output=True, text=True, timeout=30,
    )


def git(target: Path, args: list[str], env: dict[str, str]) -> str:
    """Run a checked Git command inside a scratch repo."""
    result = subprocess.run(["git", *args], cwd=target, env=env,
                            capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout
