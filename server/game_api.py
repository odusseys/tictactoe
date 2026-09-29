"""Stateless detection and move requests using the existing browser contract."""
import json

from starlette.exceptions import HTTPException

from .contracts import BOARD_OBSERVATION_SCHEMA, CELL_NAMES, has_exact_keys, is_valid_board_observation, is_valid_ai_turn
from .openai import ASTRA_MODEL, AstraClient
from .errors import GameServiceError
from .prompts import BOARD_OBSERVATION_PROMPT, MOVE_SELECTION_PROMPT


def parse_request_game_state(headers, is_move_request: bool):
    """Validate browser state and forward only fields used by the selected prompt."""
    header_name = 'x-game-state' if is_move_request else 'x-board-state'
    try:
        game_state = json.loads(headers.get(header_name, ''))
    except (ValueError, RecursionError):
        game_state = None
    if is_move_request:
        if not is_valid_ai_turn(game_state):
            raise HTTPException(400, 'Expected a legal, unfinished game where X plays next.')
        return {key: game_state[key] for key in ('cells', 'phase', 'step', 'pendingDecision', 'result')}
    cells = game_state.get('cells') if isinstance(game_state, dict) else None
    if not has_exact_keys(cells, CELL_NAMES) or not all(
        isinstance(cell, dict) and cell.get('value') in ('X', 'O', 'empty') for cell in cells.values()
    ):
        raise HTTPException(400, 'Send the last confirmed board in X-Board-State. Reload the app to start a new game.')
    return {'cells': {cell_name: {'value': cells[cell_name]['value']} for cell_name in CELL_NAMES}}


async def detect_board_state(astra_client: AstraClient, image_data_url: str, accepted_board: dict):
    observation = await astra_client.generate_structured_output(
        reasoning_effort='low', schema_name='tic_tac_toe_observation', output_schema=BOARD_OBSERVATION_SCHEMA,
        message_content=[
            {'type': 'input_text', 'text': BOARD_OBSERVATION_PROMPT},
            {'type': 'input_text', 'text': f'the state of the board detected so far is {json.dumps(accepted_board, separators=(",", ":"))} ; it may have changed or not'},
            {'type': 'input_image', 'image_url': image_data_url, 'detail': 'high'},
        ],
    )
    if not is_valid_board_observation(observation):
        raise GameServiceError(502, 'invalid_observation', 'The board reader returned an unreadable answer.')
    return {**observation, 'model': ASTRA_MODEL, 'reasoningEffort': 'low'}


async def select_ai_move(astra_client: AstraClient, image_data_url: str, game: dict):
    empty_cells = [cell_name for cell_name in CELL_NAMES if game['cells'][cell_name]['value'] == 'empty']
    decision = await astra_client.generate_structured_output(
        reasoning_effort='medium', schema_name='tic_tac_toe_move',
        output_schema={
            'type': 'object', 'additionalProperties': False,
            'properties': {'cell': {'type': 'string', 'enum': empty_cells}}, 'required': ['cell'],
        },
        message_content=[
            {'type': 'input_text', 'text': MOVE_SELECTION_PROMPT},
            {'type': 'input_text', 'text': json.dumps(game, separators=(',', ':'))},
            {'type': 'input_image', 'image_url': image_data_url, 'detail': 'high'},
        ],
    )
    if not has_exact_keys(decision, ['cell']) or decision['cell'] not in empty_cells:
        raise GameServiceError(502, 'invalid_move', 'The AI returned an invalid move. No move has been applied.')
    return decision
