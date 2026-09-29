import { getDisplayedCellPosition, renderBoard } from './board.js';

const getElement = (id) => document.getElementById(id);
function setText(id, value) {
  // Preserve live-region text when only the background request changes.
  if (getElement(id).textContent !== value) getElement(id).textContent = value;
}

function getTurnMessage({ status, game, issue, cameraOpening, operation }) {
  if (issue) {
    const recovery = issue.retrySeconds ? ` Retrying in ${issue.retrySeconds}s…`
      : status === 'running' ? ' Checking again…' : status === 'paused' ? ' Your game is saved. Retry when ready.' : '';
    return [issue.title, `${issue.message}${recovery}`];
  }
  if (cameraOpening) return ['Opening your camera…', 'Allow camera access to see your board.'];
  if (status === 'idle') return ['You go first.', 'You’re O. I’m X. You’ll draw both our moves on paper.'];
  if (status === 'finished') {
    return [{ opponent: 'You won!', self: 'I won!', draw: 'It’s a draw.' }[game.result.winner], 'Clear your board to play again.'];
  }
  if (operation === 'cropping') return ['Looking for the paper…', 'Keep the sheet well lit and in view.'];
  if (game.phase === 'self') return ['Choosing my X…', 'Keep the board as it is while I choose.'];
  if (game.phase === 'waiting self') {
    return ['Draw my X.', `Draw X in the ${getDisplayedCellPosition(game.pendingDecision.cell)} red cell, then move your hand away.`];
  }
  return ['Your turn.', 'Draw one O, then move your hand away so I can read the board.'];
}

export function renderGameSession(session) {
  const { status, game, issue, cameraReady, cameraOpening, operation } = session;
  const hasGame = status === 'running' || status === 'paused';
  const [title, detail] = getTurnMessage(session);
  getElement('crop-paper').checked = Boolean(session.cropPaper);
  getElement('game-workspace').dataset.status = status;
  getElement('game-workspace').dataset.phase = game.phase;
  getElement('turn-status').dataset.warning = Boolean(issue);
  getElement('warning-icon').toggleAttribute('hidden', !issue);
  setText('turn-title-text', title);
  setText('turn-detail', detail);
  getElement('retry-game').hidden = status !== 'paused';
  getElement('retry-game').disabled = cameraOpening;
  getElement('camera-video').hidden = !cameraReady;
  getElement('camera-guide').hidden = hasGame || status === 'finished';
  getElement('start-game').hidden = hasGame;
  getElement('start-game').disabled = !cameraReady || cameraOpening;
  setText('start-game', status === 'finished' ? 'Play again' : 'Start game');
  getElement('end-game').hidden = !hasGame;
  getElement('retry-camera').hidden = hasGame || cameraReady || cameraOpening || !issue;
  setText('camera-status', cameraOpening ? 'Connecting camera…' : cameraReady ? 'Live camera' : issue ? 'Camera unavailable' : 'Camera off');
  getElement('camera-label').dataset.live = Boolean(cameraReady);
  getElement('thinking-indicator').hidden = Boolean(issue) || !['deciding', 'cropping'].includes(operation);
  renderBoard(getElement('game-board'), game, hasGame);
}
