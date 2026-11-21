"""Dev helper: screenshot UI pages with the installed Edge.  usage: snap.py out_dir path[=name] ... [--dark] [--w=1440]"""
import sys
from playwright.sync_api import sync_playwright

out = sys.argv[1]
args = [a for a in sys.argv[2:] if not a.startswith("--")]
dark = "--dark" in sys.argv
w = int(next((a.split("=")[1] for a in sys.argv if a.startswith("--w=")), 1440))
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": w, "height": 1000}, color_scheme="dark" if dark else "light")
    for a in args:
        path, _, name = a.partition("=")
        pg.goto(f"http://127.0.0.1:8000{path}")
        pg.wait_for_timeout(2500)
        pg.screenshot(path=f"{out}/{name or 'page'}.png", full_page=True)
        print("saved", name)
    b.close()
