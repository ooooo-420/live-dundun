"""把 stubs.html（三格栏位＋票根草图）截成 stubs.png。用法：.venv\\Scripts\\python.exe design\\mp-redesign\\stubs_run.py"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1640, "height": 900}, device_scale_factor=1.4)
    pg.goto((HERE / "stubs.html").as_uri(), wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(600)
    pg.screenshot(path=str(HERE / "stubs.png"), full_page=True)
    b.close()
