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

    # v1 -> v2 migration
    pg.goto(URL)
    today = pg.evaluate("(d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`)(new Date())")
    V1["days"] = {today: V1["days"]["TODAY"]}
    pg.evaluate("v => { localStorage.clear(); localStorage.setItem('dailyTracker.v1', JSON.stringify(v)); }", V1)
    pg.reload()
    days = pg.evaluate("JSON.parse(localStorage.getItem('dailyTracker.v2')).days")
    check(days[today]["v"] == {"yoga": 2, "water": 3, "pcf": 1, "miles": 3.5}, "v1 data migrated")

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
    check("yaml" not in json.loads(hp.evaluate("localStorage.getItem('dailyTracker.v2')") or "{}"), "config not saved with data")
    hp.evaluate("""([y, t]) => { localStorage.removeItem('dailyTracker.override');
        localStorage.setItem('dailyTracker.v2', JSON.stringify({yaml: y, days: {[t]: {v: {ww: 1}}}, lastBackup: null})); }""", [LEGACY, today])
    hp.reload()
    hp.wait_for_selector('[data-row="ww"]')
    check(hp.get_attribute('[data-row="ww"] button.dot', "data-s") == "1", "legacy stored config kept as override with data")
    check(hp.evaluate("localStorage.getItem('dailyTracker.override')") == LEGACY, "legacy config moved to override key")
    check("yaml" not in json.loads(hp.evaluate("localStorage.getItem('dailyTracker.v2')")), "legacy yaml removed from data")
    hp.evaluate("""() => { localStorage.removeItem('dailyTracker.override');
        localStorage.setItem('dailyTracker.v2', JSON.stringify({yaml: document.getElementById('defaultYaml').textContent, days: {}, lastBackup: null})); }""")
    hp.reload()
    hp.wait_for_timeout(300)
    check(hp.evaluate("localStorage.getItem('dailyTracker.override')") is None, "stored default config is not turned into an override")
    srv.shutdown()

    check(not errors, "no page errors")
    browser.close()
