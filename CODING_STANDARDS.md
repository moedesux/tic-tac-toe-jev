# Coding Standards

These rules are enforced during review rather than loaded into implementation
context.

## Boundaries

- `GameSession` is the authoritative asynchronous boundary for shared game and
  pending-command state.
- Code outside `backend/game_session.py` uses public `GameSession` methods and
  the `locked()` context manager. Calls to private helpers such as `_response`,
  `_create_unlocked`, and `_move_unlocked` outside that module are review
  failures.
- Application command processing calls game operations in process. It does not
  call the application's own HTTP routes.
- TypeSafe SDK response objects remain inside `backend/jev_command_interpreter.py`;
  only domain interpretation types cross into command processing.

## Command behavior

- Application code owns legality, state transitions, pending dialogue,
  confidence policy, and response text. Jev supplies bounded judgments only.
- A confident replacement clears pending state even when deterministic game
  rules reject the replacement.
- Unclear or low-confidence follow-ups preserve pending state. Social commands
  preserve it unless the player departs.
- New games, completed games, cancellation, departure, and successful pending
  completion clear pending state.
- Pending cancellation, affirmation, and rejection judgments share the same Jev
  request as the other interpretation judgments.

## Tests

- Every command-state transition has deterministic coverage through the fake
  interpreter seam.
- Acceptance tests assert both the returned command result and authoritative
  session state where state changes are involved.
- Tests use the real declared Python dependencies. A local stand-in may support
  isolated development, but it cannot count as integration verification.
- Update `docs/acceptance-test-matrix.md` when an acceptance criterion or its
  owning test changes.

## Review checklist

1. Compare the diff with the originating issue and its prerequisite issues.
2. Check the public session boundary and TypeSafe adapter boundary.
3. Account for every changed state transition in the acceptance matrix.
4. Verify focused tests and the full deterministic suite were run in the declared
   dependency environment.
5. Report hardware-, credential-, model-, or service-dependent checks separately.
