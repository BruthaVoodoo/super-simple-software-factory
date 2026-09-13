"""sssf doctor — bounded, credential-free environment checks.

Doctor verifies resolvability and file EXISTENCE only. Credential VALIDITY is
proven only by a real run (`just smoke-real-pi`); doctor never opens auth
files and prints at most a first line of any subprocess output.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import manifest


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    detail: str


def _which(program: str) -> str | None:
    return shutil.which(program)


def _resolve_pi() -> str | None:
    """PI_PATH (even bare) or PATH, resolved to an existing executable."""
    candidates = [os.environ["PI_PATH"]] if os.environ.get("PI_PATH") else ["pi"]
    for candidate in candidates:
        if os.sep in candidate or (os.altsep and os.altsep in candidate):
            if Path(candidate).is_file():
                return candidate
        else:
            found = _which(candidate)
            if found:
                return found
    return None


def _run_pi(args: list[str]) -> tuple[int, str]:
    """Every pi subprocess goes through here (tests patch this seam)."""
    pi = _resolve_pi() or "pi"
    result = subprocess.run([pi, *args], capture_output=True, text=True,
                            timeout=10)
    return result.returncode, result.stdout


def _run_tool(argv: list[str]) -> tuple[int, str]:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=10)
    first = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode, first[0] if first else ""


def _count(value: str) -> int | None:
    """Parse pi's compact counts (1M, 128K) — mirrors agent_pi._count."""
    suffixes = {"K": 1_000, "M": 1_000_000}
    suffix = value[-1:].upper()
    if suffix in suffixes:
        try:
            return int(float(value[:-1]) * suffixes[suffix])
        except ValueError:
            return None
    try:
        return int(value)
    except ValueError:
        return None


def _parse_catalog(text: str) -> list[tuple[str, str, int | None]]:
    rows: list[tuple[str, str, int | None]] = []
    for line in text.splitlines()[1:]:
        columns = line.split()
        if len(columns) < 3:
            continue
        rows.append((columns[0], columns[1], _count(columns[2])))
    return rows


def _resolve_models(target: Path, config: str | None,
                    catalog: list[tuple[str, str, int | None]]) -> list[Check]:
    """Resolve each roster model against the SAME catalog rows doctor fetched.

    The stamped target's adw_modules is imported with dotenv suppressed (the
    same technique the test bootstrap uses) — doctor runs in the CLI env.
    """
    from unittest import mock
    sys.path.insert(0, str(Path(target) / "adws"))
    try:
        try:
            with mock.patch("dotenv.load_dotenv", return_value=False):
                from adw_modules import agent_pi, agents as target_agents
        except Exception as error:            # not stamped / unreadable roster
            return [Check("models", False,
                          f"could not load the stamped roster: {str(error)[:120]}")]
    finally:
        sys.path.pop(0)
    cfg = target_agents.load_config(
        config or "adws/adw_sssf_config/sssf.config.yaml")
    checks: list[Check] = []
    with mock.patch.object(agent_pi, "_pi_catalog", return_value=catalog):
        for agent in cfg.agents:
            try:
                provider, model_id = agent_pi.resolve_model(agent.model)
                checks.append(Check(
                    "models", True,
                    f"{agent.name}: {provider}/{model_id}"))
            except ValueError as error:
                checks.append(Check("models", False, str(error)[:200]))
    return checks


def run_checks(target: Path, config: str | None = None) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check(
        "python", sys.version_info >= (3, 11),
        f"python {platform.python_version()}"))

    for tool in ("uv", "just", "git"):
        found = _which(tool)
        if not found:
            checks.append(Check(tool, False, f"{tool} not on PATH"))
            continue
        code, first_line = _run_tool([found, "--version"])
        checks.append(Check(tool, code == 0, first_line[:80]))

    # git: present, and the target is a repo with at least one commit
    git_dir = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--git-dir"],
        capture_output=True, text=True, timeout=10)
    if git_dir.returncode != 0:
        checks.append(Check("git", False, f"{target} is not a git repository"))
    else:
        head = subprocess.run(["git", "-C", str(target), "rev-parse", "HEAD"],
                              capture_output=True, text=True, timeout=10)
        checks.append(Check("git", head.returncode == 0,
                            "repo with a commit" if head.returncode == 0
                            else "repo has no commits yet"))

    pi_path = _resolve_pi()
    rows: list[tuple[str, str, int | None]] = []
    if not pi_path:
        checks.append(Check("pi", False, "no pi on PI_PATH or PATH"))
        checks.append(Check("catalog", False, "skipped: pi not found"))
        checks.append(Check("models", False, "skipped: pi not found"))
    else:
        code, out = _run_pi(["--version"])
        checks.append(Check("pi", code == 0,
                            (out.strip().splitlines() or ["?"])[0][:80]
                            if code == 0 else f"pi --version exited {code}"))
        code, listing = _run_pi(["--list-models"])
        rows = _parse_catalog(listing) if code == 0 else []
        checks.append(Check("catalog", code == 0 and len(rows) >= 1,
                            f"{len(rows)} model(s) listed"
                            if code == 0 else f"--list-models exited {code}"))
        if rows:
            checks.extend(_resolve_models(target, config, rows))
        else:
            checks.append(Check("models", False, "skipped: catalog unavailable"))

    state = manifest.load(Path(target))
    if state is not None:
        checks.append(Check("factory", True,
                            f"stamped by sssf {state.version}, "
                            f"{len(state.entries)} file(s)"))
    elif (Path(target) / "adws/adw_prompt.py").is_file():
        checks.append(Check(
            "factory", True,
            "stamped by the direct installer — run `sssf init` to get "
            "update support"))
    else:
        checks.append(Check("factory", False, "factory not stamped here"))
    return checks
