"""Paper segmentation and the evaluated blur-tolerant board parser, in memory."""
import base64
import time

import cv2
import numpy as np
from .paper import MODEL_CACHE_DIR, PaperSegmenter, padded_mask_bounds
from .detector import detect_grid_and_marks

CELL_NAMES = [f'{row}_{col}' for row in ('top', 'middle', 'bottom') for col in ('left', 'middle', 'right')]
CELL_LABELS = {'X': 'X', 'O': 'O', '.': 'empty', '?': 'unknown'}


class VisionPipeline(PaperSegmenter):
    def detect_board(self, image_data_url):
        """Return cell labels and diagnostics; geometric scores are uncalibrated."""
        started_at = time.perf_counter()
        image_bytes = base64.b64decode(image_data_url.split(',', 1)[1], validate=True)
        image_bgr = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image_bgr is None or min(image_bgr.shape[:2]) < 32 or image_bgr.shape[0]*image_bgr.shape[1] > 24_000_000:
            raise ValueError('Use a decodable image between 32 pixels and 24 megapixels.')
        paper_mask, paper_confidence = self.segment_paper(image_bgr)
        detection = {
            'detector': 'local', 'status': 'no_paper', 'paperConfidence': paper_confidence,
            'cells': {name: {'value': 'unknown'} for name in CELL_NAMES},
        }
        if paper_mask is not None and np.any(paper_mask):
            x0, y0, x1, y1 = padded_mask_bounds(paper_mask, image_bgr.shape[1], image_bgr.shape[0])
            cell_labels, _, diagnostics = detect_grid_and_marks(image_bgr[y0:y1, x0:x1], paper_mask[y0:y1, x0:x1])
            detection.update(status='no_grid', cropBounds=[x0, y0, x1, y1])
            if cell_labels is not None:
                detection.update(
                    status='detected', geometryScore=diagnostics['selected']['score'],
                    cells={name: {'value': CELL_LABELS[value]} for name, value in zip(CELL_NAMES, cell_labels.flatten())},
                )
        detection['processingMs'] = round((time.perf_counter()-started_at)*1000, 1)
        return detection
