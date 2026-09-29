import asyncio
import unittest
from unittest.mock import patch

import httpx

from server.app import create_app
from api_fixtures import PNG, headers


class RequestLifecycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_disconnect_cancels_upstream_and_releases_request_slot(self):
        self.enterContext(patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'}))
        started = asyncio.Queue()
        cancelled = asyncio.Queue()

        async def upstream(request):
            started.put_nowait(True)
            try:
                await asyncio.Future()
            finally:
                cancelled.put_nowait(True)

        app = create_app(transport=httpx.MockTransport(upstream))
        async with app.router.lifespan_context(app):
            tasks = []
            queues = []
            responses = []

            def launch():
                queue = asyncio.Queue()
                queue.put_nowait({'type': 'http.request', 'body': PNG, 'more_body': False})
                messages = []

                async def send(message):
                    messages.append(message)

                scope = {
                    'type': 'http', 'asgi': {'version': '3.0'}, 'http_version': '1.1',
                    'method': 'POST', 'scheme': 'http', 'path': '/api/board',
                    'raw_path': b'/api/board', 'root_path': '', 'query_string': b'',
                    'headers': [(key.encode(), value.encode()) for key, value in headers().items()],
                    'server': ('localhost', 3000), 'client': ('127.0.0.1', 1234),
                }
                task = asyncio.create_task(app(scope, queue.get, send))
                tasks.append(task)
                queues.append(queue)
                responses.append(messages)
                return task

            try:
                launch()
                await asyncio.wait_for(started.get(), 1)
                launch()
                await asyncio.wait_for(started.get(), 1)
                self.assertEqual(app.state.active_game_requests, 2)
                third = launch()
                await asyncio.wait_for(third, 1)
                self.assertEqual(responses[2][0]['status'], 429)
                self.assertEqual(app.state.active_game_requests, 2)
                for index in (0, 1):
                    queues[index].put_nowait({'type': 'http.disconnect'})
                    await asyncio.wait_for(cancelled.get(), 1)
                    await asyncio.wait_for(tasks[index], 1)
                    self.assertEqual(responses[index][0]['status'], 499)
                self.assertEqual(app.state.active_game_requests, 0)
                launch()
                await asyncio.wait_for(started.get(), 1)
                self.assertEqual(app.state.active_game_requests, 1)
                queues[-1].put_nowait({'type': 'http.disconnect'})
                await asyncio.wait_for(tasks[-1], 1)
                self.assertEqual(app.state.active_game_requests, 0)
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
