"""Config loading/validation and agent execution.

Every ADW validates its agents before running (fail fast, nothing spawns
against a half-valid config). Every agent call parses against a concrete
output type; parse failures and gate violations re-prompt the SAME session
with a correction — context intact, bounded retries. Agent proposes, code
disposes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import yaml

from . import agent_pi, permissions, prompts
from .data_types import (AgentCall, AgentConfig, EnvelopeBase, EventRecord,
                         GateCheck, GateReport, Phase, PiRequest, SSSFConfig,
                         UsageBreakdown)
from .utils import new_id

JSON_FIX_ATTEMPTS = 2      # continue-with-correction attempts for malformed JSON


class GateFailure(RuntimeError):
    pass


# ── config ───────────────────────────────────────────────────────────────────

def load_config(path: str = "adws/adw_sssf_config/sssf.config.yaml") -> SSSFConfig:
    raw = yaml.safe_load(Path(path).read_text()) or {}
    defaults = raw.get("defaults", {}) or {}
    for agent in raw.get("agents", []) or []:
        for key in ("coding_agent", "model", "thinking", "color", "tools", "writes"):
            if key in defaults:
                agent.setdefault(key, defaults[key])
        agent.setdefault("harness_engineering", defaults.get("harness_engineering", []))
    return SSSFConfig(**raw)


def resolve(cfg: SSSFConfig, name: str) -> AgentConfig:
    for agent in cfg.agents:
        if agent.name == name:
            return agent
    raise SystemExit(f"agent {name!r} is not defined in the config — "
                     f"available: {[a.name for a in cfg.agents]}")


def validate(cfg: SSSFConfig, required: list[str]) -> None:
    """Fail fast: every required name must resolve to a usable agent."""
    problems = []
    for name in required:
        try:
            agent = resolve(cfg, name)
        except SystemExit as e:
            problems.append(str(e))
            continue
        for label, ref in (("system", agent.prompt_engineering.system),
                           ("user", agent.prompt_engineering.user)):
            if not Path(ref).is_file():
                problems.append(f"agent {name!r}: {label} prompt not found: {ref}")
        for extension in agent.harness_engineering:
            if not Path(extension).is_file():
                problems.append(f"agent {name!r}: extension not found: {extension}")
        try:
            agent_pi.resolve_model(agent.model)
        except ValueError as e:
            problems.append(f"agent {name!r}: {e}")
    if problems:
        raise SystemExit("config validation failed:\n- " + "\n- ".join(problems))


# ── execution ────────────────────────────────────────────────────────────────

def execute(run, phase: Phase, call: AgentCall) -> EnvelopeBase:
    """One agent call: render prompts -> pi run -> typed parse -> gates -> envelope."""
    agent = resolve(run.cfg, phase.params.owner)
    agent_dir = run.session_dir / agent.name
    agent_dir.mkdir(parents=True, exist_ok=True)

    variables = {
        "prompt": call.prompt,
        "previous_envelope": call.previous.model_dump_json(indent=2) if call.previous else "(none)",
        "context_handoff_dir": str(run.context_handoff_dir),
    }
    system_text = prompts.render(agent.prompt_engineering.system, variables)
    user_text = prompts.render(agent.prompt_engineering.user, variables)
    prompts.save(agent_dir / "prompts", "system.md", system_text)
    prompts.save(agent_dir / "prompts", "user.md", user_text)

    session_id, session_continued = _agent_session(run, agent)
    run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                 type="agent_start", name=agent.name,
                                 payload={"model": agent.model, "thinking": agent.thinking,
                                          "color": agent.color,
                                          "session_id": session_id,
                                          "session_continued": session_continued,
                                          "coding_agent": agent.coding_agent,
                                          "purpose": agent.purpose,
                                          "tools": agent.tools,  # None = all tools
                                          "harness_engineering": agent.harness_engineering}))
    if session_continued:
        run.tracer.event(EventRecord(
            adw_id=run.adw_id, phase_id=phase.phase_id, type="log",
            name="session_continued", payload={"agent": agent.name,
                                               "session_id": session_id}))
    run.console.agent_started(agent.name, agent.model, session_id)

    # Parse retries and gate corrections re-enter the SAME pi session, so the
    # last send is the one whose context occupancy is current — while spend is
    # the opposite: every send costs, so usage accumulates across all of them.
    latest: agent_pi.PiResult | None = None
    spent = UsageBreakdown()
    stats = {"sends": 0, "json_attempts": 0, "gate_attempts": 0}

    def send(prompt_text: str) -> agent_pi.PiResult:
        nonlocal latest
        stats["sends"] += 1
        request = PiRequest(
            prompt=prompt_text,
            system_prompt=system_text,
            model=agent.model,
            thinking=agent.thinking,
            session_id=session_id,
            # absolute: these are read by the pi subprocess, which runs in repo_root
            session_dir=str((agent_dir / "pi_sessions").resolve()),
            raw_output_path=str((agent_dir / "raw_output.jsonl").resolve()),
            tools=agent.tools,
            extensions=agent.harness_engineering,
            cwd=str(run.repo_root),
        )
        result = agent_pi.run(
            request,
            on_event=_event_forwarder(run, phase, agent.name),
            on_spawn=lambda pid: _spawn_child(run, phase, agent, pid),
            on_exit=_child_exit(run))
        run.add_usage(result.tokens, result.cost)
        spent.merge(result.usage)
        latest = result
        return result

    # What the tree looked like before this agent got its hands on it. Every
    # send in this phase — first prompt, JSON retries, gate corrections — is
    # measured against this one baseline. save_dir mirrors untracked/ignored
    # bytes so enforcement can restore what Git cannot.
    tree_before = permissions.snapshot(
        run, save_dir=run.session_dir / "permission_state")
    try:
        result = send(user_text)
        envelope, attempt = _parse_with_retries(run, phase, call, result, send,
                                                stats)

        # claim gates — violations flow back into the SAME session as corrections
        for gate_attempt in range(1, max(1, phase.params.retries + 1) + 1):
            violations = []
            for gate in call.gates:
                report = _as_report(gate(envelope, run))
                found = report.violations
                run.tracer.gate_row(phase, gate.__name__, report, gate_attempt)
                run.tracer.event(EventRecord(
                    adw_id=run.adw_id, phase_id=phase.phase_id,
                    type="gate_fail" if found else "gate_pass", name=gate.__name__,
                    payload={"attempt": gate_attempt, "violations": found,
                             "checks": [c.model_dump() for c in report.checks]}))
                run.console.gate_result(gate.__name__, report)
                violations.extend(found)
            if call.gates:
                stats["gate_attempts"] = gate_attempt
            if not violations:
                break
            if gate_attempt > phase.params.retries:
                raise GateFailure(f"{agent.name} failed gates after {gate_attempt} attempt(s):\n- "
                                  + "\n- ".join(violations))
            phase.attempt = gate_attempt
            run.console.retry(agent.name, gate_attempt, phase.params.retries,
                              f"{len(violations)} gate violation(s)")
            correction = ("Your previous response failed validation:\n- "
                          + "\n- ".join(violations)
                          + "\n\nFix these problems, then re-emit ONLY your Report JSON.")
            result = send(correction)
            envelope, attempt = _parse_with_retries(run, phase, call, result, send,
                                                    stats)
    except permissions.PermissionBreach:
        _emit_repair_summary(run, phase, agent, stats, [],
                             outcome="permission_breach")
        _finish_agent_trace(run, phase, agent, spent)
        raise
    except BaseException as error:
        # Enforcement runs on EVERY exit path: a write that happened before a
        # parse exhaustion or gate failure must still be audited and rolled
        # back. A breach replaces the original error (preserved as __cause__).
        try:
            permissions.enforce(run, phase, agent, tree_before)
        except permissions.PermissionBreach as breach:
            run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                         type="error", name="permission_breach",
                                         payload={"agent": agent.name,
                                                  "error": str(breach),
                                                  "writes": agent.writes,
                                                  "during": repr(error)}))
            _emit_repair_summary(run, phase, agent, stats, [],
                                 outcome="permission_breach")
            _finish_agent_trace(run, phase, agent, spent)
            raise breach from error
        outcome = ("gate_exhausted" if isinstance(error, GateFailure)
                   else "parse_exhausted" if "valid" in str(error)
                   and "JSON" in str(error) else "error")
        _emit_repair_summary(run, phase, agent, stats, [], outcome=outcome)
        _finish_agent_trace(run, phase, agent, spent)
        raise
    else:
        touched = permissions.enforce(run, phase, agent, tree_before)
    if touched:
        run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                     type="log", name="paths_touched",
                                     payload={"agent": agent.name, "paths": touched}))

    _persist_envelope(run, phase, agent.name, call, envelope, attempt, valid=True)
    run.console.envelope_summary(envelope)
    context = latest or result
    run.tracer.agent_session_row(run.adw_id, agent, session_id,
                                 context_tokens=context.context_tokens,
                                 context_window=context.context_window)
    run.save_agent_map(agent.name, {"session_id": session_id, "model": agent.model,
                                    "coding_agent": agent.coding_agent})
    run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                 type="handoff", name=agent.name,
                                 payload={"artifacts": envelope.artifacts,
                                          "summary": envelope.summary}))
    _finish_agent_trace(run, phase, agent, spent, context=context)
    run.console.agent_finished(agent.name, spent.total_tokens, spent.total_cost)
    if envelope.status != "success":
        _emit_repair_summary(run, phase, agent, stats, [], outcome="status_fail")
        raise RuntimeError(f"{agent.name} reported status={envelope.status!r}: {envelope.summary}")
    _emit_repair_summary(run, phase, agent, stats, [], outcome="success")
    return envelope


# ── internals ────────────────────────────────────────────────────────────────

def _as_report(result) -> GateReport:
    """Accept a GateReport, or a legacy gate that returned a violations list."""
    if isinstance(result, GateReport):
        return result
    return GateReport(checks=[GateCheck(item=str(v), ok=False) for v in (result or [])])


def _emit_repair_summary(run, phase, agent, stats, violations, outcome) -> None:
    """One persisted row describing the whole repair loop, on every exit
    path — the loop is observable without reading raw events."""
    run.tracer.event(EventRecord(
        adw_id=run.adw_id, phase_id=phase.phase_id, type="log",
        name="repair_summary",
        payload={"agent": agent.name, **stats,
                 "violations": list(violations)[:20], "outcome": outcome}))


def _finish_agent_trace(run, phase, agent, spent, context=None) -> None:
    """Close the agent's trace with its `agent_end` row — on success AND on
    failure. Phase totals, not the last send's: a retried phase paid for
    every attempt. A run that never sent anything has no usage to record."""
    if spent.total_tokens == 0:
        return
    run.tracer.event(EventRecord(
        adw_id=run.adw_id, phase_id=phase.phase_id,
        type="agent_end", name=agent.name,
        tokens=spent.total_tokens,
        payload={"cost": spent.total_cost,
                 "usage": spent.model_dump(),
                 "context_tokens": getattr(context, "context_tokens", 0),
                 "context_window": getattr(context, "context_window", 0)}))


def _agent_session(run, agent: AgentConfig) -> tuple[str, bool]:
    """The session id to use, and whether it CONTINUES a prior conversation
    (the same agent+model already ran in this run and rejoins its window)."""
    entry = run.agent_map.get(agent.name)
    if entry and entry.get("model") == agent.model:
        return entry["session_id"], True     # rejoin the existing context window
    return f"sssf-{run.adw_id}-{agent.name}-{new_id(4)}", False


def _spawn_child(run, phase, agent, pid: int) -> None:
    """Record the child in the trace AND in the run's kill list."""
    run.tracer.process_start(run.adw_id, "agent", agent.name, pid,
                             f"{agent.coding_agent} {agent.name} {agent.model}")
    run.register_child(pid)


def _child_exit(run):
    def on_exit(pid: int) -> None:
        run.tracer.process_end(run.adw_id, pid)
        run.child_exited(pid)
    return on_exit


def _event_forwarder(run, phase: Phase, agent_name: str):
    """One tool_call event per real tool call, with its exact args and result."""
    tracker = agent_pi.ToolCallTracker()

    def forward(event: dict) -> None:
        record = tracker.observe(event)
        if record is None:
            return
        # The call's span rides the columns; duration_ms stays in the payload as
        # pi's own authoritative number.
        run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                     type="tool_call", name=record.pop("label"),
                                     started_at=record.pop("started_at", None),
                                     ended_at=record.pop("ended_at", None),
                                     payload={**record, "agent": agent_name}))
    return forward


def _extract_json(text: str) -> dict:
    candidate = text
    if "```" in text:
        for block in text.split("```")[1::2]:
            block = block.removeprefix("json").strip()
            if block.startswith("{"):
                candidate = block
                break
    start, end = candidate.find("{"), candidate.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found in the response")
    return json.loads(candidate[start:end + 1])


def _parse_with_retries(run, phase: Phase, call: AgentCall, result, send,
                        stats=None):
    """Parse the final response against the declared output type; on failure,
    continue the SAME session with a correction (bounded). The attempt count
    lands in stats even when the final attempt raises."""
    for attempt in range(1, JSON_FIX_ATTEMPTS + 2):
        try:
            payload = _extract_json(result.text)
            return call.output_type.model_validate(payload), attempt
        except Exception as error:
            if stats is not None:
                stats["json_attempts"] += 1   # failed parse attempts, not indices
            _persist_envelope(run, phase, phase.params.owner, call, None, attempt,
                              valid=False, raw=result.text)
            if attempt > JSON_FIX_ATTEMPTS:
                raise RuntimeError(
                    f"{phase.params.owner} never produced valid "
                    f"{call.output_type.__name__} JSON: {error}") from error
            run.console.retry(phase.params.owner, attempt, JSON_FIX_ATTEMPTS,
                              f"invalid {call.output_type.__name__} JSON: {error}")
            fields = ", ".join(call.output_type.model_fields.keys())
            result = send(
                f"Your response was not valid JSON for the required structure "
                f"({error}). Respond again with ONLY a JSON object with these "
                f"fields: {fields}. No prose, no code fences.")


def _persist_envelope(run, phase: Phase, agent_name: str, call: AgentCall,
                      envelope: Optional[EnvelopeBase], attempt: int,
                      valid: bool, raw: str = "") -> None:
    payload_json = envelope.model_dump_json(indent=2) if envelope else json.dumps({"raw": raw[-2000:]})
    run.tracer.envelope_row(phase, agent_name, call.output_type.__name__,
                            payload_json, valid, attempt)
    if envelope:
        record = {"agent_name": agent_name, "purpose": resolve(run.cfg, agent_name).purpose,
                  "output_type": call.output_type.__name__, "attempt": attempt,
                  **envelope.model_dump()}
        (run.session_dir / agent_name / "envelope.json").write_text(json.dumps(record, indent=2))
