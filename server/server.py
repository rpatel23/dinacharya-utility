"""Daily Tracker server for Option 3 (Tailscale + a home box). See docs/DEPLOYMENT.md §4.

Serves public/ and a sync endpoint, /api/data (GET returns the data, PUT replaces it).
The data is one JSON file, written atomically, plus a copy of the first version of each day (kept 90 days).

Run from the repo root:  python3 server/server.py
Listens on 127.0.0.1 only; `tailscale serve --bg 8080` is the only way in.
Environment (optional): TRACKER_HOST (127.0.0.1), TRACKER_PORT (8080), TRACKER_DATA (server/data).
"""
import datetime
import json
import os
import pathlib
import shutil
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = pathlib.Path(__file__).resolve().parent
PUBLIC = HERE.parent / "public"
DATA_DIR = pathlib.Path(os.environ.get("TRACKER_DATA", HERE / "data"))
DATA = DATA_DIR / "data.json"
KEEP_DAYS = 90
MAX_BODY = 10 * 1024 * 1024
LOCK = threading.Lock()


def snapshot():
    """Copy today's first version of the data, and drop copies older than KEEP_DAYS."""
    today = datetime.date.today()
    snap = DATA_DIR / f"{today}.json"
    if not snap.exists():
        shutil.copy(DATA, snap)
    cutoff = today - datetime.timedelta(days=KEEP_DAYS)
    for f in DATA_DIR.glob("????-??-??.json"):
        try:
            if datetime.date.fromisoformat(f.stem) < cutoff:
                f.unlink()
        except ValueError:
            pass


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map,
                      ".webmanifest": "application/manifest+json", ".yaml": "text/yaml; charset=utf-8",
                      ".js": "text/javascript; charset=utf-8", ".html": "text/html; charset=utf-8"}

    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(PUBLIC), **k)

    def is_api(self):
        return urlsplit(self.path).path == "/api/data"

    def end_headers(self):
        if urlsplit(self.path).path.endswith(("/sw.js", "/habits.yaml", "/")):
            self.send_header("Cache-Control", "no-cache")      # pick up new deploys right away
        super().end_headers()

    def list_directory(self, path):
        self.send_error(404)
        return None

    def reply(self, code, body=b"", ctype="application/json"):
        self.send_response(code)
        if body:
            self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        super().end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.is_api():
            return super().do_GET()
        with LOCK:
            body = DATA.read_bytes() if DATA.exists() else b"{}"
        self.reply(200, body)

    def do_HEAD(self):
        if self.is_api():
            return self.reply(405)
        return super().do_HEAD()

    def do_PUT(self):
        if not self.is_api():
            return self.reply(405)
        try:
            n = int(self.headers.get("Content-Length", ""))
        except ValueError:
            return self.reply(411)
        if n < 0:
            return self.reply(400)
        if n > MAX_BODY:
            return self.reply(413)
        body = self.rfile.read(n)
        try:
            if not isinstance(json.loads(body), dict):
                raise ValueError("not an object")
        except ValueError:
            return self.reply(400, b'{"error":"body must be a JSON object"}')
        with LOCK:
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            tmp = DATA.with_suffix(".tmp")
            tmp.write_bytes(body)
            tmp.replace(DATA)                                   # atomic write
            snapshot()
        self.reply(204)

    def do_POST(self):
        self.reply(405)


def main():
    host = os.environ.get("TRACKER_HOST", "127.0.0.1")
    port = int(os.environ.get("TRACKER_PORT", "8080"))
    srv = ThreadingHTTPServer((host, port), Handler)
    print(f"Daily Tracker on http://{host}:{srv.server_port}/  (data: {DATA})", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
