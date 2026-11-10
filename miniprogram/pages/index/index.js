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

// 目標標籤：講過的變淡；正在講的實心；B 型（號碼不變）時，下一個要到的標出「還差幾件」，
// 並算出進度（現在講到幾號 / 目標幾號）給大號碼下面那條細線用
function info(r) {
  const exp = r.explaining
  const list = (r.targets || []).slice().sort((a, b) => a.pos - b.pos)
  let nextMarked = false
  let prog = 0
  const chips = list.map(t => {
    if (exp && exp.id === t.id) return { key: t.id, text: `${t.pos}`, cls: 'fill' }
    if (t.explained) return { key: t.id, text: `${t.pos}`, cls: 'done' }
    if (!nextMarked && r.type === 'B' && exp && exp.index && t.pos > exp.index) {
      nextMarked = true
      prog = Math.round(exp.index / t.pos * 100)
      return { key: t.id, text: `${t.pos} 還差 ${t.pos - exp.index}`, cls: 'on' }
    }
    return { key: t.id, text: `${t.pos}`, cls: '' }
  })
  return { chips, prog }
}

Page({
  data: {
    demo: api.DEMO,
    rooms: [],
    link: '',
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
    this.lastExp = {}
    this.lastIdx = {}
  },

  onShow() {
    this.refresh()
    this.timer = setInterval(() => this.refresh(), 15000)
  },

  onHide() {
    clearInterval(this.timer)
  },

  onUnload() {
    clearInterval(this.timer)
  },

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
    for (const r of this.data.rooms) if (r.x) openX[r.id] = r.x
    const bumped = []
    const rooms = d.rooms.map(r => {
      const expId = r.explaining ? r.explaining.id : null
      const bump = !!(expId && this.lastExp[r.id] && this.lastExp[r.id] !== expId)
      const prevIndex = bump ? this.lastIdx[r.id] : null  // 換號碼時，舊號碼往上飛走
      this.lastExp[r.id] = expId
      this.lastIdx[r.id] = r.explaining ? r.explaining.index : null
      if (bump) bumped.push(r.id)
      return {
        ...r,
        statusText: api.STATUS_TEXT[r.status] || r.status,
        live: r.status === 'live',
        alert: r.status === 'captcha' || r.status === 'need_login' || r.status === 'error',
        ...info(r),
        x: openX[r.id] || 0,
        drag: false,
        bump,
        prevIndex,
      }
    })
    this.setData({
      loading: false,
      error: '',
      needJoin: false,
      pending: d.pending,
      monitoring: this.switching ? this.data.monitoring : !d.paused,
      pcText: api.DEMO ? '' : ago(d.synced),
      pcOk: api.DEMO || (d.synced && Date.now() - d.synced < 3 * 60 * 1000),
      rooms,
    })
    if (bumped.length) {
      setTimeout(() => {
        const patch = {}
        this.data.rooms.forEach((r, i) => { if (r.bump) patch[`rooms[${i}].bump`] = false })
        this.setData(patch)
      }, 600)
    }
  },

  // ---------- 左滑刪除（像 iPhone：手指往左拖，刪除鍵從右邊出來） ----------

  touchStart(e) {
    const i = e.currentTarget.dataset.i
    const t = e.touches[0]
    this.sw = { i, x0: t.clientX, y0: t.clientY, base: this.data.rooms[i].x || 0, dir: '' }
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
    this.setData({ [`rooms[${s.i}].x`]: x, [`rooms[${s.i}].drag`]: true })
  },

  touchEnd() {
    const s = this.sw
    this.sw = null
    if (!s || s.dir !== 'h') return
    const cur = this.data.rooms[s.i].x
    const patch = { [`rooms[${s.i}].drag`]: false, [`rooms[${s.i}].x`]: cur < -DEL_PX / 2 ? -DEL_PX : 0 }
    // 一次只開一列
    this.data.rooms.forEach((r, j) => { if (j !== s.i && r.x) patch[`rooms[${j}].x`] = 0 })
    this.setData(patch)
  },

  open(e) {
    if (this.swiped) {
      this.swiped = false
      return
    }
    const i = e.currentTarget.dataset.i
    if (this.data.rooms[i].x) {  // 開著刪除鍵時點一下＝收回
      this.setData({ [`rooms[${i}].x`]: 0 })
      return
    }
    wx.navigateTo({ url: `/pages/room/room?id=${this.data.rooms[i].id}` })
  },

  askRemove(e) {
    const i = e.currentTarget.dataset.i
    const { id, name } = this.data.rooms[i]
    wx.showModal({
      title: `刪除「${name}」？`,
      content: '電腦會停止監控這間，目標設定也會一起刪掉。',
      confirmText: '刪除',
      confirmColor: '#c2412b',
      success: async (r) => {
        if (!r.confirm) {
          this.setData({ [`rooms[${i}].x`]: 0 })
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
    wx.showLoading({ title: on ? '正在打開監控' : '正在關閉監控' })
    try {
      const r = await api.setMonitoring(on)
      wx.hideLoading()
      if (r.pending) {
        wx.showModal({ title: '已送出', content: '電腦還沒處理完，等一下回來看。電腦要開著、黑色視窗要在跑。', showCancel: false })
      } else {
        wx.showToast({ title: r.message || (on ? '已打開' : '已關閉'), icon: 'none' })
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

  onLink(e) {
    this.setData({ link: e.detail.value })
  },

  async paste() {
    try {
      const res = await wx.getClipboardData()
      this.setData({ link: res.data })
    } catch (e) {}
  },

  async add() {
    if (this.data.busy) return
    if (!this.data.link) {
      this.paste()
      return
    }
    this.setData({ busy: true })
    wx.showLoading({ title: '電腦處理中' })
    try {
      const r = await api.addRoom(this.data.link)
      wx.hideLoading()
      this.setData({ link: '' })
      await this.refresh()
      if (r.pending) {
        wx.showModal({ title: '已送出', content: '電腦還沒處理完，等一下回來看。電腦要開著、黑色視窗要在跑。', showCancel: false })
      } else {
        wx.showToast({ title: '已加入', icon: 'success' })
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
