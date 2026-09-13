# M4 — Pi Workflow and Extension Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development if a subagent tool is actually available; otherwise use superpowers:executing-plans. Execute sequentially with review between tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Do not promise independent subagent review when it did not occur.

**Goal:** Make every supported workflow unambiguously Pi-only with explicit, configured quality commands, observable repair loops, session-continuation diagnostics, validated extensions — and no Claude Code anywhere in the runtime.

**Architecture:** Quality blocks stop being editable placeholder functions and become CONFIGURED commands in `sssf.config.yaml` (`quality:` section); an unconfigured quality invocation raises loudly, so a workflow can never report acceptance on a fake command. Agent phases persist a `repair_summary` event (sends, JSON attempts, gate attempts, outcome) on every exit path, and `agent_start` gains `session_continued` diagnostics. Extension paths are validated at config time and before each launch. The Claude Code stub, its schema acceptance, and every runtime reference are deleted, enforced by a meta-test.

**Tech Stack:** Python 3.11, stdlib unittest + the M1–M3 harness (`execute_scenario`, `pi-double.py`, lanes), pydantic config models, uv, Git, Just.

**Spec:** `docs/superpowers/specs/2026-09-12-factory-evolution-design.md`, section "M4 — Improve Pi workflows and extensions" (required changes 1–5 and the exit condition).

## Global Constraints

- Pi is the only agent harness; keep Claude Code out of the agent harness and roster; `/sssf` stays an optional operator frontend (the SKILL itself may mention Claude Code — the RUNTIME may not).
- "Changes to CLI behavior must not silently change the meaning of existing Justfile recipes." All 21 product recipes stay supported.
- Use test doubles only for control-plane tests; never as Pi integration evidence.
- Ordinary lanes: zero skips, zero expected failures. No `git add -A` in the source checkout.
- The manifest/update flow (M3) covers template changes: the starter config's `quality:` section is a stamped-file change like any other.
- Bounded everything: quality commands keep per-block timeouts; subprocess output stays bounded in envelopes.
- Scratch targets only; never touch the historical example worktree.

## Decisions that make this plan executable

### A. Quality commands are configuration, not code

```yaml
# sssf.config.yaml (starter ships this section COMMENTED — nothing enabled)
quality:
  test:
    argv: ["uv", "run", "pytest", "-q"]
    timeout_seconds: 600
  lint:
    argv: ["uv", "run", "ruff", "check", "."]
```

- `SSSFConfig.quality: QualityConfig` — `QualityConfig(blocks: dict[str, QualityBlock])`, `QualityBlock(argv: list[str], timeout_seconds: int = 120)`. `load_config` passes `quality:` through (top-level key, no inheritance rules needed).
- `quality.py` rewritten: no `_placeholder`, no banner. `run_block(run, name)` looks up `run.cfg.quality.blocks[name]`; absent → `QualityNotConfigured` (a RuntimeError whose message names the block and shows a config example). `run_quality(run)` executes every CONFIGURED block (sorted by name) — "enabled" means configured; zero configured → `QualityNotConfigured`. `run_tests(run)` = `run_block("test")` wrapped as a `QualityResult` via the existing `as_envelope` machinery. `_run(spec, run)` keeps its existing subprocess/trace/timeout/OSError behavior (exit 124 timeout, exit 127 missing binary, tail bounded at 4000 chars).
- The four ADWs that call `quality.run_tests/run_quality` are unchanged — they cannot accept while quality is unconfigured, because the code phase raises and the phase fails (proof test in Task 2).

### B. Repair-loop reporting: one persisted summary per agent phase

`agents.execute` tracks a local stats dict (`sends`, `json_attempts`, `gate_attempts`) and emits a `log` event `repair_summary` on EVERY exit path (success, parse exhaustion, gate exhaustion, status fail, breach), payload:

```json
{"agent": "scout", "sends": 3, "json_attempts": 2, "gate_attempts": 1,
 "violations": ["x: missing"], "outcome": "gate_exhausted"}
```

`outcome` ∈ `success | parse_exhausted | gate_exhausted | status_fail | permission_breach | error`. The phase `error` column already carries the last failure verbatim; the summary makes the LOOP observable without reading raw events.

### C. Session continuation diagnostics

`_agent_session_id` becomes `_agent_session(run, agent) -> tuple[str, bool]` (id, continued). `agent_start` payload gains `"session_continued": bool`; when True, a `log` event `session_continued` (agent, session_id) is emitted so a run's context reuse is queryable without parsing JSON payloads. No schema migration.

### D. Extensions validated twice

- `agents.validate`: every `harness_engineering` path must exist (resolved relative to cwd, like prompt paths) — collected into the same fail-fast problems list.
- `agent_pi.run`: before Popen, each `-e` path resolved against `request.cwd`; missing → `RuntimeError("pi extension not found: <path>")`. Unavailable extension TOOLS at runtime surface through the drained stderr tail (M2), now guaranteed to reach the error message.

### E. Claude Code is gone, and a meta-test keeps it gone

- Delete `adw_modules/agent_cc.py`.
- `data_types`: `coding_agent: Literal["pi", "claude_code"]` → `Literal["pi"]` in BOTH `AgentConfig` and `ConfigDefaults` — the schema now rejects `claude_code` at construction with a pydantic error.
- `agents.validate` drops its claude_code branch (the schema makes it unreachable); `sssf.config.yaml` comments updated.
- Meta-test: no `claude` (case-insensitive) in any `templates/adws/adw_modules/*.py` or `templates/adws/adw_*.py`. The SKILL/cookbooks may mention Claude Code (operator frontend) — the runtime may not.
- M1's `test_claude_code_agent_is_rejected_at_runtime_validation` updates: rejection now happens at model construction (`ValidationError`) — same guarantee, earlier gate.

## File map

| Path | Responsibility |
|---|---|
| `templates/adws/adw_modules/data_types.py` | `QualityConfig`/`QualityBlock`; `Literal["pi"]` (Tasks 1, 5) |
| `templates/adws/adw_modules/quality.py` | Config-driven blocks, no placeholders (Task 1) |
| `templates/sssf.config.yaml` | Commented `quality:` example (Task 1) |
| `templates/adws/adw_modules/agents.py` | `RepairStats` + `repair_summary`; session-continuation diagnostics; extension validation; drop claude_code branch (Tasks 2–5) |
| `templates/adws/adw_modules/agent_pi.py` | Extension-path pre-launch check (Task 4) |
| `templates/adws/adw_modules/agent_cc.py` | DELETED (Task 5) |
| `tests/unit/test_quality.py` (new) | Quality config behavior (Task 1) |
| `tests/control_plane/test_agents.py` | `repair_summary` + session-continuation (Tasks 2–3) |
| `tests/unit/test_config.py` | Extension validation + claude_code rejection update (Tasks 4–5) |
| `tests/control_plane/test_pi_transport.py` | Missing-extension launch error (Task 4) |
| `tests/unit/test_no_claude_code.py` (new) | The meta-test (Task 5) |
| `docs/testing.md`, `docs/baselines/m4-acceptance.md` | Docs + acceptance (Task 6) |

---

## Task 1: Config-driven quality blocks

**Files:**
- Modify: `templates/adws/adw_modules/data_types.py`, `templates/adws/adw_modules/quality.py`, `templates/sssf.config.yaml`
- Create: `tests/unit/test_quality.py`

**Interfaces:**
- Produces: `SSSFConfig.quality: QualityConfig`; `QualityNotConfigured(RuntimeError)`; `quality.run_block(run, name) -> QualityCheckResult`; `quality.run_quality(run) -> QualityResult` (all configured blocks, sorted); `quality.run_tests(run) -> QualityResult`. ADW call sites unchanged.

- [ ] **Step 1: Failing tests** in `tests/unit/test_quality.py`

```python
"""Quality blocks are configured commands — nothing ships as a placeholder."""
from __future__ import annotations

import sys
import unittest

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import quality  # noqa: E402
from tests.support.runtime import RuntimeTestCase, make_run  # noqa: E402

HEADER = """
defaults:
  model: fixture/fixture-model
  data_dir: adws/adw_data
agents:
  - name: scout
    prompt_engineering:
      system: adws/adw_data/prompt_engineering/scout/system.md
      user: adws/adw_data/prompt_engineering/scout/user.md
"""


class QualityBlockTests(RuntimeTestCase):
    def write_config(self, quality_yaml: str) -> None:
        body = HEADER + (f"quality:\n{quality_yaml}" if quality_yaml else "")
        (self.target / "adws/adw_sssf_config/sssf.config.yaml").write_text(body)

    def make_run(self, adw_id: str):
        run = make_run(self.target, adw_id)
        self.addCleanup(run.tracer.conn.close)
        return run

    def test_unconfigured_block_raises_with_guidance(self):
        self.write_config("")
        run = self.make_run("qual-1")
        with self.assertRaises(quality.QualityNotConfigured) as caught:
            quality.run_tests(run)
        self.assertIn("quality:", str(caught.exception))
        self.assertIn("test", str(caught.exception))

    def test_configured_block_runs_traces_and_passes(self):
        self.write_config("  test:\n"
                          f"    argv: [{sys.executable!r}, '-c', 'pass']\n")
        run = self.make_run("qual-2")
        result = quality.run_tests(run)
        self.assertTrue(result.passed)
        self.assertEqual(result.checks[0].returncode, 0)
        events = run.tracer.conn.execute(
            "SELECT type, name FROM events WHERE type='tool_call' AND "
            "name LIKE 'quality:%'").fetchall()
        self.assertEqual([(t, n) for t, n in events], [("tool_call", "quality:test")])

    def test_failing_block_collects_the_verbatim_tail(self):
        self.write_config(f"  test:\n"
                          f"    argv: [{sys.executable!r}, '-c',"
                          f" 'print(\"suite failed\"); raise SystemExit(3)']\n")
        run = self.make_run("qual-3")
        result = quality.run_tests(run)
        self.assertFalse(result.passed)
        self.assertIn("suite failed", result.failures[0])
        self.assertIn("exited 3", result.failures[0])

    def test_timeout_is_exit_124_and_missing_binary_is_127(self):
        self.write_config("  test:\n"
                          "    argv: [sleep, '30']\n"
                          "    timeout_seconds: 1\n")
        run = self.make_run("qual-4")
        self.assertEqual(quality.run_tests(run).checks[0].returncode, 124)
        self.write_config("  test:\n    argv: [definitely-not-a-binary-xyz]\n")
        run = self.make_run("qual-5")
        self.assertEqual(quality.run_tests(run).checks[0].returncode, 127)

    def test_run_quality_runs_only_configured_blocks_and_fails_loudly_when_none(self):
        self.write_config(f"  lint:\n    argv: [{sys.executable!r}, '-c', 'pass']\n")
        run = self.make_run("qual-6")
        result = quality.run_quality(run)
        self.assertEqual([c.name for c in result.checks], ["lint"])
        self.write_config("")
        run = self.make_run("qual-7")
        with self.assertRaises(quality.QualityNotConfigured):
            quality.run_quality(run)
```

- [ ] **Step 2: Run — expect failures** (`QualityNotConfigured` absent; blocks are placeholders).

- [ ] **Step 3: Implement.** `data_types.py` adds:

```python
class QualityBlock(BaseModel):
    argv: list[str]
    timeout_seconds: int = 120


class QualityConfig(BaseModel):
    blocks: dict[str, QualityBlock] = Field(default_factory=dict)
```

and `SSSFConfig` gains `quality: QualityConfig = Field(default_factory=QualityConfig)`. `quality.py` rewritten:

```python
def _block(run, name: str) -> QualityBlock:
    blocks = run.cfg.quality.blocks
    if name not in blocks:
        raise QualityNotConfigured(
            f"quality block {name!r} is not configured — add to sssf.config.yaml:\n"
            f"  quality:\n    {name}:\n"
            f"      argv: [<the real command, as an argv list>]")
    return blocks[name]


class QualityNotConfigured(RuntimeError):
    """A workflow asked for a quality block that is not configured."""


def run_block(run, name: str) -> QualityCheckResult:
    block = _block(run, name)
    return _run(QualityCheckSpec(name=name, area="backend", operation="build",
                                 argv=block.argv,
                                 timeout_seconds=block.timeout_seconds), run)
```

`run_quality` iterates `sorted(run.cfg.quality.blocks)` (empty → `QualityNotConfigured` with the guidance message); `run_tests` = run_block("test") + existing failure shaping. Keep `_run`, `_check_dir`, `as_envelope`, TAIL_CHARS exactly as they are. Delete `_placeholder` and the banner. `templates/sssf.config.yaml` gains a commented `quality:` example block with the two argv rules (list, bare names).

- [ ] **Step 4: Run — green.** `just test-unit` (115 + 6).

- [ ] **Step 5: Commit** — `feat: configure quality commands in the roster; placeholders removed`.

---

## Task 2: Repair-loop reporting and the acceptance guard

**Files:**
- Modify: `templates/adws/adw_modules/agents.py`
- Test: `tests/control_plane/test_agents.py`

**Interfaces:**
- Produces: every agent phase emits a `log` event `repair_summary` with payload `{"agent", "sends", "json_attempts", "gate_attempts", "violations", "outcome"}` on every exit path.

- [ ] **Step 1: Failing tests** (append to `tests/control_plane/test_agents.py`)

```python
class RepairSummaryTests(RuntimeTestCase):
    def summaries(self, result) -> list[dict]:
        rows = [event for event in result.events() if event[1] == "repair_summary"]
        return [json.loads(row[2]) for row in rows]

    def test_success_summary_counts_one_send(self):
        result = execute_scenario(self, responses(VALID), ScenarioOptions())
        (summary,) = self.summaries(result)
        self.assertEqual((summary["sends"], summary["json_attempts"],
                          summary["gate_attempts"], summary["outcome"]),
                         (1, 0, 0, "success"))

    def test_parse_exhaustion_summary_records_three_sends(self):
        result = execute_scenario(self, responses("nope", "nope", "nope"),
                                  ScenarioOptions())
        (summary,) = self.summaries(result)
        self.assertEqual((summary["sends"], summary["json_attempts"],
                          summary["outcome"]), (3, 3, "parse_exhausted"))

    def test_gate_retry_summary_records_attempts(self):
        missing = {"text": MISSING_ARTIFACT, "exit_code": 0, "usage": SCENARIO_USAGE,
                   "events": [], "writes": []}
        created = {**missing, "writes": [{"path": "report.md", "text": "content"}]}
        result = execute_scenario(
            self, {"responses": [missing, created]},
            ScenarioOptions(gates=(artifacts_exist,), retries=1,
                            writes=["report.md"]))
        (summary,) = self.summaries(result)
        self.assertEqual((summary["gate_attempts"], summary["outcome"]),
                         (2, "success"))
```

- [ ] **Step 2: Run — expect failures** (no `repair_summary` events).

- [ ] **Step 3: Implement** in `agents.execute`: a local `stats = {"sends": 0, "json_attempts": 0, "gate_attempts": 0}` — `send()` increments `sends`; after each `_parse_with_retries`, add its returned `attempt` to `json_attempts`; the gate loop sets `gate_attempts`. New helper:

```python
def _emit_repair_summary(run, phase, agent, stats, violations, outcome) -> None:
    run.tracer.event(EventRecord(
        adw_id=run.adw_id, phase_id=phase.phase_id, type="log",
        name="repair_summary",
        payload={"agent": agent.name, **stats,
                 "violations": violations[:20], "outcome": outcome}))
```

Called from the success path (`"success"`, violations `[]`) and every failure branch (Task 2's restructure from M2 already has one shared failure path — extend it: parse → `parse_exhausted`, `GateFailure` → `gate_exhausted`, status-fail → `status_fail`, breach → `permission_breach`, other → `error`).

- [ ] **Step 4: Run — green.** `just test-control-plane` (+3).

- [ ] **Step 5: Commit** — `feat: persist a repair summary for every agent phase`.

---

## Task 3: Session continuation diagnostics

**Files:**
- Modify: `templates/adws/adw_modules/agents.py`
- Test: `tests/control_plane/test_agents.py`

**Interfaces:**
- Produces: `agent_start` payload carries `"session_continued": bool`; a `log` event `session_continued` (agent, session_id) is emitted when a call rejoins an existing session.

- [ ] **Step 1: Failing test**

```python
class SessionContinuationTests(RuntimeTestCase):
    def test_second_call_reports_continued_first_reports_fresh(self):
        result = execute_scenario(self, responses(VALID, VALID),
                                  ScenarioOptions(calls=2, adw_id="cont-run"))
        starts = [json.loads(row[2]) for row in result.events()
                  if row[0] == "agent_start"]
        self.assertEqual([start["session_continued"] for start in starts],
                         [False, True])
        continued = [row for row in result.events() if row[1] == "session_continued"]
        self.assertEqual(len(continued), 1)
        self.assertIn("sssf-cont-run-scout", continued[0][2])
```

- [ ] **Step 2: Run — expect failure** (payload lacks the key).

- [ ] **Step 3: Implement** — `_agent_session(run, agent) -> tuple[str, bool]`; `agent_start` payload + `session_continued` event.

- [ ] **Step 4: Run — green.**

- [ ] **Step 5: Commit** — `feat: session continuation diagnostics in the agent trace`.

---

## Task 4: Extension path validation

**Files:**
- Modify: `templates/adws/adw_modules/agents.py`, `templates/adws/adw_modules/agent_pi.py`
- Test: `tests/unit/test_config.py`, `tests/control_plane/test_pi_transport.py`

**Interfaces:**
- Produces: `agents.validate` collects missing `harness_engineering` paths into its problems list; `agent_pi.run` raises `RuntimeError("pi extension not found: <path>")` before spawning when a `-e` path doesn't exist under `request.cwd`.

- [ ] **Step 1: Failing tests**

In `tests/unit/test_config.py` (ValidateConfigTests):

```python
    def test_missing_extension_path_is_rejected_at_validation(self):
        broken = self.config(harness_engineering=["extensions/absent.ts"])
        with self.assertRaises(SystemExit) as caught:
            agents.validate(broken, ["scout"])
        self.assertIn("extensions/absent.ts", str(caught.exception))

    def test_present_extension_path_passes_validation(self):
        (self.target / "extensions").mkdir()
        (self.target / "extensions/real.ts").write_text("// extension\n")
        agents.validate(self.config(harness_engineering=["extensions/real.ts"]),
                        ["scout"])
```

In `tests/control_plane/test_pi_transport.py`:

```python
    def test_missing_extension_fails_before_spawn(self):
        with self.assertRaises(RuntimeError) as caught:
            self._run(MINIMAL_SCENARIO, extensions=["extensions/absent.ts"])
        self.assertIn("pi extension not found", str(caught.exception))
```

- [ ] **Step 2: Run — expect failures.**

- [ ] **Step 3: Implement.** `agents.validate`: for each agent, for each `path` in `agent.harness_engineering`: `Path(path).is_file()` else problem `f"agent {name!r}: extension not found: {path}"`. `agent_pi.run`: after building `cmd`, before Popen:

```python
    for extension in request.extensions:
        extension_path = Path(request.cwd) / extension
        if not extension_path.is_file():
            raise RuntimeError(f"pi extension not found: {extension} "
                               f"(looked for {extension_path})")
```

(Reorder the loop so validation happens before the `cmd += ["-e", ...]` appends or alongside them — single loop, check first.)

- [ ] **Step 4: Run — green.**

- [ ] **Step 5: Commit** — `feat: validate pi extension paths before launch`.

---

## Task 5: Remove Claude Code from the runtime

**Files:**
- Delete: `templates/adws/adw_modules/agent_cc.py`
- Modify: `templates/adws/adw_modules/data_types.py`, `templates/adws/adw_modules/agents.py`, `templates/sssf.config.yaml`
- Create: `tests/unit/test_no_claude_code.py`; Modify: `tests/unit/test_config.py`

**Interfaces:**
- Produces: `coding_agent: Literal["pi"]` in both models (schema rejects `claude_code` at construction); `agents.validate` has no coding_agent branch; meta-test asserts zero `claude` references in runtime modules.

- [ ] **Step 1: Update the M1 test + add the meta-test.** In `tests/unit/test_config.py`, replace `test_claude_code_agent_is_rejected_at_runtime_validation`:

```python
    def test_claude_code_is_rejected_by_the_schema_itself(self):
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            self.config(coding_agent="claude_code")
        # and it cannot slip through a loaded YAML either
        self.config_path.write_text("""
agents:
  - name: scout
    coding_agent: claude_code
    prompt_engineering:
      system: prompts/scout-system.md
      user: prompts/scout-user.md
""")
        with self.assertRaises(Exception):
            agents.load_config(str(self.config_path))
```

New `tests/unit/test_no_claude_code.py`:

```python
"""Exit condition: no runtime path refers to Claude Code."""
from __future__ import annotations

import unittest

from tests.support.factory import TEMPLATE


class NoClaudeCodeTests(unittest.TestCase):
    def test_runtime_modules_never_mention_claude(self):
        for path in sorted((TEMPLATE / "adws").rglob("*.py")):
            text = path.read_text(encoding="utf-8", errors="replace").lower()
            self.assertNotIn("claude", text, str(path))
```

- [ ] **Step 2: Run — expect failures** (agent_cc.py exists; data_types mentions claude_code; the updated config test fails at validate).

- [ ] **Step 3: Implement.** `git rm` agent_cc.py; `Literal["pi"]` in both models; delete validate's coding_agent branch; update the sssf.config.yaml comment ("Pi is the only coding agent; the schema rejects anything else").

- [ ] **Step 4: Run — green.** `just test-unit`, `just test-control-plane`, `just test-install` (the starter-config change flows through the manifest/update tests).

- [ ] **Step 5: Commit** — `feat: remove claude code from the runtime; schema is pi-only`.

---

## Task 6: Docs, full re-verification, real smoke, acceptance report

**Files:**
- Modify: `docs/testing.md`
- Create: `docs/baselines/m4-acceptance.md`

- [ ] **Step 1: Extend `docs/testing.md`** — the `quality:` config section (enabled = configured; unconfigured quality fails the workflow loudly, never fakes acceptance), repair summaries, session-continuation diagnostics, extension validation.

- [ ] **Step 2: Run every offline lane twice** — `just test`, `git diff --check`.

- [ ] **Step 3: Real smoke re-run** with the operator-approved model:

```bash
SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi
```

- [ ] **Step 4: Write `docs/baselines/m4-acceptance.md`** — commits, versions, lane counts, the meta-test result (grep proof), smoke evidence, historical-worktree preservation.

- [ ] **Step 5: Commit** — `docs: record m4 workflow improvements acceptance`.

---

## Execution checkpoints

| Checkpoint | Required evidence | Does not establish |
|---|---|---|
| Task 1 | Configured quality runs real commands; unconfigured fails loudly | That the operator's chosen commands are correct |
| Tasks 2–3 | `repair_summary` + `session_continued` in persisted traces | Real-model repair quality |
| Task 4 | Extension validation at config time and pre-launch | That every pi extension bug is impossible |
| Task 5 | Meta-test: zero claude references in runtime | The operator frontend (skill) is claude-free — it may mention it |
| Task 6 | Lanes twice green + real smoke PASS | M5 UI work |

M4 is complete when the spec's exit condition holds: all supported workflows use Pi, quality commands are explicit, repair loops are observable, and no runtime path refers to Claude Code.

## Plan self-review / spec coverage

| Spec M4 requirement | Plan task |
|---|---|
| 1. Every enabled quality block runs a configured real command; no acceptance on `_placeholder` | 1, 2 |
| 2. Acceptance criteria and repair-loop reporting | 2 |
| 3. Pi session continuation diagnostics | 3 |
| 4. Validate extension paths; report unavailable extension tools clearly | 4 |
| 5. Remove the Claude Code stub and non-pi harness config | 5 |
| 8. Regression tests per behavior | each task |
