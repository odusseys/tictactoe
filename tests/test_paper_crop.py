import asyncio
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import httpx

from api_fixtures import PNG
from server.app import create_app
from server.errors import GameServiceError
from server.paper_crop import PaperCropService


class PaperCropApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.enterContext(patch.dict('os.environ', {'OPENAI_API_KEY': 'test-only'}))
        self.upstream_calls = 0

        async def upstream(request):
            self.upstream_calls += 1
            return httpx.Response(500)

        self.app = create_app(transport=httpx.MockTransport(upstream))
        await self.enterAsyncContext(self.app.router.lifespan_context(self.app))
        self.client = await self.enterAsyncContext(httpx.AsyncClient(
            transport=httpx.ASGITransport(self.app), base_url='http://testserver'))

    async def test_crop_returns_image_and_bounds_without_calling_openai(self):
        self.app.state.paper_crop.segmenter = SimpleNamespace(crop_image=lambda _: (b'cropped-jpeg', [2, 3, 40, 50]))
        response = await self.client.post('/api/crop', content=PNG, headers={'Content-Type': 'image/png'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b'cropped-jpeg')
        self.assertEqual(response.headers['content-type'], 'image/jpeg')
        self.assertEqual(response.headers['x-paper-crop-bounds'], '2,3,40,50')
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(self.upstream_calls, 0)

    async def test_no_paper_is_distinct_from_service_failure_and_does_not_call_ai(self):
        self.app.state.paper_crop.segmenter = SimpleNamespace(crop_image=lambda _: None)
        response = await self.client.post('/api/crop', content=PNG, headers={'Content-Type': 'image/png'})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()['code'], 'no_paper')
        self.assertEqual(self.app.state.active_game_requests, 0)
        self.assertEqual(self.upstream_calls, 0)

    async def test_cancelled_gpu_work_keeps_its_slot_until_completion(self):
        service = PaperCropService()
        started, finish = threading.Event(), threading.Event()

        def crop(_):
            started.set()
            finish.wait(5)
            return b'jpeg', [0, 0, 4, 4]

        service.segmenter = SimpleNamespace(crop_image=crop)
        task = asyncio.create_task(service.crop('test-frame'))
        try:
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaises(GameServiceError) as context:
                await service.crop('second-frame')
            self.assertEqual(context.exception.code, 'cropping_busy')
            finish.set()
            await asyncio.wait_for(asyncio.shield(service.pending), 5)
            self.assertEqual(await service.crop('next-frame'), (b'jpeg', [0, 0, 4, 4]))
        finally:
            finish.set()
            service.close()
