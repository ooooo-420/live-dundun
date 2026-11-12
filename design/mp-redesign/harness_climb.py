"""開發用：首頁「監控關著」那支手機，把 asleep 拿掉，逐格截熊貓爬出來的過程，再加回去截縮回去。"""
import functools, http.server, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent
OUT = HERE / "climb"
OUT.mkdir(exist_ok=True)
Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
Handler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8799), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 2500, "height": 920})
    pg.goto("http://127.0.0.1:8799/design/mp-redesign/harness.html")
    pg.wait_for_function("document.title==='done'||document.title.startsWith('ERR')", timeout=30000)
    pg.wait_for_timeout(800)
    phone = pg.locator(".phone").first
    clip = phone.bounding_box()
    clip = {"x": clip["x"], "y": clip["y"], "width": clip["width"], "height": 420}
    frames = []
    pg.evaluate("document.querySelector('.phone .hero').classList.remove('asleep')")
    t = 0
    for ms in (0, 120, 260, 420, 600, 900):
        pg.wait_for_timeout(ms - t); t = ms
        f = OUT / f"up_{ms:04d}.png"; pg.screenshot(path=str(f), clip=clip); frames.append((f"打开 {ms}ms", f.name))
    pg.wait_for_timeout(400)
    pg.evaluate("document.querySelector('.phone .hero').classList.add('asleep')")
    t = 0
    for ms in (0, 200, 450, 800):
        pg.wait_for_timeout(ms - t); t = ms
        f = OUT / f"down_{ms:04d}.png"; pg.screenshot(path=str(f), clip=clip); frames.append((f"关闭 {ms}ms", f.name))
    html = "".join(f'<div style="display:inline-block;margin:4px;font:12px sans-serif">{l}<br><img src="{n}" style="width:230px"></div>' for l, n in frames)
    (OUT / "sheet.html").write_text(f'<body style="margin:0;background:#ccc;width:1200px">{html}</body>', encoding="utf-8")
    pg2 = b.new_page(viewport={"width": 1200, "height": 600})
    pg2.goto((OUT / "sheet.html").as_uri()); pg2.wait_for_timeout(500)
    pg2.screenshot(path=str(OUT / "sheet.png"), full_page=True)
    b.close()
srv.shutdown()
print("ok")
