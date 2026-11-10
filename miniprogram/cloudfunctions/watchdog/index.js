// 雲函數 watchdog：電腦掉線看門狗。由定時觸發器每 5 分鐘跑一次（config.json）。
//
// 電腦活著時每分鐘寫一次心跳到 config/pc.time。這裡檢查：
// - 心跳超過 OFFLINE_MINUTES 沒更新，而且監控不是「關」的 → 用公眾號測試號發「電腦掉線」到微信，記下 alerted
// - 之後心跳又回來了 → 發一條「電腦回來了」，清掉 alerted
// 這是唯一一個電腦死掉也能叫人的機制，因為它跑在雲端。
//
// 公眾號的 appid / appsecret / openid / template_id 由電腦在心跳時送上來，存在 config/notify（資料表只有管理端可讀）。

const cloud = require('wx-server-sdk')
const https = require('https')
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })
const db = cloud.database()

const OFFLINE_MINUTES = 10
const REMIND_HOURS = 6  // 一直沒回來的話，每隔幾小時再提醒一次

function request(method, url, body) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, { method, headers: { 'Content-Type': 'application/json; charset=utf-8' } }, res => {
      let s = ''
      res.on('data', d => { s += d })
      res.on('end', () => { try { resolve(JSON.parse(s)) } catch (e) { reject(new Error('bad json: ' + s.slice(0, 100))) } })
    })
    req.on('error', reject)
    if (body) req.write(JSON.stringify(body))
    req.end()
  })
}

function fmtTime(ms) {
  const d = new Date(ms + 8 * 3600000)  // 北京時間
  const p = n => String(n).padStart(2, '0')
  return `${p(d.getUTCMonth() + 1)}-${p(d.getUTCDate())} ${p(d.getUTCHours())}:${p(d.getUTCMinutes())}:${p(d.getUTCSeconds())}`
}

async function sendWeChat(cfg, product, status) {
  const tok = await request('GET', `https://api.weixin.qq.com/cgi-bin/token?grant_type=client_credential&appid=${cfg.appid}&secret=${cfg.appsecret}`)
  if (!tok.access_token) throw new Error(`token: ${tok.errcode} ${tok.errmsg}`)
  const r = await request('POST', `https://api.weixin.qq.com/cgi-bin/message/template/send?access_token=${tok.access_token}`, {
    touser: cfg.openid,
    template_id: cfg.template_id,
    data: {
      room: { value: '電腦' },
      product: { value: product.slice(0, 20) },
      status: { value: status.slice(0, 20) },
      time: { value: fmtTime(Date.now()) },
    },
  })
  if (r.errcode !== 0) throw new Error(`send: ${r.errcode} ${r.errmsg}`)
}

async function getDoc(id) {
  try { return (await db.collection('config').doc(id).get()).data } catch (e) { return null }
}

exports.main = async () => {
  const now = Date.now()
  const pc = await getDoc('pc')
  const cfg = await getDoc('notify')
  if (!pc || !pc.time) return { skip: 'no heartbeat yet' }
  if (!cfg || !cfg.appid) return { skip: 'no notify config' }

  const silent = now - pc.time
  const offline = silent > OFFLINE_MINUTES * 60000
  const col = db.collection('config').doc('pc')

  if (offline && !pc.paused) {
    if (pc.alerted && now - pc.alerted < REMIND_HOURS * 3600000) return { skip: 'already alerted' }
    const mins = Math.round(silent / 60000)
    await sendWeChat(cfg, '監控程式沒有回報', `已經 ${mins} 分鐘沒心跳，去看看電腦`)
    await col.update({ data: { alerted: now, alertCount: (pc.alertCount || 0) + 1 } })
    return { alerted: true, mins }
  }
  if (!offline && pc.alerted) {
    await sendWeChat(cfg, '監控程式回來了', '電腦已恢復回報，監控繼續')
    await col.update({ data: { alerted: null, alertCount: 0 } })
    return { recovered: true }
  }
  return { ok: true, offline, paused: !!pc.paused, silentMinutes: Math.round(silent / 60000) }
}
