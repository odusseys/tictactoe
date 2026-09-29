"""Bounded, in-memory image uploads; no files or multipart parsing."""
import base64

from starlette.exceptions import HTTPException
from starlette.requests import Request
from .errors import GameServiceError

MAX_IMAGE_BYTES = 8 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {'image/jpeg', 'image/png', 'image/webp'}


def matches_image_signature(image_bytes: bytes, media_type: str) -> bool:
    if media_type == 'image/jpeg':
        return image_bytes.startswith(b'\xff\xd8\xff')
    if media_type == 'image/png':
        return image_bytes.startswith(b'\x89PNG\r\n\x1a\n')
    return image_bytes[:4] == b'RIFF' and image_bytes[8:12] == b'WEBP'


async def read_image_data_url(request: Request) -> str:
    media_type = request.headers.get('content-type', '').split(';')[0].strip()
    if media_type not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(415, 'Send a JPEG, PNG, or WebP image.')
    try:
        declared_size_bytes = int(request.headers.get('content-length', '0'))
        if declared_size_bytes < 0:
            raise ValueError
    except ValueError:
        raise HTTPException(400, 'Invalid image length.') from None
    if declared_size_bytes > MAX_IMAGE_BYTES:
        raise HTTPException(413, 'The snapshot is too large. The limit is 8 MB.')
    image_bytes = bytearray()
    # Count streamed bytes as well: chunked uploads have no Content-Length.
    async for chunk in request.stream():
        if len(image_bytes) + len(chunk) > MAX_IMAGE_BYTES:
            raise HTTPException(413, 'The snapshot is too large. The limit is 8 MB.')
        image_bytes.extend(chunk)
    if len(image_bytes) < 12 or not matches_image_signature(image_bytes, media_type):
        raise GameServiceError(400, 'invalid_image', 'The snapshot is not a valid image. Taking another may help.')
    return f'data:{media_type};base64,{base64.b64encode(image_bytes).decode("ascii")}'
