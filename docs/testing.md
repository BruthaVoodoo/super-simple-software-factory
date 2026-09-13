# Testing SSSF

## One-time setup

```bash
uv sync --locked --group test --python 3.11
git fetch https://github.com/disler/super-simple-software-factory.git example
```

The fetch pins the example commit locally so installation tests can export
the pinned Inkwell application from Git objects; nothing fetches silently.
The test environment locks the existing runtime dependencies (pydantic,
pyyaml, python-dotenv, rich) — there is no separate test framework.

## Commands

| Command | Runs | What it proves | What it cannot prove |
|---|---|---|---|
| `just test-unit` | `tests/unit/` | config/contract/gate/permission/SQLite/trace behavior of the template modules | that a real model or real Pi did anything |
| `just test-install` | `tests/install/` | the real installer against scratch targets and the pinned Inkwell app | safe upgrades to every existing project (M3) |
| `just test-control-plane` | `tests/control_plane/` | run lifecycle, retries, permissions, usage persistence — Pi is a fixture double | Pi authentication or real model behavior |
| `just test` | all three lanes | the full offline certification suite | a real model — run the smoke command for that || `just smoke-real-pi` (dev) | `scripts/smoke-real-pi.py` | the real model executes the smoke probe/recall in a fresh target | UI rendering (M5) or the full SDLC |

## What the ordinary suites guarantee

- Child subprocesses receive a credential-free environment, never the
  operator's: no API keys, proxies, or pi configuration reach test children.
- Offline lanes tripwire network access and unexpected subprocess launches.
  Every lane contains zero skips and zero expected failures; a skip is an
  error, not a pass. The M1-disclosed defects are fixed (see
  `docs/known-gaps.md` for the retired ledger); their tests are ordinary now.

## Fresh install vs re-install vs update

- **Fresh install** (`tests/install/test_install.py`): no target-owned factory
  files exist; the stamped `justfile` equals the canonical template
  byte-for-byte.
- **Re-install** is *not* drift repair: existing user Justfiles, config, and
  prompts remain byte-for-byte unchanged and are reported as skipped. Tests
  demonstrate an old (pinned-example) Justfile stays untouched — it still
  lacks `demo` after a re-install.
- **Manifest-based updates and safe merging are M3 work**, not M1.

## The canonical recipe set

```text
ask build-review build-test default demo document kill obs phases pi
plan plan-build procs prompt rosters scout sdlc sessions simple-sdlc
smoke-real-pi tail
```

This is the pinned example's set minus `cc` and `ipi` (Pi-only factory;
`/sssf` is an optional operator frontend), plus `demo` and `smoke-real-pi`.
Excluded names are asserted explicitly by tests. Details:

- Recipes run in a non-interactive shell (no interactive-zsh profile import).
- Arguments pass through as arrays, quoted; `SSSF_CONFIG` is exported and
  referenced as `"$SSSF_CONFIG"`, never interpolated into shell source.
- Inspection (`sessions`/`phases`/`tail`/`procs`/`rosters`) goes through
  `adws/manage.py`: readonly connections, parameterized queries, deterministic
  JSON. Querying never creates a session or requires a model.
- `kill` refuses to signal anything it cannot tie to this repository and the
  named run; it requires typed confirmation and sends SIGTERM only.
- Root `just test-*` recipes are development commands and are never stamped
  into user projects.

## The sssf CLI (M3)

Run from the factory checkout: `uv run --locked --project <factory> sssf <command>`.

| Command | Does | Guarantees |
|---|---|---|
| `sssf init [--dry-run] [--force]` | stamps the factory + writes `.sssf/manifest.json` | byte-identical to the direct installer, plus the manifest |
| `sssf update [--dry-run] [--force]` | manifest-driven sync | overwrites only files whose bytes still match the manifest's target hash; user-modified files are reported as conflicts (exit 3) and untouched; `--force` overwrites; application files are never touched |
| `sssf doctor [--config PATH]` | python/uv/just/git/pi/catalog/model-resolution/factory checks | credential-FREE: resolvability only, validity is proven only by a real smoke run |
| `sssf install-skill [--target] [--force]` | copies the optional /sssf skill | separate from runtime installation; never required |

The manifest (`.sssf/manifest.json`, committed in the target) records each
stamped file's SOURCE hash (the template bytes at install time) and TARGET
hash (the bytes as stamped). `sssf update` uses both: template changed +
target untouched → update; template changed + target modified → conflict.
The direct Python installer (`uv run <skill>/scripts/install.py`) delegates
to the same code and keeps working, but writes NO manifest — legacy
installs are byte-identical to what they always produced. Run `sssf init` on
such a target to opt into update support.

## The real-Pi smoke command

`SSSF_SMOKE_MODEL=provider/model-id just smoke-real-pi` (development lane)
builds a fresh pinned-Inkwell target, installs the current templates, commits
a smoke-only local roster, and runs the installed
`just smoke-real-pi --probe-file apps/inkwell/README.md` as a supervised
child (owned process group, 180-second bound).

- It requires an explicit model from your real catalog and your real
  authentication. It spends real tokens and can fail; there is no default
  model and no credential inspection.
- It is never run implicitly by `just test`.
- Live-streaming evidence means observing a tool_call while the probe phase
  is still running and the child is alive — recorded as an event id and
  timestamp, never inferred from final row counts.
- The launcher refuses test doubles: `SSSF_TEST_DOUBLE`, the double
  executable path, argv-recorder paths, and the `synthetic_pi` wire marker.
- Raw evidence is preserved under gitignored `test-results/real-pi/`; the
  summary prints only non-secret identifiers, statuses, and reported usage.

## Scope limits

- M2's fixes are covered by ordinary tests; the retired defect ledger is in
  `docs/known-gaps.md`.
- M1 makes no visualizer/UI acceptance claim (M5 owns UI work).
- `.claude/skills/sssf` is the resource location for M1, not a requirement
  for the Claude application.
