"""HTTP policy and cancellation shared by both game endpoints."""
import asyncio
from urllib.parse import urlsplit

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from .errors import error_payload

SECURITY_HEADERS = {
    'X-Content-Type-Options': 'nosniff',
    'Referrer-Policy': 'no-referrer',
    'Permissions-Policy': 'camera=(self), microphone=()',
    'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
}


def json_response(data, status=200, headers=None):
    return JSONResponse(data, status_code=status, headers={
        **SECURITY_HEADERS, 'Cache-Control': 'no-store', **(headers or {}),
    })


async def handle_http_error(request, error):
    if isinstance(error, HTTPException):
        return json_response(error_payload(error), error.status_code, error.headers)
    return json_response(error_payload(error), 500)


class SecurityHeadersMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        async def send_with_headers(message):
            if message['type'] == 'http.response.start':
                headers = dict(message['headers'])
                headers.update((key.lower().encode(), value.encode()) for key, value in SECURITY_HEADERS.items())
                message = {**message, 'headers': list(headers.items())}
            await send(message)
        await self.app(scope, receive, send_with_headers)


def require_same_origin(request):
    origin = request.headers.get('origin')
    if origin is None:
        return
    try:
        origin_url = urlsplit(origin)
        is_same_origin = origin_url.scheme in ('http', 'https') and origin_url.netloc == request.headers.get('host')
    except ValueError:
        is_same_origin = False
    if not is_same_origin:
        raise HTTPException(403, 'Send requests from this app’s own page.')


async def cancel_on_disconnect(request, upstream_call):
    """Run an API call until it finishes or the browser disconnects.

    Call only after reading the upload: the disconnect listener consumes the
    same receive channel as the request body.
    """
    async def wait_for_disconnect():
        while (await request.receive())['type'] != 'http.disconnect':
            pass

    upstream_task = asyncio.create_task(upstream_call)
    disconnect_task = asyncio.create_task(wait_for_disconnect())
    try:
        completed_tasks, _ = await asyncio.wait((upstream_task, disconnect_task), return_when=asyncio.FIRST_COMPLETED)
        if disconnect_task in completed_tasks:
            raise HTTPException(499, 'The request was cancelled.')
        return await upstream_task
    finally:
        # Join both tasks so cancellation cannot leave an API call running.
        for task in (upstream_task, disconnect_task):
            task.cancel()
        await asyncio.gather(upstream_task, disconnect_task, return_exceptions=True)
