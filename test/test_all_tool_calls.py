"""Comprehensive test script for all 8 tool calls with the SLM.

Tests the SLM's intent recognition and argument extraction capabilities
for the voice-controlled tic-tac-toe game.

Tested tools:
1. greeting - Handle greetings from the user
2. start_game - Start a new game of tic-tac-toe
3. get_board - Get the current board state
4. place_move - Place a move at specified row and column
5. get_status - Get the current game status
6. goodbye - Handle farewells
7. thank_you - Handle thank you messages
8. intent_unclear - Handle unclear or unrecognized requests

Run with: uv run python test_all_tool_calls.py
"""

import json
import sys
import time
from pathlib import Path
from typing import Optional

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from openai import OpenAI
import httpx

# Import config
from config.config import get_voice_config
from config.voice_game_config import GAME_TOOLS, SYSTEM_PROMPT


class SLMToolTester:
    """Test harness for SLM tool call recognition."""

    # Test cases for each tool with varied natural language inputs
    TEST_CASES = {
        "greeting": [
            "hello",
            "hi there",
            "good morning",
            "how are you",
            "hey",
            "greetings",
        ],
        "start_game": [
            "start a new game",
            "let's play",
            "begin the game",
            "I want to play",
            "new game please",
            "start playing",
        ],
        "get_board": [
            "show me the board",
            "what's on the board",
            "display the board",
            "show board",
            "current board state",
            "what does the board look like",
        ],
        "place_move": [
            "place at center",
            "top left",
            "bottom right",
            "row 1 col 0",
            "middle left",
            "top center",
            "bottom center",
            "row 2 column 2",
        ],
        "get_status": [
            "what's the status",
            "who won",
            "whose turn is it",
            "check the status",
            "is the game over",
            "game status",
        ],
        "goodbye": [
            "goodbye",
            "bye",
            "quit",
            "see you later",
            "I'm done",
            "exit",
        ],
        "thank_you": [
            "thank you",
            "thanks",
            "thank you very much",
            "I appreciate it",
            "thanks a lot",
        ],
        "intent_unclear": [
            "asdfgh",
            "what is the weather",
            "tell me a joke",
            "xyz123",
            "play music",
        ],
    }

    # Expected row/col values for place_move test cases
    PLACE_MOVE_EXPECTED = {
        "place at center": {"row": 1, "col": 1},
        "put my mark in the center": {"row": 1, "col": 1},
        "center": {"row": 1, "col": 1},
        "top left": {"row": 0, "col": 0},
        "row 0 column 0": {"row": 0, "col": 0},
        "place at row 0 col 0": {"row": 0, "col": 0},
        "top center": {"row": 0, "col": 1},
        "row 0 col 1": {"row": 0, "col": 1},
        "top right": {"row": 0, "col": 2},
        "row 0 column 2": {"row": 0, "col": 2},
        "middle left": {"row": 1, "col": 0},
        "row 1 col 0": {"row": 1, "col": 0},
        "middle right": {"row": 1, "col": 2},
        "row 1 column 2": {"row": 1, "col": 2},
        "bottom left": {"row": 2, "col": 0},
        "row 2 col 0": {"row": 2, "col": 0},
        "bottom center": {"row": 2, "col": 1},
        "row 2 col 1": {"row": 2, "col": 1},
        "bottom right": {"row": 2, "col": 2},
        "row 2 column 2": {"row": 2, "col": 2},
    }

    def __init__(self, model_name: str, port: int = 8080):
        """Initialize the tester with SLM connection parameters."""
        config = get_voice_config()
        self.model_name = model_name
        self.port = port
        self.client = OpenAI(
            base_url=f"http://{config.slm_host}:{port}/v1",
            api_key=config.slm_api_key,
            timeout=120.0,
            http_client=httpx.Client(
                http2=False, timeout=httpx.Timeout(timeout=120.0, connect=30.0)
            ),
        )
        self.tools = self._build_tools()
        self.system_prompt = self._get_system_prompt()

        # Statistics
        self.stats = {
            "total_tests": 0,
            "passed": 0,
            "failed": 0,
            "by_tool": {tool: {"passed": 0, "failed": 0} for tool in self.TEST_CASES},
        }

    def _build_tools(self) -> list[dict]:
        """Build the tools array for the SLM."""
        config = get_voice_config()
        tool_definitions = {
            "greeting": {
                "description": "Handle greeting from the user",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            "start_game": {
                "description": "Start a new game of tic-tac-toe",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            "get_board": {
                "description": "Get the current board state and display it",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            "place_move": {
                "description": "Place a move at the specified row and column",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "row": {
                            "type": "integer",
                            "description": "Row index (0-2, where 0 is top, 1 is middle, 2 is bottom)",
                        },
                        "col": {
                            "type": "integer",
                            "description": "Column index (0-2, where 0 is left, 1 is center, 2 is right)",
                        },
                    },
                    "required": ["row", "col"],
                    "additionalProperties": False,
                },
            },
            "get_status": {
                "description": "Get the current game status (turn, winner, game state)",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            "goodbye": {
                "description": "Handle farewell from the user",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            "thank_you": {
                "description": "Handle thank you from the user",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
            "intent_unclear": {
                "description": "Handle unclear or unrecognized requests",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                    "additionalProperties": False,
                },
            },
        }

        return [
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": tool_definitions[tool_name]["description"],
                    "parameters": tool_definitions[tool_name]["parameters"],
                },
            }
            for tool_name in GAME_TOOLS
        ]

    def _get_system_prompt(self) -> dict:
        """Get the system prompt for the SLM."""
        return {"role": "system", "content": SYSTEM_PROMPT}

    def invoke_slm(self, user_input: str) -> dict | str:
        """Send a request to the SLM and return the parsed tool call.

        Args:
            user_input: The user's natural language input

        Returns:
            dict with 'name' and 'arguments' keys, or error string
        """
        messages = [self.system_prompt, {"role": "user", "content": user_input}]

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0,
                tools=self.tools,
                tool_choice="required",
            )

            # Extract tool call from response
            if response.choices:
                msg = response.choices[0].message

                # Path A: Proper tool_calls
                if msg.tool_calls:
                    tool_call = msg.tool_calls[0].function
                    name = tool_call.name
                    arguments = tool_call.arguments
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError:
                            arguments = {}
                    return {"name": name, "arguments": arguments}

                # Path B: JSON in content
                if msg.content:
                    return self._extract_from_content(msg.content)

                # Path C: JSON in reasoning_content
                if hasattr(msg, "reasoning_content") and msg.reasoning_content:
                    return self._extract_from_content(msg.reasoning_content)

            return "Error: No valid tool call in response"

        except Exception as e:
            return f"Error: {type(e).__name__}: {str(e)}"

    def _extract_from_content(self, content: str) -> dict | str:
        """Extract function call from text content.

        Args:
            content: Text content that may contain JSON

        Returns:
            dict with name and arguments, or error string
        """
        import re

        if not content or not content.strip():
            return "Error: Empty content"

        # Try to find JSON object
        patterns = [
            r"```(?:json)?\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*```",
            r'\{[^{}]*(?:"name"\s*:\s*"[^"]+")[^{}]*\}',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and "name" in parsed:
                        return {
                            "name": parsed["name"],
                            "arguments": parsed.get("arguments", {}),
                        }
                except json.JSONDecodeError:
                    continue

        # Fallback pattern matching
        content_lower = content.lower()
        fallback_patterns = {
            "place_move": r"place[ _-]?(move|mark|x|o)",
            "start_game": r"(start|begin|play|new)[ _-]?game",
            "get_board": r"(show|display|see|look at|show me|what[\'s]?)( the)?(board|grid|position)",
            "get_status": r"(check|status|winner|turn|state|how[\'s]? it|who (won|is next))",
            "thank_you": r"(thank|thanks|thank you|appreciate)",
            "greeting": r"(hello|hi|hey|greetings|good morning|good afternoon|good evening)",
            "goodbye": r"(bye|goodbye|quit|exit|see you|leave|stop|end)",
            "intent_unclear": r".*",
        }

        for tool_name, pattern in fallback_patterns.items():
            if re.search(pattern, content_lower, re.IGNORECASE):
                return {"name": tool_name, "arguments": {}}

        return "Error: Could not extract tool call"

    def validate_tool_call(
        self,
        result: dict | str,
        expected_tool: str,
        expected_args: Optional[dict] = None,
    ) -> tuple[bool, str]:
        """Validate the SLM's tool call result.

        Args:
            result: The SLM's response (dict or error string)
            expected_tool: The expected tool name
            expected_args: Optional expected arguments dict

        Returns:
            Tuple of (is_valid, message)
        """
        # Check if result is an error
        if isinstance(result, str):
            return False, f"SLM returned error: {result}"

        # Check if result is a dict
        if not isinstance(result, dict):
            return False, f"Unexpected result type: {type(result)}"

        # Check tool name
        actual_tool = result.get("name")
        if actual_tool != expected_tool:
            return False, f"Expected tool '{expected_tool}', got '{actual_tool}'"

        # Check arguments for place_move
        if expected_args and actual_tool == "place_move":
            actual_args = result.get("arguments", {})

            # Check row
            expected_row = expected_args.get("row")
            actual_row = actual_args.get("row")
            if expected_row is not None and actual_row != expected_row:
                return False, f"Expected row={expected_row}, got row={actual_row}"

            # Check col
            expected_col = expected_args.get("col")
            actual_col = actual_args.get("col")
            if expected_col is not None and actual_col != expected_col:
                return False, f"Expected col={expected_col}, got col={actual_col}"

        return True, "PASS"

    def run_test(
        self, tool: str, input_text: str, expected_args: Optional[dict] = None
    ) -> dict:
        """Run a single test case.

        Args:
            tool: Expected tool name
            input_text: User input text
            expected_args: Optional expected arguments

        Returns:
            Test result dict with all details
        """
        self.stats["total_tests"] += 1

        # Measure response time
        start_time = time.time()
        result = self.invoke_slm(input_text)
        response_time = time.time() - start_time

        # Validate
        is_valid, message = self.validate_tool_call(result, tool, expected_args)

        # Update stats
        if is_valid:
            self.stats["passed"] += 1
            self.stats["by_tool"][tool]["passed"] += 1
        else:
            self.stats["failed"] += 1
            self.stats["by_tool"][tool]["failed"] += 1

        # Format result
        if isinstance(result, dict):
            result_str = json.dumps(result, indent=2)
        else:
            result_str = str(result)

        return {
            "tool": tool,
            "input": input_text,
            "expected_tool": tool,
            "expected_args": expected_args,
            "result": result,
            "result_str": result_str,
            "is_valid": is_valid,
            "message": message,
            "response_time": response_time,
        }

    def run_all_tests(self) -> list[dict]:
        """Run all test cases for all tools.

        Returns:
            List of all test results
        """
        all_results = []

        for tool, inputs in self.TEST_CASES.items():
            print(f"\n{'=' * 60}")
            print(f"Testing tool: {tool}")
            print("=" * 60)

            for input_text in inputs:
                # Get expected args for place_move
                expected_args = None
                if tool == "place_move" and input_text in self.PLACE_MOVE_EXPECTED:
                    expected_args = self.PLACE_MOVE_EXPECTED[input_text]

                # Run test
                result = self.run_test(tool, input_text, expected_args)
                all_results.append(result)

                # Print result
                status = "✓ PASS" if result["is_valid"] else "✗ FAIL"
                print(f'\n  Input: "{input_text}"')
                print(f"  Expected: {result['expected_tool']}")
                if result["expected_args"]:
                    print(f"  Expected args: {result['expected_args']}")
                print(
                    f"  Actual tool: {result['result'].get('name') if isinstance(result['result'], dict) else result['result']}"
                )
                if isinstance(result["result"], dict):
                    print(f"  Actual args: {result['result'].get('arguments', {})}")
                print(f"  Response time: {result['response_time']:.2f}s")
                print(f"  Status: {status}")
                if not result["is_valid"]:
                    print(f"  Message: {result['message']}")

        return all_results

    def print_summary(self) -> None:
        """Print a summary of all test results."""
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)

        total = self.stats["total_tests"]
        passed = self.stats["passed"]
        failed = self.stats["failed"]

        print(f"\nTotal tests: {total}")
        print(f"Passed: {passed} ({100 * passed / total:.1f}%)")
        print(f"Failed: {failed} ({100 * failed / total:.1f}%)")

        # Calculate timing statistics
        if self.all_results:
            response_times = [r["response_time"] for r in self.all_results]
            total_time = sum(response_times)
            avg_time = total_time / len(response_times)
            min_time = min(response_times)
            max_time = max(response_times)
            print(f"\nTiming Statistics:")
            print(f"  Total time: {total_time:.2f}s")
            print(f"  Average response time: {avg_time:.2f}s")
            print(f"  Min response time: {min_time:.2f}s")
            print(f"  Max response time: {max_time:.2f}s")

        print("\nResults by tool:")
        print("-" * 40)

        for tool, stats in self.stats["by_tool"].items():
            total_tool = stats["passed"] + stats["failed"]
            passed_pct = 100 * stats["passed"] / total_tool if total_tool > 0 else 0
            status = "✓" if stats["failed"] == 0 else "✗"
            print(
                f"  {status} {tool}: {stats['passed']}/{total_tool} ({passed_pct:.1f}%)"
            )

        # Print failed tests
        if failed > 0:
            print("\n" + "=" * 60)
            print("FAILED TESTS")
            print("=" * 60)

            for result in self.all_results:
                if not result["is_valid"]:
                    print(f"\n  Tool: {result['tool']}")
                    print(f'  Input: "{result["input"]}"')
                    print(f"  Expected: {result['expected_tool']}")
                    if result["expected_args"]:
                        print(f"  Expected args: {result['expected_args']}")
                    print(f"  Got: {result['result']}")
                    print(f"  Response time: {result['response_time']:.2f}s")
                    print(f"  Message: {result['message']}")

    def run(self) -> None:
        """Run all tests and print summary."""
        print("=" * 60)
        print("SLM TOOL CALL TEST SUITE")
        print("=" * 60)
        print(f"Model: {self.model_name}")
        print(f"Port: {self.port}")
        print(
            f"Total test cases: {sum(len(inputs) for inputs in self.TEST_CASES.values())}"
        )

        all_results = self.run_all_tests()
        self.all_results = all_results
        self.print_summary()


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Test SLM tool call recognition for all 8 tools"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="moe249/google_gemma-4-E4B-it-tictactoe",
        help="Model name (default: moe249/google_gemma-4-E4B-it-tictactoe)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="SLM server port (default: 8080)",
    )
    parser.add_argument(
        "--tool",
        type=str,
        choices=list(SLMToolTester.TEST_CASES.keys()),
        help="Test a specific tool only",
    )

    args = parser.parse_args()

    # Check if SLM server is running
    try:
        tester = SLMToolTester(model_name=args.model, port=args.port)

        if args.tool:
            # Test specific tool
            print(f"\nTesting specific tool: {args.tool}")
            for input_text in tester.TEST_CASES[args.tool]:
                expected_args = None
                if (
                    args.tool == "place_move"
                    and input_text in tester.PLACE_MOVE_EXPECTED
                ):
                    expected_args = tester.PLACE_MOVE_EXPECTED[input_text]

                result = tester.run_test(args.tool, input_text, expected_args)
                status = "✓ PASS" if result["is_valid"] else "✗ FAIL"
                print(f'\n  Input: "{input_text}"')
                print(f"  Result: {result['result']}")
                print(f"  Status: {status}")
                if not result["is_valid"]:
                    print(f"  Message: {result['message']}")

            # Print summary for single tool
            total = tester.stats["total_tests"]
            passed = tester.stats["passed"]
            print(f"\n{args.tool} tests: {passed}/{total} passed")
        else:
            # Run all tests
            tester.run()

    except Exception as e:
        print(f"Error: {e}")
        print("Make sure the SLM server is running on port 8080")
        sys.exit(1)


if __name__ == "__main__":
    main()
