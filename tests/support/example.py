"""Pinned-example Git export and disposable example-based targets.

Application bytes are read from the pinned commit in the local Git object
store — never from the live example worktree and never from a silent fetch.
Skill resources come from the CURRENT working tree so tests exercise the
templates under development, including files that are not committed yet.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from tests.support.factory import ROOT, SKILL, git, stamp

FIXTURE = ROOT / "tests" / "fixtures" / "example.json"
EXAMPLE = json.loads(FIXTURE.read_text())
COMMIT: str = EXAMPLE["commit"]
APP_PATHS: tuple[str, ...] = tuple(EXAMPLE["application_paths"])

# Directory names never copied from the current skill tree.
EXCLUDED_DIRS = {".git", "node_modules", "__pycache__", "dist", ".vite"}


def _run_git(source: Path, args: list[str]) -> bytes:
    result = subprocess.run(["git", *args], cwd=source, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(
            f"git {' '.join(args)} failed in {source}: {result.stderr.decode().strip()}")
    return result.stdout


def _require_pinned_object(source: Path) -> None:
    """Fail with the one-time preparation command if the pin is unavailable."""
    result = subprocess.run(
        ["git", "cat-file", "-e", f"{COMMIT}^{{commit}}"],
        cwd=source, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise AssertionError(
            f"pinned example commit {COMMIT} not found locally.\n"
            f"one-time preparation:\n"
            f"  git fetch {EXAMPLE['upstream']} example")


def _is_application_path(rel: str) -> bool:
    for allowed in APP_PATHS:
        if rel == allowed.rstrip("/") or rel.startswith(allowed):
            return True
    return False


def _safe_destination(destination: Path, rel: str) -> Path:
    """Resolve the export path and confine it beneath destination."""
    if ".." in Path(rel).parts or Path(rel).is_absolute():
        raise AssertionError(f"refusing traversal path {rel!r}")
    dest = (destination / rel).resolve()
    if dest != destination.resolve() and destination.resolve() not in dest.parents:
        raise AssertionError(f"path escapes destination: {rel!r}")
    return dest


def export_example(source: Path, destination: Path) -> dict[str, str]:
    """Export allowed application blobs from the pinned commit.

    Reads only `git ls-tree`/`git cat-file` objects; user data, ignored files,
    AppleDouble junk, old runtime code and old sessions cannot leak through
    because they are not blobs at that commit. Returns a map of relative
    path -> SHA-256 of the exported bytes.
    """
    if destination.exists() and any(destination.iterdir()):
        raise AssertionError(f"destination {destination} exists and is not empty")
    _require_pinned_object(source)

    exported: dict[str, str] = {}
    listing = _run_git(source, ["ls-tree", "-r", "-z", COMMIT])
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        meta, _, path_bytes = entry.partition(b"\t")
        mode, kind, oid = meta.decode().split()
        rel = path_bytes.decode("utf-8")
        if not _is_application_path(rel):
            continue
        if kind != "blob":
            raise AssertionError(f"refusing non-blob entry ({kind}) for {rel!r}")
        if mode == "120000":
            raise AssertionError(f"refusing to export symlink {rel!r}")
        dest = _safe_destination(destination, rel)
        data = _run_git(source, ["cat-file", "blob", oid])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if mode == "100755":
            dest.chmod(0o755)
        exported[rel] = hashlib.sha256(data).hexdigest()
    return exported


def excluded_name(name: str) -> bool:
    """Junk names never copied out of the current skill tree."""
    return (name in {".DS_Store", "sssf.db"}
            or name.startswith("._")
            or name.endswith((".pyc", ".pyo")))


def _copy_skill_resources(source: Path, destination: Path) -> dict[str, str]:
    """Copy the current skill tree into the target; return source hash manifest."""
    manifest: dict[str, str] = {}
    for path in sorted(source.rglob("*")):
        if any(part in EXCLUDED_DIRS for part in path.relative_to(source).parts):
            continue
        if path.is_symlink():
            raise AssertionError(f"refusing to copy symlink {path}")
        if not path.is_file() or excluded_name(path.name):
            continue
        rel = str(path.relative_to(source))
        data = path.read_bytes()
        dest = destination / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        if path.stat().st_mode & 0o111:
            dest.chmod(0o755)
        manifest[rel] = hashlib.sha256(data).hexdigest()
    return manifest


def _verify_copy(source: Path, destination: Path, manifest: dict[str, str]) -> None:
    """Confirm every copied file matches the source bytes, byte for byte."""
    for rel, expected in manifest.items():
        actual = hashlib.sha256((destination / rel).read_bytes()).hexdigest()
        if actual != expected:
            raise AssertionError(f"copied resource drifted from source: {rel}")


def _init_baseline(target: Path, env: dict[str, str]) -> None:
    """Initialize a scratch repo with a synthetic, local-only identity."""
    git(target, ["init"], env)
    for key, value in (
        ("user.name", "SSSF Test"),
        ("user.email", "sssf@example.invalid"),
        ("commit.gpgsign", "false"),
        ("core.hooksPath", "/dev/null"),
    ):
        git(target, ["config", key, value], env)
    git(target, ["add", "-A"], env)
    git(target, ["commit", "-m", "synthetic sssf test baseline"], env)


def _strip_appledouble(root: Path) -> None:
    """Delete macOS AppleDouble junk this volume generates on file writes.

    The scratch target is ours; the sweep only touches `._*` and `.DS_Store`
    files inside it. Paired with a .gitignore entry so a `git add -A` baseline
    or the tracked-tree acceptance check never trips on regenerated junk.
    """
    for pattern in ("._*", ".DS_Store"):
        for path in root.rglob(pattern):
            if path.is_file():
                path.unlink()


def prepare_example_target(destination: Path, env: dict[str, str]) -> dict[str, str]:
    """Build a disposable Inkwell-based target: pinned app + current factory.

    Exports the pinned application blobs, copies the CURRENT skill resources
    (so `pi` and `obs` work in the target), runs the real installer, then
    initializes and commits a synthetic scratch baseline containing the app
    and the installed files. Returns the PRE-INSTALL application hashes so
    callers can assert the installer never touched application bytes. Git
    setup uses a local synthetic identity with hooks and signing disabled and
    never changes the source checkout.
    """
    if destination.exists() and any(destination.iterdir()):
        raise AssertionError(f"destination {destination} exists and is not empty")
    before = export_example(ROOT, destination)
    manifest = _copy_skill_resources(SKILL, destination / ".claude" / "skills" / "sssf")
    _verify_copy(SKILL, destination / ".claude" / "skills" / "sssf", manifest)
    stamp(destination, env).check_returncode()
    with (destination / ".gitignore").open("a") as gitignore:
        gitignore.write("\n# macOS AppleDouble junk this volume regenerates\n._*\n")
    _strip_appledouble(destination)
    _init_baseline(destination, env)
    return before
