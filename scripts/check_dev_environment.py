"""Fail fast when the repository is not ready for deterministic development."""

from __future__ import annotations

import importlib.util
import argparse
import subprocess
import sys
from pathlib import Path


REQUIRED_MODULES = (
    "fastapi",
    "httpx",
    "pydantic",
    "pytest",
    "typesafe_sdk",
)


def git(*args: str) -> str:
    return subprocess.run(
        ("git", *args),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--require-ref",
        action="append",
        default=[],
        help="commit or ref that must be an ancestor of HEAD; may be repeated",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    if Path.cwd().resolve() != root:
        print(f"error: run from repository root: {root}", file=sys.stderr)
        return 1

    missing = [name for name in REQUIRED_MODULES if importlib.util.find_spec(name) is None]
    branch = git("branch", "--show-current") or "detached HEAD"
    status = git("status", "--short")

    print(f"branch: {branch}")
    print("worktree: clean" if not status else f"worktree changes:\n{status}")

    missing_refs = []
    for required_ref in args.require_ref:
        result = subprocess.run(
            ("git", "merge-base", "--is-ancestor", required_ref, "HEAD"),
            check=False,
        )
        if result.returncode:
            missing_refs.append(required_ref)
    if missing_refs:
        print(
            "error: HEAD does not contain required refs: " + ", ".join(missing_refs),
            file=sys.stderr,
        )
        return 1
    if args.require_ref:
        print("prerequisite refs: present")

    if missing:
        print(
            "error: missing Python modules: " + ", ".join(missing),
            file=sys.stderr,
        )
        print("install with: uv pip install -r requirements.txt", file=sys.stderr)
        return 1

    print("dependencies: ready")
    print("next: verify this branch contains the requested issue prerequisites")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
