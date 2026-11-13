// 假数据：首页的几种状态＋直播间页
const STATUS_TEXT = { starting: '启动中', offline: '没开播', live: '直播中', no_cart: '没有小黄车', error: '出错了', need_login: '要先登录抖音', captcha: '要人机验证', paused: '监控关闭中', idle: '没在盯' }
const cart = [[27, '“临序”植绒全棉牛仔夹克', 928], [28, '“沉墟”流苏提花纯羊毛开衫', 986], [30, '“沉墟”窄幅赤耳定制原牛', 596], [31, '“临序”宽松工装裤', 458], [32, '翻领拉链夹克', 399], [36, '灰蓝卷边卫裤', 299]].map(([i, t, p]) => ({ id: 'p' + i, index: i, title: t, price: p }))
const targets = [{ id: 'p12', pos: 12, explained: true }, { id: 'p31', pos: 31 }, { id: 'p36', pos: 36 }, { id: 'p42', pos: 42 }]
// state：off 监控关着｜none 开着但没选｜offline 选了但没开播｜live 直播中（expIdx 讲到几号）
function rooms(state, expIdx) {
  const exp = cart.find(c => c.index === expIdx)
  const first = state === 'live' ? { status: 'live', watch: true, explaining: exp, pace: { lo: 90, hi: 150, n: 5 } }
    : state === 'offline' ? { status: 'offline', watch: true, explaining: null }
    : state === 'off' ? { status: 'paused', watch: false, explaining: null }
    : { status: 'idle', watch: false, explaining: null }
  const idle = state === 'off' ? 'paused' : 'idle'
  return [
    { _id: '875426677831', name: 'Hypeyourself', type: 'B', targets, ...first },
    { _id: '470703347283', name: 'Anniehall Official', status: idle, watch: false, targets: [] },
    { _id: '516466932480', name: '贾乃亮滋源专场', status: idle, watch: false, targets: [{ id: 'x', pos: 3 }] },
  ]
}
const H = 3600000
const at = (h, m) => new Date().setHours(h, m, 0, 0)
const note = (t, kind, pos, title, extra) => ({ _id: 'n' + t, t, room: '875426677831', name: 'Hypeyourself', kind, pid: 'p' + pos, pos, index: pos, title, ok: true, ...(extra || {}) })
const NOTES = [
  note(at(21, 26), 'arrive', 31, '“临序”宽松工装裤'),
  note(at(21, 19), 'ahead', 31, '“临序”宽松工装裤'),
  note(at(21, 4), 'arrive', 12, '灰蓝卷边卫裤'),
  note(at(13, 58) - 24 * H, 'arrive', 3, '防脱洗发水套装', { name: '贾乃亮滋源专场', index: 1, ok: false }),
]
const mk = (state, expIdx, extra) => ({
  DEMO: false, STATUS_TEXT,
  parseRoom: () => null,
  async getRooms() { return { rooms: rooms(state, expIdx).map(r => ({ ...r, id: r._id })), pending: 0, synced: Date.now(), paused: state === 'off', notes: state === 'live' ? (expIdx >= 31 ? NOTES.slice(0, 3) : NOTES.slice(2, 3)) : [] } },
  async getNotes() { return NOTES },
  async getRoom() { const r = rooms(state, expIdx)[0]; return { room: { ...r, id: r._id }, cart } },
  async getCaptcha() { return null },
  ...(extra || {}),
})
;(async () => {
  await harness.render('index', mk('off'), {}, null, null, '① 监控关着')
  await harness.render('index', mk('none'), {}, null, null, '② 开着、还没选')
  await harness.render('index', mk('offline'), {}, null, null, '③ 选了、还没开播')
  await harness.render('index', mk('live', 27), {}, null, null, '④ 直播中')
  await harness.render('index', mk('live', 31), {}, null, null, '⑤ 到号')
  await harness.render('index', mk('live', 27), {}, null, async inst => { inst.setData({ 'others[0].x': -inst.data.delPx, 'others[1].x': -Math.round(inst.data.delPx * 0.45), 'others[1].drag': true }) }, '⑥ 往左滑（全开／一半）')
  const live = mk('live', 27)
  await harness.render('index', { ...live, async getRooms() { return { ...(await live.getRooms()), synced: Date.now() - 3 * 3600 * 1000 } } }, {}, null, null, '⑦ 电脑没回报：熊猫睡觉')
  await harness.render('index', mk('live', 32), {}, null, null, '⑧ 31 号讲完：票根多一张')
  await harness.render('stubs', mk('live', 32), {}, null, null, '⑨ 票根页')
  document.title = 'done'
})().catch(e => { document.title = 'ERR ' + e.message })
