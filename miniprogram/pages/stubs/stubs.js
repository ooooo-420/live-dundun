const api = require('../../utils/api')

const KIND = { arrive: ['到了', ''], ahead: ['快到了', 'near'], missed: ['可能错过', 'miss'] }
const pad = n => (n < 10 ? '0' : '') + n
const dayKey = d => `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()}`

// 把提醒照日期分组：今天、昨天、几月几日
function group(notes) {
  const now = new Date()
  const today = dayKey(now)
  const yesterday = dayKey(new Date(now.getTime() - 86400000))
  const days = []
  for (const x of notes) {
    const d = new Date(x.t)
    const key = dayKey(d)
    let g = days[days.length - 1]
    if (!g || g.key !== key) {
      g = { key, title: key === today ? '今天' : key === yesterday ? '昨天' : `${d.getMonth() + 1} 月 ${d.getDate()} 日`, items: [] }
      days.push(g)
    }
    const k = KIND[x.kind] || KIND.arrive
    // 号码被置顶挤动过（A 型）：两个都给
    const moved = x.index && x.pos && x.index !== x.pos
    g.items.push({
      id: x._id || x.id,
      n: x.index || x.pos,
      label: k[0],
      cls: k[1],
      title: x.title || '',
      sub: `${x.name || ''} · ${pad(d.getHours())}:${pad(d.getMinutes())}` + (moved ? ` · 原 ${x.pos} 号` : ''),
      sent: x.ok === false ? '微信没发出去' : '微信已发出',
      fail: x.ok === false,
    })
  }
  return days
}

Page({
  data: { days: [], loading: true, error: '' },

  onShow() { this.load() },
  onPullDownRefresh() { this.load().then(() => wx.stopPullDownRefresh()) },

  async load() {
    try {
      const notes = await api.getNotes()
      this.setData({ days: group(notes), loading: false, error: '' })
    } catch (e) {
      this.setData({ loading: false, error: e.message })
    }
  },
})
