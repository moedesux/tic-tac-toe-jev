# Jev Debug explorer

Players inspect the actual Jev exchange and application result for a Natural-Language Control.

## Sub-features

- `debug-capability` shows capture controls when enabled and an enablement explanation otherwise.
- `debug-exchange` captures commands even while the panel is closed and separates provider judgments from application outcomes.
- `debug-history` preserves selection and history across new games, with clear and refresh controls.
- `debug-layout` adjusts panel width and places the panel below the game on narrow screens.

## How to get to it (user POV)

Choose Debug on `/`, `/index.html`, or `/regular_game.html`. Typed commands are available on the full page. The regular page has the explorer but no typed command field.

## Driving it with Playwright

Preconditions: healthy isolated backend launched with `JEV_DEBUG=true`. Load provider credentials for real exchange payloads. Require GET `/api/debug/jev` to return `enabled == true` before driving capture.

- On the full page, submit a typed command while Debug is closed. Click `#jev-debug-button`, then a `.jev-exchange-entry`. Require provider status and a separate `Application:` result in `.jev-exchange-detail`, matching the captured command response. Expand Full request and Full response to inspect payloads. With browser clipboard permission, click Copy full request and require Copied feedback.
- Submit a second command so history contains two completed entries. Select the older entry, submit another command, and require the inspected entry to remain selected. Click `#jev-debug-new` to inspect the latest entry. Start a new game through Structured Controls and require unchanged history length.
- Open another tab on the same backend. Require its history to be empty while its game matches GET `/api/game`. Click `#jev-debug-clear` in the original tab and require no entries or selected payload. Refresh and require empty history again.
- At a 1600-pixel viewport, change `#jev-debug-width` within its 400–700 range and inspect the panel beside the game. At a 390-pixel viewport, require readable controls below the game and no horizontal page overflow. Save screenshots at both widths.
- In a separate backend launched with `JEV_DEBUG=false`, repeat doctor and require disabled capability. Open Debug and require the enablement explanation with `.jev-debug-controls` hidden. Structured gameplay must still work.

## Gotchas

History belongs to one tab's memory and retains only the latest 50 exchanges. Backend game and Pending Command state remain shared. Structured Controls bypass Jev and create no exchange. Provider failures can have failure diagnostics instead of a successful response payload.

Retention eviction, clearing while a request is pending, clipboard denial, and provider failures need their specific conditions. Record those branches separately when exercised. Use the production integration for live evidence. Never add a fake provider to manufacture capture proof. Keep captured credentials out of evidence.
