"""Credential-free child environments and offline guards.

The guards prevent accidental provider calls from offline test lanes. They
are tripwires inside the test process, not an operating-system sandbox.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
import tempfile
from pathlib import Path

# Programs an offline lane may launch. Anything else fails loudly — unless
# it does not exist on PATH at all, in which case the OS itself will refuse
# (quality blocks must be able to exercise the missing-binary exit-127 path).
_ALLOWED_PROGRAMS = {
    "python", "python3", "sh", "bash", "git", "just", "uv", "sleep",
    "pi-double.py", "argv-recorder.py",
}


def child_env(home: Path) -> dict[str, str]:
    """Build a minimal, credential-free environment for child processes.

    Copies only PATH and platform temp/system variables — never API keys,
    proxies, Git overrides, or the operator's pi configuration. Points HOME,
    XDG dirs, and pi's config dir at scratch paths so a stray subprocess
    cannot reach real credentials.
    """
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    for key in ("TMPDIR", "TEMP", "TMP", "SYSTEMROOT", "SYSTEMDRIVE",
                "COMSPEC", "PATHEXT"):
        if key in os.environ:
            env[key] = os.environ[key]
    home.mkdir(parents=True, exist_ok=True)
    env["HOME"] = str(home)
    env["XDG_CONFIG_HOME"] = str(home / ".config")
    env["XDG_CACHE_HOME"] = str(home / ".cache")
    env["XDG_DATA_HOME"] = str(home / ".local" / "share")
    env["PI_CODING_AGENT_DIR"] = str(home / ".pi" / "agent")
    env["ENGINEER_NAME"] = "sssf-test"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("LC_ALL", "en_US.UTF-8")
    env.setdefault("LANG", "en_US.UTF-8")
    return env


def install_offline_guards(lane: str) -> None:
    """Block network access and unexpected subprocess programs in-process.

    Installed once per checks.py run. Tests that intentionally exercise a
    protocol boundary patch the boundary itself (e.g. agent_pi.PI_PATH);
    the guard only catches accidents.
    """
    if getattr(install_offline_guards, "_installed", False):
        return
    install_offline_guards._installed = True

    def _no_network(*_args, **_kwargs):
        raise AssertionError(
            f"lane '{lane}' is offline — network use is a test bug, "
            "not something to wait out")

    socket.create_connection = _no_network
    socket.socket.connect = _no_network            # type: ignore[method-assign]

    original_popen = subprocess.Popen.__init__

    def guarded_popen(self, args, *rest, **kwargs):  # noqa: ANN001
        argv = args if isinstance(args, (list, tuple)) else str(args).split()
        name = Path(str(argv[0])).name
        if name not in _ALLOWED_PROGRAMS \
                and not str(argv[0]).startswith(tempfile.gettempdir()) \
                and shutil.which(str(argv[0])) is not None:
            raise AssertionError(
                f"offline lane '{lane}' tried to run {argv[0]!r} — patch the "
                "protocol boundary explicitly if this is intentional")
        return original_popen(self, args, *rest, **kwargs)

    subprocess.Popen.__init__ = guarded_popen      # type: ignore[method-assign]
