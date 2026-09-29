"""Errors the browser can explain and either retry or pause for user action."""
from starlette.exceptions import HTTPException


class GameServiceError(HTTPException):
    def __init__(self, status_code, code, message, *, retryable=True, headers=None):
        super().__init__(status_code, message, headers)
        self.code = code
        self.retryable = retryable


def error_payload(error):
    if isinstance(error, GameServiceError):
        return {'error': error.detail, 'code': error.code, 'retryable': error.retryable}
    if isinstance(error, HTTPException):
        code = {400: 'invalid_request', 403: 'access_denied', 404: 'not_found',
                413: 'image_too_large', 415: 'unsupported_image', 429: 'busy',
                499: 'cancelled', 504: 'timeout'}.get(error.status_code, 'service_unavailable')
        return {'error': error.detail, 'code': code, 'retryable': error.status_code in (429, 502, 503, 504)}
    return {'error': 'An unexpected server error occurred. Your game is saved; try again.',
            'code': 'internal_error', 'retryable': False}
