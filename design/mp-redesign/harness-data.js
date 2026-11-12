// 假資料：盯著一間直播中、號碼不變（B 型）的直播間，另外兩間沒在盯
const STATUS_TEXT = { starting: '啟動中', offline: '沒開播', live: '直播中', no_cart: '沒有小黃車', error: '出錯了', need_login: '要先登入抖音', captcha: '要人機驗證', paused: '監控關閉中', idle: '沒在盯' }
const cart = [[27, '「臨序」植絨全棉牛仔夾克', 928], [28, '「沉墟」流蘇提花純羊毛開衫', 986], [30, '「沉墟」窄幅赤耳定製原牛', 596], [31, '「臨序」寬鬆工裝褲', 458], [32, '翻領拉鍊夾克', 399], [36, '灰藍捲邊衛褲', 299]].map(([i, t, p]) => ({ id: 'p' + i, index: i, title: t, price: p }))
function rooms(expIdx) {
  const exp = cart.find(c => c.index === expIdx)
  return [
    { _id: '875426677831', name: 'Hypeyourself', status: 'live', watch: true, type: 'B', explaining: exp,
      targets: [{ id: 'p12', pos: 12, explained: true }, { id: 'p31', pos: 31 }, { id: 'p36', pos: 36 }, { id: 'p42', pos: 42 }] },
    { _id: '470703347283', name: 'Anniehall Official', status: 'idle', watch: false, targets: [] },
    { _id: '516466932480', name: '贾乃亮滋源專場', status: 'idle', watch: false, targets: [{ id: 'x', pos: 3 }] },
  ]
}
const mk = (expIdx, extra) => ({
  DEMO: false, STATUS_TEXT,
  parseRoom: () => null,
  async getRooms() { return { rooms: rooms(expIdx).map(r => ({ ...r, id: r._id })), pending: 0, synced: Date.now(), paused: false } },
  async getRoom() { const r = rooms(expIdx)[0]; return { room: { ...r, id: r._id }, cart } },
  async getCaptcha() { return null },
  ...(extra || {}),
})
;(async () => {
  await harness.render('index', mk(27), {}, '直播蹲蹲')
  await harness.render('index', mk(31), {}, '直播蹲蹲 · 到號')
  await harness.render('room', mk(27), { id: '875426677831' }, 'Hypeyourself', async inst => { inst.setData({ picked: { p31: true, p36: true }, pickedCount: 2, dirty: true, quick: '31 36' }) })
  await harness.render('verify', mk(27), { id: '875426677831' }, '人機驗證', async inst => { inst.setData({ shot: { img: SHOT, v: 1 }, stage: 0 }) })
  await harness.render('members', { ...mk(27), async invite() { return { code: '483920', minutes: 30 } }, async members() { return [{ index: 0, me: true, tail: '9x2k' }, { index: 1, me: false, tail: 'a81c' }] } }, {}, '成員與邀請', async inst => { inst.setData({ code: '483920', expiresText: '10:42', list: [{ index: 0, me: true, tail: '9x2k' }, { index: 1, me: false, tail: 'a81c' }] }) })
  document.title = 'done'
})().catch(e => { document.title = 'ERR ' + e.message })
