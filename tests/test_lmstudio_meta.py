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


class ModelMetadataTests(unittest.TestCase):
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

    def test_display_name_preserves_api_spelling_and_handles_missing_values(self):
        for raw, expected in (
            ("Qwen3.5 4B", "Qwen3.5 4B"),
            (" prism-ml model ", "prism-ml model"),
            (None, None), ("", None), ("  ", None), (123, None),
        ):
            with self.subTest(display_name=raw):
                self.assertEqual(parse_model_meta({"display_name": raw}).display_name, expected)
        self.assertIsNone(parse_model_meta({}).display_name)

    def test_legacy_config_metadata_is_ignored(self):
        for label_key in ("modelLabel", "model_label"):
            with self.subTest(label_key=label_key), tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
                path = Path(directory) / "config.yaml"
                path.write_text(
                    'llm:\n  model: "selected"\n  publisher: "Old publisher"\n'
                    f'  {label_key}: "Old name"\nopencode:\n  version: "test"\n',
                    encoding="utf-8",
                )
                config = load_config(path)
                self.assertIsNone(config.llm.publisher)
                self.assertIsNone(config.llm.model_label)
                self.assertEqual(config.llm.effective_model_label, "selected")

    def test_api_metadata_reaches_both_generators_folders_and_reports(self):
        for models, expected, expected_name in (
            ([{"key": "selected", "publisher": "lmstudio-community", "display_name": "Qwen3.5 4B"},
              {"key": "other", "publisher": "prism-ml", "display_name": "Other model"}],
             "LM Studio Community", "Qwen3.5 4B"),
            ([{"key": "selected", "publisher": "prism-ml", "display_name": "prism model"}],
             "Prism ML", "prism model"),
            ([{"key": "selected", "display_name": " "}], None, "selected"),
            ([{"key": "selected"}], None, "selected"),
            ([], None, "selected"),
        ):
            with self.subTest(models=models), tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
                config = AppConfig(
                    llm=LlmConfig(
                        model="selected", publisher="Old publisher", model_label="Old name",
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
                    self.assertEqual(call.args[0].llm.effective_model_label, expected_name)
                    run_dir = call.kwargs["run_dir"]
                    self.assertIn(f"_{expected_name.replace(' ', '-')}_", run_dir.name)
                    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                    self.assertEqual(summary["model"], "selected")
                    self.assertEqual(summary["modelLabel"], expected_name)
                    self.assertEqual(summary["llm"]["modelLabel"], expected_name)
                    self.assertEqual(summary["publisher"], expected)
                    self.assertEqual(summary["llm"]["publisher"], expected)
                    self.assertIn(
                        f"- Publisher: `{expected or 'n/a'}`",
                        (run_dir / "summary.md").read_text(encoding="utf-8"),
                    )
                    self.assertIn(
                        f"- Model label: `{expected_name}`",
                        (run_dir / "summary.md").read_text(encoding="utf-8"),
                    )


if __name__ == "__main__":
    unittest.main()
