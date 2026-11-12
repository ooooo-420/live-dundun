"""启动监控：开专用 Edge + 本机设置网页。

    .venv\\Scripts\\python.exe run.py
然后用浏览器打开 http://127.0.0.1:8765 。按 Ctrl+C 结束。
"""

import asyncio
import os
import socket
import sys
import time
import webbrowser
from pathlib import Path

from aiohttp import web

from app import cloud
from app.monitor import Monitor
from app.web import make_app

HOST, PORT = "127.0.0.1", 8765
ROOT = Path(__file__).resolve().parent
# 在背景跑（pythonw，没有黑色窗口）时没有地方显示文字，改写进 logs/run.log
BACKGROUND = sys.stdout is None or os.environ.get("RUN_BACKGROUND") == "1"
if BACKGROUND:
    (ROOT / "logs").mkdir(exist_ok=True)
    _log = open(ROOT / "logs" / "run.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = _log
    print(f"\n==== {time.strftime('%Y-%m-%d %H:%M:%S')} 在背景启动 ====", flush=True)


def already_running() -> bool:
    """同一时间只能有一个监控程序（两个会抢同一个专用 Edge）。设置网页的端口被占了，就当作已经在跑。"""
    s = socket.socket()
    try:
        s.bind((HOST, PORT))
        return False
    except OSError:
        return True
    finally:
        s.close()


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
    if not os.environ.get("NO_OPEN") and not BACKGROUND:
        webbrowser.open(url)
    if BACKGROUND:
        print("在背景运行中。要结束：双击 stop.bat。", flush=True)
    else:
        print("要结束监控：关掉这个黑色窗口，或双击 stop.bat。关掉 Edge 不会结束，会自动重开。", flush=True)
    await asyncio.Event().wait()


if __name__ == "__main__":
    if already_running():
        print("监控程序已经在运行了，不用再开一个。", flush=True)
        if not BACKGROUND:
            time.sleep(4)
        sys.exit(0)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("已结束。")
