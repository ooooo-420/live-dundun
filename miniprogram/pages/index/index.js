const api = require('../../utils/api')
const { NAME } = require('../../utils/brand')
const buzz = require('../../utils/buzz')

function ago(ms) {
  if (!ms) return '从没连上'
  const s = Math.round((Date.now() - ms) / 1000)
  if (s < 90) return '刚刚'
  if (s < 3600) return `${Math.round(s / 60)} 分钟前`
  return `${Math.round(s / 3600)} 小时前`
}

function windowWidth() {
  try { return (wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync()).windowWidth } catch (e) { return 375 }
}
const DEL_PX = Math.round(160 * windowWidth() / 750)  // 卡片往左滑开的距离 160rpx（删除键＋中间的缝）
const GAP_PX = Math.round(16 * windowWidth() / 750)   // 卡片和删除键之间的缝 16rpx

// 自订导航栏：对齐微信右上角的胶囊按钮（取不到就用 iPhone 常见的值）
function navLayout() {
  const ww = windowWidth()
  const tog = 50 * ww / 750  // 小开关高 50rpx
  try {
    const m = wx.getMenuButtonBoundingClientRect()
    if (m && m.height) return { top: m.top, h: m.height, right: Math.round(ww - m.left + 12), togTop: Math.round(m.top + (m.height - tog) / 2) }
  } catch (e) {}
  return { top: 50, h: 32, right: 110, togTop: Math.round(50 + (32 - tog) / 2) }
}

const PILL = { live: '● 直播中', captcha: '要验证', starting: '打开中', offline: '没开播', no_cart: '没有小黄车', need_login: '要登录', error: '出错了', idle: '没在盯', paused: '监控关着' }
const WAIT = {
  starting: '电脑正在打开直播间…',
  offline: '还没开播，开播后自动开始盯',
  captcha: '等你过一下验证',
  no_cart: '这场没有小黄车',
  need_login: '电脑要先登录抖音',
  error: '电脑读不到这间，稍后重试',
}

// 号码票上要显示的东西：目标标签、到号了没、进度和一句说明
function ticket(r) {
  const exp = r.explaining
  const list = (r.targets || []).slice().sort((a, b) => a.pos - b.pos)
  const hit = exp ? list.find(t => t.id === exp.id) : null
  const left = list.filter(t => !t.explained && t !== hit)
  const upcoming = exp && exp.index ? left.find(t => t.pos > exp.index) || left[0] : left[0]
  const chips = list.map(t => ({
    key: t.id,
    text: `${t.pos}`,
    cls: t === hit || (!hit && t === upcoming) ? 'next' : t.explained ? 'done' : '',
  }))
  // 号码不会变的直播间（B 型）才算得出“还差几件”
  const gap = r.type === 'B' && exp && exp.index && upcoming && upcoming.pos > exp.index ? upcoming.pos - exp.index : 0
  let eta = ''   // 第二段的一句话（没有三格可放时才用）
  let prog = 0
  const fields = []  // 第三段的格子：{ k 小标签, v 大数字, u 单位或文字 }
  if (!list.length) eta = '还没设目标，点这张票去选号'
  else if (r.status === 'live' && exp && exp.id) {
    if (hit) fields.push({ k: '已叫你', u: '微信 ✓' })
    if (upcoming) fields.push({ k: '下一个', v: upcoming.pos, u: '号' })
    else fields.push({ k: '目标', u: hit ? '最后一个' : '都讲过了' })
    if (gap) {
      fields.push({ k: '还差', v: gap, u: '件' })
      if (!hit) prog = Math.round(exp.index / upcoming.pos * 100)
      // 电脑估的每件秒数 × 还差几件 → 大约几分钟（给范围；跳着讲或样本太少时电脑不给）
      if (!hit && r.pace && r.pace.lo) {
        const lo = Math.max(1, Math.round(r.pace.lo * gap / 60))
        const hi = Math.max(lo, Math.round(r.pace.hi * gap / 60))
        fields.push({ k: '大约', v: lo === hi ? `${lo}` : `${lo}–${hi}`, u: '分' })
      }
    } else if (upcoming && left.length > 1) fields.push({ k: '还剩', v: left.length, u: '个目标' })
  } else if (!left.length) eta = '目标都讲过了'
  else eta = `盯着 ${left.length} 个目标`
  return { chips, eta, prog, fields, hot: !!hit }
}

const pad = n => (n < 10 ? '0' : '') + n
const hhmm = ms => { const d = new Date(ms); return `${pad(d.getHours())}:${pad(d.getMinutes())}` }
const KIND = { arrive: ['到了', ''], ahead: ['快到了', 'near'], missed: ['可能错过', 'miss'] }

Page({
  data: {
    demo: api.DEMO,
    brand: NAME,
    nav: navLayout(),
    rooms: [],
    hero: null,
    others: [],
    stubs: [],
    stubCount: 0,
    fly: null,
    headline: '',
    loading: true,
    busy: false,
    pcText: '',
    pcOk: true,
    sleep: false,
    pending: 0,
    error: '',
    needJoin: false,
    code: '',
    monitoring: true,
    switching: false,
    delPx: DEL_PX,
    gapPx: GAP_PX,
  },

  onLoad() {
    this.last = null  // 上一次号码票的 {id, expId, index, title, hot}
    this.stubIds = null  // 上一次看到的票根 id
  },

  onShow() {
    this.refresh()
    this.timer = setInterval(() => this.refresh(), 15000)
  },
  onHide() { clearInterval(this.timer) },
  onUnload() { clearInterval(this.timer) },

  onPullDownRefresh() {
    this.refresh().then(() => wx.stopPullDownRefresh())
  },

  async refresh() {
    let d
    try {
      d = await api.getRooms()
    } catch (e) {
      if (e.code === 'not_member') this.setData({ loading: false, needJoin: true, error: '' })
      else this.setData({ loading: false, error: e.message })
      return
    }
    const openX = {}
    for (const r of this.data.others) if (r.x) openX[r.id] = r.x
    const rooms = d.rooms.map(r => ({
      ...r,
      statusText: api.STATUS_TEXT[r.status] || r.status,
      live: r.status === 'live',
      alert: r.status === 'captcha' || r.status === 'need_login' || r.status === 'error',
      watch: !!r.watch,
    }))
    const monitoring = this.switching ? this.data.monitoring : !d.paused
    const pcOk = api.DEMO || !!(d.synced && Date.now() - d.synced < 3 * 60 * 1000)
    const sleep = !pcOk  // 电脑超过 3 分钟没回报：熊猫睡觉，不显示可能过期的号码

    // 号码票：正在盯的那一间（直播中的优先，其次是等验证的）
    const watched = rooms.filter(r => r.watch && r.status !== 'idle' && r.status !== 'paused')
    const rank = r => (r.status === 'live' ? 0 : r.status === 'captcha' ? 1 : 2)
    const pick = monitoring && !sleep ? watched.sort((a, b) => rank(a) - rank(b))[0] : null
    if (monitoring && !sleep) watched.forEach(buzz.check)  // 到号／快到号：震动
    let hero = null
    let fly = null
    if (pick) {
      const t = ticket(pick)
      const exp = pick.explaining
      hero = {
        ...pick, ...t,
        pill: PILL[pick.status] || pick.statusText,
        waitText: WAIT[pick.status] || (pick.live ? '等主播讲解商品' : pick.statusText),
        bump: false,
      }
      const L = this.last
      if (L && L.id === pick.id && exp && exp.id && L.expId && L.expId !== exp.id && L.index) {
        hero.bump = true  // 换号：旧存根撕走、熊猫擡手
        fly = { name: L.name, pill: L.pill, index: L.index, title: L.title, hot: L.hot }
      }
      this.last = { id: pick.id, expId: exp && exp.id, index: exp && exp.index, title: exp && exp.title, hot: t.hot, name: pick.name, pill: hero.pill }
    } else {
      this.last = null
    }

    const others = rooms.filter(r => !hero || r.id !== hero.id).map(r => ({
      ...r,
      subText: (r.status === 'idle' ? '没在盯' : r.statusText) + ((r.targets || []).length ? ` · ${r.targets.length} 个目标` : ''),
      x: openX[r.id] || 0,
      drag: false,
      watchBusy: false,
    }))
    // 票根：最近叫过你的号，叠在票下面，只露最近两张。正在“到了”的那张还在票上，等撕下来才落进来
    const notes = (d.notes || []).filter(x => !(hero && hero.hot && x.kind === 'arrive' && x.room === hero.id && hero.explaining && x.pid === hero.explaining.id))
    const known = this.stubIds  // 第一次载入时是 null：不播“落下来”的动画
    const stubs = notes.slice(0, 2).reverse().map(x => ({
      id: x._id || x.id,
      n: x.index || x.pos,
      label: (KIND[x.kind] || KIND.arrive)[0],
      cls: (KIND[x.kind] || KIND.arrive)[1],
      time: hhmm(x.t),
      fresh: !!(known && !known[x._id || x.id]),
    }))
    this.stubIds = {}
    notes.forEach(x => { this.stubIds[x._id || x.id] = true })

    const n = watched.length
    this.setData({
      stubs, stubCount: notes.length >= 10 ? '10+' : notes.length,
      loading: false,
      error: '',
      needJoin: false,
      pending: d.pending,
      monitoring,
      pcText: api.DEMO ? '' : ago(d.synced),
      pcOk, sleep,
      headline: !monitoring ? '监控关着 · 不盯直播、不发通知' : n ? `电脑在线 · 帮你盯着 ${n} 间` : '电脑准备好了 · 选一间来盯',
      rooms, hero, others, fly,
    })
    if (hero && hero.bump) {
      clearTimeout(this.bumpTimer)
      this.bumpTimer = setTimeout(() => this.setData({ 'hero.bump': false, fly: null }), 1150)
    }
  },

  // ---------- 号码票 ----------

  openHero() {
    if (this.data.hero) wx.navigateTo({ url: `/pages/room/room?id=${this.data.hero.id}` })
  },

  openStubs() {
    wx.navigateTo({ url: '/pages/stubs/stubs' })
  },

  goVerifyHero() {
    if (this.data.hero) wx.navigateTo({ url: `/pages/verify/verify?id=${this.data.hero.id}` })
  },

  heroMenu() {
    const h = this.data.hero
    if (!h) return
    wx.showActionSheet({
      itemList: ['不盯这间', '删除这个直播间'],
      itemColor: '#1f2a22',
      success: (res) => {
        if (res.tapIndex === 0) this.setWatch(h.id, false)
        else this.confirmRemove(h.id, h.name)
      },
    })
  },

  // ---------- 小卡片：往左滑删除（手指往左拖，删除键从右边出来） ----------

  touchStart(e) {
    const i = e.currentTarget.dataset.i
    const t = e.touches[0]
    this.sw = { i, x0: t.clientX, y0: t.clientY, base: this.data.others[i].x || 0, dir: '' }
    this.swiped = false
  },

  touchMove(e) {
    const s = this.sw
    if (!s) return
    const t = e.touches[0]
    const dx = t.clientX - s.x0
    const dy = t.clientY - s.y0
    if (!s.dir) {
      if (Math.abs(dx) < 6 && Math.abs(dy) < 6) return
      s.dir = Math.abs(dx) > Math.abs(dy) ? 'h' : 'v'
    }
    if (s.dir !== 'h') return
    this.swiped = true
    const x = Math.max(-DEL_PX, Math.min(0, s.base + dx))
    this.setData({ [`others[${s.i}].x`]: x, [`others[${s.i}].drag`]: true })
  },

  touchEnd() {
    const s = this.sw
    this.sw = null
    if (!s || s.dir !== 'h') return
    const cur = this.data.others[s.i].x
    const patch = { [`others[${s.i}].drag`]: false, [`others[${s.i}].x`]: cur < -DEL_PX / 2 ? -DEL_PX : 0 }
    this.data.others.forEach((r, j) => { if (j !== s.i && r.x) patch[`others[${j}].x`] = 0 })  // 一次只开一张
    this.setData(patch)
  },

  open(e) {
    if (this.swiped) {
      this.swiped = false
      return
    }
    const i = e.currentTarget.dataset.i
    const r = this.data.others[i]
    if (r.x) {  // 开着删除键时点一下＝收回
      this.setData({ [`others[${i}].x`]: 0 })
      return
    }
    if (r.status === 'captcha') wx.navigateTo({ url: `/pages/verify/verify?id=${r.id}` })
    else wx.navigateTo({ url: `/pages/room/room?id=${r.id}` })
  },

  askRemove(e) {
    const r = this.data.others.find(x => x.id === e.currentTarget.dataset.id)
    if (r) this.confirmRemove(r.id, r.name)
  },

  confirmRemove(id, name) {
    wx.showModal({
      title: `删除“${name}”？`,
      content: '电脑会停止监控这间，目标设置也会一起删掉。',
      confirmText: '删除',
      confirmColor: '#d9534a',
      success: async (r) => {
        if (!r.confirm) {
          const patch = {}
          this.data.others.forEach((x, j) => { if (x.x) patch[`others[${j}].x`] = 0 })
          this.setData(patch)
          return
        }
        wx.showLoading({ title: '电脑处理中' })
        try {
          const res = await api.removeRoom(id)
          wx.hideLoading()
          wx.showToast({ title: res.pending ? '已送出，电脑稍后处理' : '已删除', icon: 'none' })
        } catch (err) {
          wx.hideLoading()
          wx.showToast({ title: err.message, icon: 'none' })
        }
        this.refresh()
      },
    })
  },

  // ---------- 盯／不盯 ----------

  toggleWatch(e) {
    const id = e.currentTarget.dataset.id
    const r = this.data.others.find(x => x.id === id)
    if (r && !r.watchBusy) this.setWatch(id, !r.watch)
  },

  async setWatch(id, on) {
    const i = this.data.others.findIndex(x => x.id === id)
    if (i >= 0) this.setData({ [`others[${i}].watch`]: on, [`others[${i}].watchBusy`]: true })
    try {
      const res = await api.setWatch(id, on)
      if (res.pending) wx.showToast({ title: '已送出，电脑稍后处理', icon: 'none' })
    } catch (err) {
      if (i >= 0) this.setData({ [`others[${i}].watch`]: !on })
      wx.showToast({ title: err.message, icon: 'none' })
    }
    if (i >= 0) this.setData({ [`others[${i}].watchBusy`]: false })
    this.refresh()
  },

  // ---------- 其他 ----------

  onCode(e) {
    this.setData({ code: e.detail.value })
  },

  async joinNow() {
    try {
      await api.join(this.data.code)
      wx.showToast({ title: '已加入', icon: 'success' })
      this.setData({ code: '' })
      this.refresh()
    } catch (e) {
      wx.showModal({ title: '没加入成功', content: e.message, showCancel: false })
    }
  },

  // 熊猫就是监控开关：关着时点它＝打开（它会爬出来）；开着时点它，问要不要关
  tapPanda() {
    if (this.switching) return
    if (this.data.sleep) {
      wx.showModal({ title: '电脑睡着了', content: `上次回报：${this.data.pcText}。电脑可能关机、睡眠或断网了，或者监控程序没在运行。电脑一回来，熊猫就会醒。`, showCancel: false, confirmText: '知道了' })
      return
    }
    if (!this.data.monitoring) {
      this.toggleMonitoring()
      return
    }
    wx.showActionSheet({
      itemList: ['关闭监控'],
      itemColor: '#d9534a',
      success: (r) => { if (r.tapIndex === 0) this.toggleMonitoring() },
    })
  },

  async toggleMonitoring() {
    if (this.switching) return
    const on = !this.data.monitoring
    this.switching = true
    this.setData({ monitoring: on, switching: true })  // 熊猫先动，再等电脑
    if (!on) wx.showLoading({ title: '正在关闭监控' })  // 打开时熊猫爬出来就是回馈，不用转圈
    try {
      const r = await api.setMonitoring(on)
      wx.hideLoading()
      if (r.pending) {
        wx.showModal({ title: '已送出', content: '电脑还没处理完，等一下回来看。电脑要开着、监控程序要在运行。', showCancel: false })
      } else {
        wx.showToast({ title: on ? '电脑准备好了，选一间来盯' : '监控已关闭', icon: 'none' })
      }
    } catch (err) {
      wx.hideLoading()
      this.setData({ monitoring: !on })  // 没成功：熊猫退回原来的样子
      wx.showToast({ title: err.message, icon: 'none' })
    }
    this.switching = false
    this.setData({ switching: false })
    this.refresh()
  },

  openMembers() {
    wx.navigateTo({ url: '/pages/members/members' })
  },

  // 一个键：读剪贴板里的抖音链接，加入清单；要不要开始盯，加入后再问（不自动盯）
  async pasteAdd() {
    if (this.data.busy) return
    let text = ''
    try { text = (await wx.getClipboardData()).data || '' } catch (e) {}
    if (!api.parseRoom(text)) {
      wx.showModal({ title: '剪贴板里没有直播链接', content: '在抖音直播间按“分享 → 复制链接”，再回来按这个键。', showCancel: false })
      return
    }
    const ask = (o) => new Promise(r => wx.showModal({ ...o, success: x => r(x.confirm), fail: () => r(false) }))
    if (!await ask({ title: '加入这个直播间？', content: text.length > 60 ? text.slice(0, 60) + '…' : text, confirmText: '加入', confirmColor: '#34794c' })) return
    this.setData({ busy: true })
    wx.showLoading({ title: '电脑处理中' })
    let r = null
    try {
      r = await api.addRoom(text)
      wx.hideLoading()
      await this.refresh()
    } catch (e) {
      wx.hideLoading()
      wx.showToast({ title: e.message, icon: 'none', duration: 3000 })
    }
    this.setData({ busy: false })
    if (!r) return
    if (r.pending) {
      wx.showModal({ title: '链接已存好', content: '电脑上的监控程序现在没在运行。电脑一开，就会把这间加进来。', showCancel: false })
      return
    }
    if (!this.data.monitoring) {
      wx.showToast({ title: '已加入。点熊猫打开监控后，再选要盯哪间', icon: 'none', duration: 2600 })
      return
    }
    if (await ask({ title: '已加入，现在开始盯这间吗？', content: '选“先不”的话，之后打开它右边的开关就行。', confirmText: '开始盯', cancelText: '先不', confirmColor: '#34794c' })) {
      await this.setWatch(r.id, true)
      if (r.id) wx.navigateTo({ url: `/pages/room/room?id=${r.id}` })
    }
  },

  resetDemo() {
    api.resetDemo()
    this.refresh()
  },
})
