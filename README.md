# TicAI

## Requirements

- Python **3.11+**, with `pip` and `venv`.
- An OpenAI API key with access to **gpt-6-astra** and available API quota.
- Internet access, a webcam, and a modern browser.

Node.js is not required. The Python requirements include the vision libraries used for optional paper cropping.

## Setup and run

From the project directory, on macOS or Linux:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env
```

Set `OPENAI_API_KEY` in `.env` to your key, then start the app:

```sh
.venv/bin/python -m server
```

Open [http://127.0.0.1:3000](http://127.0.0.1:3000), dismiss **How to play**, allow camera access, and click **Start game**.

Stop the server with **Ctrl+C**. To run it again, repeat only the start command.

## Paper cropping

**Crop to paper** below the camera is on by default and crops each captured frame before reading the board. It can be changed during a game; the next capture uses the selected setting. The live preview stays full-frame. Detection and move selection receive the same cropped JPEG, with the existing high-detail OpenAI settings.

No manual model download is needed. On first startup, the app downloads the same `yoloe-26s-seg.pt` checkpoint (about 31 MB) from the official Ultralytics release and verifies its SHA-256 checksum. The tiny `yoloe-26s-seg-paper-only.npz` prompt file is bundled with the app, avoiding a separate text-encoder download. Both files are cached in `~/.cache/tictactoeagent/yoloe26`; set `VISION_MODEL_CACHE` to use another writable directory. Later starts reuse the cache without downloading. Initial setup requires internet access; if interrupted, restarting safely retries it.

The segmenter uses fused paper embeddings, 640px inference, confidence 0.2, and 20% crop padding. Apple MPS and CUDA use FP16; CPU-only hosts fall back to FP32. A persistent worker loads the model on the first crop request, which can take a few seconds. See the [Ultralytics YOLOE documentation](https://docs.ultralytics.com/models/yoloe/) for the model and reusable prompt format.

If no paper is detected, the app automatically sends the original full frame to OpenAI without a paper warning. Any resulting move decision uses that same frame. Cropping remains enabled and is tried again on the next capture.

`POST /api/crop` accepts the same JPEG/PNG/WebP uploads as the other endpoints (up to 8 MB), returning an in-memory JPEG and an `X-Paper-Crop-Bounds` header. No detection returns HTTP 422 with `code: "no_paper"`. Captured images are never written to disk. The optional OpenCV grid parser in `server/vision/pipeline.py` shares the FP16 paper segmenter but still requires `server/vision/requirements.txt` for its additional dependencies.
