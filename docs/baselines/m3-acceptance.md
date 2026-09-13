# M3 acceptance — measured evidence

Title: **M3 accepted** — a clean target installs through `sssf init`, the
direct installer, or `/sssf install`; all three produce equivalent runtime
files; none requires Claude Code; `just` workflows still run. Report written
2026-09-13 at execution time; all numbers measured.

## Environment

| Fact | Value |
|---|---|
| Factory commit | branch `feat/m3-cli-manifest` (worktree `.worktrees/m3`), based on `main` @ `07415de` |
| sssf CLI | 0.1.0 (uv project script) |
| Pi | 0.85.1 · uv 0.12.10 · Just 1.58.0 · Python (test env) 3.11.15 |
| Pinned example SHA | `b2dcb8e436db9b10f7580d7568b3e251609eb36b` (unchanged) |

## Offline lanes (run twice, zero skips, zero expected failures)

| Lane | Result |
|---|---|
| `just test-unit` | ran=115 failures=0 errors=0 skipped=0 |
| `just test-install` | ran=37 failures=0 errors=0 skipped=0 |
| `just test-control-plane` | ran=47 failures=0 errors=0 skipped=0 |
| `git diff --check` | clean |

## Installation equivalence proof

`tests/install/test_cli.py::InitTests::test_init_matches_the_direct_installer_byte_for_byte`
stamps two fresh targets — one via `uv run <skill>/scripts/install.py`, one
via `sssf init` — and asserts `justfile`, `adws/adw_prompt.py`,
`adws/adw_sssf_config/sssf.config.yaml`, and `.env.sample` are byte-identical
across both, with only the CLI path carrying `.sssf/manifest.json`. The
direct-installer compat test additionally proves the legacy path writes no
manifest. `/sssf install` delegates to the same shared installer by
construction (`scripts/install.py` → `sssf_cli.installer.apply`).

## Update / conflict semantics (measured, not assumed)

`tests/install/test_update.py` on prepared pinned-Inkwell targets:

- template changed + target untouched → updated, exit 0
- template changed + user-modified → **conflict, exit 3, file untouched**
- `--force` overwrites conflicts
- `--dry-run` classifies and writes nothing
- application files byte-identical after `update` (asserted against
  pre-install hashes)
- update on an unstamped target refused (exit 2, "run sssf init")

## Doctor transcript (real prepared target, verbatim)

```
  [PASS] python: python 3.11.15
  [PASS] uv: uv 0.12.10 (Homebrew 2026-09-04 aarch64-apple-darwin)
  [PASS] just: just 1.58.0
  [PASS] git: git version 2.50.1 (Apple Git-155)
  [PASS] git: repo with a commit
  [PASS] pi: 0.85.1
  [PASS] catalog: 74 model(s) listed
  [FAIL] models: model pattern 'fireworks/accounts/fireworks/models/kimi-k3' not found in pi --list-models — authenticate/register it or fix the config
  [FAIL] models: model pattern 'google/gemini-3.6-flash' not found in pi --list-models — authenticate/register it or fix the config
  [FAIL] models: model pattern 'openai/gpt-5.6-terra' not found in pi --list-models — authenticate/register it or fix the config
  [FAIL] models: model pattern 'openai/gpt-5.6-luna' not found in pi --list-models — authenticate/register it or fix the config
  [PASS] factory: stamped by sssf 0.1.0, 50 file(s)
  [info] credentials: not checked — validity is proven only by a real run (just smoke-real-pi)
sssf doctor: 5 check(s) failed
```

The models FAILs are the doctor doing its job, verified against the real
catalog: this machine's `pi --list-models` lists `opencode/gemini-3.6-flash`
and `opencode/gpt-5.6-*` — the starter roster's `google/...` and
`fireworks/...` patterns do not resolve here. That is an environment fact
(consistent with M0's local model override), not a doctor defect. Credential
validity is deliberately not checked by doctor.

## Real-Pi smoke re-run

Command (exactly): `SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi`

| Check | Result |
|---|---|
| ADW ID | `cf0f7a89` |
| Exit / duration | 0 / 10.0s |
| Live observation | YES — `evt_1867b68cea2f` while the probe phase was `running` |
| Receipt / envelopes | exact receipt; 2 valid envelopes |
| Recall tool use | 0; no synthetic marker |
| App hashes / tracked tree | unchanged / clean |
| Tokens / cost (reported) | 23904 tokens, $0.00231036 |

## Historical example worktree preservation

`/Volumes/DEV/sssf-example`: HEAD unchanged at the pinned SHA before and
after; the 7 pre-existing untracked files preserved.

## Scope

This certifies the M3 checkpoint (equivalent installation through three
doors, no Claude Code requirement, Justfile recipes untouched and guarded by
the M1 recipe tests). It does not certify M4 workflow improvements or M5 UI.
