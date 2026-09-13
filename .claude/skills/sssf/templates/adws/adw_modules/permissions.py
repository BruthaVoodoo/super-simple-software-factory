"""What an agent may CHANGE, enforced in code after the fact.

`tools:` is a capability list, not a sandbox, and two holes make it
unenforceable on its own:

  * `bash` runs anything. A builder handed bash to run a test suite can also
    run `git checkout adws/` — which is not hypothetical: one did, discarding
    uncommitted changes to the very quality check it was about to be judged by.
  * `write` reaches any path, not just the one report file an agent was given
    it for. A reviewer configured with "no edit, so it cannot quietly fix"
    could still rewrite the code it was reviewing.

So permission is verified the way every other claim in this system is —
after the fact, against the repo itself. `snapshot()` fingerprints the working
tree's change-set before an agent runs; `enforce()` compares it afterwards and
fails the phase if the agent touched anything outside its allowlist.

Comparing change-sets, rather than watching for writes, is what catches the
`git checkout` case: a path that was modified before the agent ran and is clean
afterwards has been reverted, and a reversion is a modification. Appearing,
disappearing, and changing all count.

A breach is NOT a gate violation. Gates are for work an agent can be asked to
redo; a breach cannot be corrected by re-prompting, because the write already
happened. It aborts the phase and names every offending path.

Two keys drive it, both in sssf.config.yaml:
    defaults.protected_files   paths no agent may touch unless it names them itself
    agents[].writes      None = unrestricted · [] = read-only · [...] = only these
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

from .data_types import AgentConfig, SSSFConfig


class PermissionBreach(RuntimeError):
    """An agent modified a path it was not permitted to modify."""


def _git(args: list[str], cwd) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return result.stdout if result.returncode == 0 else ""

_GREEDY_READ = 1 << 20      # 1 MiB


def _fingerprint(path: Path) -> str:
    """Content fingerprint for one path.

    Files up to 1 MiB hash whole. Larger files hash size + head + tail — an
    approximation that still sees edits at either end and size changes, while
    keeping snapshot cost bounded on big repos. Replaces the M1 numstat
    fingerprint, which could not see same-shape rewrites of dirty files, and
    the name-only marker for untracked files, which could not see their
    content change at all.
    """
    try:
        stat = path.stat()
        with path.open("rb") as handle:
            head = handle.read(_GREEDY_READ)
            if stat.st_size <= _GREEDY_READ:
                digest = hashlib.sha256(head).hexdigest()
            else:
                handle.seek(-_GREEDY_READ, 2)
                tail = handle.read(_GREEDY_READ)
                digest = hashlib.sha256(
                    f"{stat.st_size}:".encode() + head + tail).hexdigest()
        return f"content:{digest}"
    except OSError:
        return "unreadable"


def _others(run, include_ignored: bool) -> list[str]:
    """Untracked paths relative to the repo root; ignored ones too on request."""
    args = ["ls-files", "--others", "-z"]
    if not include_ignored:
        args.append("--exclude-standard")
    return [p for p in _git(args, run.repo_root).split("\0") if p]


def _runtime_prefixes(run) -> list[str]:
    if not hasattr(run, "cfg") or run.cfg is None:
        return []
    return always_writable(run.cfg)


def snapshot(run, save_dir=None) -> dict[str, str]:
    """Fingerprint every path whose state can differ: tracked-dirty,
    untracked, and ignored files OUTSIDE the always-writable runtime dir.

    With `save_dir`, each untracked/ignored file's bytes are mirrored there
    (relative paths preserved) so a later rollback can restore them
    byte-for-byte — Git only knows how to restore tracked files. Call it with
    save_dir for the BEFORE snapshot in agents.execute.
    """
    root = Path(run.repo_root)
    runtime = _runtime_prefixes(run)
    fingerprints: dict[str, str] = {}
    for line in _git(["diff", "HEAD", "--numstat"], run.repo_root).splitlines():
        fields = line.split("\t")
        if len(fields) >= 3:
            path = fields[-1].strip()
            fingerprints[path] = _fingerprint(root / path)
    for relative in _others(run, include_ignored=True):
        path = root / relative
        if any(_matches(relative, prefix) for prefix in runtime):
            continue                      # the runtime is always writable
        if path.is_file() and not path.is_symlink():
            fingerprints[relative] = _fingerprint(path)
            if save_dir is not None:
                destination = save_dir / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)
    return fingerprints


def changed_paths(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Every path whose state differs — appeared, vanished, or was rewritten."""
    return sorted({p for p in set(before) | set(after)
                   if before.get(p) != after.get(p)})


def _glob(pattern: str) -> re.Pattern:
    """Translate a pattern, with `*` stopping at a path separator.

    fnmatch would let `*` cross `/`, which quietly widens every pattern:
    `adws/adw_*.py` would match `adws/adw_data/sessions/x/y.py` as well as the
    ADW scripts it means. `**` is the way to say "cross directories".
    """
    out, i = [], 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    return re.compile("".join(out))


def _matches(path: str, pattern: str) -> bool:
    if pattern.endswith("/"):                      # directory prefix
        return path.startswith(pattern)
    if "*" in pattern or "?" in pattern:
        return _glob(pattern).fullmatch(path) is not None
    return path == pattern


def always_writable(cfg: SSSFConfig) -> list[str]:
    """The session runtime, which EVERY agent must be able to write.

    `context_handoff/` is the one place agents hand work to each other, and an
    agent's own prompts, raw_output.jsonl, and envelope.json land beside it.
    Scout writes its findings there, the reviewer its review, the planner its
    plan — a read-only agent is read-only with respect to the REPO, never with
    respect to its own report.

    This is granted from `data_dir` rather than left to .gitignore. The runtime
    is normally ignored, so it never even appears in a snapshot — but an agent's
    ability to record its work must not hang on a gitignore entry that someone
    can delete or that a changed `data_dir` can outgrow.
    """
    return [cfg.defaults.data_dir.rstrip("/") + "/"]


def permitted(path: str, agent: AgentConfig, cfg: SSSFConfig) -> bool:
    """Session runtime first, then the agent's own list, then what is protected."""
    if any(_matches(path, p) for p in always_writable(cfg)):
        return True
    if any(_matches(path, p) for p in (agent.writes or [])):
        return True                      # naming a path is what unlocks a protected one
    if any(_matches(path, p) for p in cfg.defaults.protected_files):
        return False
    return agent.writes is None          # None = unrestricted, [] = no repo writes


def _roll_back(run, path: str, before: dict[str, str], after: dict[str, str]) -> str:
    """Undo one unauthorized change. Returns a word describing what happened.

    Only changes the agent INTRODUCED are undone. A path that was already dirty
    when the agent started is left exactly as it is: the operator had
    uncommitted work there, and discarding it to tidy up would be the same harm
    this module exists to prevent, committed by the cleanup instead of the agent.

    Untracked and ignored paths (never known to Git) are restored from the
    bytes the BEFORE snapshot saved under the run's permission_state dir —
    the same files could not be recovered any other way.
    """
    if path in before:
        state_dir = Path(run.session_dir) / "permission_state" \
            if hasattr(run, "session_dir") else None
        if state_dir is not None:
            saved = state_dir / path
            if saved.is_file():                      # untracked/ignored: restorable
                destination = Path(run.repo_root) / path
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(saved, destination)
                return "restored"
        # No saved copy: a tracked pre-existing dirty file. If it is gone from
        # the diff now, the agent reverted an engineer's uncommitted work and
        # the content is not ours to reconstruct — say so loudly.
        return "REVERTED-BY-AGENT (uncommitted work lost, cannot restore)" \
            if path not in after else "left as-is (was already modified)"
    if after.get(path) == "untracked":
        try:
            (Path(run.repo_root) / path).unlink()
            return "deleted"
        except OSError as error:
            return f"could not delete ({error})"
    result = subprocess.run(["git", "checkout", "--", path],
                            cwd=run.repo_root, capture_output=True, text=True)
    return "rolled back" if result.returncode == 0 else "could not roll back"


def enforce(run, phase, agent: AgentConfig, before: dict[str, str]) -> list[str]:
    """Compare the tree against `before`; undo and raise if the agent overstepped.

    Returns the paths it legitimately changed, so the trace records what an
    agent actually touched rather than only what it claimed in its envelope.

    Detection alone would leave the repo holding the unauthorized change while
    reporting a failure, so anything the agent introduced outside its allowlist
    is rolled back before the phase dies. What it cannot undo, it names.
    """
    after = snapshot(run)
    touched = changed_paths(before, after)
    breaches = [p for p in touched if not permitted(p, agent, run.cfg)]
    if not breaches:
        return touched

    outcomes = {p: _roll_back(run, p, before, after) for p in breaches}
    scope = ("read-only" if agent.writes == []
             else f"limited to {agent.writes}" if agent.writes
             else f"barred from {run.cfg.defaults.protected_files}")
    detail = "\n".join(f"  - {p} — {outcome}" for p, outcome in outcomes.items())
    raise PermissionBreach(
        f"{agent.name} is {scope} but modified {len(breaches)} path(s):\n{detail}")
