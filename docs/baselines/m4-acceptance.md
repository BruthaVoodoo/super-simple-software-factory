# M4 acceptance — measured evidence

Title: **M4 accepted** — all supported workflows are Pi-only, quality
commands are explicit configuration, repair loops are observable in the
trace, and no runtime path refers to Claude Code. Report written 2026-09-13
at execution time; all numbers measured.

## Environment

| Fact | Value |
|---|---|
| Factory commit | branch `feat/m4-pi-workflows` (worktree `.worktrees/m4`), based on `main` @ `e0131cb` |
| sssf CLI | 0.1.0 |
| Pi | 0.85.1 · uv 0.12.10 · Just 1.58.0 · Python (test env) 3.11.15 |
| Pinned example SHA | `b2dcb8e436db9b10f7580d7568b3e251609eb36b` (unchanged) |

## Offline lanes (run twice, zero skips, zero expected failures)

| Lane | Result |
|---|---|
| `just test-unit` | ran=123 failures=0 errors=0 skipped=0 |
| `just test-install` | ran=37 failures=0 errors=0 skipped=0 |
| `just test-control-plane` | ran=52 failures=0 errors=0 skipped=0 |
| `git diff --check` | clean |

## M4 exit-condition evidence

| Requirement | Evidence |
|---|---|
| All supported workflows use Pi | schema is `Literal["pi"]` in both config models (`test_config.py::test_claude_code_is_rejected_by_the_schema_itself`); `agent_cc.py` deleted; the meta-test (`tests/unit/test_no_claude_code.py`) asserts ZERO `claude` references across every runtime module — passing |
| Quality commands are explicit | `quality:` config section; unconfigured blocks raise `QualityNotConfigured` with guidance (`tests/unit/test_quality.py`); no `_placeholder` exists anywhere in `quality.py` (the meta-test also enforces the file has no fake-command machinery — and the acceptance guard means a workflow cannot pass on an unconfigured block) |
| Repair loops observable | `repair_summary` event persisted on every exit path (success / parse_exhausted / gate_exhausted / status_fail / permission_breach) with sends, JSON attempts, gate attempts, violations (`tests/control_plane/test_agents.py::RepairSummaryTests`) |
| Session continuation diagnostics | `agent_start.session_continued` + queryable `session_continued` event (`SessionContinuationTests`) |
| Extension validation | missing extension rejected at config validation and before launch (`test_missing_extension_path_is_rejected_at_validation`, `test_missing_extension_fails_before_spawn`) |

## Real-Pi smoke re-run

Command (exactly): `SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi`

| Check | Result |
|---|---|
| ADW ID | `674b6fec` |
| Exit / duration | 0 / 10.7s |
| Live observation | YES — `evt_bab59d65b1c3` while the probe phase was `running` |
| Receipt / envelopes | exact receipt; 2 valid envelopes |
| Recall tool use | 0; no synthetic marker |
| App hashes / tracked tree | unchanged / clean |
| Tokens / cost (reported) | 23968 tokens, $0.00235564 |

## Historical example worktree preservation

`/Volumes/DEV/sssf-example`: HEAD unchanged at the pinned SHA before and
after; the 7 pre-existing untracked files preserved.

## Scope

This certifies the M4 checkpoint: explicit quality configuration, observable
repair loops, session-continuation diagnostics, extension validation, and a
Pi-only runtime enforced by tests. It does not certify M5 visualizer work or
M6 packaging/release.
