import base64
import json

from server.contracts import CELL_NAMES

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aZfoAAAAASUVORK5CYII=')


def observation(**marks):
    return {'cells': {name: {'value': marks.get(name, 'empty'), 'confidence': 1} for name in CELL_NAMES}}


def game_after(*positions):
    cells = {name: {'value': 'empty', 'playedBy': None, 'step': None} for name in CELL_NAMES}
    for step, position in enumerate(positions, 1):
        cells[CELL_NAMES[position]] = {
            'value': 'O' if step % 2 else 'X',
            'playedBy': 'opponent' if step % 2 else 'self', 'step': step,
        }
    return {'cells': cells, 'phase': 'self', 'step': len(positions), 'pendingDecision': None, 'result': None}


def headers(move=False, state=None):
    if state is None:
        state = game_after(0) if move else observation()
    return {'content-type': 'image/png', 'x-game-state' if move else 'x-board-state': json.dumps(state)}


def completed(value):
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': json.dumps(value)},
    ]}]}
