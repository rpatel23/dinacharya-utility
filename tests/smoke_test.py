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
V1 = {"config": [], "days": {"TODAY": {"v": {"water": [1, 1, 1, 0, 0, 0], "yoga": [2], "pcf": [1], "sff": [2]},
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
    check(days[today]["v"] == {k: {"n": n, "t": 0} for k, n in {"yoga": 2, "water": 3, "pcf": 1, "sff": 2, "miles": 3.5}.items()}
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
                        ("groups:\n  A:\n    x: {name: X, count: 5, min: 4, max: 3}\n", "min > max"),
                        ("groups:\n  A:\n    x: {name: X, count: 3, min: 4}\n", "min > count"),
                        ("groups:\n  A:\n    x: {name: X, count: 3, min: 1, max: 4}\n", "max > count"),
                        ("groups:\n  A:\n    x: {name: X, count: 3, max: 2}\n", "max needs min"),
                        ("groups:\n  A:\n    x: {name: X, value: mi, max: 5}\n", "max needs min"),
                        ("groups:\n  A:\n    x: {name: X, days: tu}\n", 'unknown day "tu"'),
                        ("groups:\n  A:\n    x: {name: X, every: 2}\n", "every needs a start date"),
                        ("groups:\n  A:\n    x: {name: X, avoid: true, count: 3}\n", "avoid habits are pass/fail; remove count"),
                        ("groups:\n  A:\n    x: {name: X, avoid: true, value: mi}\n", "avoid habits are pass/fail; remove value"),
                        ("groups:\n  A:\n    x: {name: X, avoid: true, min: a}\n", "avoid habits are pass/fail; remove min"),
                        ("groups:\n  A:\n    x: {name: X, avoid: true, max: b}\n", "avoid habits are pass/fail; remove max"),
                        ("groups:\n  A:\n    x: {name: X, avoid: true, show: one}\n", "avoid habits are pass/fail; remove show"),
                        ("groups:\n  A:\n    x: {name: X, avoid: yes}\n", "avoid is true or false")]:
        pg.fill("#cfg", bad)
        pg.click("#cfgOk")
        check(expect in pg.inner_text("#cfgErr"), f"rejects config: {expect}")
    pg.click("#cfgNo")

    # ---------- v3 data: timestamps ----------
    d = v3(pg)["days"][today]
    check(d["v"]["nasya"]["n"] == 1 and d["v"]["nasya"]["t"] > 1e12, "edit stores {n, t}")
    check(d["v"]["yoga"] == {"n": 2, "t": 0}, "untouched migrated value keeps t = 0")
    pg.locator('[data-row="nasya"] button.dot').click()     # plain check: done -> blank
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
    check(pg.get_attribute('[data-row="nasya"] button.dot', "data-s") == "1", "migrated v2 value shown (old 2 reads as done)")

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

    check(pg.evaluate("!navigator.serviceWorker || navigator.serviceWorker.getRegistrations().then(r => r.length === 0, () => true)"),
          "file://: no service worker registered")

    # ---------- avoid habits (issue #2) ----------
    pg.evaluate("localStorage.removeItem('dailyTracker.v3')"); pg.reload()
    adot = lambda id: pg.get_attribute(f'[data-row="{id}"] button.dot', "data-s")
    score = lambda: [int(x) for x in re.match(r"(\d+)/(\d+)(?: · (\d+) max)?", pg.inner_text("#prog")).group(1, 3, 2)]
    check(adot("nsm") == "0" and pg.is_visible(".key .kav"), "avoid habit starts blank; legend shows clean/failed")
    base = score()
    seq = []
    for _ in range(3):
        pg.locator('[data-row="nsm"] button.dot').click()
        seq.append((adot("nsm"), v3(pg)["days"][today]["v"]["nsm"]["n"], score()))
    check([x[:2] for x in seq] == [("ok", 1), ("x", -1), ("0", 0)], "avoid cycles blank -> clean -> failed -> blank (n 1, -1, 0)")
    check(v3(pg)["days"][today]["v"]["nsm"]["t"] > 1e12, "avoid clear keeps {n: 0, t}")
    check(seq[0][2] == [base[0] + 1, base[1], base[2]], "clean scores as min, never max")
    check(seq[1][2] == base and seq[2][2] == base, "failed and blank score as missed")
    check(pg.get_attribute('[data-row="nsm"] button.dot', "aria-label") == "No social media: blank", "avoid aria-label")
    # an old check value (1 or 2) reads as clean after switching the habit to avoid
    pg.evaluate("d => localStorage.setItem('dailyTracker.v3', JSON.stringify({days: d, lastBackup: null}))",
                {today: {"v": {"sff": {"n": 2, "t": 0}, "nsm": {"n": -1, "t": 1}}}})
    pg.reload()
    check(adot("sff") == "ok" and adot("nsm") == "x", "stored 2 reads as clean, -1 as failed")
    pg.locator('[data-row="sff"] button.dot').click()
    check(v3(pg)["days"][today]["v"]["sff"]["n"] == -1, "clean (old 2) -> failed on next tap")
    # week view
    pg.click("#vWeek")
    row = pg.locator('.wk tr:has(td.it[title="No social media"])')
    check(row.locator('i.m[data-s="x"]').count() == 1 and row.locator(".mn").count() == 0, "week view shows failed in red, no number")
    tot = row.locator("td.tot").inner_text()
    check(re.fullmatch(r"0/7", tot), "week total counts clean days of scheduled days")
    check(row.locator('td[title="No social media: failed"]').count() == 1, "week cell title says failed")
    pg.click("#vDay")
    # export / import keep -1
    with pg.expect_download() as dl:
        pg.click("#exp")
    b = json.loads(pathlib.Path(dl.value.path()).read_text(encoding="utf-8"))
    check(b["days"][today]["v"]["nsm"] == {"n": -1, "t": 1}, "export keeps failed (-1)")
    d = imp("av.json", {"app": "daily-tracker", "version": 3, "days": {today: {"v": {"nsm": {"n": -1, "t": 7}}}}})
    check(d["v"]["nsm"] == {"n": -1, "t": 7} and adot("nsm") == "x", "import keeps failed (-1)")
    # per_week with avoid counts clean days; legend hidden without avoid habits
    pg.click("#vWeek")
    ks = [pg.get_attribute(f".wk thead th:nth-child({i}) button", "data-go") for i in (2, 3, 4)]
    pg.click("#vDay")
    pg.evaluate("d => localStorage.setItem('dailyTracker.v3', JSON.stringify({days: d, lastBackup: null}))",
                {ks[0]: {"v": {"q": {"n": 1, "t": 1}}}, ks[1]: {"v": {"q": {"n": -1, "t": 1}}}, ks[2]: {"v": {"q": {"n": 1, "t": 1}}}})
    pg.evaluate("localStorage.setItem('dailyTracker.override', 'groups:\\n  A:\\n    q: {name: Q, avoid: true, per_week: 2}\\n')")
    pg.reload()
    check("2 of 2 this week" in pg.inner_text('[data-row="q"]'), "per_week avoid counts clean days only")
    pg.evaluate("localStorage.setItem('dailyTracker.override', 'groups:\\n  A:\\n    nasya: Nasya\\n')")
    pg.reload()
    check(not pg.is_visible(".key .kav"), "legend hides clean/failed without avoid habits")
    pg.evaluate("localStorage.removeItem('dailyTracker.override')")
    pg.reload()


    # ---------- max is optional extra credit (issue #3) ----------
    CFG3 = ("groups:\\n  A:\\n    c2: {name: C2}\\n    c3: {name: C3, max: extra}\\n"
            "    k1: {name: K1, count: 3, min: 2}\\n    k2: {name: K2, count: 3, min: 2, max: 3}\\n"
            "    v1: {name: V1, value: mi, min: 2}\\n")
    pg.evaluate("d => localStorage.setItem('dailyTracker.v3', JSON.stringify({days: d, lastBackup: null}))",
                {today: {"v": {"c2": {"n": 2, "t": 1}, "k1": {"n": 3, "t": 1}, "k2": {"n": 3, "t": 1}, "v1": {"n": 5, "t": 1}}}})
    pg.evaluate(f"localStorage.setItem('dailyTracker.override', '{CFG3}')")
    pg.reload()
    sh = lambda id: pg.get_attribute(f'[data-row="{id}"] .dot', "data-s")
    crit = lambda id: pg.inner_text(f'[data-row="{id}"] .crit') if pg.locator(f'[data-row="{id}"] .crit').count() else ""
    check(pg.inner_text("#prog").endswith("4/5 · 1 max · 80%"), "Day % counts min; only habits with a max add to max")
    check(sh("c2") == "1", "stored 2 on a check without max shows as done")
    pg.locator('[data-row="c2"] button.dot').click()
    a = v3(pg)["days"][today]["v"]["c2"]["n"]
    pg.locator('[data-row="c2"] button.dot').click()
    b = v3(pg)["days"][today]["v"]["c2"]["n"]
    check((a, b) == (0, 1), "check without max: old 2 clears in one tap, then toggles 0 <-> 1")
    seq = []
    for _ in range(3):
        pg.locator('[data-row="c3"] button.dot').click(); seq.append(sh("c3"))
    check(seq == ["1", "2", "0"], "check with max text (no min text) cycles missed -> min -> max")
    check(crit("c3") == "max: extra" and crit("c2") == "", "criteria shows only the text that is set")
    check(sh("k1") == "1" and sh("k2") == "2", "counter reaches max only when max is written")
    check(pg.get_attribute('[data-row="v1"] span.dot', "data-s") == "1", "number entry with min only never reaches max")
    check(crit("k1") == "goal 2" and crit("k2") == "min 2 · max 3" and crit("v1") == "goal 2 mi", "criteria: goal without max")
    pg.evaluate("localStorage.setItem('dailyTracker.override', 'groups:\\n  A:\\n    c2: {name: C2}\\n    k1: {name: K1, count: 3, min: 2}\\n')")
    pg.reload()
    check(re.search(r"^\d+/2 · \d+%$", pg.inner_text("#prog").strip().splitlines()[-1]) and "max" not in pg.inner_text("#prog"),
          "day bar hides the max count when no habit has a max")
    pg.evaluate("localStorage.removeItem('dailyTracker.override')")
    pg.reload()
    for _ in range(4):
        pg.locator('[data-row="greens"] button.dot').click()
    w = pg.locator('[data-row="water"] button.dot')
    w.nth(5).click()
    check(pg.get_attribute('[data-row="greens"] button.dot', "data-s") == "1"
          and pg.locator('[data-row="water"] button.dot').nth(0).get_attribute("data-s") == "2",
          "habits.yaml: greens has no bonus, water keeps max 6")

    # ---------- out-of-range stored values after a config change (issue #6) ----------
    CFG6 = ("groups:\n  A:\n    k1: {name: K1, count: 4, min: 3, show: one}\n    k2: {name: K2, count: 4, min: 3}\n"
            "    k3: {name: K3, count: 3, min: 2, show: one}\n    v1: {name: V1, value: mi}\n    v2: {name: V2, value: mi, min: 1}\n")
    D6 = {today: {"v": {"k1": {"n": 6, "t": 1}, "k2": {"n": 6, "t": 1}, "k3": {"n": -1, "t": 1}, "v1": {"n": -1, "t": 1}, "v2": {"n": -1, "t": 1}}}}
    def load6():
        pg.evaluate("([y, d]) => { localStorage.setItem('dailyTracker.override', y); localStorage.setItem('dailyTracker.v3', JSON.stringify({days: d, lastBackup: null})); }",
                    [CFG6, D6])
        pg.reload()
    stored = lambda id: v3(pg)["days"][today]["v"][id]["n"]
    load6()
    k1 = pg.locator('[data-row="k1"]')
    check(k1.locator(".unit").inner_text() == "4/4" and k1.locator("button.dot").inner_text() == "4" and stored("k1") == 6,
          "lowered count shows 4/4, stored 6 untouched")
    check([pg.locator('[data-row="k2"] button.dot').nth(i).get_attribute("data-s") for i in range(4)] == ["1"] * 4, "dots show a full counter")
    check(pg.locator('[data-row="k3"] .unit').inner_text() == "0/3" and pg.locator('[data-row="k3"] button.dot').inner_text() == "",
          "negative value on a counter shows 0")
    check(pg.input_value('[data-row="v1"] input') == "" and pg.input_value('[data-row="v2"] input') == ""
          and stored("v1") == -1 and stored("v2") == -1, "negative value on a number entry shows blank, stored -1 untouched")
    check(pg.get_attribute('[data-row="v2"] span.dot', "data-s") == "0", "negative number scores as missed, not partial")
    pg.click("#vWeek")
    wk = pg.inner_text(".wk")
    check("-1" not in wk and pg.inner_text('.wk tr:has(td.it[title="K1"]) .mn') == "4" and
          pg.inner_text('.wk tr:has(td.it[title="V1"]) td.tot') == "", "week view shows clamped values and no negative total")
    pg.click("#vDay")
    pg.locator('[data-row="k1"] button.dot').click()
    a = stored("k1")
    load6(); pg.locator('[data-row="k1"] button.dot').click(button="right")
    b = stored("k1")
    load6(); pg.locator('[data-row="k2"] button.dot').nth(3).click()
    c = stored("k2")
    load6(); pg.locator('[data-row="k3"] button.dot').click()
    d = stored("k3")
    check((a, b, c, d) == (0, 3, 3, 1), "taps act on the shown value: full -> 0, right-click -> 3, last dot -> 3, 0 -> 1")
    pg.evaluate("localStorage.removeItem('dailyTracker.override')")
    pg.reload()

    # ---------- config loading from habits.yaml (served over http) ----------
    srv, BASE = serve_public()
    hp = browser.new_page(viewport={"width": 420, "height": 900}, service_workers="block")
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
        ctx = browser.new_context(viewport={"width": 420, "height": 900}, service_workers="block")
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
    A.locator('[data-row="nasya"] button.dot').click()   # done -> blank
    sync_now(A); sync_now(B)
    check(dot(B, "nasya") == "0" and v3(B)["days"][today]["v"]["nasya"]["n"] == 0, "a cleared value propagates")

    # Avoid habit: clean, then failed later, reaches the other device
    A.locator('[data-row="nsm"] button.dot').click()      # clean
    sync_now(A); sync_now(B)
    check(dot(B, "nsm") == "ok", "avoid clean syncs")
    A.locator('[data-row="nsm"] button.dot').click()      # failed, later t
    sync_now(A); sync_now(B)
    check(dot(B, "nsm") == "x" and v3(B)["days"][today]["v"]["nsm"]["n"] == -1 and rdays()[today]["v"]["nsm"]["n"] == -1,
          "avoid failed (-1) syncs and wins over the older clean")

    # Debounced push, 5 s after the last change
    A.locator('[data-row="nasya"] button.dot').click()
    A.wait_for_timeout(2000)
    check(rdays()[today]["v"]["nasya"]["n"] == 0, "no push before the pause")
    A.wait_for_timeout(4500)
    check(rdays()[today]["v"]["nasya"]["n"] == 1, "push 5 s after the last change")

    # Pull when the app comes back to the foreground
    d = rdays(); d[today]["v"]["nasya"] = {"n": 1, "t": 9e12}
    remote["body"] = json.dumps({"days": d})
    B.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    B.wait_for_function("document.querySelector('[data-row=nasya] button.dot').dataset.s === '1'")
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

    # ---------- PWA: manifest, icons, service worker ----------
    ctx = browser.new_context(viewport={"width": 420, "height": 900})
    wp = ctx.new_page()
    wp.on("pageerror", lambda e: errors.append(str(e)))
    wp.goto(BASE)
    wp.evaluate("navigator.serviceWorker.ready")
    wp.reload()
    check(wp.evaluate("!!navigator.serviceWorker.controller"), "service worker registered and controls the page")
    shell = wp.evaluate("caches.open('tracker-v1').then(c => c.keys()).then(k => k.map(r => new URL(r.url).pathname))")
    check(len(shell) == 7 and "/habits.yaml" in shell and "/apple-touch-icon.png" in shell, "app shell cached (all 7 files exist)")
    m = wp.evaluate("fetch('manifest.webmanifest').then(r => r.json())")
    check(m["display"] == "standalone" and m["start_url"] == "./", "manifest is served and valid")
    sizes = wp.evaluate("""Promise.all(['icon-192.png', 'icon-512.png', 'apple-touch-icon.png'].map(src =>
        new Promise(ok => { const i = new Image(); i.onload = () => ok([i.naturalWidth, i.naturalHeight]); i.onerror = () => ok(null); i.src = src; })))""")
    check(sizes == [[192, 192], [512, 512], [180, 180]], "icons have the right sizes")
    check(wp.evaluate("document.querySelector('link[rel=manifest]').crossOrigin") == "use-credentials", "manifest link sends credentials (Access)")

    ctx.set_offline(True)
    wp.reload()
    wp.wait_for_selector('[data-row="nasya"]')
    check(not wp.is_visible("#sCfg"), "offline: app and habits.yaml load from the cache")
    ctx.set_offline(False)

    ctx.route("**/?signin=*", lambda r: r.fulfill(status=200, content_type="text/html", body="<title>Access login</title>"))
    wp.goto(BASE + "?signin=1")
    check(wp.title() == "Access login", "?signin navigation bypasses the cache and reaches the network")
    ctx.unroute("**/?signin=*")
    wp.goto(BASE + "?signin=2")
    wp.wait_for_selector('[data-row="nasya"]')
    check(wp.evaluate("location.search") == "", "app strips ?signin from the address")
    ctx.close()

    srv.shutdown()

    check(not errors, "no page errors")
    browser.close()
