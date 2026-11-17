"""Smoke test for public/index.html. Run: python tests/smoke_test.py"""
import pathlib
from playwright.sync_api import sync_playwright

URL = (pathlib.Path(__file__).resolve().parent.parent / "public" / "index.html").as_uri()
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

    check(not errors, "no page errors")
    browser.close()
