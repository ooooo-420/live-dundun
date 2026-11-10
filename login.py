"""第一次使用：打開監控專用的 Edge，讓你登入抖音。登入後關掉視窗即可，登入狀態會保留。

    .venv\\Scripts\\python.exe login.py
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

PROFILE = Path(__file__).with_name("browser-profile")


async def main() -> None:
    async with async_playwright() as p:
        ctx = await p.chromium.launch_persistent_context(str(PROFILE), channel="msedge", headless=False,
                                                        viewport={"width": 1400, "height": 850})
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto("https://www.douyin.com/", wait_until="domcontentloaded", timeout=60000)
        print("請在打開的 Edge 視窗登入抖音，登入完成後直接關掉那個視窗。", flush=True)
        closed = asyncio.Event()
        ctx.on("close", lambda _: closed.set())
        await closed.wait()
        print("視窗已關閉，登入狀態已存在 browser-profile。")


asyncio.run(main())
