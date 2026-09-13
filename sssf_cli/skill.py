"""sssf install-skill — copy the OPTIONAL /sssf operator frontend skill.

Completely separate from runtime installation: a factory works with just the
stamped files; this only serves Claude Code users who want the /sssf skill.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .installer import FACTORY_ROOT

SKILL_ROOT = FACTORY_ROOT / ".claude" / "skills" / "sssf"
EXCLUDED_DIRS = {".git", "__pycache__", "dist", ".vite", "node_modules"}


def _excluded(path: Path) -> bool:
    return (path.name == ".DS_Store" or path.name.startswith("._")
            or path.suffix in {".pyc", ".pyo"} or path.name.startswith("sssf.db"))


@dataclass
class SkillPlan:
    stamped: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def install(target: Path, force: bool = False) -> SkillPlan:
    """Copy the current skill tree into <target>/.claude/skills/sssf.

    Refuses symlinks rather than copying through them, and never writes
    outside the destination. Existing files are skipped unless --force —
    the operator's customized skill is theirs, exactly like stamped files.
    """
    plan = SkillPlan()
    destination_root = Path(target) / ".claude" / "skills" / "sssf"
    for source in sorted(SKILL_ROOT.rglob("*")):
        relative = source.relative_to(SKILL_ROOT)
        if any(part in EXCLUDED_DIRS for part in relative.parts):
            continue
        if source.is_symlink():
            raise SystemExit(f"sssf: refusing to copy symlink {relative}")
        if source.is_dir() or _excluded(source):
            continue
        destination = destination_root / relative
        resolved = destination.resolve()
        if destination_root.resolve() not in resolved.parents and \
                resolved != destination_root.resolve():
            raise SystemExit(f"sssf: path escapes the skill destination: {relative}")
        if destination.exists() and not force:
            plan.skipped.append(str(relative))
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        plan.stamped.append(str(relative))
    return plan
