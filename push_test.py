"""第 0 階段：用微信接口測試號推一則模板消息給自己，確認通知管道能用。

用法（在項目資料夾）：
    .venv\\Scripts\\python.exe push_test.py

讀取 config.local.json 的 wechat 區塊。不會印出任何密鑰。
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
        sys.exit(f"找不到 {CONFIG.name}。請把 config.example.json 複製成 config.local.json 並填好。")
    wx = json.loads(CONFIG.read_text(encoding="utf-8"))["wechat"]
    missing = [k for k in ("appid", "appsecret", "openid", "template_id") if not wx.get(k) or wx[k].startswith("填")]
    if missing:
        sys.exit(f"config.local.json 還沒填：{', '.join(missing)}")
    return wx


def get_token(wx: dict) -> str:
    r = requests.get(
        f"{API}/token",
        params={"grant_type": "client_credential", "appid": wx["appid"], "secret": wx["appsecret"]},
        timeout=15,
    ).json()
    if "access_token" not in r:
        sys.exit(f"取得 access_token 失敗：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")
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
        print("推送成功，請看微信。")
    else:
        sys.exit(f"推送失敗：errcode={r.get('errcode')} errmsg={r.get('errmsg')}")


if __name__ == "__main__":
    wx = load_config()
    send(wx, get_token(wx), "測試直播間", "37 號 測試商品（中文顯示測試）", "這是一則測試通知")
