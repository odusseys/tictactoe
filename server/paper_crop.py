"""Bounded single-worker paper cropping, independent of the async API loop."""
import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from .errors import GameServiceError


class PaperCropService:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='paper-crop')
        self.segmenter = None
        self.pending = None

    def _crop(self, image_data_url):
        if self.segmenter is None:
            try:
                from .vision.paper import PaperSegmenter
                self.segmenter = PaperSegmenter()
            except (ImportError, OSError, RuntimeError):
                logging.getLogger(__name__).exception('Paper segmentation initialization failed')
                raise GameServiceError(503, 'cropping_unavailable',
                    'Paper cropping is unavailable. Check the local vision dependencies and model files, or turn cropping off.',
                    retryable=False) from None
        try:
            result = self.segmenter.crop_image(image_data_url)
        except ValueError:
            raise GameServiceError(400, 'invalid_image', 'The camera image could not be decoded for cropping.') from None
        except Exception:
            logging.getLogger(__name__).exception('Paper segmentation failed')
            raise GameServiceError(503, 'cropping_unavailable',
                'Paper cropping could not finish. Try again or turn cropping off.', retryable=False) from None
        if result is None:
            raise GameServiceError(422, 'no_paper',
                'Keep the sheet of paper well lit and in view, or turn paper cropping off.', retryable=False)
        return result

    async def crop(self, image_data_url):
        # Cancellation cannot interrupt an in-flight GPU call. Keep its slot
        # occupied until it actually completes, and never build a frame backlog.
        if self.pending is not None and not self.pending.done():
            raise GameServiceError(429, 'cropping_busy', 'Paper cropping is still processing the previous frame.',
                                   headers={'Retry-After': '1'})
        self.pending = asyncio.get_running_loop().run_in_executor(self.executor, self._crop, image_data_url)
        self.pending.add_done_callback(lambda task: task.exception() if not task.cancelled() else None)
        return await asyncio.shield(self.pending)

    def close(self):
        self.executor.shutdown(wait=False, cancel_futures=True)
