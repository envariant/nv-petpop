"""python -m mock_server [--port 8000]"""
import argparse

import uvicorn

from .app import create_app

ap = argparse.ArgumentParser()
ap.add_argument("--host", default="127.0.0.1")
ap.add_argument("--port", type=int, default=8000)
args = ap.parse_args()
uvicorn.run(create_app(), host=args.host, port=args.port, log_level="info")
