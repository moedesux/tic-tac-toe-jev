"""TypeSafe Jev adapter for the Player Command interpreter seam.

This is the only module where TypeSafe SDK request and response types are used.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import os
from typing import Any

from typesafe_sdk import AsyncTypeSafeClient, Choice, Noul

from backend.models import CommandIntent, GameResponse, MovePosition, PendingCommand
from backend.player_command import CommandInterpretation

INTENT_CRITERIA = {
    CommandIntent.GREETING.value: "The player greets the game or says hello.",
    CommandIntent.START_GAME.value: (
        "The player explicitly asks to start, begin, restart, reset, or create a new game. "
        "If the utterance starts a game and also requests an initial move, select start_game. "
        "Do not classify a request to play/place/put a mark as start_game when it does not start a game."
    ),
    CommandIntent.SHOW_BOARD.value: (
        "The player asks to see or hear the current board arrangement."
    ),
    CommandIntent.SHOW_STATUS.value: (
        "The player asks whose turn it is or whether the game is ongoing, won, or drawn."
    ),
    CommandIntent.PLACE_MOVE.value: (
        "The player asks to play, place, or put their mark in a board cell, "
        "including requests that say play followed by a position (for example, "
        "'play center'), but not when the same utterance starts or restarts a game."
    ),
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
POSITION_CRITERIA["no_match"] = (
    "The player did not identify exactly one board cell; the wording is missing, "
    "vague, or matches more than one cell."
)
POSITION_REFERENCE_CONFIDENCE = 0.40

BOARD_CELLS = [position.value for position in MovePosition]
BOARD_CELL_ALIASES = {
    position.value: list(position.aliases) for position in MovePosition
}


class JevCommandInterpreter:
    """Translate one Jev Choice answer into a domain interpretation."""

    def __init__(self, client: Any) -> None:
        self._client = client
        self.last_model: str | None = None

    async def interpret(
        self,
        control: str,
        game_state: GameResponse | None,
        pending: PendingCommand | None = None,
    ) -> CommandInterpretation:
        state = self._request_state(control, game_state, pending)
        questions = {
            "intent": Choice(
                instructions=(
                    "Using `natural_language_control` and the named game facts, choose exactly one "
                    "supported Command Intent. Treat an explicit request to start/restart as "
                    "start_game even if it also asks for a first move; choose place_move only "
                    "when no start/restart is requested. Classify the requested meaning regardless "
                    "of whether the current game makes it legal; application code handles legality. "
                    "Choose unclear when no criterion matches or the wording is insufficient."
                ),
                criteria=INTENT_CRITERIA,
            ),
            "state_change_requested": Noul(
                instructions=(
                    "Does `natural_language_control` clearly direct the application to change game "
                    "state now by starting/restarting a game or placing a mark? Return no for "
                    "hypothetical, merely contemplated, hedged, or unresolved alternatives such as "
                    "'I might', 'maybe', or 'start over or keep this game'. This judgment concerns "
                    "commitment to act, not whether the requested action is legal."
                ),
            ),
            "position": Choice(
                instructions=(
                    "Using `natural_language_control`, `board.cells`, and `board.open_cells`, "
                    "choose the one Move Position explicitly identified by the player. A board-"
                    "relative phrase may select a cell only when the wording and named open cells "
                    "make exactly one match. Never infer a strategic choice. If no single cell is "
                    "identified, choose `no_match`. The separate presence and uniqueness judgments "
                    "also decide whether a selected cell is usable."
                ),
                criteria=POSITION_CRITERIA,
            ),
            "position_present": Noul(
                instructions=(
                    "Does `natural_language_control` identify any specific cell from `board.cells` "
                    "or `board.aliases`? Canonical references include top left, top center, top right, "
                    "middle left, center, middle right, bottom left, bottom center, and bottom right; "
                    "the literal word center is a concrete cell reference. Return yes for one of "
                    "those references or a uniquely resolved board-relative reference; return no "
                    "for vague wording such as somewhere, there, or somewhere in the middle."
                ),
            ),
            "position_unique": Noul(
                instructions=(
                    "Does the position wording identify exactly one cell among `board.cells`, "
                    "considering `board.open_cells` and `board.aliases`? An exact canonical cell or "
                    "alias—including the literal word center—is unique. A board-relative reference "
                    "is unique only when the named open cells leave one match; vague or multiply "
                    "matching wording is no."
                ),
            ),
            "initial_move_requested": Noul(
                instructions=(
                    "Is `natural_language_control` a start/restart request that also explicitly "
                    "asks to place a first mark? This is independent of the intent judgment: return "
                    "yes only when both start_game and an initial move are stated, otherwise no."
                ),
            ),
        }
        if pending is not None:
            # These independent judgments are deliberately part of the same
            # request as intent/position; the processor never calls Jev again
            # to classify a follow-up.
            questions.update(
                {
                    "pending_cancel": Noul(
                        instructions="Given `pending.proposed_position` and `pending.follow_up_options`, does `natural_language_control` clearly cancel the pending move? Return yes only for cancellation.",
                    ),
                    "pending_affirm": Noul(
                        instructions="Given `pending.proposed_position` and `pending.follow_up_options`, does `natural_language_control` clearly affirm that proposed position? Return yes only for affirmation.",
                    ),
                    "pending_reject": Noul(
                        instructions="Given `pending.proposed_position` and `pending.follow_up_options`, does `natural_language_control` clearly reject the proposed position while continuing the move request? Return yes only for rejection.",
                    ),
                }
            )
        response = await self._client.system_one(
            state=state,
            questions=questions,
        )
        self.last_model = getattr(response, "model", None)
        answer = response.choices["intent"]
        position_answer = response.choices.get("position")
        nouls = response.nouls
        presence_answer = nouls.get("position_present")
        uniqueness_answer = nouls.get("position_unique")
        position_present_confidence = getattr(presence_answer, "noul", 0.0)
        position_unique_confidence = getattr(uniqueness_answer, "noul", 0.0)
        position_choice = position_answer.choice if position_answer is not None else None
        position_choice_confidence = (
            position_answer.confidence if position_answer is not None else 0.0
        )
        if (
            position_choice == "no_match"
            and position_present_confidence >= POSITION_REFERENCE_CONFIDENCE
            and position_unique_confidence >= POSITION_REFERENCE_CONFIDENCE
        ):
            probabilities = getattr(position_answer, "probabilities", {})
            real_positions = {
                position.value: probabilities.get(position.value, 0.0)
                for position in MovePosition
            }
            position_choice, position_choice_confidence = max(
                real_positions.items(), key=lambda item: item[1]
            )
        has_position = (
            position_answer is not None
            and position_choice != "no_match"
            and position_choice_confidence > 0.0
            and position_present_confidence >= POSITION_REFERENCE_CONFIDENCE
            and position_unique_confidence >= POSITION_REFERENCE_CONFIDENCE
        )
        initial_move_confidence = getattr(nouls.get("initial_move_requested"), "noul", 0.0)
        state_change_confidence = getattr(nouls.get("state_change_requested"), "noul", 0.0)
        intent = CommandIntent(answer.choice)
        confidence = answer.confidence
        if intent in {CommandIntent.START_GAME, CommandIntent.PLACE_MOVE}:
            confidence = min(confidence, state_change_confidence)
        return CommandInterpretation(
            intent=intent,
            confidence=confidence,
            position=(MovePosition(position_choice) if has_position else None),
            position_confidence=(position_choice_confidence if has_position else 0.0),
            initial_move_requested=initial_move_confidence >= 0.5,
            position_present_confidence=position_present_confidence,
            position_unique_confidence=position_unique_confidence,
            initial_move_confidence=initial_move_confidence,
            state_change_confidence=state_change_confidence,
            cancel_confidence=getattr(nouls.get("pending_cancel"), "noul", 0.0),
            affirm_confidence=getattr(nouls.get("pending_affirm"), "noul", 0.0),
            reject_confidence=getattr(nouls.get("pending_reject"), "noul", 0.0),
        )

    @staticmethod
    def _request_state(
        control: str,
        game_state: GameResponse | None,
        pending: PendingCommand | None,
    ) -> dict[str, Any]:
        board = game_state.board if game_state else [None] * len(BOARD_CELLS)
        occupied = [
            {"cell": cell, "mark": mark}
            for cell, mark in zip(BOARD_CELLS, board)
            if mark is not None
        ]
        open_cells = [cell for cell, mark in zip(BOARD_CELLS, board) if mark is None]
        return {
            "natural_language_control": control,
            "game": game_state.model_dump(mode="json") if game_state else None,
            "pending_command": pending.model_dump(mode="json") if pending else None,
            "board": {
                "cells": BOARD_CELLS,
                "aliases": BOARD_CELL_ALIASES,
                "occupied": occupied,
                "open_cells": open_cells,
                "turn": game_state.turn if game_state else None,
                "lifecycle": game_state.status if game_state else "not_started",
            },
            "pending": {
                "is_follow_up": pending is not None,
                "proposed_position": pending.position.value if pending and pending.position else None,
                "follow_up_options": ["cancel", "affirm", "reject"] if pending else [],
            },
            "application_rules": {
                "only_open_cells_can_execute": True,
                "ambiguous_or_missing_position_must_not_execute": True,
                "board_relative_references_must_resolve_to_one_cell": True,
            },
        }


@asynccontextmanager
async def open_jev_command_interpreter() -> AsyncIterator[JevCommandInterpreter]:
    """Own one SDK client while exposing only the domain interpreter seam."""
    async with AsyncTypeSafeClient(
        api_key=os.getenv("TYPESAFE_API_KEY"),
        model=os.getenv("TYPESAFE_DEFAULT_MODEL", "jev-1.13.0"),
    ) as client:
        yield JevCommandInterpreter(client)
