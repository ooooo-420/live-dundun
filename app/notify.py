"""通知：微信接口测试号的模板消息（主力），加上可选的 Bark（iPhone 锁屏推播）。

每个管道失败都会自己重试几次；只要有一个管道送到就算成功，全部失败才算失败。
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config.local.json"
API = "https://api.weixin.qq.com/cgi-bin"

RETRIES = 3          # 每个管道最多试几次
RETRY_WAIT = (2, 5)  # 第 1、2 次失败后各等几秒再试


def _filled(d: dict, keys: tuple[str, ...]) -> bool:
    return all(d.get(k) and not str(d[k]).startswith("填") for k in keys)


class WeChat:
    """公众号测试号：模板消息。"""

    KEYS = ("appid", "appsecret", "openid", "template_id")

    def __init__(self, cfg: dict | None = None) -> None:
        wx = cfg if cfg is not None else json.loads(CONFIG.read_text(encoding="utf-8"))["wechat"]
        for k in self.KEYS:
            if not wx.get(k) or str(wx[k]).startswith("填"):
                raise RuntimeError(f"config.local.json 的 {k} 还没填")
        self.wx = wx
        self._token = ""
        self._expire = 0.0

    def credentials(self) -> dict:
        """给云端的掉线看门狗用：电脑死了时由云端代发同一个模板。"""
        return {k: self.wx[k] for k in self.KEYS}

    def _get_token(self) -> str:
        if self._token and time.time() < self._expire:
            return self._token
        r = requests.get(
            f"{API}/token",
            params={"grant_type": "client_credential", "appid": self.wx["appid"], "secret": self.wx["appsecret"]},
            timeout=15,
        ).json()
        if "access_token" not in r:
            raise RuntimeError(f"取得 access_token 失败：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
        self._token = r["access_token"]
        self._expire = time.time() + int(r.get("expires_in", 7200)) - 300
        return self._token

    def send(self, room: str, product: str, status: str) -> None:
        body = {
            "touser": self.wx["openid"],
            "template_id": self.wx["template_id"],
            "data": {
                "room": {"value": room[:20]},
                "product": {"value": product[:20]},
                "status": {"value": status[:20]},
                "time": {"value": datetime.now().strftime("%m-%d %H:%M:%S")},
            },
        }
        for attempt in range(2):
            r = requests.post(
                f"{API}/message/template/send",
                params={"access_token": self._get_token()},
                data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
                timeout=15,
            ).json()
            if r.get("errcode") == 0:
                return
            if r.get("errcode") in (40001, 42001) and attempt == 0:  # token 失效，重拿一次
                self._token = ""
                continue
            raise RuntimeError(f"推送失败：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")


class Bark:
    """Bark（App Store 的免费 App）：电脑对它给的网址发一个请求，iPhone 锁屏马上跳通知。
    config.local.json 的 bark.url 填 App 里显示的网址（https://api.day.app/你的key）。没填就不用。
    2026-11-11 写好，还没实测。"""

    def __init__(self, cfg: dict) -> None:
        self.url = str(cfg.get("url") or "").rstrip("/")
        self.sound = cfg.get("sound") or "minuet"
        self.level = cfg.get("level") or "timeSensitive"  # 锁屏、专注模式下也会显示

    def send(self, room: str, product: str, status: str) -> None:
        r = requests.post(
            self.url,
            json={"title": f"{room}", "body": f"{product}\n{status}", "sound": self.sound,
                  "level": self.level, "group": "直播提醒"},
            timeout=15,
        )
        if r.status_code != 200 or (r.headers.get("content-type", "").startswith("application/json") and r.json().get("code") != 200):
            raise RuntimeError(f"Bark 回应 {r.status_code}：{r.text[:100]}")


class Notifier:
    """所有管道一起发。回传每个管道的结果；全部失败才抛错。"""

    def __init__(self, cfg: dict | None = None) -> None:
        cfg = cfg if cfg is not None else json.loads(CONFIG.read_text(encoding="utf-8"))
        self.wechat = WeChat(cfg["wechat"])
        self.channels: list[tuple[str, object]] = [("wechat", self.wechat)]
        bark = cfg.get("bark") or {}
        if _filled(bark, ("url",)) and bark["url"].startswith("http"):
            self.channels.append(("bark", Bark(bark)))

    def credentials(self) -> dict:
        return self.wechat.credentials()

    def send(self, room: str, product: str, status: str) -> dict[str, str]:
        """回传 {管道: "ok" 或错误消息}。"""
        result: dict[str, str] = {}
        for name, ch in self.channels:
            err = ""
            for attempt in range(RETRIES):
                try:
                    ch.send(room, product, status)
                    err = ""
                    break
                except Exception as e:  # 网络抖一下很常见，等几秒再试
                    err = str(e)[:200]
                    if attempt < RETRIES - 1:
                        time.sleep(RETRY_WAIT[min(attempt, len(RETRY_WAIT) - 1)])
            result[name] = "ok" if not err else err
        if all(v != "ok" for v in result.values()):
            raise RuntimeError("；".join(f"{k}：{v}" for k, v in result.items()))
        return result
