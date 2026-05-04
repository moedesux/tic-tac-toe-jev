"""Voice Game Configuration Constants.

All voice game settings are defined here as clean Python constants.
This eliminates the need for \n-escaped JSON-in-INI values in voice.conf.

To update any setting, just edit this file — no escaping, no quoting hacks.
"""

# ============================================================================
# System Prompt — The SLM's instructions
# ============================================================================
SYSTEM_PROMPT = """You are a tic-tac-toe game assistant designed to interact with players through voice commands.
Your role is to manage game state, respond to player moves, and handle conversational interactions.
When players make moves, translate their natural language into precise function calls.
Respond to greetings, farewells, and thanks appropriately throughout the conversation.

## Functions

1. start_game() - Create new game
2. get_board() - Show current board state
3. place_move(row: int, col: int) - Make move at row/col (both 0-2)
4. get_status() - Get game status (turn, winner)
5. greeting() - Handle greetings
6. goodbye() - Handle farewells
7. thank_you() - Handle thanks
8. intent_unclear() - Handle unclear requests

## Position Mapping for place_move

### Row/Column Format (user gives 1-indexed numbers — you convert to 0-indexed)
- "row 1, col 1" → {"row": 0, "col": 0}
- "row 2, col 3" → {"row": 1, "col": 2}
- "row 3, col 2" → {"row": 2, "col": 1}

### Flat Position 1-9 (user gives number 1-9 — you convert)
Formula: row = (position-1) // 3, col = (position-1) % 3
- "position 1" / "cell 1" → {"row": 0, "col": 0}
- "position 2" / "cell 2" → {"row": 0, "col": 1}
- "position 3" / "cell 3" → {"row": 0, "col": 2}
- "position 4" / "cell 4" → {"row": 1, "col": 0}
- "position 5" / "cell 5" / "center" → {"row": 1, "col": 1}
- "position 6" / "cell 6" → {"row": 1, "col": 2}
- "position 7" / "cell 7" → {"row": 2, "col": 0}
- "position 8" / "cell 8" → {"row": 2, "col": 1}
- "position 9" / "cell 9" → {"row": 2, "col": 2}

### Natural Language Position Names (ALREADY 0-INDEXED — output directly, do NOT subtract 1)

#### Corner positions:
- "top-left" / "top left" → {"row": 0, "col": 0}
- "top-right" / "top right" → {"row": 0, "col": 2}
- "bottom-left" / "bottom left" → {"row": 2, "col": 0}
- "bottom-right" / "bottom right" → {"row": 2, "col": 2}

#### Edge positions:
- "top-center" / "top centre" / "top middle" → {"row": 0, "col": 1}
- "middle-left" / "middle left" / "left-middle" / "left middle" → {"row": 1, "col": 0}
- "middle-right" / "middle right" / "right-middle" / "right middle" → {"row": 1, "col": 2}
- "bottom-center" / "bottom centre" / "bottom middle" → {"row": 2, "col": 1}

#### Center:
- "center" / "centre" → {"row": 1, "col": 1}

### ⚠️ CRITICAL RULES
1. "center" ALWAYS means the exact center cell: row=1, col=1 (position 5)
2. "middle" alone means center: row=1, col=1
3. "middle right" means row=1 (middle) + col=2 (right) = {"row": 1, "col": 2}. NEVER center!
4. For explicit "row X, col Y" format: subtract 1 from each number (1-indexed → 0-indexed)
5. For flat numbers 1-9: use formula row=(N-1)//3, col=(N-1)%3
6. For position names: output the zero-indexed values directly — DO NOT subtract 1

### ⚠️ OUTPUT FORMAT RULE
When calling place_move, ALWAYS output the function arguments as a JSON object with "row" and "col" keys.
The values MUST be integers between 0 and 2 inclusive. Always verify your output makes sense.

Examples of correct output:
- "middle right" → place_move with {"row": 1, "col": 2}
- "top left" → place_move with {"row": 0, "col": 0}
- "bottom right" → place_move with {"row": 2, "col": 2}
- "center" → place_move with {"row": 1, "col": 1}

## Position Reference Board

     col 0 (left)   col 1 (center)   col 2 (right)
row 0 (top)    ┌──────┬──────┬──────┐
               │  1   │  2   │  3   │
row 1 (mid)    │  4   │  5   │  6   │
row 2 (bot)    │  7   │  8   │  9   │
               └──────┴──────┴──────┘
"""


# ============================================================================
# Game Tools — List of valid tool names for the SLM
# ============================================================================
GAME_TOOLS = [
    "greeting",
    "start_game",
    "get_board",
    "place_move",
    "get_status",
    "goodbye",
    "thank_you",
    "intent_unclear",
]

# Slot descriptions — what each argument means
GAME_TOOLS_SLOT_DESCRIPTIONS = {
    "greeting": [],
    "start_game": [],
    "get_board": [],
    "place_move": [
        {
            "name": "row",
            "description": "The row index (0-2, where 0 is top, 1 is middle, 2 is bottom)",
        },
        {
            "name": "col",
            "description": "The column index (0-2, where 0 is left, 1 is center, 2 is right)",
        },
    ],
    "get_status": [],
    "goodbye": [],
    "thank_you": [],
    "intent_unclear": [],
}

# ============================================================================
# Slot Requirements — which arguments each tool needs
# ============================================================================
SLOT_REQUIREMENTS = {
    "greeting": [],
    "start_game": [],
    "get_board": [],
    "place_move": ["row", "col"],
    "get_status": [],
    "goodbye": [],
    "thank_you": [],
    "intent_unclear": [],
}

# ============================================================================
# Slot Prompts — guidance for the SLM when asking for missing arguments
# ============================================================================
SLOT_PROMPTS = {
    "place_move": {
        "row": "row (0-2, where 0 is top, 1 is middle, 2 is bottom)",
        "col": "column (0-2, where 0 is left, 1 is center, 2 is right)",
    }
}

# ============================================================================
# Success Templates — response messages for each tool result
# ============================================================================
SUCCESS_TEMPLATES = {
    "start_game": "New game started! You are player X. Your turn to place a mark.",
    "get_board": "{board_description}",
    "get_status": "{status_description}",
    "place_move": "{move_result}",
    "greeting": "Welcome to Tic-Tac-Toe! Say 'start' to begin a new game.",
    "goodbye": "Thanks for playing! Goodbye!",
    "thank_you": "You're welcome! Is there anything else I can help with?",
    "intent_unclear": "I didn't quite understand that. I can help you start a game, place moves, check the board, or check the status.",
}

# ============================================================================
# Exit Commands — phrases that end the game session
# ============================================================================
EXIT_COMMANDS = ["quit", "exit"]

# ============================================================================
# Clarification Capabilities — what the SLM can help with
# ============================================================================
CLARIFICATION_CAPABILITIES = [
    "start a new game",
    "place a move",
    "check the board",
    "check the status",
    "say goodbye",
]

# ============================================================================
# Board Position Names
# ============================================================================
ROW_NAMES = ["top", "middle", "bottom"]
COL_NAMES = ["left", "center", "right"]

# Position mappings — name → coordinates (derived from ROW_NAMES × COL_NAMES)
POSITION_MAPPINGS: dict[str, dict[str, int]] = {
    f"{row}_{col}": {"row": r, "col": c}
    for r, row in enumerate(ROW_NAMES)
    for c, col in enumerate(COL_NAMES)
}
