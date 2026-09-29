import { CELL_NAMES } from './board-state.js';

// Reversing row-major cell order rotates the display 180 degrees to face the
// human. Stored cell names and model inputs stay in camera coordinates.
const DISPLAY_CELL_ORDER = [...CELL_NAMES].reverse();

export function getDisplayedCellPosition(cell) {
  const displayIndex = DISPLAY_CELL_ORDER.indexOf(cell);
  return CELL_NAMES[displayIndex]?.replace('middle_middle', 'center').replaceAll('middle', 'center').replaceAll('_', ' ');
}

export function renderBoard(container, game, showPending) {
  const table = document.createElement('table');
  table.className = 'board-grid';
  table.setAttribute('aria-label', 'Confirmed board, rotated to face you');
  const tableBody = table.createTBody();
  const winningCellNames = new Set(game.result?.winningLines.flat() ?? []);
  for (let row = 0; row < 3; row += 1) {
    const rowElement = tableBody.insertRow();
    for (const cellName of DISPLAY_CELL_ORDER.slice(row * 3, row * 3 + 3)) {
      const { value, playedBy, step } = game.cells[cellName];
      const isPendingMove = showPending && game.pendingDecision?.cell === cellName;
      const cellElement = rowElement.insertCell();
      cellElement.className = `board-cell is-${value.toLowerCase()}`;
      cellElement.classList.toggle('is-pending', isPendingMove);
      cellElement.classList.toggle('is-winning', winningCellNames.has(cellName));
      Object.assign(cellElement.dataset, { cell: cellName, value, playedBy: playedBy ?? '', step: step ?? '' });
      const cellDescription = isPendingMove ? 'draw my X here' : value === 'empty' ? 'empty' : `${value}, move ${step}, ${playedBy === 'opponent' ? 'you' : 'me'}`;
      cellElement.setAttribute('aria-label', `${getDisplayedCellPosition(cellName)}: ${cellDescription}`);
      const markElement = document.createElement('span');
      markElement.className = 'cell-mark';
      markElement.textContent = isPendingMove ? 'X' : value === 'empty' ? '·' : value;
      const instructionElement = document.createElement('span');
      instructionElement.className = 'cell-hint';
      instructionElement.textContent = isPendingMove ? 'DRAW HERE' : '';
      cellElement.append(markElement, instructionElement);
    }
  }
  container.replaceChildren(table);
}
