"""把 avatar.html 的三個草稿各存成 512x512 PNG，另存一張圓形裁切的對照圖。
用法：.venv\\Scripts\\python.exe design\\avatar\\render.py
（無頭 Edge，不會在桌面開視窗）"""
from pathlib import Path
from playwright.sync_api import sync_playwright

here = Path(__file__).parent
KEYS = "ab"
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 1700, "height": 1200})
    pg.goto((here / "avatar.html").as_uri())
    pg.wait_for_timeout(300)
    for k in KEYS:
        pg.locator(f"#{k}").screenshot(path=str(here / f"avatar_{k}.png"))
    # 對照圖：微信會把頭像裁成圓形
    imgs = "".join(
        f'<div><img src="{(here / f"avatar_{k}.png").as_uri()}" style="width:200px;height:200px;border-radius:50%"><br>'
        f'<img src="{(here / f"avatar_{k}.png").as_uri()}" style="width:48px;height:48px;border-radius:50%;margin-top:16px"><p>{k.upper()}</p></div>'
        for k in KEYS)
    pg.set_content('<body style="margin:0;padding:24px;background:#ededed;font:20px sans-serif;display:flex;gap:40px;text-align:center">'
                   + imgs + "</body>")
    pg.wait_for_timeout(300)
    pg.set_viewport_size({"width": 760, "height": 360})
    pg.screenshot(path=str(here / "preview_round.png"))
    b.close()
print("ok")
