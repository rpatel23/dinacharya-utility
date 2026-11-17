"""Render the Win98-style app icons into public/ (192, 512, and the 180 apple-touch icon). Run: python tools/make_icons.py"""
import sys
from playwright.sync_api import sync_playwright

# 64-unit pixel grid, drawn with crisp edges: teal desktop, grey beveled window, navy title bar,
# a sunken white panel with tracker circles (max = orange, min = yellow, missed = white).
SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="{s}" height="{s}" shape-rendering="crispEdges">
  <rect width="64" height="64" fill="#008080"/>
  <rect x="9" y="11" width="46" height="42" fill="#000"/>
  <rect x="9" y="11" width="45" height="41" fill="#DFDFDF"/>
  <rect x="10" y="12" width="44" height="40" fill="#808080"/>
  <rect x="10" y="12" width="43" height="39" fill="#FFF"/>
  <rect x="11" y="13" width="42" height="38" fill="#C0C0C0"/>
  <defs><linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#000080"/><stop offset="1" stop-color="#1084D0"/></linearGradient></defs>
  <rect x="12" y="14" width="40" height="7" fill="url(#g)"/>
  <rect x="45" y="15" width="5" height="5" fill="#C0C0C0"/>
  <rect x="45" y="15" width="5" height="1" fill="#FFF"/><rect x="45" y="15" width="1" height="5" fill="#FFF"/>
  <rect x="14" y="16" width="14" height="2" fill="#FFF" opacity=".85"/>
  <rect x="13" y="23" width="38" height="26" fill="#808080"/>
  <rect x="14" y="24" width="37" height="25" fill="#FFF"/>
  <g shape-rendering="geometricPrecision" stroke="#000" stroke-width="1">
    <circle cx="22" cy="31" r="4.5" fill="#FF7F27"/>
    <circle cx="32.5" cy="31" r="4.5" fill="#FF7F27"/>
    <circle cx="43" cy="31" r="4.5" fill="#FFD000"/>
    <circle cx="22" cy="42" r="4.5" fill="#FFD000"/>
    <circle cx="32.5" cy="42" r="4.5" fill="#FFF"/>
    <circle cx="43" cy="42" r="4.5" fill="#FF7F27"/>
  </g>
</svg>"""

out = sys.argv[1] if len(sys.argv) > 1 else str(__import__("pathlib").Path(__file__).resolve().parent.parent / "public")
with sync_playwright() as p:
    b = p.chromium.launch()
    for name, s in (("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)):
        pg = b.new_page(viewport={"width": s, "height": s})
        pg.set_content(f"<html><body style='margin:0'>{SVG.format(s=s)}</body></html>")
        pg.screenshot(path=f"{out}/{name}", clip={"x": 0, "y": 0, "width": s, "height": s})
        pg.close()
    b.close()
