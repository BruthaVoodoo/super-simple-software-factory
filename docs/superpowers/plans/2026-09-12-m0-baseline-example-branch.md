# M0 — Baseline the Upstream Factory Lab — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pin the upstream `example` branch, run its existing real-Pi demo workflow (`just demo`), verify the visualizer reads the resulting trace, and write a reproducible baseline report — without changing any factory runtime code.

**Architecture:** The upstream `example` branch is checked out into a detached worktree outside the factory source checkout. The worktree is used read-only: its tracked files are never modified. Because this machine's pi catalog carries only `lm-studio` and `opencode` providers (not `google`/`openrouter`/`fireworks`/`openai`), a local untracked roster override routes every agent to the authenticated `opencode/gemini-3.6-flash` model, passed to the demo via `SSSF_CONFIG`. All outputs are captured in committed log files and a baseline report in the factory source repo.

**Tech Stack:** git worktrees, pi (real agent harness, v0.85.1), uv, just, sqlite3, bun (visualizer), Bash.

**Spec:** `docs/superpowers/specs/2026-09-12-factory-evolution-design.md` (section 4 "Example branch and Factory Lab", section 5.3 "Real-Pi smoke test", section 6 milestone "M0")

## Global Constraints

- Factory source repo: `/Volumes/DEV/super-simple-software-factory` (branch `main`).
- Factory Lab worktree path (fixed): `/Volumes/DEV/sssf-example`.
- Pinned upstream example commit (fixed for this baseline): `b2dcb8e436db9b10f7580d7568b3e251609eb36b`.
- Upstream URL (fixed): `https://github.com/disler/super-simple-software-factory.git`.
- Never modify a tracked file inside `/Volumes/DEV/sssf-example`. Untracked additions that exist only for the baseline (the local roster override, `.env`) are permitted and must be listed in the baseline report.
- The M0 real-Pi smoke command is exactly: `SSSF_CONFIG=adws/adw_sssf_config/sssf.config.local.yaml just demo` run from `/Volumes/DEV/sssf-example`.
- Never describe a test double as Pi integration evidence. M0 uses real Pi only.
- If a step is blocked by a missing prerequisite, do not silently skip it: record the exact failing command and its output in the baseline report and stop the plan at that task.
- All report and log files are created in the factory source repo under `docs/baselines/` and committed there.
- Conventional Commits; branch `main`; no force pushes.

---

### Task 1: Pin and check out the upstream example worktree

**Files:**
- Create (git-managed, outside repo): `/Volumes/DEV/sssf-example/` — detached worktree at the pinned SHA
- Create: `docs/baselines/` directory in the factory source repo (used from Task 3 onward)

**Interfaces:**
- Consumes: nothing.
- Produces: a worktree at `/Volumes/DEV/sssf-example` checked out at the pinned SHA, containing a stamped factory (`adws/`, `justfile`). Later tasks run commands inside this path.

- [ ] **Step 1: Add the upstream remote if it is missing**

Run from the factory source repo (`/Volumes/DEV/super-simple-software-factory`):

```bash
git remote get-url upstream 2>/dev/null || git remote add upstream https://github.com/disler/super-simple-software-factory.git
git remote -v
```

Expected output includes:

```text
upstream  https://github.com/disler/super-simple-software-factory.git (fetch)
upstream  https://github.com/disler/super-simple-software-factory.git (push)
```

- [ ] **Step 2: Fetch the example branch and verify the pinned SHA exists**

```bash
git fetch upstream example
git cat-file -t b2dcb8e436db9b10f7580d7568b3e251609eb36b
```

Expected: `git cat-file -t` prints `commit`. If it prints anything else or errors, STOP and record the failure — the pinned SHA is missing upstream and the baseline target has moved; escalate to the engineer before continuing.

- [ ] **Step 3: Create the detached worktree at the pinned SHA**

```bash
git worktree add --detach /Volumes/DEV/sssf-example b2dcb8e436db9b10f7580d7568b3e251609eb36b
```

If the worktree already exists, verify instead of recreating:

```bash
git -C /Volumes/DEV/sssf-example rev-parse HEAD
```

Expected: `b2dcb8e436db9b10f7580d7568b3e251609eb36b`. If it prints a different SHA, STOP and ask the engineer — do not move or re-pin an existing worktree without approval.

- [ ] **Step 4: Verify the worktree contains a stamped factory**

```bash
test -f /Volumes/DEV/sssf-example/justfile && echo "justfile: present"
test -f /Volumes/DEV/sssf-example/adws/adw_sssf_config/sssf.config.yaml && echo "config: present"
test -d /Volumes/DEV/sssf-example/adws/adw_modules && echo "adw_modules: present"
git -C /Volumes/DEV/sssf-example status --porcelain | head -5
```

Expected: all three `present` lines, and `git status` shows a clean tree (no modifications). If the worktree is dirty, STOP and record what is dirty before doing anything else.

- [ ] **Step 5: Commit nothing yet — this task produces no files in the source repo**

This task is git-work only. There is nothing to commit in the factory source repo. Verify the working tree is still clean:

```bash
git -C /Volumes/DEV/super-simple-software-factory status --short
```

Expected: no output (or only untracked `._*` AppleDouble files, which should be deleted: `find . -name '._*' -not -path './.git/*' -delete`).

---

### Task 2: Create the local baseline roster override

**Files:**
- Create: `/Volumes/DEV/sssf-example/adws/adw_sssf_config/sssf.config.local.yaml` (untracked — lives in the worktree, listed in the baseline report)
- Test: config loads and validates via the worktree's own runtime

**Interfaces:**
- Consumes: the worktree's `adw_modules.agents.load_config` / `validate` (unchanged factory code).
- Produces: a config file path `adws/adw_sssf_config/sssf.config.local.yaml` relative to the worktree root, referenced by `SSSF_CONFIG` in Tasks 3 and 4. Every agent resolves to `opencode/gemini-3.6-flash`.

- [ ] **Step 1: Read the worktree's starter roster**

Read `/Volumes/DEV/sssf-example/adws/adw_sssf_config/sssf.config.yaml` in full. Note the agent names (`planner`, `builder`, `scout`, `reviewer`, `documenter`), each agent's `prompt_engineering` paths, `writes`, `tools`, and `harness_engineering` entries. The override in Step 2 preserves every field except model/thinking/color-unrelated provider settings.

- [ ] **Step 2: Write the override roster**

Create `/Volumes/DEV/sssf-example/adws/adw_sssf_config/sssf.config.local.yaml` by copying the starter roster and applying exactly these substitutions:

1. Replace every `model:` value (in `defaults` and in every agent) with `opencode/gemini-3.6-flash`.
2. Replace every `thinking:` value with `medium` (the local model honors reasoning; `medium` is the cheapest useful level for a smoke run).
3. Leave `coding_agent`, `tools`, `writes`, `protected_files`, `data_dir`, `observability`, `purpose`, and `prompt_engineering` paths exactly as they are in the starter roster.

Use the worktree's own modules to derive the file rather than hand-copying, so nothing drifts:

```bash
cd /Volumes/DEV/sssf-example && uv run --with pydantic --with pyyaml --with python-dotenv --with rich python3 - <<'PY'
from pathlib import Path
import yaml

src = Path("adws/adw_sssf_config/sssf.config.yaml")
raw = yaml.safe_load(src.read_text())

def retune(scope):
    if not isinstance(scope, dict):
        return
    if "model" in scope:
        scope["model"] = "opencode/gemini-3.6-flash"
    if "thinking" in scope:
        scope["thinking"] = "medium"

retune(raw.get("defaults", {}))
for agent in raw.get("agents", []):
    retune(agent)

out = Path("adws/adw_sssf_config/sssf.config.local.yaml")
out.write_text(yaml.safe_dump(raw, sort_keys=False))
print(f"wrote {out}")
PY
```

Expected: `wrote adws/adw_sssf_config/sssf.config.local.yaml`.

- [ ] **Step 3: Verify the override loads and every agent validates against the local pi catalog**

```bash
cd /Volumes/DEV/sssf-example && uv run --with pydantic --with pyyaml --with python-dotenv --with rich python3 - <<'PY'
import sys
sys.path.insert(0, "adws")
from adw_modules import agents

cfg = agents.load_config("adws/adw_sssf_config/sssf.config.local.yaml")
names = [a.name for a in cfg.agents]
print("agents:", names)
agents.validate(cfg, names)          # resolves every model against `pi --list-models`
print("validate: PASS — every agent resolves to a local pi model")
PY
```

Expected: the agent list prints, then `validate: PASS`. If validation fails with an ambiguity or not-found error, print the catalog with `pi --list-models | rg gemini` and fix the model string in the override file — the model id must be spelled exactly `opencode/gemini-3.6-flash` — then rerun this step.

- [ ] **Step 4: Confirm the worktree is still clean except for the one untracked file**

```bash
git -C /Volumes/DEV/sssf-example status --porcelain
```

Expected: exactly one line — `?? adws/adw_sssf_config/sssf.config.local.yaml`. (The `adws/adw_data/` runtime is gitignored.) If any tracked file shows as modified, STOP and restore it with `git -C /Volumes/DEV/sssf-example checkout -- <path>`, then investigate how it was modified before continuing.

---

### Task 3: Run the real-Pi smoke demo and capture evidence

**Files:**
- Create: `docs/baselines/2026-09-12-example-branch-demo.log` (in the factory source repo — committed raw command output)
- Create at runtime (gitignored, inside the worktree): `adws/adw_data/sssf.db`, `adws/adw_data/sessions/<adw_id>/…`

**Interfaces:**
- Consumes: worktree justfile recipes `demo`, `sessions`, `phases`; the Task 2 override config.
- Produces: two completed read-only ADW sessions in the worktree's `sssf.db`; an `<adw_id>` value recorded in `docs/baselines/demo-adw-id.txt`; the committed demo log.

- [ ] **Step 1: Confirm no provider credentials are needed for the override roster**

The override roster uses only the `opencode` provider, whose key lives in `~/.pi/agent/auth.json` (verified present during plan creation). Confirm pi is authenticated and record the provider list:

```bash
pi --list-models | awk '{print $1}' | sort -u | tee providers-at-baseline.txt
```

Expected: the file contains at least `lm-studio` and `opencode`. If `opencode` is missing, STOP — the smoke run would fail authentication.

- [ ] **Step 2: Run the demo with the override config, capturing everything**

```bash
cd /Volumes/DEV/sssf-example && SSSF_CONFIG=adws/adw_sssf_config/sssf.config.local.yaml just demo 2>&1 | tee /Volumes/DEV/super-simple-software-factory/docs/baselines/2026-09-12-example-branch-demo.log
```

Expected: both recipes run — `adw_prompt` with the scout agent, then `adw_scout` — each printing phase lines and a session banner ending in `success`. The final line of the log includes both run outcomes. If either run fails, keep the log (it is evidence), record the failure in the baseline report, and continue to Step 3 only to capture db state; the M0 exit condition is then not met.

- [ ] **Step 3: Record the ADW IDs and query the trace db**

```bash
cd /Volumes/DEV/sssf-example
sqlite3 adws/adw_data/sssf.db "select adw_id, status, substr(request,1,60), total_tokens, round(total_cost,4) from sessions order by started_at desc limit 5;" | tee /Volumes/DEV/super-simple-software-factory/docs/baselines/demo-adw-id.txt
```

Expected: two rows, both with `status = success` (or the recorded failure states from Step 2). Note the `adw_id` of the `adw_scout` run for the visualizer check in Task 4.

Then verify the phase and event rows exist for one of the runs, substituting the scout run's id for `<adw_id>`:

```bash
sqlite3 adws/adw_data/sssf.db "select seq, name, kind, owner, status from phases where adw_id='<adw_id>' order by seq;"
sqlite3 adws/adw_data/sssf.db "select type, count(*) from events where adw_id='<adw_id>' group by type;"
```

Expected: phases include `request` and `scout`, both `success`; events include `tool_call` rows (the scout reads files). If `tool_call` rows are absent, record that — mid-run streaming is a claim the baseline either confirms or refutes.

- [ ] **Step 4: Copy the log into the factory source repo and commit it**

```bash
cd /Volumes/DEV/super-simple-software-factory
find . -name '._*' -not -path './.git/*' -delete
git add docs/baselines/2026-09-12-example-branch-demo.log docs/baselines/demo-adw-id.txt
git commit -m "docs: capture m0 real-pi demo baseline log"
```

Expected: commit succeeds. The worktree itself stays uncommitted (only the untracked override file exists there).

---

### Task 4: Verify the visualizer reads the baseline trace

**Files:**
- Create: `docs/baselines/2026-09-12-example-branch-visualizer.log` (in the factory source repo — committed)

**Interfaces:**
- Consumes: the worktree's `just obs` recipe, which serves the visualizer from `.claude/skills/sssf/apps/visualizer` against the worktree's `sssf.db`.
- Produces: recorded evidence that the trace API returns the baseline session (or the exact prerequisite failure).

- [ ] **Step 1: Start the visualizer API**

```bash
cd /Volumes/DEV/sssf-example/.claude/skills/sssf/apps/visualizer && bun install && (SSSF_DB=/Volumes/DEV/sssf-example/adws/adw_data/sssf.db bun run server/index.ts > /tmp/sssf-vis.log 2>&1 &) && sleep 3 && curl -sf http://localhost:4600/api/sessions | head -c 2000
```

Expected: `bun install` completes, and `curl` returns JSON containing the baseline `adw_id` values recorded in Task 3. If `curl` fails, print `/tmp/sssf-vis.log`, save it to `docs/baselines/2026-09-12-example-branch-visualizer.log`, and record the failure — this blocks the visualizer portion of M0 but not the real-Pi result.

- [ ] **Step 2: Verify session detail renders server-side**

Substitute the scout run's `adw_id` from Task 3:

```bash
curl -sf "http://localhost:4600/api/sessions/<adw_id>" | head -c 3000 | tee -a /Volumes/DEV/super-simple-software-factory/docs/baselines/2026-09-12-example-branch-visualizer.log
```

Expected: JSON containing `phases` and event data for the run. Append the result to the log file.

- [ ] **Step 3: Stop the visualizer and commit the log**

```bash
pkill -f 'bun run server/index.ts' || true
cd /Volumes/DEV/super-simple-software-factory
find . -name '._*' -not -path './.git/*' -delete
git add docs/baselines/2026-09-12-example-branch-visualizer.log
git commit -m "docs: capture m0 visualizer baseline evidence"
```

Expected: commit succeeds. (Opening the UI in a browser is encouraged for the engineer's own eyes but is not the automated check; the API responses are the evidence.)

---

### Task 5: Write and commit the baseline report

**Files:**
- Create: `docs/baselines/2026-09-12-example-branch.md`

**Interfaces:**
- Consumes: the pinned SHA (Task 1), the override roster description (Task 2), demo log and ADW IDs (Task 3), visualizer log (Task 4).
- Produces: the M0 deliverable the spec requires; completing this task with the exit condition met closes M0.

- [ ] **Step 1: Write the report**

Create `docs/baselines/2026-09-12-example-branch.md` with exactly this structure, filling every `<FILLED>` marker from the recorded evidence — copy real values and real output excerpts from the Task 3/Task 4 logs; do not paraphrase failures:

```markdown
# Factory Lab Baseline — upstream example branch

## Pin

- Upstream: https://github.com/disler/super-simple-software-factory.git
- Branch: example
- Pinned commit: b2dcb8e436db9b10f7580d7568b3e251609eb36b
- Worktree: /Volumes/DEV/sssf-example (detached)
- Date: <FILLED — date the demo ran>

## Environment

- pi: 0.85.1
- pi providers: <FILLED — paste providers-at-baseline.txt>
- uv / just / bun / sqlite3 versions: <FILLED — `uv --version; just --version; bun --version; sqlite3 --version`>

## Baseline roster override

The pinned roster names google/openrouter, fireworks, and openai models, none of
which exist in this machine's pi catalog. An untracked override at
`adws/adw_sssf_config/sssf.config.local.yaml` routes every agent to
`opencode/gemini-3.6-flash` (thinking: medium). It is passed via
`SSSF_CONFIG` and is the ONLY untracked file added to the worktree.

## Real-Pi smoke result

- Command: `SSSF_CONFIG=adws/adw_sssf_config/sssf.config.local.yaml just demo`
- Result: <FILLED — success or failure per run, with the adw_ids>
- Evidence: 2026-09-12-example-branch-demo.log, demo-adw-id.txt

### Trace observations

- Phases recorded: <FILLED — paste the phases query output>
- Event types recorded: <FILLED — paste the event-type query output>
- tool_call events present mid-run: <FILLED — yes/no, with counts>

## Visualizer result

- API check: <FILLED — what /api/sessions and /api/sessions/<adw_id> returned>
- Evidence: 2026-09-12-example-branch-visualizer.log

## Friction and failures observed

- <FILLED — list every confusing output, stale doc reference, or failure met
  while executing Tasks 1–4, one bullet each, each with the exact command that
  produced it. If none: "none recorded".>

## Exit condition

`just demo` <FILLED — "completed with real Pi" or "was blocked: <exact
prerequisite>">. Visualizer check <FILLED — "succeeded" / "failed: <reason>">.
```

- [ ] **Step 2: Verify the report has no unfilled markers**

```bash
rg -n '<FILLED' docs/baselines/2026-09-12-example-branch.md && echo 'UNFILLED MARKERS REMAIN — fix before committing' || echo 'report complete'
```

Expected: `report complete`. If markers remain, fill them from the logs before proceeding.

- [ ] **Step 3: Commit the report**

```bash
cd /Volumes/DEV/super-simple-software-factory
find . -name '._*' -not -path './.git/*' -delete
git add docs/baselines/2026-09-12-example-branch.md
git commit -m "docs: write m0 factory lab baseline report"
```

Expected: commit succeeds.

---

## Self-Review

**Spec coverage (spec section → task):**
- Section 4 "record the baseline: upstream URL, SHA, worktree path" → Tasks 1, 5.
- Section 5.3 real-Pi smoke validates executable, flags, model resolution, auth, streaming, envelope parsing, trace generation → Task 3 (`just demo` exercises all of these through two real runs; tool_call event check covers streaming).
- Section 6 M0 actions 1–3 (remote, fetch, worktree) → Task 1. Action 4 (inspect stamped files) → Task 1 Step 4 and Task 2 Step 1. Action 5 (real-Pi run) → Task 3. Action 6 (visualizer) → Task 4. Action 7 (baseline report) → Task 5.
- Section 6 M0 exit condition (reproducible documented run or exact blocked prerequisite) → Task 5 Step 1 report structure.
- "M0 does not change runtime code and does not create a new application" → Global Constraints; no task touches factory source templates.

**Placeholder scan:** The `<FILLED>` markers in the Task 5 report template are intentional fill-from-evidence fields, each tied to a specific earlier task's captured output, and Task 5 Step 2 fails the build if any remain. No other placeholders exist.

**Type/name consistency:** Worktree path, pinned SHA, config override path, `SSSF_CONFIG` value, log filenames, and report filename are identical across all tasks and match the spec.
