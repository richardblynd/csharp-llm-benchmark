from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from benchmark import cli
from benchmark.config import (
    AppConfig, BenchmarkConfig, CalibrationConfig, DiscoveryConfig,
    LlmConfig, OpenCodeConfig, PiConfig, load_config,
)
from benchmark.lmstudio_meta import fetch_loaded_models, parse_model_meta, resolve_model_meta
from benchmark.scorer import score_benchmark


class ModelMetadataTests(unittest.TestCase):
    def test_loaded_variant_overrides_catalog_quantization_and_size(self):
        catalog = {
            "key": "google/gemma-4-12b", "display_name": "Gemma 4 12B",
            "quantization": {"name": "Q4_K_M"}, "size_bytes": 7381457070,
            "variants": ["google/gemma-4-12b@q4_k_m", "google/gemma-4-12b@q6_k", "google/gemma-4-12b@q8_0"],
            "selected_variant": "google/gemma-4-12b@q4_k_m", "loaded_instances": [],
        }
        loaded = {
            "identifier": "google/gemma-4-12b", "modelKey": "google/gemma-4-12b@q6_k",
            "path": "google/gemma-4-12b", "quantization": {"name": "Q6_K"},
            "sizeBytes": 9786097710,
        }
        with patch("benchmark.lmstudio_meta.fetch_models", return_value=[catalog]), patch(
            "benchmark.lmstudio_meta.fetch_loaded_models", return_value=[loaded]
        ):
            meta = resolve_model_meta("http://localhost:1234/v1", model=loaded["identifier"])
        self.assertEqual(meta.quantization, "Q6_K")
        self.assertEqual(meta.size_bytes, 9786097710)
        self.assertEqual(meta.display_name, "Gemma 4 12B")

    def test_ambiguous_catalog_does_not_supply_variant_metadata(self):
        meta = parse_model_meta({
            "quantization": {"name": "Q4_K_M"}, "size_bytes": 7381457070,
            "variants": ["model@q4_k_m", "model@q6_k"],
            "selected_variant": "model@q4_k_m", "params_string": "12B",
        })
        self.assertIsNone(meta.quantization)
        self.assertIsNone(meta.size_bytes)
        self.assertEqual(meta.params_string, "12B")

    def test_cli_only_supplies_models_for_same_host_and_port(self):
        for same_machine, port, expected_calls in ((False, 1234, 0), (True, 9999, 1), (True, 1234, 2)):
            with self.subTest(same_machine=same_machine, port=port), patch(
                "benchmark.lmstudio_meta._is_same_machine", return_value=same_machine
            ), patch("benchmark.lmstudio_meta.shutil.which", return_value="lms"), patch(
                "benchmark.lmstudio_meta.subprocess.run",
                side_effect=[
                    subprocess.CompletedProcess([], 0, json.dumps({"running": True, "port": port})),
                    subprocess.CompletedProcess([], 0, '[{"identifier": "selected"}]'),
                ],
            ) as run:
                result = fetch_loaded_models("http://localhost:1234/v1")
                self.assertEqual(result, [{"identifier": "selected"}] if expected_calls == 2 else [])
                self.assertEqual(run.call_count, expected_calls)

    def test_cli_failures_allow_fallback(self):
        for failure in (FileNotFoundError(), subprocess.TimeoutExpired("lms", 10), ValueError()):
            with self.subTest(failure=failure), patch(
                "benchmark.lmstudio_meta._is_same_machine", return_value=True
            ), patch("benchmark.lmstudio_meta.shutil.which", return_value="lms"), patch(
                "benchmark.lmstudio_meta.subprocess.run", side_effect=failure
            ), redirect_stderr(io.StringIO()):
                self.assertEqual(fetch_loaded_models("http://localhost:1234/v1"), [])

    def test_variant_metadata_reaches_run_folders_and_reports(self):
        for loaded, expected_quant, expected_size in (
            ([{"identifier": "selected", "quantization": {"name": "Q6_K"}, "sizeBytes": 9000}], "Q6_K", 9000),
            ([], "Q6_K", round(9.5 * 2**30)),
        ):
            with self.subTest(loaded=loaded), tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
                config = AppConfig(
                    llm=LlmConfig(model="selected", quantization="Q8_0", discovery=DiscoveryConfig(enabled=False)),
                    benchmark=BenchmarkConfig(output_dir=Path(directory), calibration=CalibrationConfig(enabled=False)),
                    opencode=OpenCodeConfig(version="test"), pi=PiConfig(version="test"),
                )
                args = cli._build_parser().parse_args(["run", "--generator", "all"])
                completed = cli.TemperatureRun(0.2, score_benchmark([]), [])
                stderr = io.StringIO()
                with patch("benchmark.cli.load_config", return_value=config), patch(
                    "benchmark.cli.load_tasks", return_value=[]
                ), patch("benchmark.cli.validate_tasks", return_value=[]), patch(
                    "benchmark.lmstudio_meta.fetch_models", return_value=[{
                        "key": "selected", "quantization": {"name": "Q4_K_M"},
                        "size_bytes": 7000, "variants": ["selected@q4_k_m", "selected@q6_k", "selected@q8_0"],
                    }]
                ), patch("benchmark.lmstudio_meta.fetch_loaded_models", return_value=loaded), patch(
                    "benchmark.cli._run_task_major_temperatures", return_value=[completed]
                ) as generate, patch("builtins.input", side_effect=["Q6_K", "9,5"]) as prompt, redirect_stdout(io.StringIO()), redirect_stderr(stderr):
                    self.assertEqual(cli._run(args), 0)
                self.assertEqual(generate.call_count, 2)
                if not loaded:
                    self.assertIn("multiple variants", stderr.getvalue())
                self.assertEqual(prompt.call_count, 0 if loaded else 2)
                for call in generate.call_args_list:
                    run_dir = call.kwargs["run_dir"]
                    self.assertIn(f"_{expected_quant}-", run_dir.name)
                    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                    self.assertEqual(summary["quantization"], expected_quant)
                    self.assertEqual(summary["llm"]["quantization"], expected_quant)
                    self.assertEqual(summary["model_size_bytes"], expected_size)
                    self.assertIn(f"- Quantization: `{expected_quant}`", (run_dir / "summary.md").read_text(encoding="utf-8"))

    def test_metadata_prompt_validates_input_and_preserves_identity(self):
        meta = cli.LmStudioModelMeta(publisher="Google", display_name="Gemma", params_string="12B")
        with patch("builtins.input", side_effect=[
            "", "unknown", "not-specified", " Q6_K ",
            "", "bad", "0", "-1", "nan", "inf", "1e999", "9,5",
        ]), redirect_stdout(io.StringIO()):
            result = cli._prompt_missing_model_metadata(meta, "selected")
        self.assertEqual(result.quantization, "Q6_K")
        self.assertEqual(result.size_bytes, round(9.5 * 2**30))
        self.assertEqual(result.publisher, "Google")
        self.assertEqual(result.display_name, "Gemma")
        self.assertEqual(result.params_string, "12B")

    def test_metadata_prompt_only_asks_for_missing_fields(self):
        for meta, answer in (
            (cli.LmStudioModelMeta(quantization="Q6_K"), "9.5"),
            (cli.LmStudioModelMeta(size_bytes=round(9.5 * 2**30)), "Q6_K"),
        ):
            with self.subTest(meta=meta), patch("builtins.input", return_value=answer) as prompt, redirect_stdout(io.StringIO()):
                result = cli._prompt_missing_model_metadata(meta, "selected")
            prompt.assert_called_once()
            self.assertEqual(result.quantization, "Q6_K")
            self.assertEqual(result.size_bytes, round(9.5 * 2**30))

    def test_missing_input_stops_before_calibration_or_generation(self):
        config = AppConfig(
            llm=LlmConfig(model="selected", quantization="Q8_0"),
            opencode=OpenCodeConfig(version="test"),
        )
        with patch("benchmark.cli.load_config", return_value=config), patch(
            "benchmark.cli.load_tasks", return_value=[]
        ), patch("benchmark.cli.validate_tasks", return_value=[]), patch(
            "benchmark.cli.resolve_model_meta", return_value=cli.LmStudioModelMeta()
        ), patch("builtins.input", side_effect=EOFError), patch(
            "benchmark.cli.calibrate"
        ) as calibrate, patch("benchmark.cli._execute_benchmark") as execute, redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "Model metadata is required"):
                cli._run(cli._build_parser().parse_args(["run"]))
        calibrate.assert_not_called()
        execute.assert_not_called()

    def test_cloud_model_does_not_prompt_for_local_file_metadata(self):
        config = AppConfig(
            llm=LlmConfig(base_url="https://api.example.com/v1", model="selected", quantization="cloud"),
            benchmark=BenchmarkConfig(calibration=CalibrationConfig(enabled=False)),
            opencode=OpenCodeConfig(version="test"),
        )
        with patch("benchmark.cli.load_config", return_value=config), patch(
            "benchmark.cli.load_tasks", return_value=[]
        ), patch("benchmark.cli.validate_tasks", return_value=[]), patch(
            "benchmark.cli.resolve_model_meta", return_value=cli.LmStudioModelMeta()
        ), patch("builtins.input") as prompt, patch("benchmark.cli._execute_benchmark"), redirect_stdout(io.StringIO()):
            self.assertEqual(cli._run(cli._build_parser().parse_args(["run"])), 0)
        prompt.assert_not_called()

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
            with self.subTest(models=models), tempfile.TemporaryDirectory(dir=Path.cwd()) as directory, patch(
                "benchmark.lmstudio_meta.fetch_loaded_models", return_value=[]
            ):
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
                ) as generate, patch("builtins.input", side_effect=["Q6_K", "9.5"]), redirect_stdout(io.StringIO()):
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
