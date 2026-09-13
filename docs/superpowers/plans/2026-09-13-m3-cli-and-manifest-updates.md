# M3 — CLI, Manifest Updates, and Generalized Installation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development if a subagent tool is actually available; otherwise use superpowers:executing-plans. Execute sequentially with review between tasks. Steps use checkbox (`- [ ]` syntax for tracking. Do not promise independent subagent review when it did not occur.

**Goal:** Make installation independent of Claude Code: a `sssf` CLI (`init`, `update`, `doctor`, `install-skill`) with a stamped-version manifest and conflict-preserving updates, while the direct Python installer and every Justfile recipe keep working.

**Architecture:** A stdlib-plus-runtime-deps package `sssf_cli/` at the factory root holds one installer module (`installer.py`) that `scripts/install.py`, `sssf init`, and the `/sssf` skill all delegate to. Installation writes a manifest (`.sssf/manifest.json`) recording each template's source hash and each stamped file's target hash. `sssf update` compares the CURRENT factory templates against the manifest: untouched targets update, user-modified targets become reported conflicts that only an explicit `--force` overwrites. `sssf doctor` runs bounded, credential-free environment checks; `sssf install-skill` copies the operator frontend skill separately.

**Tech Stack:** Python 3.11, stdlib + the four existing runtime dependencies (pydantic, pyyaml, python-dotenv, rich), uv (project scripts), unittest harness from M1/M2.

**Spec:** `docs/superpowers/specs/2026-09-12-factory-evolution-design.md`, section "M3 — Generalize installation and add the CLI" (required changes 1–10 and the exit condition).

## Global Constraints

- Pi is the only agent harness; keep terminal/Pi installation independent of Claude Code; `/sssf` is an optional operator frontend, never a runtime dependency.
- Keep Claude Code out of the agent harness and roster.
- "Changes to CLI behavior must not silently change the meaning of existing Justfile recipes." All 21 product recipes stay supported; the root dev recipes stay unstamped.
- The direct Python installer (`uv run <skill>/scripts/install.py`) must keep working throughout the migration (spec change 3).
- Never read credential contents. Doctor checks resolvability and file EXISTENCE only; credential validity is proven only by a real run (the smoke command).
- Test children get `child_env` (credential-free); offline lanes tripwire network and unexpected subprocesses. `uv`/`git`/`just`/`python` remain the only child programs.
- Ordinary lanes: zero skips, zero expected failures. No `git add -A` in the source checkout (AppleDouble hazard); add explicit paths.
- Scratch targets come from `tests/support/example.py::prepare_example_target` (pinned Inkwell) when a realistic target is needed, or empty `FactoryTestCase` targets otherwise. Never touch the historical example worktree.
- Manifest files are stamped into the TARGET (committed there), never into the factory source.

## Decisions that make this plan executable

### A. CLI packaging

The dev project becomes installable so `uv run --project <factory> sssf …` works from any cwd:

```toml
[project]
name = "sssf-development"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["pydantic>=2,<3", "pyyaml>=6,<7", "python-dotenv>=1,<2", "rich>=13,<15"]

[project.scripts]
sssf = "sssf_cli.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["sssf_cli"]

[tool.uv]
package = true

[dependency-groups]
test = ["pydantic>=2,<3", "pyyaml>=6,<7", "python-dotenv>=1,<2", "rich>=13,<15"]
```

Runtime dependencies move to `[project.dependencies]` because `sssf doctor` imports the stamped target's `adw_modules` (which needs pydantic/dotenv). The `test` group stays for the existing `uv run --locked --group test` flows. `uv lock && uv sync --locked --group test --python 3.11` re-run once. All four commands run without network (`--locked`).

### B. Manifest

`.sssf/manifest.json` in the TARGET, written by every successful init/update:

```json
{
  "sssf_version": "0.1.0",
  "updated_at": "<iso>",
  "files": {
    "adws/adw_prompt.py": {"source": "<sha256 of the template bytes at install time>",
                            "target": "<sha256 of the stamped bytes>"}
  }
}
```

`source` is what the template WAS when stamped; `target` is what the file WAS when stamped. `update` compares both against (a) the current template bytes and (b) the current target bytes. The manifest is a stamped file listed in the manifest itself (hash of the manifest's file records, not of itself — the self-entry records the hash of the `files` object serialized canonically).

### C. Update semantics

For every path in (manifest ∪ current templates):

| Manifest source == current source? | Current target == manifest target? | Action |
|---|---|---|
| unchanged | — | `skip` (up to date) |
| changed | yes (user untouched) | `update` (overwrite) |
| changed | no (user-modified) | `conflict` — report, do not touch; overwritten only by `update --force` |
| new in templates | absent in target | `add` |
| removed from templates | present | `orphaned` — report, never delete |

`init` on an existing target behaves like `update --force` (explicit intent). Dry-run (`--dry-run`) prints the same classification and touches nothing.

### D. Shared installer

`sssf_cli/installer.py` owns: template discovery (relative to the package: `<factory root>/.claude/skills/sssf/templates`), the stamp mappings (identical to today's `scripts/install.py`), gitignore entries, manifest read/write, and the plan/apply/dry-run report. `scripts/install.py` becomes a thin wrapper calling `installer.apply(target, write_manifest=True)` — same CLI surface (`--force`), same output style, exit codes. `sssf init` calls the same `apply`.

### E. Doctor checks (bounded, credential-free)

In order, each check a `(name, ok, detail)` row, overall exit 0 only when all pass:

1. `python` — the running interpreter is ≥ 3.11
2. `uv` — on PATH, runs `uv --version`
3. `just` — on PATH, runs `just --version`
4. `git` — present; cwd is a repo; at least one commit
5. `pi` — `PI_PATH` or PATH; `pi --version` exits 0
6. `catalog` — `pi --list-models` exits 0 and yields ≥ 1 model
7. `models` — every model in the roster (`--config`, default path) resolves via `agent_pi.resolve_model` (imported from the stamped target's `adws/` with dotenv suppressed, same trick as `tests/support/imports.py`)
8. `factory` — a stamped manifest exists (stamped check)

Credential check: doctor verifies resolvability of every model and says explicitly that credential VALIDITY is proven only by a real run (`just smoke-real-pi`); it never opens auth files.

### F. install-skill and /sssf delegation

`sssf install-skill [--target PATH] [--force]` copies the CURRENT skill directory (`.claude/skills/sssf`: SKILL.md, cookbooks/, references/, scripts/, templates/, harness_engineering/, apps/) into `<target>/.claude/skills/sssf/`, excluding `.git`, `__pycache__`, `dist`, `.vite`, `node_modules`, `.DS_Store`, `._*`, bytecode, and `sssf.db*`. It is separate from runtime installation and never required by it. The `/sssf` skill's install cookbook already instructs running `scripts/install.py`; after Task 2 that delegates to the shared installer, so `/sssf install` meets spec change 9 with no behavioral surprise. `cookbooks/install.md` gains one paragraph pointing at `sssf init`/`sssf update` as the CLI alternative.

## File map

| Path | Responsibility |
|---|---|
| `pyproject.toml`, `uv.lock` | Package + entry point + lock refresh (Task 1) |
| `sssf_cli/__init__.py`, `sssf_cli/cli.py` | Argument parsing, command dispatch, exit codes (Task 1) |
| `sssf_cli/installer.py` | Shared stamp/manifest/dry-run logic (Tasks 2–4) |
| `sssf_cli/manifest.py` | Manifest read/write/hash canonicalization (Task 2) |
| `sssf_cli/doctor.py` | Credential-free environment checks (Task 5) |
| `sssf_cli/skill.py` | `install-skill` copy with exclusions (Task 6) |
| `scripts/install.py` | Thin delegation wrapper (Task 2) |
| `.claude/skills/sssf/cookbooks/install.md` | CLI alternative paragraph (Task 6) |
| `tests/unit/test_manifest.py`, `tests/install/test_cli.py`, `tests/install/test_update.py`, `tests/unit/test_doctor.py` | Per-task tests |
| `docs/testing.md`, `docs/baselines/m3-acceptance.md` | Docs + acceptance report (Task 7) |

---

## Task 1: Package the CLI entry point

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (regenerated)
- Create: `sssf_cli/__init__.py`, `sssf_cli/cli.py`
- Test: `tests/install/test_cli.py` (new)

**Interfaces:**
- Produces: `sssf_cli.cli:main()` dispatching `init|update|doctor|install-skill` with `--version`; unknown command → exit 2 with usage; `sssf --version` prints `sssf <x.y.z>`; commands that are not implemented yet exit 2 with `not implemented until a later task` (replaced task-by-task).

- [ ] **Step 1: Write the failing test** in `tests/install/test_cli.py`

```python
"""The sssf CLI entry point, invoked through uv like an operator would."""
from __future__ import annotations

import subprocess
import unittest

from tests.support.environment import child_env
from tests.support.factory import ROOT, FactoryTestCase


def run_cli(*args: str, cwd=None) -> subprocess.CompletedProcess[str]:
    env = child_env(cwd or ROOT / ".scratch-home") if cwd else child_env(ROOT / ".scratch-home")
    return subprocess.run(
        ["uv", "run", "--locked", "--project", str(ROOT), "sssf", *args],
        cwd=cwd or str(ROOT), env=env, capture_output=True, text=True, timeout=60)


class CliEntryPointTests(FactoryTestCase):
    def test_version_prints_and_exits_zero(self):
        result = run_cli("--version")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.strip().startswith("sssf "))

    def test_unknown_command_exits_two_with_usage(self):
        result = run_cli("nonsense")
        self.assertEqual(result.returncode, 2)
        self.assertIn("usage", result.stderr.lower())

    def test_subcommands_exist_in_usage(self):
        result = run_cli("--help")
        for command in ("init", "update", "doctor", "install-skill"):
            self.assertIn(command, result.stdout)
```

- [ ] **Step 2: Run — expect failure** (`sssf` not found / no entry point).

- [ ] **Step 3: Implement.** pyproject per Decision A (keep the existing `[dependency-groups] test` exactly), then:

```python
# sssf_cli/cli.py
"""sssf CLI — install, update, doctor, install-skill. Independent of Claude Code."""
from __future__ import annotations

import argparse
import sys

from . import __version__  # noqa: F401  (set in __init__.py)

COMMANDS = ("init", "update", "doctor", "install-skill")


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"sssf {args.command}: not implemented until a later task", file=sys.stderr)
    return 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sssf")
    parser.add_argument("--version", action="version",
                        version=f"sssf {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in COMMANDS:
        sub.add_parser(name)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return _not_implemented(args)


if __name__ == "__main__":
    sys.exit(main())
```

`sssf_cli/__init__.py`: `__version__ = "0.1.0"`. Then `uv lock && uv sync --locked --group test --python 3.11`.

- [ ] **Step 4: Run — green.** `uv run --locked --project . sssf --version` and `just test-install` (21 + 3 = 24).

- [ ] **Step 5: Commit** — `feat: package the sssf cli entry point`.

---

## Task 2: Shared installer, manifest, and `sssf init`

**Files:**
- Create: `sssf_cli/installer.py`, `sssf_cli/manifest.py`
- Modify: `scripts/install.py`
- Test: `tests/install/test_cli.py` (init tests), `tests/unit/test_manifest.py` (new)

**Interfaces:**
- Produces: `installer.TEMPLATES: Path` (factory templates dir), `installer.apply(target: Path, force: bool = False, write_manifest: bool = True) -> Plan` where `Plan` is a dataclass with `stamped: list[str]`, `skipped: list[str]`, `gitignore_added: list[str]`; `sssf init [--force]` calls it. `scripts/install.py` main() delegates to `apply(cwd, force=args.force, write_manifest=False)` — **the direct installer writes NO manifest** (that stays an `init` behavior so legacy installs are untouched); equivalence between the two paths covers everything else.
- Produces: `manifest.load(target) -> Manifest | None`, `manifest.write(target, entries: dict[str, ManifestEntry])`, `ManifestEntry(source_hash: str, target_hash: str)`, canonical-JSON (`sort_keys`, `separators`) so re-writes are diff-stable.

- [ ] **Step 1: Write failing tests**

In `tests/unit/test_manifest.py`:

```python
"""Manifest read/write and hash canonicalization."""
from __future__ import annotations

import json
import unittest
from hashlib import sha256

from sssf_cli import manifest


class ManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile
        self.target = __import__("pathlib").Path(tempfile.mkdtemp())

    def test_round_trip_is_canonical_and_stable(self):
        entries = {"a.txt": manifest.ManifestEntry(source_hash="s1", target_hash="t1"),
                   "b/c.txt": manifest.ManifestEntry(source_hash="s2", target_hash="t2")}
        manifest.write(self.target, entries)
        first = (self.target / ".sssf" / "manifest.json").read_text()
        manifest.write(self.target, entries)          # identical rewrite
        self.assertEqual(first, (self.target / ".sssf" / "manifest.json").read_text())
        loaded = manifest.load(self.target)
        self.assertEqual(loaded.entries["a.txt"].source_hash, "s1")

    def test_load_returns_none_when_not_stamped(self):
        self.assertIsNone(manifest.load(self.target))

    def test_entry_hashes_match_real_files(self):
        (self.target / "f.txt").write_bytes(b"stamped bytes")
        entry = manifest.entry_for(self.target / "f.txt",
                                   (self.target / "f.txt").read_bytes())
        self.assertEqual(entry.target_hash, sha256(b"stamped bytes").hexdigest())
```

In `tests/install/test_cli.py`:

```python
class InitTests(FactoryTestCase):
    def test_init_stamps_and_writes_the_manifest(self):
        result = run_cli("init", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())
        loaded = manifest.load(self.target)
        self.assertIsNotNone(loaded)
        self.assertIn("justfile", loaded.entries)
        self.assertEqual(loaded.entries["justfile"].target_hash,
                         sha256((TEMPLATE / "justfile").read_bytes()).hexdigest())
        self.assertEqual(loaded.entries["justfile"].source_hash,
                         sha256((TEMPLATE / "justfile").read_bytes()).hexdigest())

    def test_init_matches_the_direct_installer_byte_for_byte(self):
        """Spec: direct installer and sssf init produce equivalent runtime files."""
        direct = self.target / "direct"
        cli = self.target / "cli"
        direct.mkdir(); cli.mkdir()
        stamp(direct, child_env(direct / ".home"))
        run_cli("init", cwd=str(cli))
        for path in ("justfile", "adws/adw_prompt.py",
                     "adws/adw_sssf_config/sssf.config.yaml", ".env.sample"):
            self.assertEqual((direct / path).read_bytes(),
                             (cli / path).read_bytes(), path)
        self.assertTrue((cli / ".sssf" / "manifest.json").is_file())

    def test_direct_installer_still_works_and_writes_no_manifest(self):
        result = stamp(self.target, self.env)          # the M1 helper
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIsNone(manifest.load(self.target))
```

(`stamp` and `TEMPLATE` from `tests.support.factory`; `manifest` importable because `sssf_cli` is on the path inside the test process — add `sys.path.insert(0, str(ROOT))` at module top after bootstrap-style import.)

- [ ] **Step 2: Run — expect failures** (no `sssf_cli`).

- [ ] **Step 3: Implement.**

`sssf_cli/manifest.py`:

```python
"""Stamped-version manifest: source hash + target hash for every stamped file."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_DIR = ".sssf"
MANIFEST_NAME = "manifest.json"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class ManifestEntry:
    source_hash: str
    target_hash: str


@dataclass
class Manifest:
    version: str
    entries: dict[str, ManifestEntry]


def load(target: Path) -> Manifest | None:
    path = target / MANIFEST_DIR / MANIFEST_NAME
    if not path.is_file():
        return None
    raw = json.loads(path.read_text())
    return Manifest(version=raw.get("sssf_version", ""),
                    entries={rel: ManifestEntry(**item)
                             for rel, item in raw.get("files", {}).items()})


def entry_for(path: Path, stamped_bytes: bytes) -> ManifestEntry:
    """Hash the template bytes (source) and the stamped bytes (target)."""
    return ManifestEntry(source_hash=sha256_bytes(stamped_bytes),
                         target_hash=sha256_bytes(path.read_bytes()))


def write(target: Path, entries: dict[str, ManifestEntry],
          version: str | None = None) -> None:
    from . import __version__
    payload = {
        "sssf_version": version or __version__,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": {rel: {"source": e.source_hash, "target": e.target_hash}
                  for rel, e in sorted(entries.items())},
    }
    path = target / MANIFEST_DIR / MANIFEST_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=1) + "\n")
```

`sssf_cli/installer.py`: move `stamp()`, `ensure_gitignore()`, the mapping table, and `GITIGNORE_ENTRIES` verbatim from `scripts/install.py`, refactored into `apply(target, force, write_manifest) -> Plan`. After stamping, when `write_manifest`, build entries via `entry_for` for every stamped file and `manifest.write`. `scripts/install.py` becomes:

```python
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from sssf_cli.installer import apply
    plan = apply(Path.cwd(), force=args.force, write_manifest=False)
    ...same output formatting as today...
    return 0
```

(The dependency header stays; output text stays operator-compatible — "stamped/skipped" lines.)

- [ ] **Step 4: Run — green.** `just test-install` (24 + 3) and `just test-unit`.

- [ ] **Step 5: Commit** — `feat: shared installer with stamped-version manifest and sssf init`.

---

## Task 3: Dry-run for init

**Files:**
- Modify: `sssf_cli/cli.py`, `sssf_cli/installer.py`
- Test: `tests/install/test_cli.py`

**Interfaces:**
- Produces: `installer.plan(target, force) -> Plan` (pure classification, no writes: `stamped` = would-write, `skipped` = would-skip, `gitignore_added` = would-append); `sssf init --dry-run` prints the plan and exits 0 without touching the filesystem.

- [ ] **Step 1: Failing test**

```python
class InitDryRunTests(FactoryTestCase):
    def test_dry_run_reports_writes_and_skips_without_touching_anything(self):
        (self.target / "justfile").write_bytes(b"operator-owned\n")
        before = sorted(str(p.relative_to(self.target))
                        for p in self.target.rglob("*"))
        result = run_cli("init", "--dry-run", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("would write", result.stdout.lower())
        self.assertIn("justfile", result.stdout)          # it's a conflict-skip on dry run of existing
        self.assertIn("would stamp", result.stdout.lower())
        self.assertIsNone(manifest.load(self.target))     # nothing was written
        self.assertEqual(
            sorted(str(p.relative_to(self.target)) for p in self.target.rglob("*")),
            before)
```

- [ ] **Step 2: Run — expect failure** (`init --dry-run` currently stamps for real).

- [ ] **Step 3: Implement** — refactor `apply` into `plan(target, force) -> Plan` + `apply = plan + perform`; CLI: `if args.dry_run: print(plan)`. Add `--dry-run` to the init parser.

- [ ] **Step 4: Run — green**, then **commit** — `feat: dry-run plan for sssf init`.

---

## Task 4: Manifest-driven `sssf update` with conflicts and force

**Files:**
- Modify: `sssf_cli/cli.py`, `sssf_cli/installer.py`
- Test: `tests/install/test_update.py` (new)

**Interfaces:**
- Produces: `installer.plan_update(target) -> UpdatePlan` with `updates: list[str]`, `conflicts: list[str]`, `adds: list[str]`, `orphans: list[str]`, `skips: list[str]`; `sssf update [--dry-run] [--force]` — `--force` overwrites conflicts too. Exit 0 unless a conflict is present and `--force` was not given (exit 3, so scripts can detect "user-modified files need attention").

- [ ] **Step 1: Failing tests** in `tests/install/test_update.py`

```python
"""Manifest-driven update: untouched targets update, user-modified conflict."""
from __future__ import annotations

import unittest

from sssf_cli import manifest as manifest_module
from tests.support.environment import child_env
from tests.support.factory import ROOT, TEMPLATE, FactoryTestCase, stamp, child_env as _ce  # noqa
```

Use the M1 prepared-target helper for realistic targets:

```python
from tests.support.example import prepare_example_target


class UpdateTests(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.before_hashes = prepare_example_target(self.target, self.env)
        # rewrite one template to simulate a new factory version; restored via
        # addCleanup so even a crashing test cannot leave the source modified
        self.template_copy = TEMPLATE / "env.sample"
        self.original = self.template_copy.read_bytes()
        self.template_copy.write_bytes(self.original + b"\n# updated upstream\n")
        self.addCleanup(self.template_copy.write_bytes, self.original)

    def test_untouched_target_updates(self):
        result = run_cli("update", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / ".env.sample").read_bytes(),
                         self.original + b"\n# updated upstream\n")
        self.assertIn("update", result.stdout.lower())

    def test_user_modified_file_conflicts_and_is_untouched(self):
        (self.target / ".env.sample").write_bytes(b"# user's own edits\n")
        result = run_cli("update", cwd=str(self.target))
        self.assertEqual(result.returncode, 3)
        self.assertIn("conflict", result.stdout.lower())
        self.assertIn(".env.sample", result.stdout)
        self.assertEqual((self.target / ".env.sample").read_bytes(),
                         b"# user's own edits\n")
        self.assertIn("user's own edits", (self.target / ".env.sample").read_text())

    def test_force_overwrites_conflicts(self):
        (self.target / ".env.sample").write_bytes(b"# user's own edits\n")
        result = run_cli("update", "--force", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.target / ".env.sample").read_bytes(),
                         self.original + b"\n# updated upstream\n")

    def test_dry_run_classifies_without_writing(self):
        (self.target / ".env.sample").write_bytes(b"# user's own edits\n")
        before = (self.target / ".env.sample").read_bytes()
        result = run_cli("update", "--dry-run", cwd=str(self.target))
        self.assertEqual(result.returncode, 3)       # conflict reported, nothing written
        self.assertEqual((self.target / ".env.sample").read_bytes(), before)
        self.assertEqual((self.target / "justfile").read_bytes(),
                         (TEMPLATE / "justfile").read_bytes())  # unchanged file untouched

    def test_app_files_are_never_touched_by_update(self):
        result = run_cli("update", cwd=str(self.target))
        for path, expected in self.before_hashes.items():
            self.assertEqual(
                sha256((self.target / path).read_bytes()).hexdigest(), expected, path)
```

- [ ] **Step 2: Run — expect failure** (no `update` behavior).

- [ ] **Step 3: Implement** `plan_update` per Decision C: load manifest (absent → error exit 2 "not stamped — run sssf init"), classify each manifest entry + each current template file, apply non-conflicts, re-write the manifest with fresh source/target hashes, print the classification. New-template handling: `adds` stamp through the same mapping logic.

- [ ] **Step 4: Run — green** (`just test-install` and `just test-unit`).

- [ ] **Step 5: Commit** — `feat: manifest-driven update with conflict reporting`.

---

## Task 5: `sssf doctor`

**Files:**
- Create: `sssf_cli/doctor.py`
- Modify: `sssf_cli/cli.py`
- Test: `tests/unit/test_doctor.py` (new)

**Interfaces:**
- Produces: `doctor.run_checks(target: Path, config: str | None = None) -> list[Check]` (`Check = (name, ok, detail)`); `sssf doctor [--config PATH]` prints one line per check and exits 0 only when all pass. Check 7 imports the stamped target's `adw_modules` with dotenv suppressed (the `tests/support/imports.py` technique, replicated in `sssf_cli/doctor.py` — test-support code is never imported by the CLI).

- [ ] **Step 1: Failing tests** in `tests/unit/test_doctor.py`

```python
"""Doctor: bounded, credential-free environment checks (mocked subprocesses)."""
from __future__ import annotations

import unittest
from unittest import mock

from sssf_cli import doctor
from tests.support.runtime import RuntimeTestCase


class DoctorTests(RuntimeTestCase):
    def test_stamped_target_passes_all_checks(self):
        checks = doctor.run_checks(self.target)
        failed = [c for c in checks if not c.ok]
        self.assertEqual(failed, [])
        self.assertEqual([c.name for c in checks],
                         ["python", "uv", "just", "git", "pi", "catalog",
                          "models", "factory"])

    def test_missing_pi_fails_the_pi_check_only(self):
        with mock.patch.dict("os.environ", {"PI_PATH": "/nonexistent/pi-double-missing"}), \
             mock.patch.object(doctor, "_which", return_value=None):
            checks = doctor.run_checks(self.target)
            by_name = {c.name: c for c in checks}
            self.assertFalse(by_name["pi"].ok)
            self.assertFalse(by_name["catalog"].ok)
            self.assertFalse(by_name["models"].ok)
            self.assertTrue(by_name["git"].ok)

    def test_unstamped_target_fails_the_factory_check(self):
        import tempfile, pathlib
        bare = pathlib.Path(tempfile.mkdtemp())
        checks = doctor.run_checks(bare)
        by_name = {c.name: c for c in checks}
        self.assertFalse(by_name["factory"].ok)
```

- [ ] **Step 2: Run — expect failure** (module absent).

- [ ] **Step 3: Implement** per Decision E. `pi --version`/`--list-models` subprocesses get a 10s timeout and report failure text in `detail` (never full provider output — first line only). The `models` check resolves via the target's stamped `adw_modules.agent_pi.resolve_model` with `dotenv.load_dotenv` patched off during import. Credential wording in the final output: `"credentials: not checked — validity is proven only by a real run (just smoke-real-pi)"` as an informational line, never a failure.

- [ ] **Step 4: Run — green.**

- [ ] **Step 5: Commit** — `feat: sssf doctor environment checks`.

---

## Task 6: `sssf install-skill` and /sssf delegation

**Files:**
- Create: `sssf_cli/skill.py`
- Modify: `sssf_cli/cli.py`, `.claude/skills/sssf/cookbooks/install.md`
- Test: `tests/install/test_cli.py`

**Interfaces:**
- Produces: `skill.install(target: Path, force: bool = False) -> SkillPlan(stamped, skipped)` — copies the current skill tree into `<target>/.claude/skills/sssf` with Decision F's exclusions and a symlink/traversal guard; `sssf install-skill [--target PATH] [--force]`.

- [ ] **Step 1: Failing tests** (append to `tests/install/test_cli.py`)

```python
class InstallSkillTests(FactoryTestCase):
    def test_skill_copies_with_exclusions_and_matches_source_bytes(self):
        result = run_cli("install-skill", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        installed = self.target / ".claude" / "skills" / "sssf"
        self.assertTrue((installed / "SKILL.md").is_file())
        source = SKILL / "SKILL.md"
        self.assertEqual((installed / "SKILL.md").read_bytes(), source.read_bytes())
        for path in installed.rglob("*"):
            self.assertFalse(path.name.startswith("._"), path)

    def test_existing_skill_is_skipped_without_force(self):
        installed = self.target / ".claude" / "skills" / "sssf" / "SKILL.md"
        installed.parent.mkdir(parents=True)
        installed.write_bytes(b"operator-owned skill\n")
        result = run_cli("install-skill", cwd=str(self.target))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(installed.read_bytes(), b"operator-owned skill\n")
```

- [ ] **Step 2: Run — expect failure.**

- [ ] **Step 3: Implement** `sssf_cli/skill.py` (exclusions + guards, `--force` overwrites), wire the subcommand, add the cookbook paragraph:

```markdown
## CLI alternative (no Claude Code needed)

`sssf init` stamps the same files as `/sssf install`; `sssf update` applies new
factory versions while protecting your edits (conflicts reported, `--force`
overwrites); `sssf doctor` verifies the environment. Run from the factory
checkout: `uv run --project <factory> sssf init`. `sssf install-skill` copies
this skill for Claude Code users — optional, never required at runtime.
```

- [ ] **Step 4: Run — green.**

- [ ] **Step 5: Commit** — `feat: optional sssf install-skill and cli cookbook`.

---

## Task 7: Docs, full re-verification, real smoke, acceptance report

**Files:**
- Modify: `docs/testing.md`, `.claude/skills/sssf/cookbooks/install.md`
- Create: `docs/baselines/m3-acceptance.md`

- [ ] **Step 1: Extend `docs/testing.md`** with an M3 section: the four commands, the manifest file, update/conflict/force semantics, that the direct installer writes no manifest while `init` does, and the equivalence guarantee.

- [ ] **Step 2: Run every offline lane twice** — `just test` (all lanes green, zero skips), `git diff --check`.

- [ ] **Step 3: Equivalence proof on a fresh pinned-Inkwell target**: `sssf init` and the direct installer produce byte-identical runtime files (the Task 2 test generalizes the claim; run `just test-install` as the recorded evidence).

- [ ] **Step 4: Real smoke re-run** with the operator-approved model:

```bash
SSSF_SMOKE_MODEL=opencode/gpt-5.6-luna just smoke-real-pi
```

Plus one `sssf doctor` run against a prepared target, recorded verbatim (names + ok flags + details) in the report.

- [ ] **Step 5: Write `docs/baselines/m3-acceptance.md`** — same discipline as M1/M2: commits, versions, lane counts, the equivalence proof, doctor output, smoke evidence, historical-worktree preservation.

- [ ] **Step 6: Commit** — `docs: record m3 cli and installation acceptance`.

---

## Execution checkpoints

| Checkpoint | Required evidence | Does not establish |
|---|---|---|
| Tasks 1–2 | `sssf` runs; init/direct-installer equivalence; manifest hashes | Publishing the CLI anywhere (M6) |
| Tasks 3–4 | Dry-run touches nothing; update protects user edits without `--force` | Silent upgrades of arbitrary projects — conflicts are always reported |
| Tasks 5–6 | Doctor passes on a prepared target; skill copy optional and separate | That credentials are valid (only the smoke proves that) |
| Task 7 | All lanes twice green + real smoke PASS + doctor transcript | M4 workflow improvements, M5 UI |

M3 is complete when the spec's exit condition holds: a clean target installs through `sssf init`, the direct installer, or `/sssf install`; all three produce equivalent runtime files; none requires Claude Code; and `just` workflows still run.

## Plan self-review / spec coverage

| Spec M3 requirement | Plan task |
|---|---|
| 1. Extract reusable installation logic | 2 |
| 2. `sssf init` on shared logic | 2 |
| 3. Direct installer keeps working | 2 (delegation + no-manifest compat test) |
| 4. Stamped-version manifest (source + target hashes) | 2 |
| 5. Dry-run writes/skips/conflicts | 3, 4 |
| 6. Update overwrites only manifest-matching targets; conflicts reported; separate force | 4 |
| 7. Doctor: python/uv/Pi/models/credentials/Git/target-root | 5 |
| 8. install-skill optional and separate | 6 |
| 9. `/sssf install` delegates to shared behavior | 2, 6 |
| 10. All Justfile recipes supported | unchanged templates; M1 recipe tests keep guarding |
