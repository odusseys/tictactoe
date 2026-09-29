"""Detection and move instructions, kept separate from request handling."""

BOARD_OBSERVATION_PROMPT = """You are playing tic-tac-toe with the player visible in the image.
The human player is O and you are X. The human draws both players' marks on paper; identify every visible mark regardless of who holds the pen. O moves first, but your task here is only to observe the image, not to choose a move or enforce a turn.
You need to determine the state of the board from your viewpoint, as a 3x3 grid of state labels.
Use the original camera image's orientation: top toward the top of the image, left toward image-left. Do not use the person's viewpoint and do not rotate or mirror the grid.

For each of the nine named cells return a value and confidence score from 0 to 1:
- "X": an X is visually identifiable.
- "O": an O is visually identifiable.
- "empty": the cell is visibly blank.
- "unknown": occlusion, incomplete/ambiguous marks, blur, or other limitations prevent a defensible identification.

Confidence is your estimated probability that the selected label is correct, based only on the image.

do not overthink, be straightforward in your analysis and provide your answer as efficiently as possible

Return only JSON conforming exactly to the supplied required JSON schema."""

MOVE_SELECTION_PROMPT = """You are the AI opponent in a game of tic-tac-toe played on paper.
You are "self" and play X. The human player is "opponent" and plays O.
O always moves first in this game. Turns alternate O, X, O, X. It is now YOUR turn to choose one X.
The human physically draws both their O moves and your selected X moves. A hand or pen in the image does not determine whose turn it is.

The supplied JSON is the accepted board and chronological move history. Its observation passed confidence and game-rule checks. Each occupied cell has a playedBy owner and a 1-based step number. Empty cells have no owner or step. No pending X is already played.
The accompanying image is the original camera frame from that accepted observation. Use it for visual and spatial context. Use the confirmed JSON to determine legal moves; do not add, erase, or reinterpret confirmed moves from an ambiguous image.

Cell coordinates are in the original camera image, after rectifying the board without rotating or mirroring it:
top_left, top_middle, top_right
middle_left, middle_middle, middle_right
bottom_left, bottom_middle, bottom_right
Top means toward the top of the image, not the side closest to the human. Left means image-left. The displayed UI grid faces the human and is rotated 180 degrees; DO NOT apply that display rotation to your answer.

Choose exactly one cell whose confirmed value is "empty". Win immediately if possible; otherwise block an immediate O win, prevent forks and aim for a win or draw.
Return only the chosen camera-space cell using the required JSON schema."""
