"""把正式小程序的 AppID 和 AppSecret 写进 config.local.json。双击 set_miniprogram.bat 运行。

AppSecret 输入时不会显示在画面上（粘贴后直接按 Enter）。
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

    print("在小程序后台“开发与服务 → 开发管理 → 开发设置”可以找到 AppID 和 AppSecret。")
    print("注意：要填正式小程序的，不是测试号的。\n")

    while True:
        appid = input("粘贴 AppID（wx 开头）后按 Enter：").strip()
        if re.fullmatch(r"wx[0-9a-f]{16}", appid):
            break
        print("格式不对，AppID 是 wx 加 16 个英文数字，再试一次。")

    while True:
        secret = getpass.getpass("粘贴 AppSecret 后按 Enter（画面不会显示）：").strip()
        if re.fullmatch(r"[0-9a-f]{32}", secret):
            break
        print("格式不对，AppSecret 是 32 个英文数字，再试一次。")

    mp["appid"] = appid
    mp["appsecret"] = secret
    data["miniprogram"] = mp
    CONFIG.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("\n已存好。接着双击 start.bat 重启监控。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n没有存。")
    input("按 Enter 关闭窗口。")
