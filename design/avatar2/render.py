"""新版頭像草稿：每個存一張 1024 方圖，再拼一張圓形裁切（大／實際聊天列表大小）的對照圖。"""
from pathlib import Path
from playwright.sync_api import sync_playwright
here = Path(__file__).parent
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1700, "height": 600}, device_scale_factor=2)
    pg.goto((here / "avatar.html").as_uri())
    pg.wait_for_timeout(1500)
    for k in "abc":
        pg.locator(f"#{k}").screenshot(path=str(here / f"avatar_{k}.png"))
    cells = "".join(
        f'<div style="text-align:center;font:600 18px sans-serif"><img src="avatar_{k}.png" style="width:240px;height:240px;border-radius:50%"><br>'
        f'<img src="avatar_{k}.png" style="width:48px;height:48px;border-radius:50%;margin:14px 0 6px"><br>{k.upper()}</div>' for k in "abc")
    (here / "preview.html").write_text(f'<body style="margin:0;padding:30px;background:#ededed;display:flex;gap:56px">{cells}</body>', encoding="utf-8")
    pg2 = b.new_page(viewport={"width": 960, "height": 400})
    pg2.goto((here / "preview.html").as_uri()); pg2.wait_for_timeout(600)
    pg2.screenshot(path=str(here / "preview.png"))
    b.close()
print("ok")
