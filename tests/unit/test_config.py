"""Config loading and fail-fast validation, exercised without real Pi."""
from __future__ import annotations

import unittest
from unittest import mock

from tests.support.imports import bootstrap

bootstrap()
from tests.support.runtime import RuntimeTestCase

from adw_modules import agent_pi, agents

FIXED_CATALOG = [("google", "gemini-3.6-flash", 1_000_000),
                 ("openai", "gpt-5.6-terra", 400_000)]


class LoadConfigTests(RuntimeTestCase):
    """load_config() inherits defaults and preserves explicit empty values."""

    def setUp(self) -> None:
        super().setUp()
        self.config_path = self.target / "config.yaml"
        self.config_path.write_text("""
defaults:
  model: google/gemini-3.6-flash
  thinking: low
  tools: ["read", "write"]
  writes: []

agents:
  - name: scout
    prompt_engineering:
      system: prompts/scout-system.md
      user: prompts/scout-user.md
  - name: builder
    model: openai/gpt-5.6-terra
    thinking: high
    tools: []
    writes: ["src/"]
    prompt_engineering:
      system: prompts/builder-system.md
      user: prompts/builder-user.md
""")

    def load(self) -> "agents.SSSFConfig":
        return agents.load_config(str(self.config_path))

    def test_inherited_fields_come_from_defaults(self):
        scout = agents.resolve(self.load(), "scout")
        self.assertEqual(scout.model, "google/gemini-3.6-flash")
        self.assertEqual(scout.thinking, "low")
        self.assertEqual(scout.tools, ["read", "write"])
        self.assertEqual(scout.writes, [])

    def test_agent_values_override_defaults(self):
        builder = agents.resolve(self.load(), "builder")
        self.assertEqual(builder.model, "openai/gpt-5.6-terra")
        self.assertEqual(builder.thinking, "high")

    def test_explicit_empty_tools_and_writes_stay_empty(self):
        builder = agents.resolve(self.load(), "builder")
        self.assertEqual(builder.tools, [])
        self.assertEqual(builder.writes, ["src/"])

    def test_resolve_unknown_agent_exits_with_available_names(self):
        with self.assertRaises(SystemExit) as caught:
            agents.resolve(self.load(), "nobody")
        self.assertIn("'scout'", str(caught.exception))


class ValidateConfigTests(RuntimeTestCase):
    """validate() fails fast before any agent process can spawn."""

    def setUp(self) -> None:
        super().setUp()
        # Fixed catalog: resolution never shells out to a real pi.
        self.catalog = mock.patch.object(agent_pi, "_pi_catalog",
                                         return_value=FIXED_CATALOG)
        self.catalog.start()
        self.addCleanup(self.catalog.stop)
        # Any agent launch during validation is a bug, not a test failure.
        self.run_guard = mock.patch.object(
            agent_pi, "run", side_effect=AssertionError("agent_pi.run reached"))
        self.run_guard.start()
        self.addCleanup(self.run_guard.stop)

        (self.target / "prompts").mkdir()
        (self.target / "prompts/scout-system.md").write_text("system\n")
        (self.target / "prompts/scout-user.md").write_text("user\n")

    def config(self, **overrides) -> "agents.SSSFConfig":
        from adw_modules.data_types import AgentConfig, PromptEngineering, SSSFConfig
        fields = {"name": "scout",
                  "prompt_engineering": PromptEngineering(
                      system="prompts/scout-system.md",
                      user="prompts/scout-user.md")}
        fields.update(overrides)
        return SSSFConfig(agents=[AgentConfig(**fields)])

    def test_valid_config_passes_without_reaching_agent_pi_run(self):
        agents.validate(self.config(), ["scout"])   # must not raise

    def test_missing_required_agent_is_rejected(self):
        with self.assertRaises(SystemExit) as caught:
            agents.validate(self.config(), ["nobody"])
        self.assertIn("not defined", str(caught.exception))

    def test_missing_prompt_file_is_rejected(self):
        broken = self.config(prompt_engineering={
            "system": "prompts/absent-system.md",
            "user": "prompts/scout-user.md"})
        with self.assertRaises(SystemExit) as caught:
            agents.validate(broken, ["scout"])
        self.assertIn("system prompt not found", str(caught.exception))

    def test_claude_code_agent_is_rejected_at_runtime_validation(self):
        claude = self.config(coding_agent="claude_code")
        with self.assertRaises(SystemExit) as caught:
            agents.validate(claude, ["scout"])
        self.assertIn("claude_code", str(caught.exception))
        self.assertIn("not implemented", str(caught.exception))

    def test_unknown_model_pattern_is_rejected(self):
        unknown = self.config(model="google/does-not-exist")
        with self.assertRaises(SystemExit) as caught:
            agents.validate(unknown, ["scout"])
        self.assertIn("not found in pi --list-models", str(caught.exception))

    def test_every_problem_is_collected_not_raised_one_by_one(self):
        with self.assertRaises(SystemExit) as caught:
            agents.validate(self.config(), ["nobody", "also-missing"])
        self.assertIn("nobody", str(caught.exception))
        self.assertIn("also-missing", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
