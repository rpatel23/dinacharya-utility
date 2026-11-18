"""Test for tools/config_diff.py (issue #5). Run: python tests/config_diff_test.py"""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from config_diff import report  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok  ", msg)


BASE = """week_start: mon
groups:
  Nutrition:
    water:  {name: Water, note: 12 oz, count: 6, min: 4, max: 6}
    sff:    Saturated-fat free
    amp:    {name: AM protein, note: smoothie}
  Training:
    yoga:   {name: Yoga, days: mon tue thu fri}
    miles:  {name: Miles, value: mi}
    tonic:  {name: Tonic, days: weekdays, per_week: 3-4}
    no:     {name: No-op, note: "1:30"}
"""


def diff(new, old=BASE):
    return report(old, new, "a" * 40, "b" * 40)


def sections(r):
    return {k: k in r for k in ("🔴", "🟡", "🟢")}


real = (ROOT / "public" / "habits.yaml").read_text(encoding="utf-8")
check(report(real, real) == "", "identical files: no report")
check(diff(BASE.replace("name: Water,", "name: H2O,")) == "", "name change: no report")
check(diff(BASE.replace("note: 12 oz", "note: 16 oz")) == "", "note change: no report")
check(diff(BASE.replace("{name: Yoga, days: mon tue thu fri}", "{name: Yoga, days: [Mon, Tue, Thursday, fri]}")) == "",
      "same days written differently: no report")
moved = BASE.replace("    amp:    {name: AM protein, note: smoothie}\n", "").replace("  Training:\n", "  Training:\n    amp:    {name: AM protein, note: smoothie}\n")
r = diff(moved)
check("Only free changes" in r and not any(sections(r).values()), "group move: listed as free only")

r = diff(BASE.replace("{name: Water, note: 12 oz, count: 6, min: 4, max: 6}", "{name: Water, min: 4 glasses}"))
check(sections(r)["🔴"] and "`water`: kind counter → check" in r, "counter → check: split needed")
r = diff(BASE.replace("    sff:    Saturated-fat free", "    sff:    {name: Saturated-fat free, avoid: true}"))
check(not sections(r)["🔴"] and "kind check → avoid (safe pair" in r, "check → avoid: safe pair, not split")
r = diff(BASE.replace("value: mi}", "value: km}"))
check("`miles`: unit mi → km" in r and sections(r)["🔴"], "unit change: split needed")
r = diff(BASE.replace("    sff:    Saturated-fat free", "    satfat: Saturated-fat free"))
check("`sff` → `satfat` looks like a renamed id" in r and "removed `sff`" in r and "added `satfat`" in r, "id rename detected")

r = diff(BASE.replace("min: 4, max: 6", "min: 5, max: 6"))
check(sections(r) == {"🔴": False, "🟡": True, "🟢": False} and "`water`: min 4 → 5" in r, "threshold change: rescores")
r = diff(BASE.replace("count: 6, min: 4, max: 6", "count: 8, min: 4, max: 6"))
check("`water`: count 6 → 8" in r, "count change: rescores")
r = diff(BASE.replace("min: 4, max: 6}", "min: 4}"))
check("`water`: max 6 → none" in r, "max removed: rescores")
r = diff(BASE.replace("{name: AM protein, note: smoothie}", "{name: AM protein, note: smoothie, max: double}"))
check("`amp`: max text added" in r, "check max text added: rescores")
r = diff(BASE.replace("days: mon tue thu fri", "days: mon thu fri"))
check("`yoga`: days mon tue thu fri → mon thu fri" in r, "schedule change: rescores")
r = diff(BASE.replace("per_week: 3-4", "per_week: 4-5"))
check("`tonic`: per_week 3-4 → 4-5" in r, "per_week change: rescores")
r = diff(BASE.replace("week_start: mon", "week_start: sun"))
check("`week_start` mon → sun" in r, "week_start change: rescores")
r = diff(BASE + "    nsm:    {name: No social media, avoid: true}\n")
check(sections(r) == {"🔴": False, "🟡": False, "🟢": True} and "added `nsm` (Training)" in r, "added habit: info")
import yaml  # noqa: E402
from config_diff import CoreLoader, load  # noqa: E402
y = yaml.load("a: no\nb: 1:30\nc: 2026-11-22\nd: yes\ne: true\nf: 3.5", Loader=CoreLoader)
check(y == {"a": "no", "b": "1:30", "c": "2026-11-22", "d": "yes", "e": True, "f": 3.5} and "no" in load(BASE)["habits"],
      "YAML 1.2 core scalars: no/yes/1:30/dates stay text, like the app")

r = report("groups: [", BASE)
check("Could not compare" in r, "unparsable file: reported, not raised")
check(report("", BASE).count("added `") == 7, "first deploy (no old file): everything listed as added")

p = subprocess.run([sys.executable, str(ROOT / "tools" / "config_diff.py"), str(ROOT / "nope.yaml"), str(ROOT / "public" / "habits.yaml")],
                   capture_output=True, text=True, encoding="utf-8")
check(p.returncode == 0 and "habits.yaml changes" in p.stdout, "CLI runs on two files and exits 0")
