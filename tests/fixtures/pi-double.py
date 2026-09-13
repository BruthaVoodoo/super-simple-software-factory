#!/usr/bin/env python3
"""Offline Pi protocol double — a fixture, not an implementation of Pi.

Speaks exactly the wire surface `adw_modules/agent_pi.py` consumes:
`--list-models`, `-p --mode json`, provider/model, thinking, session-id/
session-dir, system prompt, tools, repeated `-e`, final prompt. Never imports
or shells out to real Pi; has no network client.

Safety gates:
  * requires SSSF_TEST_DOUBLE=1 AND a SSSF_PI_SCENARIO file — else exit 64
  * its session header carries the unmistakable `synthetic_pi` marker, which
    live acceptance (Task 9) rejects
  * scenario writes must resolve beneath the process cwd; anything else exits 71
  * an unexpected send (scenario exhausted) exits 70 — never a default success
  * state/log files live only in the target's ignored
    adws/adw_data/sessions/test-double/ directory
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

CATALOG_HEADER = "provider model context max-out thinking images"
CATALOG_ROW = "fixture fixture-model 32K 4K yes no"

REQUIRED_FLAGS = ("provider", "model", "thinking", "session-id",
                  "session-dir", "system-prompt")


def fail(code: int, message: str) -> None:
    print(f"pi-double: {message}", file=sys.stderr)
    raise SystemExit(code)


def parse_opts(argv: list[str]) -> dict:
    """Accept exactly agent_pi's surface; anything else is a fixture bug."""
    opts: dict = {"extensions": [], "prompt": None}
    saw_p = saw_mode_json = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "-p":
            saw_p = True
        elif arg == "--mode":
            i += 1
            saw_mode_json = argv[i] == "json"
        elif arg in ("--provider", "--model", "--thinking", "--session-id",
                     "--session-dir", "--system-prompt"):
            i += 1
            opts[arg[2:]] = argv[i]
        elif arg == "--tools":
            i += 1
            opts["tools"] = argv[i]
        elif arg == "-e":
            i += 1
            opts["extensions"].append(argv[i])
        elif arg.startswith("--"):
            fail(65, f"unknown flag {arg!r} — the double implements only "
                     "the surface agent_pi sends")
        else:
            opts["prompt"] = arg
        i += 1
    if not (saw_p and saw_mode_json):
        fail(65, "expected `-p --mode json`")
    missing = [flag for flag in REQUIRED_FLAGS if flag not in opts]
    if missing:
        fail(65, f"missing required flags: {missing}")
    if opts["prompt"] is None:
        fail(65, "expected a prompt argument")
    return opts


def take_position(state_dir: Path) -> int:
    """Next scenario index. First use creates the position file exclusively."""
    position = state_dir / "position"
    try:
        fd = os.open(position, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        current = int(position.read_text() or "0")
        position.write_text(str(current + 1))
        return current
    with os.fdopen(fd, "w") as handle:
        handle.write("1")
    return 0


def emit(event: object) -> None:
    """One wire line, flushed immediately — streaming is the contract."""
    if isinstance(event, str):
        print(event, flush=True)
    else:
        print(json.dumps(event, ensure_ascii=False), flush=True)


def wait_for_release(path: Path, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while not path.exists():
        if time.monotonic() > deadline:
            return                       # proceed; the controller decides
        time.sleep(0.05)


def apply_write(record: dict) -> None:
    target = Path.cwd().resolve()
    destination = (target / record["path"]).resolve()
    if destination != target and target not in destination.parents:
        fail(71, f"scenario write escapes the scratch target: "
                 f"{record['path']!r}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(record["text"])


def main() -> int:
    if os.environ.get("SSSF_TEST_DOUBLE") != "1":
        fail(64, "requires SSSF_TEST_DOUBLE=1")
    scenario_path = os.environ.get("SSSF_PI_SCENARIO", "")
    if not scenario_path or not Path(scenario_path).is_file():
        fail(64, "requires SSSF_PI_SCENARIO pointing at a scenario file")

    argv = sys.argv[1:]
    if "--list-models" in argv:
        print(CATALOG_HEADER)
        print(CATALOG_ROW)               # catalog queries never consume a response
        return 0

    opts = parse_opts(argv)
    # agent_pi's layout: <sessions>/<agent>/pi_sessions — the double's own
    # state lives beside the agent dirs, in the ignored sessions tree.
    state_dir = Path(opts["session-dir"]).parent.parent / "test-double"
    state_dir.mkdir(parents=True, exist_ok=True)

    responses = json.loads(Path(scenario_path).read_text()).get("responses", [])
    index = take_position(state_dir)
    if index >= len(responses):
        fail(70, f"unexpected send #{index + 1}: scenario has "
                 f"{len(responses)} response(s)")
    record = responses[index]

    with (state_dir / "requests.jsonl").open("a") as log:
        log.write(json.dumps({
            "response_index": index,
            "argv": argv,
            "prompt": opts["prompt"],
            "session_id": opts["session-id"],
            "session_dir": opts["session-dir"],
        }) + "\n")

    emit({"type": "session", "id": f"synthetic_pi-{opts['session-id']}",
          "sessionId": opts["session-id"], "provider": opts["provider"],
          "model": opts["model"], "thinking": opts["thinking"]})
    for event in record.get("events", []):
        emit(event)
    if record.get("wait_for_release"):
        wait_for_release(Path(record["wait_for_release"]))
    # Writes resolve BEFORE the final assistant message: a refused write means
    # the run is broken, and the refusal must reach agent_pi as a nonzero exit
    # with no assistant text — not a success envelope followed by a silent 71.
    for write in record.get("writes", []):
        apply_write(write)
    text = record.get("text", "")
    message: dict = {"role": "assistant", "stopReason": "end_turn",
                     "content": ([{"type": "text", "text": text}] if text else [])}
    if "usage" in record:
        message["usage"] = record["usage"]
    emit({"type": "message_end", "message": message})
    return record.get("exit_code", 0)


if __name__ == "__main__":
    raise SystemExit(main())
