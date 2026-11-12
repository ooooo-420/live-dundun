"""第一次使用：打开监控专用的 Edge，让你登录抖音。登录后关掉窗口即可，登录状态会保留。

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
        print("请在打开的 Edge 窗口登录抖音，登录完成后直接关掉那个窗口。", flush=True)
        closed = asyncio.Event()
        ctx.on("close", lambda _: closed.set())
        await closed.wait()
        print("窗口已关闭，登录状态已存在 browser-profile。")


asyncio.run(main())
