"""监控主体：一个专用 Edge，每个直播间一个分页。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from . import douyin, rules, store
from .notify import Notifier

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "browser-profile"

POLL_LIVE = 4          # 直播中：每几秒读一次讲解中商品
POLL_OFFLINE = 300     # 没开播：每几秒刷新一次（太频繁容易触发滑块验证）
NO_CART_GRACE = 60     # 开播但一直没看到购物车按钮多久，就当作“没有小黄车”
WATCH_KEEP = 12 * 3600  # 重开程序时，多久以内选过的直播间才继续盯


class RoomWorker:
    def __init__(self, mon: "Monitor", rid: str) -> None:
        self.mon = mon
        self.rid = rid
        self.page: Page | None = None
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.status = "starting"
        self.explaining: dict | None = None
        self.cart: list[dict] = []
        self.cart_ref: list[dict] = []
        self.cart_time = 0.0
        self.error = ""
        # 人机验证：最新截屏（给手机看）和截屏范围（把手机上的手势对回页面）
        self.shot: dict | None = None
        self.shot_area: dict | None = None
        self.shot_v = 0

    @property
    def room(self) -> dict:
        return self.mon.state["rooms"][self.rid]

    def public(self) -> dict:
        r = self.room
        return {
            "id": self.rid,
            "url": r["url"],
            "name": r.get("name") or self.rid,
            "status": self.status,
            "error": self.error,
            "type": r.get("type"),
            "watch": bool(r.get("watch")),
            "explaining": self.explaining,
            "cart_count": len(self.cart),
            "targets": r.get("targets", []),
        }

    async def ensure_page(self) -> Page:
        if self.page is None or self.page.is_closed():
            self.page = await self.mon.ctx.new_page()
        return self.page

    async def goto(self) -> douyin.Scan:
        page = await self.ensure_page()
        await page.goto(self.room["url"], wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(8)
        return await douyin.scan(page)

    async def run(self) -> None:
        while True:
            try:
                await self.cycle()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # 页面崩溃、网络断线等：记下来，稍后重试
                self.status = "error"
                self.error = str(e)[:200]
                store.log("error", room=self.rid, error=self.error)
                await asyncio.sleep(30)

    async def cycle(self) -> None:
        async with self.lock:
            s = await self.goto()
        if s.captcha:
            s = await self.wait_captcha(s.captcha_why)
        async with self.lock:
            title = s.title.replace("的抖音直播间 - 抖音直播", "").strip()
            if title and self.room.get("name") != title:
                self.room["name"] = title
                self.mon.save()
        if s.ended:
            self.set_status("offline")
            await asyncio.sleep(POLL_OFFLINE)
            return

        start = time.time()
        while not s.has_cart_button and time.time() - start < NO_CART_GRACE:
            await asyncio.sleep(5)
            s = await douyin.scan(self.page)
        if not s.has_cart_button:
            self.set_status("no_cart")
            await asyncio.sleep(POLL_OFFLINE)
            return

        self.set_status("live")
        self.error = ""
        async with self.lock:
            await douyin.open_cart(self.page)
            s = await douyin.scan(self.page)
        if s.captcha:
            await self.wait_captcha()
            self.set_status("live")
            async with self.lock:
                await douyin.open_cart(self.page)
                s = await douyin.scan(self.page)
        async with self.lock:
            if s.need_login:
                self.set_status("need_login")
                await asyncio.sleep(60)
                return
            await douyin.load_all(self.page)
            s = await douyin.stable_scan(self.page)
            self.update_cart(s)
        # 判断 A/B 型要拿“上一次换讲解时”的清单比，不能用一直在更新的 self.cart
        self.cart_ref = list(self.cart)
        last_id = s.explaining_id
        self.explaining = self.find(last_id, s)
        store.log("live", room=self.rid, items=len(self.cart), explaining=self.explaining)

        last_reload = time.time()
        while True:
            await asyncio.sleep(POLL_LIVE)
            async with self.lock:
                s = await douyin.scan(self.page)
                if await douyin.keep_playing(self.page):
                    store.log("resumed_video", room=self.rid)
            if s.captcha:
                s = await self.wait_captcha()
                self.set_status("live")
            if s.ended:
                store.log("ended", room=self.rid)
                self.explaining = None
                self.set_status("offline")
                return
            if s.items:
                self.update_cart(s)
            elif not self.cart and time.time() - last_reload > 60:
                # 2026-11-10 实测：刚打开时偶尔读到 0 件（原因不明），一分钟内没读到就自己重载购物车
                last_reload = time.time()
                async with self.lock:
                    s2 = await douyin.refresh_cart(self.page)
                if douyin.consistent(s2.items):
                    self.cart = s2.items
                    self.cart_time = time.time()
                    self.cart_ref = list(self.cart)
                store.log("cart_reload", room=self.rid, items=len(self.cart))
            cur = s.explaining_id
            if cur and cur != last_id:
                await self.on_change(last_id, cur, s)
                last_id = cur

    async def take_shot(self, rect: dict | None = None) -> None:
        if rect is None:
            rect = (await douyin.scan(self.page)).captcha_rect
        img, area = await douyin.shot(self.page, rect)
        self.shot_v += 1
        self.shot = {"img": img, "w": area["w"], "h": area["h"], "v": self.shot_v, "t": int(time.time() * 1000)}
        self.shot_area = area

    async def wait_captcha(self, why: str = "") -> douyin.Scan:
        """出现人机验证：程序自己不解，也不绕过。把验证框截屏传到小程序，由用户本人在手机上操作
        （或到电脑上的 Edge 自己完成），完成前不刷新页面。"""
        self.set_status("captcha")
        store.log("captcha", room=self.rid, why=why)
        try:
            async with self.lock:
                await self.take_shot()
        except Exception as e:
            store.log("captcha_shot_error", room=self.rid, error=str(e)[:200])
        await self.mon.push_text(self.room.get("name") or self.rid, "需要人机验证", "打开小程序就能在手机上完成")
        last_shot = time.time()
        while True:
            await asyncio.sleep(2)
            async with self.lock:
                s = await douyin.scan(self.page)
                if s.captcha and time.time() - last_shot > 20:  # 验证图可能自己换了，定时更新
                    try:
                        await self.take_shot(s.captcha_rect)
                    except Exception:
                        pass
                    last_shot = time.time()
            if not s.captcha:
                self.shot = None
                self.shot_area = None
                store.log("captcha_done", room=self.rid)
                return s

    async def remote_input(self, payload: dict) -> str:
        """用户在手机上对验证截屏做的手势：照原样放回页面，再截一张新的给手机看结果。"""
        if self.status != "captcha" or not self.page:
            raise ValueError("这间现在不需要验证")
        kind = payload.get("kind")
        if kind not in ("tap", "drag", "refresh"):
            raise ValueError("不认得的操作")
        if payload.get("v") and self.shot and payload["v"] != self.shot["v"]:
            raise ValueError("验证画面已经换了，请照新的画面再操作一次")
        async with self.lock:
            if kind != "refresh" and self.shot_area:
                await douyin.replay(self.page, self.shot_area, kind, payload.get("points") or [])
                await asyncio.sleep(1.6)
            s = await douyin.scan(self.page)
            if s.captcha:
                await self.take_shot(s.captcha_rect)
        store.log("captcha_input", room=self.rid, kind=kind, n=len(payload.get("points") or []), still=s.captcha)
        return "还要再验证" if s.captcha else "验证完成"

    def set_status(self, st: str) -> None:
        if st != self.status:
            store.log("status", room=self.rid, status=st)
        self.status = st

    def update_cart(self, s: douyin.Scan) -> None:
        if not douyin.consistent(s.items):
            return
        if len(s.items) >= len(self.cart) or time.time() - self.cart_time > 60:
            self.cart = s.items
            self.cart_time = time.time()

    def find(self, pid: str | None, s: douyin.Scan | None = None) -> dict | None:
        if not pid:
            return None
        for it in self.cart:
            if it["id"] == pid:
                return dict(it)
        src = (s.floating if s and s.floating and s.floating["id"] == pid else None) or (s.badge if s else None)
        return {"id": pid, "index": None, "title": (src or {}).get("title", ""), "price": (src or {}).get("price")}

    async def on_change(self, old: str | None, new: str, s: douyin.Scan) -> None:
        prev_index = next((i["index"] for i in self.cart_ref if i["id"] == new), None)
        async with self.lock:
            s2 = await douyin.refresh_cart(self.page)
        if douyin.consistent(s2.items):
            self.cart = s2.items
            self.cart_time = time.time()
        self.cart_ref = list(self.cart)
        item = self.find(new, s2)
        self.explaining = item
        new_index = item.get("index") if item else None
        t = rules.detect_type(prev_index, new_index)
        if t and self.room.get("type") != t:
            self.room["type"] = t
            store.log("room_type", room=self.rid, type=t)
        store.log("explain", room=self.rid, id=new, title=item and item.get("title"),
                  prev_index=prev_index, new_index=new_index,
                  snapshot_pos=rules.snapshot_pos(self.room.get("snapshot", []), new))

        for target, kind, text in rules.evaluate(self.room, new):
            await self.mon.push(self, target, kind, text)
        self.mon.save()

    async def load_cart_now(self) -> list[dict]:
        """设置网页按“加载购物车”时调用。"""
        if self.status != "live":
            return self.cart
        async with self.lock:
            s = await douyin.refresh_cart(self.page)
        if douyin.consistent(s.items):
            self.cart = s.items
            self.cart_time = time.time()
        return self.cart


class Monitor:
    def __init__(self) -> None:
        self.state = store.load()
        self.workers: dict[str, RoomWorker] = {}
        self.ctx: BrowserContext | None = None
        self.wechat: Notifier | None = None
        self.notes: list[dict] = []  # 最近发出的通知，给网页看

    def save(self) -> None:
        store.save(self.state)

    @property
    def paused(self) -> bool:
        """手机上把监控关掉时为 True：Edge 关掉、不盯直播；背景程序照样和云端同步，等“开”的指令。"""
        return bool(self.state.get("paused"))

    def watched(self, rid: str) -> bool:
        return bool(self.state["rooms"].get(rid, {}).get("watch"))

    async def start(self) -> None:
        self.wechat = Notifier()
        self._pw = await async_playwright().start()
        self.closed = asyncio.Event()
        # 直播链接常常当天就失效：超过 12 小时前选的直播间，重开程序时不自动再盯
        stale = time.time() - WATCH_KEEP
        for r in self.state["rooms"].values():
            if r.get("watch") and r.get("watch_since", 0) < stale:
                r["watch"] = False
        self.save()
        for rid in list(self.state["rooms"]):
            self.workers[rid] = RoomWorker(self, rid)
            if not self.watched(rid):
                self.workers[rid].status = "idle"
        if self.paused:
            print("监控目前是“关”（在手机上关的），等手机打开。", flush=True)
            for w in self.workers.values():
                w.status = "paused"
            self.closed.set()
        else:
            await self.launch()
            self.run_workers()
        # 用户把专用 Edge 关掉时，自动重开；要真的结束，关黑色窗口或运行 stop.bat
        asyncio.create_task(self.keep_browser())

    def run_workers(self) -> None:
        """只盯用户选了的直播间。"""
        for rid, w in self.workers.items():
            if self.watched(rid) and (w.task is None or w.task.done()):
                w.status = "starting"
                w.task = asyncio.create_task(w.run())

    async def watch(self, rid: str, on: bool) -> None:
        """手机上对某一间按“盯”或“不盯”。"""
        if rid not in self.workers:
            raise ValueError("电脑上没有这个直播间")
        if on and self.paused:
            raise ValueError("监控是关的，先打开监控")
        room = self.state["rooms"][rid]
        room["watch"] = on
        if on:
            room["watch_since"] = time.time()
        self.save()
        w = self.workers[rid]
        if on:
            self.run_workers()
        else:
            if w.task:
                w.task.cancel()
            w.task = None
            if w.page and not w.page.is_closed():
                try:
                    await w.page.close()
                except Exception:
                    pass
            w.page = None
            w.explaining = None
            w.shot = None
            w.status = "idle"
        store.log("watch", room=rid, on=on)

    async def pause(self) -> None:
        if self.paused:
            return
        self.state["paused"] = True
        self.save()
        for w in self.workers.values():
            if w.task:
                w.task.cancel()
            w.task = None
            w.page = None
            w.explaining = None
            w.status = "paused"
        if self.ctx:
            try:
                await self.ctx.close()
            except Exception:
                pass
        store.log("paused")

    async def resume(self) -> None:
        if not self.paused:
            return
        # 先开好 Edge 再把 paused 改成 False，不然 keep_browser 会以为 Edge 被关掉而抢着再开一次
        if self.closed.is_set():
            await self.launch()
        # 打开监控＝电脑先准备好（Edge 开着、登录状态在），不自动打开以前的直播间；用户在手机上选了哪间才盯哪间
        self.state["paused"] = False
        for r in self.state["rooms"].values():
            r["watch"] = False
        self.save()
        for w in self.workers.values():
            w.status = "idle"
        store.log("resumed")

    async def launch(self) -> None:
        self.ctx = await self._pw.chromium.launch_persistent_context(
            str(PROFILE), channel="msedge", headless=False, viewport={"width": 1400, "height": 850},
            args=[
                "--start-minimized",  # 一开始缩到最小，不挡画面；要人工验证时再从任务栏点开
                # 窗口被盖住或最小化时，不让 Edge 降速或暂停页面
                "--autoplay-policy=no-user-gesture-required",
                "--disable-background-timer-throttling",
                "--disable-renderer-backgrounding",
                "--disable-backgrounding-occluded-windows",
            ])
        self.closed = asyncio.Event()
        self.ctx.on("close", lambda *_: self.closed.set())

    async def keep_browser(self) -> None:
        recent: list[float] = []
        while True:
            ev = self.closed
            await ev.wait()
            while self.paused:  # 手机关掉的，不要自己重开
                await asyncio.sleep(2)
            if self.closed is not ev or not self.closed.is_set():
                continue  # 已经由 resume() 重开了
            now = time.time()
            recent = [t for t in recent if now - t < 600] + [now]
            if len(recent) > 5:  # 十分钟内被关超过 5 次，多半是出问题了，先等久一点
                store.log("browser_relaunch_backoff")
                await asyncio.sleep(300)
            else:
                await asyncio.sleep(5)
            if self.paused:
                continue
            try:
                await self.launch()
                store.log("browser_relaunch")
                print("专用 Edge 被关掉了，已重新打开。（要结束监控请关这个黑色窗口）", flush=True)
            except Exception as e:
                store.log("browser_relaunch_error", error=str(e)[:200])
                await asyncio.sleep(30)

    def spawn(self, rid: str) -> None:
        w = RoomWorker(self, rid)
        self.workers[rid] = w
        w.status = "paused" if self.paused else "idle"
        self.run_workers()

    def add_room(self, url: str) -> str:
        """贴了新链接＝要盯这间：加进来并马上开始盯（监控是关的就先记着）。同一间重贴也会重新开始盯。"""
        rid = store.room_id_from_url(url)
        if not rid:
            raise ValueError("看不懂这个网址，要是 live.douyin.com/数字 这种")
        if rid not in self.state["rooms"]:
            self.state["rooms"][rid] = {"url": f"https://live.douyin.com/{rid}", "targets": [], "snapshot": []}
        self.state["rooms"][rid]["watch"] = True
        self.state["rooms"][rid]["watch_since"] = time.time()
        self.save()
        if rid not in self.workers:
            self.spawn(rid)
        elif not self.paused:
            self.run_workers()
        return rid

    async def remove_room(self, rid: str) -> None:
        w = self.workers.pop(rid, None)
        if w:
            if w.task:
                w.task.cancel()
            if w.page and not w.page.is_closed():
                await w.page.close()
        self.state["rooms"].pop(rid, None)
        self.save()

    def set_targets(self, rid: str, targets: list[dict]) -> None:
        """targets: [{id, arrive, ahead, missed}]。以目前购物车拍快照。"""
        w = self.workers[rid]
        if not targets:  # 清空目标不需要购物车
            self.state["rooms"][rid]["targets"] = []
            self.save()
            store.log("targets", room=rid, targets=[])
            return
        if not w.cart:
            raise ValueError("还没有购物车清单，请先在直播中按“加载购物车”")
        snapshot = [i["id"] for i in w.cart]
        by_id = {i["id"]: i for i in w.cart}
        out = []
        for t in targets:
            it = by_id.get(t["id"])
            if not it:
                continue
            out.append({
                "id": it["id"], "title": it["title"], "pos": snapshot.index(it["id"]) + 1,
                "arrive": bool(t.get("arrive", True)), "ahead": int(t.get("ahead") or 0),
                "missed": bool(t.get("missed")), "sent": {}, "explained": False,
            })
        room = self.state["rooms"][rid]
        room["snapshot"] = snapshot
        room["targets"] = out
        room["last_pos"] = rules.snapshot_pos(snapshot, w.explaining and w.explaining.get("id"))
        self.save()
        store.log("targets", room=rid, targets=[{"pos": t["pos"], "title": t["title"]} for t in out])

    async def push(self, w: RoomWorker, target: dict, kind: str, text: str) -> None:
        cur = next((i["index"] for i in w.cart if i["id"] == target["id"]), None)
        if cur is None or cur == target["pos"]:
            product = f"{target['pos']}号 {target['title']}"
        else:  # 号码被置顶挤动了，两个都给
            product = f"{cur}号(原{target['pos']}号) {target['title']}"
        note = {"t": time.strftime("%H:%M:%S"), "room": w.room.get("name") or w.rid, "product": product,
                "status": text, "ok": True}
        try:
            note["channels"] = await asyncio.to_thread(self.wechat.send, note["room"], product, text)
        except Exception as e:
            note["ok"] = False
            note["error"] = str(e)[:200]
        self.notes = ([note] + self.notes)[:30]
        store.log("notify", room=w.rid, kind=kind, product=product, status=text, ok=note["ok"],
                  error=note.get("error"), channels=note.get("channels"))

    def notify_credentials(self) -> dict | None:
        """给云端看门狗用的公众号数据（电脑掉线时由云端代发通知）。"""
        return self.wechat.credentials() if self.wechat else None

    async def push_text(self, room: str, product: str, status: str) -> None:
        note = {"t": time.strftime("%H:%M:%S"), "room": room, "product": product, "status": status, "ok": True}
        try:
            note["channels"] = await asyncio.to_thread(self.wechat.send, room, product, status)
        except Exception as e:
            note["ok"] = False
            note["error"] = str(e)[:200]
        self.notes = ([note] + self.notes)[:30]

    async def test_push(self) -> None:
        await asyncio.to_thread(self.wechat.send, "测试", "监控程序运作中", "这是测试通知")

    def public(self) -> dict:
        return {"rooms": [w.public() for w in self.workers.values()], "notes": self.notes}
