"""Smoke acceptance: config derivation, claim gates, and evidence checks.

The smoke run is a bounded two-call probe/recall ADW that proves the real Pi
runtime end to end: read a file, write a receipt, then recall a value from
conversation WITHOUT tools or reinjection. It is acceptance evidence only —
it certifies nothing about builder output quality.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .agents import resolve
from .data_types import (
    AgentConfig,
    EnvelopeBase,
    GateReport,
    PromptEngineering,
    SSSFConfig,
)
from .runner import Run

PROMPT_DIR = "adws/adw_data/prompt_engineering/smoke"


def configure_probe(cfg: SSSFConfig) -> SSSFConfig:
    """Copy the selected config and ADD a smoke-only role derived from scout.

    Only the smoke agent's model/thinking come from the configured scout; the
    original roster is carried over untouched. The smoke role has tools
    `read,write`, no harness extensions, `writes=[]`, and the smoke prompts.
    """
    try:
        scout = resolve(cfg, "scout")
    except SystemExit as error:
        raise SystemExit(
            f"smoke: derive the probe model from a 'scout' agent — {error}")
    probe_cfg = cfg.model_copy(deep=True)
    probe_cfg.agents.append(AgentConfig(
        name="smoke", coding_agent="pi", model=scout.model,
        thinking=scout.thinking, color="",
        purpose="bounded real-Pi smoke probe/recall",
        prompt_engineering=PromptEngineering(
            system=f"{PROMPT_DIR}/system.md", user=f"{PROMPT_DIR}/user.md"),
        harness_engineering=[], tools=["read", "write"], writes=[]))
    return probe_cfg


def receipt_gate(expected: Path) -> Callable:
    """The receipt must be declared as the EXACT expected path and be nonempty."""
    def gate(envelope: EnvelopeBase, run) -> GateReport:
        report = GateReport()
        path = str(expected)
        exact = list(envelope.artifacts) == [path]
        report.check(f"receipt artifact is exactly {path}", exact,
                     "declared" if exact
                     else f"declared {list(envelope.artifacts)!r}")
        if Path(expected).is_file():
            size = Path(expected).stat().st_size
            report.check("receipt is nonempty", size > 0, f"{size}B")
        else:
            report.check("receipt is nonempty", False, "receipt file missing")
        return report
    return gate


def recall_gate(nonce: str) -> Callable:
    """The recall summary must equal the remembered nonce — never disclosed
    in the correction text, or a model could copy it out of the violation."""
    def gate(envelope: EnvelopeBase, run) -> GateReport:
        matches = envelope.summary == nonce
        return GateReport().check(
            "recall summary matches the remembered value", matches,
            "matches" if matches
            else "summary does not match the remembered value")
    return gate


@dataclass
class SmokeEvidence:
    """Recorded after the probe call, before recall starts."""
    probe_file: Path
    receipt_file: Path
    recall_raw_offset: int          # byte offset where probe output ends
    first_pi_session_id: str        # the session header id the probe produced


def raw_output_path(run: Run) -> Path:
    return run.session_dir / "smoke" / "raw_output.jsonl"


def session_header_id(raw_path: Path) -> str:
    """The session id from the first `session`-type wire event."""
    if not Path(raw_path).is_file():
        return ""
    for line in Path(raw_path).read_text().splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "session":
            return str(event.get("id") or event.get("sessionId") or "")
    return ""


def capture_evidence(run: Run, probe_file: Path, receipt_file: Path) -> SmokeEvidence:
    raw = raw_output_path(run)
    return SmokeEvidence(
        probe_file=probe_file, receipt_file=receipt_file,
        recall_raw_offset=raw.stat().st_size if raw.is_file() else 0,
        first_pi_session_id=session_header_id(raw))


def _count(conn, sql: str, params: tuple) -> int:
    return conn.execute(sql, params).fetchone()[0]


def verify_trace(run: Run, evidence: SmokeEvidence) -> GateReport:
    """Verify the persisted smoke run, not the agent's claims.

    Checks: phases succeeded; two valid envelopes; the probe produced real
    tool evidence; the recall produced none (in the trace AND in the raw wire
    output after the saved offset); the Pi session identity is unchanged; and
    the session file continues the same conversation.
    """
    report = GateReport()
    conn = run.tracer.conn

    unmet = _count(conn, "SELECT COUNT(*) FROM phases WHERE adw_id=? AND "
                         "status != 'success'", (run.adw_id,))
    report.check("all phases succeeded", unmet == 0,
                 f"{unmet} unmet phase(s)" if unmet else "every phase succeeded")

    valid = _count(conn, "SELECT COUNT(*) FROM envelopes WHERE adw_id=? AND valid=1",
                   (run.adw_id,))
    report.check("two valid envelopes (probe + recall)", valid == 2,
                 f"{valid} valid envelope(s)")

    probe_tools = _count(conn, "SELECT COUNT(*) FROM events WHERE adw_id=? AND "
                               "type='tool_call' AND phase_id LIKE '%probe'",
                         (run.adw_id,))
    report.check("probe produced read/write evidence", probe_tools >= 1,
                 f"{probe_tools} tool call(s) during probe")

    recall_tools = _count(conn, "SELECT COUNT(*) FROM events WHERE adw_id=? AND "
                                "type='tool_call' AND phase_id LIKE '%recall'",
                          (run.adw_id,))
    report.check("recall used no tools", recall_tools == 0,
                 f"{recall_tools} tool call(s) during recall")

    _verify_raw_output(run, evidence, report)

    rows = conn.execute("SELECT session_id FROM agent_sessions WHERE adw_id=? "
                        "AND agent='smoke'", (run.adw_id,)).fetchall()
    ids = {row[0] for row in rows}
    unchanged = ids == {evidence.first_pi_session_id}
    report.check("pi session identity is unchanged", unchanged,
                 f"session ids {sorted(ids)!r}" if not unchanged else "one session")

    session_dir = run.session_dir / "smoke" / "pi_sessions"
    files = ([p for p in session_dir.iterdir()
              if evidence.first_pi_session_id in p.name]
             if session_dir.is_dir() else [])
    report.check("pi session file continues the same conversation",
                 len(files) >= 1,
                 f"no session file for {evidence.first_pi_session_id}"
                 if not files else f"{len(files)} session file(s)")
    return report


def _verify_raw_output(run: Run, evidence: SmokeEvidence, report: GateReport) -> None:
    """The recall's raw wire output: no tool events, no new session identity."""
    raw = raw_output_path(run)
    if not raw.is_file():
        report.check("raw wire output exists", False, "raw output missing")
        return
    report.check("raw wire output exists", True, f"{raw.stat().st_size}B")
    with raw.open("rb") as handle:
        handle.seek(evidence.recall_raw_offset)
        tail = handle.read().decode("utf-8", errors="replace")
    tool_events, foreign_session = 0, []
    for line in tail.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = str(event.get("type", ""))
        if etype.startswith("tool_execution"):
            tool_events += 1
        if etype == "message_end":
            message = event.get("message", {})
            if any(isinstance(block, dict) and block.get("type") == "toolCall"
                   for block in message.get("content", []) or []):
                tool_events += 1
        if etype == "session":
            session_id = str(event.get("id") or event.get("sessionId") or "")
            if session_id and session_id != evidence.first_pi_session_id:
                foreign_session.append(session_id)
    report.check("recall wire output used no tools", tool_events == 0,
                 f"{tool_events} tool event(s) after the probe")
    report.check("recall stayed in the same pi session", not foreign_session,
                 f"new session id(s) {foreign_session!r}" if foreign_session
                 else "no session switch")
