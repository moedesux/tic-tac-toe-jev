# Hard cutover verification

The issue #12 verification run on 2026-10-07 checks the prerequisite issue #11
commit `960f736` and the documentation and audit changes built on it.

## Deterministic evidence

The declared dependency environment passes 82 tests and 43 subtests with
`uv run pytest -q`. Focused command tests pass 41 tests and 15 subtests.
Repository standards pass four tests, including an audit regression that detects
an ignored log and an obsolete cache filename without printing secret content.

`uv run --with mypy mypy scripts/audit_hard_cutover.py scripts/render_architecture.py`
passes for the two new scripts. The repository has no configured whole-project
typechecking gate. `git diff --check` passes.

The diagram renderer regenerates the PNG from the editable graph. Visual
inspection confirms the browser and standalone entry points, command module,
Jev adapter, TypeSafe service, shared GameSession, Pending Command, Structured
Controls, and retained local speech.

## Live service evidence

The original workspace backend starts with `uv run --env-file .env uvicorn
backend.main:app --host 127.0.0.1 --port 8002`. Credential availability is checked
without recording its value. Passive TypeSafe health reports `jev-1.13.0` after
real command requests.

A real Chromium browser creates a game through a Structured Control, places X
at center, submits a typed Natural-Language Control, and observes O at top left
and the rendered command response. A second browser flow starts a new game,
requests a move without a position, verifies no board mutation, supplies
"center", and verifies the completed move and healthy TypeSafe status.
The existing workspace screenshot utility
also runs its three scenarios, including a completed X win, against the live
command route.

The standalone `VoiceTicTacToe` client runs typed simulation with its real
`BackendCommandClient` against the same backend. Start, move, status, and
departure commands pass with real Jev interpretation. TTS is disabled in that
command-transport check.

Production Kokoro synthesis produces a decodable 24000 Hz WAV. Feeding the
result into the production Qwen ASR endpoint returns "Place your mark at
center." This verifies both retained speech engines and endpoint integration.
Microphone capture and audible speaker playback are not exercised by these
checks and remain hardware-dependent manual checks.

## Worktree audit evidence

The isolated implementation worktree passes `scripts/audit_hard_cutover.py`.
The original workspace is scanned separately because it contains ignored
artifacts. Historical operational logs, obsolete local plans, stale compiled
runtime files, and the upstream model README with obsolete terminology are
preserved in an archive outside the repository rather than deleted.

The original untracked screenshot utility is retained as untracked user work.
Its endpoint, port, terminology, and win sequence are updated for the current
architecture. It is not included in the documentation commit.

The final original-workspace audit passes after applying the implementation
and both review corrections. It inventories 213 project files, checks 86 text
files, and inventories 126 binary/cache files. Two Git/dependency directories
are excluded. Sixteen obsolete compiled files are archived outside the
workspace. The directory-symlink and known retired-file regressions pass.
The repository standards test definition changes so that the
accepted decision record is the only project text naming retired technologies.
The audit scans model text too. Git internals and installed dependency
environments are excluded, and binary contents are not semantic evidence.
