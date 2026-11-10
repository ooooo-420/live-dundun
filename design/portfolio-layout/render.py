from pathlib import Path
from playwright.sync_api import sync_playwright
here = Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 2900})
    pg.goto((here / "mock.html").as_uri())
    pg.wait_for_timeout(2500)
    for i, k in enumerate("ABC"):
        pg.locator(".mock").nth(i).screenshot(path=str(here / f"mock_{k}.png"))
    b.close()
print("ok")
