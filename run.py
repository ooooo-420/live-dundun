"""啟動監控：開專用 Edge + 本機設定網頁。

    .venv\\Scripts\\python.exe run.py
然後用瀏覽器打開 http://127.0.0.1:8765 。按 Ctrl+C 結束。
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
    print(f"監控已啟動。設定網頁：{url}  （按 Ctrl+C 結束）", flush=True)
    cfg = cloud.load_config()
    if cfg:
        sync = cloud.CloudSync(mon, cloud.Cloud(cfg))
        mon.cloud_sync = sync
        asyncio.create_task(sync.run())
        print("小程序同步：已開啟（每 15 秒一次）", flush=True)
    else:
        print("小程序同步：沒開。config.local.json 的 miniprogram 還沒填。", flush=True)
    if not os.environ.get("NO_OPEN"):
        webbrowser.open(url)
    print("要結束監控：關掉這個黑色視窗，或雙擊 stop.bat。關掉 Edge 不會結束，會自動重開。", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("已結束。")
