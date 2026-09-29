"""Persistent paper segmentation with FP16 acceleration and padded image crops."""
import base64
import math
import os
from .assets import MODEL_CACHE_DIR, ensure_paper_assets
os.environ.setdefault('YOLO_CONFIG_DIR', str(MODEL_CACHE_DIR / 'settings'))

import cv2
import numpy as np
import torch
from ultralytics import YOLOE


def padded_mask_bounds(mask, width, height):
    """Match full-size nearest-neighbor mask bounds without expanding the mask."""
    columns = cv2.resize(np.any(mask, axis=0).astype(np.uint8)[None, :], (width, 1), interpolation=cv2.INTER_NEAREST)
    rows = cv2.resize(np.any(mask, axis=1).astype(np.uint8)[:, None], (1, height), interpolation=cv2.INTER_NEAREST)
    xs, ys = np.flatnonzero(columns), np.flatnonzero(rows)
    if not len(xs) or not len(ys):
        return None
    x0, y0, x1, y1 = int(xs[0]), int(ys[0]), int(xs[-1]) + 1, int(ys[-1]) + 1
    px, py = math.ceil((x1 - x0) * .2), math.ceil((y1 - y0) * .2)
    return [max(0, x0 - px), max(0, y0 - py), min(width, x1 + px), min(height, y1 + py)]


class PaperSegmenter:
    def __init__(self):
        cv2.setNumThreads(1)
        self.device = 'mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu'
        # CPU-only hosts keep a supported FP32 fallback; Apple/CUDA GPUs use FP16.
        self.precision = 32 if self.device == 'cpu' else 16
        weights, embeddings = ensure_paper_assets(MODEL_CACHE_DIR)
        self.paper_model = YOLOE(str(weights))
        self.paper_model.load_prompt_embeddings(embeddings)
        if list(self.paper_model.names.values()) != ['paper']:
            raise RuntimeError('Expected paper-only prompt embeddings.')
        self.paper_model.model.eval()
        self.paper_model.model.model[-1].fuse(self.paper_model.model.pe)
        self.paper_model.to(self.device)

    def _segment_small_mask(self, image_bgr):
        height, width = image_bgr.shape[:2]
        scale = 640 / max(height, width)
        resized = cv2.resize(image_bgr, (round(width * scale), round(height * scale)), interpolation=cv2.INTER_AREA)
        result = self.paper_model.predict(
            resized, imgsz=640, rect=True, device=self.device, quantize=self.precision,
            conf=.2, max_det=1, retina_masks=True, verbose=False, save=False,
        )[0]
        if result.masks is None or not len(result.boxes):
            return None, None
        index = int(result.boxes.conf.argmax())
        confidence = float(result.boxes.conf[index])
        mask = np.uint8(result.masks.data[index].cpu().numpy() > .5) * 255
        return (mask, confidence) if np.any(mask) else (None, None)

    def segment_paper(self, image_bgr):
        """Full-size mask for the optional local OpenCV grid parser."""
        mask, confidence = self._segment_small_mask(image_bgr)
        if mask is None:
            return None, None
        return cv2.resize(mask, (image_bgr.shape[1], image_bgr.shape[0]), interpolation=cv2.INTER_NEAREST), confidence

    def crop_image(self, image_data_url):
        """Return a JPEG crop and original-frame bounds, or None for no paper."""
        image_bytes = base64.b64decode(image_data_url.split(',', 1)[1], validate=True)
        image = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None or min(image.shape[:2]) < 32 or image.shape[0] * image.shape[1] > 24_000_000:
            raise ValueError('Use a decodable image between 32 pixels and 24 megapixels.')
        mask, _ = self._segment_small_mask(image)
        if mask is None:
            return None
        bounds = padded_mask_bounds(mask, image.shape[1], image.shape[0])
        if bounds is None:
            return None
        x0, y0, x1, y1 = bounds
        ok, jpeg = cv2.imencode('.jpg', image[y0:y1, x0:x1], [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not ok:
            raise RuntimeError('Could not encode the paper crop.')
        return jpeg.tobytes(), bounds
