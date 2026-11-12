// 假数据：首页的几种状态＋直播间页
const STATUS_TEXT = { starting: '启动中', offline: '没开播', live: '直播中', no_cart: '没有小黄车', error: '出错了', need_login: '要先登录抖音', captcha: '要人机验证', paused: '监控关闭中', idle: '没在盯' }
const cart = [[27, '“临序”植绒全棉牛仔夹克', 928], [28, '“沉墟”流苏提花纯羊毛开衫', 986], [30, '“沉墟”窄幅赤耳定制原牛', 596], [31, '“临序”宽松工装裤', 458], [32, '翻领拉链夹克', 399], [36, '灰蓝卷边卫裤', 299]].map(([i, t, p]) => ({ id: 'p' + i, index: i, title: t, price: p }))
const targets = [{ id: 'p12', pos: 12, explained: true }, { id: 'p31', pos: 31 }, { id: 'p36', pos: 36 }, { id: 'p42', pos: 42 }]
// state：off 监控关着｜none 开着但没选｜offline 选了但没开播｜live 直播中（expIdx 讲到几号）
function rooms(state, expIdx) {
  const exp = cart.find(c => c.index === expIdx)
  const first = state === 'live' ? { status: 'live', watch: true, explaining: exp }
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
const mk = (state, expIdx, extra) => ({
  DEMO: false, STATUS_TEXT,
  parseRoom: () => null,
  async getRooms() { return { rooms: rooms(state, expIdx).map(r => ({ ...r, id: r._id })), pending: 0, synced: Date.now(), paused: state === 'off' } },
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
  document.title = 'done'
})().catch(e => { document.title = 'ERR ' + e.message })
