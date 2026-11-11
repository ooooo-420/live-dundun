"""和小程序同步：透過雲開發的雲函數 api 交換資料。

電腦每 15 秒呼叫一次雲函數：
- 送上去：直播間狀態（有變才送）、購物車（有變才送）、上一輪指令的處理結果。
- 拿回來：小程序送來、還沒處理的指令（加入直播間、移除、設目標）。

電腦是主動連出去的，不用內網穿透，也不用對外開放任何連接埠。
呼叫雲函數要用正式小程序的 AppID 和 AppSecret 換 access_token，這兩個只放在 config.local.json。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests

from . import store

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.local.json"
API = "https://api.weixin.qq.com"

INTERVAL = 15        # 幾秒同步一次
CAPTCHA_INTERVAL = 1.5  # 有直播間在等人機驗證時，同步快一點，手機上的操作才不會延遲
PAUSED_INTERVAL = 60  # 手機把監控關掉時，改成每分鐘同步一次（省雲端額度）
HEARTBEAT_EVERY = 4  # 每幾次同步帶一次心跳（約一分鐘），省資料庫寫入次數


def load_config() -> dict | None:
    """沒填小程序設定就回 None（只用電腦本機的設定網頁，不同步）。"""
    try:
        mp = json.loads(CONFIG.read_text(encoding="utf-8")).get("miniprogram") or {}
    except FileNotFoundError:
        return None
    for k in ("appid", "appsecret", "env"):
        v = str(mp.get(k) or "")
        if not v or v.startswith("填"):
            return None
    return mp


class Cloud:
    """呼叫雲函數 api。"""

    def __init__(self, cfg: dict, function: str = "api") -> None:
        self.cfg = cfg
        self.function = function
        self._token = ""
        self._expire = 0.0

    def _get_token(self) -> str:
        if self._token and time.time() < self._expire:
            return self._token
        r = requests.get(
            f"{API}/cgi-bin/token",
            params={"grant_type": "client_credential", "appid": self.cfg["appid"], "secret": self.cfg["appsecret"]},
            timeout=15,
        ).json()
        if "access_token" not in r:
            raise RuntimeError(f"小程序取得 access_token 失敗：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
        self._token = r["access_token"]
        self._expire = time.time() + int(r.get("expires_in", 7200)) - 300
        return self._token

    def invoke(self, data: dict) -> Any:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        for attempt in range(2):
            r = requests.post(
                f"{API}/tcb/invokecloudfunction",
                params={"access_token": self._get_token(), "env": self.cfg["env"], "name": self.function},
                data=body,
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=30,
            ).json()
            if r.get("errcode", 0) == 0:
                resp = json.loads(r.get("resp_data") or "{}")
                if not resp.get("ok"):
                    raise RuntimeError(f"雲函數回報錯誤：{resp.get('error')}")
                return resp.get("data")
            if r.get("errcode") in (40001, 42001) and attempt == 0:
                self._token = ""
                continue
            raise RuntimeError(f"呼叫雲函數失敗：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
        raise RuntimeError("呼叫雲函數失敗")


def resolve_room_url(text: str) -> str:
    """把小程序貼來的連結變成 live.douyin.com/數字。短連結（v.douyin.com）會跟著轉址去找。"""
    m = re.search(r"live\.douyin\.com/(\d+)", text)
    if m:
        return f"https://live.douyin.com/{m.group(1)}"
    s = re.search(r"https?://v\.douyin\.com/[\w-]+/?", text)
    if not s:
        raise ValueError("看不懂這個連結")
    ua = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
    r = requests.get(s.group(0), allow_redirects=True, timeout=15, headers=ua)
    hay = " ".join([h.headers.get("Location", "") for h in r.history] + [r.url])
    for pat in (r"live\.douyin\.com/(\d+)", r"web_rid=(\d+)"):
        m = re.search(pat, hay)
        if m:
            return f"https://live.douyin.com/{m.group(1)}"
    # 2026-11-10 實測：手機分享的直播短連結會轉到 webcast.amemv.com/douyin/webcast/reflow/<內部 room_id>，
    # 網址裡沒有網頁版號碼。分享頁自己會呼叫 reflow/info，回傳的 owner.web_rid 就是 live.douyin.com/ 後面那串。
    m = re.search(r"/reflow/(\d+)", r.url)
    if m:
        q = parse_qs(urlparse(r.url).query)
        info = requests.get(
            "https://webcast.amemv.com/webcast/room/reflow/info/",
            params={"type_id": 0, "live_id": 1, "room_id": m.group(1),
                    "sec_user_id": (q.get("sec_user_id") or [""])[0], "app_id": 1128},
            headers=ua, timeout=15,
        )
        w = re.search(r'"web_rid"\s*:\s*"?(\d+)', info.text)
        if w:
            return f"https://live.douyin.com/{w.group(1)}"
    raise ValueError("短連結轉不出直播間號碼。請在電腦上打開直播間，複製 live.douyin.com 開頭的網址再貼。")


def _digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class CloudSync:
    def __init__(self, mon, cloud, resolver=resolve_room_url) -> None:
        self.mon = mon
        self.cloud = cloud
        self.resolver = resolver
        self.results: list[dict] = []
        # 已處理過的指令：雲端沒標成完成時會再送來，這時只重送結果，不再做一次
        self.handled: dict[str, dict] = {}
        self.sent_rooms = ""
        self.sent_paused: bool | None = None
        self.sent_notify = ""
        self.sent_carts: dict[str, str] = {}
        self.sent_shots: dict[str, int] = {}  # 直播間 → 已送上去的驗證截圖版本（0＝沒有截圖）
        self.count = 0
        self.ok = False
        self.last_error = ""

    def rooms_payload(self) -> list[dict]:
        out = []
        for w in self.mon.workers.values():
            p = w.public()
            out.append({k: p.get(k) for k in ("id", "url", "name", "status", "error", "type", "watch", "explaining", "cart_count", "targets")})
        return out

    def build(self) -> tuple[dict, str | None, dict[str, str]]:
        body: dict[str, Any] = {"action": "pc_sync"}
        rooms = self.rooms_payload()
        rd = _digest(rooms)
        if rd != self.sent_rooms:
            body["rooms"] = rooms
        carts, cd = {}, {}
        for rid, w in self.mon.workers.items():
            if not w.cart:
                continue
            d = _digest(w.cart)
            if self.sent_carts.get(rid) != d:
                carts[rid] = w.cart
                cd[rid] = d
        if carts:
            body["carts"] = carts
        # 人機驗證截圖：換了才送；驗證完成（沒有截圖了）也要送一次 null 讓手機知道
        shots = {}
        for rid, w in self.mon.workers.items():
            sh = getattr(w, "shot", None)
            v = sh["v"] if sh else 0
            if self.sent_shots.get(rid, 0) != v:
                shots[rid] = sh
        if shots:
            body["captchas"] = shots
        if self.results:
            body["results"] = self.results
        paused = bool(getattr(self.mon, "paused", False))
        # 關著的時候每分鐘才同步一次，所以每次都帶心跳；開關一變也馬上帶，讓手機看到
        if self.count % HEARTBEAT_EVERY == 0 or paused or paused != self.sent_paused:
            body["heartbeat"] = True
            body["pc"] = {"paused": paused}
            # 公眾號資料交給雲端的看門狗（watchdog）：電腦超過 10 分鐘沒心跳時，由雲端代發「電腦掉線」
            creds = getattr(self.mon, "notify_credentials", lambda: None)()
            if creds and _digest(creds) != self.sent_notify:
                body["notify"] = creds
        return body, (rd if "rooms" in body else None), cd

    async def tick(self) -> int:
        """同步一次，回傳這輪處理了幾個指令。"""
        body, rd, cd = self.build()
        data = await asyncio.to_thread(self.cloud.invoke, body)
        self.count += 1
        # 送成功才記下來，失敗下一輪會重送
        if rd is not None:
            self.sent_rooms = rd
        if "pc" in body:
            self.sent_paused = body["pc"]["paused"]
        if "notify" in body:
            self.sent_notify = _digest(body["notify"])
        self.sent_carts.update(cd)
        for rid in list(self.sent_carts):
            if rid not in self.mon.workers:
                del self.sent_carts[rid]
        for rid, sh in (body.get("captchas") or {}).items():
            self.sent_shots[rid] = sh["v"] if sh else 0
        self.results = []
        errs = (data or {}).get("resultErrors") or []
        if errs:
            store.log("cloud_result_error", errors=errs[:5])
        commands = (data or {}).get("commands") or []
        new = 0
        for cmd in commands:
            cid = cmd.get("_id")
            if cid in self.handled:
                self.results.append(self.handled[cid])
                continue
            res = await self.apply(cmd)
            self.handled[cid] = res
            self.results.append(res)
            new += 1
        if len(self.handled) > 500:
            self.handled = dict(list(self.handled.items())[-200:])
        return new

    async def apply(self, cmd: dict) -> dict:
        cid = cmd.get("_id")
        kind = cmd.get("type")
        room = cmd.get("room")
        payload = cmd.get("payload") or {}
        try:
            if kind == "add_room":
                url = await asyncio.to_thread(self.resolver, payload.get("text") or "")
                rid = self.mon.add_room(url)
                res = {"ok": True, "message": "已加入", "room": rid}
            elif kind == "pause":
                await self.mon.pause()
                res = {"ok": True, "message": "監控已關閉", "room": None}
            elif kind == "resume":
                await self.mon.resume()
                res = {"ok": True, "message": "監控已打開", "room": None}
            elif kind in ("watch", "unwatch"):
                await self.mon.watch(room, kind == "watch")
                res = {"ok": True, "message": "開始盯這間" if kind == "watch" else "不盯這間了", "room": room}
            elif kind == "captcha_input":
                w = self.mon.workers.get(room)
                if not w:
                    raise ValueError("電腦上沒有這個直播間")
                msg = await w.remote_input(payload)
                res = {"ok": True, "message": msg, "room": room}
            elif kind == "remove_room":
                await self.mon.remove_room(room)
                res = {"ok": True, "message": "已移除", "room": room}
            elif kind == "set_targets":
                if room not in self.mon.workers:
                    raise ValueError("電腦上沒有這個直播間")
                wanted = payload.get("targets") or []
                self.mon.set_targets(room, wanted)
                got = len(self.mon.state["rooms"][room].get("targets", []))
                lost = len(wanted) - got
                msg = f"已設 {got} 件" if got else "已清空目標"
                if lost > 0:
                    msg += f"（{lost} 件已不在購物車）"
                res = {"ok": True, "message": msg, "room": room}
            else:
                raise ValueError(f"不認得的指令 {kind}")
        except Exception as e:
            res = {"ok": False, "message": str(e)[:200], "room": room}
        store.log("cloud_command", type=kind, room=room, ok=res["ok"], message=res["message"])
        return {"id": cid, **res}

    async def run(self) -> None:
        while True:
            n = 0
            try:
                n = await self.tick()
                if not self.ok:
                    store.log("cloud_ok")
                self.ok, self.last_error = True, ""
            except asyncio.CancelledError:
                raise
            except Exception as e:
                err = str(e)[:200]
                if err != self.last_error:
                    store.log("cloud_error", error=err)
                    print(f"[小程序同步] {err}", flush=True)
                self.ok, self.last_error = False, err
            # 剛處理完新指令就很快再同步一次，讓小程序早點看到結果；只對新指令這樣做，避免卡住時狂打雲端
            idle = PAUSED_INTERVAL if getattr(self.mon, "paused", False) else INTERVAL
            if any(getattr(w, "status", "") == "captcha" for w in self.mon.workers.values()):
                idle = CAPTCHA_INTERVAL
            await asyncio.sleep(min(2, idle) if n else idle)
