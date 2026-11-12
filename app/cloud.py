"""和小程序同步：通过云开发的云函数 api 交换数据。

电脑每 15 秒调用一次云函数：
- 送上去：直播间状态（有变才送）、购物车（有变才送）、上一轮指令的处理结果。
- 拿回来：小程序送来、还没处理的指令（加入直播间、移除、设目标）。

电脑是主动连出去的，不用内网穿透，也不用对外开放任何连接端口。
调用云函数要用正式小程序的 AppID 和 AppSecret 换 access_token，这两个只放在 config.local.json。
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

INTERVAL = 15        # 几秒同步一次
CAPTCHA_INTERVAL = 1.5  # 有直播间在等人机验证时，同步快一点，手机上的操作才不会延迟
PAUSED_INTERVAL = 60  # 手机把监控关掉时，改成每分钟同步一次（省云端额度）
HEARTBEAT_EVERY = 4  # 每几次同步带一次心跳（约一分钟），省数据库写入次数


def load_config() -> dict | None:
    """没填小程序设置就回 None（只用电脑本机的设置网页，不同步）。"""
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
    """调用云函数 api。"""

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
            raise RuntimeError(f"小程序取得 access_token 失败：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
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
                    raise RuntimeError(f"云函数回报错误：{resp.get('error')}")
                return resp.get("data")
            if r.get("errcode") in (40001, 42001) and attempt == 0:
                self._token = ""
                continue
            raise RuntimeError(f"调用云函数失败：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
        raise RuntimeError("调用云函数失败")


def resolve_room_url(text: str) -> str:
    """把小程序贴来的链接变成 live.douyin.com/数字。短链接（v.douyin.com）会跟着转址去找。"""
    m = re.search(r"live\.douyin\.com/(\d+)", text)
    if m:
        return f"https://live.douyin.com/{m.group(1)}"
    s = re.search(r"https?://v\.douyin\.com/[\w-]+/?", text)
    if not s:
        raise ValueError("看不懂这个链接")
    ua = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X)"}
    r = requests.get(s.group(0), allow_redirects=True, timeout=15, headers=ua)
    hay = " ".join([h.headers.get("Location", "") for h in r.history] + [r.url])
    for pat in (r"live\.douyin\.com/(\d+)", r"web_rid=(\d+)"):
        m = re.search(pat, hay)
        if m:
            return f"https://live.douyin.com/{m.group(1)}"
    # 2026-11-10 实测：手机分享的直播短链接会转到 webcast.amemv.com/douyin/webcast/reflow/<内部 room_id>，
    # 网址里没有网页版号码。分享页自己会调用 reflow/info，回传的 owner.web_rid 就是 live.douyin.com/ 后面那串。
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
    raise ValueError("短链接转不出直播间号码。请在电脑上打开直播间，复制 live.douyin.com 开头的网址再贴。")


def _digest(obj: Any) -> str:
    return hashlib.sha1(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


class CloudSync:
    def __init__(self, mon, cloud, resolver=resolve_room_url) -> None:
        self.mon = mon
        self.cloud = cloud
        self.resolver = resolver
        self.results: list[dict] = []
        # 已处理过的指令：云端没标成完成时会再送来，这时只重送结果，不再做一次
        self.handled: dict[str, dict] = {}
        self.sent_rooms = ""
        self.sent_paused: bool | None = None
        self.sent_notify = ""
        self.sent_carts: dict[str, str] = {}
        self.sent_shots: dict[str, int] = {}  # 直播间 → 已送上去的验证截屏版本（0＝没有截屏）
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
        # 人机验证截屏：换了才送；验证完成（没有截屏了）也要送一次 null 让手机知道
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
        # 关着的时候每分钟才同步一次，所以每次都带心跳；开关一变也马上带，让手机看到
        if self.count % HEARTBEAT_EVERY == 0 or paused or paused != self.sent_paused:
            body["heartbeat"] = True
            body["pc"] = {"paused": paused}
            # 公众号数据交给云端的看门狗（watchdog）：电脑超过 10 分钟没心跳时，由云端代发“电脑掉线”
            creds = getattr(self.mon, "notify_credentials", lambda: None)()
            if creds and _digest(creds) != self.sent_notify:
                body["notify"] = creds
        return body, (rd if "rooms" in body else None), cd

    async def tick(self) -> int:
        """同步一次，回传这轮处理了几个指令。"""
        body, rd, cd = self.build()
        data = await asyncio.to_thread(self.cloud.invoke, body)
        self.count += 1
        # 送成功才记下来，失败下一轮会重送
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
                res = {"ok": True, "message": "监控已关闭", "room": None}
            elif kind == "resume":
                await self.mon.resume()
                res = {"ok": True, "message": "监控已打开", "room": None}
            elif kind in ("watch", "unwatch"):
                await self.mon.watch(room, kind == "watch")
                res = {"ok": True, "message": "开始盯这间" if kind == "watch" else "不盯这间了", "room": room}
            elif kind == "captcha_input":
                w = self.mon.workers.get(room)
                if not w:
                    raise ValueError("电脑上没有这个直播间")
                msg = await w.remote_input(payload)
                res = {"ok": True, "message": msg, "room": room}
            elif kind == "remove_room":
                await self.mon.remove_room(room)
                res = {"ok": True, "message": "已移除", "room": room}
            elif kind == "set_targets":
                if room not in self.mon.workers:
                    raise ValueError("电脑上没有这个直播间")
                wanted = payload.get("targets") or []
                self.mon.set_targets(room, wanted)
                got = len(self.mon.state["rooms"][room].get("targets", []))
                lost = len(wanted) - got
                msg = f"已设 {got} 件" if got else "已清空目标"
                if lost > 0:
                    msg += f"（{lost} 件已不在购物车）"
                res = {"ok": True, "message": msg, "room": room}
            else:
                raise ValueError(f"不认得的指令 {kind}")
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
            # 刚处理完新指令就很快再同步一次，让小程序早点看到结果；只对新指令这样做，避免卡住时狂打云端
            idle = PAUSED_INTERVAL if getattr(self.mon, "paused", False) else INTERVAL
            if any(getattr(w, "status", "") == "captcha" for w in self.mon.workers.values()):
                idle = CAPTCHA_INTERVAL
            await asyncio.sleep(min(2, idle) if n else idle)
