const api = require('../../utils/api')

Page({
  data: {
    list: [],
    code: '',
    minutes: 0,
    expiresText: '',
  },

  onShow() {
    this.load()
  },

  async load() {
    try {
      this.setData({ list: await api.members() })
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
    }
  },

  async makeCode() {
    try {
      const r = await api.invite()
      const t = new Date(Date.now() + r.minutes * 60000)
      const hh = String(t.getHours()).padStart(2, '0')
      const mm = String(t.getMinutes()).padStart(2, '0')
      this.setData({ code: r.code, minutes: r.minutes, expiresText: `${hh}:${mm}` })
    } catch (e) {
      wx.showToast({ title: e.message, icon: 'none' })
    }
  },

  copyCode() {
    wx.setClipboardData({ data: this.data.code })
  },

  remove(e) {
    const index = e.currentTarget.dataset.index
    wx.showModal({
      title: '移除这个成员？',
      content: '移除后，那个微信号就打不开这里的数据，要重新输入邀请码才能加入。',
      confirmText: '移除',
      confirmColor: '#c43333',
      success: async (r) => {
        if (!r.confirm) return
        try {
          await api.removeMember(index)
          this.load()
        } catch (err) {
          wx.showToast({ title: err.message, icon: 'none' })
        }
      },
    })
  },
})
