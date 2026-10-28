"""python -m backend.api [--port 8000]"""
import argparse
import os

import uvicorn

ap = argparse.ArgumentParser()
ap.add_argument("--host", default=os.environ.get("API_HOST", "127.0.0.1"))
ap.add_argument("--port", type=int, default=int(os.environ.get("API_PORT", "8000")))
args = ap.parse_args()
uvicorn.run("backend.api.app:create_app", factory=True, host=args.host, port=args.port, log_level="info")
