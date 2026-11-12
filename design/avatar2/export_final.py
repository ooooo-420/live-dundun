"""定稿 A（熊貓扒在竹青票上）：輸出 1024、512、144 三種尺寸到 final/。"""
from pathlib import Path
from playwright.sync_api import sync_playwright
here = Path(__file__).parent
out = here / "final"
out.mkdir(exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    for size in (1024, 512, 144):
        pg = b.new_page(viewport={"width": 1700, "height": 600}, device_scale_factor=size / 512)
        pg.goto((here / "avatar.html").as_uri())
        pg.wait_for_timeout(800)
        pg.locator("#a").screenshot(path=str(out / f"avatar_{size}.png"))
        pg.close()
    b.close()
for f in sorted(out.glob("*.png")):
    print(f.name, f.stat().st_size // 1024, "KB")
