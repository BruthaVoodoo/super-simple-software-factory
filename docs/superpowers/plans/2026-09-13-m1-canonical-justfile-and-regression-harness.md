# M1 — Canonical Justfile and Regression Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development if a subagent tool is actually available; otherwise use superpowers:executing-plans. Execute sequentially with review between tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Do not promise independent subagent review when it did not occur.

**Goal:** Establish one canonical stamped Justfile, test fresh and repeated installation against the existing Inkwell example, exercise the Python control plane deterministically, and verify the current stamped runtime with real Pi.

**Architecture:** Keep the factory source in its current location for M1. Export application files from the pinned example Git commit into disposable targets, then install the current working tree's templates into those targets. The historical example worktree remains unchanged. Separate offline tests, documented known defects, and an explicit real-Pi acceptance command.

**Tech Stack:** Python 3.11 for the development test environment; standard-library `unittest`, `unittest.mock`, `tempfile`, `subprocess`, `hashlib`, and `sqlite3`; the existing Pydantic, PyYAML, python-dotenv, and Rich dependencies; uv; Git; Just; real Pi for the live acceptance lane.

**Spec:** `docs/superpowers/specs/2026-09-12-factory-evolution-design.md`, sections 3.4, 4, 5, and M1.

**Prior evidence:** `docs/baselines/2026-09-12-example-branch.md`. M0 ran on September 13 despite the report filename. It exercised two read-only workflows using a local model override. Treat that as a recorded observation, not as certification of every Pi feature.

## Global Constraints

The following binding requirements are copied from the spec:

- **Pi is the only agent harness supported by SSSF.**
- “The generated Justfile remains a supported interface. The CLI does not replace project-local Just commands.”
- “Use the pinned example worktree for real-Pi dogfooding and visualizer evaluation.”
- “Use clean temporary copies for automated installation tests.”
- “Use test doubles only for control-plane tests; never use them as Pi integration evidence.”
- “Keep terminal/Pi installation independent of Claude Code.”
- “Keep `/sssf` as an optional operator frontend, not a runtime dependency.”
- “M0 and M1 do not create a second demo application.”

Additional execution constraints:

- Work on `feat/m1-regression-harness` in an isolated development worktree. Do not implement on `main` or in `/Volumes/DEV/sssf-example`.
- Example source: `https://github.com/disler/super-simple-software-factory.git`, commit `b2dcb8e436db9b10f7580d7568b3e251609eb36b`.
- Derive the factory root from files/Git, not `/Volumes/DEV` or an operator's home directory.
- Do not fetch an updated example automatically, read credentials, change Pi configuration, choose a model for the operator, or publish raw traces.
- No CI/CD edits, package publication, new test framework, alternate harness, source relocation, or new demo application.
- No blanket `git clean`, `git checkout --`, `rm -rf`, `pkill`, or process-name-based termination. Standard-library temporary-directory cleanup is restricted to directories created and owned by the test runner. Tests exercising existing rollback code do so only inside those scratch repos. Do not delete the historical worktree.
- Development helpers and tests must not be stamped into users' projects. New operational helpers explicitly listed below are stamped because Just recipes need them.
- New Python test modules use `test_*.py`/importable module names, matching unittest discovery and the existing Python module convention. Executable scripts and Markdown files use kebab-case names.
- Every new behavior gets a failing test before its implementation. Characterization tests of existing behavior may pass immediately; do not damage production code just to manufacture a red test.

---

## Decisions that make this plan executable

### A. Three different directories, not three competing factories

| Directory | Purpose | Source of its factory files |
|---|---|---|
| Factory development checkout | Change templates and maintain tests | Current branch |
| Historical example worktree | Preserve M0's reference installation | Pinned upstream commit |
| Disposable acceptance target | Test today's install and runtime against Inkwell | Pinned application files + current templates |

**Do not clone the full stamped example and call a skipped install a fresh-install test.** A fresh target exports only `apps/inkwell/` and `LICENSE` from the pinned Git object. It excludes the old `adws/`, old root Justfile, old skill, secrets, sessions, and databases. Its application bytes remain the upstream bytes; this is not a rewritten application.

### B. Two Justfiles with separate responsibilities

- `.claude/skills/sssf/templates/justfile` is the canonical **product** Justfile. The installer copies this exact file to a target's `justfile`.
- A new root `justfile` contains **factory development** commands only: `test`, `test-unit`, `test-install`, `test-control-plane`, `test-known-gaps`, and `smoke-real-pi`.
- The root Justfile must not duplicate the product workflow recipes. It is not an installation template.

### C. Canonical recipe contract

The product recipe set at M1 completion is exactly:

```text
ask build-review build-test default demo document kill obs phases pi
plan plan-build procs prompt rosters scout sdlc sessions simple-sdlc
smoke-real-pi tail
```

This is the pinned example's set minus `cc` and `ipi`, plus the current template's `demo` and M1's `smoke-real-pi`. The historical branch is not automatically synchronized.

| Recipe | Required routing/behavior |
|---|---|
| `default` | List available recipes; no model call |
| `pi` | Launch Pi with the existing SSSF operator instructions; no Claude executable |
| `prompt` | `adws/adw_prompt.py`, preserving all user arguments |
| `ask AGENT` | `adws/adw_prompt.py --agent AGENT`, forwarding remaining arguments once |
| `scout` | `adws/adw_scout.py` |
| `plan` | `adws/adw_plan.py` |
| `plan-build` | `adws/adw_plan_build.py` |
| `build-test` | `adws/adw_build_test.py` |
| `build-review` | `adws/adw_build_review.py` |
| `document` | `adws/adw_document.py` |
| `sdlc` | `adws/adw_plan_build_test.py` |
| `simple-sdlc` | `adws/adw_simple_sdlc.py` |
| `demo` | Current template's two read-only runs, in order; stop after the first failure |
| `sessions`, `phases`, `tail`, `procs` | Read the selected configuration's trace DB; parameterized query inputs |
| `rosters` | List YAML rosters and effective agent models using the existing YAML loader |
| `kill` | Confirm and stop only verified, trace-recorded processes; refuse ambiguous identity |
| `obs` | Keep current visualizer launch behavior; no UI redesign in M1 |
| `smoke-real-pi` | New bounded real-Pi smoke ADW, never a test double |

Retain `set dotenv-load` and `set positional-arguments`. Export the resolved `config` Just variable as `SSSF_CONFIG` and reference it as `"$SSSF_CONFIG"` inside recipe shells, rather than interpolating user-provided text into shell source. Keep the template's non-interactive shell behavior; do not import the example's interactive zsh profile requirement. `ipi` is excluded by the agreed recipe contract; no assumption about its internal implementation is required.

A recipe-list assertion is necessary but insufficient. Tests must also check stamped bytes, argument forwarding, selected config, subprocess status, and no-model inspection commands.

### D. Fresh install, re-install, and upgrade are different tests

1. **Fresh install:** no target-owned factory files exist. The stamped Justfile must equal the canonical template byte-for-byte.
2. **Re-install:** existing user Justfile/config/prompts must remain byte-for-byte unchanged. Report skips. Re-install is not an automatic drift repair.
3. **Old installation:** an old Justfile remains unchanged under the current skip policy. Tests demonstrate that compatibility explicitly.
4. **Upgrade:** safe merging and manifest-based updates belong to M3, not M1.

### E. Test coverage must not conceal M2 defects

M1 adds passing characterization tests and separate reproductions for known defects. Do not encode unsafe behavior as a desired passing assertion.

`tests/known_gaps/` contains narrowly scoped `unittest.expectedFailure` cases with stable IDs and owning milestones. Unexpected successes fail that command and require removing the expectation. Ordinary unit/install/control-plane suites contain no skips or expected failures. Every M1 summary shows known-gap counts separately; a green M1 harness is not a safety certification.

An unexpected new failure stops that task. Investigate it; do not turn it into an expected failure merely to finish M1. A genuine runtime blocker requires a separately reviewed bugfix before real-Pi acceptance can pass.

### F. Evidence from M0 does not replace M1 acceptance

- Counting stored tool events after completion does **not** prove they were visible while a run was active. M1 measures that explicitly.
- HTTP 200 from a listening server does **not** prove the intended DB was served or that the UI rendered. M1 makes no visualizer acceptance claim; M5 owns UI work.
- Passing `--session-id` twice does **not** by itself prove context continuation. The live smoke uses an unrepeated recall challenge and checks Pi's session history.
- The spec's literal M0 `just demo` requirement was superseded operationally by the recorded equivalent two Just commands because the pinned recipe did not exist. Do not change the historical Justfile to make that record appear different.

## File map

Current production source remains under `.claude/skills/sssf/` for M1.

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | Locked development environment using existing runtime dependencies |
| `justfile` | Factory development commands, not stamped |
| `scripts/checks.py` | Offline lane selection, isolation, test counts and exit status |
| `scripts/smoke-real-pi.py` | Build a fresh example-based target and supervise live acceptance |
| `tests/__init__.py` and package `__init__.py` files | unittest discovery |
| `tests/support/factory.py` | Scratch target, installer invocation, current source locations |
| `tests/support/environment.py` | Credential-free offline child environments and executable tripwires |
| `tests/support/imports.py` | Verified import of current template modules without loading operator dotenv |
| `tests/support/example.py` | Pinned Git export; no worktree copying or automatic fetch |
| `tests/support/processes.py` | Bounded commands and owned-process-group cleanup |
| `tests/fixtures/example.json` | Upstream URL, pinned SHA, export paths, observed recipe list |
| `tests/fixtures/argv-recorder.py` | Record recipe arguments without running workflow commands |
| `tests/fixtures/pi-double.py` | Explicit synthetic Pi protocol for offline process tests |
| `tests/unit/test_*.py` | Pure/config/filesystem/Git/SQLite unit checks |
| `tests/install/test_*.py` | Actual installer and Just behavior against scratch targets |
| `tests/control_plane/test_*.py` | Runtime lifecycle and deterministic child-process scenarios |
| `tests/known_gaps/test_*.py` | Disclosed M2 defect reproductions |
| `.claude/skills/sssf/templates/justfile` | Canonical product recipe set |
| `.claude/skills/sssf/templates/adws/manage.py` | No-agent inspection/stop command entry point, not an ADW |
| `.claude/skills/sssf/templates/adws/adw_modules/operations.py` | Query and roster inspection logic |
| `.claude/skills/sssf/templates/adws/adw_modules/process_control.py` | Conservative confirmed stop of recorded PIDs |
| `.claude/skills/sssf/templates/adws/adw_smoke.py` | Thin real-Pi probe/recall workflow |
| `.claude/skills/sssf/templates/adws/adw_modules/smoke.py` | Smoke config, claim gates, evidence checks |
| `.claude/skills/sssf/templates/prompt_engineering/smoke/system.md` and `user.md` | Smoke-only GenericOutput contract; not a starter-roster role |
| `docs/testing.md` | Commands, prerequisites, test lanes and limitations |
| `docs/known-gaps.md` | Reproduction IDs, failing invariant, next milestone |
| `docs/baselines/m1-acceptance.md` | Sanitized measured acceptance result, written at execution time |

Do not create files for a proposed `sssf` application package, UI rewrite, GitHub Actions, or a new example app.

---

## Task 1: Establish the canonical contract and isolated installer test foundation

**Files:** Create `pyproject.toml`, `uv.lock`, root `justfile`, `scripts/checks.py`, `tests/__init__.py`, `tests/support/{__init__,factory,environment,imports,processes}.py`, `tests/install/{__init__,test_install}.py`.

**Interfaces:**

- `tests.support.factory.ROOT: Path` — factory source root derived from `__file__`.
- `SKILL: Path = ROOT / '.claude/skills/sssf'`.
- `TEMPLATE: Path = SKILL / 'templates'`.
- `FactoryTestCase(unittest.TestCase)` — `setUp` creates a `TemporaryDirectory` outside the source checkout; exposes `self.target: Path` and `self.env: dict[str, str]`; cleanup restores cwd/env and closes only its own resources.
- `stamp(target: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]` — execute `[sys.executable, str(SKILL / 'scripts/install.py')]`, `cwd=target`, captured output, 30-second deadline; return the real exit code.
- `git(target: Path, args: list[str], env: dict[str, str]) -> str` — checked Git command, 30-second deadline.
- `child_env(home: Path) -> dict[str, str]` — allowlist PATH, platform temp/system variables and UTF-8 locale; set scratch HOME/XDG/PI_CODING_AGENT_DIR, `ENGINEER_NAME=sssf-test`, `PYTHONDONTWRITEBYTECODE=1`, and disable dotenv loading before runtime imports. Do not copy keys, proxies, Git-directory overrides, or the operator's auth files.
- `run_owned(argv: list[str], target: Path, options: ProcessOptions) -> ProcessResult` — dataclasses hold environment, deadline and capture paths; launch a new process group, terminate/reap only that group on timeout. No name-based kill.
- `ProcessOptions`: `env: dict[str, str]`, `timeout_seconds: float`, `output_dir: Path`.
- `ProcessResult`: `returncode: int`, `timed_out: bool`, `pid: int`, `stdout_path: Path`, `stderr_path: Path`. A timeout returns code 124 after owned-group cleanup.
- `install_python_entrypoint(destination: Path, script: Path) -> Path` in `tests/support/processes.py` writes an executable scratch shell shim using `exec`, shell-quoted absolute `sys.executable`, shell-quoted script path and `"$@"`. Recorder/double subprocesses use the locked test interpreter, not whichever `python3` remains after the runtime strips uv's venv PATH.
- `tests.support.imports` adds `TEMPLATE / 'adws'` to import search, imports `adw_modules.utils` while `dotenv.load_dotenv` is patched to return `False`, then checks the resolved package path. This suppresses the actual import-time dotenv call before other modules reuse utils. Import this before new runtime helpers in Task 2; it does not change global environment outside the test process.

- [ ] **Step 1: Add the development environment, with no new test framework.**

Use this manifest. Existing runtime dependencies are locked for tests; this does not change the per-script production dependency declarations.

```toml
[project]
name = "sssf-development"
version = "0.0.0"
requires-python = ">=3.11"
dependencies = []

[dependency-groups]
test = ["pydantic>=2,<3", "pyyaml>=6,<7", "python-dotenv>=1,<2", "rich>=13,<15"]

[tool.uv]
package = false
```

Run `uv lock`, then `uv sync --locked --group test --python 3.11`. These commands can download the existing dependencies; the test execution itself must not invoke providers. If environment setup fails, stop rather than use the machine's Python 3.9 by accident.

- [ ] **Step 2: Write installer characterization tests before helper implementation.**

```python
from tests.support.factory import FactoryTestCase, TEMPLATE, stamp

class InstallTests(FactoryTestCase):
    def test_fresh_justfile_is_template_bytes(self):
        result = stamp(self.target, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            (self.target / "justfile").read_bytes(),
            (TEMPLATE / "justfile").read_bytes(),
        )

    def test_existing_justfile_is_preserved(self):
        path = self.target / "justfile"
        before = b"owned-by-project:\n    @echo keep-me\n"
        path.write_bytes(before)
        result = stamp(self.target, self.env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertIn("skipped", result.stdout)
```

Run `uv run --locked --group test python -m unittest tests.install.test_install -v`. Initial failure should be the absent test helper, not a runtime install error.

- [ ] **Step 3: Implement scratch helpers and rerun.**

`FactoryTestCase.setUp` creates an empty target and scratch home, without changing the source checkout. `stamp` uses the actual installer, not a reimplementation. Set subprocess import paths explicitly; do not let an installed older `adw_modules` shadow the template modules. The import bootstrap in `tests/support/imports.py` is only for tests, never imported by the real-Pi launcher.

Add helper tests in `tests/install/test_install.py` for scratch-only cleanup and a `run_owned` timeout of an owned Python child. Verify the returned PID has exited before teardown completes.

Add assertions covering config and prompt preservation, `.gitignore` entries exactly once after two installs, `.env` never created, no session DB created by installation, and exact bytes for every template mapping from `install.py`.

- [ ] **Step 4: Add the development command runner.**

The root Justfile commands use `uv run --locked --group test python scripts/checks.py LANE`. Map `unit`, `install`, `control-plane`, and `known-gaps` to their directories. `test` runs the first three and reports the fourth separately. Before each suite, print the lane and count discovered tests; count zero is an error, not a pass. Use `unittest.TextTestRunner(verbosity=2)` and propagate `result.wasSuccessful()` to process exit.

For ordinary lanes, reject any skips or expected failures. Only `known-gaps` permits declared expected failures. In-process network connections and Pi-launch attempts are tripwired unless a test explicitly patches the protocol boundary. Child subprocesses receive `child_env`, not the operator's environment. This is accidental-call prevention, not an OS sandbox claim.

Until later tasks create a lane, execute only the populated `test-install` lane. Do not claim the entire `just test` command passes with empty suites.

- [ ] **Step 5: Verify and commit.**

Run `just test-install` twice. Expect identical test outcomes, preserved user Justfile, no provider subprocess, and no tracked source changes caused by tests. Commit only the files listed for this task with `test: add isolated installer regression foundation`.

---

## Task 2: Reconcile the product Justfile and test recipe behavior

**Files:** Modify `.claude/skills/sssf/templates/justfile`; create `tests/fixtures/argv-recorder.py`, `tests/install/test_justfile.py`, `.claude/skills/sssf/templates/adws/manage.py`, `.claude/skills/sssf/templates/adws/adw_modules/{operations,process_control}.py`, `tests/unit/{__init__,test_operations,test_process_control}.py`.

**Interfaces:**

- `recipe_names(target: Path, env: dict[str, str]) -> set[str]` in `tests/install/test_justfile.py` — real `just --summary`, split whitespace; this helper always receives an already stamped scratch target.
- `operations.query_view(config: str, view: str, adw_id: str | None) -> list[dict[str, object]]` — readonly SQLite connection; view in `sessions/phases/tail/procs`; bound parameters for IDs.
- `operations.rosters(directory: Path) -> list[dict[str, object]]` — YAML config loading with inherited models; no `agents.validate`, Pi catalog call, or auth requirement.
- `process_control.stop_run(config: str, adw_id: str) -> int` — fail closed on unknown process identity; explicit interactive confirmation before signals.
- `manage.py --config PATH sessions|phases|tail|procs|rosters|kill [--adw-id ID]` dispatches these operations. This is an operator utility, not an `adw_*.py` workflow; querying sessions must not create another session. Require `--adw-id` for phases/tail/procs/kill; rosters lists the selected config's parent directory. No `AgentCall`, no new session, no model dependency. Use the existing runtime dependency header.

- [ ] **Step 1: Write the independent recipe-set assertion.**

Use an explicit set in the test; do not derive expected names from the template being tested. The final set is the contract in section C. Initially exclude only `smoke-real-pi` from the green target because Task 8 introduces that behavior; add it with its implementation, not as a no-op recipe.

```python
BASE_RECIPES = set("""
ask build-review build-test default demo document kill obs phases pi
plan plan-build procs prompt rosters scout sdlc sessions simple-sdlc tail
""".split())

class JustfileTests(FactoryTestCase):
    def test_canonical_base_recipe_set(self):
        stamp(self.target, self.env).check_returncode()
        self.assertEqual(recipe_names(self.target, self.env), BASE_RECIPES)
```

Run the specific test before editing the template. Expect missing `ask`, `build-review`, `build-test`, `document`, `kill`, `pi`, and `rosters`. Add tests explicitly rejecting `cc` and `ipi`.

- [ ] **Step 2: Add recipe wrappers without importing example shell quirks.**

Use environment and positional argument expansion rather than inserting values into executable shell source. Retain `config := env_var_or_default("SSSF_CONFIG", "adws/adw_sssf_config/sssf.config.yaml")` and add `export SSSF_CONFIG := config`. For the named-agent wrapper shift off only the first positional parameter:

```just
ask AGENT *ARGS:
    agent="$1"; shift; uv run adws/adw_prompt.py --config "$SSSF_CONFIG" --agent "$agent" "$@"

build-test *ARGS:
    uv run adws/adw_build_test.py --config "$SSSF_CONFIG" "$@"

build-review *ARGS:
    uv run adws/adw_build_review.py --config "$SSSF_CONFIG" "$@"

document *ARGS:
    uv run adws/adw_document.py --config "$SSSF_CONFIG" "$@"

pi:
    pi "Read and Execute .claude/skills/sssf/SKILL.md"
```

Apply quoted config forwarding to existing workflow wrappers too. The `.claude` source path remains for M1; it is a file Pi can read, not a dependency on the Claude executable. M3 handles relocation.

Route inspection and stop recipes through `manage.py`; do not copy the example's interpolated SQL, formatting-dependent AWK, broad `*pi*|*python*` PID match, or interactive-zsh requirement. For example:

```just
sessions:
    uv run adws/manage.py --config "$SSSF_CONFIG" sessions

phases ADW_ID:
    uv run adws/manage.py --config "$SSSF_CONFIG" phases --adw-id="$1"

kill ADW_ID:
    uv run adws/manage.py --config "$SSSF_CONFIG" kill --adw-id="$1"
```

Use the same argument form for tail/procs and the no-ID form for rosters. `manage.py` must not import a model catalog during module initialization.

- [ ] **Step 3: Verify argument arrays and failure propagation.**

`argv-recorder.py` appends JSON arrays to a path supplied in `SSSF_ARGV_RECORD`, then returns `SSSF_STUB_EXIT` (default zero). Install an executable `uv` wrapper pointing to this script in scratch PATH. It must not execute the recorded commands.

Required cases:

| Invocation | Assertion |
|---|---|
| `just ask scout` with prompt `spaces; $(touch UNEXPECTED)` and `--adw-id a1b2c3d4` | One prompt argument, no shell execution, agent appears once, remaining flags retained |
| Each workflow recipe in section C | Exact expected `adws/adw_*.py` path and `--config` value |
| `SSSF_CONFIG` points to `config with spaces.yaml` or a filename containing a quote and literal `$()` | One literal config argument, no command execution |
| `just demo` with first stub returning 7 | Just returns nonzero and only one invocation was recorded |
| `just demo` with both successful | Exactly prompt/scout invocations in order |
| `just pi` with a separate `pi` recorder | Invokes Pi, not Claude, with the instruction path |

Test command routing without actually running build/commit workflows or a real `kill` against operator processes.

- [ ] **Step 4: Implement and test no-agent operations.**

Construct the readonly URI with `Path(db).resolve().as_uri() + '?mode=ro'`, use `sqlite3.connect(uri, uri=True)`, and fail nonzero if absent rather than creating an empty DB. `sessions` returns the newest ten; `phases` orders by sequence for one ID; `tail` returns newest 25 events for one ID; `procs` returns rows with `ended_at IS NULL` for one ID. Use deterministic JSON output so tests do not depend on terminal styling. Document this inspection-output change in Task 9.

Test two isolated SQLite datasets with different IDs; selected config must select the correct DB. Test an ID containing a quote as data, not SQL. Verify all queries leave rows unchanged and `conn.total_changes == 0`. Do not assert byte-identical live WAL files: another writer or checkpoint can change physical bytes without this reader issuing a write. Test YAML with inherited and overridden models, including non-default formatting. No provider catalog call is permitted for these operations.

- [ ] **Step 5: Port `kill` conservatively, with safety tests before signals.**

The canonical name is required, but unsafe example behavior is not. Read only live process rows for the requested run, order agent rows before the ADW row, reject PID <= 1/current process, inspect each PID's current command, and refuse signals unless its identity is tied to this repository and this run. For a Pi child require its exact absolute `--session-dir` beneath the configured run directory. For an ADW require an absolute script path under this target's `adws/` and the explicit `--adw-id` value. If legacy records/relative argv cannot establish this, return nonzero with `process identity not verified`; do not guess from executable names. Show the verified PID list and require the user to type the run ID; non-interactive invocation refuses to signal. Send SIGTERM only, then wait up to five seconds; a still-live PID remains reported live. Do not manufacture closed trace rows for live processes.

Before every signal, inspect identity again. Test with mocked process inspection and `os.kill`: wrong repo, wrong session, missing PID, changed identity, failed confirmation, non-TTY, successful confirmation, and child-before-parent ordering. No unit test sends a signal to an operator process. Full runtime-owned process lifecycle improvements remain M2.

- [ ] **Step 6: Verify and commit.**

Run `just test-install` and `just test-unit`. Check a stamped `just --list` manually in the test target. Commit this slice as `feat: establish canonical pi-only just recipes`. Do not edit the pinned example Justfile.

---

## Task 3: Test installation using the pinned Inkwell application

**Files:** Create `tests/fixtures/example.json`, `tests/support/example.py`, `tests/install/test_example_install.py`.

**Interfaces:**

- `export_example(source: Path, destination: Path) -> dict[str, str]` — export allowed application blobs from the pinned Git object, return relative-path SHA-256 map.
- `prepare_example_target(destination: Path, env: dict[str, str]) -> dict[str, str]` — export, copy current skill resources for `pi`/`obs` compatibility, install current factory, then initialize and commit the synthetic scratch baseline containing the app and installed files. Return pre-install application hashes. Git setup uses the local synthetic test identity, disabled hooks/signing, and never changes the source checkout.
- Reject an existing nonempty destination. Never overwrite the historical worktree or source repo.

- [ ] **Step 1: Record the verified pin and paths.**

```json
{
  "upstream": "https://github.com/disler/super-simple-software-factory.git",
  "commit": "b2dcb8e436db9b10f7580d7568b3e251609eb36b",
  "application_paths": ["apps/inkwell/", "LICENSE"],
  "example_recipes": ["ask", "build-review", "build-test", "cc", "default", "document", "ipi", "kill", "obs", "phases", "pi", "plan", "plan-build", "procs", "prompt", "rosters", "scout", "sdlc", "sessions", "simple-sdlc", "tail"]
}
```

Verify the local object with `git cat-file -e b2dcb8e436db9b10f7580d7568b3e251609eb36b^{commit}`. If unavailable, the test fails with the one-time preparation command `git fetch https://github.com/disler/super-simple-software-factory.git example`; it must not fetch silently or substitute a moving branch.

- [ ] **Step 2: Write the fresh-example test.**

```python
class ExampleInstallTests(FactoryTestCase):
    def test_current_factory_stamps_untouched_inkwell(self):
        before = export_example(ROOT, self.target)
        self.assertIn("apps/inkwell/server.ts", before)
        self.assertFalse((self.target / "adws").exists())
        self.assertFalse((self.target / "justfile").exists())
        stamp(self.target, self.env).check_returncode()
        for path, expected in before.items():
            self.assertEqual(sha256((self.target / path).read_bytes()).hexdigest(), expected)
        self.assertEqual((self.target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())
```

Import `sha256` from `hashlib` and the named helpers in this task. Run the specific test before implementing the exporter; expect a missing helper, then implement and rerun.

- [ ] **Step 3: Export from Git objects, not the live example directory.**

Use `git ls-tree -r -z` at the pinned commit. For each allowed regular blob, fetch bytes using `git cat-file blob OBJECT_ID`, validate that its normalized path stays beneath destination, create its parents and write bytes; preserve executable mode. Reject symlinks, submodules and traversal paths rather than extracting them. Read only `apps/inkwell/` and `LICENSE`. This automatically excludes user data, ignored files, AppleDouble files, credentials, old runtime code and existing sessions.

Copy current skill resource files from the working tree, including new files that have not yet been committed. Traverse only this known skill directory, reject symlinks, and exclude directories `.git`, `node_modules`, `__pycache__`, `dist`, `.vite`; exclude `.DS_Store`, names beginning `._`, bytecode, and `sssf.db*`. Never read the live example worktree for this step. Compare copied bytes against the source manifest so tests cannot accidentally exercise a stale committed template. This supports the existing two-step distribution path without requiring staging before tests.

- [ ] **Step 4: Test the other two installation modes.**

1. Run install twice on a fresh example target; application hashes, config, prompts and Justfile must remain unchanged on the second pass.
2. In a separate scratch target, seed the pinned example Justfile and a user-modified config/prompt, then run install. Assert exact preservation and a skip report. Explicitly assert this old Justfile still lacks `demo`; this verifies non-destructive re-install, not an upgrade failure.
3. Compare the fixture's example recipe names against `just --summary` on a temporary file exported from the pinned commit; ensure `canonical - {'demo', 'smoke-real-pi'} == example - {'cc', 'ipi'}`.
4. Run the fresh install from a target path containing spaces. Dependencies and caller cwd must not select the historical runtime accidentally.

- [ ] **Step 5: Verify and commit.**

Run `just test-install`. Missing Git objects are a prerequisite failure, not a skipped test. Commit as `test: verify installs against pinned inkwell files`.

---

## Task 4: Characterize config, envelopes, prompts, gates and Git behavior

**Files:** Create `tests/support/runtime.py`, `tests/unit/test_config.py`, `tests/unit/test_contracts.py`, `tests/unit/test_gates.py`, `tests/unit/test_permissions.py`, `tests/unit/test_changes.py`.

**Interfaces:**

- `tests.support.runtime` imports the verified bootstrap from Task 1; it does not duplicate import-path or dotenv logic.
- `RuntimeTestCase(FactoryTestCase)` stamps the temporary target, initializes a Git repository with local-only identity `SSSF Test <sssf@example.invalid>`, disabled hooks/signing, and tracked `sample.txt` containing `original\n`; commit the stamped files and sample as the fixture baseline. The install's `.gitignore` excludes runtime session writes from permission diffs. It changes cwd to the target and restores it in teardown. Tests run serially because cwd is process-global.

- [ ] **Step 1: Write config and contract cases using actual public types.**

```python
class ContractTests(RuntimeTestCase):
    def test_phase_description_cannot_echo_name(self):
        with self.assertRaises(ValidationError):
            PhaseParams(name="build", kind="agent", owner="builder", description="Build")

    def test_gate_report_derives_violations_from_checks(self):
        report = GateReport().check("plan.md", True, "exists")
        report.check("missing.md", False, "missing")
        self.assertFalse(report.passed)
        self.assertEqual(report.violations, ["missing.md: missing"])
        self.assertEqual(len(report.checks), 2)
```

Import `ValidationError` and named runtime models. Add cases for required envelope status; invalid status; default artifact lists not shared; Generic/Plan/Build/Scout/Review/Document/Verify envelope round-trip; prompt replacement of all three supported variables; exact saved prompt bytes.

- [ ] **Step 2: Exercise config validation without real Pi.**

Test inherited/overridden model, thinking, tools and extension paths; preserve `tools=[]` and `writes=[]` as distinct from omission; reject missing required agents, missing prompt files and `coding_agent='claude_code'` at runtime validation. Patch only model catalog resolution to a fixed list. Assert validation never reaches `agent_pi.run`. Do not claim the schema already rejects Claude Code—the current validator, not the schema, does that.

- [ ] **Step 3: Exercise gate and permissions policy boundaries.**

Required gate cases: existing artifact, missing artifact, zero-byte file, valid/invalid JSON, review approval with blocking findings, rejection without a finding, and a failing `tests_pass` command using `sys.executable -c 'raise SystemExit(3)'` in scratch cwd.

Required permission cases: `writes=None`, `writes=[]`, exact path, directory prefix, single-segment `*`, recursive `**`, protected path with/without explicit grant, runtime directory grant. For enforcement: modify previously clean `sample.txt` as read-only scout, expect `PermissionBreach` and original bytes restored. Do not use an operator file or ignored secret as input.

- [ ] **Step 4: Exercise actual Git capture in scratch repos.**

Test missing repo and missing ref errors; base branch with dirty file; a feature branch ahead of its base; clean tree falling back to last commit; untracked file inclusion/exclusion; diff truncation using a two-line limit; artifact path under an explicitly absolute scratch `context_handoff_dir` supplied to `changes.capture`. Assert returned filenames, counts, base commit/reason, and diff artifact contents. These commands never run in the source checkout.

- [ ] **Step 5: Verify and commit.**

Run `just test-unit`. Existing correct behavior may pass immediately. Any observed bug goes through the rule in section E; no speculative production refactor in this task. Commit as `test: characterize factory contracts and git boundaries`.

---

## Task 5: Verify SQLite schema, migrations and independent-reader visibility

**Files:** Create `tests/unit/test_tracer.py` and `tests/control_plane/{__init__,test_runner}.py`.

**Interfaces:**

- `make_run(target: Path, adw_id: str) -> Run` in `tests/support/runtime.py` — with cwd already set to target, load its stamped config, construct real `Tracer` and `Run`, call `tracer.session_start`, and use engineer `sssf-test`. Keep `defaults.data_dir='adws/adw_data'` so permission-prefix semantics match production; resolve only the trace DB path absolutely for independent readers. Register `run.tracer.conn.close` with the caller's cleanup. Direct construction avoids registering signal handlers in unit tests.

- [ ] **Step 1: Write a visible-before-finish assertion.**

```python
class RunnerTests(RuntimeTestCase):
    def test_phase_is_visible_to_an_independent_reader(self):
        run = make_run(self.target, "a1b2c3d4")
        self.addCleanup(run.tracer.conn.close)
        with run.phase(PhaseParams(name="inspect", kind="code", owner="test",
                                   description="Record evidence before finishing")):
            with sqlite3.connect(run.tracer.db_path) as reader:
                status = reader.execute(
                    "SELECT status FROM phases WHERE adw_id=?", (run.adw_id,)
                ).fetchone()[0]
            self.assertEqual(status, "running")
        self.assertEqual(run.finish(), 0)
```

This tests SSSF persistence visibility, not live Pi streaming.

- [ ] **Step 2: Test schema creation and additive migrations.**

Assert all seven runtime tables exist and pragmas are WAL/NORMAL/5000ms. Seed literal old table definitions for sessions, agent_sessions, and gate_results without the six columns in `MIGRATIONS`; insert a sentinel row. Open `Tracer`, assert the new columns and sentinel survive, close, reopen and assert idempotency. Do not derive old fixtures by deleting text from `SCHEMA`, which would let production/schema mistakes redefine their own test input.

- [ ] **Step 3: Verify persisted records and outcome semantics.**

Required cases: event JSONL and DB share event ID/payload; tool span start/end preserved; invalid and valid envelope rows retain attempts; gate checks/violations both persisted; `session_add_usage` adds two calls correctly; process_start/process_end rows are closed once; `finish(accepted=False)` returns 1, writes session fail and `not_accepted`; raising inside a phase records phase/session fail; joining a completed run appends phase sequence rather than overwriting old rows.

Do not infer OS process death from a DB row marked ended. Test that separately in Task 7.

- [ ] **Step 4: Verify and commit.**

Run `just test-unit` and `just test-control-plane`. Close tracer connections after every test; make sure temporary DBs can be reopened independently. Commit as `test: cover trace persistence and run outcomes`.

---

## Task 6: Add an explicit offline Pi protocol double

**Files:** Create `tests/fixtures/pi-double.py`, `tests/control_plane/test_pi_transport.py`; extend `tests/support/processes.py`.

**Interfaces:**

- The executable double implements only the wire surface consumed by the current `agent_pi.py`: `--list-models`, `-p --mode json`, provider/model, thinking, session-id/session-dir, system prompt, tools, repeated `-e`, final prompt.
- It requires `SSSF_TEST_DOUBLE=1` and a scratch `SSSF_PI_SCENARIO` file; otherwise exit 64. It never imports or shells out to real Pi and has no network client.
- Scenarios use JSON records with `text`, `exit_code`, `usage`, `events`, `writes`, and optional `wait_for_release`. A write record is `{"path": "relative/to/target", "text": "fixture bytes"}`; an event is a literal JSON wire event; `wait_for_release` is a path under the scratch directory. State/log files live only in the target's ignored `adws/adw_data/sessions/test-double/` directory. Unexpected extra sends are an error, not a default success. Catalog queries do not consume a scenario response.

- [ ] **Step 1: Define a minimal scenario and transport assertion.**

```json
{
  "responses": [
    {
      "text": "{\"status\":\"success\",\"summary\":\"synthetic response\"}",
      "exit_code": 0,
      "usage": {"input": 10, "output": 2, "cacheRead": 0, "cacheWrite": 0,
                "totalTokens": 12, "cost": {"input": 0.01, "output": 0.002,
                "cacheRead": 0, "cacheWrite": 0, "total": 0.012}},
      "events": [],
      "writes": []
    }
  ]
}
```

Write a test constructing real `PiRequest`, installing the double with `install_python_entrypoint`, patching `agent_pi.PI_PATH` to that executable shim and `MODELS_JSON` to scratch `{"providers": {}}`, clearing `_pi_catalog` before/after. Assert real `agent_pi.run` returns exactly 12 tokens, cost approximately 0.012 (`assertAlmostEqual`), the text above, and a raw JSONL file. Spawn/exit callbacks must reference the child's actual PID. Initial failure is missing double implementation.

- [ ] **Step 2: Implement the process protocol.**

Print a catalog headed `provider model context max-out thinking images` with `fixture fixture-model 32K 4K yes no`. Emit a `session` header and real-shaped `message_end`/tool_execution events, each followed by flush. Request logs capture synthetic prompts and argv in scratch only. Increment response position atomically in the scenario state. Permit scenario writes only after resolving their destination beneath the scratch target. Gate writes are fixture actions, not genuine model intelligence.

The fixture contains an unmistakable `synthetic_pi` marker in its own session/header output. Live acceptance rejects that marker and rejects the double executable path.

- [ ] **Step 3: Test streaming with a deterministic release handshake.**

The double emits a completed tool event, flushes stdout, then waits for a controller-created release file for at most ten seconds. While it waits, the test must observe the forwarded tool record and confirm the child is still alive. Only then create the release file. A five-second observation deadline failure releases/terminates the owned child in `finally` and fails the test. Do not use a final row count as a streaming assertion.

- [ ] **Step 4: Cover transport failure and event folding.**

Assert a nonzero exit with no assistant text raises; malformed non-JSON stdout does not erase a subsequent valid event; one announce/start/end sequence produces exactly one tool_call with matching ID/tool/args/result; Unicode output survives; catalog resolution selects explicit provider and rejects ambiguous bare patterns. Use a bounded child stderr sample. A large-stderr hang reproduction belongs to the separately bounded known-gap lane, not a hanging normal test.

- [ ] **Step 5: Verify and commit.**

Run `just test-control-plane` in the credential-free environment. Assert only the double and owned Python/Git subprocesses launched. Commit as `test: add explicit offline pi transport double`.

---

## Task 7: Cover retries, permissions and failures without hiding known defects

**Files:** Create `tests/control_plane/test_agents.py`, `tests/control_plane/test_lifecycle.py`, `tests/known_gaps/{__init__,test_safety,test_failures}.py`, `docs/known-gaps.md`; extend the runtime helper with scenario setup.

**Interfaces:**

- `execute_scenario(case: RuntimeTestCase, scenario: dict[str, object], options: ScenarioOptions) -> ScenarioResult` — uses a real scratch config, Run, Tracer and AgentCall; only Pi is the double. Options name output type, gates, retries and read-only/write permission. Result exposes captured error, persisted run ID, request-log path and process evidence; it must not suppress assertions.
- Each test verifies rows using a fresh SQLite connection and exact expected attempts.

- [ ] **Step 1: Write retry behavior assertions against the real orchestrator.**

```python
class AgentRetryTests(RuntimeTestCase):
    def test_bad_json_is_corrected_in_the_same_session(self):
        result = execute_scenario(self, responses("not-json", '{"status":"success"}'),
                                  ScenarioOptions())
        self.assertIsNone(result.error)
        requests = result.requests()
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0]["session_id"], requests[1]["session_id"])
        self.assertIn("not valid JSON", requests[1]["prompt"])
        self.assertEqual(result.envelope_validity(), [0, 1])
```

Define `responses(*texts)` locally to build Task 6 scenarios with fixed usage per send; implement `ScenarioOptions`, `requests()` and `envelope_validity()` in `tests/support/runtime.py` exactly as named. Errors from the orchestrator are captured for explicit assertions, not treated as a passing test automatically.

- [ ] **Step 2: Add the full behavior table.**

| Case | Expected evidence |
|---|---|
| Valid first envelope | One send; valid row; handoff and agent_end; success |
| Malformed then valid | Two sends, same session ID; invalid then valid rows |
| Always malformed | Exactly three sends (`JSON_FIX_ATTEMPTS + 1`); phase/session fail |
| Missing artifact then created on correction, phase retries=1 | Two sends; gate attempts 1 fail / 2 pass with checks |
| Gate still fails with retries=0 | One send; GateFailure; no downstream phase |
| Envelope status fail | Parsed envelope stored; run fails |
| Valid output plus unauthorized clean-file edit | PermissionBreach; original bytes restored; no accepted handoff |
| Valid output plus allowed handoff-file write | File exists; phase succeeds |
| Repeated successful calls for one agent | Same mapped session ID; phase sequence increases |
| Three sends with fixed 12-token usage each | Session totals 36, cost 0.036, final successful agent_end reconciles |
| Normal child completion | Child actually exited and process row ended |
| Signal to controller-owned ADW process | Capture process/DB outcome separately; no signal to other runs |

Use an in-process `Run` for most cases; test OS signal behavior in a supervised child because `session.ensure` installs process-global signal handlers. Always restore handlers for direct lifecycle tests.

- [ ] **Step 3: Add narrow known-gap reproductions for M2.**

Each case asserts the desired invariant. Run once undecorated to capture the precise failure, then add `expectedFailure` only if the known defect is reproduced. Do not pre-declare results as measured. Setup and scenario-execution exceptions must fail the suite rather than count as the expected invariant failure. Execute the reproduction and capture its result in `setUp` with registered cleanup; put only the final desired-invariant assertion in the `expectedFailure` test method.

| ID | Reproduction / desired assertion | Owner |
|---|---|---|
| M2-PERM-01 | Replace an already-dirty line with different bytes but identical numstat; `changed_paths` must report it | M2 |
| M2-PERM-02 | Change an existing untracked file's contents; snapshot must notice it | M2 |
| M2-PERM-03 | Modify synthetic ignored `ignored.txt` outside runtime; permission enforcement must catch it | M2 |
| M2-PERM-04 | Unauthorized write followed by exhausted JSON parsing; enforcement must still run | M2 |
| M2-TRACE-01 | Exhausted JSON/gate correction; agent_end usage must exist | M2 |
| M2-PROC-01 | Interrupt an ADW owning a blocked double; child must actually terminate, not just have ended_at set | M2 |
| M2-PROC-02 | Child writes more than pipe capacity to stderr while stdout remains open; transport must finish or fail within deadline | M2 |

The process-gap tests must use external deadlines and owned-group cleanup even while reproducing a leak/deadlock. No indefinite waits. Document test name, command, assertion failure and owner in `docs/known-gaps.md`. Broader commit-isolation changes are M2 work; do not alter `commit_all` here.

- [ ] **Step 4: Verify the lanes separately and commit.**

Run `just test-unit`, `just test-install`, `just test-control-plane`, then `just test-known-gaps`. Ordinary lanes must have zero skips/expected failures. The known-gap command must enumerate IDs, expected failures and unexpected successes. Record that distinction; do not report “all safety tests pass.” Commit as `test: cover orchestration retries and record m2 gaps`.

---

## Task 8: Add bounded real-Pi smoke verification and a fresh-target launcher

**Files:** Create `.claude/skills/sssf/templates/adws/adw_smoke.py`, `.claude/skills/sssf/templates/adws/adw_modules/smoke.py`, `.claude/skills/sssf/templates/prompt_engineering/smoke/{system,user}.md`, `scripts/smoke-real-pi.py`, `tests/unit/test_smoke.py`, `tests/control_plane/test_smoke_supervisor.py`; modify product and root Justfiles and `tests/install/test_justfile.py`.

**Interfaces:**

- Installed command: `just smoke-real-pi --probe-file README.md`; config from existing `SSSF_CONFIG`; probe file must be a regular file inside target root.
- Development command: `SSSF_SMOKE_MODEL=provider/model-id just smoke-real-pi`; requires an explicit model, exports the pinned Inkwell app to a new target, installs current templates, writes a smoke-only local roster, and invokes the installed command with `--probe-file apps/inkwell/README.md`.
- No default to `opencode/gemini-3.6-flash`. M0's model is evidence from one machine, not a product prerequisite or permission to inspect credentials.
- `smoke.configure_probe(cfg: SSSFConfig) -> SSSFConfig` — copy the selected config, derive only the smoke agent's model/thinking from the configured scout, keep original roster untouched, add a smoke-only role with tools `read,write`, no harness extensions, `writes=[]`, and the new smoke prompt paths.
- `smoke.receipt_gate(expected: Path) -> Callable` and `smoke.recall_gate(nonce: str) -> Callable` — closure gates returning `GateReport`; receipt must be the exact expected path and nonempty; recall is exact summary match without disclosing nonce in correction text.
- `SmokeEvidence` in `smoke.py`: `probe_file: Path`, `receipt_file: Path`, `recall_raw_offset: int`, `first_pi_session_id: str`. Record offset and actual Pi session header ID after the probe call, before recall.
- `smoke.verify_trace(run: Run, evidence: SmokeEvidence) -> GateReport` — require probe read/write evidence, no recall tool calls/announcements in raw output after the saved offset, successful phase/envelope records and actual Pi session continuity.

- [ ] **Step 1: Write tests for smoke boundaries before production code.**

Test missing explicit development model, nonexistent probe file, probe path escaping repo, non-scout mutation in derived config, fake executable refusal, missing provider, nonzero exit, missing receipt, empty artifact list, wrong recall answer, tool use during recall, changed Pi session identity, and wrong trace DB. For each case assert nonzero or a failed gate; no “skip because credentials missing.” Tests patch transport or use the double only in `test-control-plane` and are not live acceptance evidence.

The new prompts ask for `GenericOutput`, and both call sites use `output_type=GenericOutput`. The system text is:

```text
You are SSSF's smoke probe, not a software builder. Follow the current task only.
Read only the explicitly named probe file. Write only the requested receipt in
context_handoff_dir. Do not use subagents. During a recall task use no tools.
Respond with only GenericOutput JSON: status, summary, artifacts, notes_for_next_agent.
```

`user.md` renders the existing `prompt`, `previous_envelope`, and `context_handoff_dir` variables and includes a valid GenericOutput JSON example. Do not alter the scout's production prompt to accommodate a test.

- [ ] **Step 2: Implement the two-call ADW using real runtime primitives.**

`adw_smoke.py` uses the same dependency header as other ADWs. Resolve/validate config and probe path before creating a session. Record the request in an engineer phase. Mint a fresh 32-hex-character nonce. Use the same smoke agent in two agent phases, each with zero gate retries:

1. **probe:** ask Pi to read the nominated file, write exactly `SSSF smoke receipt\n` to this run's `context_handoff_dir / 'smoke-receipt.txt'`, remember the nonce only in conversation, and return summary `probe complete` plus that artifact. Apply receipt/existence/nonempty gates.
2. **recall:** ask for the remembered nonce as summary, `artifacts=[]`, no tools. Do not inject the first envelope or nonce into this prompt. Apply recall gate.

Then a code phase calls `verification = smoke.verify_trace(run, evidence)` to check session records and absence of recall tools. Return `run.finish(accepted=verification.passed, reason="; ".join(verification.violations))`. The workflow must not return success before this check.

Example of the load-bearing handoff:

```python
with run.phase(PhaseParams(name="recall", kind="agent", owner="smoke",
                           description="Verify prior context without reinjecting it")) as ph:
    ph.call(AgentCall(output_type=GenericOutput,
                     prompt="Return the remembered nonce as summary. Use no tools.",
                     gates=[smoke.recall_gate(nonce)]))
```

Check the Pi JSONL session headers and parent-linked message entries, not only `agent_map.json`. The second call must continue the first call's conversation in the same session file. Inspect tool events to ensure recall did not read the saved prompt or session files to retrieve the answer. This proves more than identifier reuse.

Receipt creation is the smoke's real file-write check. It does not certify builder output, product-code edits, repairs or the application's full test suite. Pi's ambient user resources remain part of the real runtime; record their non-secret configuration effects when diagnosing failures. A fresh Git directory and a tools list are not an OS sandbox. A model that violates the bounded task fails the smoke; do not loosen the gate to get a green run.

- [ ] **Step 3: Implement the developer launcher with owned-process supervision.**

The root script requires `SSSF_SMOKE_MODEL` and a real `PI_PATH` or PATH `pi`, records their non-secret identifiers, creates a fresh example target via Task 3, and derives a local config without touching starter model defaults or user files. Keep normal Pi authentication available for this explicitly live lane; never read or copy `auth.json` into the target or report. Set `ENGINEER_NAME=sssf-smoke` in the child environment so baseline output does not record the operator's personal Git identity.

After writing the smoke-only local roster in the disposable target, include it in the synthetic fixture baseline before launching any agent; no user files are involved. Mint the ADW ID in the launcher and pass it explicitly to the installed `just smoke-real-pi`. Capture stdout and stderr in separate local files using `Popen(start_new_session=True, stdin=DEVNULL)`. Poll a readonly connection to the **specific target's** DB every 200ms. Evidence of live streaming requires observing a tool_call for this ADW while its probe phase is `running` and the launched process is still alive. Record the observation time and event ID. If no live observation occurs, report that check as unverified rather than infer it from final counts.

Bound the entire live run to 180 seconds. On timeout/cancellation, terminate the process group created by the launcher, wait five seconds, then kill only that owned group if still alive and reap it. Preserve the scratch evidence on failure; never invoke the product's `kill` recipe for harness cleanup.

Before launch, reject `SSSF_TEST_DOUBLE`, the known double path and any argv-recorder path. After launch, reject the synthetic marker from Task 6. This prevents accidental fake fallback; it is not an attestation against a deliberately substituted executable.

After exit require: subprocess exit zero, exact ADW ID success in the selected DB, receipt contents, two valid envelopes, same actual Pi session history, no recall tool use, live observation, app-file hashes unchanged, no unrelated tracked changes, no remaining owned child. Token values come from actual reports; zero provider cost is valid and not proof that no model ran.

Store raw evidence under gitignored `test-results/real-pi/` with restricted permissions. Print only model, run ID, statuses, paths, measured durations and reported usage/cost. Do not print credentials, inherited environment, raw provider failures or source contents to the committed report.

- [ ] **Step 4: Wire the two commands and complete the recipe contract.**

Installed recipe:

```just
smoke-real-pi *ARGS:
    uv run adws/adw_smoke.py --config "$SSSF_CONFIG" "$@"
```

Development recipe:

```just
smoke-real-pi:
    uv run --locked --group test python scripts/smoke-real-pi.py
```

Add `smoke-real-pi` to the exact canonical assertion. Test the installed route with the argv recorder and test the developer supervisor with synthetic child processes under the control-plane label. Developer `just test` must never invoke this live command implicitly.

- [ ] **Step 5: Verify offline implementation and commit.**

Run all populated offline lanes. Verify three supervisor outcomes deterministically: valid live-style observation before child release, child failure before DB creation, and timeout with owned child cleanup. Test that an unrelated listener/process is untouched. Commit as `feat: add explicit real-pi smoke acceptance command`.

Do not claim live acceptance in this commit solely because these tests pass. The actual paid/local-model run occurs in Task 9 after the operator confirms the selected model.

---

## Task 9: Document the contract, run real acceptance and record evidence

**Files:** Create `docs/testing.md`, `docs/baselines/m1-acceptance.md`; update `README.md`, `.claude/skills/sssf/cookbooks/install.md`, `.claude/skills/sssf/templates/justfile` comments and `docs/superpowers/specs/2026-09-12-factory-evolution-design.md` only for the clarifications below.

- [ ] **Step 1: Document executable commands and the installation distinction.**

`docs/testing.md` must explain:

- one-time `uv sync --locked --group test --python 3.11` and pinned-example Git fetch;
- what each root `just test-*` command runs and what it cannot prove;
- why root development recipes are not stamped;
- fresh install vs skip-preserving re-install vs future M3 update;
- the exact canonical recipe list and excluded names;
- noninteractive shell, quoted argv, parameterized inspection and conservative `kill` behavior;
- the real-Pi command requires explicit model choice, uses real authentication, spends tokens, preserves local evidence, and can fail;
- M1 does not certify M2 safety fixes or UI rendering;
- `.claude/skills/sssf` is a resource location during M1, not a requirement for the Claude application.

Make the spec consistent with measured M0 evidence: name the equivalent two recipes used when `demo` was absent, mark the M0 stage as recorded, and explain that M1 drift assertions cover freshly stamped files rather than silently updating users' custom Justfiles. Do not rewrite old logs or claim the originally attempted `just demo` succeeded.

- [ ] **Step 2: Run every offline lane and inspect the full results.**

```bash
just test-unit
just test-install
just test-control-plane
just test-known-gaps
git diff --check
```

Record the actual counts and expectation IDs. Ordinary suite skips, empty discovery, unexpected errors, and unexpected known-gap successes block completion. Record all dependency versions from the locked environment, not remembered M0 versions.

- [ ] **Step 3: Confirm a model, then run the real lane.**

Ask the operator to choose a current exact `provider/model-id` from their real Pi catalog and confirm live execution. Do not inspect credentials or assume M0's provider is still authenticated. The operator sets `SSSF_SMOKE_MODEL`; the execution command is then exactly:

```bash
just smoke-real-pi
```

Missing model, credentials, Pi executable, catalog entry or failed provider execution is a failed prerequisite/run, not a pass. Do not retry a paid run silently or swap providers. Diagnose a failure from retained local evidence and report the blocker. Real-Pi acceptance must pass before M1 is marked complete.

- [ ] **Step 4: Verify preservation and write a sanitized report.**

Required report facts: current factory commit, pinned example SHA, lockfile hash, actual command, Pi/Python/uv/Just versions, model/provider identifier, run ID, exact exit statuses, unit/install/control-plane counts, known-gap IDs/counts, receipt check, live-event observation, session-continuation result, token/cost values reported by Pi, app hash check and owned-process cleanup outcome.

Compare the historical example worktree's HEAD and tracked diff before/after to prove it was not updated. Preserve pre-existing untracked files; do not delete them to make status look clean. Include local evidence paths without publishing raw prompts, environment values, credential contents, full provider errors, or unrelated sessions.

If any acceptance check is blocked or unverified, title the result `M1 incomplete` and name that check. An honest blocker report is useful but does not satisfy the milestone.

- [ ] **Step 5: Review and commit only intended artifacts.**

Review template-to-stamped diffs, independent recipe expectations, captured exit codes, process ownership, known-gap disclosures and real-Pi evidence. Use independent review only if a real subagent tool is available; otherwise state that review was inline. No API-only result may be called UI validation.

Stage only the documented source/test/doc files. Never stage the scratch target, auth, sessions, provider output or raw trace DB. Commit the final documentation/evidence summary as `docs: record m1 installation and real-pi acceptance`. Do not merge, push or publish without approval.

---

## Execution checkpoints

| Checkpoint | Required evidence | Does not establish |
|---|---|---|
| Tasks 1–3 | Canonical recipe tests, argv/exit tests, current installer on pinned app, preserved custom re-install | Safe upgrades to every existing project |
| Tasks 4–7 | Unit/control-plane results plus disclosed M2 reproductions | Pi authentication, real model behavior or repaired safety defects |
| Task 8 | Smoke command and supervisor tested offline | A successful real-Pi run |
| Task 9 | Explicit real-Pi acceptance with live visibility and continuation checks | UI usability or full SDLC correctness |

M1 is complete only when these checkpoints have their required evidence. Do not use M0's historical success in place of Task 9.

## Plan self-review / spec coverage

| Spec M1 requirement | Plan task |
|---|---|
| Canonical Justfile, example minus exclusions plus demo | 1–2, exact completed set in 8 |
| Drift regression, fresh stamping, `just --list` | 1–3 |
| Existing example remains manual Factory Lab | 3, 9 preservation checks |
| Clean example-based installation targets | 3 |
| Unit checks in spec section 5.1 | 4–5 |
| Retry/permission/lifecycle/usage persistence coverage | 5–7, known defects separately disclosed |
| Real-Pi smoke recipe and genuine execution | 8–9 |
| Justfile behavior and SQLite trace evidence | 2, 5–9 |
| Fake/real separation | 1, 6–9 |
| No second application | Git export in 3, tiny disposable unit inputs only |

M2's permission/process fixes, M3's generic package/updates and source relocation, M4's wider workflow improvements, and M5's UI redesign are deliberately not implemented here. The new conservative stop helper is needed to expose the canonical `kill` recipe without copying an unsafe broad process matcher; it does not replace M2 lifecycle work.

The plan specifies no API credentials, invented version outputs, fixed successful token counts, hidden provider fallback or pre-filled acceptance result. Implementers must record actual outcomes at execution time.
