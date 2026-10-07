"""Audit current project artifacts without printing matched text or secrets."""

from __future__ import annotations

import argparse
import os
import re
from pathlib import Path


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--root", type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
if not (root / "backend/main.py").is_file():
    parser.error("root must be a project worktree")

approved = Path("docs/adr/0001-use-jev-for-command-interpretation.md")
vendor = {".git", ".venv", "venv", "ENV"}
caches = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
# Encode the policy so the audit itself does not name retired technologies.
retired = re.compile(
    bytes.fromhex(
        "5c62283f3a67656d6d617c6c6c616d617c736c6d295c627c6f70656e61697c766f6963655f67616d"
        "655f6f7263686573747261746f727c766f6963655f67616d655f696e746572666163657c766f6963"
        "655f67616d655f636f6e6669677c6170692f766f6963652f636f6d6d616e647c66696e655b5f202d"
        "5d3f74756e696e675b5f202d5d3f283f3a646174617c6d6f64656c297c67656e65726174655b5f20"
        "2d5d3f646174617365747c746573745f616c6c5f746f6f6c5f63616c6c737c746573745f73696d70"
        "6c655f746f6f6c5f63616c6c73"
    ).decode(),
    re.IGNORECASE,
)
violations: set[str] = set()
files = texts = binaries = excluded = 0
for directory, directories, filenames in os.walk(root, followlinks=False):
    relative_directory = Path(directory).relative_to(root)
    for name in directories[:]:
        relative = relative_directory / name
        if name in vendor:
            directories.remove(name)
            excluded += 1
        else:
            if retired.search(str(relative)) or retired.search(str(relative).replace("_", " ")):
                violations.add(str(relative))
            path = root / relative
            if path.is_symlink() and retired.search(os.readlink(path)):
                violations.add(str(relative))
    for name in filenames:
        path = Path(directory) / name
        relative = path.relative_to(root)
        files += 1
        if relative == approved:
            continue
        if retired.search(str(relative)) or retired.search(str(relative).replace("_", " ")):
            violations.add(str(relative))
        if any(part in caches for part in relative.parts):
            binaries += 1
            continue
        if path.is_symlink():
            if retired.search(os.readlink(path)):
                violations.add(str(relative))
            binaries += 1
            continue
        with path.open("rb") as stream:
            prefix = stream.read(8192)
            if b"\0" in prefix:
                binaries += 1
                continue
            stream.seek(0)
            for line in stream:
                if retired.search(line.decode("utf-8", errors="replace")):
                    violations.add(str(relative))
        texts += 1

print(f"Audited {files} project files, {texts} text files, {binaries} binary/cache files")
print(f"Excluded {excluded} Git/dependency directories; binary/cache contents are not semantic evidence")
print("Approved historical decision record: " + str(approved))
for violation in sorted(violations):
    print("FAIL: " + violation)
print("FAIL: retired artifacts remain" if violations else "PASS: no retired project artifacts found")
raise SystemExit(bool(violations))
