"""Runtime test fixture: a stamped, committed scratch repo with cwd switched.

Imports the Task 1 bootstrap first, so template modules load with the
import-time dotenv call suppressed and the path verified. Tests run serially:
`os.chdir` is process-global state, so setUp/tearDown own the cwd.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from tests.support.imports import bootstrap

bootstrap()

from adw_modules import agents  # noqa: E402
from adw_modules.data_types import (  # noqa: E402
    AgentCall,
    GenericOutput,
    PhaseParams,
)
from adw_modules.runner import Run  # noqa: E402
from adw_modules.tracer import Tracer  # noqa: E402
from adw_modules.utils import new_id  # noqa: E402
from tests.support.factory import ROOT, FactoryTestCase, git, stamp  # noqa: E402
from tests.support.processes import (  # noqa: E402
    _stop_group,
    install_python_entrypoint,
)


class RuntimeTestCase(FactoryTestCase):
    """A stamped target repo with a tracked sample file and one baseline commit.

    The stamped .gitignore keeps runtime session writes out of permission
    snapshots and change captures. Everything the tests commit lives in the
    scratch target; the source checkout is never touched.
    """

    def setUp(self) -> None:
        super().setUp()
        stamp(self.target, self.env).check_returncode()
        git(self.target, ["init"], self.env)
        for key, value in (
            ("user.name", "SSSF Test"),
            ("user.email", "sssf@example.invalid"),
            ("commit.gpgsign", "false"),
            ("core.hooksPath", "/dev/null"),
        ):
            git(self.target, ["config", key, value], self.env)
        (self.target / "sample.txt").write_text("original\n")
        git(self.target, ["add", "-A"], self.env)
        git(self.target, ["commit", "-m", "fixture baseline"], self.env)
        self._previous_cwd = os.getcwd()
        self.addCleanup(os.chdir, self._previous_cwd)
        os.chdir(self.target)

    @property
    def branch(self) -> str:
        """The target repo's current branch name."""
        return git(self.target, ["rev-parse", "--abbrev-ref", "HEAD"],
                   self.env).strip()


def make_run(target: Path, adw_id: str) -> Run:
    """Construct a real Run for the stamped target; cwd must already be it.

    Direct construction (instead of session.ensure) avoids installing
    process-global signal handlers in tests. `defaults.data_dir` stays
    relative so permission-prefix semantics match production; only the trace
    DB path is resolved absolutely, for independent readers. The caller owns
    the connection: register `run.tracer.conn.close` as cleanup.
    """
    assert Path.cwd().resolve() == Path(target).resolve(), \
        "chdir to the target before make_run"
    cfg = agents.load_config()
    tracer = Tracer(Path(cfg.observability.db).resolve(),
                    str(Path(cfg.defaults.data_dir) / "sessions" / adw_id
                         / "events.jsonl"))
    run = Run(cfg=cfg, adw_id=adw_id, tracer=tracer, engineer="sssf-test")
    tracer.session_start(adw_id, run.engineer)
    return run


# ── the fixture double as the only Pi (Task 6/7 scenarios) ────────────────

FIXTURE_MODEL = "fixture/fixture-model"
_DOUBLE_SCRIPT = ROOT / "tests" / "fixtures" / "pi-double.py"
SCENARIO_USAGE = {"input": 10, "output": 2, "cacheRead": 0, "cacheWrite": 0,
                  "totalTokens": 12,
                  "cost": {"input": 0.01, "output": 0.002, "cacheRead": 0,
                           "cacheWrite": 0, "total": 0.012}}


def responses(*texts: str) -> dict:
    """Build a Task 6 scenario with the fixed 12-token usage on every send."""
    return {"responses": [
        {"text": text, "exit_code": 0, "usage": SCENARIO_USAGE,
         "events": [], "writes": []}
        for text in texts]}


def pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False


def wait_until(predicate, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def wire_double(case: FactoryTestCase) -> Path:
    """Point agent_pi at the fixture double for the duration of one test."""
    from unittest import mock
    from adw_modules import agent_pi
    shim = install_python_entrypoint(case._scratch / "bin" / "pi", _DOUBLE_SCRIPT)
    models_json = case._scratch / "models.json"
    models_json.write_text('{"providers": {}}')
    for patch in (mock.patch.object(agent_pi, "PI_PATH", str(shim)),
                  mock.patch.object(agent_pi, "MODELS_JSON", str(models_json))):
        patch.start()
        case.addCleanup(patch.stop)
    agent_pi._pi_catalog.cache_clear()
    case.addCleanup(agent_pi._pi_catalog.cache_clear)
    return shim


@dataclass
class ScenarioOptions:
    """What one orchestrated scenario configures: output type, gates,
    retries, and the agent's write permission."""
    output_type: type = GenericOutput
    gates: tuple = ()
    retries: int = 0
    # () -> read-only (writes=[]); None -> unrestricted; list/tuple -> grants.
    writes: object = ()
    calls: int = 1               # number of agent phases in the run
    prompt: str = "produce your report"
    phase_name: str = "work"
    adw_id: str = ""             # minted when empty
    description: str = "Scenario phase producing an agent envelope"


@dataclass
class ScenarioResult:
    """Everything a test needs to make its OWN assertions. Never swallows
    failures: the captured error is exposed, not treated as a pass."""
    error: Optional[BaseException]
    envelope: object
    run_id: str
    db_path: Path
    request_log_path: Path

    def _query(self, sql: str, params: tuple = ()) -> list[tuple]:
        # A fresh connection per verification — the tracer's connection stays
        # open and WAL lets both coexist.
        with sqlite3.connect(self.db_path) as conn:
            return conn.execute(sql, params).fetchall()

    def requests(self) -> list[dict]:
        if not self.request_log_path.exists():
            return []
        return [json.loads(line) for line
                in self.request_log_path.read_text().splitlines() if line.strip()]

    def envelope_validity(self) -> list[int]:
        rows = self._query("SELECT valid FROM envelopes WHERE adw_id=? "
                           "ORDER BY rowid", (self.run_id,))
        return [row[0] for row in rows]

    def events(self) -> list[tuple]:
        return self._query("SELECT type, name, payload_json, tokens FROM events "
                           "WHERE adw_id=? ORDER BY rowid", (self.run_id,))

    def gates(self) -> list[tuple]:
        return self._query("SELECT attempt, passed, violations_json, checks_json "
                           "FROM gate_results WHERE adw_id=? ORDER BY rowid",
                           (self.run_id,))

    def session_row(self) -> tuple:
        return self._query("SELECT status, total_tokens, total_cost, ended_at "
                           "FROM sessions WHERE adw_id=?", (self.run_id,))[0]

    def phases(self) -> list[tuple]:
        return self._query("SELECT seq, name, status, attempt, error FROM phases "
                           "WHERE adw_id=? ORDER BY seq", (self.run_id,))

    def processes(self) -> list[tuple]:
        return self._query("SELECT kind, name, pid, ended_at FROM processes "
                           "WHERE adw_id=?", (self.run_id,))


def _write_roster(case: FactoryTestCase, options: ScenarioOptions) -> None:
    """A one-agent roster in the scratch target, honoring the scenario's
    write permission. Prompts use the real placeholder set."""
    writes = "null" if options.writes is None else json.dumps(list(options.writes))
    config_dir = case.target / "adws/adw_sssf_config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "sssf.config.yaml").write_text(f"""
defaults:
  model: {FIXTURE_MODEL}
  thinking: medium
  data_dir: adws/adw_data

agents:
  - name: scout
    model: {FIXTURE_MODEL}
    thinking: medium
    writes: {writes}
    purpose: scenario agent
    prompt_engineering:
      system: adws/adw_data/prompt_engineering/scout/system.md
      user: adws/adw_data/prompt_engineering/scout/user.md
""")
    prompts = case.target / "adws/adw_data/prompt_engineering/scout"
    prompts.mkdir(parents=True, exist_ok=True)
    (prompts / "system.md").write_text("You are the scenario agent.\n")
    (prompts / "user.md").write_text(
        "task: {{prompt}}\nprevious: {{previous_envelope}}\n"
        "handoff: {{context_handoff_dir}}\n")


def execute_scenario(case: FactoryTestCase, scenario: dict,
                     options: ScenarioOptions) -> ScenarioResult:
    """Run a real config + Run + Tracer + AgentCall with only Pi doubled.

    Orchestrator errors are captured on `result.error` for explicit
    assertions — never treated as a passing test automatically.
    """
    wire_double(case)
    _write_roster(case, options)
    scenario_path = case._scratch / "scenario.json"
    scenario_path.write_text(json.dumps(scenario))
    os.environ["SSSF_TEST_DOUBLE"] = "1"
    os.environ["SSSF_PI_SCENARIO"] = str(scenario_path)
    case.addCleanup(os.environ.pop, "SSSF_TEST_DOUBLE", None)
    case.addCleanup(os.environ.pop, "SSSF_PI_SCENARIO", None)

    adw_id = options.adw_id or new_id(8)
    run = make_run(case.target, adw_id)
    case.addCleanup(run.tracer.conn.close)

    error: Optional[BaseException] = None
    envelope = None
    try:
        for index in range(options.calls):
            name = (options.phase_name if options.calls == 1
                    else f"{options.phase_name}-{index + 1}")
            with run.phase(PhaseParams(name=name, kind="agent", owner="scout",
                                       description=options.description,
                                       retries=options.retries)) as phase:
                envelope = phase.call(AgentCall(
                    output_type=options.output_type, prompt=options.prompt,
                    gates=list(options.gates)))
    except Exception as exc:
        error = exc                 # the phase context already recorded the fail

    return ScenarioResult(
        error=error, envelope=envelope, run_id=adw_id,
        db_path=Path(run.tracer.db_path),
        request_log_path=(case.target / "adws/adw_data/sessions" / adw_id
                          / "test-double" / "requests.jsonl"))


# ── supervised ADW children (OS-signal behavior; session.ensure runs there) ──

@dataclass
class SupervisedAdw:
    process: "subprocess.Popen[bytes]"
    adw_id: str
    db_path: Path

    @property
    def pid(self) -> int:
        return self.process.pid

    def signal(self, signum: int) -> None:
        os.kill(self.pid, signum)

    def wait(self, timeout: float = 5.0) -> int:
        return self.process.wait(timeout=timeout)


def supervised_adw(case: FactoryTestCase, adw_id: str, scenario: dict,
                   *, release: Path | None = None) -> SupervisedAdw:
    """Launch adw_prompt.py as a supervised scratch child speaking to the double.

    The child runs in its own process group, owned by this test; cleanup TERMs
    that group only. Creating the release file at teardown un-parks a double
    that would otherwise wait out its own 10-second timeout.
    """
    wire_double(case)
    _write_roster(case, ScenarioOptions())
    scenario_path = case._scratch / "supervised-scenario.json"
    scenario_path.write_text(json.dumps(scenario))
    os.environ["SSSF_TEST_DOUBLE"] = "1"
    os.environ["SSSF_PI_SCENARIO"] = str(scenario_path)
    case.addCleanup(os.environ.pop, "SSSF_TEST_DOUBLE", None)
    case.addCleanup(os.environ.pop, "SSSF_PI_SCENARIO", None)
    if release is not None:
        release.parent.mkdir(parents=True, exist_ok=True)
        case.addCleanup(release.write_text, "go")

    env = dict(os.environ, PI_PATH=str(case._scratch / "bin" / "pi"))
    stdout = (case._scratch / f"adw-{adw_id}.stdout").open("wb")
    stderr = (case._scratch / f"adw-{adw_id}.stderr").open("wb")
    case.addCleanup(stdout.close)
    case.addCleanup(stderr.close)
    process = subprocess.Popen(
        [sys.executable, "adws/adw_prompt.py", "hello", "--agent", "scout",
         "--adw-id", adw_id],
        cwd=case.target, env=env, stdin=subprocess.DEVNULL,
        stdout=stdout, stderr=stderr, start_new_session=True)
    case.addCleanup(_stop_group, process.pid)
    return SupervisedAdw(process=process, adw_id=adw_id,
                         db_path=(case.target / "adws/adw_data/sssf.db").resolve())
