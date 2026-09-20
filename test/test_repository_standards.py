"""Automated checks for repository boundaries and acceptance-test navigation."""

from __future__ import annotations

import ast
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SESSION_HELPERS = {"_response", "_create_unlocked", "_move_unlocked"}


class RepositoryStandardsTests(unittest.TestCase):
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
