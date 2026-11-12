"""换微信通知要发给谁：把公众号测试号的 openid 写进 config.local.json，并发一则测试通知。

双击 set_openid.bat 运行。要先用那个微信号扫“公众号测试号”页面上的测试号二维码、关注它，
然后在同一页的“用户列表”复制那个帐号的 openid（微信号那一栏）。
改完要重启监控（start.bat）才会生效。
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
    print(f"目前通知发给：…{old[-4:]}" if old and not old.startswith("填") else "目前还没设置通知对象。")
    print("请粘贴新帐号的 openid（公众号测试号页面“用户列表”里那一行）。\n")

    while True:
        openid = input("粘贴 openid 后按 Enter：").strip()
        if re.fullmatch(r"[A-Za-z0-9_-]{20,40}", openid):
            break
        print("格式不对，openid 通常是 o 开头、28 个英文数字，再试一次。")

    wx["openid"] = openid
    data["wechat"] = wx
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\n已存好，之后通知发给：…{openid[-4:]}")

    if input("要发一则测试通知确认吗？（Enter = 要，输入 n = 不要）").strip().lower() != "n":
        try:
            from app.notify import WeChat
            WeChat().send("测试", "通知对象已更换", "收到这则就代表设置正确")
            print("已发送。请在那个微信号的“公众号测试号”对话里看看有没有收到。")
        except Exception as e:
            print(f"发送失败：{e}")
            print("常见原因：那个帐号还没关注公众号测试号，或 openid 贴错了。")
    print("\n记得重启监控（双击 start.bat），新的设置才会生效。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n没有存。")
    input("按 Enter 关闭窗口。")
