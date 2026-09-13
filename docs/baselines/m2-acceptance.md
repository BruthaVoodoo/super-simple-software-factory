# M2 acceptance — measured evidence

Title: **M2 accepted** — all seven M1-disclosed defects are fixed, covered by
ordinary passing tests, and the real-Pi smoke passes with the M2 changes in
place. Report written 2026-09-13 at execution time; all numbers measured.

## Environment

| Fact | Value |
|---|---|
| Factory commit | branch `feat/m2-safety-lifecycle` (worktree `.worktrees/m2`), based on `main` @ `cc0161c` |
| Pinned example SHA | `b2dcb8e436db9b10f7580d7568b3e251609eb36b` (unchanged) |
| Pi | 0.85.1 · uv 0.12.10 · Just 1.58.0 · Python (test env) 3.11.15 |
| Model / provider | `opencode/gpt-5.6-luna` (operator-approved for smoke runs in M1) |

## Offline lanes (run twice, zero skips, zero expected failures)

| Lane | Result |
|---|---|
| `just test-unit` | ran=108 failures=0 errors=0 skipped=0 |
| `just test-install` | ran=21 failures=0 errors=0 skipped=0 |
| `just test-control-plane` | ran=47 failures=0 errors=0 skipped=0 |
| `git diff --check` | clean |

The known-gaps lane is retired: every disclosed defect is now an ordinary
test. The retired ledger lives in `docs/known-gaps.md`.

## Fixed defects → covering tests

| ID | Covering test |
|---|---|
| M2-PERM-01 | `tests/unit/test_permissions.py::FingerprintTests::test_same_shape_rewrite_of_dirty_file_is_reported` |
| M2-PERM-02 | `tests/unit/test_permissions.py::FingerprintTests::test_untracked_content_change_is_reported` |
| M2-PERM-03 | `tests/unit/test_permissions.py::IgnoredPathTests::test_ignored_file_modification_outside_runtime_is_caught` |
| M2-PERM-04 | `tests/control_plane/test_agents.py::EnforcementOnFailureTests::test_unauthorized_write_before_parse_exhaustion_still_breaches` |
| M2-TRACE-01 | `tests/control_plane/test_agents.py::FailureTraceTests::test_exhausted_corrections_record_agent_end_usage` |
| M2-PROC-01 | `tests/control_plane/test_lifecycle.py::InterruptedChildTerminationTests::test_interrupted_adw_child_actually_terminates` |
| M2-PROC-02 | `tests/control_plane/test_pi_transport.py::StderrFloodTests::test_transport_completes_despite_a_flooded_stderr` |

Additional M2 scope covered by new tests: commit scoping
(`tests/unit/test_git_scope.py` — pre-existing dirty/untracked operator work
is never staged) and branch isolation
(`tests/control_plane/test_lifecycle.py::BranchIsolationTests` — committing
workflows run on `sssf/<adw_id>`, the operator's branch ref never moves).

## Real-Pi smoke re-run

Command (exactly): `SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi`

| Check | Result |
|---|---|
| ADW ID | `4549e423` |
| Exit / duration | 0 / 10.5s |
| Live observation | YES — `evt_e8563d0c5e8b` while the probe phase was `running` |
| Receipt / envelopes | exact receipt; 2 valid envelopes |
| Recall tool use | 0 (trace + raw wire output) |
| Session continuity | single session, no synthetic marker |
| App hashes / tracked tree | unchanged / clean |
| Tokens / cost (reported) | 23826 tokens, $0.0023 |

## Historical example worktree preservation

`/Volumes/DEV/sssf-example`: HEAD unchanged at the pinned SHA before and
after; the 7 pre-existing untracked files preserved.

## Scope

This certifies the M2 checkpoint: pre-existing work preserved, unauthorized
changes detected (tracked, untracked, and ignored), commit scope controlled,
interrupted runs finalized as failed WITH their children terminated, and
failed agent calls leaving complete trace evidence. It does not certify M3
packaging/updates or M5 UI work.
