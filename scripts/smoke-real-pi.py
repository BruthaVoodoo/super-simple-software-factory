#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""Build a fresh example-based target and supervise live smoke acceptance.

Development command: `SSSF_SMOKE_MODEL=provider/model-id just smoke-real-pi`.

Requires an explicit model — never a default — and a real `pi` executable.
Exports the pinned Inkwell app (Task 3), installs the current templates,
writes a smoke-only local roster, and runs the INSTALLED `just smoke-real-pi`
in that target as a supervised child (owned process group, 180s bound,
stdin=DEVNULL). Live-streaming evidence means observing a tool_call for this
ADW while its probe phase is still running and the launched process is still
alive — never a final-count inference. This command spends real tokens and
can fail; it is not an offline test.

Raw evidence lands in gitignored test-results/real-pi/. Output prints only
non-secret identifiers, statuses, paths, durations, and reported usage.
"""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOUND_SECONDS = 180.0
POLL_SECONDS = 0.2
EVIDENCE_DIR = ROOT / "test-results" / "real-pi"
FORBIDDEN_PATH_MARKERS = ("pi-double", "argv-recorder", "synthetic_pi")
RECEIPT_TEXT = "SSSF smoke receipt\n"


def _refuse(message: str) -> None:
    print(f"smoke: refusing — {message}", file=sys.stderr)
    raise SystemExit(1)


def preflight() -> dict:
    """Fail before creating anything unless this is a real, explicit live run."""
    model = os.environ.get("SSSF_SMOKE_MODEL", "").strip()
    if not model:
        _refuse("set SSSF_SMOKE_MODEL=provider/model-id — the smoke run has no "
                "default model and never inspects credentials")
    if os.environ.get("SSSF_TEST_DOUBLE"):
        _refuse("SSSF_TEST_DOUBLE is set; this lane runs real Pi or nothing")
    pi = os.environ.get("PI_PATH") or _which("pi")
    if not pi:
        _refuse("no real pi on PI_PATH or PATH")
    for marker in FORBIDDEN_PATH_MARKERS:
        if marker in pi or marker in os.environ.get("PATH", ""):
            _refuse(f"the pi executable or PATH mentions {marker!r}")
    return {"model": model, "pi": pi}


def _which(program: str) -> str:
    for directory in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(directory) / program
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return ""


def _git(target: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=target,
                            capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout


def build_target(model: str) -> tuple[Path, dict[str, str]]:
    """Fresh pinned-Inkwell target + smoke-only roster, committed before launch."""
    sys.path.insert(0, str(ROOT))
    from tests.support.environment import child_env
    from tests.support.example import prepare_example_target

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    target = EVIDENCE_DIR / f"target-{time.strftime('%Y%m%d-%H%M%S')}"
    if target.exists():
        _refuse(f"target {target} already exists")
    # The scratch HOME must live OUTSIDE the target: child_env() creates it,
    # and prepare_example_target rejects a nonempty destination.
    scratch = EVIDENCE_DIR / f"scratch-{time.strftime('%Y%m%d-%H%M%S')}"
    before = prepare_example_target(target, child_env(scratch / "home"))

    config_dir = target / "adws/adw_sssf_config"
    prompts = target / "adws/adw_data/prompt_engineering"
    (prompts / "scout").mkdir(parents=True, exist_ok=True)
    (config_dir / "sssf.config.yaml").write_text(f"""
defaults:
  model: {model}
  thinking: medium
  data_dir: adws/adw_data

agents:
  - name: scout
    model: {model}
    thinking: medium
    purpose: smoke probe model carrier
    prompt_engineering:
      system: adws/adw_data/prompt_engineering/scout/system.md
      user: adws/adw_data/prompt_engineering/scout/user.md
""")
    (prompts / "scout/system.md").write_text("You carry the smoke model.\n")
    (prompts / "scout/user.md").write_text("{{prompt}}\n")
    _git(target, "add", "adws/adw_sssf_config/sssf.config.yaml",
         "adws/adw_data/prompt_engineering/scout")
    _git(target, "commit", "-m", "smoke-only local roster")
    return target, before


@dataclass
class SupervisionResult:
    returncode: int
    timed_out: bool
    pid: int
    live_event_id: str | None
    live_observed_at: str | None
    stdout_path: Path
    stderr_path: Path


def supervise(argv: list[str], *, target: Path, db_path: Path, adw_id: str,
              timeout: float = BOUND_SECONDS, poll: float = POLL_SECONDS,
              env: dict | None = None) -> SupervisionResult:
    """Run argv as an owned process group and watch the trace live.

    Every `poll` seconds a readonly connection to THIS target's db looks for a
    tool_call on this adw_id while the probe phase is `running` and the child
    is still alive. The first such sighting is the live-streaming evidence.
    On timeout the owned group is TERM'd, given five seconds, then KILL'd.
    """
    from tests.support.processes import _stop_group

    # Capture files live in the target's IGNORED runtime area, or the
    # tracked-tree acceptance check would trip on the harness's own output.
    capture_dir = target / "adws/adw_data/sessions"
    capture_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = capture_dir / "smoke.stdout"
    stderr_path = capture_dir / "smoke.stderr"
    process = subprocess.Popen(
        argv, cwd=target, env=env if env is not None else os.environ.copy(),
        stdin=subprocess.DEVNULL, stdout=stdout_path.open("wb"),
        stderr=stderr_path.open("wb"), start_new_session=True)
    live_event_id = live_observed_at = None
    deadline = time.monotonic() + timeout
    timed_out = False
    while True:
        if process.poll() is not None:
            break
        if time.monotonic() > deadline:
            timed_out = True
            _stop_group(process.pid)
            break
        if live_event_id is None:
            live_event_id, live_observed_at = _observe_live(
                db_path, adw_id, process)
        time.sleep(poll)
    returncode = process.wait() if not timed_out else 124
    return SupervisionResult(
        returncode=returncode, timed_out=timed_out, pid=process.pid,
        live_event_id=live_event_id, live_observed_at=live_observed_at,
        stdout_path=stdout_path, stderr_path=stderr_path)


def _observe_live(db_path: Path, adw_id: str,
                  process: subprocess.Popen) -> tuple[str | None, str | None]:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=1)
    except sqlite3.OperationalError:
        return None, None            # the child has not created the db yet
    try:
        row = conn.execute(
            "SELECT e.event_id FROM events e JOIN phases p ON e.phase_id = p.phase_id "
            "WHERE e.adw_id=? AND e.type='tool_call' AND p.name='probe' "
            "AND p.status='running' LIMIT 1", (adw_id,)).fetchone()
    except sqlite3.OperationalError:
        return None, None            # schema not there yet
    finally:
        conn.close()
    if row and process.poll() is None:
        return row[0], time.strftime("%Y-%m-%dT%H:%M:%S")
    return None, None


def _app_hashes(target: Path) -> dict[str, str]:
    apps = target / "apps" / "inkwell"
    files = ([target / "LICENSE"] + sorted(apps.rglob("*"))
             if apps.is_dir() else [target / "LICENSE"])
    return {str(path.relative_to(target)):
            hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files if path.is_file()}


def verify_acceptance(target: Path, adw_id: str, before: dict[str, str],
                      supervision: SupervisionResult) -> list[str]:
    """Every acceptance check; returns the list of violations (empty = pass)."""
    violations: list[str] = []
    db_path = target / "adws/adw_data/sssf.db"
    if supervision.timed_out:
        violations.append(f"run exceeded {BOUND_SECONDS:.0f}s and was terminated")
    elif supervision.returncode != 0:
        violations.append(f"exit code {supervision.returncode}, expected 0")

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        session = conn.execute("SELECT status, total_tokens, total_cost FROM "
                               "sessions WHERE adw_id=?", (adw_id,)).fetchone()
        if not session or session[0] != "success":
            violations.append(f"session status is "
                              f"{session[0] if session else 'missing'}, expected success")
        valid = conn.execute("SELECT COUNT(*) FROM envelopes WHERE adw_id=? AND "
                             "valid=1", (adw_id,)).fetchone()[0]
        if valid < 2:
            violations.append(f"{valid} valid envelope(s), expected 2")
        recall_tools = conn.execute(
            "SELECT COUNT(*) FROM events WHERE adw_id=? AND type='tool_call' AND "
            "phase_id LIKE '%recall'", (adw_id,)).fetchone()[0]
        if recall_tools:
            violations.append(f"{recall_tools} tool call(s) during recall")
        probe_tools = conn.execute(
            "SELECT COUNT(*) FROM events WHERE adw_id=? AND type='tool_call' AND "
            "phase_id LIKE '%probe'", (adw_id,)).fetchone()[0]
        if not probe_tools:
            violations.append("no probe tool evidence in the trace")
    finally:
        conn.close()

    raw = target / "adws/adw_data/sessions" / adw_id / "smoke" / "raw_output.jsonl"
    if raw.is_file():
        raw_text = raw.read_text()
        if "synthetic_pi" in raw_text:
            violations.append("the raw wire output contains the synthetic marker")
        receipt = target / "adws/adw_data/sessions" / adw_id / "context_handoff" \
            / "smoke-receipt.txt"
        if not receipt.is_file() or receipt.read_text() != RECEIPT_TEXT:
            violations.append("receipt missing or wrong contents")
        if supervision.live_event_id is None:
            violations.append("no live tool_call was observed while the probe "
                              "phase ran — reported unverified, not inferred")
    else:
        violations.append("raw wire output missing")

    after = _app_hashes(target)
    if after != before:
        violations.append("application files changed during the smoke run")
    dirty = _git(target, "status", "--porcelain").strip()
    if dirty:
        violations.append(f"tracked tree is not clean after the run: {dirty!r}")
    return violations


def main() -> int:
    identifiers = preflight()
    model = identifiers["model"]

    sys.path.insert(0, str(ROOT))
    from tests.support.example import prepare_example_target  # noqa: F401

    print(f"smoke: model={model} pi={identifiers['pi']}")
    target, before = build_target(model)
    adw_id = secrets.token_hex(4)

    env = os.environ.copy()
    env["ENGINEER_NAME"] = "sssf-smoke"    # the baseline must not record the operator's identity
    env["SSSF_CONFIG"] = "adws/adw_sssf_config/sssf.config.yaml"

    started = time.monotonic()
    supervision = supervise(
        ["just", "smoke-real-pi", "--probe-file", "apps/inkwell/README.md",
         "--adw-id", adw_id],
        target=target, db_path=target / "adws/adw_data/sssf.db",
        adw_id=adw_id, env=env)
    duration = time.monotonic() - started

    violations = verify_acceptance(target, adw_id, before, supervision)
    tokens = cost = None
    try:
        conn = sqlite3.connect(f"file:{target / 'adws/adw_data/sssf.db'}?mode=ro",
                               uri=True)
        row = conn.execute("SELECT total_tokens, total_cost FROM sessions "
                           "WHERE adw_id=?", (adw_id,)).fetchone()
        if row:
            tokens, cost = row
        conn.close()
    except sqlite3.OperationalError:
        pass

    print(f"\nsmoke: adw_id={adw_id} exit={supervision.returncode} "
          f"duration={duration:.1f}s live_event={supervision.live_event_id} "
          f"tokens={tokens} cost={cost}")
    print(f"smoke: evidence in {EVIDENCE_DIR} (raw, gitignored)")
    if violations:
        for violation in violations:
            print(f"smoke: FAILED — {violation}")
        return 1
    print("smoke: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
