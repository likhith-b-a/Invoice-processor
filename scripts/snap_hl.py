"""Dev helper: open a run, go to extraction stage, click a field, screenshot."""
import sys
from playwright.sync_api import sync_playwright
out, run_id, field = sys.argv[1], sys.argv[2], sys.argv[3]
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1600, "height": 1000})
    pg.goto(f"http://127.0.0.1:8000/runs/{run_id}")
    pg.wait_for_timeout(1500)
    pg.get_by_role("button", name="Field extraction").click()
    pg.wait_for_timeout(500)
    pg.get_by_title("Show on page").filter(has_text=field).first.click()
    pg.wait_for_timeout(1500)
    pg.screenshot(path=out, full_page=False)
    b.close()
