// 人機驗證：顯示電腦截的驗證框，把使用者本人的手勢（點一下或按住拖動的軌跡）送回電腦照原樣操作。
// 程式不自己解驗證，只是幫人把手伸到電腦那邊。
const api = require('../../utils/api')

Page({
  data: { id: '', shot: null, busy: false, msg: '', done: false, finger: null },

  onLoad(q) {
    this.setData({ id: q.id })
    this.load()
  },

  onShow() {
    this.timer = setInterval(() => { if (!this.data.busy) this.load() }, 2000)
  },
  onHide() { clearInterval(this.timer) },
  onUnload() { clearInterval(this.timer) },

  async load() {
    let shot
    try { shot = await api.getCaptcha(this.data.id) } catch (e) { this.setData({ msg: e.message }); return }
    if (!shot) {
      if (this.data.shot) this.finish()  // 原本有截圖、現在沒了＝驗證完成
      return
    }
    if (!this.data.shot || shot.v !== this.data.shot.v) this.setData({ shot })
  },

  finish() {
    clearInterval(this.timer)
    this.setData({ done: true, shot: null, msg: '驗證完成，電腦繼續盯了' })
    setTimeout(() => wx.navigateBack({ fail: () => wx.reLaunch({ url: '/pages/index/index' }) }), 1400)
  },

  // ---------- 手勢 ----------
  ts(e) {
    if (this.data.busy) return
    const t = e.touches[0]
    wx.createSelectorQuery().in(this).select('#shot').boundingClientRect(r => { this.rect = r }).exec()
    this.t0 = Date.now()
    this.raw = [[t.clientX, t.clientY, 0]]
    this.moved = 0
    this.showFinger(t)
  },

  tm(e) {
    if (!this.raw) return
    const t = e.touches[0]
    const last = this.raw[this.raw.length - 1]
    this.moved += Math.abs(t.clientX - last[0]) + Math.abs(t.clientY - last[1])
    this.raw.push([t.clientX, t.clientY, Date.now() - this.t0])
    this.showFinger(t)
  },

  showFinger(t) {
    const r = this.rect
    if (r) this.setData({ finger: { x: t.clientX - r.left, y: t.clientY - r.top } })
  },

  async te() {
    const raw = this.raw
    this.raw = null
    this.setData({ finger: null })
    const r = this.rect
    if (!raw || !r || !r.width) return
    const points = raw.map(([x, y, t]) => [(x - r.left) / r.width, (y - r.top) / r.height, t])
    const kind = this.moved < 8 ? 'tap' : 'drag'
    await this.send({ kind, points: kind === 'tap' ? points.slice(0, 1) : points })
  },

  refresh() {
    this.send({ kind: 'refresh', points: [] })
  },

  async send(payload) {
    if (this.data.busy || !this.data.shot) return
    this.setData({ busy: true, msg: payload.kind === 'refresh' ? '請電腦重新截圖…' : '送到電腦…' })
    try {
      const res = await api.captchaInput(this.data.id, { ...payload, v: this.data.shot.v })
      if (res.pending) this.setData({ msg: '電腦還沒回應，等一下' })
      else this.setData({ msg: res.message === '驗證完成' ? '' : '還沒過，照新的畫面再試一次' })
      if (res.message === '驗證完成') { this.finish(); return }
    } catch (e) {
      this.setData({ msg: e.message })
    }
    this.setData({ busy: false })
    this.load()
  },
})
