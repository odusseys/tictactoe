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

The paper segmenter keeps the same `yoloe-26s-seg.pt` model and `yoloe-26s-seg-paper-only.npz` embeddings. Place both in `~/.cache/tictactoeagent/yoloe26`, or set `VISION_MODEL_CACHE` to their directory. It uses fused paper embeddings, 640px inference, confidence 0.2, and 20% crop padding. Apple MPS and CUDA use FP16; CPU-only hosts fall back to FP32. A persistent worker loads the model on the first crop request, which can take a few seconds.

If no paper is detected, the app automatically sends the original full frame to OpenAI without a paper warning. Any resulting move decision uses that same frame. Cropping remains enabled and is tried again on the next capture.

`POST /api/crop` accepts the same JPEG/PNG/WebP uploads as the other endpoints (up to 8 MB), returning an in-memory JPEG and an `X-Paper-Crop-Bounds` header. No detection returns HTTP 422 with `code: "no_paper"`. Nothing is written to disk. The optional OpenCV grid parser in `server/vision/pipeline.py` shares the FP16 paper segmenter but still requires `server/vision/requirements.txt` for its additional dependencies.
