"""把正式小程序的 AppID 和 AppSecret 寫進 config.local.json。雙擊 set_miniprogram.bat 執行。

AppSecret 輸入時不會顯示在畫面上（貼上後直接按 Enter）。
"""

import getpass
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.local.json"
EXAMPLE = ROOT / "config.example.json"


def main() -> None:
    data = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    mp = data.get("miniprogram") or json.loads(EXAMPLE.read_text(encoding="utf-8"))["miniprogram"]

    print("在小程序後台「开发与服务 → 开发管理 → 开发设置」可以找到 AppID 和 AppSecret。")
    print("注意：要填正式小程序的，不是測試號的。\n")

    while True:
        appid = input("貼上 AppID（wx 開頭）後按 Enter：").strip()
        if re.fullmatch(r"wx[0-9a-f]{16}", appid):
            break
        print("格式不對，AppID 是 wx 加 16 個英文數字，再試一次。")

    while True:
        secret = getpass.getpass("貼上 AppSecret 後按 Enter（畫面不會顯示）：").strip()
        if re.fullmatch(r"[0-9a-f]{32}", secret):
            break
        print("格式不對，AppSecret 是 32 個英文數字，再試一次。")

    mp["appid"] = appid
    mp["appsecret"] = secret
    data["miniprogram"] = mp
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n已存好。接著雙擊 start.bat 重啟監控。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n沒有存。")
    input("按 Enter 關閉視窗。")
