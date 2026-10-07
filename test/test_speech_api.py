"""Deterministic speech HTTP contract checks, separate from real model inference."""

import base64
import io
import unittest
import wave
from unittest.mock import patch

import httpx
import numpy as np

from backend.main import app


class SpeechApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_transcribe_decodes_audio_and_returns_trimmed_text(self) -> None:
        test_case = self

        class SpeechRecognizer:
            def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
                np.testing.assert_array_equal(audio, [0.0, 0.25, -0.5])
                test_case.assertEqual(sample_rate, 16000)
                return "  place a mark in the center  "

        encoded = base64.b64encode(
            np.array([0.0, 0.25, -0.5], dtype=np.float32).tobytes()
        ).decode("ascii")
        with patch("backend.main._asr_instance", SpeechRecognizer()):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/api/voice/transcribe",
                    json={"audio": encoded, "sample_rate": 16000},
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"text": "place a mark in the center"})

    async def test_synthesize_returns_playable_mono_wav(self) -> None:
        test_case = self

        class SpeechSynthesizer:
            def synthesize(self, text: str) -> tuple[np.ndarray, int]:
                test_case.assertEqual(text, "X goes first.")
                return np.array([0.0, 0.5, -0.5], dtype=np.float32), 24000

        with patch("backend.main._tts_instance", SpeechSynthesizer()):
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                response = await client.post(
                    "/api/voice/synthesize", json={"text": "X goes first."}
                )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sample_rate"], 24000)
        audio = base64.b64decode(response.json()["audio"])
        with wave.open(io.BytesIO(audio), "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getsampwidth(), 2)
            self.assertEqual(wav_file.getframerate(), 24000)
            self.assertEqual(wav_file.getnframes(), 3)
            self.assertEqual(wav_file.readframes(3), b"\x00\x00\xff\x3f\x01\xc0")
