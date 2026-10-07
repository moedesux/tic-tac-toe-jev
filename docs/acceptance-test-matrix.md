# Command acceptance test matrix

This matrix is the index from command behavior to deterministic evidence. Update
it whenever command acceptance criteria or test ownership changes.

| Behavior | Deterministic evidence |
| --- | --- |
| All nine positions execute through the command module | `test_confident_move_commands_cover_all_nine_positions` |
| Moves require an existing game | `test_move_requires_game_and_does_not_create_one` |
| Ambiguous or uncertain moves do not mutate the board | `test_ambiguous_move_does_not_mutate_board`; `test_uncertain_position_clarifies_without_mutation` |
| Unique board-relative judgment resolves to a typed position and executes with current-player alternation | `test_unique_board_relative_judgment_returns_typed_position_and_full_game_state`; `test_unique_board_relative_adapter_move_applies_current_mark_and_alternates` |
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
| Compound start with a precise initial move creates the game and places X atomically while retaining start intent | `test_start_with_precise_initial_move_is_one_atomic_start_transition` |
| Compound start without a position starts the game and creates a missing-position pending command | `test_start_with_missing_initial_position_starts_and_waits_for_position` |
| Compound start with an uncertain position starts without moving and creates a confirmation pending command | `test_start_with_uncertain_initial_position_starts_without_moving` |
| TypeSafe failures use stable non-success HTTP mappings and safe request identifiers | `test_typesafe_failure_mapping` |
| TypeSafe health reports configuration and cached command outcomes | `test_typesafe_health_transitions_and_recovery`; `test_successful_uncertainty_is_healthy_http_success`; `test_failed_command_updates_health_and_sanitizes_output` |
| Health polling does not call the interpreter | `test_typesafe_health_endpoint_is_passive` |
| Unsupported compounds execute only the selected supported action | `test_unsupported_compound_executes_only_the_selected_action` |
| Initial move judgment is independently batched by the Jev adapter | `test_start_move_judgment_is_batched_as_an_independent_choice` |
| Replacing an existing game requires stricter start confidence | `test_existing_game_requires_stricter_confidence_to_reset_for_start`; `test_high_confidence_start_can_reset_existing_game` |
| Browser typed text and Web Speech transcripts share the domain command route | `test_browser_controller_smoke` |
| Browser structured controls bypass Jev and remain usable without TypeSafe | `test_browser_controller_smoke`; `test_structured_departure_bypasses_interpretation_and_clears_pending` |
| Browser renders domain responses and passive TypeSafe health | `test_browser_controller_smoke` |
| Standalone microphone and simulation transcripts share the backend command path; responses reach TTS and failures recover | `test/test_standalone_command.py`: `test_microphone_loop_transcribes_then_uses_shared_command_path`; `test_simulation_text_uses_same_path_for_clarification`; `test_backend_failure_is_reported_and_loop_can_continue`; `test_http_adapter_has_bounded_timeout_and_maps_connection_failure`; `test_adapter_matches_representative_real_backend_command_results` |
| Retired command-interpreter runtime, configuration, dependencies, and provider-specific tests are absent | `test_retired_command_interpreter_artifacts_are_absent` |
| Retained speech endpoints decode ASR input and return playable TTS WAV audio after runtime cleanup | `test_transcribe_decodes_audio_and_returns_trimmed_text`; `test_synthesize_returns_playable_mono_wav` |

The test names above live in `test/test_player_command.py`,
`test/test_jev_command_interpreter.py`, `test/test_game_session.py`,
`test/test_game_command_api.py`, `test/test_browser_controller.py`,
`test/test_standalone_command.py`, and `test/test_speech_api.py`.

Speech endpoint contract tests use fake speech engines and do not establish real
model inference. Live ASR and TTS verification requires the retained local speech
assets and their production dependencies.

Live confidence calibration remains a separate migration criterion.

Issue #7 calibration evidence is produced by `uv run python
scripts/evaluate_jev_fixtures.py`. It uses the same `fixtures/command_behaviors.jsonl`
corpus as deterministic tests, skips when `TYPESAFE_API_KEY` is absent, and emits
only aggregate intent/position matches and confidence distributions. The four
policy gates are recorded independently as `read_only_social`, `move`,
`existing_game_reset`, and `position_selection`. The evaluator reports and
checks the resolved `response.model`; production startup pins the validated
version through `TYPESAFE_DEFAULT_MODEL` while allowing an explicit deployment
override. A credential-free invocation still skips clearly.

The calibrated Jev 1.13.0 policy is: baseline/read-only/social `0.60`, move
`0.30`, existing-game reset `0.90`, and position selection `0.40`. Position
reference presence/uniqueness use `0.40`, and pending follow-ups use `0.75`.
Three consecutive pinned evaluations passed with zero canonical, safety, or
composed behavior failures. The final sanitized judgment distributions are in
`docs/calibration/jev-1.13.0.json`.

## Documentation and final cutover acceptance

Issue #12 also requires evidence beyond deterministic command contracts.

| Acceptance criterion | Verification |
| --- | --- |
| Active documentation uses the glossary and describes both entry points, Structured Controls, and local speech | Review `README.md` and `docs/jev-migration-plan.md` against `CONTEXT.md` and executable entry points |
| Setup uses server-side credentials and the validated model | Compare setup instructions with application lifespan and `open_jev_command_interpreter`; live evaluation reports `jev-1.13.0` |
| Operations and troubleshooting match executable behavior | Compare commands with `voice_game.sh`, `download_models.sh`, configuration accessors, CLI help, health routes, and `FAILURE_MAPPINGS` |
| Editable and rendered architecture show command ownership and Pending Command | Run `scripts/render_architecture.py` and inspect `assets/architecture.png` |
| Tracked and ignored project artifacts contain no retired runtime | Run `scripts/audit_hard_cutover.py --root "$PWD"` on every active worktree; `test_retired_command_interpreter_artifacts_are_absent` |
| Only the accepted decision record names retired technologies in project-owned text | Same audit, with the explicit dependency and binary scope described in the architecture explanation |
| Audit detects ignored artifacts and preserves the approved decision record | `test_cutover_audit_detects_ignored_artifacts_without_exposing_content` |
| Deterministic tests and live entry points pass | Full `uv run pytest -q`; real browser game, standalone client against running backend, and separate local speech inference checks |

Record live service and hardware checks separately. Browser controller fakes,
standalone adapter fakes, and speech endpoint fakes cannot replace live checks.
Standalone simulation with TTS disabled establishes command transport but does
not establish audio playback. A TTS WAV round-trip through ASR establishes local
speech inference but does not establish microphone capture or audible output.

## Jev debug capture, issue #16

| Acceptance criterion | Passing deterministic coverage |
| --- | --- |
| Explicit `JEV_DEBUG=true` setting, visible Debug control, initially closed panel and disabled explanation | `test_browser_inspects_actual_exchange_and_disabled_explanation`; `test_enabled_capture_contains_actual_provider_exchange` |
| Actual request state/questions and returned confidence/probabilities with one provider call | `test_enabled_capture_contains_actual_provider_exchange` using the recording TypeSafe provider |
| Request-local correlation under overlapping reverse-order completion; disabled response contract | `test_overlapping_capture_is_submission_local_and_sanitized`; `test_success_response_has_only_domain_fields` |
| Pending entry updates, list selection, separate provider/application summary, payload inspection, literal hostile command | `test_browser_inspects_actual_exchange_and_disabled_explanation` through Chromium and the real command HTTP route |
| Credentials excluded by key and configured-secret substring | `test_overlapping_capture_is_submission_local_and_sanitized` |
| Structured Controls bypass interpreter and preserve authoritative game behavior | Existing command, session and browser controller acceptance suite |

Browser coverage above is deterministic provider integration. Its unrelated
speech health and synthesis requests are intercepted to avoid loading speech
models. Real Jev service capture and browser verification without interception
are separate credential-gated checks, recorded for the parent issue #15.


## Jev failures and application outcomes, issue #17

| Acceptance criterion | Passing deterministic coverage |
| --- | --- |
| Provider failure keeps HTTP status and error detail, includes duration and actual request with safe failure code | `test_failure_preserves_http_contract_and_originating_request` |
| Reverse-order successful and failing submissions remain request-local; capture scope resets and disabled failure contract remains unchanged | `test_failure_preserves_http_contract_and_originating_request` |
| Credential and Authorization strings in provider error bodies or request IDs cannot enter HTTP diagnostics or the panel | `test_failure_preserves_http_contract_and_originating_request`; `test_browser_distinguishes_application_outcomes_from_provider_failure` |
| Jev success displays application rejection and clarification independently, with their returned messages | `test_browser_distinguishes_application_outcomes_from_provider_failure` |
| Failed game refresh preserves already completed Jev success | `test_browser_distinguishes_application_outcomes_from_provider_failure` |
| Rejected move preserves legacy `success=true` HTTP contract and authoritative board when capture is disabled | `test_rejected_move_retains_legacy_contract_without_capture` |

The processor records an excluded domain application outcome because the legacy
command success flag also reports successful processing of rejected moves. Debug
responses expose that outcome without changing ordinary command JSON. Browser
coverage drives real controls and command HTTP routes with a recording provider;
speech requests and the intentional failed game refresh are external test seams.
## Jev payload explorer, issue #18

| Acceptance criterion | Evidence |
| --- | --- |
| Collapsed full request/response and formatted raw JSON below compact SDK judgments | `test_browser_expands_and_copies_sanitized_actual_payloads` through real browser controls |
| Actual submitted state/questions, SDK confidence and probabilities, pending follow-up questions/judgments | `test_browser_expands_and_copies_sanitized_actual_payloads` with recording provider returning declared SDK response models |
| Request/response Copy produces captured sanitized JSON | `test_browser_expands_and_copies_sanitized_actual_payloads` reads the browser clipboard |
| Hostile command markup stays literal and configured credentials are redacted in display/copy | `test_browser_expands_and_copies_sanitized_actual_payloads`, `test_overlapping_capture_is_submission_local_and_sanitized` |
| Available failure payload remains inspectable without fabricated response | Provider failure coverage owned by issue #17; the same expandable payload helper renders failure details |

Browser acceptance isolates speech HTTP boundaries explicitly. It does not verify live ASR, TTS, or external provider calls.

## Jev history and responsive layout, issue #19

| Criterion | Deterministic browser evidence |
| --- | --- |
| Latest 50 exchanges, closed-panel capture, new-game preservation, refresh reset | `test_history_lifetime_selection_retention_and_layout` |
| Preserved selection, new indicator, explicit selected-entry eviction | `test_history_lifetime_selection_retention_and_layout` |
| Clear history and selection, pending response cannot restore cleared entries | `test_history_lifetime_selection_retention_and_layout` |
| Wide side panel and adjustable width, narrow panel below game without page overflow, readable history and expanded details | `test_history_lifetime_selection_retention_and_layout` |
| Independent tab histories and shared authoritative game and Pending Command | `test_two_tabs_have_private_history_and_share_game_and_pending` |
| Debug-only label endpoint redacts configured secrets and explicit credential syntax without Jev calls or game mutations; disabled endpoint discloses no command | `test_debug_label_sanitizes_without_provider_or_game_operations`, `test_disabled_debug_label_discloses_no_command` |
| Pending entries start with numbered generic labels and show server-sanitized Player Commands when labels arrive; configured secrets and explicit credential assignments are excluded, failed label fetch keeps the generic label, and pending raw JSON excludes command text | `test_pending_command_identity_excludes_explicit_credentials_and_raw_payload` |
| Overlapping real submissions in two tabs complete in reverse order with originating request, distinct SDK response, application result, and shared authoritative state preserved | `test_overlapping_tabs_correlate_reverse_completion_and_shared_game` |
| Command submitted while capability fetch is pending retains its correlated response | `test_command_submitted_during_capability_loading_is_correlated` |

These tests drive production browser controls and command routes with the declared
TypeSafe SDK recording provider. Speech routes are isolated at their model
boundary. A separate credential-gated browser run must verify live Jev capture;
deterministic provider results do not establish service availability.
