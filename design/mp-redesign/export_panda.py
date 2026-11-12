"""把熊貓 A 輸出成小程序用的透明 PNG（3 倍圖，600×510，對應 viewBox 200×170）。
- panda_head.png：平常的頭
- panda_hot.png：到號時的頭（眼睛睜大、嘴巴張開、兩手舉起）
- panda_paws.png：扒在票上的兩隻爪子（單獨一張，換號時才能自己抬起來）
用法：.venv\\Scripts\\python.exe design\\mp-redesign\\export_panda.py"""
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "miniprogram" / "images"
OUT.mkdir(exist_ok=True)

HEAD = """
 <defs><radialGradient id="fa" cx="45%" cy="35%" r="70%"><stop offset="0" stop-color="#fff"/><stop offset="1" stop-color="#ece8e1"/></radialGradient></defs>
 <circle cx="44" cy="44" r="22" fill="#2b2624"/><circle cx="156" cy="44" r="22" fill="#2b2624"/>
 <circle cx="44" cy="46" r="10" fill="#4a423e"/><circle cx="156" cy="46" r="10" fill="#4a423e"/>
 <ellipse cx="100" cy="100" rx="76" ry="64" fill="url(#fa)"/>
 <ellipse cx="68" cy="98" rx="17" ry="23" transform="rotate(32 68 98)" fill="#2b2624"/>
 <ellipse cx="132" cy="98" rx="17" ry="23" transform="rotate(-32 132 98)" fill="#2b2624"/>
 EYES
 <path d="M93 115q7-4 14 0q-2 7-7 8q-5-1-7-8z" fill="#2b2624"/>
 MOUTH
 <ellipse cx="50" cy="122" rx="11" ry="6" fill="#ff9e8f" opacity=".45"/><ellipse cx="150" cy="122" rx="11" ry="6" fill="#ff9e8f" opacity=".45"/>
 EXTRA
"""
EYES = """<circle cx="72" cy="93" r="6.5" fill="#fff"/><circle cx="128" cy="93" r="6.5" fill="#fff"/>
 <circle cx="73.5" cy="94" r="4" fill="#2b2624"/><circle cx="126.5" cy="94" r="4" fill="#2b2624"/>
 <circle cx="75" cy="92" r="1.4" fill="#fff"/><circle cx="128" cy="92" r="1.4" fill="#fff"/>"""
EYES_HOT = """<circle cx="72" cy="91" r="8" fill="#fff"/><circle cx="128" cy="91" r="8" fill="#fff"/>
 <circle cx="73.5" cy="92" r="5" fill="#2b2624"/><circle cx="126.5" cy="92" r="5" fill="#2b2624"/>
 <circle cx="75.5" cy="89.5" r="1.8" fill="#fff"/><circle cx="128.5" cy="89.5" r="1.8" fill="#fff"/>"""
MOUTH = '<path d="M100 123v4M92 128q8 6 16 0" stroke="#2b2624" stroke-width="2.6" fill="none" stroke-linecap="round"/>'
MOUTH_HOT = '<ellipse cx="100" cy="132" rx="9" ry="8" fill="#2b2624"/><ellipse cx="100" cy="135" rx="5" ry="3.5" fill="#ff8f80"/>'
ARMS = ('<rect x="10" y="96" width="30" height="44" rx="15" fill="#2b2624" transform="rotate(-24 25 118)"/>'
        '<rect x="160" y="96" width="30" height="44" rx="15" fill="#2b2624" transform="rotate(24 175 118)"/>')
PAWS = """<rect x="40" y="124" width="42" height="30" rx="15" fill="#2b2624"/><rect x="118" y="124" width="42" height="30" rx="15" fill="#2b2624"/>
 <path d="M51 129v7M61 128v8M71 129v7M129 129v7M139 128v8M149 129v7" stroke="#554c47" stroke-width="2.6" stroke-linecap="round"/>"""

ART = {
    "panda_head": HEAD.replace("EYES", EYES).replace("MOUTH", MOUTH).replace("EXTRA", ""),
    "panda_hot": HEAD.replace("EYES", EYES_HOT).replace("MOUTH", MOUTH_HOT).replace("EXTRA", ARMS),
    "panda_paws": PAWS,
}

with sync_playwright() as p:
    b = p.chromium.launch(channel="msedge", headless=True)
    pg = b.new_page(viewport={"width": 200, "height": 170}, device_scale_factor=3)
    for name, body in ART.items():
        pg.set_content(f'<html><body style="margin:0;background:transparent"><svg width="200" height="170" viewBox="0 0 200 170" style="display:block">{body}</svg></body></html>')
        pg.screenshot(path=str(OUT / f"{name}.png"), omit_background=True)
    b.close()
for f in sorted(OUT.glob("panda_*.png")):
    print(f.name, f.stat().st_size // 1024, "KB")
