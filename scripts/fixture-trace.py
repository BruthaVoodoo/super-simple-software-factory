#!/usr/bin/env -S uv run
# /// script
# dependencies = []
# ///
"""Generate deterministic fixture traces for visualizer development.

Usage:
    uv run --locked --group test python scripts/fixture-trace.py TARGET_DIR

Writes TARGET_DIR/fixture.db (+ per-run events JSONL) containing the FIVE
canonical run shapes the UI must handle:

    fixture-success        2 phases, spanned tool calls, quality events, handoff
    fixture-gate-fail      gate checks with violations, repair_summary gate_exhausted
    fixture-parse-fail     invalid envelope rows, repair_summary parse_exhausted
    fixture-not-accepted   phases succeeded but the acceptance criterion failed
    fixture-running        mid-flight: a running phase, an open process row

Ids, sequences, and token counts are fixed constants. The ONLY nondeterminism
is timestamps (documented in the contract); UI behavior must not depend on
them. No agents, no Pi, no network — pure tracer writes.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.support.imports import bootstrap  # noqa: E402

bootstrap()

from adw_modules.data_types import (  # noqa: E402
    AgentConfig,
    EventRecord,
    GateReport,
    Phase,
    PhaseParams,
    PromptEngineering,
    SSSFConfig,
)
from adw_modules.tracer import Tracer  # noqa: E402
from adw_modules.utils import now_iso  # noqa: E402

USAGE = {"input_tokens": 10, "output_tokens": 2, "cache_read_tokens": 0,
         "cache_write_tokens": 0, "reasoning_tokens": 0, "total_tokens": 12,
         "input_cost": 0.01, "output_cost": 0.002, "cache_read_cost": 0.0,
         "cache_write_cost": 0.0, "total_cost": 0.012}


def make_tracer(out_dir: Path, adw_id: str) -> Tracer:
    return Tracer(out_dir / "fixture.db",
                  out_dir / "sessions" / adw_id / "events.jsonl")


def start(tracer: Tracer, adw_id: str) -> None:
    tracer.session_start(adw_id, "fixture-engineer", adw_name="fixture")


def phase(tracer: Tracer, adw_id: str, seq: int, name: str, status: str,
          description: str, error: str | None = None) -> Phase:
    phase_row = Phase(phase_id=f"{adw_id}_{seq:02d}_{name}", adw_id=adw_id,
                      seq=seq, params=PhaseParams(
                          name=name, kind="code", owner="fixture",
                          description=description),
                      status=status, started_at=now_iso(),
                      ended_at=now_iso(), error=error)
    tracer.phase_upsert(phase_row)
    tracer.event(EventRecord(adw_id=adw_id, phase_id=phase_row.phase_id,
                             type="phase_start", name=name,
                             payload={"kind": "code", "owner": "fixture",
                                      "description": description}))
    tracer.event(EventRecord(adw_id=adw_id, phase_id=phase_row.phase_id,
                             type="phase_end", name=name,
                             payload={"status": status}))
    return phase_row


def tool_call(tracer: Tracer, adw_id: str, phase_row: Phase, name: str,
              payload: dict) -> str:
    return tracer.event(EventRecord(
        adw_id=adw_id, phase_id=phase_row.phase_id, type="tool_call",
        name=name, payload=payload, started_at=now_iso(), ended_at=now_iso(),
        tokens=12))


def agent_rows(tracer: Tracer, adw_id: str, phase_row: Phase, *, tokens: int,
               valid: bool, attempt: int) -> None:
    tracer.envelope_row(phase_row, "scout", "GenericOutput",
                        json.dumps({"raw": "not json" if not valid
                                    else "synthetic"}), valid, attempt)
    tracer.agent_session_row(adw_id, AgentConfig(
        name="scout", prompt_engineering=PromptEngineering(system="s", user="u")),
        f"sssf-{adw_id}-scout-0001", context_tokens=6304, context_window=1_100_000)
    tracer.event(EventRecord(
        adw_id=adw_id, phase_id=phase_row.phase_id, type="agent_start",
        name="scout", payload={"model": "opencode/gpt-5.6-luna",
                               "session_id": f"sssf-{adw_id}-scout-0001",
                               "session_continued": attempt > 1,
                               "coding_agent": "pi", "tools": ["read", "write"],
                               "harness_engineering": []}))
    tracer.event(EventRecord(
        adw_id=adw_id, phase_id=phase_row.phase_id, type="agent_end",
        name="scout", tokens=tokens, payload={"cost": tokens * 0.001,
                                              "usage": {**USAGE, "total_tokens": tokens,
                                                        "total_cost": tokens * 0.001},
                                              "context_tokens": 6304,
                                              "context_window": 1_100_000}))


def repair_summary(tracer: Tracer, adw_id: str, phase_row: Phase, *,
                   sends: int, json_attempts: int, gate_attempts: int,
                   violations: list[str], outcome: str) -> None:
    tracer.event(EventRecord(
        adw_id=adw_id, phase_id=phase_row.phase_id, type="log",
        name="repair_summary",
        payload={"agent": "scout", "sends": sends,
                 "json_attempts": json_attempts, "gate_attempts": gate_attempts,
                 "violations": violations, "outcome": outcome}))


def build_success(tracer: Tracer) -> None:
    adw_id = "fixture-success"
    start(tracer, adw_id)
    p1 = phase(tracer, adw_id, 1, "probe", "success", "Read the probe file")
    tool_call(tracer, adw_id, p1, "read: apps/inkwell/README.md",
              {"tool": "read", "tool_call_id": "fix-1", "ok": True,
               "label": "read: apps/inkwell/README.md"})
    p2 = phase(tracer, adw_id, 2, "test", "success", "Run the configured suite")
    tool_call(tracer, adw_id, p2, "quality:test",
              {"area": "backend", "operation": "build", "command": "pytest -q",
               "returncode": 0, "passed": True,
               "output_artifact": "quality/test/command.log"})
    tool_call(tracer, adw_id, p2, "quality:lint",
              {"area": "backend", "operation": "lint", "command": "ruff check .",
               "returncode": 0, "passed": True,
               "output_artifact": "quality/lint/command.log"})
    agent_rows(tracer, adw_id, p1, tokens=12, valid=True, attempt=1)
    repair_summary(tracer, adw_id, p1, sends=1, json_attempts=0,
                   gate_attempts=0, violations=[], outcome="success")
    tracer.session_finish(adw_id, ok=True)
    tracer.conn.execute("UPDATE sessions SET request='build the widget', "
                        "total_tokens=24, total_cost=0.024 WHERE adw_id=?",
                        (adw_id,))


def build_gate_fail(tracer: Tracer) -> None:
    adw_id = "fixture-gate-fail"
    start(tracer, adw_id)
    p1 = phase(tracer, adw_id, 1, "build", "fail",
               "Implement the request", error="scout failed gates after "
               "2 attempt(s):\n- plan.md: declared artifact does not exist")
    report = GateReport().check("plan.md", False,
                                "declared artifact does not exist")
    tracer.gate_row(p1, "artifacts_exist", report, 1)
    tracer.event(EventRecord(adw_id=adw_id, phase_id=p1.phase_id,
                             type="gate_fail", name="artifacts_exist",
                             payload={"attempt": 1, "violations": report.violations,
                                      "checks": [c.model_dump() for c in report.checks]}))
    agent_rows(tracer, adw_id, p1, tokens=12, valid=True, attempt=1)
    repair_summary(tracer, adw_id, p1, sends=2, json_attempts=0,
                   gate_attempts=2, violations=report.violations,
                   outcome="gate_exhausted")
    tracer.session_finish(adw_id, ok=False)
    tracer.conn.execute("UPDATE sessions SET request='build the widget', "
                        "total_tokens=36, total_cost=0.036 WHERE adw_id=?",
                        (adw_id,))


def build_parse_fail(tracer: Tracer) -> None:
    adw_id = "fixture-parse-fail"
    start(tracer, adw_id)
    p1 = phase(tracer, adw_id, 1, "build", "fail", "Implement the request",
               error="scout never produced valid GenericOutput JSON: "
                     "no JSON object found in the response")
    tracer.envelope_row(p1, "scout", "GenericOutput",
                        json.dumps({"raw": "I think maybe the plan is..."}),
                        False, 1)
    tracer.envelope_row(p1, "scout", "GenericOutput",
                        json.dumps({"raw": "the plan file plan.md contains..."})
                        , False, 2)
    agent_rows(tracer, adw_id, p1, tokens=12, valid=False, attempt=1)
    repair_summary(tracer, adw_id, p1, sends=3, json_attempts=3,
                   gate_attempts=0, violations=[],
                   outcome="parse_exhausted")
    tracer.session_finish(adw_id, ok=False)
    tracer.conn.execute("UPDATE sessions SET request='build the widget', "
                        "total_tokens=36, total_cost=0.036 WHERE adw_id=?",
                        (adw_id,))


def build_not_accepted(tracer: Tracer) -> None:
    adw_id = "fixture-not-accepted"
    start(tracer, adw_id)
    p1 = phase(tracer, adw_id, 1, "test", "success", "Run the configured suite")
    agent_rows(tracer, adw_id, p1, tokens=12, valid=True, attempt=1)
    repair_summary(tracer, adw_id, p1, sends=1, json_attempts=0,
                   gate_attempts=0, violations=[], outcome="success")
    tracer.event(EventRecord(adw_id=adw_id, phase_id=p1.phase_id,
                             type="error", name="not_accepted",
                             payload={"reason": "the suite still failed after "
                                                "3 fix attempt(s)"}))
    tracer.session_finish(adw_id, ok=False)
    tracer.conn.execute("UPDATE sessions SET request='build the widget', "
                        "total_tokens=12, total_cost=0.012 WHERE adw_id=?",
                        (adw_id,))


def build_running(tracer: Tracer) -> None:
    adw_id = "fixture-running"
    start(tracer, adw_id)
    p1 = phase(tracer, adw_id, 1, "build", "running", "Implement the request")
    tracer.process_start(adw_id, "adw", "", 424242,
                         "adw_build.py --adw-id fixture-running")
    tracer.process_start(adw_id, "agent", "scout", 424243,
                         "pi scout opencode/gpt-5.6-luna")
    agent_rows(tracer, adw_id, p1, tokens=12, valid=True, attempt=1)
    tracer.conn.execute("UPDATE sessions SET request='build the widget' "
                        "WHERE adw_id=?", (adw_id,))


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".fixtures")
    out_dir.mkdir(parents=True, exist_ok=True)
    # Regeneration must be clean: phase upserts would dedupe, but events,
    # gates, and envelopes append — a reused db would double every row.
    for stale in out_dir.glob("fixture.db*"):
        stale.unlink()
    shutil.rmtree(out_dir / "sessions", ignore_errors=True)
    tracer = make_tracer(out_dir, "fixture")
    try:
        build_success(tracer)
        build_gate_fail(tracer)
        build_parse_fail(tracer)
        build_not_accepted(tracer)
        build_running(tracer)
        # A cleanly closed WAL db has no -wal file, and a READONLY bun:sqlite
        # open cannot create the shared-memory file for it (unable to open
        # database file). Fixture dbs are static snapshots, so convert to
        # DELETE journaling — the server reads them fine and warns, correctly,
        # that live reads would block.
        tracer.conn.execute("PRAGMA journal_mode=DELETE;")
    finally:
        tracer.conn.close()
    print(f"fixture traces written to {out_dir / 'fixture.db'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
