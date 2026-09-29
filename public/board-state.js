export const CELL_NAMES = [
  'top_left', 'top_middle', 'top_right',
  'middle_left', 'middle_middle', 'middle_right',
  'bottom_left', 'bottom_middle', 'bottom_right',
];

const CELL_VALUES = ['X', 'O', 'empty', 'unknown'];

function hasExactKeys(value, keys) {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
    && Object.keys(value).length === keys.length
    && keys.every((key) => Object.hasOwn(value, key));
}

export function hasValidCellObservations(cells) {
  // Validate the response shape here; game rules handle confidence and unknowns.
  return hasExactKeys(cells, CELL_NAMES) && CELL_NAMES.every((name) => {
    const cell = cells[name];
    return hasExactKeys(cell, ['value', 'confidence']) && CELL_VALUES.includes(cell.value)
      && Number.isFinite(cell.confidence) && cell.confidence >= 0 && cell.confidence <= 1;
  });
}
