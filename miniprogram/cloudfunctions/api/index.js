// 雲函數 api：小程序和電腦都只透過它讀寫資料庫。資料表一律設成「僅管理端可讀寫」。
//
// 誰在呼叫：
// - 小程序：有 OPENID。第一個呼叫的人自動成為成員（config/members），
//   其他帳號要輸入成員產生的邀請碼才能加入。所有成員看到同一份資料。
// - 電腦：用 AppSecret 換的 access_token 走 HTTP API 呼叫，沒有 OPENID，視為電腦。
//
// 資料表：
// - rooms     電腦寫：每間直播間的狀態、講解中、目標（_id = 直播間號碼）
// - carts     電腦寫：購物車清單 { items: [{id,index,title,price}] }（_id = 直播間號碼）
// - commands  小程序寫：要電腦做的事 { type, room, payload, done, result, created }
// - config    members（成員 openid、邀請碼）、pc（電腦心跳）

const cloud = require('wx-server-sdk')
cloud.init({ env: cloud.DYNAMIC_CURRENT_ENV })
const db = cloud.database()
const _ = db.command

const COLLECTIONS = ['rooms', 'carts', 'commands', 'config', 'captcha']
const COMMANDS = ['add_room', 'remove_room', 'set_targets', 'pause', 'resume', 'watch', 'unwatch', 'captcha_input']
let ensured = false

async function ensure() {
  if (ensured) return
  for (const name of COLLECTIONS) {
    try { await db.createCollection(name) } catch (e) { /* 已經有了 */ }
  }
  ensured = true
}

// ---------- 成員 ----------
// config/members：{ list: [openid...], invite: { code, expires, fails } }
// 第一個用的人自動成為成員；之後要由成員產生邀請碼，新帳號輸入邀請碼才能加入。

const INVITE_MINUTES = 30
const INVITE_MAX_FAILS = 5

async function getMembers() {
  const col = db.collection('config')
  let doc = null
  try { doc = (await col.doc('members').get()).data } catch (e) { doc = null }
  if (!doc) {
    // 舊版只記主人（config/owner），搬過來
    let owner = null
    try { owner = (await col.doc('owner').get()).data } catch (e) {}
    doc = { list: owner && owner.openid ? [owner.openid] : [], invite: null }
  }
  return doc
}

async function saveMembers(doc) {
  await db.collection('config').doc('members').set({ data: { list: doc.list, invite: doc.invite || null } })
}

async function isMember(openid) {
  const doc = await getMembers()
  if (doc.list.length === 0) {
    doc.list.push(openid)
    await saveMembers(doc)
    return true
  }
  return doc.list.includes(openid)
}

async function makeInvite() {
  const doc = await getMembers()
  const code = String(Math.floor(100000 + Math.random() * 900000))
  doc.invite = { code, expires: Date.now() + INVITE_MINUTES * 60000, fails: 0 }
  await saveMembers(doc)
  return { code, minutes: INVITE_MINUTES }
}

async function join(openid, code) {
  const doc = await getMembers()
  if (doc.list.includes(openid)) return { joined: true }
  const inv = doc.invite
  if (!inv || Date.now() > inv.expires) throw new Error('沒有有效的邀請碼，請主人重新產生')
  if (String(code).trim() !== inv.code) {
    inv.fails = (inv.fails || 0) + 1
    if (inv.fails >= INVITE_MAX_FAILS) doc.invite = null
    await saveMembers(doc)
    throw new Error(doc.invite ? '邀請碼不對' : '錯太多次，邀請碼已作廢，請主人重新產生')
  }
  doc.list.push(openid)
  doc.invite = null  // 用過就作廢
  await saveMembers(doc)
  return { joined: true }
}

async function removeMember(openid, index) {
  const doc = await getMembers()
  const target = doc.list[index]
  if (!target) throw new Error('沒有這個成員')
  if (target === openid) throw new Error('不能移除自己')
  doc.list.splice(index, 1)
  await saveMembers(doc)
  return { count: doc.list.length }
}

async function listAll(col, where) {
  const out = []
  for (let skip = 0; ; skip += 100) {
    let q = db.collection(col)
    if (where) q = q.where(where)
    const r = await q.skip(skip).limit(100).get()
    out.push(...r.data)
    if (r.data.length < 100) return out
  }
}

// ---------- 小程序 ----------

async function fromApp(event) {
  switch (event.action) {
    case 'rooms': {
      const rooms = await listAll('rooms')
      const pending = await listAll('commands', { done: false })
      const pc = await pcInfo()
      return { rooms, pending: pending.length, synced: pc.time, paused: pc.paused }
    }
    case 'room': {
      let room = null
      let cart = []
      try { room = (await db.collection('rooms').doc(event.id).get()).data } catch (e) {}
      try { cart = (await db.collection('carts').doc(event.id).get()).data.items || [] } catch (e) {}
      return { room, cart }
    }
    case 'command': {
      const { type, room, payload } = event
      if (!COMMANDS.includes(type)) throw new Error('不認得的指令')
      const r = await db.collection('commands').add({
        data: { type, room: room || null, payload: payload || null, done: false, result: null, created: Date.now() },
      })
      return { id: r._id }
    }
    case 'command_result': {
      const r = await db.collection('commands').doc(event.id).get()
      return { done: r.data.done, result: r.data.result }
    }
    case 'captcha': {
      // 人機驗證截圖：電腦截下驗證框，手機上由使用者本人操作
      let shot = null
      try { shot = (await db.collection('captcha').doc(event.id).get()).data } catch (e) {}
      return { shot: shot && shot.img ? shot : null }
    }
    case 'invite':
      return makeInvite()
    case 'members': {
      const doc = await getMembers()
      return { list: doc.list.map((o, i) => ({ index: i, me: o === event.__openid, tail: o.slice(-4) })) }
    }
    case 'remove_member':
      return removeMember(event.__openid, event.index)
    default:
      throw new Error('不認得的動作')
  }
}

async function pcInfo() {
  try {
    const d = (await db.collection('config').doc('pc').get()).data
    return { time: d.time || null, paused: !!d.paused }
  } catch (e) {
    return { time: null, paused: false }
  }
}

// ---------- 電腦 ----------
// event: { action:'pc_sync', rooms?:[...], carts?:{id:[items]}, results?:[{id, ok, message, room}] }
// 回傳：還沒處理的指令

async function fromPc(event) {
  if (event.action !== 'pc_sync') throw new Error('不認得的動作')
  const now = Date.now()

  if (Array.isArray(event.rooms)) {
    const keep = new Set()
    for (const r of event.rooms) {
      const { id, ...data } = r
      keep.add(id)
      await db.collection('rooms').doc(id).set({ data: { ...data, updated: now } })
    }
    const old = await listAll('rooms')
    for (const r of old) {
      if (!keep.has(r._id)) {
        await db.collection('rooms').doc(r._id).remove()
        try { await db.collection('carts').doc(r._id).remove() } catch (e) {}
      }
    }
  }

  if (event.carts) {
    for (const id of Object.keys(event.carts)) {
      await db.collection('carts').doc(id).set({ data: { items: event.carts[id], updated: now } })
    }
  }

  // 驗證截圖：{ 直播間: {img,w,h,v,t} 或 null（驗證完成） }
  if (event.captchas) {
    for (const id of Object.keys(event.captchas)) {
      const sh = event.captchas[id]
      if (sh) await db.collection('captcha').doc(id).set({ data: { ...sh, updated: now } })
      else { try { await db.collection('captcha').doc(id).remove() } catch (e) {} }
    }
  }

  // result 原本是 null，直接 update 成物件會被當成「在 null 裡建欄位」而失敗，所以要用 _.set 整個換掉
  const resultErrors = []
  for (const res of event.results || []) {
    try {
      await db.collection('commands').doc(res.id).update({
        data: { done: true, result: _.set({ ok: !!res.ok, message: res.message || '', room: res.room || null }), finished: now },
      })
    } catch (e) {
      resultErrors.push(`${res.id}: ${e.message || e}`)
    }
  }

  // 心跳：讓小程序知道電腦還活著。電腦大約每分鐘才帶一次，省資料庫寫入次數。
  // 用 update 不用 set：看門狗（watchdog 雲函數）記在同一份文件裡的 alerted 不能被洗掉。
  if (event.heartbeat) {
    const data = { time: now, paused: !!(event.pc && event.pc.paused) }
    try {
      const r = await db.collection('config').doc('pc').update({ data })
      if (!r.stats || r.stats.updated === 0) throw new Error('no doc')
    } catch (e) {
      await db.collection('config').doc('pc').set({ data })
    }
    // 清掉一天前已完成的指令，免得越積越多
    try { await db.collection('commands').where({ done: true, created: _.lt(now - 86400000) }).remove() } catch (e) {}
  }

  // 公眾號測試號的資料（電腦有變才送）：存在 config/notify，給 watchdog 在電腦掉線時代發通知用
  if (event.notify && event.notify.appid) {
    await db.collection('config').doc('notify').set({ data: { ...event.notify, updated: now } })
  }

  const pending = await db.collection('commands').where({ done: false }).orderBy('created', 'asc').limit(20).get()
  return { commands: pending.data, resultErrors }
}

exports.main = async (event) => {
  await ensure()
  const { OPENID } = cloud.getWXContext()
  try {
    if (OPENID) {
      if (event.action === 'join') return { ok: true, data: await join(OPENID, event.code) }
      if (!(await isMember(OPENID))) return { ok: false, code: 'not_member', error: '還沒加入，請輸入邀請碼' }
      return { ok: true, data: await fromApp({ ...event, __openid: OPENID }) }
    }
    return { ok: true, data: await fromPc(event) }
  } catch (e) {
    return { ok: false, error: String(e.message || e) }
  }
}
