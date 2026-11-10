"""開發用探測：開一個直播間，測試讀取、全部載入和重新整理購物車。

    .venv\\Scripts\\python.exe probe.py <直播間網址>
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from app import douyin

PROFILE = Path(__file__).with_name("browser-profile")


def show(tag, s):
    exp = s.explaining_id
    idx = next((i["index"] for i in s.items if i["id"] == exp), None)
    print(f"[{tag}] ended={s.ended} cartBtn={s.has_cart_button} items={len(s.items)} "
          f"floating={'有' if s.floating else '無'} badge={s.badge and s.badge['index']} "
          f"explaining_index={idx} first={[i['index'] for i in s.items[:3]]} last={[i['index'] for i in s.items[-2:]]}")


async def main(url):
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(PROFILE), channel="msedge", headless=False,
                                                        viewport={"width": 1400, "height": 850})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)
        show("load", await douyin.scan(page))
        print("open_cart:", await douyin.open_cart(page))
        show("open", await douyin.scan(page))
        print("load_all:", await douyin.load_all(page))
        show("all", await douyin.scan(page))
        await douyin.close_cart(page)
        show("esc", await douyin.scan(page))
        show("refresh", await douyin.refresh_cart(page))
        await ctx.close()


asyncio.run(main(sys.argv[1]))
