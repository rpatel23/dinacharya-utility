"""Test for server/server.py (Option 3), including two devices syncing through it. Run: python tests/server_test.py"""
import datetime
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok  ", msg)


def req(method, path, body=None):
    r = urllib.request.Request(BASE + path, data=body, method=method)
    try:
        with urllib.request.urlopen(r) as res:
            return res.status, res.headers, res.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers, e.read()


with tempfile.TemporaryDirectory() as data_dir:
    data_dir = pathlib.Path(data_dir)
    env = {**os.environ, "TRACKER_PORT": "0", "TRACKER_DATA": str(data_dir)}
    proc = subprocess.Popen([sys.executable, "-u", str(ROOT / "server" / "server.py")], env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    try:
        line = proc.stdout.readline()
        BASE = line.split()[3].rstrip("/")
        check(BASE.startswith("http://127.0.0.1:"), "server listens on 127.0.0.1 only")

        # Static files
        s, h, b = req("GET", "/")
        check(s == 200 and b"<title>Daily Tracker</title>" in b, "serves public/index.html at /")
        for path, ctype in (("/habits.yaml", "text/yaml"), ("/manifest.webmanifest", "application/manifest+json"),
                            ("/sw.js", "text/javascript"), ("/icon-192.png", "image/png")):
            s, h, _ = req("GET", path)
            check(s == 200 and h["Content-Type"].startswith(ctype), f"{path} served as {ctype}")
        check(req("GET", "/sw.js")[1]["Cache-Control"] == "no-cache", "sw.js is revalidated on every load")
        check(req("GET", "/%2e%2e/server/server.py")[0] == 404 and req("GET", "/../README.md")[0] == 404,
              "nothing outside public/ is served")

        # /api/data
        s, h, b = req("GET", "/api/data")
        check(s == 200 and json.loads(b) == {} and h["Cache-Control"] == "no-store", "GET /api/data starts as {}")
        old = data_dir / "2000-01-01.json"
        old.write_text("{}")
        doc = {"app": "daily-tracker", "version": 3, "days": {"2026-11-17": {"v": {"nasya": {"n": 1, "t": 5}}}}}
        check(req("PUT", "/api/data", json.dumps(doc).encode())[0] == 204, "PUT /api/data stores the data")
        check(json.loads(req("GET", "/api/data?x=1")[2]) == doc, "GET returns what was PUT (query string ignored)")
        snap = data_dir / f"{datetime.date.today()}.json"
        check(snap.exists() and json.loads(snap.read_text()) == doc, "daily snapshot written")
        check(not old.exists(), "snapshots older than 90 days are pruned")
        doc2 = {**doc, "days": {}}
        req("PUT", "/api/data", json.dumps(doc2).encode())
        check(json.loads(snap.read_text()) == doc, "snapshot keeps the day's first version")
        for bad in (b"not json", b"[1, 2]", b'"text"'):
            check(req("PUT", "/api/data", bad)[0] == 400, f"rejects body {bad.decode()!r}")
        check(json.loads(req("GET", "/api/data")[2]) == doc2, "rejected PUTs leave the data unchanged")
        check(req("POST", "/api/data", b"{}")[0] == 405 and req("PUT", "/index.html", b"{}")[0] == 405,
              "other methods and paths are refused")
        check(not list(data_dir.glob("*.tmp")), "no temp files left behind")

        # Two devices syncing through the real server
        req("PUT", "/api/data", b"{}")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            errors = []

            def device():
                page = browser.new_context(viewport={"width": 420, "height": 900}).new_page()
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(BASE + "/")
                page.click("#set"); page.check('input[name="sm"][value="api"]'); page.click("#sOk")
                page.wait_for_function("document.getElementById('s3').textContent.startsWith('Synced')")
                return page

            def sync_now(page):
                page.evaluate("document.getElementById('s3').textContent = ''")
                page.click("#s3")
                page.wait_for_function("document.getElementById('s3').textContent.startsWith('Synced')")

            A = device()
            A.locator('[data-row="nasya"] button.dot').click()
            A.fill("#note", "via the box")
            sync_now(A)
            today = A.evaluate("Object.keys(JSON.parse(localStorage.getItem('dailyTracker.v3')).days)[0]")
            stored = json.loads((data_dir / "data.json").read_text())
            check(stored["days"][today]["v"]["nasya"]["n"] == 1 and stored["days"][today]["note"] == "via the box",
                  "device A's change lands in data.json")
            B = device()
            check(B.get_attribute('[data-row="nasya"] button.dot', "data-s") == "1" and B.input_value("#note") == "via the box",
                  "device B pulls it from the server")
            A.evaluate("navigator.serviceWorker.ready")
            check(A.evaluate("navigator.serviceWorker.getRegistration().then(r => !!r)"), "service worker installs from the server")
            check(not errors, "no page errors")
            browser.close()
    finally:
        proc.terminate()
        proc.wait()
