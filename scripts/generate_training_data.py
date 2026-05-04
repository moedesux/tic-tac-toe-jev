"""
Generate training data for tic-tac-toe finetuning.
Generates 800 training samples and 200 evaluation samples for SLM finetuning.

Format:
- question: JSON string with multi-turn conversation including assistant tool_calls
- answer: JSON string with final function name and parameters

Key structure:
- tool_calls use "arguments" key (NOT "parameters")
- Final answer uses "parameters" key
- 1-indexed user text → 0-indexed model outputs for place_move
- ASR artifacts applied to user turns (~70% intensity)
"""

import json
import random
from pathlib import Path
from typing import List, Dict, Any, Optional

# Set random seed for reproducibility
random.seed(42)

# Training sample counts (total: 800)
TRAIN_COUNTS = {
    "start_game": 100,
    "get_board": 100,
    "place_move": 110,
    "get_status": 100,
    "greeting": 90,
    "goodbye": 80,
    "thank_you": 90,
    "intent_unclear": 60,
    "multi_turn": 70,
}

# Evaluation sample counts (total: 200)
EVAL_COUNTS = {
    "start_game": 25,
    "get_board": 25,
    "place_move": 30,
    "get_status": 25,
    "greeting": 20,
    "goodbye": 20,
    "thank_you": 20,
    "intent_unclear": 18,
    "multi_turn": 17,
}


def add_filler_words(text: str) -> str:
    """Add filler words like um, uh, like, you know."""
    fillers = [" um", " uh", " like", " you know", " I mean", " so"]
    words = text.split()
    result = []
    for word in words:
        result.append(word)
        if len(result) % 3 == 0 and random.random() < 0.3:
            result.append(random.choice(fillers))
    return " ".join(result)


def add_word_repeats(text: str) -> str:
    """Add repeated letters or words."""
    words = text.split()
    result = []
    for word in words:
        result.append(word)
        if len(result) % 4 == 0 and random.random() < 0.2:
            result.append(word)
    return " ".join(result)


def add_elision(text: str) -> str:
    """Add elisions like wanna, gonna, gotta."""
    substitutions = {
        "want to": "wanna",
        "going to": "gonna",
        "got to": "gotta",
        "let me": "lemme",
        "give me": "giveme",
    }
    for original, elided in substitutions.items():
        if original in text and random.random() < 0.4:
            text = text.replace(original, elided, 1)
    return text


def add_self_correction(text: str) -> str:
    """Add self-corrections like start... I mean begin."""
    corrections = [
        ("start", "begin"),
        ("play", "have a game"),
        ("board", "grid"),
        ("move", "turn"),
        ("position", "spot"),
    ]
    for original, correction in corrections:
        if original in text and random.random() < 0.2:
            text = text.replace(original, f"{original}... I mean {correction}", 1)
    return text


def add_word_splits(text: str) -> str:
    """Split words like tic-tac-toe into tic tac toe."""
    splits = {
        "tic-tac-toe": "tic tac toe",
        "X": "X mark",
        "O": "O mark",
    }
    for original, split in splits.items():
        if original in text and random.random() < 0.3:
            text = text.replace(original, split, 1)
    return text


def add_homophones(text: str) -> str:
    """Replace words with homophones."""
    homophones = {
        "to": "two",
        "for": "four",
        "there": "their",
        "their": "there",
    }
    for original, replacement in homophones.items():
        if f" {original} " in text and random.random() < 0.1:
            text = text.replace(f" {original} ", f" {replacement} ", 1)
    return text


def apply_asr_artifacts(text: str, intensity: float = 0.7) -> str:
    """Apply ASR artifacts with given intensity (~70% for user turns)."""
    if not text:
        return text
    if random.random() < intensity:
        text = add_filler_words(text)
    if random.random() < intensity:
        text = add_word_repeats(text)
    if random.random() < intensity:
        text = add_elision(text)
    if random.random() < intensity:
        text = add_self_correction(text)
    if random.random() < intensity:
        text = add_word_splits(text)
    if random.random() < intensity:
        text = add_homophones(text)
    return text


# Function templates
START_GAME_TEMPLATES = [
    "I want to start a new game of tic-tac-toe",
    "Let's begin a tic-tac-toe game",
    "Can we start playing tic-tac-toe?",
    "I'd like to have a game of tic tac toe",
    "Start a new tic-tac-toe match",
    "Begin a fresh game of tic-tac-toe",
    "Let's play tic-tac-toe",
    "Can you start a tic-tac-toe game for me?",
    "I want to begin a new round of tic-tac-toe",
    "Let's start a game of tic tac toe",
    "Please start a fresh tic-tac-toe game",
    "I'm ready to play tic-tac-toe",
    "Can we begin a game of tic-tac-toe?",
    "Start playing tic-tac-toe with me",
    "Let's have a tic-tac-toe match",
    "I'd like to start a new tic-tac-toe game",
    "Begin a new game of tic tac toe",
    "Can we start a tic-tac-toe match?",
    "Let's kick off a game of tic-tac-toe",
    "I want to play a game of tic-tac-toe",
]

GET_BOARD_TEMPLATES = [
    "Show me the current board",
    "What does the board look like now?",
    "Display the tic-tac-toe board",
    "I need to see the board state",
    "What's on the board?",
    "Can you show me the board?",
    "Display the current game board",
    "What does the grid look like?",
    "Show the board state",
    "I want to see the current board",
    "What's the board configuration?",
    "Display the board for me",
    "What does the tic-tac-toe grid look like?",
    "Show me the board layout",
    "What's on the game board?",
    "Can I see the current board?",
    "Display the board layout",
    "What's the state of the board?",
    "Show the current game state",
    "I need to see what's on the board",
]

PLACE_MOVE_TEMPLATES = [
    "Place X at row {row}, column {col}",
    "Put my mark at position {row}, {col}",
    "I want to place X in row {row} column {col}",
    "Place X at {row}-{col}",
    "My move: X at row {row}, col {col}",
    "Put X in the cell at {row}, {col}",
    "I'll place my mark at {row}, {col}",
    "Place my X at position {row}, {col}",
    "Make a move at row {row}, column {col}",
    "I want to put X at {row}, {col}",
    "Place X in row {row} and column {col}",
    "My turn: place X at {row}, {col}",
    "Put my mark in cell {row}, {col}",
    "I'd like to place X at {row}, {col}",
    "Make my move at {row}, {col}",
    "Place my X in position {row}, {col}",
    "I'll put X at row {row}, column {col}",
    "Place X at the spot {row}, {col}",
    "My move is at {row}, {col}",
    "Put X in row {row}, col {col}",
]

POSITION_CONVERSION_TEMPLATES = [
    "Place X at position {pos}",
    "Put my mark at spot {pos}",
    "I want to place X in position {pos}",
    "Place X at cell {pos}",
    "My move: position {pos}",
    "Put X in position {pos}",
    "I'll place my mark at {pos}",
    "Place my X at position {pos}",
    "Make a move at position {pos}",
    "I want to put X at {pos}",
]

GET_STATUS_TEMPLATES = [
    "What's the game status?",
    "How is the game going?",
    "Tell me the current status",
    "What's the state of the game?",
    "How's the match progressing?",
    "Can you tell me the status?",
    "What's the current game state?",
    "How is tic-tac-toe going?",
    "Tell me about the game status",
    "What's happening in the game?",
    "What's the status of our match?",
    "How's the game progressing?",
    "Can I get the current status?",
    "What's the game situation?",
    "Tell me the game status",
    "What's the current state?",
    "How's our game going?",
    "What's the match status?",
    "Tell me the current game situation",
    "What's the status right now?",
]

GREETING_TEMPLATES = [
    "Hello!",
    "Hi there!",
    "Hey!",
    "Good morning!",
    "Good afternoon!",
    "Good evening!",
    "Greetings!",
    "Hi!",
    "Hello friend!",
    "Hey there!",
    "Good day!",
    "Hi, how are you?",
    "Hello, nice to meet you!",
    "Hey, what's up?",
    "Good morning, friend!",
    "Hi there, nice to see you!",
    "Hello!",
    "Hey, how's it going?",
    "Good afternoon!",
    "Hi, hello!",
]

GOODBYE_TEMPLATES = [
    "Goodbye!",
    "Bye!",
    "See you later!",
    "I'm leaving now",
    "That's all for me",
    "I have to go",
    "Take care!",
    "Until next time!",
    "Bye bye!",
    "I'm done here",
    "Signing off!",
    "See ya!",
    "Have a good one!",
    "Farewell!",
    "I'm heading out",
    "Bye for now!",
    "Catch you later!",
    "Good night!",
    "I'll be going now",
    "Peace out!",
]

THANK_YOU_TEMPLATES = [
    "Thank you!",
    "Thanks!",
    "I appreciate it",
    "Thank you very much",
    "Thanks a lot!",
    "I'm grateful",
    "Much appreciated!",
    "Thanks so much!",
    "I thank you",
    "Thank you for your help",
    "Thanks for everything",
    "I'm thankful",
    "Much thanks!",
    "Thanks a bunch!",
    "I'm so grateful",
    "Thank you kindly",
    "Thanks for your assistance",
    "I appreciate your help",
    "Thank you dear",
    "Thanks again!",
]

INTENT_UNCLEAR_TEMPLATES = [
    "Um... I'm not sure what to say",
    "Hello... I think...",
    "Can you help me with something?",
    "I'm trying to figure something out",
    "What can I do here?",
    "I have a question but...",
    "Um, I'm confused",
    "Can you tell me about this game?",
    "I'm not sure how to proceed",
    "What are the rules?",
    "I need some guidance",
    "Can you explain something?",
    "I'm lost here",
    "What should I do?",
    "I'm trying to understand",
    "Can you help me out?",
    "I'm not sure about this",
    "What's going on?",
    "I need clarification",
    "Can you guide me?",
]


def convert_position_to_row_col(pos: int) -> Dict[str, int]:
    """Convert 0-indexed position (0-8) to row and column (0-2)."""
    row = pos // 3
    col = pos % 3
    return {"row": row, "col": col}


def create_tool_call(function_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Create a tool_calls structure with arguments key."""
    return {
        "type": "function",
        "function": {
            "name": function_name,
            "arguments": arguments,
        },
    }


def create_training_format(
    conversation: List[Dict[str, Any]],
    answer: Dict[str, Any],
) -> Dict[str, str]:
    """Convert to training data format with JSON strings for question and answer."""
    return {
        "question": json.dumps(conversation),
        "answer": json.dumps(answer),
    }


def create_2_turn_conversation(
    user_text: str,
    function_name: str,
    function_args: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Create a 2-turn conversation: user greeting + assistant tool_call + user text."""
    return [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call("greeting", {})],
        },
        {"role": "user", "content": user_text},
    ]


def create_3_turn_conversation(
    first_action: str,
    first_function: str,
    first_args: Dict[str, Any],
    user_text: str,
    function_name: str,
    function_args: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Create a 3-turn conversation with initial action."""
    return [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call("greeting", {})],
        },
        {"role": "user", "content": first_action},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call(first_function, first_args)],
        },
        {"role": "user", "content": user_text},
    ]


def create_4_turn_conversation(
    first_action: str,
    first_function: str,
    first_args: Dict[str, Any],
    second_action: str,
    second_function: str,
    second_args: Dict[str, Any],
    user_text: str,
    function_name: str,
    function_args: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Create a 4-turn conversation with two initial actions."""
    return [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call("greeting", {})],
        },
        {"role": "user", "content": first_action},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call(first_function, first_args)],
        },
        {"role": "user", "content": second_action},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call(second_function, second_args)],
        },
        {"role": "user", "content": user_text},
    ]


def create_5_turn_conversation(
    first_action: str,
    first_function: str,
    first_args: Dict[str, Any],
    second_action: str,
    second_function: str,
    second_args: Dict[str, Any],
    third_action: str,
    third_function: str,
    third_args: Dict[str, Any],
    user_text: str,
    function_name: str,
    function_args: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Create a 5-turn conversation with three initial actions."""
    return [
        {"role": "user", "content": "Hello"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call("greeting", {})],
        },
        {"role": "user", "content": first_action},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call(first_function, first_args)],
        },
        {"role": "user", "content": second_action},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call(second_function, second_args)],
        },
        {"role": "user", "content": third_action},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [create_tool_call(third_function, third_args)],
        },
        {"role": "user", "content": user_text},
    ]


def generate_start_game_samples(count: int) -> List[Dict[str, Any]]:
    """Generate start_game function samples with multi-turn conversations."""
    samples = []
    for _ in range(count):
        template = random.choice(START_GAME_TEMPLATES)
        text = apply_asr_artifacts(template, 0.7)

        # 30% 2-turn, 50% 3-turn, 20% 4+ turn distribution
        turn_choice = random.random()
        if turn_choice < 0.3:
            # 2-turn: greeting → start_game
            conversation = create_2_turn_conversation(text, "start_game", {})
        elif turn_choice < 0.8:
            # 3-turn: greeting → start_game → thank_you → start_game
            conversation = create_3_turn_conversation(
                "Let's start",
                "start_game",
                {},
                text,
                "start_game",
                {},
            )
        else:
            # 4-turn: greeting → thank_you → start_game → get_board → start_game
            conversation = create_4_turn_conversation(
                "Thank you",
                "thank_you",
                {},
                "Start a game",
                "start_game",
                {},
                text,
                "start_game",
                {},
            )

        samples.append(
            create_training_format(
                conversation,
                {"name": "start_game", "parameters": {}},
            )
        )
    return samples


def generate_get_board_samples(count: int) -> List[Dict[str, Any]]:
    """Generate get_board function samples with multi-turn conversations."""
    samples = []
    for _ in range(count):
        template = random.choice(GET_BOARD_TEMPLATES)
        text = apply_asr_artifacts(template, 0.7)

        turn_choice = random.random()
        if turn_choice < 0.3:
            # 2-turn
            conversation = create_2_turn_conversation(text, "get_board", {})
        elif turn_choice < 0.8:
            # 3-turn: greeting → start_game → get_board
            conversation = create_3_turn_conversation(
                "Start a new game",
                "start_game",
                {},
                text,
                "get_board",
                {},
            )
        else:
            # 4-turn: greeting → start_game → thank_you → get_board
            conversation = create_4_turn_conversation(
                "Start a game",
                "start_game",
                {},
                "Thanks",
                "thank_you",
                {},
                text,
                "get_board",
                {},
            )

        samples.append(
            create_training_format(
                conversation,
                {"name": "get_board", "parameters": {}},
            )
        )
    return samples


def generate_place_move_samples(
    count: int, position_conversion_count: int = 0
) -> List[Dict[str, Any]]:
    """Generate place_move function samples with multi-turn conversations."""
    samples = []

    # Regular row/col samples
    regular_count = count - position_conversion_count
    for _ in range(regular_count):
        template = random.choice(PLACE_MOVE_TEMPLATES)
        # Generate 1-indexed for user-facing text
        row_1indexed = random.randint(1, 3)
        col_1indexed = random.randint(1, 3)
        # Convert to 0-indexed for API parameters
        row_0indexed = row_1indexed - 1
        col_0indexed = col_1indexed - 1
        text = template.format(row=row_1indexed, col=col_1indexed)
        text = apply_asr_artifacts(text, 0.7)

        turn_choice = random.random()
        if turn_choice < 0.3:
            # 2-turn
            conversation = create_2_turn_conversation(
                text, "place_move", {"row": row_0indexed, "col": col_0indexed}
            )
        elif turn_choice < 0.8:
            # 3-turn: greeting → start_game → place_move
            conversation = create_3_turn_conversation(
                "Start a game",
                "start_game",
                {},
                text,
                "place_move",
                {"row": row_0indexed, "col": col_0indexed},
            )
        else:
            # 4-turn: greeting → start_game → get_board → place_move
            conversation = create_4_turn_conversation(
                "Start a game",
                "start_game",
                {},
                "Show the board",
                "get_board",
                {},
                text,
                "place_move",
                {"row": row_0indexed, "col": col_0indexed},
            )

        samples.append(
            create_training_format(
                conversation,
                {
                    "name": "place_move",
                    "parameters": {"row": row_0indexed, "col": col_0indexed},
                },
            )
        )

    # Position conversion samples
    for _ in range(position_conversion_count):
        template = random.choice(POSITION_CONVERSION_TEMPLATES)
        # Generate 1-indexed position for user-facing text (1-9)
        pos_1indexed = random.randint(1, 9)
        # Convert to 0-indexed for API parameters
        pos_0indexed = pos_1indexed - 1
        text = template.format(pos=pos_1indexed)
        text = apply_asr_artifacts(text, 0.7)
        row_col = convert_position_to_row_col(pos_0indexed)

        turn_choice = random.random()
        if turn_choice < 0.3:
            # 2-turn
            conversation = create_2_turn_conversation(text, "place_move", row_col)
        elif turn_choice < 0.8:
            # 3-turn
            conversation = create_3_turn_conversation(
                "Start a game",
                "start_game",
                {},
                text,
                "place_move",
                row_col,
            )
        else:
            # 4-turn
            conversation = create_4_turn_conversation(
                "Start a game",
                "start_game",
                {},
                "Show board",
                "get_board",
                {},
                text,
                "place_move",
                row_col,
            )

        samples.append(
            create_training_format(
                conversation,
                {"name": "place_move", "parameters": row_col},
            )
        )

    return samples


def generate_get_status_samples(count: int) -> List[Dict[str, Any]]:
    """Generate get_status function samples with multi-turn conversations."""
    samples = []
    for _ in range(count):
        template = random.choice(GET_STATUS_TEMPLATES)
        text = apply_asr_artifacts(template, 0.7)

        turn_choice = random.random()
        if turn_choice < 0.3:
            # 2-turn
            conversation = create_2_turn_conversation(text, "get_status", {})
        elif turn_choice < 0.8:
            # 3-turn: greeting → start_game → get_status
            conversation = create_3_turn_conversation(
                "Start a game",
                "start_game",
                {},
                text,
                "get_status",
                {},
            )
        else:
            # 4-turn: greeting → start_game → place_move → get_status
            conversation = create_4_turn_conversation(
                "Start a game",
                "start_game",
                {},
                "Place X at row 1, column 1",
                "place_move",
                {"row": 0, "col": 0},
                text,
                "get_status",
                {},
            )

        samples.append(
            create_training_format(
                conversation,
                {"name": "get_status", "parameters": {}},
            )
        )
    return samples


def generate_greeting_samples(count: int) -> List[Dict[str, Any]]:
    """Generate greeting function samples."""
    samples = []
    for _ in range(count):
        template = random.choice(GREETING_TEMPLATES)
        text = apply_asr_artifacts(template, 0.7)
        # Simple 2-turn: user greeting
        conversation = [{"role": "user", "content": text}]
        samples.append(
            create_training_format(
                conversation,
                {"name": "greeting", "parameters": {}},
            )
        )
    return samples


def generate_goodbye_samples(count: int) -> List[Dict[str, Any]]:
    """Generate goodbye function samples."""
    samples = []
    for _ in range(count):
        template = random.choice(GOODBYE_TEMPLATES)
        text = apply_asr_artifacts(template, 0.7)
        # Simple 2-turn: user goodbye
        conversation = [{"role": "user", "content": text}]
        samples.append(
            create_training_format(
                conversation,
                {"name": "goodbye", "parameters": {}},
            )
        )
    return samples


def generate_thank_you_samples(count: int) -> List[Dict[str, Any]]:
    """Generate thank_you function samples."""
    samples = []
    for _ in range(count):
        template = random.choice(THANK_YOU_TEMPLATES)
        text = apply_asr_artifacts(template, 0.7)
        # Simple 2-turn: user thank you
        conversation = [{"role": "user", "content": text}]
        samples.append(
            create_training_format(
                conversation,
                {"name": "thank_you", "parameters": {}},
            )
        )
    return samples


def generate_intent_unclear_samples(count: int) -> List[Dict[str, Any]]:
    """Generate intent_unclear function samples."""
    samples = []
    for _ in range(count):
        template = random.choice(INTENT_UNCLEAR_TEMPLATES)
        text = apply_asr_artifacts(template, 0.7)
        # Simple 2-turn: user unclear intent
        conversation = [{"role": "user", "content": text}]
        samples.append(
            create_training_format(
                conversation,
                {"name": "intent_unclear", "parameters": {}},
            )
        )
    return samples


def generate_multi_turn_samples(count: int) -> List[Dict[str, Any]]:
    """Generate multi-turn conversation samples (4+ turns)."""
    samples = []

    # 50% 4-turn, 30% 5-turn, 20% 6+ turn
    for i in range(count):
        turn_choice = random.random()

        if turn_choice < 0.5:
            # 4-turn: full game flow
            row_1indexed = random.randint(1, 3)
            col_1indexed = random.randint(1, 3)
            row_0indexed = row_1indexed - 1
            col_0indexed = col_1indexed - 1

            move_template = random.choice(PLACE_MOVE_TEMPLATES)
            move_text = move_template.format(row=row_1indexed, col=col_1indexed)
            move_text = apply_asr_artifacts(move_text, 0.7)

            conversation = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("greeting", {})],
                },
                {"role": "user", "content": "Start a game"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("start_game", {})],
                },
                {"role": "user", "content": move_text},
            ]

            samples.append(
                create_training_format(
                    conversation,
                    {
                        "name": "place_move",
                        "parameters": {"row": row_0indexed, "col": col_0indexed},
                    },
                )
            )

        elif turn_choice < 0.8:
            # 5-turn: game with board view
            row_1indexed = random.randint(1, 3)
            col_1indexed = random.randint(1, 3)
            row_0indexed = row_1indexed - 1
            col_0indexed = col_1indexed - 1

            move_template = random.choice(PLACE_MOVE_TEMPLATES)
            move_text = move_template.format(row=row_1indexed, col=col_1indexed)
            move_text = apply_asr_artifacts(move_text, 0.7)

            conversation = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("greeting", {})],
                },
                {"role": "user", "content": "Start a game"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("start_game", {})],
                },
                {"role": "user", "content": "Show me the board"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("get_board", {})],
                },
                {"role": "user", "content": move_text},
            ]

            samples.append(
                create_training_format(
                    conversation,
                    {
                        "name": "place_move",
                        "parameters": {"row": row_0indexed, "col": col_0indexed},
                    },
                )
            )

        else:
            # 6+ turn: complete game flow with status check
            row1_1indexed = random.randint(1, 3)
            col1_1indexed = random.randint(1, 3)
            row1_0indexed = row1_1indexed - 1
            col1_0indexed = col1_1indexed - 1

            row2_1indexed = random.randint(1, 3)
            col2_1indexed = random.randint(1, 3)
            row2_0indexed = row2_1indexed - 1
            col2_0indexed = col2_1indexed - 1

            move1_template = random.choice(PLACE_MOVE_TEMPLATES)
            move1_text = move1_template.format(row=row1_1indexed, col=col1_1indexed)
            move1_text = apply_asr_artifacts(move1_text, 0.7)

            move2_template = random.choice(PLACE_MOVE_TEMPLATES)
            move2_text = move2_template.format(row=row2_1indexed, col=col2_1indexed)
            move2_text = apply_asr_artifacts(move2_text, 0.7)

            conversation = [
                {"role": "user", "content": "Hello"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("greeting", {})],
                },
                {"role": "user", "content": "Start a game"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("start_game", {})],
                },
                {"role": "user", "content": move1_text},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        create_tool_call(
                            "place_move", {"row": row1_0indexed, "col": col1_0indexed}
                        )
                    ],
                },
                {"role": "user", "content": "Show the board"},
                {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [create_tool_call("get_board", {})],
                },
                {"role": "user", "content": move2_text},
            ]

            samples.append(
                create_training_format(
                    conversation,
                    {
                        "name": "place_move",
                        "parameters": {"row": row2_0indexed, "col": col2_0indexed},
                    },
                )
            )

    return samples


def generate_all_samples(
    train_counts: Dict[str, int], eval_counts: Dict[str, int]
) -> tuple:
    """Generate all training and evaluation samples."""
    train_samples = []
    eval_samples = []

    # start_game
    train_samples.extend(generate_start_game_samples(train_counts["start_game"]))
    eval_samples.extend(generate_start_game_samples(eval_counts["start_game"]))

    # get_board
    train_samples.extend(generate_get_board_samples(train_counts["get_board"]))
    eval_samples.extend(generate_get_board_samples(eval_counts["get_board"]))

    # place_move (with 50 position conversion samples for train)
    train_samples.extend(generate_place_move_samples(train_counts["place_move"], 50))
    eval_samples.extend(generate_place_move_samples(eval_counts["place_move"], 10))

    # get_status
    train_samples.extend(generate_get_status_samples(train_counts["get_status"]))
    eval_samples.extend(generate_get_status_samples(eval_counts["get_status"]))

    # greeting
    train_samples.extend(generate_greeting_samples(train_counts["greeting"]))
    eval_samples.extend(generate_greeting_samples(eval_counts["greeting"]))

    # goodbye
    train_samples.extend(generate_goodbye_samples(train_counts["goodbye"]))
    eval_samples.extend(generate_goodbye_samples(eval_counts["goodbye"]))

    # thank_you
    train_samples.extend(generate_thank_you_samples(train_counts["thank_you"]))
    eval_samples.extend(generate_thank_you_samples(eval_counts["thank_you"]))

    # intent_unclear
    train_samples.extend(
        generate_intent_unclear_samples(train_counts["intent_unclear"])
    )
    eval_samples.extend(generate_intent_unclear_samples(eval_counts["intent_unclear"]))

    # multi_turn
    train_samples.extend(generate_multi_turn_samples(train_counts["multi_turn"]))
    eval_samples.extend(generate_multi_turn_samples(eval_counts["multi_turn"]))

    return train_samples, eval_samples


def write_jsonl(samples: List[Dict[str, Any]], filepath: str) -> None:
    """Write samples to JSONL file."""
    with open(filepath, "w") as f:
        for sample in samples:
            f.write(json.dumps(sample) + "\n")


def main():
    """Main function to generate and write training data."""
    print("Generating training data...")

    train_samples, eval_samples = generate_all_samples(TRAIN_COUNTS, EVAL_COUNTS)

    # Write to files
    train_filepath = Path(__file__).parent.parent / "data/finetune-train.jsonl"
    eval_filepath = Path(__file__).parent.parent / "data/finetune-eval.jsonl"

    write_jsonl(train_samples, train_filepath)
    write_jsonl(eval_samples, eval_filepath)

    print(f"Generated {len(train_samples)} training samples")
    print(f"Generated {len(eval_samples)} evaluation samples")
    print(f"Training data written to: {train_filepath}")
    print(f"Evaluation data written to: {eval_filepath}")

    # Print sample format
    print("\nSample format:")
    print(f"Question: {train_samples[0]['question'][:200]}...")
    print(f"Answer: {train_samples[0]['answer']}")


if __name__ == "__main__":
    main()
