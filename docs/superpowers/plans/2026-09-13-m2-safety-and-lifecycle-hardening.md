# M2 — Safety and Lifecycle Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development if a subagent tool is actually available; otherwise use superpowers:executing-plans. Execute sequentially with review between tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Do not promise independent subagent review when it did not occur.

**Goal:** Close every disclosed M1 known gap and harden the factory against losing user work, committing unrelated work, or leaving misleading traces.

**Architecture:** All changes are inside the stamped template modules (`adw_modules/`, `adws/`) plus their call sites. Permission detection moves from numstat fingerprints to content fingerprints, with ignored paths included and the SSSF runtime directory exempt. Enforcement moves inside the failure paths so it runs even when parsing or gates raise. Commit phases stage only the paths the run actually touched, and code-modifying workflows run on a dedicated `sssf/<adw_id>` branch. Interruption terminates recorded child processes; Pi's stderr drains to a file, never a pipe.

**Tech Stack:** Python 3.11, stdlib `unittest`/`sqlite3`/`hashlib`, the existing M1 test harness (`tests/support/*`, `scripts/checks.py` lanes, `pi-double.py`), uv, Git, Just.

**Spec:** `docs/superpowers/specs/2026-09-12-factory-evolution-design.md`, section "M2 — Harden safety and lifecycle behavior" (required changes 1–8 and the exit condition).

**Baseline:** `docs/known-gaps.md` records the seven M1 reproductions (M2-PERM-01…04, M2-TRACE-01, M2-PROC-01/02). Each is a failing desired-invariant assertion; M2 is complete per gap when that assertion passes as an ordinary test.

## Global Constraints

- Pi is the only agent harness supported by SSSF.
- "Use test doubles only for control-plane tests; never use them as Pi integration evidence."
- Never signal, revert, or delete anything the test/run does not own: no name-based kills, no `git checkout .`, no `rm -rf`, no `git clean`. Rollbacks restore only paths the run's own snapshots saw change.
- Pre-existing operator work (dirty tracked files, untracked files) is never destroyed. A path that was already modified before an agent ran is reported, never silently reverted.
- Ordinary test lanes contain zero skips and zero expected failures; only `tests/known_gaps/` carries `expectedFailure`, and each decorator is removed exactly when its defect is fixed.
- Child process cleanup uses exact recorded PIDs / owned process groups, bounded waits, and reaping. Never process-name matching.
- No new dependencies; no CI/CD edits; no second demo application; `.claude/skills/sssf` remains the resource location.
- New test modules: `test_*.py`, importable names; executable fixtures and scripts: kebab-case.
- macOS AppleDouble hazard: never `git add -A` in the source checkout; add explicit paths.

## Decisions that make this plan executable

### A. One fingerprint shape for every path state

`permissions.snapshot()` returns `dict[str, str]` mapping path → fingerprint for every path whose state can differ: tracked-dirty, untracked, and (new) ignored-outside-runtime. The fingerprint is the SHA-256 of the file content (files ≤ 1 MiB hashed whole; larger files hashed as `size + first 1 MiB + last 1 MiB`, a documented approximation that still detects edits at either end and size changes). Presence/absence differences are detected by dict comparison exactly as today. `changed_paths()` is unchanged.

Rollback sources, decided by the BEFORE state:

| Path state in before | After agent | Rollback |
|---|---|---|
| tracked-dirty (hash recorded) | changed | **left as-is, reported** (operator's uncommitted work — cannot restore from Git without destroying it) |
| untracked (bytes saved in `permission_state/`) | changed | restore saved bytes |
| untracked (bytes saved) | deleted | restore saved bytes |
| absent | appeared | delete the new file |
| tracked-clean | changed | `git checkout -- <path>` (HEAD content) |

`save_dir`: `snapshot(run, save_dir=None)` — when `save_dir` is given, every untracked/ignored file's bytes are mirrored under `save_dir` (preserving relative paths). `agents.execute` passes `run.session_dir / "permission_state"` for the BEFORE snapshot only. Mirrored files are bounded by the same 1 MiB approximation (larger files are NOT restorable byte-exact; they are reported as such).

### B. Enforcement runs on every exit path

`agents.execute` restructures so `permissions.enforce` runs on success, on parse exhaustion, and on gate failure. On the failure paths a breach **replaces** the original error (the original is preserved as `__cause__` and in an `error` trace event); a clean enforcement re-raises the original error. `agent_end` is emitted on every path that had at least one Pi send, with the usage spent so far.

### C. Commit scope comes from run snapshots

`Run` takes a tree baseline snapshot at construction (`run.tree_baseline`). `run.changed_paths()` = `changed_paths(tree_baseline, snapshot(now))` — with post-M2 snapshots this is exactly the set the run introduced, runtime paths already excluded by snapshot itself. `git_helper.commit_paths(paths, message)` stages only those paths (`git add -- <paths>`) and refuses when nothing changed. `commit_all` is deleted; the four ADWs with commit phases call `commit_paths(run.changed_paths(), message)`.

### D. Branch isolation for workflows that commit

`session.ensure(cfg, adw_id, *, isolate_branch=False)` — when set, immediately creates/switches to `sssf/<adw_id>` (skipping if already there) and records the event. The four committing ADWs pass `isolate_branch=True`. The operator's original branch ref is never moved; the working tree (including pre-existing dirty/untracked work) travels with the checkout; the run ends on the run branch, which the operator merges or discards. Read-only workflows keep running in place.

### E. Child lifecycle: registered, terminated, reaped

`Run` tracks live child PIDs (`register_child`/`child_exited`, fed by the same `on_spawn`/`on_exit` callbacks that already record trace rows). `_finalize_when_killed` now TERMs each registered child, waits up to 5 seconds, KILLs survivors, and only then closes the session — the trace rows close *after* the children are actually dealt with.

### F. Stderr drains to a file

`agent_pi.run` passes the child's stderr to an appended file (`<agent dir>/stderr.log`) instead of `PIPE`. The error path reads the last 800 characters from the file. A child can write unlimited stderr with stdout open and nothing blocks.

## File map

| Path | Responsibility |
|---|---|
| `templates/adws/adw_modules/permissions.py` | Content fingerprints, ignored-path detection, restore-capable rollback (A) |
| `templates/adws/adw_modules/agents.py` | Enforcement on all exit paths, `agent_end` on failures (B) |
| `templates/adws/adw_modules/git_helper.py` | `commit_paths`; delete `commit_all` (C) |
| `templates/adws/adw_modules/runner.py` | `tree_baseline`, `changed_paths()`, child registry (C, E) |
| `templates/adws/adw_modules/session.py` | `isolate_branch` on `ensure`, child termination in the signal handler (D, E) |
| `templates/adws/adw_modules/agent_pi.py` | stderr to file (F) |
| `templates/adws/adw_{plan_build,plan_build_test,plan_build_test_quality,simple_sdlc}.py` | `commit_paths` + `isolate_branch=True` (C, D) |
| `tests/unit/test_permissions.py` | Ordinary fingerprint/rollback tests (Tasks 1–2) |
| `tests/control_plane/test_agents.py` | Enforcement placement + `agent_end` failure rows (Tasks 2–3) |
| `tests/unit/test_git_scope.py` | Commit-scope tests (Task 4) |
| `tests/control_plane/test_lifecycle.py` | Branch isolation + child termination (Tasks 5–6) |
| `tests/control_plane/test_pi_transport.py` | Stderr-drain completion (Task 7) |
| `tests/known_gaps/*`, `docs/known-gaps.md` | Decorator removal per fixed gap (each task) |

---

## Task 1: Content fingerprints and restorable untracked state (M2-PERM-01, M2-PERM-02)

**Files:**
- Modify: `.claude/skills/sssf/templates/adws/adw_modules/permissions.py`
- Test: `tests/unit/test_permissions.py` (add `FingerprintTests`, `RollbackRestoreTests`)
- Also: port the two fixed assertions out of `tests/known_gaps/test_safety.py`; update `docs/known-gaps.md`

**Interfaces:**
- Produces: `snapshot(run, save_dir: Path | None = None) -> dict[str, str]` — same shape as M1; fingerprints are content hashes; ignored-outside-runtime paths included; runtime paths (`always_writable(cfg)`) always excluded.
- Produces: `enforce(run, phase, agent, before)` — unchanged signature; rollback now restores saved untracked bytes from `before`'s save dir.

- [ ] **Step 1: Write failing tests in `tests/unit/test_permissions.py`**

```python
class FingerprintTests(RuntimeTestCase):
    def test_same_shape_rewrite_of_dirty_file_is_reported(self):
        # M2-PERM-01
        run_stub = SimpleNamespace(repo_root=self.target, cfg=config())
        (self.target / "sample.txt").write_text("line one\nline two\n")
        before = permissions.snapshot(run_stub)
        (self.target / "sample.txt").write_text("line ONE\nline TWO\n")
        after = permissions.snapshot(run_stub)
        self.assertIn("sample.txt", permissions.changed_paths(before, after))

    def test_untracked_content_change_is_reported(self):
        # M2-PERM-02
        run_stub = SimpleNamespace(repo_root=self.target, cfg=config())
        (self.target / "notes.txt").write_text("version one\n")
        before = permissions.snapshot(run_stub)
        (self.target / "notes.txt").write_text("version two\n")
        after = permissions.snapshot(run_stub)
        self.assertIn("notes.txt", permissions.changed_paths(before, after))

    def test_runtime_directory_is_never_fingerprinted(self):
        run_stub = SimpleNamespace(repo_root=self.target, cfg=config())
        (self.target / "adws/adw_data/sessions/x/envelope.json").mkdir(
            parents=True, exist_ok=True)
        (self.target / "adws/adw_data/sessions/x/envelope.json").write_text("{}")
        self.assertNotIn("adws/adw_data/sessions/x/envelope.json",
                         permissions.snapshot(run_stub))


class RollbackRestoreTests(RuntimeTestCase):
    """Restore semantics are driven through _roll_back directly: enforce()
    only rolls back BREACH paths, and these tests exercise the restore
    mechanism itself (the breach path is covered by EnforcementTests)."""

    def test_modified_untracked_file_is_restored_from_saved_bytes(self):
        run_stub = SimpleNamespace(
            repo_root=self.target, cfg=config(),
            session_dir=self.target / "adws/adw_data/sessions/run-1")
        state = run_stub.session_dir / "permission_state"
        (self.target / "notes.txt").write_text("version one\n")
        before = permissions.snapshot(run_stub, save_dir=state)
        (self.target / "notes.txt").write_text("vandalized\n")
        outcome = permissions._roll_back(
            run_stub, "notes.txt", before, permissions.snapshot(run_stub))
        self.assertEqual(outcome, "restored")
        self.assertEqual((self.target / "notes.txt").read_text(), "version one\n")

    def test_deleted_untracked_file_is_restored_from_saved_bytes(self):
        run_stub = SimpleNamespace(
            repo_root=self.target, cfg=config(),
            session_dir=self.target / "adws/adw_data/sessions/run-1")
        state = run_stub.session_dir / "permission_state"
        (self.target / "notes.txt").write_text("keep me\n")
        before = permissions.snapshot(run_stub, save_dir=state)
        (self.target / "notes.txt").unlink()
        outcome = permissions._roll_back(
            run_stub, "notes.txt", before, permissions.snapshot(run_stub))
        self.assertEqual(outcome, "restored")
        self.assertEqual((self.target / "notes.txt").read_text(), "keep me\n")
```

Delete the now-fixed `NumstatIdenticalRewriteReproduction` and `UntrackedChangeReproduction` classes from `tests/known_gaps/test_safety.py` (their assertions now live here as ordinary tests).

- [ ] **Step 2: Run — expect failures.**

`uv run --locked --group test python -m unittest tests.unit.test_permissions -v`
Expected: the new tests FAIL (numstat fingerprints / name-only untracked) and the pre-existing 14 PASS.

- [ ] **Step 3: Implement in `permissions.py`**

```python
import hashlib

_GREEDY_READ = 1 << 20  # 1 MiB

def _fingerprint(path: Path) -> str:
    """Content fingerprint. Files over 1 MiB hash size + head + tail — an
    approximation that still sees edits at either end and size changes."""
    stat = path.stat()
    try:
        with path.open("rb") as handle:
            head = handle.read(_GREEDY_READ)
            if stat.st_size <= _GREEDY_READ:
                digest = hashlib.sha256(head).hexdigest()
            else:
                handle.seek(-_GREEDY_READ, 2)
                tail = handle.read(_GREEDY_READ)
                digest = hashlib.sha256(
                    f"{stat.st_size}:".encode() + head + tail).hexdigest()
        return f"content:{digest}"
    except OSError:
        return f"state:{stat.st_size},{int(stat.st_mtime_ns)}"

def _others(run, include_ignored: bool) -> list[str]:
    args = ["ls-files", "--others", "-z"]
    if not include_ignored:
        args.append("--exclude-standard")
    return [p for p in _git(args, run.repo_root).split("\0") if p]
```

Rewrite `snapshot`:

```python
def snapshot(run, save_dir=None) -> dict[str, str]:
    """Fingerprint every path whose state can differ: tracked-dirty,
    untracked, and ignored files OUTSIDE the always-writable runtime dir.
    With save_dir, untracked/ignored file bytes are mirrored there so a
    later rollback can restore them byte-for-byte."""
    root = Path(run.repo_root)
    runtime = [p for p in (always_writable(run.cfg) if hasattr(run, "cfg")
                           else [])]
    fingerprints: dict[str, str] = {}
    for line in _git(["diff", "HEAD", "--numstat"], run.repo_root).splitlines():
        fields = line.split("\t")
        if len(fields) >= 3:
            path = fields[-1].strip()
            fingerprints[path] = _fingerprint(root / path)
    for relative in _others(run, include_ignored=True):
        path = root / relative
        if any(_matches(relative, prefix) for prefix in runtime):
            continue                      # the runtime is always writable
        if path.is_file() and not path.is_symlink():
            fingerprints[relative] = _fingerprint(path)
            if save_dir is not None:
                destination = save_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
    return fingerprints
```

Parser note: `git ls-files --others -z` emits untracked AND ignored (without `--exclude-standard`); the deleted/ignored distinction needs no porcelain parsing — a listed path that doesn't fingerprint (gone) simply never enters the dict, and `_roll_back`'s restore logic covers it. Add `shutil` to imports. `_roll_back` gains the saved-bytes branch BEFORE the existing branches:

```python
    if save := Path(run.session_dir).joinpath("permission_state") if hasattr(
            run, "session_dir") else None:
        pass  # unused; the save dir is passed through the snapshot caller —
              # restore reads the copy stored under run.session_dir/permission_state
```

Concretely: `_roll_back` restores from `run.session_dir / "permission_state" / path` when that file exists (the test's `run_stub` gets `session_dir=self.target / "adws/adw_data/sessions/run-1"`); outcome word `"restored"`. Order: saved-copy restore first, then `untracked`-delete, then `git checkout --`. `test_permissions.py`'s `run_stub` is updated to `SimpleNamespace(repo_root=self.target, cfg=config(), session_dir=self.target / "adws/adw_data/sessions/run-1")` where restore is exercised.

- [ ] **Step 4: Run — all green.**

`just test-unit` — 14 pre-existing + 5 new PASS; `just test-control-plane` still green (43). The two deleted known-gap classes shrink the gap lane to 5.

- [ ] **Step 5: Update `docs/known-gaps.md`** — mark M2-PERM-01 and M2-PERM-02 as FIXED (moved to `tests/unit/test_permissions.py`), keeping the table honest (rows for fixed gaps say "fixed in M2, see test_permissions.py").

- [ ] **Step 6: Commit** — `git add <explicit paths>` (AppleDouble rule): `feat: fingerprint tracked and untracked state for permissions`.

---

## Task 2: Ignored paths are enforced, and enforcement runs on failure paths (M2-PERM-03, M2-PERM-04)

**Files:**
- Modify: `templates/adws/adw_modules/agents.py`
- Test: `tests/unit/test_permissions.py` (ignored-path enforcement), `tests/control_plane/test_agents.py` (enforcement-during-parse-exhaustion)
- Also: delete the two fixed reproductions from `tests/known_gaps/`; update `docs/known-gaps.md`

**Interfaces:**
- Consumes: `permissions.snapshot(run, save_dir=...)`, `permissions.enforce(...)` from Task 1.
- Produces: `agents.execute` behaves identically on success; on parse/gate failure it runs enforcement first and raises `PermissionBreach` (cause = original error) if the agent overstepped; on clean enforcement the original error propagates.

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_permissions.py`:

```python
class IgnoredPathTests(RuntimeTestCase):
    def test_ignored_file_modification_outside_runtime_is_caught(self):
        # M2-PERM-03
        run_stub = SimpleNamespace(repo_root=self.target, cfg=config(),
                                   session_dir=self.target / "adws/adw_data/sessions/run-1")
        with (self.target / ".gitignore").open("a") as gitignore:
            gitignore.write("\nignored.txt\n")
        (self.target / "ignored.txt").write_text("version one\n")
        before = permissions.snapshot(run_stub)
        (self.target / "ignored.txt").write_text("version two\n")
        with self.assertRaises(permissions.PermissionBreach):
            permissions.enforce(run_stub, None, agent(writes=[]), before)

    def test_ignored_file_with_explicit_permission_is_allowed(self):
        run_stub = SimpleNamespace(repo_root=self.target, cfg=config(),
                                   session_dir=self.target / "adws/adw_data/sessions/run-1")
        with (self.target / ".gitignore").open("a") as gitignore:
            gitignore.write("\nignored.txt\n")
        (self.target / "ignored.txt").write_text("version one\n")
        before = permissions.snapshot(run_stub)
        (self.target / "ignored.txt").write_text("version two\n")
        writer = agent(name="builder", writes=["ignored.txt"])
        self.assertEqual(permissions.enforce(run_stub, None, writer, before),
                         ["ignored.txt"])
```

In `tests/control_plane/test_agents.py`:

```python
class EnforcementOnFailureTests(RuntimeTestCase):
    """M2-PERM-04: enforcement runs even when parsing exhausts."""

    def test_unauthorized_write_before_parse_exhaustion_still_breaches(self):
        first = {"text": "nope", "exit_code": 0, "usage": SCENARIO_USAGE,
                 "events": [], "writes": [{"path": "sample.txt",
                                           "text": "vandalized"}]}
        scenario = {"responses": [first, *responses("nope", "nope")["responses"]]}
        result = execute_scenario(self, scenario, ScenarioOptions(writes=[]))
        self.assertIsInstance(result.error, permissions.PermissionBreach)
        self.assertEqual((self.target / "sample.txt").read_text(), "original\n")

    def test_parse_exhaustion_without_breach_raises_the_original_error(self):
        result = execute_scenario(self, responses("nope", "nope", "nope"),
                                  ScenarioOptions())
        self.assertIn("never produced valid GenericOutput JSON", str(result.error))
```

Delete `IgnoredFileEnforcementReproduction` and `EnforcementAfterParseExhaustionReproduction` from `tests/known_gaps/`.

- [ ] **Step 2: Run — expect failures** (M2-PERM-03: `PermissionBreach not raised`; M2-PERM-04: error is `RuntimeError`, not `PermissionBreach`).

- [ ] **Step 3: Implement.**

`agents.execute` — wrap the send/parse/gate section so enforcement happens on every exit:

```python
    tree_before = permissions.snapshot(run, save_dir=run.session_dir / "permission_state")
    try:
        result = send(user_text)
        envelope, attempt = _parse_with_retries(run, phase, call, result, send)
        for gate_attempt in range(1, max(1, phase.params.retries + 1) + 1):
            ...unchanged gate loop...
    except permissions.PermissionBreach:
        _finish_agent_trace(run, phase, agent, spent, context=None)
        raise
    except BaseException as error:
        try:
            permissions.enforce(run, phase, agent, tree_before)
        except permissions.PermissionBreach as breach:
            run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                         type="error", name="permission_breach",
                                         payload={"agent": agent.name,
                                                  "error": str(breach),
                                                  "during": repr(error)}))
            _finish_agent_trace(run, phase, agent, spent, context=None)
            raise breach from error        # the breach replaces the parse/gate error
        _finish_agent_trace(run, phase, agent, spent, context=None)
        raise
    else:
        touched = permissions.enforce(run, phase, agent, tree_before)
        ...unchanged success path, ending in _persist_envelope/handoff/agent_end...
```

Task 3 replaces the `_finish_agent_trace` placeholder with the real `agent_end` emission (or introduce it in this task emitting `agent_end` only if at least one send happened — define `_finish_agent_trace` here to emit `agent_end` with `spent` usage; Task 3's test then verifies its contents). Enforce runtime-dir exemption unchanged; ignored files flow through the snapshot from Task 1, so `permitted()` already applies `writes`/`protected_files` to them.

- [ ] **Step 4: Run — all green.** `just test-unit` and `just test-control-plane` (44).

- [ ] **Step 5: Update `docs/known-gaps.md`** — M2-PERM-03/04 fixed.

- [ ] **Step 6: Commit** — `feat: enforce permissions on ignored paths and failure exits`.

---

## Task 3: `agent_end` usage on failed agent calls (M2-TRACE-01)

**Files:**
- Modify: `templates/adws/adw_modules/agents.py`
- Test: `tests/control_plane/test_agents.py`

**Interfaces:**
- Consumes: `_finish_agent_trace` from Task 2 (emits the `agent_end` event with `tokens=spent.total_tokens` and payload usage).
- Produces: after any failure with ≥1 send, the events table contains one `agent_end` row for the phase with the accumulated usage.

- [ ] **Step 1: Write the failing test**

```python
class FailureTraceTests(RuntimeTestCase):
    def test_exhausted_corrections_record_agent_end_usage(self):
        # M2-TRACE-01 — flipped from tests/known_gaps/test_failures.py
        result = execute_scenario(self, responses("nope", "nope", "nope"),
                                  ScenarioOptions())
        self.assertIn("never produced valid", str(result.error))
        agent_end = [event for event in result.events() if event[0] == "agent_end"]
        self.assertEqual(len(agent_end), 1)
        self.assertEqual(agent_end[0][3], 36)   # 3 sends x 12 tokens
```

Delete `AgentEndUsageReproduction` from `tests/known_gaps/test_failures.py`.

- [ ] **Step 2: Run — expect failure** (`0 != 1`).

- [ ] **Step 3: Implement** — in `_finish_agent_trace`, mirror the success path's `agent_end` emission:

```python
def _finish_agent_trace(run, phase, agent, spent, context) -> None:
    if spent.total_tokens == 0:
        return                       # nothing was ever sent; no usage to record
    run.tracer.event(EventRecord(adw_id=run.adw_id, phase_id=phase.phase_id,
                                 type="agent_end", name=agent.name,
                                 tokens=spent.total_tokens,
                                 payload={"cost": spent.total_cost,
                                          "usage": spent.model_dump(),
                                          "context_tokens": getattr(context, "context_tokens", 0),
                                          "context_window": getattr(context, "context_window", 0)}))
```

The success path replaces its inline `agent_end` block with the same helper (context = `latest`). The success-path gate-failure (`GateFailure`) exit also flows through the `except BaseException` branch, so gate-failures after successful sends record usage too.

- [ ] **Step 4: Run — all green.** `just test-control-plane` (45).

- [ ] **Step 5: Update `docs/known-gaps.md`** — M2-TRACE-01 fixed.

- [ ] **Step 6: Commit** — `feat: record agent_end usage for failed agent calls`.

---

## Task 4: Commit phases stage only the run's own paths

**Files:**
- Modify: `templates/adws/adw_modules/git_helper.py`, `templates/adws/adw_modules/runner.py`, `templates/adws/adw_{plan_build,plan_build_test,plan_build_test_quality,simple_sdlc}.py`
- Test: `tests/unit/test_git_scope.py` (new)

**Interfaces:**
- Produces: `Run.tree_baseline: dict[str, str]`; `Run.changed_paths() -> list[str]` — paths changed since run start, runtime excluded; `git_helper.commit_paths(paths: list[str], message: str) -> str` — stages ONLY those paths (`git add --`), refuses empty list or empty staging; `commit_all` deleted.
- Call sites: the four committing ADWs change `git_helper.commit_all(message)` → `git_helper.commit_paths(run.changed_paths(), message)`.

- [ ] **Step 1: Write failing tests in `tests/unit/test_git_scope.py`**

```python
"""Commit scope: only the run's own paths are staged. Scratch repos only."""
from __future__ import annotations

import unittest

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import git_helper  # noqa: E402
from tests.support.runtime import RuntimeTestCase, make_run  # noqa: E402


class CommitScopeTests(RuntimeTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(self.run.tracer.conn.close)

    def test_pre_existing_dirty_file_is_never_committed(self):
        (self.target / "sample.txt").write_text("operator's uncommitted work\n")
        (self.target / "feature.txt").write_text("the run's work\n")
        self.run.tree_baseline = git_helper_snapshot(self.run)   # baseline AFTER the dirty file
        sha = git_helper.commit_paths(self.run.changed_paths(), "run work")
        self.assertTrue(sha)
        staged = git(self.target, ["show", "--name-only", "--format=", "HEAD"],
                     self.env)
        self.assertIn("feature.txt", staged)
        self.assertNotIn("sample.txt", staged)
        self.assertEqual((self.target / "sample.txt").read_text(),
                         "operator's uncommitted work\n")

    def test_pre_existing_untracked_file_is_never_committed(self):
        (self.target / "loose.txt").write_text("pre-existing untracked\n")
        self.run.tree_baseline = git_helper_snapshot(self.run)
        (self.target / "feature.txt").write_text("the run's work\n")
        git_helper.commit_paths(self.run.changed_paths(), "run work")
        staged = git(self.target, ["show", "--name-only", "--format=", "HEAD"],
                     self.env)
        self.assertNotIn("loose.txt", staged)

    def test_commit_with_no_run_changes_is_refused(self):
        self.run.tree_baseline = git_helper_snapshot(self.run)
        with self.assertRaises(RuntimeError) as caught:
            git_helper.commit_paths(self.run.changed_paths(), "nothing")
        self.assertIn("nothing to commit", str(caught.exception))
```

(with `git_helper_snapshot` a one-line helper calling `permissions.snapshot(run)` — imported from `adw_modules.permissions`.)

- [ ] **Step 2: Run — expect failure** (`commit_paths` does not exist).

- [ ] **Step 3: Implement.**

`git_helper.py`:

```python
def commit_paths(paths: list[str], message: str) -> str:
    """Stage ONLY the given paths and commit them.

    A run must never stage pre-existing operator work: the caller derives
    `paths` from run snapshots. An empty list is an error, not an `add -A`.
    """
    if not is_repo():
        raise RuntimeError("not a git repository — a commit phase needs one.")
    if not paths:
        raise RuntimeError(
            "nothing to commit — this run changed no paths it may commit")
    _git("add", "--", *paths)
    if not _git("status", "--porcelain"):
        raise RuntimeError("nothing to commit — the staged paths had no changes")
    _git("commit", "-m", message)
    return _git("rev-parse", "--short", "HEAD")
```

Delete `commit_all` (all four call sites change in this task; no other callers exist). `runner.py`:

```python
        self.tree_baseline = permissions.snapshot(self)

    def changed_paths(self) -> list[str]:
        """Paths THIS run introduced — the only thing a commit phase stages."""
        return permissions.changed_paths(self.tree_baseline,
                                         permissions.snapshot(self))
```

(`runner.py` already imports `agents`; add `permissions`.) The four ADWs: replace `git_helper.commit_all(message)` with `git_helper.commit_paths(run.changed_paths(), message)` (each file's local `run` variable name checked on site).

- [ ] **Step 4: Run — all green.** `just test-unit` (+3) and `just test-control-plane`.

- [ ] **Step 5: Commit** — `feat: commit phases stage only the run's own paths`.

---

## Task 5: Dedicated branch for workflows that commit

**Files:**
- Modify: `templates/adws/adw_modules/session.py`, the four committing ADWs
- Test: `tests/control_plane/test_lifecycle.py`

**Interfaces:**
- Produces: `session.ensure(cfg, adw_id=None, *, isolate_branch: bool = False) -> Run` — when set, creates and checks out `sssf/<adw_id>` (idempotent when already on it) before any phase, recording a `log` event `branch_isolated` with the base commit. Original branch ref never moves.

- [ ] **Step 1: Write the failing test**

```python
class BranchIsolationTests(RuntimeTestCase):
    def test_isolated_run_commits_on_its_own_branch(self):
        original_branch = self.branch
        run = session.ensure(cfg_from_target(), adw_id="isol8run",
                             isolate_branch=True)
        self.addCleanup(run.tracer.conn.close)
        self.assertEqual(git_helper.current_branch(), "sssf/isol8run")
        (self.target / "feature.txt").write_text("run work\n")
        git_helper.commit_paths(run.changed_paths(), "run work")
        # the operator's branch ref did not move
        base_sha = git(self.target, ["rev-parse", original_branch], self.env).strip()
        self.assertEqual(base_sha, git(self.target, ["rev-parse", "HEAD~1"],
                                       self.env).strip())
        # pre-existing dirty work survived the switch
        (self.target / "sample.txt").write_text("operator's uncommitted work\n")

    def test_read_only_runs_stay_in_place(self):
        run = session.ensure(cfg_from_target(), adw_id="inplace1")
        self.addCleanup(run.tracer.conn.close)
        self.assertNotIn("sssf/", git_helper.current_branch())
```

(`cfg_from_target()` = `agents.load_config()` — cwd is already the target; `session`/`git_helper` imported through the bootstrap. `session.ensure` installs signal handlers — these tests finish the run or rely on process exit; acceptable here because the test process exits at lane end. Note this in the test docstring.)

- [ ] **Step 2: Run — expect failure** (`ensure` has no `isolate_branch`).

- [ ] **Step 3: Implement** in `session.py`:

```python
def ensure(cfg: SSSFConfig, adw_id: str | None = None,
           *, isolate_branch: bool = False) -> Run:
    ...
    run = Run(...)
    tracer.session_start(adw_id, run.engineer, adw_name=Path(sys.argv[0]).stem)
    if isolate_branch:
        branch = f"sssf/{adw_id}"
        if git_helper.current_branch() != branch:
            git_helper.create_branch(branch)
            run.tracer.event(EventRecord(
                adw_id=adw_id, type="log", name="branch_isolated",
                payload={"branch": branch,
                         "base": git_helper.short_sha("HEAD")}))
    ...process_start / signal handlers unchanged...
```

The four committing ADWs: `session.ensure(cfg, adw_id, isolate_branch=True)`.

- [ ] **Step 4: Run — all green.** `just test-control-plane` (47).

- [ ] **Step 5: Commit** — `feat: run committing workflows on a dedicated branch`.

---

## Task 6: Interruption terminates recorded children (M2-PROC-01)

**Files:**
- Modify: `templates/adws/adw_modules/runner.py`, `templates/adws/adw_modules/session.py`, `templates/adws/adw_modules/agents.py`
- Test: `tests/control_plane/test_lifecycle.py` (flip the known gap)

**Interfaces:**
- Produces: `Run.register_child(pid: int) -> None`, `Run.child_exited(pid: int) -> None`; `agents.execute`'s `on_spawn`/`on_exit` call them alongside the tracer rows; `_finalize_when_killed` TERMs registered children (5s wait, KILL survivors) BEFORE `session_finish`.

- [ ] **Step 1: Flip the known gap into a passing assertion**

Move `InterruptedChildTerminationReproduction` from `tests/known_gaps/test_failures.py` into `tests/control_plane/test_lifecycle.py` as an ordinary test class, decorator removed:

```python
class InterruptedChildTerminationTests(RuntimeTestCase):
    """M2-PROC-01 — interrupting an ADW must actually terminate the
    coding-agent child, not merely mark the process row ended."""

    def setUp(self) -> None:
        super().setUp()
        never = self._scratch / "release" / "never-created"
        self.handle = supervised_adw(self, "proc-run",
                                     _parked_scenario(str(never)))
        self.assertTrue(wait_until(self._double_parked, 30),
                        "the double never parked inside the supervised ADW")
        with sqlite3.connect(self.handle.db_path) as conn:
            (self.double_pid,) = conn.execute(
                "SELECT pid FROM processes WHERE adw_id=? AND kind='agent' "
                "AND ended_at IS NULL", (self.handle.adw_id,)).fetchone()
        self.handle.signal(signal.SIGTERM)
        self.exit_code = self.handle.wait(timeout=5)

    def _double_parked(self) -> bool:
        try:
            with sqlite3.connect(self.handle.db_path) as conn:
                rows = conn.execute(
                    "SELECT pid FROM processes WHERE adw_id=? AND kind='agent' "
                    "AND ended_at IS NULL", (self.handle.adw_id,)).fetchall()
        except sqlite3.OperationalError:
            return False
        return bool(rows)

    def test_interrupted_adw_child_actually_terminates(self):
        self.assertEqual(self.exit_code, 143)
        deadline = time.monotonic() + 5.0
        while pid_alive(self.double_pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(pid_alive(self.double_pid),
                         "the trace says ended, but the coding-agent child is alive")
```

- [ ] **Step 2: Run — expect failure** (child alive; the defect is real until the fix lands).

- [ ] **Step 3: Implement.** `runner.py`: `self._children: set[int] = set()` plus `register_child`/`child_exited`. `agents.execute`'s send:

```python
        def on_spawn(pid: int) -> None:
            run.tracer.process_start(run.adw_id, "agent", agent.name, pid, ...)
            run.register_child(pid)

        def on_exit(pid: int) -> None:
            run.tracer.process_end(run.adw_id, pid)
            run.child_exited(pid)
```

`session.py`'s handler:

```python
    def handler(signum, _frame):
        for pid in list(run._children):
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + 5.0
        while run._children and time.monotonic() < deadline:
            time.sleep(0.05)          # exited children remove themselves
        for pid in list(run._children):
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        run.tracer.session_finish(run.adw_id, ok=False)
        raise SystemExit(128 + signum)
```

- [ ] **Step 4: Run — all green.** `just test-control-plane` (48), known-gaps shrinks to 2.

- [ ] **Step 5: Update `docs/known-gaps.md`** — M2-PROC-01 fixed.

- [ ] **Step 6: Commit** — `feat: terminate registered children on interruption`.

---

## Task 7: Stderr drains to a file (M2-PROC-02)

**Files:**
- Modify: `templates/adws/adw_modules/agent_pi.py`
- Test: `tests/control_plane/test_pi_transport.py` (flip the known gap)

**Interfaces:**
- Produces: `agent_pi.run` writes child stderr to `<raw_output_path>.stderr` (appended across retries) and reads at most the last 800 characters on failure. No `stderr=PIPE` remains.

- [ ] **Step 1: Flip the known gap into a passing test**

Move `StderrFloodReproduction` from `tests/known_gaps/test_failures.py` into `tests/control_plane/test_pi_transport.py`, decorator removed, assertion tightened:

```python
class StderrFloodTests(DoubleTestCase):
    """M2-PROC-02 — a child that fills the stderr pipe while stdout stays
    open must not deadlock the transport."""

    def test_transport_completes_despite_a_flooded_stderr(self):
        flooder = self._scratch / "flood-pi.py"
        flooder.write_text(
            "import sys, time\n"
            "sys.stderr.write('e' * 200_000)\n"   # > pipe capacity (64KiB)
            "sys.stderr.flush()\n"
            "time.sleep(30)\n")                    # stdout stays open
        self.shim = install_python_entrypoint(self._scratch / "bin" / "flood-pi",
                                              flooder)
        with mock.patch.object(agent_pi, "PI_PATH", str(self.shim)), \
             mock.patch.object(agent_pi, "_pi_catalog",
                               return_value=[("fixture", "fixture-model", 32000)]):
            holder: dict = {}
            pids: list[int] = []

            def transport() -> None:
                try:
                    holder["result"] = agent_pi.run(self._request(),
                                                    on_spawn=pids.append)
                except BaseException as error:   # a transport failure also counts
                    holder["error"] = error

            thread = threading.Thread(target=transport, daemon=True)
            thread.start()
            try:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive(),
                                 "transport still blocked on a flooded stderr")
            finally:
                for pid in pids:                    # owned child cleanup
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
```

(`threading`, `os`, `signal`, `mock`, and `install_python_entrypoint` are already imported in that module from Task 6's patterns.)

- [ ] **Step 2: Run — expect failure** (thread still alive at 5s).

- [ ] **Step 3: Implement** in `agent_pi.run`:

```python
    stderr_path = raw_path.parent / (raw_path.name + ".stderr")
    with stderr_path.open("ab") as err:      # appended: retries accumulate
        process = subprocess.Popen(cmd, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=err,
                                   text=True, bufsize=1, cwd=request.cwd,
                                   env=operator_env())
        ...unchanged stdout loop...
    result.returncode = process.wait()
    if on_exit:
        on_exit(process.pid)
    if result.returncode != 0 and not result.text:
        stderr_tail = stderr_path.read_text(errors="replace")[-800:]
        raise RuntimeError(f"pi exited {result.returncode}: {stderr_tail.strip()}")
```

- [ ] **Step 4: Run — all green.** `just test-control-plane` (49), `tests/known_gaps/` now empty (delete `__init__.py`-carried package? keep the package with a README pointer if `checks.py` requires the directory; `scripts/checks.py` maps the lane — an empty lane must fail with "count zero is an error", so REMOVE the known-gaps lane mapping and the `just test-known-gaps` recipe, updating `justfile`, `scripts/checks.py`, and `docs/testing.md` accordingly).

- [ ] **Step 5: Update `docs/known-gaps.md`** — replace with a short "all M1-disclosed gaps fixed in M2" note; update `docs/testing.md` (lane table loses the known-gaps row; `just test` description updated).

- [ ] **Step 6: Commit** — `feat: drain pi stderr to a file and retire the known-gap lane`.

---

## Task 8: Re-verify offline lanes and re-run the real smoke

**Files:**
- Modify: `docs/baselines/` — add `m2-acceptance.md`

- [ ] **Step 1: Run every offline lane twice** (`just test`, `just test-install` twice) — all green, zero skips, zero expected failures anywhere. `git diff --check` clean.

- [ ] **Step 2: Re-run the real smoke** — the operator approved `opencode/gpt-5.6-luna` for smoke runs in M1; re-run with the same model:

```bash
SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi
```

Expected: PASS with live observation, receipt, session continuity, unchanged app hashes. The M2 changes (branch isolation now applies to committing ADWs — smoke does not commit; stderr file; fingerprinted snapshots) must not regress the two-call smoke. A failure here is a separately reviewed bugfix, never a loosened gate.

- [ ] **Step 3: Write `docs/baselines/m2-acceptance.md`** — same discipline as M1's report: commit, versions, lane counts, smoke evidence (adw_id, live event id, tokens/cost), and the explicit statement that all seven M1-disclosed gaps are fixed with their tests now ordinary. Historical example worktree preservation check (HEAD before/after).

- [ ] **Step 4: Commit** — `docs: record m2 safety and lifecycle acceptance`.

---

## Execution checkpoints

| Checkpoint | Required evidence | Does not establish |
|---|---|---|
| Tasks 1–3 | Fingerprinted snapshots, ignored-path enforcement, enforcement on failure exits, `agent_end` on failures — ordinary tests, gap lane shrinking | Real-model behavior |
| Tasks 4–5 | Commit scope + branch isolation tests in scratch repos | That the operator's own repos are safe from bugs outside these paths |
| Tasks 6–7 | Child termination on interrupt; stderr flood completes | That all possible hangs are fixed — only the disclosed one |
| Task 8 | All lanes green twice + a fresh real-Pi smoke PASS | UI work (M5), generic packaging (M3) |

M2 is complete when the exit condition in the spec holds: tests demonstrate that pre-existing work is preserved, unauthorized changes are detected, commit scope is controlled, interrupted runs are finalized as failed, and failed agent calls leave complete trace evidence.

## Plan self-review / spec coverage

| Spec M2 requirement | Plan task |
|---|---|
| 1. Per-path content/state fingerprints | 1 |
| 2. Ignored files outside runtime detected + rolled back | 1, 2 |
| 3. Commit phases stage only run-owned files | 4 |
| 4. Dedicated branch/worktree for code-modifying workflows | 5 |
| 5. Children + process records closed on completion/failure/interruption | 6 (interruption; completion/failure already closed in M1, regression-covered by `test_normal_child_completion…`) |
| 6. `agent_end` usage on parse/gate failures | 2, 3 |
| 7. Pi subprocess never blocks on undrained stderr | 7 |
| 8. Regression tests per behavior | each task; gap decorators removed exactly at fix time |
