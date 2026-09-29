import base64
import json
import unittest
from unittest.mock import patch

import httpx

from server.app import create_app
from server.contracts import BOARD_OBSERVATION_SCHEMA, CELL_NAMES
from server.images import MAX_IMAGE_BYTES
from api_fixtures import PNG, completed, game_after, headers, observation


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'}))
        self.calls = []
        self.upstream_status = 200
        self.upstream_headers = {}
        self.upstream_text = None
        self.upstream_body = completed(observation(top_left='O'))

        async def upstream(request):
            self.calls.append(json.loads(request.content))
            if self.upstream_text is not None:
                return httpx.Response(self.upstream_status, text=self.upstream_text, headers=self.upstream_headers)
            return httpx.Response(self.upstream_status, json=self.upstream_body, headers=self.upstream_headers)

        self.app = create_app(transport=httpx.MockTransport(upstream))
        await self.enterAsyncContext(self.app.router.lifespan_context(self.app))
        self.client = await self.enterAsyncContext(httpx.AsyncClient(
            transport=httpx.ASGITransport(self.app, raise_app_exceptions=False),
            base_url='http://testserver',
        ))

    async def test_static_health_and_private_paths(self):
        response = await self.client.get('/')
        self.assertIn('Start game', response.text)
        self.assertEqual(response.headers['x-content-type-options'], 'nosniff')
        self.assertEqual((await self.client.head('/app.js')).content, b'')
        self.assertEqual((await self.client.get('/api/health')).json(), {'ok': True, 'configured': True})
        for path in ('/.env', '/server/prompts.py', '/sample_images/01-drawing.png', '/board-stability.js'):
            with self.subTest(path=path):
                self.assertEqual((await self.client.get(path)).status_code, 404)
        response = await self.client.get('/api/board')
        self.assertEqual(response.status_code, 405)
        self.assertIn('error', response.json())

    async def test_board_contract_and_original_image_are_preserved(self):
        state = observation()
        state['unrelated'] = 'discard me'
        response = await self.client.post('/api/board', headers=headers(state=state), content=PNG)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['cells']['top_left']['value'], 'O')
        self.assertEqual(response.json()['model'], 'gpt-6-astra')
        payload = self.calls[0]
        self.assertEqual(payload['reasoning'], {'effort': 'low'})
        self.assertEqual(payload['service_tier'], 'fast')
        self.assertFalse(payload['store'])
        self.assertEqual(payload['text']['format']['schema'], BOARD_OBSERVATION_SCHEMA)
        prompt, context, image = payload['input'][0]['content']
        self.assertIn('do not overthink', prompt['text'])
        self.assertNotIn('discard me', context['text'])
        self.assertNotIn('confidence', context['text'])
        self.assertEqual(base64.b64decode(image['image_url'].split(',')[1]), PNG)
        self.assertEqual(image['detail'], 'high')
        self.assertEqual(self.app.state.active_game_requests, 0)

    async def test_move_contract_roles_history_and_legal_choices(self):
        self.upstream_body = completed({'cell': 'middle_middle'})
        game = game_after(0)
        response = await self.client.post('/api/move', headers=headers(True, game), content=PNG)
        self.assertEqual(response.json(), {'cell': 'middle_middle'})
        payload = self.calls[0]
        self.assertEqual(payload['model'], 'gpt-6-astra')
        self.assertEqual(payload['reasoning'], {'effort': 'medium'})
        prompt, context, image = payload['input'][0]['content']
        for wording in ('You are "self" and play X', 'human player is "opponent" and plays O',
                        'O always moves first', 'DO NOT apply that display rotation'):
            self.assertIn(wording, prompt['text'])
        self.assertEqual(json.loads(context['text']), game)
        self.assertEqual(base64.b64decode(image['image_url'].split(',')[1]), PNG)
        self.assertEqual(payload['text']['format']['schema']['properties']['cell']['enum'], CELL_NAMES[1:])
        self.upstream_body = completed({'cell': 'top_left'})
        self.assertEqual((await self.client.post('/api/move', headers=headers(True), content=PNG)).status_code, 502)

    async def test_invalid_context_and_images_never_reach_openai(self):
        cases = [
            ({'content-type': 'image/png'}, PNG, 400),
            (headers(state={'cells': []}), PNG, 400),
            ({**headers(), 'content-type': 'text/plain'}, PNG, 415),
            (headers(), b'invalid-image-bytes', 400),
            (headers(), b'', 400),
            ({**headers(), 'content-length': str(MAX_IMAGE_BYTES + 1)}, PNG, 413),
        ]
        for request_headers, content, status in cases:
            with self.subTest(status=status, headers=request_headers):
                response = await self.client.post('/api/board', headers=request_headers, content=content)
                self.assertEqual(response.status_code, status, response.text)
                self.assertIn('error', response.json())
        bad_game = game_after(0)
        bad_game['cells']['top_left']['playedBy'] = 'self'
        response = await self.client.post('/api/move', headers=headers(True, bad_game), content=PNG)
        self.assertEqual(response.status_code, 400)
        response = await self.client.post('/api/move', headers=headers(True), content=b'')
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.calls, [])
        self.assertEqual(self.app.state.active_game_requests, 0)

    async def test_chunked_upload_cannot_bypass_size_limit(self):
        async def chunks():
            yield PNG
            yield b'0' * MAX_IMAGE_BYTES
        response = await self.client.post('/api/board', headers=headers(), content=chunks())
        self.assertEqual(response.status_code, 413)
        self.assertEqual(self.calls, [])

    async def test_origin_policy(self):
        for origin in ('https://elsewhere.example', 'null', 'http://[invalid'):
            response = await self.client.post('/api/board', headers={**headers(), 'origin': origin}, content=PNG)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.calls, [])
        response = await self.client.post('/api/board', headers={**headers(), 'origin': 'http://testserver'}, content=PNG)
        self.assertEqual(response.status_code, 200)

    async def test_unknown_is_valid_but_malformed_model_outputs_are_not(self):
        self.upstream_body = completed(observation(top_left='unknown'))
        response = await self.client.post('/api/board', headers=headers(), content=PNG)
        self.assertEqual(response.status_code, 200)
        for body in (completed({}), {'status': 'incomplete', 'output': []},
                     {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]},
                     {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 'bad json'}]}]}):
            self.upstream_body = body
            response = await self.client.post('/api/board', headers=headers(), content=PNG)
            self.assertEqual(response.status_code, 502)

    async def test_upstream_errors_and_missing_key(self):
        for status, code, expected in ((401, None, 502), (403, None, 502), (404, None, 502),
                                      (429, 'insufficient_quota', 503), (429, None, 429), (500, None, 502)):
            self.upstream_status = status
            self.upstream_body = {'error': {'code': code}}
            response = await self.client.post('/api/board', headers=headers(), content=PNG)
            self.assertEqual(response.status_code, expected)
            self.assertNotIn('test-only', response.text)
        self.app.state.astra_client.api_key = ''
        before = len(self.calls)
        response = await self.client.post('/api/board', headers=headers(), content=PNG)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(self.calls), before)
        self.assertFalse((await self.client.get('/api/health')).json()['configured'])

    async def test_error_codes_distinguish_retries_from_configuration_problems(self):
        for status, upstream_code, expected_code, retryable in (
            (401, None, 'api_key_rejected', False),
            (403, None, 'model_unavailable', False),
            (429, 'insufficient_quota', 'quota_exhausted', False),
            (429, None, 'rate_limited', True),
            (400, 'invalid_image', 'invalid_image', True),
            (400, 'invalid_parameter', 'service_configuration', False),
            (500, None, 'service_unavailable', True),
        ):
            with self.subTest(code=expected_code):
                self.upstream_status = status
                self.upstream_body = {'error': {'code': upstream_code}}
                response = await self.client.post('/api/board', headers=headers(), content=PNG)
                self.assertEqual(response.json()['code'], expected_code)
                self.assertEqual(response.json()['retryable'], retryable)
                self.assertEqual(self.app.state.active_game_requests, 0)

    async def test_non_json_upstream_errors_keep_status_and_retry_after(self):
        self.upstream_status = 429
        self.upstream_headers = {'Retry-After': '9'}
        self.upstream_text = '<html>Busy</html>'
        response = await self.client.post('/api/board', headers=headers(), content=PNG)
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.json()['code'], 'rate_limited')
        self.assertTrue(response.json()['retryable'])
        self.assertEqual(response.headers['retry-after'], '9')
