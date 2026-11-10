"""讀取抖音網頁版直播間：開播狀態、購物車清單、講解中的商品。

只讀頁面資料，不下單、不發言。讀法依賴抖音網頁的 React 內部資料，抖音改版時這裡最可能要修。
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from playwright.async_api import Page

# 在頁面裡掃描所有帶 promotion_id 的商品資料。
# 購物車裡的商品 index >= 1（畫面上的序號）；右側浮動「講解中」卡的 index 是 0。
SCAN_JS = r"""
() => {
  const fiberOf = el => { const k = Object.keys(el).find(k => k.startsWith('__reactFiber')); return k ? el[k] : null; };
  const promoOf = (el, depth) => {
    let f = fiberOf(el);
    for (let i = 0; i < depth && f; i++, f = f.return) {
      const p = f.memoizedProps;
      if (p && typeof p === 'object') {
        for (const v of [p.promotion, p.itemInfo]) {
          if (v && typeof v === 'object' && v.promotion_id) return v;
        }
      }
    }
    return null;
  };
  const brief = v => ({
    id: String(v.promotion_id),
    index: typeof v.index === 'number' ? v.index : null,
    title: String(v.title || ''),
    price: typeof v.min_price === 'number' ? v.min_price / 100 : null,
  });
  const text = document.body ? document.body.innerText : '';
  const ended = /直播已结束|直播已結束|暂未开播|主播暂时离开/.test(text);
  const leaves = [...document.querySelectorAll('div,span')].filter(e => e.children.length === 0);
  const hasCartButton = leaves.some(e => e.textContent.trim() === '全部商品');
  // 抖音的滑塊驗證：通常是 id 含 captcha 的容器或 verify 網域的 iframe
  // 驗證完成後容器可能只是隱藏、還留在頁面裡，所以只算看得見的
  const shown = e => { const r = e.getBoundingClientRect(); return r.width > 20 && r.height > 20 && getComputedStyle(e).visibility !== 'hidden'; };
  const capEl = [...document.querySelectorAll('#captcha_container, [id*="captcha" i] iframe, iframe[src*="verify"], iframe[src*="captcha"]')].find(shown);
  const capText = leaves.find(e => /拖动.*滑块|完成.*拼图|请完成下列验证/.test(e.textContent) && shown(e));
  const captcha = !!(capEl || capText);
  const captchaWhy = capEl ? (capEl.id || capEl.tagName) + ' ' + (capEl.src || '').slice(0, 60) : capText ? capText.textContent.slice(0, 30) : '';
  const needLogin =leaves.some(e => /^(扫码登录|登录后抖音更懂你)$/.test(e.textContent.trim()) && e.getBoundingClientRect().width > 0);

  const items = new Map();
  let floating = null;
  for (const el of document.querySelectorAll('div')) {
    const v = promoOf(el, 3);
    if (!v) continue;
    const b = brief(v);
    if (b.index && b.index >= 1) { if (!items.has(b.id)) items.set(b.id, b); }
    // 浮動卡在購物車打開時會被隱藏（寬高 0），但資料還在，所以不檢查可見性
    else if (!floating) floating = b;
  }
  // 購物車裡標「讲解中」的那一列
  let badge = null;
  for (const el of leaves) {
    if (el.textContent.trim() === '讲解中') { const v = promoOf(el, 12); if (v) { badge = brief(v); break; } }
  }
  return {
    ended, hasCartButton, needLogin, captcha, captchaWhy,
    items: [...items.values()].sort((a, b) => a.index - b.index),
    floating, badge,
    title: document.title,
  };
}
"""

# 把購物車捲到底，直到商品數不再增加。
LOAD_ALL_JS = r"""
async () => {
  const fiberOf = el => { const k = Object.keys(el).find(k => k.startsWith('__reactFiber')); return k ? el[k] : null; };
  const isItem = el => {
    let f = fiberOf(el);
    for (let i = 0; i < 3 && f; i++, f = f.return) {
      const p = f.memoizedProps;
      if (p && p.promotion && p.promotion.promotion_id && p.promotion.index >= 1) return true;
    }
    return false;
  };
  const row = [...document.querySelectorAll('div')].find(isItem);
  if (!row) return { ok: false, reason: 'no-cart-rows' };
  let c = row;
  while (c && !(c.scrollHeight > c.clientHeight + 10 && /(auto|scroll)/.test(getComputedStyle(c).overflowY))) c = c.parentElement;
  if (!c) return { ok: true, reason: 'not-scrollable' };
  let last = -1, same = 0;
  for (let i = 0; i < 40 && same < 3; i++) {
    c.scrollTop = c.scrollHeight;
    await new Promise(r => setTimeout(r, 1200));
    const n = c.scrollHeight;
    if (n === last) same++; else { same = 0; last = n; }
  }
  c.scrollTop = 0;
  return { ok: true };
}
"""


@dataclass
class Scan:
    ended: bool = False
    has_cart_button: bool = False
    need_login: bool = False
    captcha: bool = False
    captcha_why: str = ""
    items: list[dict] = field(default_factory=list)
    floating: dict | None = None
    badge: dict | None = None
    title: str = ""

    @property
    def explaining_id(self) -> str | None:
        if self.floating:
            return self.floating["id"]
        if self.badge:
            return self.badge["id"]
        return None


async def scan(page: Page) -> Scan:
    r = await page.evaluate(SCAN_JS)
    return Scan(
        ended=r["ended"],
        has_cart_button=r["hasCartButton"],
        need_login=r["needLogin"],
        captcha=r["captcha"],
        captcha_why=r.get("captchaWhy") or "",
        items=r["items"],
        floating=r["floating"],
        badge=r["badge"],
        title=r["title"],
    )


KEEP_PLAYING_JS = r"""
() => {
  let resumed = 0;
  for (const v of document.querySelectorAll('video')) {
    v.muted = true;
    if (v.paused) { v.play().catch(() => {}); resumed++; }
  }
  return resumed;
}
"""


async def keep_playing(page: Page) -> int:
    """直播影片靜音；被暫停就叫它繼續播（在頁面內呼叫 play()，不是模擬滑鼠）。回傳恢復了幾個。"""
    return await page.evaluate(KEEP_PLAYING_JS)


async def open_cart(page: Page) -> bool:
    btn = page.get_by_text("全部商品", exact=True).first
    try:
        await btn.click(timeout=5000)
    except Exception:
        return False
    await asyncio.sleep(2.5)
    return True


async def close_cart(page: Page) -> None:
    await page.keyboard.press("Escape")
    await asyncio.sleep(0.8)


async def load_all(page: Page) -> dict:
    return await page.evaluate(LOAD_ALL_JS)


async def refresh_cart(page: Page) -> Scan:
    """關掉再打開購物車，讓它重新向抖音要最新的清單，再全部載入。"""
    await close_cart(page)
    s = await scan(page)
    if s.items:  # Escape 沒關掉，改點一次按鈕切換
        await open_cart(page)
        await asyncio.sleep(0.8)
    await open_cart(page)
    await load_all(page)
    return await stable_scan(page)


def consistent(items: list[dict]) -> bool:
    """清單正在重排時會讀到重複或跳號的序號，這種清單不能用。"""
    idx = [i["index"] for i in items]
    return bool(idx) and len(set(idx)) == len(idx) and idx == list(range(1, len(idx) + 1))


async def stable_scan(page: Page, tries: int = 6) -> Scan:
    """連續兩次讀到一樣且序號連續的清單才算數，最多等 tries*2 秒。"""
    prev = await scan(page)
    for _ in range(tries):
        await asyncio.sleep(2)
        cur = await scan(page)
        same = [(i["id"], i["index"]) for i in cur.items] == [(i["id"], i["index"]) for i in prev.items]
        if same and consistent(cur.items):
            return cur
        prev = cur
    return prev
