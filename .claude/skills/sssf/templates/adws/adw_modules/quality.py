"""Deterministic quality blocks — CONFIGURED commands, never placeholders.

A block is enabled exactly when it is configured in sssf.config.yaml:

    quality:
      test:
        argv: ["uv", "run", "pytest", "-q"]
        timeout_seconds: 600

Two rules for a real command:
  1. argv LIST, never a shell string — no quoting bugs, no shell injection.
  2. Call binaries by BARE NAME. These blocks inherit the operator's
     environment (utils.operator_env), so `bun`, `uv`, `pytest` resolve
     exactly as they do in their terminal.

A workflow that asks for an unconfigured block fails loudly — it can never
report acceptance on a command that does nothing.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from pathlib import Path
from typing import Callable

from .data_types import (EventRecord, QualityBlock, QualityCheckResult,
                         QualityCheckSpec, QualityResult, VerifyOutput)

QualityBlockSpec = QualityBlock
from .utils import now_iso, operator_env

# How much of a failing command's output rides back inside the envelope. Enough
# for a builder to act on without opening the artifact; bounded so a runaway
# stack trace can't swamp the next agent's context.
TAIL_CHARS = 4_000


def _check_dir(run, name: str) -> Path:
    seq = run.phases[-1].seq if run.phases else 0
    path = run.context_handoff_dir / "quality" / f"{seq:02d}_{name}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _run(spec: QualityCheckSpec, run) -> QualityCheckResult:
    phase = run.phases[-1]
    output_dir = _check_dir(run, spec.name)
    output_artifact = output_dir / "command.log"
    command = shlex.join(spec.argv)
    env = operator_env()             # the engineer's own shell environment

    run.console.note(f"quality {spec.name}: {command}")
    started_at = now_iso()
    clock = time.monotonic()
    stdout = ""
    stderr = ""
    try:
        completed = subprocess.run(
            spec.argv,
            cwd=run.repo_root,
            env=env,
            capture_output=True,
            text=True,
            timeout=spec.timeout_seconds,
        )
        returncode = completed.returncode
        stdout = completed.stdout
        stderr = completed.stderr
    except subprocess.TimeoutExpired as error:
        returncode = 124
        stdout = error.stdout or ""
        stderr = (error.stderr or "") + f"\nTimed out after {spec.timeout_seconds}s."
    except OSError as error:
        # A missing binary lands here as exit 127 with the real message — no
        # pre-flight probe needed, and none wanted.
        returncode = 127
        stderr = str(error)

    duration = time.monotonic() - clock
    output_artifact.write_text(
        f"$ {command}\nexit: {returncode}\nduration_seconds: {duration:.3f}\n"
        f"\n--- stdout ---\n{stdout}\n--- stderr ---\n{stderr}\n"
    )
    passed = returncode == 0
    run.tracer.event(EventRecord(
        adw_id=run.adw_id,
        phase_id=phase.phase_id,
        type="tool_call",
        name=f"quality:{spec.name}",
        payload={
            "area": spec.area,
            "operation": spec.operation,
            "command": command,
            "returncode": returncode,
            "passed": passed,
            "output_artifact": str(output_artifact),
        },
        started_at=started_at,
        ended_at=now_iso(),
    ))
    run.console.note(
        f"quality {spec.name}: {'passed' if passed else 'failed'} "
        f"(exit {returncode}, {duration:.1f}s)"
    )
    return QualityCheckResult(
        name=spec.name,
        area=spec.area,
        operation=spec.operation,
        command=command,
        returncode=returncode,
        passed=passed,
        duration_seconds=duration,
        output_artifact=str(output_artifact),
        output_tail=(stdout + stderr)[-TAIL_CHARS:],
    )


# ── Blocks ────────────────────────────────────────────────────────────────────
# Enabled = configured in sssf.config.yaml. There is no placeholder fallback.

class QualityNotConfigured(RuntimeError):
    """A workflow asked for a quality block that is not configured."""


def _block(run, name: str) -> QualityBlockSpec:
    blocks = run.cfg.quality.blocks
    if name not in blocks:
        raise QualityNotConfigured(
            f"quality block {name!r} is not configured — add to sssf.config.yaml:\n"
            f"  quality:\n    {name}:\n"
            f"      argv: [<the real command, as an argv list>]")
    return blocks[name]


def run_block(run, name: str) -> QualityCheckResult:
    block = _block(run, name)
    return _run(QualityCheckSpec(name=name, area="backend", operation="build",
                                 argv=block.argv,
                                 timeout_seconds=block.timeout_seconds), run)


def run_tests(run) -> QualityResult:
    """The test suite alone, as a QualityResult — the deterministic test phase.

    This is what replaces a `tester` agent once the command is written down. An
    agent rediscovering the runner on every run costs a fortune to learn what a
    subprocess already knows; the repair loop is unchanged, because a failure
    still reaches the builder through `as_envelope` below.
    """
    check = run_block(run, "test")
    failures = ([] if check.passed else
                [f"{check.name}: `{check.command}` exited {check.returncode}\n"
                 f"{check.output_tail}".rstrip()])
    return QualityResult(passed=check.passed, checks=[check], failures=failures,
                         artifacts=[check.output_artifact])


def as_envelope(result: QualityResult, what: str) -> VerifyOutput:
    """Wrap a deterministic result so an agent can be handed it directly.

    Agents hand each other typed envelopes; code blocks return QualityResult.
    This is the adapter, so a failing lint or test run flows back into the
    builder through exactly the same door an agent's report would — the ADW
    script is the only thing that knows the difference.
    """
    return VerifyOutput(
        status="success" if result.passed else "fail",
        summary=(f"{what}: all {len(result.checks)} check(s) passed" if result.passed
                 else f"{what}: {len(result.failures)} of {len(result.checks)} check(s) failed"),
        artifacts=result.artifacts,
        notes_for_next_agent=("" if result.passed else
                              "Fix every failure below. The output is verbatim from the "
                              "command — trust it over any summary."),
        passed=result.passed,
        failures=result.failures,
    )


def run_quality(run) -> QualityResult:
    """Run every CONFIGURED block and collect ALL failures.

    Enabled = configured. Zero configured blocks is a loud error, not a pass —
    a workflow must never report acceptance on commands that do nothing.
    """
    names = sorted(run.cfg.quality.blocks)
    if not names:
        raise QualityNotConfigured(
            "no quality blocks are configured — add to sssf.config.yaml:\n"
            "  quality:\n    test:\n"
            "      argv: [<the real command, as an argv list>]")
    checks = [run_block(run, name) for name in names]
    failures = [
        f"{check.name}: `{check.command}` exited {check.returncode}\n{check.output_tail}".rstrip()
        for check in checks if not check.passed
    ]
    return QualityResult(
        passed=not failures,
        checks=checks,
        failures=failures,
        artifacts=[check.output_artifact for check in checks],
    )
