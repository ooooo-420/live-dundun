"""本機設定網頁：http://127.0.0.1:8765（只綁本機，外面連不進來）。"""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

from .monitor import Monitor

STATIC = Path(__file__).resolve().parent / "static"
ROOT = Path(__file__).resolve().parent.parent

# 找出頁面上所有「看起來像商品」的 React props：記下 prop 名稱和欄位，看抖音這間用的是哪種結構
DEBUG_JS = r"""
() => {
  const fiberOf = el => { const k = Object.keys(el).find(k => k.startsWith('__reactFiber')); return k ? el[k] : null; };
  const shapes = {};
  let n = 0;
  for (const el of document.querySelectorAll('div')) {
    let f = fiberOf(el);
    for (let i = 0; i < 4 && f; i++, f = f.return) {
      const p = f.memoizedProps;
      if (!p || typeof p !== 'object') continue;
      for (const [k, v] of Object.entries(p)) {
        if (v && typeof v === 'object' && !Array.isArray(v) && (v.promotion_id || v.product_id || v.productId || v.promotionId)) {
          const key = k + ':' + Object.keys(v).slice(0, 25).join(',');
          if (!shapes[key]) shapes[key] = { prop: k, index: v.index, title: String(v.title || v.name || '').slice(0, 30), count: 0 };
          shapes[key].count++;
          n++;
        }
      }
    }
  }
  const leaves = [...document.querySelectorAll('div,span')].filter(e => e.children.length === 0);
  const texts = leaves.map(e => e.textContent.trim()).filter(t => /商品|购物|讲解|小黄车|登录|验证/.test(t) && t.length < 20);
  return { matches: n, shapes: Object.entries(shapes).slice(0, 15).map(([k, v]) => ({ keys: k, ...v })), texts: [...new Set(texts)].slice(0, 30), url: location.href };
}
"""


def make_app(mon: Monitor) -> web.Application:
    app = web.Application()

    async def index(_):
        return web.FileResponse(STATIC / "index.html")

    async def state(_):
        return web.json_response(mon.public())

    async def add_room(req):
        body = await req.json()
        try:
            rid = mon.add_room(body.get("url", ""))
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"id": rid})

    async def remove_room(req):
        await mon.remove_room(req.match_info["rid"])
        return web.json_response({"ok": True})

    async def cart(req):
        w = mon.workers.get(req.match_info["rid"])
        if not w:
            return web.json_response({"error": "沒有這個直播間"}, status=404)
        items = await w.load_cart_now()
        return web.json_response({"status": w.status, "items": items})

    async def targets(req):
        body = await req.json()
        try:
            mon.set_targets(req.match_info["rid"], body.get("targets", []))
        except (ValueError, KeyError) as e:
            return web.json_response({"error": str(e)}, status=400)
        return web.json_response({"ok": True})

    async def debug(req):
        """開發用：把直播間分頁截圖存到 logs/，並回報頁面上帶商品資料的 React props 長什麼樣子。只綁本機。"""
        w = mon.workers.get(req.match_info["rid"])
        if not w or not w.page:
            return web.json_response({"error": "沒有這個直播間"}, status=404)
        shot = ROOT / "logs" / f"debug_{w.rid}.png"
        async with w.lock:
            await w.page.screenshot(path=str(shot))
            info = await w.page.evaluate(DEBUG_JS)
        return web.json_response({"screenshot": str(shot), **info})

    async def test_push(_):
        try:
            await mon.test_push()
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({"ok": True})

    app.router.add_get("/", index)
    app.router.add_get("/api/state", state)
    app.router.add_post("/api/rooms", add_room)
    app.router.add_delete("/api/rooms/{rid}", remove_room)
    app.router.add_post("/api/rooms/{rid}/cart", cart)
    app.router.add_post("/api/rooms/{rid}/targets", targets)
    app.router.add_post("/api/test_push", test_push)
    app.router.add_get("/api/debug/{rid}", debug)

    async def pause(_):
        await mon.pause()
        return web.json_response({"ok": True, "paused": True})

    async def resume(_):
        await mon.resume()
        return web.json_response({"ok": True, "paused": False})

    app.router.add_post("/api/pause", pause)
    app.router.add_post("/api/resume", resume)
    return app
