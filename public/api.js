import { CELL_NAMES, hasValidCellObservations } from './board-state.js';
import { GameError } from './errors.js';

function retryDelay(response) {
  const value = response.headers.get('Retry-After');
  if (!value) return 0;
  const seconds = Number(value);
  const delay = Number.isFinite(seconds) ? seconds * 1000 : Date.parse(value) - Date.now();
  return Number.isFinite(delay) ? Math.max(0, delay) : 0;
}

async function postImage(endpoint, body, signal, headers, binary = false) {
  // The server's complete request budget is 75s; leave time for its error response.
  const requestSignal = AbortSignal.any([signal, AbortSignal.timeout(85_000)]);
  try {
    const response = await fetch(endpoint, {
      method: 'POST', headers: { 'Content-Type': body.type, ...headers }, body, signal: requestSignal,
    });
    if (response.ok && binary) {
      const image = await response.blob();
      if (image.type !== 'image/jpeg' || !image.size) {
        throw new GameError('invalid_response', 'The server returned an unreadable paper crop.');
      }
      return image;
    }
    const text = await response.text();
    let data;
    try { data = JSON.parse(text); } catch { /* HTTP status still explains non-JSON error pages. */ }
    if (!response.ok) {
      const fallbackCode = { 400: 'invalid_request', 401: 'access_denied', 403: 'access_denied',
        404: 'not_found', 413: 'image_too_large', 415: 'unsupported_image', 429: 'busy', 504: 'timeout' }[response.status];
      const error = new GameError(typeof data?.code === 'string' ? data.code : fallbackCode || 'service_unavailable',
        typeof data?.error === 'string' ? data.error : `The server returned an error (${response.status}).`, {
          retryable: typeof data?.retryable === 'boolean' ? data.retryable : response.status === 429 || response.status >= 500,
          retryAfterMs: retryDelay(response),
        });
      error.status = response.status;
      throw error;
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      throw new GameError('invalid_response', 'The server returned an unreadable answer.');
    }
    return data;
  } catch (error) {
    signal.throwIfAborted();
    if (error instanceof GameError) throw error;
    if (requestSignal.aborted) throw new GameError('timeout', 'The request took too long. Your game is saved.');
    throw new GameError('network', 'Check your connection. Your game is saved.');
  }
}

export function requestPaperCrop(image, signal) {
  return postImage('/api/crop', image, signal, {}, true);
}

export async function requestBoardObservation(image, game, signal) {
  // Only accepted marks are context; the pending X is still blank on paper.
  const acceptedBoard = {
    cells: Object.fromEntries(CELL_NAMES.map((name) => [name, { value: game.cells[name].value }])),
  };
  const response = await postImage('/api/board', image, signal, { 'X-Board-State': JSON.stringify(acceptedBoard) });
  if (!hasValidCellObservations(response.cells)) throw new GameError('invalid_observation', 'The board reader returned an unreadable answer.');
  return response;
}

export async function requestAiMove(game, image, signal) {
  const response = await postImage('/api/move', image, signal, { 'X-Game-State': JSON.stringify(game) });
  if (!CELL_NAMES.includes(response.cell)) throw new GameError('invalid_move', 'The AI returned an invalid move. No move has been applied.');
  return response;
}
