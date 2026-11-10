"""換微信通知要發給誰：把公眾號測試號的 openid 寫進 config.local.json，並發一則測試通知。

雙擊 set_openid.bat 執行。要先用那個微信號掃「公眾號測試號」頁面上的測試號二維碼、關注它，
然後在同一頁的「用戶列表」複製那個帳號的 openid（微信號那一欄）。
改完要重啟監控（start.bat）才會生效。
"""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.local.json"


def main() -> None:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    wx = data.get("wechat") or {}
    old = str(wx.get("openid") or "")
    print(f"目前通知發給：…{old[-4:]}" if old and not old.startswith("填") else "目前還沒設定通知對象。")
    print("請貼上新帳號的 openid（公眾號測試號頁面「用戶列表」裡那一行）。\n")

    while True:
        openid = input("貼上 openid 後按 Enter：").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{20,40}", openid):
            break
        print("格式不對，openid 通常是 o 開頭、28 個英文數字，再試一次。")

    wx["openid"] = openid
    data["wechat"] = wx
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已存好，之後通知發給：…{openid[-4:]}")

    if input("要發一則測試通知確認嗎？（Enter = 要，輸入 n = 不要）").strip().lower() != "n":
        try:
            from app.notify import WeChat
            WeChat().send("測試", "通知對象已更換", "收到這則就代表設定正確")
            print("已發送。請在那個微信號的「公眾號測試號」對話裡看看有沒有收到。")
        except Exception as e:
            print(f"發送失敗：{e}")
            print("常見原因：那個帳號還沒關注公眾號測試號，或 openid 貼錯了。")
    print("\n記得重啟監控（雙擊 start.bat），新的設定才會生效。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n沒有存。")
    input("按 Enter 關閉視窗。")
