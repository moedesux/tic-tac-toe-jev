#!/usr/bin/env python3
"""Simple test script for SLM tool calls."""

import json
import sys
import time
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from openai import OpenAI
import httpx

# Test cases for each tool
TEST_CASES = [
    # (input, expected_tool, expected_args, description)
    # GREETING TESTS
    ("hello", "greeting", None, "Simple hello"),
    ("hi there", "greeting", None, "Casual hi"),
    ("good morning", "greeting", None, "Time-based greeting"),
    ("how are you", "greeting", None, "How are you greeting"),
    # START_GAME TESTS
    ("start a new game", "start_game", None, "Start new game"),
    ("let's play", "start_game", None, "Let's play"),
    ("begin the game", "start_game", None, "Begin game"),
    ("I want to play", "start_game", None, "Want to play"),
    # GET_BOARD TESTS
    ("show me the board", "get_board", None, "Show me board"),
    ("what's on the board", "get_board", None, "What's on board"),
    ("display the board", "get_board", None, "Display board"),
    ("show board", "get_board", None, "Show board short"),
    # PLACE_MOVE TESTS
    ("place at center", "place_move", {"row": 1, "col": 1}, "Place center"),
    ("top left", "place_move", {"row": 0, "col": 0}, "Top left corner"),
    ("bottom right", "place_move", {"row": 2, "col": 2}, "Bottom right corner"),
    ("row 1 col 0", "place_move", {"row": 1, "col": 0}, "Explicit middle left"),
    # GET_STATUS TESTS
    ("what's the status", "get_status", None, "What's status"),
    ("who won", "get_status", None, "Who won"),
    ("whose turn is it", "get_status", None, "Whose turn"),
    ("check the status", "get_status", None, "Check status"),
    # THANK_YOU TESTS
    ("thank you", "thank_you", None, "Thank you"),
    ("thanks", "thank_you", None, "Thanks"),
    ("thank you very much", "thank_you", None, "Thank you very much"),
    # GOODBYE TESTS
    ("goodbye", "goodbye", None, "Goodbye"),
    ("bye", "goodbye", None, "Bye"),
    ("quit", "goodbye", None, "Quit"),
    ("see you later", "goodbye", None, "See you later"),
    # INTENT_UNCLEAR TESTS
    ("asdfgh", "intent_unclear", None, "Random characters"),
    ("what is the weather", "intent_unclear", None, "Out of domain query"),
    ("tell me a joke", "intent_unclear", None, "Out of domain request"),
]

# Build tools definition
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "greeting",
            "description": "Handle greeting from the user",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_game",
            "description": "Start a new game of tic-tac-toe",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_board",
            "description": "Get the current board state and display it",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "place_move",
            "description": "Place a move at the specified row and column",
            "parameters": {
                "type": "object",
                "properties": {
                    "row": {"type": "integer", "description": "Row index (0-2)"},
                    "col": {"type": "integer", "description": "Column index (0-2)"},
                },
                "required": ["row", "col"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_status",
            "description": "Get the current game status (turn, winner, game state)",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "goodbye",
            "description": "Handle farewell from the user",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "thank_you",
            "description": "Handle thank you from the user",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "intent_unclear",
            "description": "Handle unclear or unrecognized requests",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
]

SYSTEM_PROMPT = {
    "role": "system",
    "content": """You are a helpful assistant for a voice-controlled tic-tac-toe game. Your job is to understand the user's natural language input and call the appropriate tool.

Available tools:
- greeting: Handle greetings like "hello", "hi", "good morning"
- start_game: Start a new game when user says "start", "let's play", "begin"
- get_board: Show the current board when user asks "show board", "what's on the board"
- place_move: Place a move when user specifies a position like "center", "top left", "row 1 col 2"
- get_status: Check game status when user asks "who won", "what's the status", "whose turn"
- thank_you: Handle thank you messages
- goodbye: Handle farewells like "bye", "goodbye", "quit"
- intent_unclear: Use when you cannot understand the user's intent

For place_move, parse position descriptions:
- "center", "middle" -> row=1, col=1
- "top left", "row 0 col 0" -> row=0, col=0
- "top center", "row 0 col 1" -> row=0, col=1
- "top right", "row 0 col 2" -> row=0, col=2
- "middle left", "row 1 col 0" -> row=1, col=0
- "middle right", "row 1 col 2" -> row=1, col=2
- "bottom left", "row 2 col 0" -> row=2, col=0
- "bottom center", "row 2 col 1" -> row=2, col=1
- "bottom right", "row 2 col 2" -> row=2, col=2

Always call exactly one tool. Do not generate text responses.""",
}


def main():
    print("=" * 70)
    print("SLM Tool Call Test - Simple Version")
    print("=" * 70)
    print()

    # Initialize client
    client = OpenAI(
        base_url="http://localhost:8080/v1",
        api_key="test-key",
        timeout=60.0,
        http_client=httpx.Client(
            http2=False, timeout=httpx.Timeout(timeout=60.0, connect=30.0)
        ),
    )

    passed = 0
    failed = 0
    results = []

    for input_text, expected_tool, expected_args, description in TEST_CASES:
        print(f"\n{'=' * 70}")
        print(f"Test: {description}")
        print(f"Input: '{input_text}'")
        print(f"Expected: {expected_tool}", end="")
        if expected_args:
            print(f" with args {expected_args}", end="")
        print()

        messages = [SYSTEM_PROMPT, {"role": "user", "content": input_text}]

        start_time = time.time()
        try:
            response = client.chat.completions.create(
                model="moe249/google_gemma-4-E4B-it-tictactoe",
                messages=messages,
                temperature=0,
                tools=TOOLS,
                tool_choice="required",
            )
            elapsed = time.time() - start_time

            # Extract tool call
            msg = response.choices[0].message
            if msg.tool_calls:
                tool_call = msg.tool_calls[0].function
                actual_tool = tool_call.name
                try:
                    actual_args = json.loads(tool_call.arguments)
                except:
                    actual_args = {}
            else:
                actual_tool = "unknown"
                actual_args = {}

            print(f"Actual: {actual_tool}", end="")
            if actual_args:
                print(f" with args {actual_args}", end="")
            print()
            print(f"Response time: {elapsed:.2f}s")

            # Validate
            tool_match = actual_tool == expected_tool
            args_match = True
            if expected_args:
                args_match = actual_args.get("row") == expected_args.get(
                    "row"
                ) and actual_args.get("col") == expected_args.get("col")

            success = tool_match and args_match
            status = "✓ PASS" if success else "✗ FAIL"
            print(f"Status: {status}")

            if success:
                passed += 1
            else:
                failed += 1

            results.append(
                {
                    "input": input_text,
                    "description": description,
                    "expected_tool": expected_tool,
                    "expected_args": expected_args,
                    "actual_tool": actual_tool,
                    "actual_args": actual_args,
                    "success": success,
                    "response_time": elapsed,
                }
            )

        except Exception as e:
            elapsed = time.time() - start_time
            print(f"ERROR: {type(e).__name__}: {e}")
            print(f"Status: ✗ FAIL")
            failed += 1
            results.append(
                {
                    "input": input_text,
                    "description": description,
                    "expected_tool": expected_tool,
                    "expected_args": expected_args,
                    "actual_tool": "ERROR",
                    "actual_args": {},
                    "success": False,
                    "response_time": elapsed,
                    "error": str(e),
                }
            )

    # Print summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"Total tests: {len(TEST_CASES)}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Success rate: {passed / len(TEST_CASES) * 100:.1f}%")

    # Export results
    with open("test_results.json", "w") as f:
        json.dump(
            {"results": results, "summary": {"passed": passed, "failed": failed}},
            f,
            indent=2,
        )
    print(f"\nResults saved to test_results.json")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(0)
    except Exception as e:
        print(f"\n\nTest failed: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
