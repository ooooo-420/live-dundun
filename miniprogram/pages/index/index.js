const api = require('../../utils/api')

function ago(ms) {
  if (!ms) return '從沒連上'
  const s = Math.round((Date.now() - ms) / 1000)
  if (s < 90) return '剛剛'
  if (s < 3600) return `${Math.round(s / 60)} 分鐘前`
  return `${Math.round(s / 3600)} 小時前`
}

function windowWidth() {
  try { return (wx.getWindowInfo ? wx.getWindowInfo() : wx.getSystemInfoSync()).windowWidth } catch (e) { return 375 }
}
const DEL_PX = Math.round(160 * windowWidth() / 750)  // 刪除鍵寬 160rpx

const PILL = { live: '● 直播中', captcha: '要驗證', starting: '打開中', offline: '沒開播', no_cart: '沒有小黃車', need_login: '要登入', error: '出錯了', idle: '沒在盯', paused: '監控關著' }
const WAIT = {
  starting: '電腦正在打開直播間…',
  offline: '還沒開播，開播後自動開始盯',
  captcha: '等你過一下驗證',
  no_cart: '這場沒有小黃車',
  need_login: '電腦要先登入抖音',
  error: '電腦讀不到這間，稍後重試',
}

// 號碼票上要顯示的東西：目標標籤、到號了沒、進度和一句說明
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
  let eta = ''
  let prog = 0
  if (hit) eta = '已經發微信提醒你' + (upcoming ? ` · 下一個 ${upcoming.pos} 號` : '')
  else if (!list.length) eta = '還沒設目標，點這張票去選號'
  else if (!left.length) eta = '目標都講過了'
  else if (r.type === 'B' && exp && exp.index && upcoming && upcoming.pos > exp.index) {
    eta = `還差 ${upcoming.pos - exp.index} 件到 ${upcoming.pos} 號`
    prog = Math.round(exp.index / upcoming.pos * 100)
  } else eta = `盯著 ${left.length} 個目標`
  return { chips, eta, prog, hot: !!hit }
}

Page({
  data: {
    demo: api.DEMO,
    rooms: [],
    hero: null,
    others: [],
    fly: null,
    headline: '',
    loading: true,
    busy: false,
    pcText: '',
    pcOk: true,
    pending: 0,
    error: '',
    needJoin: false,
    code: '',
    monitoring: true,
    switching: false,
    delPx: DEL_PX,
  },

  onLoad() {
    this.last = null  // 上一次號碼票的 {id, expId, index, title, hot}
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

    // 號碼票：正在盯的那一間（直播中的優先，其次是等驗證的）
    const watched = rooms.filter(r => r.watch && r.status !== 'idle' && r.status !== 'paused')
    const rank = r => (r.status === 'live' ? 0 : r.status === 'captcha' ? 1 : 2)
    const pick = monitoring ? watched.sort((a, b) => rank(a) - rank(b))[0] : null
    let hero = null
    let fly = null
    if (pick) {
      const t = ticket(pick)
      const exp = pick.explaining
      hero = {
        ...pick, ...t,
        pill: PILL[pick.status] || pick.statusText,
        waitText: WAIT[pick.status] || (pick.live ? '等主播講解商品' : pick.statusText),
        bump: false,
      }
      const L = this.last
      if (L && L.id === pick.id && exp && exp.id && L.expId && L.expId !== exp.id && L.index) {
        hero.bump = true  // 換號：舊存根撕走、熊貓抬手
        fly = { name: L.name, pill: L.pill, index: L.index, title: L.title, hot: L.hot }
      }
      this.last = { id: pick.id, expId: exp && exp.id, index: exp && exp.index, title: exp && exp.title, hot: t.hot, name: pick.name, pill: hero.pill }
    } else {
      this.last = null
    }

    const others = rooms.filter(r => !hero || r.id !== hero.id).map(r => ({
      ...r,
      subText: (r.status === 'idle' ? '沒在盯' : r.statusText) + ((r.targets || []).length ? ` · ${r.targets.length} 個目標` : ''),
      x: openX[r.id] || 0,
      drag: false,
      watchBusy: false,
    }))
    const n = watched.length
    this.setData({
      loading: false,
      error: '',
      needJoin: false,
      pending: d.pending,
      monitoring,
      pcText: api.DEMO ? '' : ago(d.synced),
      pcOk: api.DEMO || (d.synced && Date.now() - d.synced < 3 * 60 * 1000),
      headline: !monitoring ? '監控關著 · 不盯直播、不發通知' : n ? `電腦在線 · 幫你盯著 ${n} 間` : '電腦準備好了 · 選一間來盯',
      rooms, hero, others, fly,
    })
    if (hero && hero.bump) {
      clearTimeout(this.bumpTimer)
      this.bumpTimer = setTimeout(() => this.setData({ 'hero.bump': false, fly: null }), 1150)
    }
  },

  // ---------- 號碼票 ----------

  openHero() {
    if (this.data.hero) wx.navigateTo({ url: `/pages/room/room?id=${this.data.hero.id}` })
  },

  goVerifyHero() {
    if (this.data.hero) wx.navigateTo({ url: `/pages/verify/verify?id=${this.data.hero.id}` })
  },

  heroMenu() {
    const h = this.data.hero
    if (!h) return
    wx.showActionSheet({
      itemList: ['不盯這間', '刪除這個直播間'],
      itemColor: '#1f2a22',
      success: (res) => {
        if (res.tapIndex === 0) this.setWatch(h.id, false)
        else this.confirmRemove(h.id, h.name)
      },
    })
  },

  // ---------- 小卡片：往左滑刪除（手指往左拖，刪除鍵從右邊出來） ----------

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
    this.data.others.forEach((r, j) => { if (j !== s.i && r.x) patch[`others[${j}].x`] = 0 })  // 一次只開一張
    this.setData(patch)
  },

  open(e) {
    if (this.swiped) {
      this.swiped = false
      return
    }
    const i = e.currentTarget.dataset.i
    const r = this.data.others[i]
    if (r.x) {  // 開著刪除鍵時點一下＝收回
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
      title: `刪除「${name}」？`,
      content: '電腦會停止監控這間，目標設定也會一起刪掉。',
      confirmText: '刪除',
      confirmColor: '#d9534a',
      success: async (r) => {
        if (!r.confirm) {
          const patch = {}
          this.data.others.forEach((x, j) => { if (x.x) patch[`others[${j}].x`] = 0 })
          this.setData(patch)
          return
        }
        wx.showLoading({ title: '電腦處理中' })
        try {
          const res = await api.removeRoom(id)
          wx.hideLoading()
          wx.showToast({ title: res.pending ? '已送出，電腦稍後處理' : '已刪除', icon: 'none' })
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
      if (res.pending) wx.showToast({ title: '已送出，電腦稍後處理', icon: 'none' })
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
      wx.showModal({ title: '沒加入成功', content: e.message, showCancel: false })
    }
  },

  async toggleMonitoring() {
    if (this.switching) return
    const on = !this.data.monitoring
    this.switching = true
    this.setData({ monitoring: on, switching: true })  // 先動開關，再等電腦
    wx.showLoading({ title: on ? '電腦準備中' : '正在關閉監控' })
    try {
      const r = await api.setMonitoring(on)
      wx.hideLoading()
      if (r.pending) {
        wx.showModal({ title: '已送出', content: '電腦還沒處理完，等一下回來看。電腦要開著、黑色視窗要在跑。', showCancel: false })
      } else {
        wx.showToast({ title: on ? '電腦準備好了，選一間來盯' : '監控已關閉', icon: 'none' })
      }
    } catch (err) {
      wx.hideLoading()
      wx.showToast({ title: err.message, icon: 'none' })
    }
    this.switching = false
    this.setData({ switching: false })
    this.refresh()
  },

  openMembers() {
    wx.navigateTo({ url: '/pages/members/members' })
  },

  // 一個鍵：讀剪貼簿裡的抖音連結，確認後加入並開始盯
  async pasteAdd() {
    if (this.data.busy) return
    let text = ''
    try { text = (await wx.getClipboardData()).data || '' } catch (e) {}
    if (!api.parseRoom(text)) {
      wx.showModal({ title: '剪貼簿裡沒有直播連結', content: '在抖音直播間按「分享 → 複製連結」，再回來按這個鍵。', showCancel: false })
      return
    }
    const ok = await new Promise(r => wx.showModal({
      title: '加入並開始盯這間？',
      content: text.length > 60 ? text.slice(0, 60) + '…' : text,
      confirmText: '加入',
      confirmColor: '#3f8f5b',
      success: x => r(x.confirm),
      fail: () => r(false),
    }))
    if (!ok) return
    this.setData({ busy: true })
    wx.showLoading({ title: '電腦處理中' })
    try {
      const r = await api.addRoom(text)
      wx.hideLoading()
      await this.refresh()
      if (r.pending) {
        wx.showModal({ title: '已送出', content: '電腦還沒處理完，等一下回來看。電腦要開著、黑色視窗要在跑。', showCancel: false })
      } else {
        wx.showToast({ title: '已加入，開始盯', icon: 'none' })
        if (r.id) wx.navigateTo({ url: `/pages/room/room?id=${r.id}` })
      }
    } catch (e) {
      wx.hideLoading()
      wx.showToast({ title: e.message, icon: 'none', duration: 3000 })
    }
    this.setData({ busy: false })
  },

  resetDemo() {
    api.resetDemo()
    this.refresh()
  },
})
