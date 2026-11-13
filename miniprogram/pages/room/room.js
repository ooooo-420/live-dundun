const api = require('../../utils/api')
const buzz = require('../../utils/buzz')

// 输入框里只有数字和分隔符号＝选号；有别的字＝找商品名
const isNums = s => /^[\d\s,，、\-~～到]*$/.test(s)

// “2-10”“3 5 8”“2-5,9”→ [2,3,...]
function parseNums(text) {
  const out = new Set()
  for (const part of String(text).split(/[\s,，、]+/)) {
    const m = part.match(/^(\d+)(?:[-~～到](\d+))?$/)
    if (!m) continue
    const a = +m[1]
    const b = m[2] ? +m[2] : a
    for (let i = Math.min(a, b); i <= Math.max(a, b) && i - Math.min(a, b) < 300; i++) out.add(i)
  }
  return [...out]
}

Page({
  data: {
    id: '',
    room: null,
    cart: [],
    picked: {},        // { 商品id: true }
    pickedCount: 0,
    quick: '',
    search: '',        // 正在找的商品名（输入框里不是号码时）
    onlyPicked: false,
    hide: {},          // { 商品id: true }＝被搜寻或“只看已选”筛掉
    noMatch: false,
    aheadOptions: ['到了才叫', '提前 1 件', '提前 3 件', '提前 5 件'],
    aheadValues: [0, 1, 3, 5],
    aheadIdx: 0,
    missed: false,
    statusText: '',
    dirty: false,
    bump: false,
    prevIndex: null,
  },

  onLoad(q) {
    this.setData({ id: q.id })
    this.load()
  },

  onShow() {
    // 每 15 秒只更新“讲解中”和状态，不碰购物车和你正在勾的东西
    this.timer = setInterval(() => this.refreshLive(), 15000)
  },

  onHide() { clearInterval(this.timer) },
  onUnload() { clearInterval(this.timer) },

  async refreshLive() {
    if (!this.data.room) return
    let room
    try { ({ room } = await api.getRoom(this.data.id)) } catch (e) { return }
    if (!room) return
    const old = this.data.room
    const oldId = old.explaining ? old.explaining.id : null
    const newId = room.explaining ? room.explaining.id : null
    const bump = !!(oldId && newId && oldId !== newId)
    this.setData({
      'room.status': room.status,
      'room.type': room.type,
      'room.explaining': room.explaining,
      'room.targets': room.targets,
      statusText: api.STATUS_TEXT[room.status] || room.status,
      bump,
      prevIndex: bump ? old.explaining.index : null,
    })
    buzz.check({ ...room, id: this.data.id })
    if (bump) setTimeout(() => this.setData({ bump: false, prevIndex: null }), 600)
  },

  async load() {
    let room = null
    let cart = []
    try {
      ({ room, cart } = await api.getRoom(this.data.id))
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
      return
    }
    if (!room) {
      wx.showToast({ title: '找不到这个直播间', icon: 'none' })
      return
    }
    wx.setNavigationBarTitle({ title: room.name })
    const picked = {}
    for (const t of room.targets || []) picked[t.id] = true
    const first = (room.targets || [])[0]
    const aheadIdx = first ? Math.max(0, this.data.aheadValues.indexOf(first.ahead || 0)) : 0
    this.setData({
      room,
      cart,
      picked,
      pickedCount: Object.keys(picked).length,
      aheadIdx,
      missed: !!(first && first.missed),
      statusText: api.STATUS_TEXT[room.status] || room.status,
      dirty: false,
    })
    this.filter()
    buzz.check({ ...room, id: this.data.id })
  },

  goVerify() {
    wx.navigateTo({ url: `/pages/verify/verify?id=${this.data.id}` })
  },

  // 依“找商品名”和“只看已选”算出哪些商品要藏起来
  filter(patch) {
    const d = { ...this.data, ...(patch || {}) }
    const count = Object.keys(d.picked).length
    const only = d.onlyPicked && count > 0  // 已选清空时自动回到全部
    const word = d.search.toLowerCase()
    const hide = {}
    let shown = 0
    for (const it of d.cart) {
      if ((only && !d.picked[it.id]) || (word && String(it.title).toLowerCase().indexOf(word) < 0)) hide[it.id] = true
      else shown++
    }
    this.setData({ ...(patch || {}), pickedCount: count, onlyPicked: only, hide, noMatch: !!word && d.cart.length > 0 && shown === 0 })
  },

  toggle(e) {
    const id = e.currentTarget.dataset.id
    const picked = { ...this.data.picked }
    if (picked[id]) delete picked[id]
    else picked[id] = true
    // 正在“只看已选”时取消一件：先留在画面上（不然会突然消失、点错没法反悔），所以这里不重算筛选
    this.setData({ picked, pickedCount: Object.keys(picked).length, dirty: true })
    if (!Object.keys(picked).length) this.filter()
  },

  toggleOnly() {
    this.filter({ onlyPicked: !this.data.onlyPicked })
  },

  onQuick(e) {
    const quick = e.detail.value
    this.filter({ quick, search: isNums(quick) ? '' : quick.trim() })
  },

  clearQuick() {
    this.filter({ quick: '', search: '' })
  },

  applyQuick() {
    if (this.data.search) return
    const nums = parseNums(this.data.quick)
    if (!nums.length) {
      wx.showToast({ title: '格式像 2-10 或 3 5 8', icon: 'none' })
      return
    }
    const byIndex = {}
    for (const it of this.data.cart) byIndex[it.index] = it.id
    const picked = {}
    let miss = 0
    for (const n of nums) {
      if (byIndex[n]) picked[byIndex[n]] = true
      else miss++
    }
    this.filter({ picked, dirty: true })
    wx.showToast({ title: miss ? `已选 ${nums.length - miss} 件，${miss} 个号码不存在` : `已选 ${nums.length} 件`, icon: 'none' })
  },

  clearAll() {
    this.filter({ picked: {}, dirty: true })
  },

  onSeg(e) {
    this.setData({ aheadIdx: +e.currentTarget.dataset.i, dirty: true })
  },

  onMissed() {
    this.setData({ missed: !this.data.missed, dirty: true })
  },

  async save() {
    if (this.busy) return
    this.busy = true
    const ahead = this.data.aheadValues[this.data.aheadIdx]
    const targets = this.data.cart
      .filter(it => this.data.picked[it.id])
      .map(it => ({ id: it.id, ahead, missed: this.data.missed }))
    wx.showLoading({ title: '电脑处理中' })
    try {
      const r = await api.setTargets(this.data.id, targets)
      wx.hideLoading()
      if (r.pending) {
        wx.showModal({ title: '已送出', content: '电脑还没处理完，等一下回来看。电脑要开着、监控程序要在运行。', showCancel: false })
      } else {
        wx.showToast({ title: r.message || (targets.length ? `已设 ${targets.length} 件` : '已清空目标'), icon: 'none' })
        await this.load()
      }
    } catch (e) {
      wx.hideLoading()
      wx.showModal({ title: '没设成', content: e.message, showCancel: false })
    }
    this.busy = false
  },

  remove() {
    wx.showModal({
      title: '不监控这间了？',
      content: '目标设置会一起删掉。',
      confirmText: '移除',
      confirmColor: '#c43333',
      success: async (r) => {
        if (!r.confirm) return
        wx.showLoading({ title: '电脑处理中' })
        try {
          const res = await api.removeRoom(this.data.id)
          wx.hideLoading()
          if (res.pending) wx.showToast({ title: '已送出，电脑稍后处理', icon: 'none' })
          wx.navigateBack()
        } catch (e) {
          wx.hideLoading()
          wx.showToast({ title: e.message, icon: 'none' })
        }
      },
    })
  },
})
