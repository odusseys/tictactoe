"""API schemas and stateless validation of observations and move history."""

CELL_NAMES = [f'{row}_{col}' for row in ('top', 'middle', 'bottom')
              for col in ('left', 'middle', 'right')]
CELL_VALUES = ['X', 'O', 'empty', 'unknown']
WINNING_LINES = ((0, 1, 2), (3, 4, 5), (6, 7, 8), (0, 3, 6),
                 (1, 4, 7), (2, 5, 8), (0, 4, 8), (2, 4, 6))

BOARD_OBSERVATION_SCHEMA = {
    'type': 'object', 'additionalProperties': False,
    'properties': {'cells': {
        'type': 'object', 'additionalProperties': False,
        'properties': {cell_name: {'$ref': '#/$defs/cell'} for cell_name in CELL_NAMES},
        'required': CELL_NAMES,
    }},
    'required': ['cells'],
    '$defs': {'cell': {
        'type': 'object', 'additionalProperties': False,
        'properties': {
            'value': {
                'type': 'string', 'enum': CELL_VALUES,
                'description': 'X or O for a visually identifiable mark, empty for a visibly blank cell, unknown when the cell cannot be determined from the image.',
            },
            'confidence': {
                'type': 'number', 'minimum': 0, 'maximum': 1,
                'description': 'Estimated probability that the selected label is correct, based only on the image.',
            },
        },
        'required': ['value', 'confidence'],
    }},
}


def has_exact_keys(value, keys):
    return isinstance(value, dict) and value.keys() == set(keys)


def is_valid_board_observation(value):
    """Check the response shape; unknown or low-confidence labels are valid data.

    The frontend separately decides whether an observation can advance the game.
    """
    if not has_exact_keys(value, ['cells']) or not has_exact_keys(value['cells'], CELL_NAMES):
        return False
    for cell in value['cells'].values():
        if not has_exact_keys(cell, ['value', 'confidence']) or cell['value'] not in CELL_VALUES:
            return False
        if type(cell['confidence']) not in (int, float) or not 0 <= cell['confidence'] <= 1:
            return False
    return True


def has_winner(replayed_board):
    return any(replayed_board[first] != 'empty' and replayed_board[first] == replayed_board[second] == replayed_board[third]
               for first, second, third in WINNING_LINES)


def is_valid_ai_turn(game):
    """Return whether this is a legal, unfinished game awaiting an AI X choice.

    Replay the numbered moves because a plausible board alone cannot prove that
    turns alternated or that play stopped at the first win. This validates the
    supplied history, not the image or the observation's confidence.
    """
    if not isinstance(game, dict) or game.get('phase') != 'self':
        return False
    if game.get('pendingDecision', False) is not None or game.get('result', False) is not None:
        return False
    if not has_exact_keys(game.get('cells'), CELL_NAMES) or type(game.get('step')) is not int:
        return False
    recorded_moves = []
    for cell_index, cell_name in enumerate(CELL_NAMES):
        cell = game['cells'][cell_name]
        if not has_exact_keys(cell, ['value', 'playedBy', 'step']):
            return False
        if cell['value'] == 'empty':
            if cell['playedBy'] is not None or cell['step'] is not None:
                return False
        else:
            if cell['value'] not in ('X', 'O') or type(cell['step']) is not int:
                return False
            if cell['playedBy'] != ('opponent' if cell['value'] == 'O' else 'self'):
                return False
            recorded_moves.append((cell['step'], cell_index, cell['value']))
    # O starts, so an odd number of accepted moves must precede an X choice.
    if game['step'] != len(recorded_moves) or len(recorded_moves) % 2 != 1:
        return False
    replayed_board = ['empty'] * 9
    for expected_move_number, (step, cell_index, value) in enumerate(sorted(recorded_moves), 1):
        if has_winner(replayed_board) or step != expected_move_number or value != ('O' if expected_move_number % 2 else 'X'):
            return False
        replayed_board[cell_index] = value
    return not has_winner(replayed_board) and 'empty' in replayed_board
