"""Readonly trace inspection and roster listing. No sessions, no agents, no Pi.

Every DB connection opens in readonly mode and issues zero writes; a missing
db is an error, never an empty database silently created in its place.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import yaml

_VIEW_SQL = {
    "sessions": (
        "SELECT adw_id, status, substr(request, 1, 60) AS request, "
        "total_tokens, total_cost FROM sessions ORDER BY started_at DESC LIMIT 10"
    ),
    "phases": (
        "SELECT seq, name, kind, owner, status, attempt FROM phases "
        "WHERE adw_id = :adw_id ORDER BY seq"
    ),
    "tail": (
        "SELECT started_at, type, name FROM events "
        "WHERE adw_id = :adw_id ORDER BY rowid DESC LIMIT 25"
    ),
    "procs": (
        "SELECT kind, name, pid, command, started_at FROM processes "
        "WHERE adw_id = :adw_id AND ended_at IS NULL ORDER BY id"
    ),
}


def _readonly_connection(db_path: Path) -> sqlite3.Connection:
    """Open the trace db strictly readonly; a missing db is an error."""
    if not db_path.is_file():
        raise FileNotFoundError(f"trace db not found: {db_path}")
    uri = db_path.resolve().as_uri() + "?mode=ro"
    connection = sqlite3.connect(uri, uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def _config_db_path(config_path: str) -> Path:
    """Resolve the observability db path the way every ADW does: relative
    paths are relative to the process cwd — the target repo root when run
    through the justfile recipes."""
    raw = yaml.safe_load(Path(config_path).read_text()) or {}
    db = (raw.get("observability") or {}).get("db") or "adws/adw_data/sssf.db"
    db_path = Path(db)
    return db_path if db_path.is_absolute() else Path.cwd() / db_path


def query_view(config_path: str, view: str, adw_id: str | None) -> list[dict]:
    """Run one readonly inspection query with bound parameters."""
    if view not in _VIEW_SQL:
        raise ValueError(f"unknown view {view!r}")
    if view in ("phases", "tail", "procs") and not adw_id:
        raise ValueError(f"view {view!r} requires an adw_id")
    db_path = _config_db_path(config_path)
    connection = _readonly_connection(db_path)
    try:
        parameters = {"adw_id": adw_id}
        rows = connection.execute(_VIEW_SQL[view], parameters).fetchall()
        changes = connection.total_changes
        if changes:
            raise RuntimeError(f"readonly connection reported {changes} writes")
    finally:
        connection.close()
    return [dict(row) for row in rows]


def rosters(directory: Path) -> list[dict]:
    """List every roster in a config directory with effective agent models.

    Uses plain YAML loading — no agent validation, no Pi catalog call, no
    credentials. A missing file or malformed YAML is an error.
    """
    results = []
    for path in sorted(directory.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text()) or {}
        defaults = raw.get("defaults") or {}
        default_model = defaults.get("model", "")
        agents = []
        for agent in raw.get("agents") or []:
            agents.append({
                "name": agent.get("name", "?"),
                "model": agent.get("model") or default_model,
            })
        results.append({"roster": str(path), "default_model": default_model,
                        "agents": agents})
    return results
