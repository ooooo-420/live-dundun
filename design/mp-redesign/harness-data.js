// 假数据：盯着一间直播中、号码不变（B 型）的直播间，另外两间没在盯
const STATUS_TEXT = { starting: '启动中', offline: '没开播', live: '直播中', no_cart: '没有小黄车', error: '出错了', need_login: '要先登录抖音', captcha: '要人机验证', paused: '监控关闭中', idle: '没在盯' }
const cart = [[27, '“临序”植绒全棉牛仔夹克', 928], [28, '“沉墟”流苏提花纯羊毛开衫', 986], [30, '“沉墟”窄幅赤耳定制原牛', 596], [31, '“临序”宽松工装裤', 458], [32, '翻领拉链夹克', 399], [36, '灰蓝卷边卫裤', 299]].map(([i, t, p]) => ({ id: 'p' + i, index: i, title: t, price: p }))
function rooms(expIdx) {
  const exp = cart.find(c => c.index === expIdx)
  return [
    { _id: '875426677831', name: 'Hypeyourself', status: 'live', watch: true, type: 'B', explaining: exp,
      targets: [{ id: 'p12', pos: 12, explained: true }, { id: 'p31', pos: 31 }, { id: 'p36', pos: 36 }, { id: 'p42', pos: 42 }] },
    { _id: '470703347283', name: 'Anniehall Official', status: 'idle', watch: false, targets: [] },
    { _id: '516466932480', name: '贾乃亮滋源专场', status: 'idle', watch: false, targets: [{ id: 'x', pos: 3 }] },
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
  await harness.render('index', mk(27), {}, '', null, '首页 · 直播蹲蹲')
  await harness.render('index', mk(27), {}, '', async inst => { inst.setData({ brand: '目候' }) }, '首页 · 目候')
  await harness.render('index', mk(31), {}, '', null, '首页 · 到号')
  await harness.render('room', mk(27), { id: '875426677831' }, 'Hypeyourself', async inst => { inst.setData({ picked: { p31: true, p36: true }, pickedCount: 2, dirty: true, quick: '31 36' }) })
  await harness.render('verify', mk(27), { id: '875426677831' }, '人机验证', async inst => { inst.setData({ shot: { img: SHOT, v: 1 }, stage: 0 }) })
  await harness.render('members', { ...mk(27), async invite() { return { code: '483920', minutes: 30 } }, async members() { return [{ index: 0, me: true, tail: '9x2k' }, { index: 1, me: false, tail: 'a81c' }] } }, {}, '成员与邀请', async inst => { inst.setData({ code: '483920', expiresText: '10:42', list: [{ index: 0, me: true, tail: '9x2k' }, { index: 1, me: false, tail: 'a81c' }] }) })
  document.title = 'done'
})().catch(e => { document.title = 'ERR ' + e.message })
