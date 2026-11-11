"""監控主體：一個專用 Edge，每個直播間一個分頁。"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from playwright.async_api import BrowserContext, Page, async_playwright

from . import douyin, rules, store
from .notify import Notifier

ROOT = Path(__file__).resolve().parent.parent
PROFILE = ROOT / "browser-profile"

POLL_LIVE = 4          # 直播中：每幾秒讀一次講解中商品
POLL_OFFLINE = 300     # 沒開播：每幾秒重新整理一次（太頻繁容易觸發滑塊驗證）
NO_CART_GRACE = 60     # 開播但一直沒看到購物車按鈕多久，就當作「沒有小黃車」
WATCH_KEEP = 12 * 3600  # 重開程式時，多久以內選過的直播間才繼續盯


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
        # 人機驗證：最新截圖（給手機看）和截圖範圍（把手機上的手勢對回頁面）
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
            except Exception as e:  # 頁面崩潰、網路斷線等：記下來，稍後重試
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
        # 判斷 A/B 型要拿「上一次換講解時」的清單比，不能用一直在更新的 self.cart
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
                # 2026-11-10 實測：剛打開時偶爾讀到 0 件（原因不明），一分鐘內沒讀到就自己重載購物車
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
        """出現人機驗證：程式自己不解，也不繞過。把驗證框截圖傳到小程序，由使用者本人在手機上操作
        （或到電腦上的 Edge 自己完成），完成前不重新整理頁面。"""
        self.set_status("captcha")
        store.log("captcha", room=self.rid, why=why)
        try:
            async with self.lock:
                await self.take_shot()
        except Exception as e:
            store.log("captcha_shot_error", room=self.rid, error=str(e)[:200])
        await self.mon.push_text(self.room.get("name") or self.rid, "需要人機驗證", "打開小程序就能在手機上完成")
        last_shot = time.time()
        while True:
            await asyncio.sleep(2)
            async with self.lock:
                s = await douyin.scan(self.page)
                if s.captcha and time.time() - last_shot > 20:  # 驗證圖可能自己換了，定時更新
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
        """使用者在手機上對驗證截圖做的手勢：照原樣放回頁面，再截一張新的給手機看結果。"""
        if self.status != "captcha" or not self.page:
            raise ValueError("這間現在不需要驗證")
        kind = payload.get("kind")
        if kind not in ("tap", "drag", "refresh"):
            raise ValueError("不認得的操作")
        if payload.get("v") and self.shot and payload["v"] != self.shot["v"]:
            raise ValueError("驗證畫面已經換了，請照新的畫面再操作一次")
        async with self.lock:
            if kind != "refresh" and self.shot_area:
                await douyin.replay(self.page, self.shot_area, kind, payload.get("points") or [])
                await asyncio.sleep(1.6)
            s = await douyin.scan(self.page)
            if s.captcha:
                await self.take_shot(s.captcha_rect)
        store.log("captcha_input", room=self.rid, kind=kind, n=len(payload.get("points") or []), still=s.captcha)
        return "還要再驗證" if s.captcha else "驗證完成"

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
        """設定網頁按「載入購物車」時呼叫。"""
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
        self.notes: list[dict] = []  # 最近發出的通知，給網頁看

    def save(self) -> None:
        store.save(self.state)

    @property
    def paused(self) -> bool:
        """手機上把監控關掉時為 True：Edge 關掉、不盯直播；背景程式照樣和雲端同步，等「開」的指令。"""
        return bool(self.state.get("paused"))

    def watched(self, rid: str) -> bool:
        return bool(self.state["rooms"].get(rid, {}).get("watch"))

    async def start(self) -> None:
        self.wechat = Notifier()
        self._pw = await async_playwright().start()
        self.closed = asyncio.Event()
        # 直播連結常常當天就失效：超過 12 小時前選的直播間，重開程式時不自動再盯
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
            print("監控目前是「關」（在手機上關的），等手機打開。", flush=True)
            for w in self.workers.values():
                w.status = "paused"
            self.closed.set()
        else:
            await self.launch()
            self.run_workers()
        # 使用者把專用 Edge 關掉時，自動重開；要真的結束，關黑色視窗或執行 stop.bat
        asyncio.create_task(self.keep_browser())

    def run_workers(self) -> None:
        """只盯使用者選了的直播間。"""
        for rid, w in self.workers.items():
            if self.watched(rid) and (w.task is None or w.task.done()):
                w.status = "starting"
                w.task = asyncio.create_task(w.run())

    async def watch(self, rid: str, on: bool) -> None:
        """手機上對某一間按「盯」或「不盯」。"""
        if rid not in self.workers:
            raise ValueError("電腦上沒有這個直播間")
        if on and self.paused:
            raise ValueError("監控是關的，先打開監控")
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
        # 先開好 Edge 再把 paused 改成 False，不然 keep_browser 會以為 Edge 被關掉而搶著再開一次
        if self.closed.is_set():
            await self.launch()
        # 打開監控＝電腦先準備好（Edge 開著、登入狀態在），不自動打開以前的直播間；使用者在手機上選了哪間才盯哪間
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
                "--start-minimized",  # 一開始縮到最小，不擋畫面；要人工驗證時再從工作列點開
                # 視窗被蓋住或最小化時，不讓 Edge 降速或暫停頁面
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
            while self.paused:  # 手機關掉的，不要自己重開
                await asyncio.sleep(2)
            if self.closed is not ev or not self.closed.is_set():
                continue  # 已經由 resume() 重開了
            now = time.time()
            recent = [t for t in recent if now - t < 600] + [now]
            if len(recent) > 5:  # 十分鐘內被關超過 5 次，多半是出問題了，先等久一點
                store.log("browser_relaunch_backoff")
                await asyncio.sleep(300)
            else:
                await asyncio.sleep(5)
            if self.paused:
                continue
            try:
                await self.launch()
                store.log("browser_relaunch")
                print("專用 Edge 被關掉了，已重新打開。（要結束監控請關這個黑色視窗）", flush=True)
            except Exception as e:
                store.log("browser_relaunch_error", error=str(e)[:200])
                await asyncio.sleep(30)

    def spawn(self, rid: str) -> None:
        w = RoomWorker(self, rid)
        self.workers[rid] = w
        w.status = "paused" if self.paused else "idle"
        self.run_workers()

    def add_room(self, url: str) -> str:
        """貼了新連結＝要盯這間：加進來並馬上開始盯（監控是關的就先記著）。同一間重貼也會重新開始盯。"""
        rid = store.room_id_from_url(url)
        if not rid:
            raise ValueError("看不懂這個網址，要是 live.douyin.com/數字 這種")
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
        """targets: [{id, arrive, ahead, missed}]。以目前購物車拍快照。"""
        w = self.workers[rid]
        if not targets:  # 清空目標不需要購物車
            self.state["rooms"][rid]["targets"] = []
            self.save()
            store.log("targets", room=rid, targets=[])
            return
        if not w.cart:
            raise ValueError("還沒有購物車清單，請先在直播中按「載入購物車」")
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
            product = f"{target['pos']}號 {target['title']}"
        else:  # 號碼被置頂擠動了，兩個都給
            product = f"{cur}號(原{target['pos']}號) {target['title']}"
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
        """給雲端看門狗用的公眾號資料（電腦掉線時由雲端代發通知）。"""
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
        await asyncio.to_thread(self.wechat.send, "測試", "監控程式運作中", "這是測試通知")

    def public(self) -> dict:
        return {"rooms": [w.public() for w in self.workers.values()], "notes": self.notes}
