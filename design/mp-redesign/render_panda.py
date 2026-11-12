from pathlib import Path
from playwright.sync_api import sync_playwright
here = Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1200, "height": 900})
    pg.goto((here / "panda.html").as_uri())
    pg.wait_for_timeout(3000)
    pg.screenshot(path=str(here / "panda.png"), full_page=True)
    b.close()
print("ok")
