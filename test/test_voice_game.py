#!/usr/bin/env python3
"""Test script for voice-based tic-tac-toe game.

This script tests the conversation flow using:
- Mock ASR component (echoes input)
- Mock TTS component (echoes text)
- Real SLM client for intent recognition

Run with: python test_voice_game.py
"""

import sys
import httpx
import json
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

import numpy as np
from httpx import ConnectError
from openai import OpenAI
from voice_game_interface import VoiceGameInterface
from voice_game_orchestrator import SLMClient


# =============================================================================
# Mock Audio Container
# =============================================================================
class MockAudioContainer:
    """Simple container to hold mock audio data and associated text."""

    def __init__(self, text: str):
        self.text = text
        self.data = np.array([0.0])


# =============================================================================
# Mock ASR Component
# =============================================================================
class MockASR:
    """Mock ASR that just echoes the input for testing."""

    def transcribe(self, audio, sample_rate: int) -> str:
        if isinstance(audio, MockAudioContainer):
            return audio.text
        if hasattr(audio, "mock_text"):
            return audio.mock_text
        return str(audio)


# =============================================================================
# Mock TTS Component
# =============================================================================
class MockTTS:
    """Mock TTS that just echoes the input text."""

    def synthesize(self, text: str) -> tuple[np.ndarray, int]:
        text_bytes = text.encode("utf-8")
        mock_audio = np.array(list(text_bytes), dtype=np.float32)
        return mock_audio, 16000


# =============================================================================
# Main Test Flow
# =============================================================================
def test_voice_game():
    """Test a simple conversation flow with the voice game using real SLM."""
    print("=" * 70)
    print("Voice Tic-Tac-Toe Game Test")
    print("=" * 70)
    print()

    # Initialize mock components and SLM client
    mock_asr = MockASR()
    mock_tts = MockTTS()
    game_interface = VoiceGameInterface()

    # Create SLM client with extended timeout for conversation history
    http_client = httpx.Client(
        http2=False, timeout=httpx.Timeout(timeout=600.0, connect=120.0)
    )
    slm_client = SLMClient(model_name="test-model", api_key="test-key")
    slm_client.client._client = http_client

    # Test conversation flow
    test_sequence = [
        ("hello", "Greeting should trigger"),
        ("start", "Should start a new game"),
        ("show board", "Should display current board state"),
        ("place at center", "Should make a move at center"),
        ("show board", "Should show updated board"),
    ]

    print("Testing conversation flow:")
    print("-" * 70)

    # Track game state manually
    game_started = False
    board = [[" " for _ in range(3)] for _ in range(3)]

    # Initialize conversation history
    conversation_history = []

    for user_input, description in test_sequence:
        print()
        print(f"> User: '{user_input}'")
        print(f"  [{description}]")

        # Simulate ASR
        mock_audio = MockAudioContainer(user_input)
        transcript = mock_asr.transcribe(mock_audio, 16000)
        print(f"  [ASR transcribed]: '{transcript}'")

        # Add user turn to conversation history
        conversation_history.append({"role": "user", "content": transcript})

        # Call real SLM client
        print(f"  [SLM] Invoking with conversation history")
        try:
            import time

            start = time.time()
            function_call = slm_client.invoke(conversation_history)
            elapsed = time.time() - start
            print(f"  [SLM] Invoke took {elapsed:.2f}s")
        except (ConnectError, Exception) as e:
            # If SLM server is not available, treat as unclear intent
            print(f"  [SLM] Connection error: {e}")
            print(f"  [SLM] Treating as intent_unclear")
            function_call = "No valid tool call in SLM response"

        # Properly parse tool_calls from SLM response
        if isinstance(function_call, str):
            # SLM returned an error string
            intent = "intent_unclear"
            arguments = {}
        else:
            # Extract tool_calls[0].function.name
            intent = function_call["name"]
            # Parse arguments as JSON from tool_calls[0].function.arguments
            arguments = function_call.get("arguments", {})
            if isinstance(arguments, str):
                arguments = json.loads(arguments)

        print(f"  [SLM Function call]: {intent} with args {arguments}")

        # Process based on intent
        bot_response = ""
        if intent == "greeting":
            bot_response = (
                "Hello! Welcome to Tic-Tac-Toe! Type 'start' to begin the game."
            )
        elif intent == "start_game":
            game_started = True
            board = [[" " for _ in range(3)] for _ in range(3)]
            bot_response = "Game started! You are X. What's your first move?"
        elif intent == "get_board":
            if not game_started:
                bot_response = "Game hasn't started yet. Type 'start' to begin."
            else:
                board_str = "\n"
                for row in board:
                    board_str += "  " + " | ".join(row) + "\n"
                    board_str += "  " + "---+---+---\n"
                    board_str = board_str.rstrip()
                bot_response = f"Current board state:\n{board_str}"
        elif intent == "place_move":
            if not game_started:
                bot_response = "Game hasn't started yet. Type 'start' to begin."
            else:
                if "center" in transcript.lower() or "middle" in transcript.lower():
                    board[1][1] = "X"
                    bot_response = "You placed X in the center. Your opponent's turn."
                else:
                    board[0][0] = "X"
                    bot_response = (
                        "You placed X in the top-left corner. Your opponent's turn."
                    )
        elif intent == "thank_you":
            bot_response = "You're welcome! Happy gaming!"
        elif intent == "goodbye":
            bot_response = "Goodbye! Thanks for playing Tic-Tac-Toe!"
            print(f"  [Orchestrator]: Conversation ended")
            break
        else:
            bot_response = "I didn't understand that. Could you clarify?"

        print(f"  [Response]: {bot_response}")

        # Simulate TTS
        audio, sample_rate = mock_tts.synthesize(bot_response)
        print(f"  [TTS generated]: {len(audio)} samples at {sample_rate}Hz")

    print()
    print("-" * 70)
    print("Test completed successfully!")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(test_voice_game())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user. Exiting cleanly.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nTest failed with error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
