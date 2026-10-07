# Speech and standalone client

Players speak commands through the browser or standalone microphone client, and hear responses through local TTS.

## Sub-features

- `browser-microphone` turns speech into a Player Command.
- `browser-response-audio` plays a synthesized response when enabled.
- `standalone-simulation` accepts typed transcripts against the shared backend.
- `standalone-microphone` records between Enter presses and transcribes locally.

## How to get to it (user POV)

Open `/` or `/index.html`, enable Speak Responses, and choose the microphone button. Alternatively run `uv run python voice_tic_tac_toe.py` or add `--simulation` for typed input.

## Driving it with Playwright and a terminal

Preconditions: declared dependencies and provider credentials on the server. Local transcription needs Qwen assets; synthesis needs Kokoro assets. Standalone simulation skips Qwen and loads Kokoro only when `tts.enabled=true`. Hardware checks need microphone and output devices, a controlled spoken command, and an observer for audible playback. Browser microphone needs permission and a supported secure context. Run speech checks serially.

- In Playwright, use `page.locator("#tts-toggle").check()` and click `#mic-btn`. Speak `start a game`, then `place a mark`, then `center`. Capture transcript, command response, resulting board, and microphone permission outcome. Browser recognition may bypass `/api/voice/transcribe`; capture which route actually ran.
- Send a typed command with speech enabled. Observe POST `/api/voice/synthesize`, record response sample rate and nonempty decoded WAV metadata, and verify audible playback on a machine with output devices. A successful WAV response alone does not prove playback.
- The standalone CLI has no backend URL flag. Create a scratch copy of the client and config, then change only that copy's `api_gateway.base_url` to the exact owned backend URL. From the repository root, run this setup with that URL as its first argument:

```bash
uv run python - http://127.0.0.1:PORT <<'PY'
import configparser
from pathlib import Path
import shutil
import sys
import tempfile

scratch = Path(tempfile.mkdtemp(prefix="tic-tac-toe-client-"))
shutil.copy2("voice_tic_tac_toe.py", scratch)
shutil.copytree("config", scratch / "config")
config = configparser.ConfigParser(interpolation=None)
path = scratch / "config/voice.conf"
config.read(path)
config.set("api_gateway", "base_url", sys.argv[1])
with path.open("w") as output:
    config.write(output)
print(scratch)
PY
```

- Replace PORT with your owned backend port. Use the printed scratch path in `PYTHONPATH="$PWD" uv run python /tmp/tic-tac-toe-client-ACTUAL/voice_tic_tac_toe.py --simulation`. The scratch script imports its adjacent copied config and other production modules from the repository. Keep the working directory at the repository root for model paths. In the owned PTY, type `start a game` and `center`, then preserve the terminal transcript plus GET `/api/game` state. The checked-in configuration enables TTS, so this run loads Kokoro and attempts playback.
- For microphone mode, launch the scratch client without `--simulation`, follow its Enter prompts to record a command, and capture transcript, backend response, board, and audible output. Stop the exact owned client process on success or failure. Remove only the scratch client directory you created after stopping it; preserve proof artifacts elsewhere.

## Gotchas

Headless synthetic input does not establish physical microphone or speaker behavior. Report missing devices, model assets, credentials, and provider errors separately. Health routes can load models, and degraded speech health is not success. Keep actual audio evidence free of unrelated conversation. The baseline helper does not verify any speech feature.
