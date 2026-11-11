// 資料介面。頁面只呼叫這裡的函式，不直接碰雲端或本機儲存。
// MODE（在 utils/config.js）：'cloud' 走雲函數 api；'demo' 用示範資料，只存在手機本機。
//
// 雲端模式的寫入（加入、移除、設目標）不是直接改資料，而是送一筆「指令」給電腦，
// 電腦處理完才會更新。所以這些函式會等一下電腦的回覆，等不到就回 { pending: true }。

const { MODE } = require('./config')

const DEMO = MODE !== 'cloud'

const STATUS_TEXT = {
  starting: '啟動中',
  offline: '沒開播',
  live: '直播中',
  no_cart: '沒有小黃車',
  error: '出錯了',
  need_login: '要先登入抖音',
  captcha: '要人機驗證',
  paused: '監控關閉中',
  idle: '沒在盯',
}

// 從分享文字或網址裡找出直播間連結
function parseRoom(text) {
  const t = String(text || '')
  const m = t.match(/live\.douyin\.com\/(\d+)/)
  if (m) return { id: m[1], text: `https://live.douyin.com/${m[1]}` }
  const s = t.match(/https?:\/\/v\.douyin\.com\/[\w-]+\/?/)
  if (s) return { short: true, text: s[0] }
  return null
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms))

// ---------------- 雲端 ----------------

async function call(action, data) {
  const res = await wx.cloud.callFunction({ name: 'api', data: { action, ...(data || {}) } })
  const r = res.result || {}
  if (!r.ok) {
    const err = new Error(r.error || '雲端出錯了')
    err.code = r.code || ''  // 'not_member'：還沒加入，要輸入邀請碼
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
      if (!r.result || !r.result.ok) throw new Error((r.result && r.result.message) || '電腦處理失敗')
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
  // 監控開關。關著的時候電腦每分鐘才同步一次，所以「開」要等久一點
  async setMonitoring(on) {
    return command(on ? 'resume' : 'pause', null, null, on ? 75000 : 25000)
  },
  async getRoom(id) {
    const d = await call('room', { id })
    return { room: d.room ? { ...d.room, id: d.room._id } : null, cart: d.cart }
  },
  async addRoom(text) {
    const p = parseRoom(text)
    if (!p) throw new Error('看不懂這個連結，請貼直播間的分享連結')
    const r = await command('add_room', p.id || null, { text: p.text })
    return { id: r.room || p.id || null, pending: !!r.pending }
  },
  async removeRoom(id) {
    return command('remove_room', id, null)
  },
  // targets: [{id, ahead, missed}]，電腦會以它當下的購物車重新對號碼
  async setTargets(id, targets) {
    return command('set_targets', id, { targets })
  },
  // 盯／不盯某一間
  async setWatch(id, on) {
    return command(on ? 'watch' : 'unwatch', id, null)
  },
  // 人機驗證：拿電腦截的驗證框圖；把使用者在手機上的手勢送回電腦
  async getCaptcha(id) {
    return (await call('captcha', { id })).shot
  },
  async captchaInput(id, payload) {
    return command('captcha_input', id, payload, 15000)
  },
  // 成員：產生邀請碼、用邀請碼加入、列出和移除成員
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

// ---------------- 示範資料 ----------------

const KEY = 'demo_state_v1'

function demoCart(prefix, n) {
  const names = ['復古羊毛毛衣', '水洗原色牛仔褲', '粗針翻領短毛衣', '頭層牛皮皮帶', '重磅假兩件帽衫',
    '竹節棉白牛仔褲', '水洗機車夾克', '叢林工裝褲', '灰藍捲邊衛褲', '翻領拉鍊夾克']
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
        explaining: { id: 'a2', index: 2, title: '水洗原色牛仔褲' },
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
    if (!p) throw new Error('看不懂這個連結，請貼直播間的分享連結')
    const s = load()
    const id = p.id || ('short-' + Date.now())
    if (!s.rooms.find(r => r.id === id)) {
      s.rooms.unshift({ id, name: p.id ? `直播間 ${p.id}` : '（等電腦轉換短連結）', status: 'starting', type: null, explaining: null, targets: [] })
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
    return wait({ message: '驗證完成' })
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
