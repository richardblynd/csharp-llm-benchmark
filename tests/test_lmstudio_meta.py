from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from benchmark import cli
from benchmark.config import (
    AppConfig, BenchmarkConfig, CalibrationConfig, DiscoveryConfig,
    LlmConfig, OpenCodeConfig, PiConfig, load_config,
)
from benchmark.lmstudio_meta import parse_model_meta
from benchmark.scorer import score_benchmark


class PublisherMetadataTests(unittest.TestCase):
    def test_publisher_names_and_missing_values(self):
        for raw, expected in (
            ("qwen", "Qwen"),
            ("lmstudio-community", "LM Studio Community"),
            ("prism-ml", "Prism ML"),
            (" other-publisher ", "Other-publisher"),
            (None, None),
            ("", None),
            ("  ", None),
            (123, None),
        ):
            with self.subTest(publisher=raw):
                self.assertEqual(parse_model_meta({"publisher": raw}).publisher, expected)
        self.assertIsNone(parse_model_meta({}).publisher)

    def test_legacy_config_publisher_is_ignored(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "config.yaml"
            path.write_text(
                'llm:\n  publisher: "Old publisher"\nopencode:\n  version: "test"\n',
                encoding="utf-8",
            )
            self.assertIsNone(load_config(path).llm.publisher)

    def test_api_publisher_reaches_both_generators_and_reports(self):
        for models, expected in (
            ([{"key": "selected", "publisher": "lmstudio-community"},
              {"key": "other", "publisher": "prism-ml"}], "LM Studio Community"),
            ([{"key": "selected", "publisher": "prism-ml"}], "Prism ML"),
            ([{"key": "selected"}], None),
            ([], None),
        ):
            with self.subTest(models=models), tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
                config = AppConfig(
                    llm=LlmConfig(
                        model="selected", publisher="Old publisher",
                        discovery=DiscoveryConfig(enabled=False),
                    ),
                    benchmark=BenchmarkConfig(
                        output_dir=Path(directory),
                        calibration=CalibrationConfig(enabled=False),
                    ),
                    opencode=OpenCodeConfig(version="test"),
                    pi=PiConfig(version="test"),
                )
                args = cli._build_parser().parse_args(["run", "--generator", "all"])
                completed = cli.TemperatureRun(0.2, score_benchmark([]), [])
                with patch("benchmark.cli.load_config", return_value=config), patch(
                    "benchmark.cli.load_tasks", return_value=[]
                ), patch("benchmark.cli.validate_tasks", return_value=[]), patch(
                    "benchmark.lmstudio_meta.fetch_models", return_value=models
                ) as fetch, patch(
                    "benchmark.cli._run_task_major_temperatures", return_value=[completed]
                ) as generate, redirect_stdout(io.StringIO()):
                    self.assertEqual(cli._run(args), 0)

                fetch.assert_called_once_with("http://localhost:1234", api_key="lm-studio")
                self.assertEqual(generate.call_count, 2)
                self.assertEqual(
                    [call.args[0].benchmark.generator for call in generate.call_args_list],
                    ["opencode", "pi"],
                )
                for call in generate.call_args_list:
                    self.assertEqual(call.args[0].llm.publisher, expected)
                    run_dir = call.kwargs["run_dir"]
                    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                    self.assertEqual(summary["publisher"], expected)
                    self.assertEqual(summary["llm"]["publisher"], expected)
                    self.assertIn(
                        f"- Publisher: `{expected or 'n/a'}`",
                        (run_dir / "summary.md").read_text(encoding="utf-8"),
                    )


if __name__ == "__main__":
    unittest.main()
