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
