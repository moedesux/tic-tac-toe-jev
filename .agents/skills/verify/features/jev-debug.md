# Jev exchange debugging

## Sub-features

- `jev-debug-configuration` shows the disabled explanation or enables capture after a backend restart.
- `jev-debug-command` records typed and spoken commands from this tab.
- `jev-debug-structured` keeps direct game actions out of Jev history.
- `jev-debug-history` retains, selects, clears, and copies exchanges independently of shared game state.

## Driving it with Playwright

Use an isolated backend from [verify](../SKILL.md), with `JEV_DEBUG=true` and credentials loaded for live commands. Open `/index.html`. Uncheck `#tts-toggle` to silence responses. Speech health requests can still load models.

1. Read GET `/api/debug/jev` and require `enabled == true`. Click `#jev-debug-button`. Require `#jev-debug-panel` visible and its configuration explanation hidden. Its empty detail must explain typed or spoken commands, Send or Enter, and direct game buttons.
2. Click `[data-cmd="start_game"]`, then `.cell[data-position="0"]`, then `.position-buttons [data-row="1"][data-col="1"]`. Wait for POST `/api/game` and each POST `/api/game/move`. Require X at index zero and O at index four in the DOM and GET `/api/game`. Require no `.jev-exchange-entry` in this tab.
3. Fill `#voice-input` with `start a game` and click `#send-cmd-btn` inside `page.expect_response` for POST `/api/game/command`. Require a Jev exchange in the actual response and a matching history entry. Record the application outcome and verify its authoritative board. Submit another command using Enter and require another entry. Successful Jev requests make passive TypeSafe health healthy; the badge updates on its next poll.
4. Select an entry, inspect Full request and Full response, and use its Copy buttons. Verify copied JSON matches the selected payload. Close Debug, submit a command, reopen it, and require the captured entry. New games preserve history. Click `#jev-debug-clear` and require empty entries and selection.
5. Open another tab connected to the same backend. Require shared game state and empty history there. Commands submitted in one tab appear only in that tab. Refresh clears its history. For the 50-entry retention boundary and pending-response clear race, run the focused browser contract tests and report them separately from live checks.
6. On a separate backend with capture disabled, require `enabled == false` and the visible `JEV_DEBUG=true` explanation. Submit a typed command and require its normal domain result without `jev_exchange`.

## Evidence and limits

Keep actual command responses, screenshots, authoritative state, clipboard JSON, and cleanup evidence. `TYPESAFE: UNVERIFIED` means configured with no Jev request observed yet. Structured Controls do not verify the provider. Spoken commands use the [speech recipes](speech.md); physical microphone input and audible playback need human confirmation.
