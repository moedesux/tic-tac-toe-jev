"""TypeSafe Jev adapter for the Player Command interpreter seam.

This is the only module where TypeSafe SDK request and response types are used.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul

from backend.models import CommandIntent, GameResponse, MovePosition
from backend.player_command import CommandInterpretation

INTENT_CRITERIA = {
    CommandIntent.GREETING.value: "The player greets the game or says hello.",
    CommandIntent.START_GAME.value: (
        "The player explicitly asks to start, begin, restart, or play a game."
    ),
    CommandIntent.SHOW_BOARD.value: (
        "The player asks to see or hear the current board arrangement."
    ),
    CommandIntent.SHOW_STATUS.value: (
        "The player asks whose turn it is or whether the game is ongoing, won, or drawn."
    ),
    CommandIntent.PLACE_MOVE.value: "The player asks to place their mark in a specific board cell.",
    CommandIntent.THANKS.value: "The player expresses thanks or appreciation.",
    CommandIntent.GOODBYE.value: "The player says goodbye or asks to leave.",
    CommandIntent.UNCLEAR.value: (
        "The request has none of the supported meanings or is too unclear to classify."
    ),
}

POSITION_CRITERIA = {
    position.value: (
        f"The requested move position is {position.value.replace('_', ' ')}. "
        f"Also accept these equivalent descriptions: {', '.join(position.aliases)}."
    )
    for position in MovePosition
}


class JevCommandInterpreter:
    """Translate one Jev Choice answer into a domain interpretation."""

    def __init__(self, client: Any) -> None:
        self._client = client

    async def interpret(
        self,
        control: str,
        game_state: GameResponse | None,
    ) -> CommandInterpretation:
        response = await self._client.system_one(
            state={
                "natural_language_control": control,
                "game": game_state.model_dump(mode="json") if game_state else None,
            },
            questions={
                "intent": Choice(
                    instructions=(
                        "Which single supported Command Intent best represents "
                        "the player's Natural-Language Control?"
                    ),
                    criteria=INTENT_CRITERIA,
                ),
                "position": Choice(
                    instructions=(
                        "Which single Move Position did the player identify? "
                        "Use the board and utterance; never choose a position strategically."
                    ),
                    criteria=POSITION_CRITERIA,
                ),
                "position_present": Noul(
                    instructions="Did the player identify a specific board cell for this command?",
                ),
                "position_unique": Noul(
                    instructions="Does the player's board-relative description identify exactly one cell?",
                ),
            },
        )
        answer = response.choices["intent"]
        position_answer = response.choices.get("position")
        presence_answer = response.choices.get("position_present")
        uniqueness_answer = response.choices.get("position_unique")
        has_position = (
            position_answer is not None
            and (presence_answer is None or getattr(presence_answer, "noul", 1.0) >= 0.5)
            and (uniqueness_answer is None or getattr(uniqueness_answer, "noul", 1.0) >= 0.5)
        )
        return CommandInterpretation(
            intent=CommandIntent(answer.choice),
            confidence=answer.confidence,
            position=(MovePosition(position_answer.choice) if has_position else None),
            position_confidence=(position_answer.confidence if has_position else 0.0),
        )


@asynccontextmanager
async def open_jev_command_interpreter() -> AsyncIterator[JevCommandInterpreter]:
    """Own one SDK client while exposing only the domain interpreter seam."""
    async with AsyncTypeSafeClient() as client:
        yield JevCommandInterpreter(client)
