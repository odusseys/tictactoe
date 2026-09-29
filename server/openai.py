"""Shared asynchronous Responses API transport for detection and moves."""
import asyncio
import json

import httpx
from .errors import GameServiceError

ASTRA_MODEL = 'gpt-6-astra'


def map_openai_error(status_code, error_code, headers=None):
    if status_code == 401:
        return GameServiceError(502, 'api_key_rejected', 'The server API key was rejected. Update OPENAI_API_KEY and restart the server.', retryable=False)
    if status_code in (403, 404):
        return GameServiceError(502, 'model_unavailable', 'OpenAI denied access or could not find the requested model. Check the server’s model and project access.', retryable=False)
    if status_code == 429 and error_code == 'insufficient_quota':
        return GameServiceError(503, 'quota_exhausted', 'The OpenAI project has no available API quota. Check its billing, then retry.', retryable=False)
    if status_code == 429:
        retry_headers = {'Retry-After': headers['retry-after']} if headers and headers.get('retry-after') else None
        return GameServiceError(429, 'rate_limited', 'The AI service is busy. Your game is saved.', headers=retry_headers)
    if status_code in (400, 422):
        if error_code in ('invalid_image', 'invalid_image_format', 'image_too_large', 'image_parse_error'):
            return GameServiceError(502, 'invalid_image', 'The AI could not read the captured image.')
        return GameServiceError(502, 'service_configuration', 'OpenAI rejected the request settings. Check the server configuration before retrying.', retryable=False)
    return GameServiceError(502, 'service_unavailable', 'The AI service is temporarily unavailable. Your game is saved.')


def parse_structured_output(response_data):
    if not isinstance(response_data, dict) or response_data.get('status') != 'completed' or not isinstance(response_data.get('output'), list):
        raise GameServiceError(502, 'incomplete_response', 'The AI did not finish its answer.')
    try:
        # Reasoning output is separate; only message text contains the JSON.
        content_parts = [part for item in response_data['output'] if item['type'] == 'message'
                         for part in item.get('content', [])]
        if any(part['type'] == 'refusal' for part in content_parts):
            raise GameServiceError(502, 'refused_response', 'The AI could not process this image. Keep only the board in view.')
        return json.loads(''.join(part['text'] for part in content_parts if part['type'] == 'output_text'))
    except (ValueError, KeyError, TypeError, RecursionError):
        raise GameServiceError(502, 'invalid_response', 'The AI returned an unreadable answer.') from None


class AstraClient:
    def __init__(self, http_client: httpx.AsyncClient, api_key: str):
        self.http_client = http_client
        self.api_key = api_key

    async def generate_structured_output(self, *, reasoning_effort, message_content, output_schema, schema_name):
        if not self.api_key:
            raise GameServiceError(503, 'api_key_missing', 'Add OPENAI_API_KEY to the server’s .env file, then restart it.', retryable=False)
        payload = {
            'model': ASTRA_MODEL, 'service_tier': 'fast', 'reasoning': {'effort': reasoning_effort},
            'store': False, 'max_output_tokens': 10000,
            'input': [{'role': 'user', 'content': message_content}],
            'text': {'format': {'type': 'json_schema', 'name': schema_name, 'strict': True, 'schema': output_schema}},
        }
        try:
            async with asyncio.timeout(60):
                response = await self.http_client.post(
                    'https://api.openai.com/v1/responses', json=payload,
                    headers={'Authorization': f'Bearer {self.api_key}'},
                )
        except (TimeoutError, httpx.TimeoutException):
            raise GameServiceError(504, 'timeout', 'The AI took too long to answer. Your game is saved.') from None
        except httpx.HTTPError:
            raise GameServiceError(502, 'upstream_connection', 'The server lost its connection to the AI service.') from None
        try:
            response_data = response.json()
        except (ValueError, RecursionError):
            # Preserve an HTTP failure even when a proxy returns HTML instead of JSON.
            if not response.is_success:
                raise map_openai_error(response.status_code, None, response.headers) from None
            raise GameServiceError(502, 'invalid_response', 'The AI service returned an unreadable response.') from None
        if not response.is_success:
            error = response_data.get('error') if isinstance(response_data, dict) else None
            raise map_openai_error(response.status_code, error.get('code') if isinstance(error, dict) else None, response.headers)
        return parse_structured_output(response_data)
