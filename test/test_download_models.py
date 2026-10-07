"""Behavioral checks for the speech-model download operation."""

from __future__ import annotations

import os
import shutil
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class DownloadModelsTests(unittest.TestCase):
    def test_metadata_only_asr_cache_reports_missing_config(self) -> None:
        """A cache marker must not count as a downloaded ASR model."""
        with tempfile.TemporaryDirectory() as temporary_directory:
            sandbox = Path(temporary_directory)
            script, environment = self._prepare_sandbox(
                sandbox,
                {"CACHEDIR.TAG": "cache metadata\n"},
            )
            result = self._run(script, sandbox, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "ASR model is missing config.json\n")

    def test_config_without_weights_reports_missing_safetensors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            sandbox = Path(temporary_directory)
            script, environment = self._prepare_sandbox(
                sandbox,
                {"config.json": '{"model_type":"qwen3_asr"}\n'},
            )
            result = self._run(script, sandbox, environment)

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, "")
            self.assertEqual(
                result.stderr,
                "ASR model is missing safetensors weights\n",
            )

    def test_valid_asr_artifacts_reach_tts_download_and_succeed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            sandbox = Path(temporary_directory)
            script, environment = self._prepare_sandbox(
                sandbox,
                {
                    "config.json": '{"model_type":"qwen3_asr"}\n',
                    "model.safetensors": "representative weights\n",
                },
            )
            result = self._run(script, sandbox, environment)

            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stderr, "")
            self.assertEqual(
                result.stdout,
                "ASR and TTS models downloaded and verified.\n",
            )
            self.assertEqual(
                (sandbox / "models" / "kokoro-v1.0.onnx").read_text(),
                "fixture\n",
            )
            self.assertEqual(
                (sandbox / "models" / "voices-v1.0.bin").read_text(),
                "fixture\n",
            )

    @staticmethod
    def _prepare_sandbox(
        sandbox: Path,
        asr_files: dict[str, str],
    ) -> tuple[Path, dict[str, str]]:
        script = sandbox / "download_models.sh"
        shutil.copy2(ROOT / "download_models.sh", script)

        asr_directory = sandbox / "models" / "Qwen3-ASR-0.6B"
        asr_directory.mkdir(parents=True)
        for name, contents in asr_files.items():
            (asr_directory / name).write_text(contents)

        command_directory = sandbox / "commands"
        command_directory.mkdir()
        DownloadModelsTests._write_executable(
            command_directory / "hf",
            "#!/usr/bin/env bash\nexit 0\n",
        )
        DownloadModelsTests._write_executable(
            command_directory / "curl",
            """#!/usr/bin/env bash
output=""
while (($#)); do
    if [[ "$1" == "--output" || "$1" == "-o" ]]; then
        output="$2"
        shift 2
    else
        shift
    fi
done
mkdir -p "$(dirname "$output")"
printf 'fixture\n' > "$output"
""",
        )

        environment = os.environ.copy()
        environment["PATH"] = f"{command_directory}:{environment['PATH']}"
        return script, environment

    @staticmethod
    def _run(
        script: Path,
        sandbox: Path,
        environment: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", str(script)],
            cwd=sandbox,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _write_executable(path: Path, contents: str) -> None:
        path.write_text(contents)
        path.chmod(path.stat().st_mode | stat.S_IXUSR)


if __name__ == "__main__":
    unittest.main()
