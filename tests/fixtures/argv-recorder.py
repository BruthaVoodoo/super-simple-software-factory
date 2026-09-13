#!/usr/bin/env python3
"""Test double: record argv as JSON lines; never execute the recorded command.

Requires SSSF_ARGV_RECORD. Optional SSSF_STUB_EXIT sets the exit code
(default 0). Used only by the offline test lanes.
"""
from __future__ import annotations

import json
import os
import sys

record = os.environ.get("SSSF_ARGV_RECORD")
if not record:
    print("argv-recorder: SSSF_ARGV_RECORD is required", file=sys.stderr)
    raise SystemExit(64)

# argv[0] is this recorder's interpreter; the recorded command starts after it.
argv = sys.argv[1:]
if argv and argv[0].endswith("argv-recorder.py"):
    argv = argv[1:]

with open(record, "a") as handle:
    handle.write(json.dumps(argv) + "\n")
raise SystemExit(int(os.environ.get("SSSF_STUB_EXIT", "0")))
