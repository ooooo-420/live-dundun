"""通知：微信接口測試號的模板消息（主力），加上可選的 Bark（iPhone 鎖屏推播）。

每個管道失敗都會自己重試幾次；只要有一個管道送到就算成功，全部失敗才算失敗。
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

RETRIES = 3          # 每個管道最多試幾次
RETRY_WAIT = (2, 5)  # 第 1、2 次失敗後各等幾秒再試


def _filled(d: dict, keys: tuple[str, ...]) -> bool:
    return all(d.get(k) and not str(d[k]).startswith("填") for k in keys)


class WeChat:
    """公眾號測試號：模板消息。"""

    KEYS = ("appid", "appsecret", "openid", "template_id")

    def __init__(self, cfg: dict | None = None) -> None:
        wx = cfg if cfg is not None else json.loads(CONFIG.read_text(encoding="utf-8"))["wechat"]
        for k in self.KEYS:
            if not wx.get(k) or str(wx[k]).startswith("填"):
                raise RuntimeError(f"config.local.json 的 {k} 還沒填")
        self.wx = wx
        self._token = ""
        self._expire = 0.0

    def credentials(self) -> dict:
        """給雲端的掉線看門狗用：電腦死了時由雲端代發同一個模板。"""
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
            raise RuntimeError(f"取得 access_token 失敗：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
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
            raise RuntimeError(f"推送失敗：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")


class Bark:
    """Bark（App Store 的免費 App）：電腦對它給的網址發一個請求，iPhone 鎖屏馬上跳通知。
    config.local.json 的 bark.url 填 App 裡顯示的網址（https://api.day.app/你的key）。沒填就不用。
    2026-11-11 寫好，還沒實測。"""

    def __init__(self, cfg: dict) -> None:
        self.url = str(cfg.get("url") or "").rstrip("/")
        self.sound = cfg.get("sound") or "minuet"
        self.level = cfg.get("level") or "timeSensitive"  # 鎖屏、專注模式下也會顯示

    def send(self, room: str, product: str, status: str) -> None:
        r = requests.post(
            self.url,
            json={"title": f"{room}", "body": f"{product}\n{status}", "sound": self.sound,
                  "level": self.level, "group": "直播提醒"},
            timeout=15,
        )
        if r.status_code != 200 or (r.headers.get("content-type", "").startswith("application/json") and r.json().get("code") != 200):
            raise RuntimeError(f"Bark 回應 {r.status_code}：{r.text[:100]}")


class Notifier:
    """所有管道一起發。回傳每個管道的結果；全部失敗才拋錯。"""

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
        """回傳 {管道: "ok" 或錯誤訊息}。"""
        result: dict[str, str] = {}
        for name, ch in self.channels:
            err = ""
            for attempt in range(RETRIES):
                try:
                    ch.send(room, product, status)
                    err = ""
                    break
                except Exception as e:  # 網路抖一下很常見，等幾秒再試
                    err = str(e)[:200]
                    if attempt < RETRIES - 1:
                        time.sleep(RETRY_WAIT[min(attempt, len(RETRY_WAIT) - 1)])
            result[name] = "ok" if not err else err
        if all(v != "ok" for v in result.values()):
            raise RuntimeError("；".join(f"{k}：{v}" for k, v in result.items()))
        return result
