import { CELL_NAMES, hasValidCellObservations } from './board-state.js';
import { GameError } from './errors.js';

const MIN_CELL_CONFIDENCE = 0.8;

const WINNING_LINES = [
  [0, 1, 2], [3, 4, 5], [6, 7, 8],
  [0, 3, 6], [1, 4, 7], [2, 5, 8],
  [0, 4, 8], [2, 4, 6],
].map((line) => line.map((index) => CELL_NAMES[index]));

export function createEmptyGame() {
  // API roles: opponent = human O; self = AI X. 'waiting self' means the
  // AI has chosen a cell and the human still needs to draw that X on paper.
  return {
    cells: Object.fromEntries(CELL_NAMES.map((name) => [name, { value: 'empty', playedBy: null, step: null }])),
    phase: 'opponent', step: 0, pendingDecision: null, result: null,
  };
}

// Wins take precedence over a full board, including a win on the ninth move.
function evaluateGameResult(cells) {
  const winningLines = WINNING_LINES.filter((line) => cells[line[0]].value !== 'empty'
    && line.every((name) => cells[name].value === cells[line[0]].value));
  if (winningLines.length) {
    return { winner: cells[winningLines[0][0]].value === 'O' ? 'opponent' : 'self', winningLines };
  }
  return CELL_NAMES.every((name) => cells[name].value !== 'empty')
    ? { winner: 'draw', winningLines: [] } : null;
}

function recordObservedMove(game, cell, value) {
  const step = game.step + 1;
  const cells = { ...game.cells, [cell]: { value, playedBy: value === 'O' ? 'opponent' : 'self', step } };
  return { ...game, cells, step, result: evaluateGameResult(cells) };
}

const rejectObservation = (reason) => ({ kind: 'incompatible', reason });

// Return a transition without mutating the accepted game. The session commits
// readable, legal observations immediately; uncertain/rejected ones keep it intact.
export function applyBoardObservation(game, observedCells) {
  if (!hasValidCellObservations(observedCells)) throw new GameError('invalid_observation', 'The board reader returned an unreadable answer.');
  if (CELL_NAMES.some((name) => observedCells[name].value === 'unknown' || observedCells[name].confidence < MIN_CELL_CONFIDENCE)) {
    return { kind: 'uncertain' };
  }
  if (game.result || game.phase === 'self') return rejectObservation('The board changed outside a playing turn.');
  const changedCellNames = CELL_NAMES.filter((name) => observedCells[name].value !== game.cells[name].value);
  if (!changedCellNames.length) return { kind: 'unchanged', game };
  // Old marks at startup are a setup condition, never a failed game.
  if (game.step === 0 && (changedCellNames.length !== 1 || observedCells[changedCellNames[0]].value !== 'O')) {
    return { kind: 'waiting-start', reason: 'Clear old marks. Start with an empty grid or just your first O.' };
  }
  if (changedCellNames.some((name) => game.cells[name].value !== 'empty')) {
    return rejectObservation('An existing mark was erased or changed.');
  }
  if (game.phase === 'opponent') {
    if (changedCellNames.length !== 1 || observedCells[changedCellNames[0]].value !== 'O') {
      return rejectObservation('Expected exactly one new O on your turn.');
    }
    return { kind: 'changed', game: { ...recordObservedMove(game, changedCellNames[0], 'O'), phase: 'self' } };
  }
  const pendingCellName = game.pendingDecision?.cell;
  if (!pendingCellName || !changedCellNames.includes(pendingCellName) || observedCells[pendingCellName].value !== 'X') {
    return rejectObservation('The X must be drawn in the red cell I chose.');
  }
  const additionalCellNames = changedCellNames.filter((name) => name !== pendingCellName);
  if (additionalCellNames.length > 1 || (additionalCellNames.length === 1 && observedCells[additionalCellNames[0]].value !== 'O')) {
    return rejectObservation('Expected my chosen X, optionally followed by your next O.');
  }
  let updatedGame = { ...recordObservedMove(game, pendingCellName, 'X'), phase: 'opponent', pendingDecision: null };
  // A snapshot can contain both moves, but nothing may be played after a win.
  if (additionalCellNames.length) {
    if (updatedGame.result) return rejectObservation('An extra O was drawn after the game was already over.');
    updatedGame = { ...recordObservedMove(updatedGame, additionalCellNames[0], 'O'), phase: 'self' };
  }
  return { kind: 'changed', game: updatedGame };
}

export function setPendingAiMove(game, cell) {
  if (game.phase !== 'self' || game.result || !CELL_NAMES.includes(cell) || game.cells[cell].value !== 'empty') {
    throw new GameError('invalid_move', 'The AI returned an invalid move. No move has been applied.');
  }
  // Record only the instruction. The move enters history once X is seen on paper.
  return { ...game, phase: 'waiting self', pendingDecision: { cell } };
}
