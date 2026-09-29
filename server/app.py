"""Single-process ASGI app: static frontend, board detection, and move selection."""
import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path

import httpx
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.middleware import Middleware
from starlette.requests import ClientDisconnect, Request
from starlette.responses import FileResponse, Response
from starlette.routing import Route

from .game_api import detect_board_state, select_ai_move, parse_request_game_state
from .http import SecurityHeadersMiddleware, require_same_origin, handle_http_error, json_response, cancel_on_disconnect
from .images import read_image_data_url
from .openai import AstraClient
from .paper_crop import PaperCropService

PUBLIC_ROOT = Path(__file__).resolve().parent.parent / 'public'
STATIC_FILES = {
    '/': ('index.html', 'text/html'),
    '/styles.css': ('styles.css', 'text/css'),
    '/game.css': ('game.css', 'text/css'),
    '/favicon.svg': ('favicon.svg', 'image/svg+xml'),
    **{f'/{name}.js': (f'{name}.js', 'text/javascript') for name in (
        'app', 'camera', 'api', 'board', 'board-state', 'game-state', 'game-session', 'game-view', 'errors', 'retry',
    )},
}


async def get_health(request):
    return json_response({'ok': True, 'configured': bool(request.app.state.astra_client.api_key)})


async def serve_static_file(request):
    asset = STATIC_FILES.get(request.url.path)
    if asset is None:
        raise HTTPException(404, 'Not found.')
    filename, media_type = asset
    return FileResponse(PUBLIC_ROOT / filename, media_type=media_type, headers={'Cache-Control': 'no-cache'})


async def handle_game_request(request: Request):
    require_same_origin(request)
    server_state = request.app.state
    if server_state.active_game_requests >= 2:
        raise HTTPException(429, 'The server is busy processing snapshots.', headers={'Retry-After': '2'})
    # No await between checking and reserving a slot on this event loop.
    server_state.active_game_requests += 1
    try:
        async with asyncio.timeout(75):
            if request.url.path == '/api/crop':
                image_data_url = await read_image_data_url(request)
                jpeg, bounds = await cancel_on_disconnect(request, server_state.paper_crop.crop(image_data_url))
                return Response(jpeg, media_type='image/jpeg', headers={
                    'Cache-Control': 'no-store', 'X-Paper-Crop-Bounds': ','.join(map(str, bounds)),
                })
            is_move_request = request.url.path == '/api/move'
            game_state = parse_request_game_state(request.headers, is_move_request)
            image_data_url = await read_image_data_url(request)
            process_game_image = select_ai_move if is_move_request else detect_board_state
            result = await cancel_on_disconnect(request, process_game_image(server_state.astra_client, image_data_url, game_state))
            return json_response(result)
    except ClientDisconnect:
        raise HTTPException(499, 'The request was cancelled.') from None
    except TimeoutError:
        raise HTTPException(504, 'The request took too long. Your game is saved.') from None
    finally:
        server_state.active_game_requests -= 1


def create_app(*, transport=None):
    @asynccontextmanager
    async def lifespan(app):
        async with httpx.AsyncClient(timeout=60, transport=transport) as http_client:
            app.state.astra_client = AstraClient(http_client, os.getenv('OPENAI_API_KEY', ''))
            app.state.active_game_requests = 0
            app.state.paper_crop = PaperCropService()
            try:
                yield
            finally:
                app.state.paper_crop.close()

    return Starlette(
        routes=[
            Route('/api/health', get_health),
            Route('/api/board', handle_game_request, methods=['POST']),
            Route('/api/move', handle_game_request, methods=['POST']),
            Route('/api/crop', handle_game_request, methods=['POST']),
            *(Route(path, serve_static_file) for path in STATIC_FILES),
        ],
        lifespan=lifespan, middleware=[Middleware(SecurityHeadersMiddleware)],
        exception_handlers={HTTPException: handle_http_error, Exception: handle_http_error},
    )


app = create_app()
