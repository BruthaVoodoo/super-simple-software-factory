# Software Factory Evolution Design

## Status

Proposed design for review.

## Decision summary

Evolve SSSF into a **Pi-first, CLI-first, template-based local software factory** while retaining the generated Justfile and optional Claude Code skill as interfaces.

The factory source remains the product repository. The upstream `example` branch becomes the real-Pi dogfooding and integration target. Deterministic temporary repositories provide repeatable control-plane tests, but they do not replace real-Pi validation.

The factory is not being turned into a hosted web application in this phase.

## Goals

1. Preserve the current install-into-an-existing-project workflow.
2. Keep the Justfile as the primary project-local workflow surface.
3. Make the factory usable without Claude Code through a generic CLI.
4. Make real Pi integration an explicit, tested contract.
5. Improve safety before increasing agent autonomy.
6. Improve the visualizer after the trace and lifecycle contracts are reliable.
7. Document and preserve a staged roadmap so work stays focused.
8. Use the upstream example branch as a real, working target project.

## Non-goals for the first evolution cycle

- A hosted multi-user service.
- Cloud execution or remote worker management.
- Replacing the local SQLite trace architecture.
- Supporting every coding-agent provider immediately.
- Treating fake or recorded agent output as proof of Pi integration.
- Rewriting the existing install flow before it is covered by tests.

## Product boundary

The system will have three layers.

### Factory runtime

The Python runtime owns:

- phase sequencing;
- agent invocation;
- typed envelopes;
- gates and retries;
- permissions;
- quality commands;
- session lifecycle;
- SQLite and raw-file traces.

The runtime is Pi-only for this product. Claude Code is not an agent harness and is never required to install or run the factory. The runtime must not contain a Claude Code execution adapter. The `/sssf` skill is an optional operator frontend that can route commands to the same CLI and Justfile interfaces available from a terminal or Pi.

### Installation and project tooling

The current installer remains the source of truth for stamping a project. It will eventually be exposed through a generic CLI, while preserving its current behavior:

- execute from the target project root;
- stamp `adws/`, prompts, config, environment examples, and a Justfile;
- skip existing files by default;
- require explicit force/update behavior for overwrites;
- add runtime paths to `.gitignore`.

The target interface is:

```text
uvx sssf init
sssf doctor
sssf update
sssf run ...
```

The canonical packaging direction is Python-native (`uvx`/`pipx`) because the runtime is Python. An `npx` launcher can be considered later, but it is not required for the first implementation.

### Interfaces and integrations

The following are interfaces over the same Pi-based runtime:

- CLI: primary generic installation, execution, and diagnostics interface;
- Justfile: project-local repeatable workflow interface;
- Claude Code skill: optional conversational `/sssf` frontend only;
- visualizer: read-only trace inspection.

A user must be able to install and operate the factory with Pi and a terminal even when Claude Code is not installed. The Claude skill is retained for users who want `/sssf`, but it is neither the installer nor the runtime harness.

## Example branch strategy

The upstream `example` branch is a stamped, real project and will serve three purposes:

1. **baseline** — establish the current behavior before changes;
2. **dogfooding target** — run real Pi workflows through the Justfile and visualizer;
3. **product reference** — observe the experience of a complete factory installation.

It is not the sole automated test fixture because it contains model-dependent behavior and historical run artifacts.

The working layout should be conceptually:

```text
super-simple-software-factory/  # factory source, normally main
sssf-example/                   # separate worktree of upstream/example
```

The example branch should be recorded by source URL and commit SHA in the project documentation so baseline runs are reproducible. It should be synchronized deliberately, not silently treated as an always-moving dependency.

## Factory Lab and test strategy

For this roadmap, the pinned upstream `example` worktree is the Factory Lab. M0 establishes it as the manual, real-Pi target. M1 builds deterministic and automated test coverage around copies of that target; it does not create a second demo application by default. A smaller fixture should only be introduced if the example project proves too large or too model-dependent for a particular test.

The project will use distinct test layers with explicit names and responsibilities.

### Unit tests

These do not invoke Pi. They cover pure or mostly deterministic behavior:

- configuration loading and validation;
- Pydantic data types;
- gates;
- path matching and permission policy;
- SQLite migrations;
- change capture helpers;
- prompt rendering.

### Control-plane tests

These may use a fake or recorded Pi process. They test the factory's orchestration behavior, not Pi itself:

- phase success and failure;
- malformed-envelope retries;
- gate correction loops;
- permission breaches;
- process cleanup;
- session finalization;
- usage aggregation;
- event and envelope persistence.

A control-plane test must be labeled as such and must never be described as a Pi integration test.

### Real-Pi smoke tests

These invoke the real Pi executable and a real configured provider. They validate:

- executable discovery and command-line flags;
- provider/model resolution;
- authentication;
- JSONL streaming;
- tool-call event parsing;
- session creation and continuation;
- real envelope output;
- real file changes;
- real trace generation.

Real-Pi smoke tests are the integration acceptance gate. They may be opt-in locally and required for release or scheduled verification, but a fake Pi cannot substitute for them.

### Example-project dogfooding

The upstream example worktree is used for human-oriented acceptance:

- run the existing Justfile workflows;
- inspect real traces in the visualizer;
- evaluate prompt and workflow quality;
- assess installation and upgrade ergonomics;
- validate the end-to-end user experience.

## Milestone roadmap

### M0 — Baseline the real example branch

- Fetch the upstream `example` branch into a separate worktree.
- Run its real-Pi workflows.
- Open and inspect the visualizer.
- Record successful paths, confusing paths, and failures.
- Pin the baseline commit in documentation.

Exit criteria: there is a written current-state report and a known reproducible real-Pi example run.

### M1 — Build the regression harness around the Factory Lab

- Keep the pinned example worktree as the manual dogfooding target.
- Create temporary copies or clones from the pinned example commit for clean-install tests.
- Add deterministic control-plane tests using those temporary targets where practical.
- Add a real-Pi smoke command against the example worktree or a clean copy of it.
- Verify Justfile commands and SQLite trace output.
- Ensure tests distinguish fake/recorded Pi from real Pi.
- Introduce a smaller target fixture only when a specific test cannot reasonably use the example project.

Exit criteria: the example project is the documented manual Factory Lab, clean temporary copies can be installed and tested, and a real-Pi smoke path completes against the example-based target.

### M2 — Harden safety and lifecycle behavior

- Replace line-count permission fingerprints with content/state fingerprints.
- Define behavior for ignored-file changes.
- Prevent commit phases from including unrelated pre-existing work.
- Add branch or worktree isolation for suitable workflows.
- Guarantee process cleanup on errors and signals.
- Emit complete agent lifecycle and usage events on failed calls.
- Fix subprocess stream handling so stderr cannot deadlock the agent process.

Exit criteria: unauthorized changes, unrelated changes, failed agents, and interrupted runs are all handled and tested explicitly.

### M3 — Generalize installation and add the CLI

- Extract reusable installation logic from the script entry point.
- Add `sssf init`, preserving current skip-by-default behavior.
- Add version/manifest metadata for stamped files.
- Add dry-run and conflict reporting.
- Add `sssf doctor` for prerequisites, config, model, and runtime checks.
- Add safe update behavior separate from destructive force behavior.
- Keep the generated Justfile unchanged as a supported project-local interface.
- Keep `/sssf install` working as an optional frontend over the same installation layer.
- Ensure direct terminal/Pi installation works without Claude Code being installed.

Exit criteria: a project can be installed and diagnosed through the generic CLI, direct Python entry point, or optional Claude frontend without divergent behavior or a Claude dependency.

### M4 — Improve Pi workflows and extensions

- Make project quality commands explicit and difficult to leave as placeholders.
- Improve workflow composition and acceptance criteria.
- Improve Pi session continuation, extension loading, and tool-boundary diagnostics.
- Add human approval points where they improve safety.
- Keep Claude Code out of the runtime and agent roster.

Exit criteria: workflows are reusable across projects while Pi remains the sole supported agent harness.

### M5 — Redesign the visualizer UX

First stabilize the trace contract, then improve the UI.

The UI should make it easy to answer:

- which runs failed;
- what is running now;
- which phase failed;
- what changed;
- what tests reported;
- what the run cost;
- whether a run can be resumed or inspected safely.

The redesign should cover information architecture before visual polish, then address responsive layout, typography, accessibility, empty/error states, live updates, filters, timeline readability, and tool-call detail.

Use both real example traces and deterministic fixture traces for visual development.

Exit criteria: the visualizer supports live and historical traces with a clear run-to-failure-to-evidence path.

### M6 — Package, document, and release

- Document installation paths and supported integrations.
- Document the real-Pi versus control-plane test boundary.
- Publish a reproducible example workflow.
- Add release/version guidance.
- Validate a clean install into a project that does not contain the factory source.

Exit criteria: a new user can install, run, observe, diagnose, and update the factory without reading its internals first.

## Development rules

1. Change templates and runtime source in the factory repository, not generated files in the example worktree.
2. Use the example worktree for real-Pi dogfooding and UX discovery.
3. Use temporary repositories for deterministic automated tests.
4. Do not call a fake-Pi test an integration test.
5. Keep the Justfile supported throughout the transition.
6. Keep direct Pi/terminal installation independent of Claude Code.
7. Treat `/sssf` as an optional Claude frontend, never as a runtime dependency.
8. Keep Claude Code out of the agent harness and agent roster.
9. Do not redesign the visualizer against an unstable event contract.
10. Complete each milestone with evidence from the appropriate test layer.

## Immediate next action

The first implementation step is M0:

1. fetch the upstream `example` branch;
2. create a separate worktree;
3. inspect its stamped files and current documentation;
4. run the cheapest real-Pi smoke path available;
5. record the baseline before modifying the factory source.

No runtime code should be changed until that baseline is captured.
