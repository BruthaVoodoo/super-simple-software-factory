"""Session lifecycle: pin-or-create an adw_id, build the Run object.

`ensure(cfg, adw_id)` joins the session if it exists or creates it under
exactly that id (pinned ids for repeatable runs); omitted, a fresh id is
minted and printed so the next ADW can pick it up.
"""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from .data_types import EventRecord, SSSFConfig
from .runner import Run
from .tracer import Tracer
from . import git_helper
from .utils import engineer_name, new_id


def _finalize_when_killed(run: Run) -> None:
    """A killed run closes its own trace AND its actual children.

    Python's default SIGTERM handling exits without unwinding, so `just kill`
    (or any `kill <pid>`) would leave the session reading `running` forever and
    its process rows open — the trace would claim work is in flight that is
    already dead. Worse (observed as M2-PROC-01): it also orphaned the live
    coding-agent child, which kept running with no owner. The handler now
    terminates every registered child — TERM, five seconds, KILL — BEFORE
    closing the session, so the trace never claims an end the process tree
    hasn't reached.
    """
    def handler(signum, _frame):
        for pid in list(run._children):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        # The main thread is interrupted inside this handler, so the normal
        # on_exit bookkeeping cannot run — reap the children here ourselves.
        deadline = time.monotonic() + 5.0
        while run._children and time.monotonic() < deadline:
            for pid in list(run._children):
                try:
                    waited, _ = os.waitpid(pid, os.WNOHANG)
                    if waited:
                        run._children.discard(pid)
                except ChildProcessError:
                    run._children.discard(pid)   # reaped elsewhere or gone
            if run._children:
                time.sleep(0.05)
        for pid in list(run._children):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        run.tracer.session_finish(run.adw_id, ok=False)   # also closes process rows
        raise SystemExit(128 + signum)

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, handler)


def ensure(cfg: SSSFConfig, adw_id: str | None = None,
           *, isolate_branch: bool = False) -> Run:
    adw_id = adw_id or new_id(8)
    tracer = Tracer(cfg.observability.db,
                    f"{cfg.defaults.data_dir}/sessions/{adw_id}/events.jsonl")
    run = Run(cfg=cfg, adw_id=adw_id, tracer=tracer, engineer=engineer_name())
    tracer.session_start(adw_id, run.engineer, adw_name=Path(sys.argv[0]).stem)
    if isolate_branch:
        # Workflows that modify and commit code run on a dedicated branch: the
        # operator's branch ref never moves, and pre-existing working-tree
        # state (dirty or untracked) travels with the checkout untouched. The
        # run ends ON the branch — the operator merges or discards it.
        branch = f"sssf/{adw_id}"
        if git_helper.current_branch() != branch:
            git_helper.create_branch(branch)
        run.tracer.event(EventRecord(
            adw_id=adw_id, type="log", name="branch_isolated",
            payload={"branch": branch,
                     "base": git_helper.short_sha("HEAD")}))
    # This process is the run. Record it before any phase opens, so a run that
    # hangs in its first agent call is still killable by adw_id.
    tracer.process_start(adw_id, "adw", "", os.getpid(),
                         " ".join([Path(sys.argv[0]).name, *sys.argv[1:]]))
    _finalize_when_killed(run)
    run.console.session_started(adw_id, run.engineer)
    return run
