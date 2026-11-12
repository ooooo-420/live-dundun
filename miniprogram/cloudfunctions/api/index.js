// 云函数 api：小程序和电脑都只通过它读写数据库。数据表一律设成“仅管理端可读写”。
//
// 谁在调用：
// - 小程序：有 OPENID。第一个调用的人自动成为成员（config/members），
//   其他帐号要输入成员产生的邀请码才能加入。所有成员看到同一份数据。
// - 电脑：用 AppSecret 换的 access_token 走 HTTP API 调用，没有 OPENID，视为电脑。
//
// 数据表：
// - rooms     电脑写：每间直播间的状态、讲解中、目标（_id = 直播间号码）
// - carts     电脑写：购物车清单 { items: [{id,index,title,price}] }（_id = 直播间号码）
// - commands  小程序写：要电脑做的事 { type, room, payload, done, result, created }
// - config    members（成员 openid、邀请码）、pc（电脑心跳）

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
    try { await db.createCollection(name) } catch (e) { /* 已经有了 */ }
  }
  ensured = true
}

// ---------- 成员 ----------
// config/members：{ list: [openid...], invite: { code, expires, fails } }
// 第一个用的人自动成为成员；之后要由成员生成邀请码，新帐号输入邀请码才能加入。

const INVITE_MINUTES = 30
const INVITE_MAX_FAILS = 5

async function getMembers() {
  const col = db.collection('config')
  let doc = null
  try { doc = (await col.doc('members').get()).data } catch (e) { doc = null }
  if (!doc) {
    // 旧版只记主人（config/owner），搬过来
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
  if (!inv || Date.now() > inv.expires) throw new Error('没有有效的邀请码，请主人重新生成')
  if (String(code).trim() !== inv.code) {
    inv.fails = (inv.fails || 0) + 1
    if (inv.fails >= INVITE_MAX_FAILS) doc.invite = null
    await saveMembers(doc)
    throw new Error(doc.invite ? '邀请码不对' : '错太多次，邀请码已作废，请主人重新生成')
  }
  doc.list.push(openid)
  doc.invite = null  // 用过就作废
  await saveMembers(doc)
  return { joined: true }
}

async function removeMember(openid, index) {
  const doc = await getMembers()
  const target = doc.list[index]
  if (!target) throw new Error('没有这个成员')
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
      if (!COMMANDS.includes(type)) throw new Error('不认得的指令')
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
      // 人机验证截屏：电脑截下验证框，手机上由用户本人操作
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
      throw new Error('不认得的动作')
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

// ---------- 电脑 ----------
// event: { action:'pc_sync', rooms?:[...], carts?:{id:[items]}, results?:[{id, ok, message, room}] }
// 回传：还没处理的指令

async function fromPc(event) {
  if (event.action !== 'pc_sync') throw new Error('不认得的动作')
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

  // 验证截屏：{ 直播间: {img,w,h,v,t} 或 null（验证完成） }
  if (event.captchas) {
    for (const id of Object.keys(event.captchas)) {
      const sh = event.captchas[id]
      if (sh) await db.collection('captcha').doc(id).set({ data: { ...sh, updated: now } })
      else { try { await db.collection('captcha').doc(id).remove() } catch (e) {} }
    }
  }

  // result 原本是 null，直接 update 成对象会被当成“在 null 里建字段”而失败，所以要用 _.set 整个换掉
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

  // 心跳：让小程序知道电脑还活着。电脑大约每分钟才带一次，省数据库写入次数。
  // 用 update 不用 set：看门狗（watchdog 云函数）记在同一份文档里的 alerted 不能被洗掉。
  if (event.heartbeat) {
    const data = { time: now, paused: !!(event.pc && event.pc.paused) }
    try {
      const r = await db.collection('config').doc('pc').update({ data })
      if (!r.stats || r.stats.updated === 0) throw new Error('no doc')
    } catch (e) {
      await db.collection('config').doc('pc').set({ data })
    }
    // 清掉一天前已完成的指令，免得越积越多
    try { await db.collection('commands').where({ done: true, created: _.lt(now - 86400000) }).remove() } catch (e) {}
  }

  // 公众号测试号的数据（电脑有变才送）：存在 config/notify，给 watchdog 在电脑掉线时代发通知用
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
      if (!(await isMember(OPENID))) return { ok: false, code: 'not_member', error: '还没加入，请输入邀请码' }
      return { ok: true, data: await fromApp({ ...event, __openid: OPENID }) }
    }
    return { ok: true, data: await fromPc(event) }
  } catch (e) {
    return { ok: false, error: String(e.message || e) }
  }
}
