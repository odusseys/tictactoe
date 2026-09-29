import test from 'node:test';
import assert from 'node:assert/strict';
import { CELL_NAMES } from '../public/board-state.js';
import { createEmptyGame, applyBoardObservation, setPendingAiMove } from '../public/game-state.js';

function observation(game, changes = {}) {
  return Object.fromEntries(CELL_NAMES.map((name) => [name, {
    value: changes[name] ?? game.cells[name].value, confidence: 1,
  }]));
}

function play(indices) {
  let game = createEmptyGame();
  for (const index of indices) {
    const cell = CELL_NAMES[index];
    if (game.phase === 'self') game = setPendingAiMove(game, cell);
    const value = game.phase === 'opponent' ? 'O' : 'X';
    const change = applyBoardObservation(game, observation(game, { [cell]: value }));
    assert.equal(change.kind, 'changed');
    game = change.game;
  }
  return game;
}

test('confirmed moves retain owners and chronological steps; a choice remains empty', () => {
  const first = play([0]);
  const pending = setPendingAiMove(first, 'middle_middle');
  assert.equal(pending.phase, 'waiting self');
  assert.equal(pending.step, 1);
  assert.deepEqual(pending.cells.middle_middle, { value: 'empty', playedBy: null, step: null });
  assert.deepEqual(first.cells.top_left, { value: 'O', playedBy: 'opponent', step: 1 });
  const next = applyBoardObservation(pending, observation(pending, { middle_middle: 'X' })).game;
  assert.equal(next.phase, 'opponent');
  assert.equal(next.pendingDecision, null);
  assert.deepEqual(next.cells.middle_middle, { value: 'X', playedBy: 'self', step: 2 });
});

test('one snapshot may confirm the requested X then the next O', () => {
  const game = setPendingAiMove(play([0]), 'middle_middle');
  const result = applyBoardObservation(game, observation(game, { middle_middle: 'X', bottom_right: 'O' }));
  assert.equal(result.kind, 'changed');
  assert.equal(result.game.phase, 'self');
  assert.equal(result.game.cells.middle_middle.step, 2);
  assert.equal(result.game.cells.bottom_right.step, 3);
});

test('unknown and low-confidence cells do not advance; exactly 0.8 is accepted', () => {
  const game = createEmptyGame();
  const seen = observation(game, { top_left: 'O' });
  seen.bottom_right.confidence = 0.799;
  assert.equal(applyBoardObservation(game, seen).kind, 'uncertain');
  seen.bottom_right.confidence = 0.8;
  assert.equal(applyBoardObservation(game, seen).kind, 'changed');
  seen.bottom_right.value = 'unknown';
  seen.bottom_right.confidence = 1;
  assert.equal(applyBoardObservation(game, seen).kind, 'uncertain');
  assert.equal(game.step, 0);
});

test('unchanged frames are valid; erased marks and wrong choices leave state untouched', () => {
  const game = setPendingAiMove(play([0]), 'middle_middle');
  const before = JSON.stringify(game);
  assert.equal(applyBoardObservation(game, observation(game)).kind, 'unchanged');
  for (const changes of [{ top_left: 'empty' }, { top_left: 'X' }, { top_right: 'X' }, { middle_middle: 'O' }]) {
    assert.equal(applyBoardObservation(game, observation(game, changes)).kind, 'incompatible');
  }
  assert.equal(JSON.stringify(game), before);
  assert.throws(() => setPendingAiMove(play([0]), 'top_left'));
});

test('a new game waits for an empty board or exactly one O', () => {
  const game = createEmptyGame();
  assert.equal(applyBoardObservation(game, observation(game, { top_left: 'X' })).kind, 'waiting-start');
  assert.equal(applyBoardObservation(game, observation(game, { top_left: 'O', top_right: 'O' })).kind, 'waiting-start');
  assert.equal(applyBoardObservation(game, observation(game)).kind, 'unchanged');
  assert.equal(applyBoardObservation(game, observation(game, { top_left: 'O' })).kind, 'changed');
});

test('local rules find either winner and a draw; a ninth-move win is not a draw', () => {
  assert.equal(play([0, 3, 1, 4, 2]).result.winner, 'opponent');
  assert.equal(play([0, 3, 2, 4, 6, 5]).result.winner, 'self');
  assert.equal(play([0, 1, 2, 4, 3, 5, 7, 6, 8]).result.winner, 'draw');
  assert.equal(play([0, 1, 4, 2, 3, 5, 7, 6, 8]).result.winner, 'opponent');
});

test('catch-up cannot add an O after a winning X', () => {
  const game = setPendingAiMove(play([0, 3, 2, 4, 6]), 'middle_right');
  const change = applyBoardObservation(game, observation(game, { middle_right: 'X', bottom_middle: 'O' }));
  assert.equal(change.kind, 'incompatible');
  assert.equal(game.step, 5);
});
