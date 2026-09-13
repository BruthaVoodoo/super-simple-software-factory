"""M2-TRACE / M2-PROC known-gap reproductions: tracing and process leaks."""
from __future__ import annotations

import os
import signal
import sqlite3
import threading
import time
import unittest
from unittest import mock

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import agent_pi  # noqa: E402
from adw_modules.data_types import PiRequest  # noqa: E402
from tests.support.processes import install_python_entrypoint  # noqa: E402
from tests.support.runtime import (  # noqa: E402
    SCENARIO_USAGE,
    RuntimeTestCase,
    ScenarioOptions,
    execute_scenario,
    pid_alive,
    responses,
    supervised_adw,
    wait_until,
)

class AgentEndUsageReproduction(RuntimeTestCase):
    """M2-TRACE-01 — exhausted corrections leave no agent_end usage row."""

    def setUp(self) -> None:
        super().setUp()
        self.result = execute_scenario(self, responses("nope", "nope", "nope"),
                                       ScenarioOptions())

    @unittest.expectedFailure
    def test_exhausted_corrections_still_record_agent_end_usage(self):
        self.assertEqual(len(self.result.requests()), 3)
        agent_end = [event for event in self.result.events()
                     if event[0] == "agent_end"]
        self.assertEqual(len(agent_end), 1)
        self.assertEqual(agent_end[0][3], 36)   # 3 sends x 12 tokens


class InterruptedChildTerminationReproduction(RuntimeTestCase):
    """M2-PROC-01 — a signalled ADW closes its trace rows but orphans the
    coding-agent child, which keeps running with no owner."""

    def setUp(self) -> None:
        super().setUp()
        never = self._scratch / "release" / "never-created"
        self.handle = supervised_adw(self, "proc-run",
                                     _parked_scenario(str(never)))
        self.assertTrue(wait_until(self._double_parked, 30),
                        "the double never parked inside the supervised ADW")
        with sqlite3.connect(self.handle.db_path) as conn:
            (self.double_pid,) = conn.execute(
                "SELECT pid FROM processes WHERE adw_id=? AND kind='agent' "
                "AND ended_at IS NULL", (self.handle.adw_id,)).fetchone()
        self.handle.signal(signal.SIGTERM)
        self.exit_code = self.handle.wait(timeout=5)

    def _double_parked(self) -> bool:
        try:
            with sqlite3.connect(self.handle.db_path) as conn:
                rows = conn.execute(
                    "SELECT pid FROM processes WHERE adw_id=? AND kind='agent' "
                    "AND ended_at IS NULL", (self.handle.adw_id,)).fetchall()
        except sqlite3.OperationalError:
            return False        # the child has not created the schema yet
        return bool(rows)

    @unittest.expectedFailure
    def test_interrupted_adw_child_actually_terminates(self):
        self.assertEqual(self.exit_code, 143)
        self.assertFalse(pid_alive(self.double_pid),
                         "the trace says ended, but the coding-agent child is alive")


def _parked_scenario(release_path: str) -> dict:
    return {"responses": [{
        "text": '{"status":"success","summary":"parked"}', "exit_code": 0,
        "usage": SCENARIO_USAGE, "events": [], "writes": [],
        "wait_for_release": release_path,
    }]}


class StderrFloodReproduction(RuntimeTestCase):
    """M2-PROC-02 — a child that fills the stderr pipe while stdout stays
    open deadlocks the transport: nothing drains stderr until stdout EOF."""

    def setUp(self) -> None:
        super().setUp()
        from tests.support.runtime import wire_double
        wire_double(self)   # catalog + models.json patched like the other lanes
        catalog = mock.patch.object(agent_pi, "_pi_catalog",
                                    return_value=[("fixture", "fixture-model",
                                                   32000)])
        catalog.start()
        self.addCleanup(catalog.stop)

        flooder = self._scratch / "flood-pi.py"
        flooder.write_text(
            "import sys, time\n"
            "sys.stderr.write('e' * 200_000)\n"   # > pipe capacity (64KiB)
            "sys.stderr.flush()\n"
            "time.sleep(30)\n")                    # stdout stays open
        self.shim = install_python_entrypoint(self._scratch / "bin" / "flood-pi",
                                              flooder)
        flood_patch = mock.patch.object(agent_pi, "PI_PATH", str(self.shim))
        flood_patch.start()
        self.addCleanup(flood_patch.stop)

        agent_dir = self.target / "adws/adw_data/sessions/flood-agent"
        self.request = PiRequest(
            prompt="flood", system_prompt="s", model="fixture/fixture-model",
            thinking="medium", session_id="flood-session",
            session_dir=str(agent_dir / "pi_sessions"),
            raw_output_path=str(agent_dir / "raw_output.jsonl"),
            cwd=str(self.target))

        self.pids: list[int] = []
        self.holder: dict = {}

        def transport() -> None:
            try:
                self.holder["result"] = agent_pi.run(self.request,
                                                     on_spawn=self.pids.append)
            except BaseException as error:   # a transport failure also counts
                self.holder["error"] = error

        self.thread = threading.Thread(target=transport, daemon=True)
        self.thread.start()

        def cleanup() -> None:
            for pid in self.pids:
                try:
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            self.thread.join(timeout=5)
        self.addCleanup(cleanup)
        time.sleep(0.5)   # let the flood happen before we measure

    @unittest.expectedFailure
    def test_transport_finishes_or_fails_within_the_deadline(self):
        self.thread.join(timeout=5)
        self.assertFalse(self.thread.is_alive(),
                         "transport still blocked on a flooded stderr pipe")
