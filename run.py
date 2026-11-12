"""启动监控：开专用 Edge + 本机设置网页。

    .venv\\Scripts\\python.exe run.py
然后用浏览器打开 http://127.0.0.1:8765 。按 Ctrl+C 结束。
"""

import asyncio
import os
import webbrowser

from aiohttp import web

from app import cloud
from app.monitor import Monitor
from app.web import make_app

HOST, PORT = "127.0.0.1", 8765


async def main() -> None:
    mon = Monitor()
    await mon.start()
    runner = web.AppRunner(make_app(mon))
    await runner.setup()
    await web.TCPSite(runner, HOST, PORT).start()
    url = f"http://{HOST}:{PORT}"
    print(f"监控已启动。设置网页：{url}  （按 Ctrl+C 结束）", flush=True)
    cfg = cloud.load_config()
    if cfg:
        sync = cloud.CloudSync(mon, cloud.Cloud(cfg))
        mon.cloud_sync = sync
        asyncio.create_task(sync.run())
        print("小程序同步：已打开（每 15 秒一次）", flush=True)
    else:
        print("小程序同步：没开。config.local.json 的 miniprogram 还没填。", flush=True)
    if not os.environ.get("NO_OPEN"):
        webbrowser.open(url)
    print("要结束监控：关掉这个黑色窗口，或双击 stop.bat。关掉 Edge 不会结束，会自动重开。", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("已结束。")
