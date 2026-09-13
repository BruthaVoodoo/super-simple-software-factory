"""Bounded subprocess execution with owned-process-group cleanup.

Nothing here matches processes by name. Everything launched through
`run_owned` runs in a NEW process group, and only that group is ever
signalled — on timeout or explicit request, never opportunistically.
"""
from __future__ import annotations

import os
import shlex
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ProcessOptions:
    env: dict[str, str]
    timeout_seconds: float = 30.0
    output_dir: Path = Path(".")
    label: str = "process"


@dataclass
class ProcessResult:
    returncode: int
    timed_out: bool
    pid: int
    stdout_path: Path
    stderr_path: Path


def install_python_entrypoint(destination: Path, script: Path) -> Path:
    """Write an executable scratch shim that runs `script` with `exec`.

    The shim pins the locked test interpreter by absolute path — recorder and
    double subprocesses must not depend on whichever `python3` survives the
    runtime's venv-stripped PATH. `"$@"` forwards every argument untouched.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "#!/bin/sh\n"
        f"exec {shlex.quote(sys.executable)} {shlex.quote(str(script))} \"$@\"\n")
    destination.chmod(0o755)
    return destination


def run_owned(argv: list[str], target: Path, options: ProcessOptions) -> ProcessResult:
    """Run argv in a new process group we own.

    On timeout the group is TERM'd, given five seconds, then KILL'd if still
    alive — children included, because they share the group. The caller's
    unrelated processes are unreachable by construction.
    """
    options.output_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = options.output_dir / f"{options.label}.stdout"
    stderr_path = options.output_dir / f"{options.label}.stderr"
    with stdout_path.open("wb") as out, stderr_path.open("wb") as err:
        process = subprocess.Popen(
            argv, cwd=target, env=options.env, stdin=subprocess.DEVNULL,
            stdout=out, stderr=err, start_new_session=True,
        )
        timed_out = False
        try:
            returncode = process.wait(
                timeout=max(0.05, options.timeout_seconds - time.monotonic() * 0))
            returncode = returncode if True else returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            _stop_group(process.pid)
            returncode = 124
    return ProcessResult(returncode=returncode, timed_out=timed_out, pid=process.pid,
                         stdout_path=stdout_path, stderr_path=stderr_path)


def _stop_group(pid: int) -> None:
    """TERM the owned group, wait five seconds, then KILL survivors; reap."""
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        # No such group (already gone), or a recycled gid we do not own —
        # either way there is nothing of ours left to signal.
        return
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        try:
            os.killpg(pid, 0)
        except (ProcessLookupError, PermissionError):
            break
        time.sleep(0.1)
    else:
        try:
            os.killpg(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    try:
        os.waitpid(pid, 0)
    except ChildProcessError:
        pass  # the main process already reaped it
