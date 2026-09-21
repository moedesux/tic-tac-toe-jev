"""Credential-gated Jev calibration run for the curated command corpus.

The command is intentionally separate from CI. It emits aggregate, JSON-safe
results only; utterances and SDK responses are never written to artifacts.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import argparse
from collections import Counter
from pathlib import Path

# Support direct invocation from the repository root (`python scripts/...`).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.jev_command_interpreter import JevCommandInterpreter
from backend.game_session import GameSession, NoGameError
from backend.models import GameResponse, MovePosition, PendingCommand
from backend.player_command import PlayerCommandProcessor
from test.fakes import load_command_fixtures
from typesafe_sdk import AsyncTypeSafeClient


def fixture_state(fixture: dict):
    setup = fixture.get("setup", {})
    moves = setup.get("moves", [])
    board = [None] * 9
    for index, move in enumerate(moves):
        board[move] = "X" if index % 2 == 0 else "O"
    needs_game = bool(moves) or fixture["category"] in {
        "position", "board_relative", "ambiguous"
    }
    game_state = GameResponse(
        gameId="fixture", board=board, turn="X" if len(moves) % 2 == 0 else "O",
        winner=None, status="ongoing", gameOver=False,
    ) if setup.get("game", needs_game) else None
    pending_data = setup.get("pending")
    pending = PendingCommand(**pending_data) if pending_data else None
    return game_state, pending


async def session_snapshot(session: GameSession) -> tuple[object, PendingCommand | None]:
    """Capture authoritative state without exposing provider-shaped data."""
    try:
        game = await session.read()
    except NoGameError:
        game = None
    async with session.locked():
        pending = session.pending
    return game, pending


async def evaluate() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    api_key = os.getenv("TYPESAFE_API_KEY")
    if not api_key:
        print("SKIP: TYPESAFE_API_KEY is not configured")
        return 0

    model = os.getenv("TYPESAFE_DEFAULT_MODEL")
    fixtures = load_command_fixtures()
    counts: Counter[str] = Counter()
    confidences: dict[str, list[float]] = {}
    gate_map = {
        "social": "read_only_social",
        "read_only": "read_only_social",
        "position": "position_selection",
        "board_relative": "position_selection",
        "insufficient_confidence_reset": "existing_game_reset",
        "existing_game_reset": "existing_game_reset",
    }
    safety_failures = 0
    canonical_failures = 0
    behavior_failures: set[str] = set()
    records: list[dict] = []
    async with AsyncTypeSafeClient(api_key=api_key, model=model) as client:
        interpreter = JevCommandInterpreter(client)
        observed_models: set[str] = set()
        for fixture in fixtures:
            game_state, pending = fixture_state(fixture)
            interpretation = await interpreter.interpret(fixture["control"], game_state, pending)
            if interpreter.last_model:
                observed_models.add(interpreter.last_model)
            category = fixture["category"]
            expected = fixture["intent"]
            counts[f"{category}.total"] += 1
            counts[f"{category}.intent_match"] += interpretation.intent.value == expected
            canonical = category in {"social", "read_only", "position", "board_relative", "start"}
            intent_match = interpretation.intent.value == expected
            position_match = not fixture.get("position") or (
                interpretation.position is not None
                and interpretation.position.value == fixture["position"]
            )
            canonical_failures += int(canonical and (not intent_match or not position_match))
            gate = gate_map.get(category, "move")
            counts[f"{gate}.total"] += 1
            counts[f"{gate}.intent_match"] += interpretation.intent.value == expected
            if fixture.get("position"):
                counts[f"{gate}.position_match"] += (
                    interpretation.position is not None
                    and interpretation.position.value == fixture["position"]
                )
            if fixture.get("position"):
                counts[f"{category}.position_match"] += (
                    interpretation.position is not None
                    and interpretation.position.value == fixture["position"]
                )
            safety_categories = {
                "ambiguous",
                "irrelevant",
                "insufficient_confidence_move",
                "insufficient_confidence_position",
                "insufficient_confidence_reset",
            }
            mutated = False
            if fixture:
                session = GameSession()
                setup = fixture.get("setup", {})
                if setup.get("game", bool(setup.get("moves")) or category in {
                    "position", "board_relative", "ambiguous"
                }):
                    await session.create()
                    for move in setup.get("moves", []):
                        await session.move(move)
                if setup.get("pending"):
                    pending_setup = setup["pending"]
                    async with session.locked():
                        session.set_pending(
                            PendingCommand(
                                intent=pending_setup["intent"],
                                position=(
                                    MovePosition(pending_setup["position"])
                                    if pending_setup.get("position")
                                    else None
                                ),
                            )
                        )
                before = await session_snapshot(session)

                class ObservedInterpreter:
                    async def interpret(self, *_args, **_kwargs):
                        return interpretation

                result = await PlayerCommandProcessor(ObservedInterpreter(), session).process(
                    fixture["control"]
                )
                # Pending creation/replacement is clarification state, not game execution.
                after = await session_snapshot(session)
                mutated = before[0] != after[0]
                if category in safety_categories and mutated:
                    safety_failures += 1
                expected_result = fixture.get("expected", {})
                expected_result_intent = expected_result.get("intent")
                if expected_result_intent is not None and result.intent.value != expected_result_intent:
                    behavior_failures.add(fixture["id"])
                elif expected_result_intent is None and category not in safety_categories and result.intent.value != fixture["intent"]:
                    behavior_failures.add(fixture["id"])
                if "position" in fixture:
                    actual_result_position = (
                        result.position.value if result.position else None
                    )
                    if actual_result_position != fixture["position"]:
                        behavior_failures.add(fixture["id"])
                if category in {
                    "position",
                    "board_relative",
                    "start",
                    "start_plus_move",
                    "start_plus_move_missing",
                    "start_plus_move_uncertain",
                    "existing_game_reset",
                } and not mutated:
                    behavior_failures.add(fixture["id"])
                if "intent" in expected_result and result.intent.value != expected_result["intent"]:
                    behavior_failures.add(fixture["id"])
                if "position" in expected_result:
                    actual_position = result.position.value if result.position else None
                    if actual_position != expected_result["position"]:
                        behavior_failures.add(fixture["id"])
                if "clarification_required" in expected_result and result.clarification_required != expected_result["clarification_required"]:
                    behavior_failures.add(fixture["id"])
                if any(key in expected_result for key in ("board", "turn")):
                    actual_game = (await session_snapshot(session))[0]
                    if actual_game is None or (
                        "board" in expected_result and actual_game.board != expected_result["board"]
                    ) or (
                        "turn" in expected_result and actual_game.turn != expected_result["turn"]
                    ):
                        behavior_failures.add(fixture["id"])
                if "pending" in expected_result:
                    actual_pending = (await session_snapshot(session))[1]
                    expected_pending = expected_result["pending"]
                    if (actual_pending is None) != (expected_pending is None):
                        behavior_failures.add(fixture["id"])
                    elif actual_pending is not None:
                        if actual_pending.intent.value != expected_pending["intent"] or (
                            actual_pending.position.value if actual_pending.position else None
                        ) != expected_pending.get("position"):
                            behavior_failures.add(fixture["id"])
            confidences.setdefault(gate, []).append(interpretation.confidence)
            if fixture.get("position"):
                confidences.setdefault("position_selection", []).append(interpretation.position_confidence)
            records.append({
                "id": fixture["id"],
                "category": category,
                "judgment": {
                    "intent": interpretation.intent.value,
                    "confidence": interpretation.confidence,
                    "position": interpretation.position.value if interpretation.position else None,
                    "position_confidence": interpretation.position_confidence,
                    "position_present_confidence": interpretation.position_present_confidence,
                    "position_unique_confidence": interpretation.position_unique_confidence,
                    "initial_move_requested": interpretation.initial_move_requested,
                    "initial_move_confidence": interpretation.initial_move_confidence,
                    "state_change_confidence": interpretation.state_change_confidence,
                    "cancel_confidence": interpretation.cancel_confidence,
                    "affirm_confidence": interpretation.affirm_confidence,
                    "reject_confidence": interpretation.reject_confidence,
                },
                "expected_intent_match": intent_match,
                "expected_position_match": position_match,
                "mutated": mutated,
            })

        if not observed_models:
            print("ERROR: Jev did not return an exact response.model")
            return 1
        if len(observed_models) != 1:
            print("ERROR: Jev returned inconsistent model versions")
            return 1
        observed_model = observed_models.pop()

        result = {
            "model": observed_model,
            "fixtures": len(fixtures),
            "safety_failures": safety_failures,
            "canonical_failures": canonical_failures,
            "behavior_failures": sorted(behavior_failures),
            "judgments": dict(counts),
            "confidence": {
                key: {"min": min(values), "max": max(values), "mean": sum(values) / len(values)}
                for key, values in confidences.items()
            },
            "records": records,
        }
        rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
    return 1 if safety_failures or canonical_failures or behavior_failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(evaluate()))
