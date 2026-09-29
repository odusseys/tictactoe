import copy
import unittest

from server.contracts import is_valid_board_observation, is_valid_ai_turn
from api_fixtures import game_after, observation


class ContractTests(unittest.TestCase):
    def test_legal_histories_and_terminal_states(self):
        for positions in ((0,), (0, 4, 8), (0, 3, 2, 4, 6)):
            self.assertTrue(is_valid_ai_turn(game_after(*positions)))
        for positions in ((), (0, 4), (0, 3, 1, 4, 2), (0, 3, 2, 4, 6, 5, 8), (0, 1, 2, 4, 3, 5, 7, 6, 8)):
            self.assertFalse(is_valid_ai_turn(game_after(*positions)))

    def test_bad_ownership_steps_and_shapes(self):
        valid = game_after(0, 4, 8)
        for cell, key, value in (('top_left', 'playedBy', 'self'), ('bottom_right', 'step', 1),
                                 ('top_left', 'step', True), ('top_middle', 'step', 2),
                                 ('top_left', 'value', 'unknown')):
            game = copy.deepcopy(valid)
            game['cells'][cell][key] = value
            self.assertFalse(is_valid_ai_turn(game))
        for field, value in (('phase', 'opponent'), ('pendingDecision', {}), ('result', {}), ('cells', []), ('step', True)):
            game = {**valid, field: value}
            self.assertFalse(is_valid_ai_turn(game))
        for game in (None, [], {}, {'cells': None}):
            self.assertFalse(is_valid_ai_turn(game))

    def test_observation_confidence_and_exact_shape(self):
        seen = observation(top_left='unknown')
        self.assertTrue(is_valid_board_observation(seen))
        for confidence in (False, float('nan'), float('inf'), -0.1, 1.1, '1', None):
            seen['cells']['top_left']['confidence'] = confidence
            self.assertFalse(is_valid_board_observation(seen))
        for malformed in (None, [], {}, {'cells': []}, {**observation(), 'extra': True}):
            self.assertFalse(is_valid_board_observation(malformed))
