"""Voice Game Orchestrator — Game-specific dialogue manager.

Replaces TOOLS with tic-tac-toe game functions.
Handles position parsing, slot filling, and game response generation.
"""

import json
import logging
import re
from typing import Any

import httpx
from openai import OpenAI

from config.voice_game_config import (
    CLARIFICATION_CAPABILITIES,
    EXIT_COMMANDS,
    GAME_TOOLS,
    GAME_TOOLS_SLOT_DESCRIPTIONS,
    SLOT_PROMPTS,
    SLOT_REQUIREMENTS,
    SUCCESS_TEMPLATES,
    SYSTEM_PROMPT,
)
from voice_game_interface import VoiceGameInterface
from config.config import get_voice_config

# Configure module-level logger
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration Loaders
# ---------------------------------------------------------------------------
def _build_tools() -> list[dict[str, Any]]:
    """Build tool definitions for the SLM.

    Tool names come from GAME_TOOLS, slot descriptions from
    GAME_TOOLS_SLOT_DESCRIPTIONS.
    """
    tools_list = []
    for tool_name in GAME_TOOLS:
        slots = GAME_TOOLS_SLOT_DESCRIPTIONS.get(tool_name, [])

        # Build properties dict from slot descriptions
        # slots format: [{"name": "row", "description": "..."}, ...]
        properties = {}
        for slot in slots:
            slot_name = slot["name"]
            slot_desc = slot["description"]
            properties[slot_name] = {
                "type": "string",
                "description": slot_desc,
            }

        tools_list.append(
            {
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": f"Use the '{tool_name}' function to {tool_name.replace('_', ' ')}",
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": SLOT_REQUIREMENTS.get(tool_name, []),
                        "additionalProperties": False,
                    },
                },
            }
        )

    return tools_list


# Cached tool definitions — computed once at import time
_build_tools_cache: list[dict[str, Any]] | None = None


def _get_cached_tools() -> list[dict[str, Any]]:
    """Return cached tool definitions, computing once on first call."""
    global _build_tools_cache
    if _build_tools_cache is None:
        _build_tools_cache = _build_tools()
    return _build_tools_cache


def _get_valid_tool_names() -> set[str]:
    """Return the set of valid tool names for validation."""
    return {tool["function"]["name"] for tool in _get_cached_tools()}


def _get_required_args() -> dict[str, list[str]]:
    """Return slot requirements from voice_game_config."""
    return {func: list(args) for func, args in SLOT_REQUIREMENTS.items()}


def _get_slot_prompts() -> dict[str, dict[str, str]]:
    """Return slot prompts from voice_game_config."""
    return SLOT_PROMPTS


def _get_templates() -> dict[str, str]:
    """Return success templates from voice_game_config."""
    return SUCCESS_TEMPLATES


def _get_system_prompt() -> dict[str, str]:
    """Return system prompt from voice_game_config."""
    return {
        "role": "system",
        "content": SYSTEM_PROMPT,
    }


def _get_exit_commands() -> list[str]:
    """Return exit commands from voice_game_config."""
    return EXIT_COMMANDS


def _get_clarification_capabilities() -> list[str]:
    """Return clarification capabilities from voice_game_config."""
    return CLARIFICATION_CAPABILITIES


# ---------------------------------------------------------------------------
# SLM Client — stateless wrapper around an OpenAI-compatible endpoint
# ---------------------------------------------------------------------------
class SLMClient:
    """Lightweight client for a llama.cpp / Ollama / vLLM server.

    Implements robust JSON extraction and validation for tool calls.
    """

    # Priority-ordered fallback patterns for intent detection
    # Higher priority patterns are checked first to avoid false matches
    FALLBACK_PATTERNS: dict[str, tuple[str, int]] = {
        # Priority 1: Explicit function name mentions
        "place_move": (r"place[ _-]?(move|mark|x|o)", 1),
        "start_game": (r"(start|begin|play|new)[ _-]?game", 1),
        # Priority 2: Board/status queries
        "get_board": (
            r"(show|display|see|look at|show me|what[\'s]?)( the)?(board|grid|position)",
            2,
        ),
        "get_status": (
            r"(check|status|winner|turn|state|how[\'s]? it|who (won|is next))",
            2,
        ),
        # Priority 3: Social interactions
        "thank_you": (r"(thank|thanks|thank you|appreciate)", 3),
        "greeting": (
            r"(hello|hi|hey|greetings|good morning|good afternoon|good evening|how are you)",
            3,
        ),
        "goodbye": (r"(bye|goodbye|quit|exit|see you|leave|stop|end)", 3),
        # Priority 4: Fallback for unclear intent
        "intent_unclear": (r".*", 4),
    }

    def __init__(
        self, model_name: str, api_key: str | None = None, port: int | None = None
    ):
        self.model_name = model_name
        http_client = httpx.Client(
            http2=False,
            timeout=60.0,
        )
        # Use provided port or fall back to config
        actual_port = port if port is not None else get_voice_config().slm_port
        self.client = OpenAI(
            base_url=f"http://{get_voice_config().slm_host}:{actual_port}/v1",
            api_key=api_key or get_voice_config().slm_api_key,
            timeout=60.0,
            http_client=http_client,
        )

    def invoke(self, conversation_history: list[dict]) -> dict | str:
        """Send conversation history to the SLM and return a parsed function-call.

        Returns:
            dict: {"name": str, "arguments": dict} if a valid tool call is extracted
            str: Error message if no valid tool call could be extracted

        Extraction priority:
            1. Proper tool_calls in response
            2. JSON in content (multiple formats)
            3. JSON in reasoning_content
            4. Priority-based fallback pattern matching
        """
        # Guard clause: Empty conversation
        if not conversation_history:
            logger.error("invoke() called with empty conversation_history")
            return "Error: Empty conversation history provided"

        messages = [_get_system_prompt()] + conversation_history

        logger.info(f"[SLM] Sending request to {self.model_name}")
        logger.info(f"[SLM] Temperature: 0, Tool choice: required")
        logger.info(f"[SLM] Messages count: {len(messages)}")
        logger.debug(f"[SLM] base_url: {self.client.base_url}")
        logger.debug(f"[SLM] model: {self.model_name}")
        logger.debug(
            f"[SLM] messages: {json.dumps(messages[-2:], indent=2, ensure_ascii=False)[:1000]}"
        )
        logger.debug(f"[SLM] tools count: {len(_get_cached_tools())}")

        try:
            chat_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0,
                tools=_get_cached_tools(),
                tool_choice="required",
            )
        except Exception as e:
            error_msg = f"SLM API call failed: {type(e).__name__}: {str(e)}"
            logger.error(error_msg)
            return error_msg

        response = chat_response.choices[0].message
        logger.info("[SLM] Raw response received")

        # --- Path A: Proper tool_calls in the response (highest priority) ---
        if response.tool_calls:
            return self._extract_from_tool_calls(response.tool_calls)

        # --- Path B: JSON in content ---
        if response.content:
            result = self._extract_from_content(response.content)
            if result is not None:
                return result

        # --- Path C: JSON in reasoning_content ---
        if hasattr(response, "reasoning_content") and response.reasoning_content:
            result = self._extract_from_content(response.reasoning_content)
            if result is not None:
                return result

        # --- Path D: Priority-based fallback pattern matching ---
        content_to_search = response.content or (
            response.reasoning_content if hasattr(response, "reasoning_content") else ""
        )
        if content_to_search:
            result = self._fallback_pattern_match(content_to_search)
            if result is not None:
                return result

        # --- Final fallback: No valid tool call found ---
        error_details = self._format_response_error(response)
        logger.error(f"[SLM] No valid tool call found: {error_details}")
        return f"No valid tool call in SLM response: {error_details}"

    def _extract_from_tool_calls(self, tool_calls: list) -> dict | str:
        """Extract function call from proper tool_calls response.

        Args:
            tool_calls: List of tool call objects from the response

        Returns:
            dict with name and arguments, or error string
        """
        if not tool_calls:
            return "Error: Empty tool_calls list"

        fn = tool_calls[0].function

        # Guard clause: Missing function name
        if not hasattr(fn, "name") or not fn.name:
            return "Error: Tool call missing function name"

        # Parse arguments with robust error handling
        arguments = fn.arguments
        if isinstance(arguments, str):
            try:
                arguments = self._parse_json_safely(arguments)
            except json.JSONDecodeError as e:
                error_msg = f"Failed to parse arguments JSON: {e}"
                logger.warning(error_msg)
                return error_msg

        # Validate function name
        valid_tools = _get_valid_tool_names()
        if fn.name not in valid_tools:
            error_msg = f"Invalid tool name '{fn.name}'. Valid tools: {valid_tools}"
            logger.warning(error_msg)
            return error_msg

        logger.info(f"[SLM] Function call extracted: {fn.name} with args {arguments}")
        return {"name": fn.name, "arguments": arguments}

    def _extract_from_content(self, content: str) -> dict | str | None:
        """Extract function call from text content with multiple JSON formats.

        Args:
            content: Text content that may contain JSON

        Returns:
            dict with name and arguments, error string, or None if no match
        """
        if not content or not content.strip():
            return None

        content = content.strip()
        logger.debug(f"[SLM] Content extraction attempt: {content[:200]}...")

        # Try multiple JSON extraction patterns in order of preference
        json_candidates = self._extract_json_candidates(content)

        for candidate in json_candidates:
            parsed = self._parse_json_safely(candidate)
            if parsed is None:
                continue

            # Validate and extract function call from parsed JSON
            result = self._validate_function_call(parsed, source="content JSON")
            if result is not None:
                return result

        return None

    def _extract_json_candidates(self, content: str) -> list[str]:
        """Extract all potential JSON strings from content.

        Uses multiple regex patterns to handle various formats:
        - Plain JSON
        - JSON in markdown code blocks
        - JSON wrapped in text
        - Nested JSON structures

        Args:
            content: Text to extract JSON from

        Returns:
            List of JSON string candidates, ordered by likelihood of validity
        """
        candidates: list[str] = []

        # Pattern 1: JSON in markdown code blocks (```json ... ```)
        markdown_pattern = r"```(?:json)?\s*(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})\s*```"
        matches = re.findall(markdown_pattern, content, re.DOTALL)
        candidates.extend(matches)

        # Pattern 2: JSON in triple quotes (""" ... """)
        triple_quote_pattern = r'"""(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})"""'
        matches = re.findall(triple_quote_pattern, content, re.DOTALL)
        candidates.extend(matches)

        # Pattern 3: Balanced braces with "name" key (handles nested structures)
        # This is more robust than simple [^{}]* patterns
        name_json_pattern = r'\{[^{}]*(?:"name"\s*:\s*"[^"]+")[^{}]*\}'
        matches = re.findall(name_json_pattern, content)
        candidates.extend(matches)

        # Pattern 4: Try to find any balanced JSON object
        # Start from first { and find matching }
        if "{" in content:
            start_idx = content.find("{")
            brace_count = 0
            for end_idx in range(start_idx, len(content)):
                if content[end_idx] == "{":
                    brace_count += 1
                elif content[end_idx] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        candidates.append(content[start_idx : end_idx + 1])
                        break

        # Pattern 5: Full content (last resort)
        if content.strip().startswith("{") and content.strip().endswith("}"):
            candidates.append(content.strip())

        # Remove duplicates while preserving order
        seen: set[str] = set()
        unique_candidates: list[str] = []
        for candidate in candidates:
            normalized = candidate.replace(" ", "").replace("\n", "")
            if normalized not in seen:
                seen.add(normalized)
                unique_candidates.append(candidate)

        logger.debug(f"[SLM] Found {len(unique_candidates)} JSON candidates")
        return unique_candidates

    def _parse_json_safely(self, json_str: str) -> dict | None:
        """Parse JSON string with comprehensive error handling.

        Args:
            json_str: String to parse as JSON

        Returns:
            Parsed dict or None if parsing fails
        """
        if not json_str or not isinstance(json_str, str):
            return None

        # Try direct parsing first
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # Try common fixes
        fixes_to_try = [
            # Remove trailing commas
            re.sub(r",(\s*[}\]])", r"\1", json_str),
            # Fix unquoted keys
            re.sub(r"(\s*)(\w+)(\s*:\s*)", r"\1\"\2\"\3", json_str),
            # Handle single quotes
            json_str.replace("'", '"'),
        ]

        for fixed in fixes_to_try:
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                continue

        return None

    def _validate_function_call(
        self, parsed: dict, source: str = ""
    ) -> dict | str | None:
        """Validate that parsed JSON contains a valid function call.

        Args:
            parsed: Parsed JSON dict
            source: Source description for logging

        Returns:
            Valid function call dict, error string, or None if invalid
        """
        if not isinstance(parsed, dict):
            logger.debug(f"[SLM] Parsed JSON is not a dict: {type(parsed)}")
            return None

        # Extract function name
        func_name = parsed.get("name")
        if not func_name or not isinstance(func_name, str):
            logger.debug(f"[SLM] Missing or invalid 'name' in parsed JSON")
            return None

        # Validate function name against known tools
        valid_tools = _get_valid_tool_names()
        if func_name not in valid_tools:
            logger.warning(
                f"[SLM] Invalid tool name '{func_name}' from {source}. Valid: {valid_tools}"
            )
            return None

        # Extract and parse arguments
        args = parsed.get("arguments", parsed.get("parameters", {}))
        if isinstance(args, str):
            try:
                args = self._parse_json_safely(args)
                if args is None:
                    args = {}
            except Exception:
                args = {}
        elif not isinstance(args, dict):
            args = {}

        logger.info(f"[SLM] Valid function call from {source}: {func_name}")
        return {"name": func_name, "arguments": args}

    def _fallback_pattern_match(self, content: str) -> dict | str | None:
        """Match intent using priority-ordered regex patterns.

        Args:
            content: Text content to match against patterns

        Returns:
            Function call dict for matched intent, or None
        """
        if not content:
            return None

        content_lower = content.lower()
        logger.debug(f"[SLM] Running fallback pattern matching on: {content[:100]}...")

        # Sort patterns by priority (lower number = higher priority)
        sorted_patterns = sorted(
            self.FALLBACK_PATTERNS.items(),
            key=lambda x: x[1][1],  # Sort by priority number
        )

        for func_name, (pattern, priority) in sorted_patterns:
            if re.search(pattern, content_lower, re.IGNORECASE):
                # Validate the matched function name
                valid_tools = _get_valid_tool_names()
                if func_name in valid_tools:
                    logger.info(
                        f"[SLM] Fallback pattern matched (priority {priority}): {func_name}"
                    )
                    return {"name": func_name, "arguments": {}}
                else:
                    logger.warning(f"[SLM] Matched invalid tool name: {func_name}")

        return None

    def _format_response_error(self, response: Any) -> str:
        """Format response details for error logging.

        Args:
            response: The SLM response object

        Returns:
            Formatted error description string
        """
        parts = []

        if hasattr(response, "content") and response.content:
            parts.append(f"content: {response.content[:100]}")

        if hasattr(response, "tool_calls") and response.tool_calls:
            parts.append(f"tool_calls: {len(response.tool_calls)} items")

        if hasattr(response, "reasoning_content") and response.reasoning_content:
            parts.append(f"reasoning: {response.reasoning_content[:100]}")

        return "; ".join(parts) if parts else "empty response"


# ---------------------------------------------------------------------------
# Text Orchestrator
# ---------------------------------------------------------------------------
class TextOrchestrator:
    """Deterministic dialogue manager for tic-tac-toe game."""

    def __init__(
        self,
        slm_client: SLMClient,
        game_interface: VoiceGameInterface,
        debug: bool = False,
    ):
        self.slm = slm_client
        self.game = game_interface
        self.debug = debug
        self.conversation_history: list[dict] = []
        self.game_started = False

    def process_utterance(self, transcript: str) -> str | None:
        """Full turn: user text in -> bot response out."""
        # 0. Exit if the user wants to quit
        if transcript.lower() in _get_exit_commands():
            return None

        # 1. Append user turn
        self.conversation_history.append({"role": "user", "content": transcript})

        # 2. Call SLM
        function_call = self.slm.invoke(self.conversation_history)

        if self.debug:
            print(f"  [DEBUG] SLM returned: {function_call}")

        # 3. If the SLM failed to return a valid call, treat as unclear
        if isinstance(function_call, str):
            self.conversation_history.append({"role": "assistant", "content": ""})
            return self.generate_clarification_response()

        # 4. Record assistant turn in history (tool_calls format)
        args_str = (
            json.dumps(function_call["arguments"])
            if isinstance(function_call["arguments"], dict)
            else function_call["arguments"]
        )
        tool_call_msg = {
            "role": "assistant",
            "tool_calls": [
                {
                    "type": "function",
                    "function": {
                        "name": function_call["name"],
                        "arguments": args_str,
                    },
                }
            ],
        }
        self.conversation_history.append(tool_call_msg)

        # 5. Route through orchestrator logic — None signals end of conversation
        return self.handle_function_call(function_call)

    def reset(self) -> None:
        self.conversation_history = []

    def handle_function_call(self, function_call: dict) -> str | None:
        name = function_call["name"]
        arguments = function_call.get("arguments", {})

        if name == "goodbye":
            return None

        if name == "intent_unclear":
            return self.generate_clarification_response()

        # Check for missing required args
        missing = self.get_missing_args(name, arguments)
        if missing:
            return self.generate_slot_elicitation(name, missing, arguments)

        # All slots filled — execute
        return self.execute_and_respond(name, arguments)

    def get_missing_args(self, function_name: str, arguments: dict) -> list[str]:
        required = _get_required_args().get(function_name, [])
        return [arg for arg in required if arguments.get(arg) is None]

    def generate_clarification_response(self) -> str:
        capabilities = _get_clarification_capabilities()
        return (
            "I didn't quite understand that. Could you tell me what you need? "
            f"I can help you {', '.join(capabilities)}."
        )

    def generate_slot_elicitation(
        self, function: str, missing_args: list[str], current_args: dict
    ) -> str:
        individual = _get_slot_prompts().get(function, {})
        questions = [
            individual.get(arg, f"the {arg.replace('_', ' ')}") for arg in missing_args
        ]
        if len(questions) == 1:
            return f"Could you provide {questions[0]}?"
        return f"Could you provide {', '.join(questions[:-1])}, and {questions[-1]}?"

    def execute_and_respond(self, function: str, arguments: dict) -> str:
        api_result = self.call_backend_api(function, arguments)
        template = _get_templates().get(function, "Done.")
        return template.format(**arguments, **api_result)

    def call_backend_api(self, function: str, arguments: dict) -> dict:
        """Execute game logic via API and return result for template."""
        if function == "start_game":
            game_id = self.game.start_game()
            self.game_started = True
            return {"message": f"Game started with ID {game_id}"}

        elif function == "get_board":
            if not self.game_started:
                return {
                    "board_description": "No game started yet. Say 'start' to begin."
                }
            state = self.game.get_game_state()
            board_desc = self.game.board_to_description(state["board"])
            return {"board_description": board_desc}

        elif function == "get_status":
            if not self.game_started:
                return {"status_description": "No game started yet."}
            state = self.game.get_game_state()
            status_desc = self.game.status_to_description(state)
            return {"status_description": status_desc}

        elif function == "place_move":
            if not self.game_started:
                return {
                    "move_result": "No game started yet. Say 'start' to begin first."
                }

            row = int(arguments["row"])
            col = int(arguments["col"])
            api_position = self.game.position_to_api(row, col)
            pos_desc = self.game.position_from_api(api_position)

            try:
                state = self.game.make_move(api_position)

                if state["winner"]:
                    return {
                        "move_result": f"You placed your mark at {pos_desc}. {state['winner']} has won the game!"
                    }
                elif state["status"] == "draw":
                    return {
                        "move_result": f"You placed your mark at {pos_desc}. It's a draw!"
                    }
                else:
                    return {
                        "move_result": f"You placed your mark at {pos_desc}. Your opponent's turn."
                    }
            except Exception as e:
                return {"move_result": f"{str(e)}"}

        return {}
