# M5 acceptance — measured evidence

Title: **M5 accepted** — the visualizer answers all eight session-detail
questions against both fixture and real traces, validated live. Report
written 2026-09-13 at execution time; all numbers measured.

## Environment

| Fact | Value |
|---|---|
| Factory commit | branch `feat/m5-visualizer-ux` (worktree `.worktrees/m5`), based on `main` @ `eaed0e6` |
| sssf CLI | 0.1.0 · Pi 0.85.1 · uv 0.12.10 · Just 1.58.0 · Python (test env) 3.11.15 |
| Visualizer | bun 1.4.0, vue-tsc clean, oxlint: 1 pre-existing warning (models.ts, untouched) |
| Pinned example SHA | `b2dcb8e436db9b10f7580d7568b3e251609eb36b` (unchanged) |

## Offline lanes (run twice, zero skips, zero expected failures)

| Lane | Result |
|---|---|
| `just test-unit` | ran=131 failures=0 errors=0 skipped=0 |
| `just test-install` | ran=37 failures=0 errors=0 skipped=0 |
| `just test-control-plane` | ran=52 failures=0 errors=0 skipped=0 |
| `git diff --check` | clean |

## The eight questions — walkthrough (fixture + real trace)

Validated live: `bun run server/index.ts --db <trace>` + the API surfaces the
UI renders (component wiring inspected against the same shapes).

| Question | Where the answer lives | Fixture | Real trace |
|---|---|---|---|
| 1. Run status | `StatusChip` + `not_accepted` as its own state (fail + `not_accepted` event) | all five shapes served with correct statuses (success/fail/running) | 2 M0-era sessions, `success` |
| 2. Failing phase | failed phase auto-selected on load; waterfall rows | `fixture-gate-fail` → `build` phase `fail` with error text | n/a (no failed runs in the example trace) |
| 3. Failure cause | phase `error` bar + `RepairSummary` section (sends/attempts/violations) + invalid envelope rows | gate fixture: error + repair_summary served | n/a |
| 4. What changed | `ChangedFiles` section from `paths_touched` + handoff artifacts | generator emits `paths_touched` for the success fixture | M0 sessions carry handoffs |
| 5. Gate evidence | gates grouped by attempt with `checks_json` item/ok/note rows | gate fixture: 1 gate row with checks, passed=0 | n/a |
| 6. Quality results | `QualityEvents` section: command, exit code, artifact | success fixture: `quality:test` + `quality:lint`, exit 0 | n/a |
| 7. Cost | session headline + per-phase `agent_end` breakdown; raw read/written | served: usage read=20 written=4 for the gate fixture | served: M0 usage |
| 8. Next actions | `NextActions` strip: copyable `just tail/procs/kill/phases/--adw-id` commands computed from state; `not_accepted` names the criterion from the event payload | not-accepted fixture: criterion + resume command served | n/a |

Two real defects found and fixed during validation:

1. `just fixture-trace DIR` passed `{DIR}` literally (just needs `{{DIR}}`) — fixed.
2. Regenerating fixtures over an existing db doubled events (phases dedupe by PK; events append) — the generator now starts clean and the determinism test pins event counts.

Also discovered: a cleanly-closed WAL db cannot be opened READONLY by
bun:sqlite (no `-wal` file, no shm creatable). Fixture dbs now convert to
DELETE journaling (static snapshots); real traces carry live WAL files and
open fine. Documented in the generator.

## Source gates

`bun run typecheck` clean; `bun run lint`: 1 pre-existing warning
(`models.ts`, untouched by M5).

## Real-Pi smoke re-run

Command (exactly): `SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi`

| Check | Result |
|---|---|
| ADW ID | `a34ffb12` |
| Exit / duration | 0 / 11.3s |
| Live observation | YES — `evt_09fddfd2567c` while the probe phase was `running` |
| Receipt / envelopes | exact receipt; 2 valid envelopes |
| Recall tool use | 0; no synthetic marker |
| App hashes / tracked tree | unchanged / clean |
| Tokens / cost (reported) | 24022 tokens, $0.00240817 |

## Historical example worktree preservation

`/Volumes/DEV/sssf-example`: HEAD unchanged at the pinned SHA before and
after; the 7 pre-existing untracked files preserved; its trace db read
read-only (no writes).

## Scope

This certifies the M5 checkpoint: navigation from run list to failed phase,
evidence, changed files, and next actions without opening SQLite manually.
It does not certify M6 packaging/release.
