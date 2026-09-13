"""Canonical Justfile recipe contract: names, routing, and behavior."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from tests.support.factory import FactoryTestCase, stamp

# Independent contract — deliberately NOT derived from the template file.
# Pinned example recipes minus cc/ipi, plus demo and smoke-real-pi.
BASE_RECIPES = {
    "ask", "build-review", "build-test", "default", "demo", "document",
    "kill", "obs", "phases", "pi", "plan", "plan-build", "procs",
    "prompt", "rosters", "scout", "sdlc", "sessions", "simple-sdlc",
    "smoke-real-pi", "tail",
}


def recipe_names(target: Path, env: dict[str, str]) -> set[str]:
    result = subprocess.run(["just", "--justfile", str(target / "justfile"),
                             "--summary"], env=env, capture_output=True,
                            text=True, timeout=30, cwd=target)
    if result.returncode != 0:
        raise AssertionError(f"just --summary failed: {result.stderr.strip()}")
    return set(result.stdout.split())


class JustfileTests(FactoryTestCase):
    def setUp(self) -> None:
        super().setUp()
        stamp(self.target, self.env).check_returncode()

    def test_canonical_base_recipe_set(self):
        self.assertEqual(recipe_names(self.target, self.env), BASE_RECIPES)

    def test_no_cc_or_ipi_recipes(self):
        names = recipe_names(self.target, self.env)
        self.assertNotIn("cc", names)
        self.assertNotIn("ipi", names)


class RecipeRoutingTests(FactoryTestCase):
    """Workflow recipes forward argv exactly; the recorder never executes them."""

    def setUp(self) -> None:
        super().setUp()
        stamp(self.target, self.env).check_returncode()
        record_dir = self._scratch / "record"
        record_dir.mkdir()
        self.record_path = record_dir / "invocations.jsonl"
        shim_dir = record_dir / "bin"
        shim_dir.mkdir()
        shim = shim_dir / "uv"
        shim.write_text(
            "#!/bin/sh\n"
            'exec '
            + json.dumps(_python()) + ' '
            + json.dumps(str(_recorder())) + ' "$@"\n'
        )
        shim.chmod(0o755)
        self.env["PATH"] = f"{shim_dir}:{self.env['PATH']}"
        self.env["SSSF_ARGV_RECORD"] = str(self.record_path)
        self.unset = self.env.pop("SSSF_STUB_EXIT", None)

    def tearDown(self) -> None:
        self.env.pop("SSSF_ARGV_RECORD", None)
        if self.unset is not None:
            self.env["SSSF_STUB_EXIT"] = self.unset
        super().tearDown()

    def _run_recipe(self, *recipe_args: str, config: str = "default") -> subprocess.CompletedProcess:
        env = dict(self.env)
        if config != "default":
            env["SSSF_CONFIG"] = config
        return subprocess.run(["just", *recipe_args], cwd=self.target, env=env,
                              capture_output=True, text=True, timeout=60)

    def _recorded(self) -> list[list[str]]:
        if not self.record_path.exists():
            return []
        return [json.loads(line) for line in
                self.record_path.read_text().splitlines() if line.strip()]

    def test_workflow_recipes_route_to_expected_scripts(self):
        cases = {
            "prompt": "adws/adw_prompt.py",
            "scout": "adws/adw_scout.py",
            "plan": "adws/adw_plan.py",
            "plan-build": "adws/adw_plan_build.py",
            "build-test": "adws/adw_build_test.py",
            "build-review": "adws/adw_build_review.py",
            "document": "adws/adw_document.py",
            "sdlc": "adws/adw_plan_build_test.py",
            "simple-sdlc": "adws/adw_simple_sdlc.py",
            "smoke-real-pi": "adws/adw_smoke.py",
        }
        for recipe, script in cases.items():
            result = self._run_recipe(recipe, "check")
            self.assertEqual(result.returncode, 0, f"{recipe}: {result.stderr}")
            (argv,) = self._recorded()
            self.assertIn(script, argv, recipe)
            config_index = argv.index("--config") + 1
            self.assertEqual(argv[config_index],
                             "adws/adw_sssf_config/sssf.config.yaml")
            self.record_path.write_text("")

    def test_arguments_pass_through_without_shell_execution(self):
        result = self._run_recipe(
            "ask", "scout", "spaces; $(touch UNEXPECTED)", "--adw-id", "a1b2c3d4")
        self.assertEqual(result.returncode, 0, result.stderr)
        (argv,) = self._recorded()
        self.assertFalse((self.target / "UNEXPECTED").exists(),
                         "shell metacharacters were executed")
        self.assertIn("adws/adw_prompt.py", argv)
        self.assertEqual(argv.count("spaces; $(touch UNEXPECTED)"), 1)
        self.assertEqual(argv.count("--agent"), 1)
        self.assertIn("a1b2c3d4", argv)

    def test_config_with_spaces_and_metacharacters_passes_as_one_argument(self):
        result = self._run_recipe("scout", "check",
                                  config="config with $(spaces).yaml")
        self.assertEqual(result.returncode, 0, result.stderr)
        (argv,) = self._recorded()
        config_index = argv.index("--config") + 1
        self.assertEqual(argv[config_index], "config with $(spaces).yaml")
        self.assertFalse((self.target / "UNEXPECTED").exists())

    def test_demo_stops_after_first_failure(self):
        self.env["SSSF_STUB_EXIT"] = "7"
        result = self._run_recipe("demo")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(len(self._recorded()), 1)

    def test_demo_runs_two_read_only_workflows_in_order(self):
        result = self._run_recipe("demo")
        self.assertEqual(result.returncode, 0, result.stderr)
        recorded = self._recorded()
        self.assertEqual(len(recorded), 2)
        self.assertIn("adw_prompt.py", " ".join(recorded[0]))
        self.assertIn("adw_scout.py", " ".join(recorded[1]))


def _python() -> str:
    import sys
    return sys.executable


def _recorder() -> Path:
    from tests.support.factory import ROOT
    return ROOT / "tests" / "fixtures" / "argv-recorder.py"
