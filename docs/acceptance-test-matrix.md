# Command Acceptance Test Matrix

This matrix is the index from command behavior to deterministic evidence. Update
it whenever command acceptance criteria or test ownership changes.

| Behavior | Deterministic evidence |
| --- | --- |
| All nine positions execute through the command module | `test_confident_move_commands_cover_all_nine_positions` |
| Moves require an existing game | `test_move_requires_game_and_does_not_create_one` |
| Ambiguous or uncertain moves do not mutate the board | `test_ambiguous_move_does_not_mutate_board`; `test_uncertain_position_clarifies_without_mutation` |
| Game rules reject occupied cells and retain win/draw semantics | `test_occupied_move_is_rejected_by_game_rules`; `test_command_moves_preserve_win_and_draw_results` |
| Missing position creates pending state and a follow-up completes it | `test_missing_position_is_completed_by_follow_up_position` |
| Medium-confidence position requires confirmation | `test_proposed_position_requires_affirmation_and_rejection_reopens_choice` |
| Cancellation clears pending; social input preserves it | `test_cancellation_and_social_follow_up_preserve_expected_pending_state` |
| Low-confidence follow-up preserves pending state | `test_low_confidence_follow_up_preserves_pending_move` |
| Confident gameplay replaces pending state | `test_confident_gameplay_replaces_pending_move` |
| Invalid confident replacement still clears pending state | `test_invalid_confident_replacement_also_clears_pending_move` |
| New game clears pending state | `test_new_game_clears_pending_move_and_replaces_state` |
| Game completion clears pending state | `test_game_completion_clears_pending_move` |
| Departure clears pending state | `test_departure_clears_pending_move` |
| Public game operations serialize through one lock | `test_concurrent_public_moves_are_serialized` |
| Pending cancellation, affirmation, and rejection are batched | `test_pending_request_batches_cancellation_affirmation_and_rejection` |
| Command API preserves domain response and no implicit game creation | `test_success_response_has_only_domain_fields`; `test_non_start_request_does_not_implicitly_create_game` |

The test names above live in `test/test_player_command.py`,
`test/test_jev_command_interpreter.py`, `test/test_game_session.py`, and
`test/test_game_command_api.py`.

The bounded start-plus-move behavior and live confidence calibration remain
separate migration criteria; add their evidence here when their owning issues are
implemented.
