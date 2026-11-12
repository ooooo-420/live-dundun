"""開發用：開一個本機伺服器（項目根目錄），用無頭 Edge 打開 harness.html，把五個頁面的模擬畫面截成一張圖。
用法：.venv\\Scripts\\python.exe design\\mp-redesign\\harness_run.py"""
import base64, functools, http.server, threading
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).parent

# 假的驗證截圖
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 340, "height": 280})
    pg.set_content('<body style="margin:0;background:#fff;font:14px sans-serif"><div style="padding:14px">請拖動滑塊完成拼圖</div>'
                   '<div style="margin:0 14px;height:150px;border-radius:8px;background:linear-gradient(135deg,#a6c4d8,#e8d3b5 60%,#c6a98a)"></div>'
                   '<div style="margin:16px 14px;height:40px;border-radius:20px;background:#eef0f2;position:relative">'
                   '<div style="position:absolute;left:0;width:52px;height:40px;border-radius:20px;background:#2f7bff"></div></div></body>')
    (HERE / "harness-shot.js").write_text('const SHOT="' + base64.b64encode(pg.screenshot(type="jpeg", quality=70)).decode() + '"', encoding="utf-8")
    b.close()

Handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
Handler.log_message = lambda *a: None
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8799), Handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 2100, "height": 920})
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:8799/design/mp-redesign/harness.html")
    pg.wait_for_function("document.title==='done'||document.title.startsWith('ERR')", timeout=30000)
    print("title", pg.title(), "errors", errs)
    pg.wait_for_timeout(1500)
    pg.screenshot(path=str(HERE / "harness.png"), full_page=True)
    b.close()
srv.shutdown()
