// 数据接口。页面只调用这里的函数，不直接碰云端或本机保存。
// MODE（在 utils/config.js）：'cloud' 走云函数 api；'demo' 用示范数据，只存在手机本机。
//
// 云端模式的写入（加入、移除、设目标）不是直接改数据，而是送一笔“指令”给电脑，
// 电脑处理完才会更新。所以这些函数会等一下电脑的回复，等不到就回 { pending: true }。

const { MODE } = require('./config')

const DEMO = MODE !== 'cloud'

const STATUS_TEXT = {
  starting: '启动中',
  offline: '没开播',
  live: '直播中',
  no_cart: '没有小黄车',
  error: '出错了',
  need_login: '要先登录抖音',
  captcha: '要人机验证',
  paused: '监控关闭中',
  idle: '没在盯',
}

// 从分享文本或网址里找出直播间链接
function parseRoom(text) {
  const t = String(text || '')
  const m = t.match(/live\.douyin\.com\/(\d+)/)
  if (m) return { id: m[1], text: `https://live.douyin.com/${m[1]}` }
  const s = t.match(/https?:\/\/v\.douyin\.com\/[\w-]+\/?/)
  if (s) return { short: true, text: s[0] }
  return null
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

// ---------------- 云端 ----------------

async function call(action, data) {
  const res = await wx.cloud.callFunction({ name: 'api', data: { action, ...(data || {}) } })
  const r = res.result || {}
  if (!r.ok) {
    const err = new Error(r.error || '云端出错了')
    err.code = r.code || ''  // 'not_member'：还没加入，要输入邀请码
    throw err
  }
  return r.data
}

async function command(type, room, payload, waitMs = 25000) {
  const { id } = await call('command', { type, room, payload })
  const end = Date.now() + waitMs
  while (Date.now() < end) {
    await sleep(2000)
    const r = await call('command_result', { id })
    if (r.done) {
      if (!r.result || !r.result.ok) throw new Error((r.result && r.result.message) || '电脑处理失败')
      return r.result
    }
  }
  return { pending: true }
}

const cloudApi = {
  async getRooms() {
    const d = await call('rooms')
    return {
      rooms: d.rooms.map(r => ({ ...r, id: r._id })),
      pending: d.pending,
      synced: d.synced,
      paused: !!d.paused,
    }
  },
  // 监控开关。关着的时候电脑每分钟才同步一次，所以“开”要等久一点
  async setMonitoring(on) {
    return command(on ? 'resume' : 'pause', null, null, on ? 75000 : 25000)
  },
  async getRoom(id) {
    const d = await call('room', { id })
    return { room: d.room ? { ...d.room, id: d.room._id } : null, cart: d.cart }
  },
  async addRoom(text) {
    const p = parseRoom(text)
    if (!p) throw new Error('看不懂这个链接，请贴直播间的分享链接')
    const r = await command('add_room', p.id || null, { text: p.text })
    return { id: r.room || p.id || null, pending: !!r.pending }
  },
  async removeRoom(id) {
    return command('remove_room', id, null)
  },
  // targets: [{id, ahead, missed}]，电脑会以它当下的购物车重新对号码
  async setTargets(id, targets) {
    return command('set_targets', id, { targets })
  },
  // 盯／不盯某一间
  async setWatch(id, on) {
    return command(on ? 'watch' : 'unwatch', id, null)
  },
  // 人机验证：拿电脑截的验证框图；把用户在手机上的手势送回电脑
  async getCaptcha(id) {
    return (await call('captcha', { id })).shot
  },
  async captchaInput(id, payload) {
    return command('captcha_input', id, payload, 15000)
  },
  // 成员：生成邀请码、用邀请码加入、列出和移除成员
  async invite() {
    return call('invite')
  },
  async join(code) {
    return call('join', { code })
  },
  async members() {
    return (await call('members')).list
  },
  async removeMember(index) {
    return call('remove_member', { index })
  },
  resetDemo() {},
}

// ---------------- 示范数据 ----------------

const KEY = 'demo_state_v1'

function demoCart(prefix, n) {
  const names = ['复古羊毛毛衣', '水洗原色牛仔裤', '粗针翻领短毛衣', '头层牛皮皮带', '重磅假两件帽衫',
    '竹节棉白牛仔裤', '水洗机车夹克', '丛林工装裤', '灰蓝卷边卫裤', '翻领拉链夹克']
  const out = []
  for (let i = 1; i <= n; i++) {
    out.push({
      id: `${prefix}${i}`,
      index: i,
      title: names[(i - 1) % names.length] + (i > names.length ? ` 款${i}` : ''),
      price: 99 + ((i * 37) % 400),
    })
  }
  return out
}

function initial() {
  return {
    rooms: [
      {
        id: '470703347283', name: 'Anniehall Official', status: 'live', type: 'B',
        explaining: { id: 'a2', index: 2, title: '水洗原色牛仔裤' },
        targets: [3, 5, 8].map(i => ({ id: `a${i}`, pos: i, arrive: true, ahead: 0, missed: false })),
      },
      { id: '516466932480', name: '贾乃亮', status: 'offline', type: 'A', explaining: null, targets: [] },
    ],
    carts: { '470703347283': demoCart('a', 45) },
  }
}

function load() {
  try { return wx.getStorageSync(KEY) || initial() } catch (e) { return initial() }
}
function save(s) {
  try { wx.setStorageSync(KEY, s) } catch (e) {}
}
const wait = (v) => sleep(200).then(() => v)

const demoApi = {
  async getRooms() {
    return wait({ rooms: load().rooms, pending: 0, synced: null, paused: false })
  },
  async setMonitoring() {
    return wait({})
  },
  async getRoom(id) {
    const s = load()
    return wait({ room: s.rooms.find(r => r.id === id) || null, cart: s.carts[id] || [] })
  },
  async addRoom(text) {
    const p = parseRoom(text)
    if (!p) throw new Error('看不懂这个链接，请贴直播间的分享链接')
    const s = load()
    const id = p.id || ('short-' + Date.now())
    if (!s.rooms.find(r => r.id === id)) {
      s.rooms.unshift({ id, name: p.id ? `直播间 ${p.id}` : '（等电脑转换短链接）', status: 'starting', type: null, explaining: null, targets: [] })
      save(s)
    }
    return wait({ id, pending: false })
  },
  async removeRoom(id) {
    const s = load()
    s.rooms = s.rooms.filter(r => r.id !== id)
    delete s.carts[id]
    save(s)
    return wait({})
  },
  async setTargets(id, targets) {
    const s = load()
    const r = s.rooms.find(x => x.id === id)
    const cart = s.carts[id] || []
    if (r) {
      r.targets = targets.map(t => {
        const it = cart.find(c => c.id === t.id) || {}
        return { ...t, pos: it.index, title: it.title, arrive: true }
      })
    }
    save(s)
    return wait({})
  },
  async setWatch(id, on) {
    const s = load()
    const r = s.rooms.find(x => x.id === id)
    if (r) { r.watch = on; r.status = on ? 'starting' : 'idle' }
    save(s)
    return wait({})
  },
  async getCaptcha() {
    return wait(null)
  },
  async captchaInput() {
    return wait({ message: '验证完成' })
  },
  async invite() {
    return wait({ code: '123456', minutes: 30 })
  },
  async join() {
    return wait({ joined: true })
  },
  async members() {
    return wait([{ index: 0, me: true, tail: 'demo' }])
  },
  async removeMember() {
    return wait({})
  },
  resetDemo() {
    save(initial())
  },
}

module.exports = {
  DEMO,
  STATUS_TEXT,
  parseRoom,
  ...(DEMO ? demoApi : cloudApi),
}
