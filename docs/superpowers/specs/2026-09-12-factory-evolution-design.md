# SSSF Evolution Design

## 1. Status and scope

**Status:** proposed design for review.

This document defines the next development cycle for the Super Simple Software Factory (SSSF). It is intentionally limited to the local, Pi-based factory: installation into an existing project, Justfile workflows, deterministic Python orchestration, SQLite traces, and the local visualizer.

This document does not authorize implementation of a hosted service, remote workers, multi-user accounts, or a second agent harness.

## 2. Product definition

SSSF is a local software factory that installs into an existing project and runs repeatable agent-plus-code workflows.

The product has one supported agent harness:

> **Pi is the only agent harness supported by SSSF.**

Claude Code is not an agent harness in SSSF. Claude Code is an optional operator interface that can expose `/sssf` commands. A user must be able to install and operate SSSF without Claude Code installed.

The product interfaces are:

| Interface | Required? | Responsibility |
|---|---:|---|
| Pi | yes | Execute every agent phase |
| `sssf` CLI | yes, after M3 | Install, diagnose, and invoke factory operations from a terminal |
| generated Justfile | yes | Provide project-local repeatable workflow commands |
| Claude Code `/sssf` skill | optional | Translate conversational requests into CLI/Justfile operations |
| visualizer | yes | Read-only inspection of SQLite traces |

The Claude skill does not install or execute agents by itself. It invokes the same installation and workflow commands available to a terminal user.

## 3. Fixed architectural decisions

### 3.1 Pi-only runtime

All agent phases call Pi through the existing `agent_pi.py` path. No Claude Code subprocess is started by the runtime.

The target runtime configuration has no selectable alternative harness. During the M3 migration, an existing `coding_agent` field is accepted only when its value is `pi`; any other value is invalid. The `agent_cc.py` stub and `claude_code` schema option are removed in M4.

Model provider and agent harness are separate concepts. A model supplied by Google, OpenRouter, Fireworks, OpenAI, or another provider is still executed through Pi. The starter roster remains provider-configurable; this design does not prohibit a model provider unless a later policy explicitly does so.

### 3.2 Installation is CLI-first

The current installer remains the behavioral baseline. The generic CLI becomes the primary installation interface in M3.

The supported installation paths are:

```text
uvx sssf init                 # primary path after M3
uv run <installer>/install.py # compatibility path during migration
/sssf install                 # optional Claude frontend after skill installation
```

All three paths must call the same installation library after M3. They must produce the same target files and the same conflict behavior.

`sssf init` runs from the target project root and performs these actions:

1. copy runtime templates into `adws/`;
2. copy prompt files into `adws/adw_data/prompt_engineering/`;
3. copy the Pi extension templates into `adws/adw_data/harness_engineering/`;
4. copy the starter roster into `adws/adw_sssf_config/sssf.config.yaml`;
5. copy `.env.sample` and the generated `justfile`;
6. add runtime paths to `.gitignore`;
7. report stamped files, skipped files, and conflicts.

The default behavior remains non-destructive: existing files are skipped. An explicit update/force operation is required to overwrite a file.

### 3.3 Claude skill is an optional integration

The source repository retains the Claude skill through M3 so existing `/sssf` installation remains available. The skill is packaging and documentation, not runtime code. M3 moves its source into a dedicated integration directory while preserving the target path `.claude/skills/sssf/` for users who explicitly install it.

The source layout after M3 is:

```text
integrations/claude-skill/sssf/  # optional skill source
src/sssf/                        # CLI and installation library
templates/                       # stamped runtime files
apps/visualizer/                 # trace UI
```

The target project may receive `.claude/skills/sssf/` only when the user explicitly installs the optional skill. A target project using only Pi, the CLI, and Justfile does not need `.claude/`.

### 3.4 Justfile remains first-class

The generated Justfile remains a supported interface. The CLI does not replace project-local Just commands.

The template justfile in the factory source repository is the **canonical** justfile. From M1 onward it is the single source of truth for stamped recipes, and it must be a superset of every recipe the pinned example worktree ships (minus the exclusions below). Recipe drift between the template and previously stamped repos is detected by an M1 regression test, not by users.

**Exclusions from the canonical set:** `cc` and `ipi` — recipes that boot a Claude-Code or ipi orchestrator — are not stamped by default, because the factory is Pi-only and `/sssf` is an optional frontend. They may exist as documented opt-in additions.

The installed project continues to expose commands such as:

```text
just demo
just scout ...
just plan ...
just sdlc ...
just sessions
just phases <adw-id>
just obs
```

Changes to CLI behavior must not silently change the meaning of existing Justfile recipes. Recipe changes require an explicit migration note.

## 4. Example branch and Factory Lab

The upstream `example` branch is the Factory Lab for this development cycle. It is not a plan for creating another demo application.

The Factory Lab has two forms:

1. a separate worktree used for manual real-Pi dogfooding;
2. clean temporary copies used by automated installation and control-plane tests.

The source repository and Factory Lab remain separate:

```text
super-simple-software-factory/  # factory source, normally main
sssf-example/                   # worktree of the pinned upstream/example commit
```

The baseline must record:

- upstream URL;
- example branch commit SHA;
- local worktree path;
- command invoked;
- ADW ID, when a workflow runs;
- result and failure output.

The example project is used for manual acceptance because it contains a complete stamped factory, real prompts, a Justfile, a demo application, and historical traces. It is not the only automated fixture because historical state and model output are not deterministic.

M0 and M1 do not create a second demo application. A test that does not need the full example project may create a temporary repository containing only the files required by that test; such a repository is disposable test input, not a product example and not a second Factory Lab.

## 5. Test model

Every test command must identify which layer it exercises.

### 5.1 Unit tests

Unit tests do not start Pi or require API credentials. They cover:

- configuration parsing and validation;
- Pydantic models;
- prompt rendering;
- gates;
- path matching and permission policy;
- SQLite schema creation and migrations;
- Git change-capture helpers.

### 5.2 Control-plane tests

Control-plane tests use a deterministic Pi test double or recorded Pi event stream. They test SSSF behavior around an agent call, not the Pi product.

They cover:

- phase transitions;
- malformed JSON retries;
- gate-correction retries;
- permission-breach handling;
- process cleanup;
- session finalization;
- usage aggregation;
- event and envelope persistence.

These tests must be labeled `control-plane`. A passing control-plane test is never reported as proof of Pi integration.

### 5.3 Real-Pi smoke test

The real-Pi smoke test starts the installed `pi` executable and uses a configured provider. It validates:

- executable discovery;
- Pi command-line flags;
- model resolution through Pi;
- provider authentication;
- JSONL output streaming;
- tool-call event parsing;
- session creation and continuation;
- typed envelope parsing;
- real file changes;
- SQLite trace generation.

The command is:

```text
just smoke-real-pi
```

The command must fail clearly when Pi, the model, or credentials are unavailable. It must not silently fall back to a test double.

The real-Pi smoke test is required for M0 completion and for release acceptance. Unit-test and control-plane commands do not run it. If Pi or provider credentials are unavailable, the smoke test must fail with a prerequisite message and M0 remains incomplete.

### 5.4 Factory Lab dogfooding

Factory Lab dogfooding uses real Pi, the generated Justfile, and the visualizer. It evaluates product behavior that automated tests cannot judge well:

- prompt usefulness;
- workflow ergonomics;
- clarity of failure reports;
- quality of generated plans and code;
- trace readability;
- visualizer information architecture.

## 6. Milestone roadmap

### M0 — Baseline the upstream Factory Lab

**Purpose:** establish the current real-Pi behavior before changing the factory.

**Actions:**

1. Add or use an upstream remote pointing to `https://github.com/disler/super-simple-software-factory.git`.
2. Fetch the `example` branch.
3. Create a separate worktree at a path outside the factory source checkout.
4. Inspect the stamped files, Justfile, prompts, config, and existing traces.
**Recorded M0 outcome (2026-09-13):** the pinned example's Justfile had no `demo` recipe, so the recorded equivalent was the two read-only runs `demo` now composes — `uv run adws/adw_prompt.py … --agent scout` followed by `uv run adws/adw_scout.py …` — executed with a local model override from the example worktree. This is a recorded observation, not a certification of every Pi feature. The historical Justfile was not altered to make the record appear different. M1's recipe drift assertions cover freshly stamped files; they do not silently update users' custom Justfiles (re-install preserves them byte-for-byte and reports skips).

5. Run `just demo` from the example worktree. This is the fixed M0 real-Pi smoke path because it exercises the existing read-only `adw_prompt` and `adw_scout` workflows. See the recorded M0 outcome above for what actually ran.
6. Start the visualizer against the example trace database with `just obs`. If Bun dependencies or a browser are unavailable, record the exact prerequisite failure in the baseline report; this blocks the visualizer portion of M0 but does not change the real-Pi command.
7. Write the baseline report.

**Required output:**

```text
docs/baselines/2026-09-12-example-branch.md
```

The report must include the pinned SHA, exact commands, environment prerequisites, observed output, failures, and either screenshots/trace references or an explicit visualizer prerequisite failure.

**Exit condition:** `just demo` completes with real Pi from the pinned example worktree and the report makes the visualizer result explicit. If `just demo` cannot run, M0 is incomplete and the report records the blocking prerequisite.

M0 does not change runtime code and does not create a new application.

### M1 — Build the regression harness around the Factory Lab

**Purpose:** make installation and control-plane behavior repeatable without replacing real-Pi validation.

**Actions:**

1. Define the canonical justfile recipe set and make the template justfile that superset: every recipe in the pinned example justfile except `cc` and `ipi`, plus `demo`.
2. Add a drift regression test: stamp a clean temporary target, then assert the stamped justfile contains the canonical recipe set and that `just --list` succeeds there.
3. Use the pinned example project as the manual dogfooding target.
4. Create clean temporary copies or clones from the pinned example commit for installation tests.
5. Add unit tests for the modules listed in section 5.1.
6. Add control-plane tests for the failure and retry cases listed in section 5.2.
7. Add the `smoke-real-pi` command and run it against the example-based target.
8. Verify Justfile recipes and SQLite trace output in a clean target.
9. Ensure tests distinguish fake/recorded Pi from real Pi.
10. Add a smaller fixture only when a specific test cannot use the example-based target; document that reason beside the fixture.

**Required outputs:**

- automated test commands and test files;
- `just smoke-real-pi`;
- a clean-target install test;
- a documented distinction between control-plane and real-Pi tests.

**Exit condition:**

- clean temporary copies can be installed without manual file preparation;
- the stamped justfile in a clean target matches the canonical recipe set and the drift test passes;
- control-plane tests pass without API calls;
- `just smoke-real-pi` completes with real Pi;
- the example worktree remains available for manual dogfooding;
- no test claims that a test double proves Pi integration.

### M2 — Harden safety and lifecycle behavior

**Purpose:** prevent the factory from losing user work, committing unrelated work, or leaving misleading traces.

**Required changes:**

1. Replace permission snapshots based only on Git line counts with per-path content/state fingerprints.
2. Detect changes to ignored files outside the SSSF runtime directory and roll them back unless the agent explicitly has permission to modify them.
3. Prevent commit phases from staging unrelated pre-existing changes; stage only files belonging to the current run.
4. Run every workflow that can modify and commit code in a dedicated branch/worktree. Read-only workflows may run in the operator's existing worktree.
5. Close child processes and process records on normal completion, failure, and interruption.
6. Emit `agent_end` usage and context data for parse failures and gate failures when a Pi result exists.
7. Prevent the Pi subprocess from blocking because stderr is not drained.
8. Add regression tests for each behavior.

**Exit condition:** tests demonstrate that pre-existing work is preserved, unauthorized changes are detected, commit scope is controlled, interrupted runs are finalized as failed, and failed agent calls leave complete trace evidence.

### M3 — Generalize installation and add the CLI

**Purpose:** make installation independent of Claude Code while preserving the current installer and Justfile experience.

**Required commands:**

```text
sssf init
sssf doctor
sssf update
sssf install-skill       # optional Claude Code integration
```

**Required changes:**

1. Extract reusable installation logic from `scripts/install.py`.
2. Implement `sssf init` using that shared logic.
3. Keep the direct Python installer working during migration.
4. Add a stamped-version manifest.
5. Add dry-run output showing writes, skips, and conflicts.
6. Make the manifest record both each template's source hash and each installed file's target hash. Make `sssf update` overwrite a stamped file only when its current target hash matches the manifest; report user-modified files as conflicts. Keep a separate explicit force operation for overwriting conflicts.
7. Implement `sssf doctor` for Python/uv, Pi, model resolution, credentials, Git, and target-root checks.
8. Make `sssf install-skill` optional and separate from runtime installation.
9. Make `/sssf install` delegate to the shared installation behavior.
10. Keep all existing Justfile recipes supported.

**Exit condition:** a clean target project can be installed through `sssf init`, the direct Python installer, or `/sssf install`; all three produce equivalent runtime files; none requires Claude Code to be installed; and `just` workflows still run.

### M4 — Improve Pi workflows and extensions

**Purpose:** improve the usefulness and reliability of the Pi-based workflow catalog after the runtime is safe.

**Required changes:**

1. Require every enabled quality block to run a configured real command; a workflow must not report acceptance while an enabled block still uses `_placeholder`.
2. Improve workflow acceptance criteria and repair-loop reporting.
3. Improve Pi session continuation diagnostics.
4. Validate Pi extension paths and report unavailable extension tools clearly.
5. Remove the inactive Claude Code stub and all non-`pi` harness configuration from the supported runtime.

**Exit condition:** all supported workflows use Pi, quality commands are explicit, repair loops are observable, and no runtime path refers to Claude Code.

### M5 — Redesign the visualizer UX

**Purpose:** make a running or completed workflow understandable without reading raw JSON or terminal logs.

The UI must answer these questions from a session detail view:

1. Is the run running, successful, failed, or not accepted?
2. Which phase is running or failed?
3. What caused the failure?
4. What did the agent change?
5. What did gates verify?
6. What did deterministic quality commands report?
7. What did the run cost?
8. What can the user inspect or resume next?

**Required sequence:**

1. freeze and document the trace/API contract;
2. add deterministic fixture traces for UI development;
3. revise sessions-list and run-detail information architecture;
4. improve responsive behavior and accessibility;
5. improve typography, spacing, states, filters, and timeline readability;
6. validate against both fixture traces and real example traces.

**Exit condition:** a user can navigate from a run list to a failed phase, its evidence, its changed files, and its next action without opening the SQLite database manually.

### M6 — Package, document, and release

**Purpose:** make the Pi-based factory reproducible for a new user.

**Required changes:**

1. Document CLI, Justfile, direct-installer, and optional skill installation paths.
2. Document the control-plane versus real-Pi test boundary.
3. Publish the pinned example workflow and baseline procedure.
4. Add version and upgrade guidance.
5. Test installation into a project that does not contain the factory source.
6. Run real-Pi smoke acceptance and record its result.

**Exit condition:** a new user can install SSSF without Claude Code, configure Pi, run a Justfile workflow, inspect the trace, and update the installation using documented commands.

## 7. Development rules

1. Modify factory source, templates, CLI, and documentation in the factory source repository.
2. Do not modify generated factory files in the example worktree to fix source behavior.
3. Use the pinned example worktree for real-Pi dogfooding and visualizer evaluation.
4. Use clean temporary copies for automated installation tests.
5. Use test doubles only for control-plane tests; never use them as Pi integration evidence.
6. Keep the Justfile supported throughout all milestones.
7. Keep terminal/Pi installation independent of Claude Code.
8. Keep `/sssf` as an optional operator frontend, not a runtime dependency.
9. Keep Claude Code out of the agent harness and roster.
10. Do not redesign the visualizer against an undocumented or changing trace contract.
11. Complete each milestone only when its listed output and exit condition are satisfied.

## 8. Immediate next action

The next action is M0, not implementation of M1:

1. fetch the upstream `example` branch;
2. create the separate worktree;
3. inspect the target project;
4. run `just demo` with real Pi;
5. run `just obs` and record whether visualizer startup succeeds;
6. write the baseline report with the pinned SHA and all prerequisite failures.

No runtime code, CLI, or new application may be created until the M0 baseline report exists and `just demo` has passed. If `just demo` is blocked by missing prerequisites, resolve those prerequisites before M1 begins.
