"""Install the fixed paper model once, without a separate text encoder."""
import hashlib
import os
from pathlib import Path
import shutil
import tempfile

import httpx

MODEL_CACHE_DIR = Path(os.environ.get('VISION_MODEL_CACHE', Path.home() / '.cache/tictactoeagent/yoloe26')).expanduser()
WEIGHTS_NAME = 'yoloe-26s-seg.pt'
WEIGHTS_URL = f'https://github.com/ultralytics/assets/releases/download/v8.4.0/{WEIGHTS_NAME}'
WEIGHTS_SHA256 = '48f24206bc8680d60cbbfa296b0140da849669b9515058b72f5a945142df0654'
PROMPT_NAME = 'yoloe-26s-seg-paper-only.npz'
BUNDLED_PROMPT = Path(__file__).with_name('assets') / PROMPT_NAME


def _valid_weights(path):
    if not path.is_file():
        return False
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest() == WEIGHTS_SHA256


def _download_weights(destination):
    print('Downloading paper segmentation model (31 MB, first run only)…', flush=True)
    temporary = None
    try:
        # Publish only a complete, verified file. A failed download can be
        # retried safely, and other server processes never see a partial model.
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix='.part', delete=False) as target:
            temporary = Path(target.name)
            with httpx.stream('GET', WEIGHTS_URL, follow_redirects=True,
                              timeout=httpx.Timeout(60, connect=15)) as response:
                response.raise_for_status()
                for chunk in response.iter_bytes(chunk_size=1024 * 1024):
                    target.write(chunk)
        if not _valid_weights(temporary):
            raise RuntimeError('The downloaded paper model failed its checksum check. Restart to try again.')
        temporary.replace(destination)
    except httpx.HTTPError as error:
        raise RuntimeError('Could not download the paper model. Check your internet connection and restart.') from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def ensure_paper_assets(cache_dir=None):
    """Return local checkpoint/prompt paths, downloading only missing weights."""
    cache_dir = Path(cache_dir) if cache_dir is not None else MODEL_CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    weights = cache_dir / WEIGHTS_NAME
    if not _valid_weights(weights):
        _download_weights(weights)
    # Use the exact precomputed paper prompt. Generating it at runtime would
    # require downloading an additional, much larger text encoder.
    embeddings = cache_dir / PROMPT_NAME
    if not embeddings.is_file():
        with tempfile.NamedTemporaryFile(dir=cache_dir, suffix='.part', delete=False) as target:
            temporary = Path(target.name)
        try:
            shutil.copyfile(BUNDLED_PROMPT, temporary)
            temporary.replace(embeddings)
        finally:
            temporary.unlink(missing_ok=True)
    return weights, embeddings
