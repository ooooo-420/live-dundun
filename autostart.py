"""开机自动在背景启动监控（不出现黑色窗口）。

    双击 autostart_on.bat  打开
    双击 autostart_off.bat 关闭

做法：在你自己的“启动”文件夹（shell:startup）放一个小脚本，登录 Windows 时用 pythonw 在背景跑 run.py。
只影响你这个 Windows 账号，不改系统设置；删掉那个脚本就恢复原样。
"""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STARTUP = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
SCRIPT = STARTUP / "muhou_monitor.vbs"


def turn_on() -> None:
    pyw = ROOT / ".venv" / "Scripts" / "pythonw.exe"
    if not pyw.exists():
        sys.exit(f"找不到 {pyw}，请确认 .venv 还在。")
    vbs = (
        "' 目候：开机在背景启动监控程序（由 autostart.py 产生，删掉这个文件就不会再自动启动）\r\n"
        'Set sh = CreateObject("WScript.Shell")\r\n'
        f'sh.CurrentDirectory = "{ROOT}"\r\n'
        f'sh.Run """{pyw}"" ""{ROOT / "run.py"}""", 0, False\r\n'
    )
    STARTUP.mkdir(parents=True, exist_ok=True)
    SCRIPT.write_text(vbs, encoding="utf-16")  # VBS 要用 UTF-16 才认得中文路径
    print("已打开：下次登录 Windows 时，监控程序会自己在背景启动。")
    print(f"（放在：{SCRIPT}）")


def turn_off() -> None:
    if SCRIPT.exists():
        SCRIPT.unlink()
        print("已关闭：开机不会再自动启动。现在正在跑的监控不受影响，要结束请双击 stop.bat。")
    else:
        print("本来就没有打开开机自动启动。")


if __name__ == "__main__":
    (turn_off if len(sys.argv) > 1 and sys.argv[1] == "off" else turn_on)()
    if len(sys.argv) > 2 and sys.argv[2] == "pause":
        input("按 Enter 关闭这个窗口……")
