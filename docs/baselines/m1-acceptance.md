# M1 acceptance — measured evidence

Title: **M1 accepted** — every checkpoint has its required evidence. Report
written 2026-09-13 at execution time; all numbers are measured, none assumed.

## Environment

| Fact | Value |
|---|---|
| Factory commit | `fb9bf19` (plus the smoke-launcher fix below), branch `feat/m1-regression-harness`, worktree `.worktrees/m1` |
| Pinned example SHA | `b2dcb8e436db9b10f7580d7568b3e251609eb36b` |
| Lockfile hash (sha256/uv.lock) | `1f7ac273bd248787…` |
| Pi | 0.85.1 |
| Python (test env) | 3.11.15 (uv-managed; the machine Python 3.9 was not used) |
| uv | 0.12.10 |
| Just | 1.58.0 |
| Model / provider | `opencode/gpt-5.6-luna` (operator-selected from the real catalog; context window 1.1M confirmed by the run's agent_sessions row) |

## Offline lanes (all zero skips, run twice)

| Lane | Result |
|---|---|
| `just test-unit` | ran=98 failures=0 errors=0 skipped=0 |
| `just test-install` | ran=21 failures=0 errors=0 skipped=0 |
| `just test-control-plane` | ran=40 failures=0 errors=0 skipped=0 |
| `just test-known-gaps` | ran=7 — expected_failures=7 (M2-PERM-01…04, M2-TRACE-01, M2-PROC-01/02), unexpected_successes=0 |
| `git diff --check` | clean |

The known-gap lane is a disclosure, not a pass: those 7 defects are owned by
M2 and documented in `docs/known-gaps.md`.

## Real-Pi acceptance run

Command (exactly):

```bash
SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi
```

| Check | Result |
|---|---|
| ADW ID | `58611d35` (minted by the launcher, passed explicitly) |
| Exit status | 0 |
| Duration | 17.8s (bounded at 180s) |
| Session status | `success` in the target's trace DB |
| Phases | request / probe / recall — all `success` |
| Valid envelopes | 2 of 2 (probe + recall) |
| Receipt | exact contents `SSSF smoke receipt` |
| Probe tool evidence | 2 tool_call events (read + write) observed in the trace |
| Recall tool use | 0 tool_call events; 0 tool events in raw wire output after the saved offset |
| Live observation | YES — event `evt_91eb0bf411d7` observed while the probe phase was `running` and the child was alive (not inferred from final counts) |
| Session continuity | one Pi session `sssf-58611d35-smoke-75a2`; session file on disk contains the full conversation; recall used no tools and never read the saved prompt |
| Synthetic marker | 0 occurrences of `synthetic_pi` in the raw wire output |
| App-file hashes | unchanged (pinned `apps/inkwell/` + `LICENSE` byte-identical after the run) |
| Tracked tree | clean after the run |
| Tokens / cost (reported by Pi) | 23778 tokens, $0.00228721 — actual reported values; zero cost would also have been valid |

Raw evidence: `test-results/real-pi/` (gitignored, local only). Nothing in
this report contains credentials, environment dumps, raw prompts, or provider
error text.

## Historical example worktree preservation

`/Volumes/DEV/sssf-example`: HEAD unchanged at the pinned SHA before and
after; tracked diff empty; the 7 pre-existing untracked files were preserved
(not deleted).

## Scope of this acceptance

This certifies the M1 checkpoint: canonical recipes, fresh/skip-preserving
installation against the pinned Inkwell app, deterministic control-plane
behavior, and a real bounded Pi run with live visibility and context
continuity. It does NOT certify: the M2 safety fixes (disclosed, still
failing), UI rendering (M5), or full SDLC correctness on real work.
