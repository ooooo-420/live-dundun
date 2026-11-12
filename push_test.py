"""第 0 阶段：用微信接口测试号推一则模板消息给自己，确认通知管道能用。

用法（在项目文件夹）：
    .venv\\Scripts\\python.exe push_test.py

读取 config.local.json 的 wechat 区块。不会印出任何密钥。
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import requests

CONFIG = Path(__file__).with_name("config.local.json")
API = "https://api.weixin.qq.com/cgi-bin"


def load_config() -> dict:
    if not CONFIG.exists():
        sys.exit(f"找不到 {CONFIG.name}。请把 config.example.json 复制成 config.local.json 并填好。")
    wx = json.loads(CONFIG.read_text(encoding="utf-8"))["wechat"]
    missing = [k for k in ("appid", "appsecret", "openid", "template_id") if not wx.get(k) or wx[k].startswith("填")]
    if missing:
        sys.exit(f"config.local.json 还没填：{', '.join(missing)}")
    return wx


def get_token(wx: dict) -> str:
    r = requests.get(
        f"{API}/token",
        params={"grant_type": "client_credential", "appid": wx["appid"], "secret": wx["appsecret"]},
        timeout=15,
    ).json()
    if "access_token" not in r:
        sys.exit(f"取得 access_token 失败：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
    return r["access_token"]


def send(wx: dict, token: str, room: str, product: str, status: str) -> None:
    body = {
        "touser": wx["openid"],
        "template_id": wx["template_id"],
        "data": {
            "room": {"value": room},
            "product": {"value": product},
            "status": {"value": status},
            "time": {"value": datetime.now().strftime("%m-%d %H:%M:%S")},
        },
    }
    r = requests.post(
        f"{API}/message/template/send",
        params={"access_token": token},
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=15,
    ).json()
    if r.get("errcode") == 0:
        print("推送成功，请看微信。")
    else:
        sys.exit(f"推送失败：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")


if __name__ == "__main__":
    wx = load_config()
    send(wx, get_token(wx), "测试直播间", "37 号 测试商品（中文显示测试）", "这是一则测试通知")
