"""Smoke test for public/index.html. Run: python tests/smoke_test.py"""
import functools
import http.server
import json
import pathlib
import re
import threading
from playwright.sync_api import sync_playwright

PUBLIC = pathlib.Path(__file__).resolve().parent.parent / "public"
URL = (PUBLIC / "index.html").as_uri()


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve_public():
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(PUBLIC)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}/"


DEPLOYED = "groups:\r\n  A:\r\n    nasya: Nasya\r\n    zz: Deployed habit\r\n"   # CRLF on purpose
LOCAL = "groups:\n  A:\n    nasya: Nasya\n    zz: Deployed habit\n    yy: Local habit\n"
LEGACY = "groups:\n  A:\n    ww: Legacy habit\n"
V1 = {"config": [], "days": {"TODAY": {"v": {"water": [1, 1, 1, 0, 0, 0], "yoga": [2], "pcf": [1]},
                                            "miles": "3.5", "note": "old"}}, "lastBackup": None}

def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok  ", msg)

with sync_playwright() as p:
    browser = p.chromium.launch()
    pg = browser.new_page(viewport={"width": 420, "height": 900})
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))

    pg.on("dialog", lambda d: d.accept())               # confirm() on import
    v3 = lambda page: json.loads(page.evaluate("localStorage.getItem('dailyTracker.v3')"))

    # v1 -> v3 migration
    pg.goto(URL)
    today = pg.evaluate("(d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`)(new Date())")
    V1["days"] = {today: V1["days"]["TODAY"]}
    pg.evaluate("v => { localStorage.clear(); localStorage.setItem('dailyTracker.v1', JSON.stringify(v)); }", V1)
    pg.reload()
    days = v3(pg)["days"]
    check(days[today]["v"] == {k: {"n": n, "t": 0} for k, n in {"yoga": 2, "water": 3, "pcf": 1, "miles": 3.5}.items()}
          and days[today]["note"] == "old" and days[today]["noteT"] == 0, "v1 data migrated to v3 with t = 0")

    # Counter (dots): set water to 4 -> min
    pg.locator('[data-row="water"] button.dot').nth(3).click()
    shades = [pg.locator('[data-row="water"] button.dot').nth(i).get_attribute("data-s") for i in range(6)]
    check(shades == ["1", "1", "1", "1", "0", "0"], "water counter reaches min at 4")

    # Counter (one): tap 3x -> 3 = min, right-click -> 2
    g = pg.locator('[data-row="greens"] button.dot')
    for _ in range(3):
        g.click()
    check(g.inner_text() == "3", "greens single-circle counter increments")
    g.click(button="right")
    check(pg.locator('[data-row="greens"] button.dot').inner_text() == "2", "right-click subtracts")

    # Check: cycles
    c = pg.locator('[data-row="nasya"] button.dot')
    c.click()
    check(pg.locator('[data-row="nasya"] button.dot').get_attribute("data-s") == "1", "check cycles to min")

    # Persistence
    pg.reload()
    check(pg.locator('[data-row="nasya"] button.dot').get_attribute("data-s") == "1", "state persists after reload")

    # Config validation
    pg.click("#edit")
    for bad, expect in [("groups:\n  A:\n    x: {name: X, cnt: 3}\n", 'unknown option "cnt"'),
                        ("groups:\n  A:\n    x: {name: X, count: 3, min: 4}\n", "min > max"),
                        ("groups:\n  A:\n    x: {name: X, days: tu}\n", 'unknown day "tu"'),
                        ("groups:\n  A:\n    x: {name: X, every: 2}\n", "every needs a start date")]:
        pg.fill("#cfg", bad)
        pg.click("#cfgOk")
        check(expect in pg.inner_text("#cfgErr"), f"rejects config: {expect}")
    pg.click("#cfgNo")

    # ---------- v3 data: timestamps ----------
    d = v3(pg)["days"][today]
    check(d["v"]["nasya"]["n"] == 1 and d["v"]["nasya"]["t"] > 1e12, "edit stores {n, t}")
    check(d["v"]["yoga"] == {"n": 2, "t": 0}, "untouched migrated value keeps t = 0")
    pg.locator('[data-row="nasya"] button.dot').click()
    pg.locator('[data-row="nasya"] button.dot').click()
    n = v3(pg)["days"][today]["v"]["nasya"]
    check(n["n"] == 0 and n["t"] > 1e12, "clearing a value keeps {n: 0, t}")
    check(pg.get_attribute('[data-row="nasya"] button.dot', "data-s") == "0", "cleared value shows missed")
    pg.fill("#note", "hello")
    d = v3(pg)["days"][today]
    check(d["note"] == "hello" and d["noteT"] > 1e12, "note stores noteT")

    # v2 -> v3 migration
    V2 = {"days": {today: {"v": {"nasya": 2, "water": 5}, "note": "v2 note"}}, "lastBackup": 123}
    pg.evaluate("v => { localStorage.clear(); localStorage.setItem('dailyTracker.v2', JSON.stringify(v)); }", V2)
    pg.reload()
    s3 = v3(pg)
    check(s3["days"][today] == {"v": {"nasya": {"n": 2, "t": 0}, "water": {"n": 5, "t": 0}}, "note": "v2 note", "noteT": 0}
          and s3["lastBackup"] == 123, "v2 data migrated to v3")
    check(pg.evaluate("localStorage.getItem('dailyTracker.v2')") is not None, "v2 key kept as a safety copy")
    check(pg.get_attribute('[data-row="nasya"] button.dot', "data-s") == "2", "migrated v2 value shown")

    # Export writes v3
    with pg.expect_download() as dl:
        pg.click("#exp")
    b = json.loads(pathlib.Path(dl.value.path()).read_text(encoding="utf-8"))
    check(b["version"] == 3 and b["days"][today]["v"]["nasya"] == {"n": 2, "t": 0} and "yaml" not in b, "export writes a v3 backup")

    # Import: v1, v2 and v3 backups
    def imp(name, obj):
        pg.set_input_files("#file", files=[{"name": name, "mimeType": "application/json", "buffer": json.dumps(obj).encode()}])
        pg.wait_for_function(f"document.getElementById('s3').textContent === 'Imported {name}'")
        return v3(pg)["days"][today]
    d = imp("b2.json", {"app": "daily-tracker", "version": 2, "yaml": "groups: {}", "days": {today: {"v": {"nasya": 1}}}})
    check(d == {"v": {"nasya": {"n": 1, "t": 0}}}, "v2 backup imports (config ignored)")
    d = imp("b1.json", {"config": [], "days": {today: {"v": {"nasya": [2]}, "note": "n1"}}})
    check(d == {"v": {"nasya": {"n": 2, "t": 0}}, "note": "n1", "noteT": 0}, "v1 backup imports")
    d = imp("b3.json", {"app": "daily-tracker", "version": 3, "days": {today: {"v": {"nasya": {"n": 1, "t": 5}}, "note": "x", "noteT": 6}}})
    check(d == {"v": {"nasya": {"n": 1, "t": 5}}, "note": "x", "noteT": 6}, "v3 backup imports with timestamps")
    pg.click("#vWeek")
    check(pg.locator('.wk tr:has(td.it[title="Nasya"]) i.m[data-s="1"]').count() == 1, "week view reads v3 values")
    pg.click("#vDay")

    # ---------- sync: Gist adapter (works from file://; /api/data does not) ----------
    gist = {"auth": None, "patch": None, "status": 200}
    def gist_route(route):
        cors = {"Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "authorization, accept, content-type",
                "Access-Control-Allow-Methods": "GET, PATCH"}
        r = route.request
        if r.method == "OPTIONS":
            return route.fulfill(status=204, headers=cors)
        gist["auth"] = r.headers.get("authorization")
        if gist["status"] != 200:
            return route.fulfill(status=gist["status"], headers=cors, content_type="application/json", body='{"message":"Bad credentials"}')
        if r.method == "PATCH":
            gist["patch"] = json.loads(json.loads(r.post_data)["files"]["tracker.json"]["content"])
            return route.fulfill(status=200, headers=cors, content_type="application/json", body="{}")
        route.fulfill(status=200, headers=cors, content_type="application/json",
                      body=json.dumps({"files": {"tracker.json": {"content": "{}", "truncated": False}}}))
    pg.route("https://api.github.com/gists/**", gist_route)

    def wait_s3(page, prefix):
        page.wait_for_function(f"document.getElementById('s3').textContent.startsWith({json.dumps(prefix)})")

    def sync_now(page, prefix="Synced"):
        page.evaluate("document.getElementById('s3').textContent = ''")
        page.click("#s3")
        wait_s3(page, prefix)

    pg.click("#set")
    check(pg.is_disabled('input[name="sm"][value="api"]'), "file://: /api/data sync not offered")
    pg.check('input[name="sm"][value="gist"]')
    pg.fill("#gId", "https://gist.github.com/me/0123456789abcdef0123")
    pg.click("#sOk")
    check("Gist ID" in pg.inner_text("#sErr") and pg.is_visible("#sdlg"), "Gist settings need a token")
    pg.fill("#gTok", "tok123")
    pg.click("#sOk")
    wait_s3(pg, "Synced")
    check(gist["auth"] == "Bearer tok123", "Gist requests carry the token")
    check(gist["patch"] and gist["patch"]["version"] == 3 and gist["patch"]["days"][today]["v"]["nasya"] == {"n": 1, "t": 5},
          "Gist push uploads local data (ID taken from a pasted URL)")
    gist["status"] = 401
    sync_now(pg, "Sync error")
    check("401" in pg.get_attribute("#s3", "title"), "Gist auth failure shows Sync error with detail")
    pg.click("#set"); pg.check('input[name="sm"][value="off"]'); pg.click("#sOk")
    check(pg.inner_text("#s3").startswith(("Saved", "Ready", "Imported")), "sync off restores the plain status")

    # ---------- config loading from habits.yaml (served over http) ----------
    srv, BASE = serve_public()
    hp = browser.new_page(viewport={"width": 420, "height": 900})
    hp.on("pageerror", lambda e: errors.append(str(e)))
    mode = {"m": "real"}

    def yaml_route(route):
        if mode["m"] == "real":
            route.continue_()
        elif mode["m"] == "abort":
            route.abort()
        else:
            route.fulfill(status=200, content_type="text/yaml; charset=utf-8", body=mode["m"])
    hp.route("**/habits.yaml", yaml_route)
    cached = lambda: hp.evaluate("localStorage.getItem('dailyTracker.deployed')")
    cfg_cell = lambda: hp.inner_text("#sCfg") if hp.is_visible("#sCfg") else ""

    hp.goto(BASE)
    hp.wait_for_function("localStorage.getItem('dailyTracker.deployed') !== null")
    real = (PUBLIC / "habits.yaml").read_text(encoding="utf-8").replace("\r\n", "\n")
    check(cached() == real, "deployed habits.yaml fetched and cached")
    check(cfg_cell() == "", "no config status when using deployed")

    mode["m"] = DEPLOYED
    hp.reload()
    hp.wait_for_selector('[data-row="zz"]')
    check("zz:" in cached() and "\r" not in cached(), "changed habits.yaml applied, cached with LF")

    mode["m"] = "groups:\n  A:\n    x: {name: X, cnt: 3}\n"
    hp.reload()
    hp.wait_for_function("document.getElementById('sCfg').textContent.startsWith('Config error')")
    check('unknown option "cnt"' in cfg_cell(), "invalid habits.yaml reported in status bar")
    check(hp.is_visible('[data-row="zz"]') and "zz:" in cached(), "invalid habits.yaml keeps last valid config")

    mode["m"] = "groups:\n  A: [nasya,\n"
    hp.reload()
    hp.wait_for_function("document.getElementById('sCfg').textContent.startsWith('Config error')")
    check(re.search(r"\(\d+:\d+\)", cfg_cell()), "YAML syntax error shows line number")

    mode["m"] = "abort"
    hp.reload()
    hp.wait_for_timeout(300)
    check(hp.is_visible('[data-row="zz"]') and cfg_cell() == "", "offline: cached config used, no error")

    # Local override
    mode["m"] = DEPLOYED
    hp.reload()
    hp.click("#edit")
    check(not hp.is_visible("#cfgUse"), "Use deployed hidden without an override")
    hp.click("#cfgOk")
    check(hp.evaluate("localStorage.getItem('dailyTracker.override')") is None, "OK on unchanged deployed config adds no override")
    hp.click("#edit")
    hp.fill("#cfg", LOCAL)
    hp.click("#cfgOk")
    check(cfg_cell() == "Config: local" and hp.is_visible('[data-row="yy"]'), "local override applied, status shows Config: local")
    hp.reload()
    hp.wait_for_timeout(300)
    check(hp.is_visible('[data-row="yy"]') and cfg_cell() == "Config: local", "override survives reload over deployed")
    hp.click("#edit")
    check("local override" in hp.inner_text("#dlgT"), "editor marks the local override")
    hp.click("#cfgUse")
    check(not hp.is_visible('[data-row="yy"]') and hp.is_visible('[data-row="zz"]') and cfg_cell() == "",
          "Use deployed drops the override")
    check(hp.evaluate("localStorage.getItem('dailyTracker.override')") is None, "override removed from storage")

    # Config no longer stored with data; old stored config migrates to an override
    check("yaml" not in json.loads(hp.evaluate("localStorage.getItem('dailyTracker.v3')") or "{}"), "config not saved with data")
    hp.evaluate("""([y, t]) => { localStorage.removeItem('dailyTracker.override'); localStorage.removeItem('dailyTracker.v3');
        localStorage.setItem('dailyTracker.v2', JSON.stringify({yaml: y, days: {[t]: {v: {ww: 1}}}, lastBackup: null})); }""", [LEGACY, today])
    hp.reload()
    hp.wait_for_selector('[data-row="ww"]')
    check(hp.get_attribute('[data-row="ww"] button.dot', "data-s") == "1", "legacy stored config kept as override with data")
    check(hp.evaluate("localStorage.getItem('dailyTracker.override')") == LEGACY, "legacy config moved to override key")
    check("yaml" not in json.loads(hp.evaluate("localStorage.getItem('dailyTracker.v3')")), "legacy yaml not carried into v3")
    hp.evaluate("""() => { localStorage.removeItem('dailyTracker.override'); localStorage.removeItem('dailyTracker.v3');
        localStorage.setItem('dailyTracker.v2', JSON.stringify({yaml: document.getElementById('defaultYaml').textContent, days: {}, lastBackup: null})); }""")
    hp.reload()
    hp.wait_for_timeout(300)
    check(hp.evaluate("localStorage.getItem('dailyTracker.override')") is None, "stored default config is not turned into an override")
    # ---------- sync: two devices through /api/data ----------
    remote = {"body": "{}", "mode": "ok"}

    def api_route(route):
        m = remote["mode"]
        if m == "abort":
            return route.abort()
        if m == "login":
            return route.fulfill(status=302, headers={"location": "https://team.cloudflareaccess.com/cdn-cgi/access/login"})
        if m == "500":
            return route.fulfill(status=500, body="boom")
        if route.request.method == "PUT":
            remote["body"] = route.request.post_data
            return route.fulfill(status=204)
        route.fulfill(status=200, content_type="application/json", headers={"cache-control": "no-store"}, body=remote["body"])

    def device():
        ctx = browser.new_context(viewport={"width": 420, "height": 900})
        ctx.route("**/api/data", api_route)
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(BASE)
        return page

    def enable_api(page):
        page.click("#set"); page.check('input[name="sm"][value="api"]'); page.click("#sOk")
        wait_s3(page, "Synced")
    rdays = lambda: json.loads(remote["body"]).get("days", {})
    dot = lambda page, id: page.get_attribute(f'[data-row="{id}"] button.dot', "data-s")

    A, B = device(), device()
    enable_api(A)
    A.locator('[data-row="nasya"] button.dot').click()
    sync_now(A)
    check(rdays()[today]["v"]["nasya"]["n"] == 1, "device A pushes to /api/data")
    enable_api(B)
    check(dot(B, "nasya") == "1", "device B pulls A's change")

    # Merge of two diverging copies
    remote["body"] = "{}"
    DA = {today: {"v": {"nasya": {"n": 2, "t": 100}, "water": {"n": 1, "t": 300}, "yoga": {"n": 1, "t": 0}}, "note": "from A", "noteT": 50}}
    DB = {today: {"v": {"nasya": {"n": 1, "t": 200}, "water": {"n": 3, "t": 100}, "greens": {"n": 2, "t": 10}, "yoga": {"n": 2, "t": 0}},
                  "note": "from B", "noteT": 60},
          "2026-01-01": {"v": {"nasya": {"n": 2, "t": 5}}}}
    for page, d in ((A, DA), (B, DB)):
        page.evaluate("d => localStorage.setItem('dailyTracker.v3', JSON.stringify({days: d, lastBackup: null}))", d)
        page.reload()
        wait_s3(page, "Synced")
    sync_now(A)
    want = {today: {"v": {"nasya": {"n": 1, "t": 200}, "water": {"n": 1, "t": 300}, "greens": {"n": 2, "t": 10}, "yoga": {"n": 2, "t": 0}},
                    "note": "from B", "noteT": 60},
            "2026-01-01": {"v": {"nasya": {"n": 2, "t": 5}}}}
    check(v3(A)["days"] == want and v3(B)["days"] == want and rdays() == want,
          "diverging copies merge per habit by t (ties: higher n), note by noteT")
    check(dot(A, "nasya") == "1" and A.input_value("#note") == "from B", "merged result shown on screen")

    # A clear propagates
    A.locator('[data-row="nasya"] button.dot').click()   # 1 -> 2
    A.locator('[data-row="nasya"] button.dot').click()   # 2 -> 0
    sync_now(A); sync_now(B)
    check(dot(B, "nasya") == "0" and v3(B)["days"][today]["v"]["nasya"]["n"] == 0, "a cleared value propagates")

    # Debounced push, 5 s after the last change
    A.locator('[data-row="nasya"] button.dot').click()
    A.wait_for_timeout(2000)
    check(rdays()[today]["v"]["nasya"]["n"] == 0, "no push before the pause")
    A.wait_for_timeout(4500)
    check(rdays()[today]["v"]["nasya"]["n"] == 1, "push 5 s after the last change")

    # Pull when the app comes back to the foreground
    d = rdays(); d[today]["v"]["nasya"] = {"n": 2, "t": 9e12}
    remote["body"] = json.dumps({"days": d})
    B.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    B.wait_for_function("document.querySelector('[data-row=nasya] button.dot').dataset.s === '2'")
    check(True, "foreground pull applies remote changes")

    # Status states
    for mode, prefix, msg in (("abort", "Offline", "network failure shows Offline"),
                              ("login", "Sync: sign in", "Access login redirect shows Sync: sign in"),
                              ("500", "Sync error", "server error shows Sync error"),
                              ("ok", "Synced", "recovers to Synced")):
        remote["mode"] = mode
        sync_now(B, prefix)
        check(True, msg)
    B.locator('[data-row="greens"] button.dot').click()
    remote["mode"] = "abort"
    sync_now(B, "Offline")
    check(dot(B, "greens") != "0", "tracking keeps working while sync fails")
    remote["mode"] = "ok"

    srv.shutdown()

    check(not errors, "no page errors")
    browser.close()
