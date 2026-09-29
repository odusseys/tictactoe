"""Run with python -m server; add --reload during development."""
import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
import uvicorn


def main():
    load_dotenv(Path(__file__).resolve().parent.parent / '.env')
    parser = argparse.ArgumentParser(description='Frame webcam tic-tac-toe server')
    parser.add_argument('--reload', action='store_true')
    args = parser.parse_args()
    uvicorn.run(
        'server.app:app', host=os.getenv('HOST', '127.0.0.1'),
        port=int(os.getenv('PORT', '3000')), reload=args.reload,
        timeout_keep_alive=15, timeout_graceful_shutdown=5,
    )


if __name__ == '__main__':
    main()
