"""把 fonts.html（号码字体对照，字体从 Google Fonts 载入）截成 fonts.png。
用法：.venv\\Scripts\\python.exe design\\mp-redesign\\fonts_run.py"""
from pathlib import Path
from playwright.sync_api import sync_playwright

HERE = Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1500, "height": 900}, device_scale_factor=1.5)
    failed = []
    pg.on("requestfailed", lambda r: failed.append(r.url))
    pg.goto((HERE / "fonts.html").as_uri(), wait_until="networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(800)
    loaded = pg.evaluate("[...document.fonts].filter(f=>f.status==='loaded').map(f=>f.family)")
    print("loaded:", sorted(set(loaded)))
    print("failed:", failed)
    pg.screenshot(path=str(HERE / "fonts.png"), full_page=True)
    b.close()
