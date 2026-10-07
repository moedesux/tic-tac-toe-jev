# Jev command interpretation architecture

## Outcome

TypeSafe Jev supplies bounded, typed judgments for Natural-Language Controls.
Application code owns game rules, state transitions, Pending Commands,
confidence policy, and deterministic response text. Local ASR and TTS remain
available for speech input and output.

Production has one command-interpretation path. Structured Controls bypass Jev
and call game operations directly, so visual gameplay remains available when
TypeSafe is unavailable.

## Command path

`PlayerCommandProcessor.process` is the public command boundary. It sends the
utterance, board, current mark, game status, and optional Pending Command to the
Jev adapter in one batched request. Only domain interpretation values leave the
adapter; TypeSafe SDK objects remain inside
`backend/jev_command_interpreter.py`.

The processor applies the calibrated confidence policy, updates Pending Command
state, invokes `GameSession` in process, and returns a domain `CommandResult`.
FastAPI owns the TypeSafe client for its application lifetime.

The browser and standalone microphone client both use
`POST /api/game/command`. The standalone client is a separate process and uses
`backend_command_client.py`; browser Structured Controls call the direct game
endpoints.

## Dialogue and confidence

A Pending Command either lacks a Move Position or holds a proposed position
awaiting confirmation. Completion, cancellation, confident replacement, a new
game, game completion, or departure clears it. Social and unclear follow-ups
preserve it.

Commands normally execute one action. Starting a game with an initial move is
the single bounded composition. Read-only/social commands, moves, existing-game
resets, and position selection use separate confidence gates recorded in
`docs/calibration/jev-1.13.0.json`.

## Operations

Server credentials come from `TYPESAFE_API_KEY`; the validated production model
defaults to `jev-1.13.0` and can be overridden by `TYPESAFE_DEFAULT_MODEL`. `GET /api/health/typesafe` is passive and
reports cached outcomes from real command requests without making provider
calls.

`voice_game.sh` manages only the FastAPI backend. `download_models.sh` downloads
and verifies only the retained Qwen ASR and Kokoro TTS assets.

## Verification

- Deterministic command behavior uses the fake interpreter boundary.
- Curated provider-neutral cases live in `fixtures/command_behaviors.jsonl`.
- Browser and standalone smoke tests exercise the common command endpoint.
- Repository standards audit the completed runtime cutover.
- Credential-gated evaluation uses `scripts/evaluate_jev_fixtures.py`.

The behavior-to-test mapping is maintained in
`docs/acceptance-test-matrix.md`. Historical architectural rationale is retained
only in `docs/adr/0001-use-jev-for-command-interpretation.md`.

## Diagram and cutover evidence

`architecture.drawio` is the editable component graph. After editing its labels
or connections, run `uv run python scripts/render_architecture.py` with Graphviz
installed to regenerate `assets/architecture.png`. The renderer reads that graph
rather than maintaining a second set of component labels.

Run `uv run python scripts/audit_hard_cutover.py --root "$PWD"` in each active
worktree, including the original workspace. A clean implementation worktree does
not establish that ignored artifacts in another worktree are clean.

The audit inventories tracked, untracked, and ignored project files, including
logs, configuration, model filenames, process files, and cache filenames. It
checks text content and symlink targets without printing matched text or secrets.
The accepted decision record is the only exception for project-owned text.
Git internals and installed dependency environments are excluded. Binary
contents and cache contents cannot establish semantic provenance. Model text and configuration are scanned too. These scope limits are
reported by the audit.

An audit failure names the file for investigation. Preserve unrelated work and
credentials. Archive historical operational artifacts outside the repository,
then rerun the audit. Do not delete a model based only on an upstream comparison
or a generic metadata field.
