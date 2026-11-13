// 到号／快到号时震动。同一间、同一件商品只震一次（首页和直播间页共用这份记录）。
const seen = {}

// 'hit:商品id'＝正在讲你要的；'near:商品id'＝照你选的“提前 N 件”快到了；''＝都不是
function key(r) {
  const exp = r && r.explaining
  if (!r || r.status !== 'live' || !exp || !exp.id) return ''
  const list = r.targets || []
  if (list.some(t => t.id === exp.id)) return 'hit:' + exp.id
  if (!exp.index) return ''
  const near = list
    .filter(t => !t.explained && t.ahead > 0 && t.pos > exp.index && t.pos - exp.index <= t.ahead)
    .sort((a, b) => a.pos - b.pos)[0]
  return near ? 'near:' + near.id : ''
}

function fire(k) {
  try {
    if (k.indexOf('hit:') === 0) wx.vibrateLong()  // 到了：长震一下
    else {  // 快到了：短震两下
      wx.vibrateShort({ type: 'heavy' })
      setTimeout(() => { try { wx.vibrateShort({ type: 'heavy' }) } catch (e) {} }, 220)
    }
  } catch (e) {}
}

function check(r) {
  if (!r || !r.id) return
  const k = key(r)
  if (k && seen[r.id] !== k) fire(k)
  seen[r.id] = k
}

module.exports = { check, key }
