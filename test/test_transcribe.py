#!/usr/bin/env python3
"""Test script for /api/voice/transcribe endpoint.

Reads a WAV file, converts raw PCM to float32, base64-encodes it,
and sends it to the transcribe endpoint.
"""

import base64
import json
import struct
import sys
import wave
from pathlib import Path

import requests

BASE_URL = "http://localhost:8002"
WAV_FILE = Path(__file__).parent / "test_speech.wav"
ENDPOINT = f"{BASE_URL}/api/voice/transcribe"


def read_wav_as_float32_pcm(wav_path: str) -> tuple[bytes, int]:
    """Read a WAV file and return raw float32 PCM bytes and sample rate.

    The transcribe endpoint expects:
      base64-encoded bytes that, when decoded, produce a np.float32 array.
    """
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        sample_rate = wf.getframerate()
        n_frames = wf.getnframes()
        raw_frames = wf.readframes(n_frames)

    print(f"  WAV info: {n_channels}ch, {sample_width * 8}bit, {sample_rate}Hz, {n_frames} frames")

    # Unpack raw PCM as signed integer samples
    if sample_width == 1:
        fmt = f"{n_frames * n_channels}B"
        samples = struct.unpack(fmt, raw_frames)
        # Normalize from [0, 255] -> [-1.0, 1.0]
        samples = [s / 127.5 - 1.0 for s in samples]
    elif sample_width == 2:
        fmt = f"<{n_frames * n_channels}h"  # little-endian int16
        samples = struct.unpack(fmt, raw_frames)
        # Normalize from [-32768, 32767] -> [-1.0, 1.0]
        samples = [s / 32768.0 for s in samples]
    elif sample_width == 4:
        fmt = f"<{n_frames * n_channels}i"  # little-endian int32
        samples = struct.unpack(fmt, raw_frames)
        samples = [s / 2147483648.0 for s in samples]
    else:
        raise ValueError(f"Unsupported sample width: {sample_width}")

    # Stereo-to-mono conversion: average interleaved channels together
    if n_channels > 1:
        mono_samples = []
        for i in range(0, len(samples), n_channels):
            channel_sum = sum(samples[i + ch] for ch in range(n_channels))
            mono_samples.append(channel_sum / n_channels)
        samples = mono_samples

    # Convert to float32 bytes
    pcm_bytes = struct.pack(f"<{len(samples)}f", *samples)
    return pcm_bytes, sample_rate


def main():
    print(f"Reading WAV file: {WAV_FILE}")
    try:
        pcm_bytes, sample_rate = read_wav_as_float32_pcm(WAV_FILE)
    except FileNotFoundError:
        print(f"ERROR: WAV file not found at {WAV_FILE}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR reading WAV: {e}")
        sys.exit(1)

    print(f"  Parsed {len(pcm_bytes)} bytes of float32 PCM ({len(pcm_bytes) / 4:.0f} samples)")

    # Base64 encode (encode entire buffer at once — chunked encoding corrupts padding)
    audio_b64 = base64.b64encode(pcm_bytes).decode("ascii")
    print(f"  Base64 encoded: {len(audio_b64)} characters")

    # Send to transcribe endpoint
    payload = {
        "audio": audio_b64,
        "sample_rate": sample_rate,
    }

    print(f"\nPOST {ENDPOINT}")
    print(f"  Payload: {json.dumps(payload, default=lambda o: f'<{type(o).__name__}>')[:200]}...")

    try:
        resp = requests.post(ENDPOINT, json=payload, timeout=30)
    except requests.exceptions.ConnectionError:
        print(f"\nERROR: Cannot connect to {BASE_URL}")
        print("  Is the backend running? Try: ./voice_game.sh start")
        sys.exit(1)
    except requests.exceptions.Timeout:
        print(f"\nERROR: Request timed out after 30s")
        sys.exit(1)

    print(f"\n  Status: {resp.status_code}")
    print(f"  Headers: {dict(resp.headers)}")

    try:
        result = resp.json()
        print(f"\n  Response body: {json.dumps(result, indent=2)}")
    except Exception:
        print(f"\n  Response body (raw): {resp.text[:500]}")

    # Summary
    if resp.status_code == 200:
        text = result.get("text", "(no text)")
        print(f"\n  SUCCESS: Transcribed text = \"{text}\"")
    else:
        print(f"\n  FAILED: HTTP {resp.status_code}")
        sys.exit(1)


if __name__ == "__main__":
    main()
