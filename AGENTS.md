# Tic-Tac-Toe Agent Guide

Keep this file as a navigation layer. Executable sources and focused docs are the
sources of truth.

## Before implementation

1. Run `uv run python scripts/check_dev_environment.py` from the repository root.
   When prerequisite commits are known, pass each as `--require-ref <ref>`.
2. Read the requested issue and identify prerequisite issues or commits.
3. Confirm the current branch contains those prerequisites with `git log` and
   targeted file checks before editing or delegating work.
4. Preserve unrelated work reported by `git status --short`.

Completion criterion: the target branch, prerequisite code, dependencies, and
starting worktree state are all explicit in the session.

When delegating, assign one implementation owner and one review owner after the
preflight completes. Ask for targeted evidence, wait for a meaningful work
interval, and avoid duplicate delegates or repeated short status polls.

## Navigation

- **Domain language:** read [CONTEXT.md](CONTEXT.md) when naming player commands,
  interpretations, positions, or pending state.
- **Jev migration:** read
  [docs/jev-migration-plan.md](docs/jev-migration-plan.md) for command behavior,
  confidence policy, architecture, and migration completion criteria.
- **Command implementation:** start with `backend/player_command.py`, then
  `backend/jev_command_interpreter.py`, `backend/game_session.py`, and
  `backend/models.py`.
- **Acceptance coverage:** read
  [docs/acceptance-test-matrix.md](docs/acceptance-test-matrix.md) when changing
  command or pending-dialogue behavior.
- **Operations:** use [README.md](README.md), `voice_game.sh`, and the files under
  `config/` for setup, startup, configuration, logs, and troubleshooting.
- **Architecture:** open [architecture.drawio](architecture.drawio) for the full
  component diagram.
- **Review:** apply [CODING_STANDARDS.md](CODING_STANDARDS.md) to every diff.

## Verification

Use `uv` for dependency management and execution. Run the narrowest relevant
tests while iterating, then the full deterministic suite before completion:

```bash
uv run pytest -q test/test_player_command.py test/test_jev_command_interpreter.py
uv run pytest -q test/test_repository_standards.py
uv run pytest -q
```

Tests that require models, hardware, credentials, or running services must be
reported separately from deterministic tests. Never replace a missing production
dependency with a test shim when verifying the real integration.

Completion criterion: every applicable acceptance criterion maps to a passing
test, the full deterministic suite passes, and environment-limited checks are
named precisely.
