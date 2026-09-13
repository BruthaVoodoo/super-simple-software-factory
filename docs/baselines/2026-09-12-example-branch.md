# Factory Lab Baseline — upstream example branch

## Pin

- Upstream: https://github.com/disler/super-simple-software-factory.git
- Branch: example
- Pinned commit: b2dcb8e436db9b10f7580d7568b3e251609eb36b
- Worktree: /Volumes/DEV/sssf-example (detached HEAD)
- Date: 2026-09-13

## Environment

- pi: 0.85.1
- pi providers: see `providers-at-baseline.txt` — `lm-studio` and `opencode` only. There is no `google`, `openrouter`, `fireworks`, or `openai` provider on this machine.
- uv / just / bun / sqlite3: uv (homebrew), just 1.42.0, bun 1.4.0, sqlite3 3.50.4 (versions as installed at baseline time).

## Baseline roster override

The pinned roster names `google/gemini-3.6-flash` (via openrouter), `fireworks/.../kimi-k3`, and `openai/gpt-5.6-*` models, none of which exist in this machine's pi catalog. An untracked override at `adws/adw_sssf_config/sssf.config.local.yaml` routes every agent to `opencode/gemini-3.6-flash` (thinking: medium). It is passed via `SSSF_CONFIG` and is the ONLY untracked file added to the worktree. All other roster fields (tools, writes, prompts, protected_files) are untouched from the pinned starter roster.

## Real-Pi smoke result

- Command: `SSSF_CONFIG=adws/adw_sssf_config/sssf.config.local.yaml just ask scout "reply with a one-line summary of this repo"` followed by `SSSF_CONFIG=adws/adw_sssf_config/sssf.config.local.yaml just scout "list the top-level directories in this repo and what each is for. change nothing."`
- **Ruling:** the plan specified `just demo`, but the pinned example justfile predates that recipe (it exists only in the current template's justfile). The two commands above are the pinned branch's exact equivalent — the same two read-only runs (`adw_prompt --agent scout`, then `adw_scout`) the demo recipe wraps.
- Result: **both runs succeeded with real Pi.**
  - Run 1 (`adw_prompt`, agent scout): adw_id `c2f79587`, status `success`, 2/2 phases, 49,311 tokens, $0.0678, 10.9s.
  - Run 2 (`adw_scout`): adw_id `1a275b77`, status `success`, 2/2 phases, 99,723 tokens, $0.1554, 28.5s. Gate `artifacts_exist` passed (scout_findings.md, 1.8KB).
- Evidence: `2026-09-12-example-branch-demo.log.txt`, `demo-adw-id.txt`

### Trace observations

- Phases recorded (1a275b77): `1|request|engineer|bruthavudu|success`, `2|scout|agent|scout|success`.
- Event types recorded (1a275b77): agent_start 1, agent_end 1, gate_pass 1, handoff 1, log 14, phase_start 2, phase_end 2, **tool_call 11**.
- tool_call events present mid-run: **yes** — 11 for the scout run, streamed live (JSONL tailing works as documented).

## Visualizer result

- API check: `GET /api/sessions` returned 200 with JSON including both baseline runs and historical example-branch runs (e.g. `1157f62f`, an `adw_build_review` run from 2026-09-12). `GET /api/sessions/1a275b77` returned 200 with full session detail: phases, usage (89,391 tokens read / 2,684 written), and per-phase data.
- Evidence: `2026-09-12-example-branch-visualizer.txt`
- Visualizer provenance note: the UI is served from the worktree's `.claude/skills/sssf/apps/visualizer/`, so it renders with the pinned (older) UI code, not the current template's.

## Friction and failures observed

- `just demo` does not exist in the pinned example justfile — the plan had to substitute the two equivalent raw runs (ruling above). The current template's justfile and the example branch's have already drifted apart.
- The pinned starter roster references three providers (`openrouter`, `fireworks`, `openai`) this machine does not have registered in pi; running the pinned roster verbatim fails at `agents.validate()` model resolution. The override roster was required to get any run at all.
- The repo `.gitignore` bans `*.log` (line 139), so baseline logs are committed as `.txt` instead.
- macOS AppleDouble (`._*`) files appear as untracked noise on this mounted volume and had to be deleted repeatedly (worktree and source repo).
- The visualizer's first `bun install` + server startup worked, but the server outlived the shell that launched it; `pkill -f 'bun run server/index.ts'` did not match the actual process (`bun run /full/path/server/index.ts`), and a relaunch failed with EADDRINUSE until the real pid was killed.

## Exit condition

`just demo` equivalent completed with real Pi from the pinned example worktree (both runs `success`). Visualizer check **succeeded** (both API endpoints 200 with real data).

**M0 exit condition: MET.**
