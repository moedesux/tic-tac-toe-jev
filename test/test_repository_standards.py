"""Automated checks for repository boundaries and acceptance-test navigation."""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SESSION_HELPERS = {"_response", "_create_unlocked", "_move_unlocked"}


class RepositoryStandardsTests(unittest.TestCase):
    def test_retired_command_interpreter_artifacts_are_absent(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/audit_hard_cutover.py"), "--root", str(ROOT)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_cutover_audit_detects_ignored_artifacts_without_exposing_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "backend").mkdir()
            (root / "backend/main.py").touch()
            record = root / "docs/adr/0001-use-jev-for-command-interpretation.md"
            record.parent.mkdir(parents=True)
            retired_name = bytes.fromhex("67656d6d61").decode()
            record.write_text(retired_name)
            command = [sys.executable, str(ROOT / "scripts/audit_hard_cutover.py"), "--root", str(root)]
            clean = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(0, clean.returncode, clean.stdout + clean.stderr)
            (root / ".gitignore").write_text("*.log\n")
            (root / "obsolete.log").write_text(retired_name + " secret-value-must-stay-private")
            failed = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(1, failed.returncode)
            self.assertIn("FAIL: obsolete.log", failed.stdout)
            self.assertNotIn("secret-value-must-stay-private", failed.stdout)
            self.assertNotIn(retired_name, failed.stdout)
            (root / "obsolete.log").unlink()
            cache = root / "__pycache__"
            cache.mkdir()
            retired_file = bytes.fromhex("766f6963655f67616d655f6f7263686573747261746f722e707963").decode()
            (cache / retired_file).write_bytes(b"\x00compiled-code")
            cached = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(1, cached.returncode)
            self.assertIn("FAIL: __pycache__/" + retired_file, cached.stdout)

    def test_game_session_private_helpers_stay_inside_game_session_module(self) -> None:
        violations: list[str] = []
        for path in (ROOT / "backend").glob("*.py"):
            if path.name == "game_session.py":
                continue
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and node.attr in PRIVATE_SESSION_HELPERS:
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno}:{node.attr}")

        self.assertEqual([], violations)

    def test_acceptance_matrix_names_existing_tests(self) -> None:
        matrix = (ROOT / "docs" / "acceptance-test-matrix.md").read_text()
        referenced = set(re.findall(r"`(test_[a-z0-9_]+)`", matrix))
        discovered: set[str] = set()
        for path in (ROOT / "test").glob("test_*.py"):
            tree = ast.parse(path.read_text(), filename=str(path))
            discovered.update(
                node.name
                for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test_")
            )

        self.assertTrue(referenced, "acceptance matrix must reference tests")
        self.assertEqual(set(), referenced - discovered)


if __name__ == "__main__":
    unittest.main()
