from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from benchmark import cli
from benchmark.aggregate_benchmark_results import (
    group_results,
    parse_summary,
    render_html,
    render_markdown,
)
from benchmark.config import (
    AppConfig,
    BenchmarkConfig,
    OpenCodeConfig,
    PiConfig,
    apply_cli_overrides,
    load_config,
)
from benchmark.generation import (
    OpenCodeGenerator,
    PiGenerator,
    create_solution_generator,
)
from benchmark.report import create_run_dir, write_summary
from benchmark.scorer import score_benchmark
from benchmark.solution import extract_solution_code


class AgentGeneratorTests(unittest.TestCase):
    def setUp(self):
        self.config = AppConfig(
            opencode=OpenCodeConfig(version="test-opencode"),
            pi=PiConfig(version="test-pi"),
        )

    def test_example_and_default_select_opencode(self):
        config = load_config(Path("config.example.yaml"))
        self.assertEqual(config.benchmark.generator, "opencode")
        self.assertIsInstance(create_solution_generator(config), OpenCodeGenerator)
        self.assertEqual(BenchmarkConfig().generator, "opencode")

    def test_cli_and_config_reject_removed_generator(self):
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            cli._build_parser().parse_args(["run", "--generator", "llm"])
        with self.assertRaises(ValueError):
            apply_cli_overrides(self.config, generator="llm")
        with tempfile.TemporaryDirectory() as directory:
            config_path = Path(directory) / "config.yaml"
            config_path.write_text('benchmark:\n  generator: "llm"\n')
            with self.assertRaises(ValueError):
                load_config(config_path)

    def test_factory_accepts_only_concrete_agents(self):
        for generator, expected in (("opencode", OpenCodeGenerator), ("pi", PiGenerator)):
            config = replace(self.config, benchmark=BenchmarkConfig(generator=generator))
            self.assertIsInstance(create_solution_generator(config), expected)
        for generator in ("llm", "all", "unknown"):
            config = replace(self.config, benchmark=BenchmarkConfig(generator=generator))
            with self.assertRaises(ValueError):
                create_solution_generator(config)

    def test_all_runs_exactly_both_agents(self):
        args = cli._build_parser().parse_args(["run", "--generator", "all"])
        with patch("benchmark.cli.load_config", return_value=self.config), patch(
            "benchmark.cli.resolve_model_meta"
        ), patch("benchmark.cli.load_tasks", return_value=[]), patch(
            "benchmark.cli.validate_tasks", return_value=[]
        ), patch("benchmark.cli._report_quantization_precedence"), patch(
            "benchmark.cli._execute_benchmark", return_value=score_benchmark([])
        ) as execute, redirect_stdout(io.StringIO()):
            self.assertEqual(cli._run(args), 0)
        self.assertEqual(
            [call.args[0].benchmark.generator for call in execute.call_args_list],
            ["opencode", "pi"],
        )

    def test_all_requires_both_pinned_versions(self):
        for section in ("pi", "opencode"):
            config = replace(self.config, **{section: replace(getattr(self.config, section), version=None)})
            with self.assertRaises(ValueError):
                apply_cli_overrides(config, generator="all")

    def test_resume_does_not_infer_removed_generator(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            for generator in (None, "llm"):
                path.write_text(json.dumps({"status": "passed", "generator": generator}))
                with self.assertRaises(ValueError):
                    cli._read_task_result_json(path)
            for generator in ("pi", "opencode"):
                path.write_text(json.dumps({"status": "passed", "generator": generator}))
                self.assertEqual(cli._read_task_result_json(path).generator, generator)

    def test_summary_keeps_agent_timeout_and_shared_model_settings(self):
        for generator in ("pi", "opencode"):
            config = replace(self.config, benchmark=BenchmarkConfig(generator=generator))
            with tempfile.TemporaryDirectory() as directory:
                path = create_run_dir(
                    Path(directory), model_label="model", quantization="Q4", generator_mode=generator
                )
                self.assertTrue(path.name.endswith("-" + generator.upper()))
                write_summary(path, config=config, score=score_benchmark([]), task_scores=[])
                summary = json.loads((path / "summary.json").read_text())
                self.assertEqual(summary[generator]["timeout_seconds"], 900)
                self.assertEqual(summary["llm"]["model"], config.llm.model)
                self.assertNotIn("seed", summary["llm"])
                self.assertNotIn("timeout_seconds", summary["llm"])

    def test_run_directory_rejects_removed_generator(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(ValueError):
            create_run_dir(Path(directory), model_label="model", quantization="Q4", generator_mode="llm")

    def test_shared_extraction_preserves_agent_file_validation(self):
        extracted = extract_solution_code(
            'public class Solution { public string Text = "namespace Allowed;"; }',
        )
        self.assertIsNotNone(extracted.code)
        self.assertIsNone(extracted.error)
        extracted = extract_solution_code(
            "namespace Disallowed; public class Solution {}"
        )
        self.assertIsNone(extracted.code)


class AgentRankingTests(unittest.TestCase):
    def result(self, generator, score, model="model"):
        return parse_summary("run", {
            "generator": generator,
            "model": model,
            generator: {"version": "test"},
            "score": {"final_score": score},
        }, [])

    def test_ranking_uses_only_available_agent_scores(self):
        groups = group_results([
            self.result("pi", 80), self.result("opencode", 20),
            self.result("pi", 60, model="single-agent"),
            self.result("pi", 0, model="zero-score"),
        ])
        self.assertEqual([g.model for g in groups], ["single-agent", "model", "zero-score"])
        self.assertEqual(groups[0].avg_score(), 60)
        self.assertEqual(groups[1].avg_score(), 50)
        self.assertEqual(groups[1].max_score(), 80)
        self.assertEqual(groups[2].avg_score(), 0)
        markdown = render_markdown(groups, Path("results"))
        html = render_html(groups, Path("results"))
        self.assertIn("SCORE PI | SCORE OPENCODE", markdown)
        self.assertNotIn("SCORE LLM", markdown)
        self.assertNotIn("scoreLlm", html)
        self.assertNotIn("data-score-llm", html)
        self.assertEqual(markdown.splitlines()[7].count("|"), markdown.splitlines()[9].count("|"))

    def test_aggregate_rejects_removed_and_missing_generators(self):
        for generator in (None, "llm", "unknown"):
            with self.assertRaises(ValueError):
                self.result(generator, 100)


if __name__ == "__main__":
    unittest.main()
