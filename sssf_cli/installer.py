"""Shared installation logic: one stamp/manifest implementation, three doors.

`scripts/install.py` (the direct installer), `sssf init`, and `/sssf install`
all delegate here. The direct installer keeps its exact CLI surface and does
NOT write a manifest (legacy installs are untouched); `sssf init` does.
"""
from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import manifest
from .manifest import ManifestEntry, entry_for, sha256_bytes

# The factory source root: parents of the sssf_cli package.
FACTORY_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = FACTORY_ROOT / ".claude" / "skills" / "sssf" / "templates"

GITIGNORE_ENTRIES = [
    "adws/adw_data/sessions/",
    "adws/adw_data/sssf.db*",
    ".env",
    # The ADWs are Python, so importing adw_modules writes bytecode next to it.
    # Chains that end in a commit phase call git commits, so without this a
    # stamped repo commits its own .pyc files.
    "__pycache__/",
    "*.pyc",
]


@dataclass
class Plan:
    """What one installation pass did (or would do, for a dry run)."""
    stamped: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    gitignore_added: list[str] = field(default_factory=list)


def collect_template_files() -> list[tuple[Path, str]]:
    """Every regular template file with its TARGET-relative destination,
    skipping junk (the same rules the installer has always had)."""
    mappings = [
        (TEMPLATES / "adws", "adws"),
        (TEMPLATES / "prompt_engineering", "adws/adw_data/prompt_engineering"),
        (TEMPLATES / "harness_engineering", "adws/adw_data/harness_engineering"),
    ]
    files: list[tuple[Path, str]] = []
    for source_root, target_root in mappings:
        for source in sorted(source_root.rglob("*")):
            if source.is_dir() or source.name == "__pycache__":
                continue
            if (source.name == ".DS_Store" or source.name.startswith("._")
                    or source.suffix in {".pyc", ".pyo"}):
                continue
            files.append((source, str(Path(target_root) / source.relative_to(source_root))))
    for single, rel in (
        (TEMPLATES / "sssf.config.yaml", "adws/adw_sssf_config/sssf.config.yaml"),
        (TEMPLATES / "env.sample", ".env.sample"),
        (TEMPLATES / "justfile", "justfile"),
    ):
        files.append((single, rel))
    return [(source, rel) for source, rel in files if source.is_file()]


def plan(target: Path, force: bool = False) -> Plan:
    """Classify what an installation pass WOULD do. No writes."""
    plan_result = Plan()
    for source, relative in collect_template_files():
        destination = target / relative
        if destination.exists() and not force:
            plan_result.skipped.append(relative)
        else:
            plan_result.stamped.append(relative)
    gitignore = target / ".gitignore"
    existing = gitignore.read_text().splitlines() if gitignore.exists() else []
    plan_result.gitignore_added = [e for e in GITIGNORE_ENTRIES if e not in existing]
    return plan_result


def apply(target: Path, force: bool = False,
          write_manifest: bool = True) -> Plan:
    """Stamp the factory templates into target; optionally write the manifest.

    Stamped files record BOTH hashes in the manifest: the template bytes they
    came from (source) and the bytes as stamped (target). Everything stamped
    is user's-to-edit afterward — the manifest records, it does not protect.
    """
    plan_result = Plan()
    entries: dict[str, ManifestEntry] = {}
    for source, relative in collect_template_files():
        destination = target / relative
        if destination.exists() and not force:
            plan_result.skipped.append(relative)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        template_bytes = source.read_bytes()
        shutil.copy2(source, destination)
        plan_result.stamped.append(relative)
        entries[relative] = ManifestEntry(source_hash=sha256_bytes(template_bytes),
                                          target_hash=sha256_bytes(
                                              destination.read_bytes()))

    gitignore = target / ".gitignore"
    existing = gitignore.read_text().splitlines() if gitignore.exists() else []
    missing = [e for e in GITIGNORE_ENTRIES if e not in existing]
    if missing:
        with gitignore.open("a") as f:
            f.write("\n# sssf runtime\n" + "\n".join(missing) + "\n")
        plan_result.gitignore_added = [f".gitignore (+{len(missing)} entries)"]

    if write_manifest:
        manifest_path = target / manifest.MANIFEST_DIR / manifest.MANIFEST_NAME
        if manifest_path.is_file():
            # Preserve original stamps: an update/re-init must not silently
            # re-baseline hashes for files it did NOT touch this pass.
            previous = manifest.load(target)
            if previous:
                for relative, entry in previous.entries.items():
                    entries.setdefault(relative, entry)
        manifest.write(target, entries)

    return plan_result


@dataclass
class UpdatePlan:
    """Classification of one update pass. Conflicts are the operator's voice:
    user-modified files whose template also changed."""
    updates: list[str] = field(default_factory=list)   # template changed, target untouched
    conflicts: list[str] = field(default_factory=list) # template changed AND user-modified
    adds: list[str] = field(default_factory=list)      # new in templates, absent in target
    orphans: list[str] = field(default_factory=list)   # stamped once, template removed
    skips: list[str] = field(default_factory=list)     # template unchanged


def plan_update(target: Path) -> UpdatePlan:
    """Classify the target against the manifest and the CURRENT templates."""
    from . import __version__
    state = manifest.load(target)
    if state is None:
        import sys
        print("sssf: not stamped — run `sssf init` first", file=sys.stderr)
        raise SystemExit(2)
    plan_result = UpdatePlan()
    seen: set[str] = set()
    for source, relative in collect_template_files():
        if relative == manifest.MANIFEST_DIR + "/" + manifest.MANIFEST_NAME:
            continue
        seen.add(relative)
        destination = target / relative
        template_hash = sha256_bytes(source.read_bytes())
        entry = state.entries.get(relative)
        if entry is None:
            plan_result.adds.append(relative)
        elif entry.source_hash == template_hash:
            plan_result.skips.append(relative)
        elif destination.is_file() and \
                sha256_bytes(destination.read_bytes()) == entry.target_hash:
            plan_result.updates.append(relative)   # user untouched → safe
        else:
            plan_result.conflicts.append(relative)  # user-modified → report
    for relative in state.entries:
        if relative not in seen:
            plan_result.orphans.append(relative)
    return plan_result


def apply_update(target: Path, force: bool = False) -> UpdatePlan:
    """Apply the safe subset of plan_update; --force overwrites conflicts too.
    App files, user files, and orphans are never touched by classification."""
    plan_result = plan_update(target)
    if plan_result.conflicts and not force:
        return plan_result                    # nothing written on conflicts
    state = manifest.load(target)
    entries = dict(state.entries)
    for source, relative in collect_template_files():
        if relative in plan_result.updates or relative in plan_result.adds \
                or (force and relative in plan_result.conflicts):
            destination = target / relative
            template_bytes = source.read_bytes()
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            entries[relative] = ManifestEntry(
                source_hash=sha256_bytes(template_bytes),
                target_hash=sha256_bytes(destination.read_bytes()))
    manifest.write(target, entries)
    return plan_result


def print_update(plan_result: UpdatePlan) -> None:
    if plan_result.updates:
        print(f"  update (template changed, target untouched): {len(plan_result.updates)}")
        for relative in plan_result.updates:
            print(f"    U {relative}")
    if plan_result.adds:
        print(f"  add (new in templates): {len(plan_result.adds)}")
        for relative in plan_result.adds:
            print(f"    A {relative}")
    if plan_result.conflicts:
        print(f"  CONFLICT (template changed AND you edited it — pass --force "
              f"to overwrite): {len(plan_result.conflicts)}")
        for relative in plan_result.conflicts:
            print(f"    C {relative}")
    if plan_result.orphans:
        print(f"  orphaned (template removed, file kept): {len(plan_result.orphans)}")
        for relative in plan_result.orphans:
            print(f"    O {relative}")
    print(f"  up to date: {len(plan_result.skips)}")


def print_plan(plan_result: Plan, *, target: Path) -> None:
    print(f"sssf installed into {target}")
    print(f"  stamped: {len(plan_result.stamped)} file(s)")
    for relative in plan_result.stamped:
        print(f"    + {relative}")
    if plan_result.skipped:
        print(f"  skipped (already exist, use --force to overwrite): "
              f"{len(plan_result.skipped)}")
    for entry in plan_result.gitignore_added:
        print(f"    + {entry}")
