const ERROR_TITLES = {
  network: 'Connection interrupted', upstream_connection: 'AI connection interrupted',
  timeout: 'The AI is taking too long', busy: 'The server is busy', rate_limited: 'The AI is busy',
  invalid_response: 'The AI answer was unreadable', invalid_observation: 'The board could not be read',
  invalid_move: 'Trying another move', incomplete_response: 'The AI answer was incomplete',
  refused_response: 'The AI could not read this image', invalid_image: 'The image could not be read',
  api_key_missing: 'API key needed', api_key_rejected: 'API key rejected',
  model_unavailable: 'AI access needs attention', quota_exhausted: 'API quota exhausted',
  service_configuration: 'AI configuration needs attention', service_unavailable: 'The AI is unavailable',
  invalid_request: 'The request needs attention', access_denied: 'Access was denied',
  not_found: 'The game service was not found', image_too_large: 'The camera image is too large',
  unsupported_image: 'This image format is unsupported', internal_error: 'The server needs attention',
  camera_permission: 'Allow camera access', camera_missing: 'Connect a camera',
  camera_busy: 'The camera is unavailable', camera_blocked: 'Camera access is blocked',
  camera_frame: 'Waiting for the camera', camera_disconnected: 'Camera disconnected',
  no_paper: 'No paper detected', cropping_busy: 'Paper cropping is busy', cropping_unavailable: 'Paper cropping unavailable',
};

export class GameError extends Error {
  constructor(code, message, { retryable = true, retryAfterMs = 0 } = {}) {
    super(message);
    this.name = 'GameError';
    Object.assign(this, { code, retryable, retryAfterMs });
  }
}

export function describeError(error) {
  return {
    code: error.code || 'unexpected',
    title: ERROR_TITLES[error.code] || 'Something needs attention',
    message: error instanceof GameError ? error.message : 'An unexpected error occurred. Your game is saved; try again.',
  };
}
