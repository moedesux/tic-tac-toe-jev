import argparse
import asyncio
import unittest
from unittest.mock import patch

import httpx
import numpy as np

from backend_command_client import BackendCommandClient, BackendCommandError
from backend.game_session import GameSession
from backend.main import app, get_command_processor
from backend.models import CommandIntent, MovePosition
from backend.player_command import CommandInterpretation, PlayerCommandProcessor
from test.fakes import FakeCommandInterpreter
from voice_tic_tac_toe import VoiceTicTacToe, _validate_config


class FakeASR:
    def transcribe(self, audio, sample_rate):
        return "start game"


class FakeTTS:
    def __init__(self):
        self.messages = []

    def synthesize(self, message):
        self.messages.append(message)
        return object(), 16000


class FakeCommands:
    def __init__(self, results):
        self.results = iter(results)
        self.transcripts = []

    def process(self, transcript):
        self.transcripts.append(transcript)
        result = next(self.results)
        if isinstance(result, Exception):
            raise result
        return result


class StandaloneCommandTests(unittest.TestCase):
    def test_simulation_validation_skips_asr_dependency_and_model(self):
        args = argparse.Namespace(asr_model="/does/not/exist", tts_model="", tts_voices="")
        _validate_config(args, tts_enabled=False, simulation=True)

    def make_voice(self, commands, tts=None):
        voice = VoiceTicTacToe(FakeASR(), commands, tts)
        voice.play_audio = lambda audio, sample_rate: None
        return voice

    def test_microphone_transcript_uses_shared_command_endpoint_and_tts(self):
        commands = FakeCommands([{"message": "Started", "intent": "start_game"}])
        tts = FakeTTS()
        voice = self.make_voice(commands, tts)
        self.assertFalse(voice.process_transcript("start game"))
        self.assertEqual(commands.transcripts, ["start game"])
        self.assertEqual(tts.messages, ["Started"])

    def test_microphone_loop_transcribes_then_uses_shared_command_path(self):
        commands = FakeCommands([{"message": "Started", "intent": "start_game"}])
        tts = FakeTTS()
        voice = self.make_voice(commands, tts)
        with patch.object(
            voice,
            "record_utterance",
            side_effect=[(np.ones(3), 16000), EOFError],
        ):
            voice.run()
        self.assertEqual(commands.transcripts, ["start game"])
        self.assertEqual(tts.messages, ["Started"])

    def test_simulation_text_uses_same_path_for_clarification(self):
        commands = FakeCommands([{"message": "Which square?", "intent": "place_move"}])
        tts = FakeTTS()
        voice = self.make_voice(commands, tts)
        with patch("builtins.input", side_effect=["center", EOFError]):
            voice.run_simulation()
        self.assertEqual(commands.transcripts, ["center"])
        self.assertEqual(tts.messages, ["Which square?"])

    def test_backend_failure_is_reported_and_loop_can_continue(self):
        commands = FakeCommands(
            [BackendCommandError("timed out"), {"message": "OK", "intent": "thanks"}]
        )
        voice = self.make_voice(commands)
        self.assertFalse(voice.process_transcript("hello"))
        self.assertFalse(voice.process_transcript("thanks"))

    def test_http_adapter_has_bounded_timeout_and_maps_connection_failure(self):
        client = BackendCommandClient("http://backend", timeout=2.5)
        with patch(
            "backend_command_client.requests.post",
            side_effect=__import__("requests").exceptions.Timeout,
        ) as post:
            with self.assertRaisesRegex(BackendCommandError, "timed out"):
                client.process("hello")
        self.assertEqual(post.call_args.kwargs["timeout"], 2.5)

    def test_http_adapter_posts_domain_control_and_decodes_browser_shape(self):
        client = BackendCommandClient("http://backend")
        expected = {
            "success": True,
            "message": "New game started. X goes first.",
            "intent": "start_game",
            "position": None,
            "confidence": 0.97,
            "clarification_required": False,
            "pending": None,
        }
        response = unittest.mock.Mock(ok=True)
        response.json.return_value = expected
        with patch("backend_command_client.requests.post", return_value=response) as post:
            result = client.process("Start a game")
        self.assertEqual(result, expected)
        post.assert_called_once_with(
            "http://backend/api/game/command",
            json={"control": "Start a game"},
            timeout=10.0,
        )

    def test_adapter_matches_representative_real_backend_command_results(self):
        session = GameSession()
        processor = PlayerCommandProcessor(
            FakeCommandInterpreter(
                [
                    CommandInterpretation(CommandIntent.START_GAME, confidence=0.97),
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        confidence=0.95,
                        position=MovePosition.CENTER,
                        position_confidence=0.95,
                        position_present_confidence=0.95,
                        position_unique_confidence=0.95,
                    ),
                    CommandInterpretation(
                        CommandIntent.PLACE_MOVE,
                        confidence=0.95,
                    ),
                ]
            ),
            session,
        )
        controls = ["Start a game", "Move center", "Make a move"]

        async def request():
            app.dependency_overrides[get_command_processor] = lambda: processor
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://testserver"
            ) as client:
                responses = [
                    await client.post(
                        "/api/game/command", json={"control": control}
                    )
                    for control in controls
                ]
            state = await session.read()
            async with session.locked():
                pending = session.pending
            return responses, state, pending

        try:
            responses, state, pending = asyncio.run(request())
        finally:
            app.dependency_overrides.clear()
        expected = [response.json() for response in responses]
        fake_responses = []
        for result in expected:
            fake_response = unittest.mock.Mock(ok=True)
            fake_response.json.return_value = result
            fake_responses.append(fake_response)
        with patch(
            "backend_command_client.requests.post", side_effect=fake_responses
        ):
            actual = [
                BackendCommandClient("http://testserver").process(control)
                for control in controls
            ]
        self.assertEqual(actual, expected)
        self.assertEqual(state.board[MovePosition.CENTER.cell_index], "X")
        self.assertIsNotNone(pending)


if __name__ == "__main__":
    unittest.main()
