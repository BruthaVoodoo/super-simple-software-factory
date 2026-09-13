"""Conservative stop of trace-recorded processes. Fail closed, always.

The recipe name is `kill`, but this module earns the name: it signals ONLY
processes whose current identity ties them to THIS repository and THIS run —
the Pi child by its exact absolute `--session-dir` beneath the configured
run directory, the ADW parent by its absolute script path under `adws/` plus
the explicit `--adw-id`. An unverifiable row is reported and left alone,
because pid recycling means a stale row can point at an innocent process.

Signals require an interactive confirmation: the verified PID list is shown
and the operator must retype the run id. Non-interactive invocation refuses.
Only SIGTERM is sent; a surviving process is reported live, and no trace row
is manufactured for it — M2 owns real lifecycle ownership.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from . import operations

TERM_GRACE_SECONDS = 5.0


def _ps_command(pid: int) -> str:
    result = subprocess.run(["ps", "-p", str(pid), "-o", "command="],
                            capture_output=True, text=True, timeout=5)
    return result.stdout.strip()


def _identity_verified(kind: str, pid: int, command: str,
                       target_root: Path, adw_id: str) -> bool:
    """True when the live command string still matches THIS run in THIS repo."""
    if not command:
        return False
    if kind == "agent":
        marker = f"--session-dir {(target_root / 'adws' / 'adw_data' / 'sessions' / adw_id).resolve()}"
        return marker in command
    if kind == "adw":
        script = command.split(" ", 1)[0]
        try:
            script_path = Path(script).resolve()
        except OSError:
            return False
        under_adws = (target_root / "adws").resolve() in script_path.parents
        return under_adws and f"--adw-id {adw_id}" in command
    return False


def _live_rows(config_path: str, adw_id: str) -> list[dict]:
    db_path = operations._config_db_path(config_path)
    connection = operations._readonly_connection(db_path)
    try:
        rows = connection.execute(
            "SELECT kind, pid, command FROM processes "
            "WHERE adw_id = :adw_id AND ended_at IS NULL "
            "ORDER BY CASE kind WHEN 'agent' THEN 0 ELSE 1 END, id DESC",
            {"adw_id": adw_id},
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows]


def stop_run(config_path: str, adw_id: str) -> int:
    """Verify, confirm, then TERM — children before the ADW parent."""
    target_root = Path(config_path).resolve().parent.parent.parent
    verified: list[tuple[str, int, str]] = []
    for row in _live_rows(config_path, adw_id):
        pid = int(row["pid"])
        if pid <= 1 or pid == os.getpid():
            print(f"  refusing pid {pid} (protected)")
            continue
        command = _ps_command(pid)
        if not _identity_verified(row["kind"], pid, command, target_root, adw_id):
            print(f"  process identity not verified for pid {pid} "
                  f"({row['kind']}) — leaving it alone")
            continue
        verified.append((row["kind"], pid, command))

    if not verified:
        print("no verified live processes recorded for this run")
        return 1

    print("verified live processes for run", adw_id)
    for kind, pid, command in verified:
        print(f"  {kind} {pid} — {command}")
    answer = input(f"type the run id ({adw_id}) to send SIGTERM: ").strip()
    if answer != adw_id:
        print("confirmation failed — nothing signalled")
        return 1

    failed = 0
    for kind, pid, _command in verified:   # agents first, then the adw row
        try:
            os.kill(pid, signal.SIGTERM)
            print(f"  SIGTERM sent to {kind} {pid}")
        except ProcessLookupError:
            print(f"  {kind} {pid} already gone")
        except OSError as error:
            print(f"  could not signal {kind} {pid}: {error}")
            failed += 1
    deadline = time.monotonic() + TERM_GRACE_SECONDS
    for kind, pid, _command in verified:
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            time.sleep(0.1)
        else:
            print(f"  {kind} {pid} is still live after SIGTERM — leaving it")
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit("import this module through manage.py")
