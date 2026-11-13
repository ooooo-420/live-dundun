"""把大号码的字体（Baloo 2 ExtraBold，OFL 授权）只取 0-9 十个字，转成 base64 写进 miniprogram/app.wxss 最后的标记之间。
字体子集直接向 Google Fonts 要（text= 参数），不用另外装工具；写进 wxss 后小程序不需要网域白名单。
用法：.venv\\Scripts\\python.exe design\\mp-redesign\\embed_font.py"""
import base64, re
from pathlib import Path
import requests

FAMILY, WEIGHT, TEXT = "Baloo 2", 800, "0123456789"
ROOT = Path(__file__).resolve().parents[2]
WXSS = ROOT / "miniprogram" / "app.wxss"
A, B = "/* LiveNum:start（由 design/mp-redesign/embed_font.py 产生，不要手改） */", "/* LiveNum:end */"

# 不带浏览器 UA：Google Fonts 会给 TTF，各种手机都认
css = requests.get("https://fonts.googleapis.com/css2", params={"family": f"{FAMILY}:wght@{WEIGHT}", "text": TEXT}, timeout=30).text
url = re.search(r"url\((https://[^)]+)\)", css).group(1)
fmt = re.search(r"format\('([^']+)'\)", css).group(1)
data = requests.get(url, timeout=30).content
assert fmt == "truetype" and data[:4] in (b"\x00\x01\x00\x00", b"true"), (fmt, data[:4])
face = (f'{A}\n@font-face {{ font-family: "LiveNum"; font-weight: {WEIGHT}; '
        f'src: url("data:font/ttf;base64,{base64.b64encode(data).decode()}") format("truetype"); }}\n{B}')
text = WXSS.read_text(encoding="utf-8")
text = re.sub(re.escape(A) + r"[\s\S]*?" + re.escape(B), lambda m: face, text) if A in text else text.rstrip() + "\n\n" + face + "\n"
WXSS.write_text(text, encoding="utf-8", newline="\n")
print(f"{FAMILY} {WEIGHT}: {len(data)} bytes ttf -> app.wxss")
