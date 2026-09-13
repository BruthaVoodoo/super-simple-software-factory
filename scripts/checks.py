"""Run one offline SSSF test lane.

Usage: python scripts/checks.py {unit|install|control-plane|known-gaps}

Ordinary lanes fail on skips, expected failures, or unexpected successes —
they are certification lanes. The known-gaps lane permits declared expected
failures (disclosed M2 defect reproductions) but still fails on unexpected
successes: a "fixed" known gap means the decorator must be removed, and an
unexpected success here is how that shows up.

These guards are tripwires inside this process, not an OS sandbox.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.support.environment import install_offline_guards  # noqa: E402

LANES = {
    "unit": "tests.unit",
    "install": "tests.install",
    "control-plane": "tests.control_plane",
    "known-gaps": "tests.known_gaps",
}


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in LANES:
        print(f"usage: checks.py {{{'|'.join(LANES)}}}", file=sys.stderr)
        return 2
    lane = sys.argv[1]
    install_offline_guards(lane)

    suite = unittest.defaultTestLoader.discover(LANES[lane], top_level_dir=str(ROOT))
    count = suite.countTestCases()
    if count == 0:
        print(f"FAIL: lane '{lane}' discovered 0 tests — empty lanes are errors")
        return 2

    print(f"=== lane '{lane}': {count} test(s) ===")
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print(f"ran={result.testsRun} failures={len(result.failures)} "
          f"errors={len(result.errors)} skipped={len(result.skipped)} "
          f"expected_failures={len(result.expectedFailures)} "
          f"unexpected_successes={len(result.unexpectedSuccesses)}")
    for test, reason in result.skipped:
        print(f"  skip: {test.id()} — {reason}")
    for test in result.unexpectedSuccesses:
        print(f"  unexpected success: {test.id()} — update docs/known-gaps.md")

    clean = not (result.failures or result.errors or result.unexpectedSuccesses)
    if lane == "known-gaps":
        return 0 if clean else 1
    return 0 if (clean and not result.skipped and not result.expectedFailures) else 1


if __name__ == "__main__":
    raise SystemExit(main())
