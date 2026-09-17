# Voice-Controlled Tic-Tac-Toe

This context describes how a player expresses and executes commands in a voice-controlled game of tic-tac-toe.

## Language

**Player**:
One of the game's two participants, identified by the mark X or O.
_Avoid_: User, AI opponent

**Player Command**:
A player's request to inspect, start, play, or leave the game, whether expressed in natural language or through a structured control.
_Avoid_: Prompt, tool call, function call

**Command Intent**:
One supported meaning assigned to a natural-language player command: greet, start a game, show the board, place a move, show status, acknowledge thanks, leave, or unclear.
_Avoid_: Tool, function

**Command Interpretation**:
The judgment that maps natural-language input to a command intent and, when applicable, a move position.
_Avoid_: Chat completion, tool calling

**Move Position**:
One of the nine cells on the tic-tac-toe board where a player intends to place a mark.
_Avoid_: Slot, argument

**Pending Command**:
A player command whose intent is known but which cannot execute until the player supplies a missing value or confirms an uncertain interpretation.
_Avoid_: Conversation history, chat context, incomplete tool call

**Natural-Language Control**:
A player command expressed as typed or transcribed language and requiring command interpretation.
_Avoid_: SLM command, voice pipeline command

**Structured Control**:
A button or other interface element whose command intent and values are already known and therefore require no interpretation.
_Avoid_: Prompt, synthetic utterance
