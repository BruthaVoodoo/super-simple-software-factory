"""Operator utility: inspect traces and stop stuck runs — no agents, no sessions.

This is NOT an `adw_*.py` workflow: it never mints a session, never spawns a
coding agent, and never resolves a model catalog. It reads the trace db
readonly and, for `kill`, stops only processes whose identity it can verify.

Usage:
    manage.py --config PATH sessions|rosters
    manage.py --config PATH phases|tail|procs|kill --adw-id ID
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adw_modules import operations, process_control  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True,
                        help="path to sssf.config.yaml (its parent holds rosters)")
    parser.add_argument("view", choices=["sessions", "phases", "tail",
                                         "procs", "rosters", "kill"])
    parser.add_argument("--adw-id", default=None,
                        help="required for phases/tail/procs/kill")
    args = parser.parse_args()

    if args.view in ("phases", "tail", "procs", "kill") and not args.adw_id:
        parser.error(f"{args.view} requires --adw-id")

    config_path = Path(args.config)
    if args.view == "kill":
        return process_control.stop_run(str(config_path), args.adw_id or "")

    if args.view == "rosters":
        rows = operations.rosters(config_path.parent)
    else:
        rows = operations.query_view(str(config_path), args.view, args.adw_id)
    print(json.dumps(rows, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
