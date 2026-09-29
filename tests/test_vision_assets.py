import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from server.vision.assets import BUNDLED_PROMPT, PROMPT_NAME, WEIGHTS_NAME, ensure_paper_assets


class PaperAssetTests(unittest.TestCase):
    def setUp(self):
        self.cache = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.weights = b'test checkpoint'
        self.enterContext(patch('server.vision.assets.WEIGHTS_SHA256', hashlib.sha256(self.weights).hexdigest()))

    def response(self, content):
        return httpx.Response(200, content=content, request=httpx.Request('GET', 'https://example.test/model'))

    def test_first_download_and_cached_offline_restart(self):
        with patch('server.vision.assets.httpx.stream') as stream:
            stream.return_value.__enter__.return_value = self.response(self.weights)
            weights, prompt = ensure_paper_assets(self.cache)
            stream.assert_called_once()
        self.assertEqual(weights.read_bytes(), self.weights)
        self.assertEqual(prompt.read_bytes(), BUNDLED_PROMPT.read_bytes())
        # A missing prompt is restored locally, even without internet access.
        prompt.unlink()
        with patch('server.vision.assets.httpx.stream', side_effect=AssertionError('Must stay offline')):
            self.assertEqual(ensure_paper_assets(self.cache), (weights, prompt))
        self.assertEqual(prompt.read_bytes(), BUNDLED_PROMPT.read_bytes())

    def test_checksum_failure_does_not_install_partial_checkpoint(self):
        with patch('server.vision.assets.httpx.stream') as stream:
            stream.return_value.__enter__.return_value = self.response(b'corrupted')
            with self.assertRaisesRegex(RuntimeError, 'checksum'):
                ensure_paper_assets(self.cache)
        self.assertFalse((self.cache / WEIGHTS_NAME).exists())
        self.assertEqual(list(self.cache.glob('*.part')), [])

    def test_interrupted_download_cleans_up_and_can_retry(self):
        with patch('server.vision.assets.httpx.stream') as stream:
            response = stream.return_value.__enter__.return_value
            def interrupted(**_):
                yield b'partial'
                raise httpx.ReadError('disconnected')
            response.iter_bytes.side_effect = interrupted
            with self.assertRaisesRegex(RuntimeError, 'internet connection'):
                ensure_paper_assets(self.cache)
        self.assertEqual(list(self.cache.iterdir()), [])
        with patch('server.vision.assets.httpx.stream') as stream:
            stream.return_value.__enter__.return_value = self.response(self.weights)
            ensure_paper_assets(self.cache)
        self.assertEqual((self.cache / WEIGHTS_NAME).read_bytes(), self.weights)
        self.assertTrue((self.cache / PROMPT_NAME).exists())
