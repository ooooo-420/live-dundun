// 云函数 watchdog：电脑掉线看门狗。由定时触发器每 5 分钟跑一次（config.json）。
//
// 电脑活着时每分钟写一次心跳到 config/pc.time。这里检查：
// - 心跳超过 OFFLINE_MINUTES 没更新，而且监控不是“关”的 → 用公众号测试号发“电脑掉线”到微信，记下 alerted
// - 之后心跳又回来了 → 发一条“电脑回来了”，清掉 alerted
// 这是唯一一个电脑死掉也能叫人的机制，因为它跑在云端。
//
// 公众号的 appid / appsecret / openid / template_id 由电脑在心跳时送上来，存在 config/notify（数据表只有管理端可读）。

const cloud = require('wx-server-sdk')
const https = require('https')
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })
const db = cloud.database()

const OFFLINE_MINUTES = 10
const REMIND_HOURS = 6  // 一直没回来的话，每隔几小时再提醒一次

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
  const d = new Date(ms + 8 * 3600000)  // 北京时间
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
      room: { value: '电脑' },
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
    await sendWeChat(cfg, '监控程序没有回报', `已经 ${mins} 分钟没心跳，去看看电脑`)
    await col.update({ data: { alerted: now, alertCount: (pc.alertCount || 0) + 1 } })
    return { alerted: true, mins }
  }
  if (!offline && pc.alerted) {
    await sendWeChat(cfg, '监控程序回来了', '电脑已恢复回报，监控继续')
    await col.update({ data: { alerted: null, alertCount: 0 } })
    return { recovered: true }
  }
  return { ok: true, offline, paused: !!pc.paused, silentMinutes: Math.round(silent / 60000) }
}
