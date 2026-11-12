"""小程序同步的逻辑测试：云端和监控都用假的，不连网络、不开浏览器。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import cloud, store  # noqa: E402
from app.cloud import HEARTBEAT_EVERY  # noqa: E402

store.log = lambda *a, **k: None  # 测试不写记录档


class FakeWorker:
    def __init__(self, rid, cart):
        self.rid = rid
        self.cart = cart

    def public(self):
        return {"id": self.rid, "url": f"https://live.douyin.com/{self.rid}", "name": self.rid, "status": "live",
                "error": "", "type": None, "watch": True, "explaining": None, "cart_count": len(self.cart), "targets": []}


class FakeMonitor:
    def __init__(self):
        self.workers = {}
        self.state = {"rooms": {}}
        self.creds = None

    def notify_credentials(self):
        return self.creds

    def add_room(self, url):
        rid = store.room_id_from_url(url)
        self.workers[rid] = FakeWorker(rid, [])
        self.state["rooms"][rid] = {"targets": []}
        return rid

    async def remove_room(self, rid):
        self.workers.pop(rid, None)
        self.state["rooms"].pop(rid, None)

    def set_targets(self, rid, targets):
        w = self.workers[rid]
        if targets and not w.cart:
            raise ValueError("还没有购物车清单")
        ids = {i["id"] for i in w.cart}
        self.state["rooms"][rid]["targets"] = [t for t in targets if t["id"] in ids]


class FakeCloud:
    def __init__(self):
        self.calls = []
        self.queue = []

    def invoke(self, body):
        self.calls.append(body)
        cmds, self.queue = self.queue, []
        return {"commands": cmds}


def make():
    mon, fc = FakeMonitor(), FakeCloud()
    return mon, fc, cloud.CloudSync(mon, fc, resolver=lambda t: cloud.resolve_room_url(t))


def run(c):
    return asyncio.run(c)


def test_only_send_changes():
    mon, fc, s = make()
    mon.add_room("https://live.douyin.com/111")
    run(s.tick())
    assert "rooms" in fc.calls[0] and fc.calls[0].get("heartbeat")
    run(s.tick())
    assert "rooms" not in fc.calls[1] and "carts" not in fc.calls[1]
    mon.workers["111"].cart = [{"id": "p1", "index": 1, "title": "a", "price": 1}]
    run(s.tick())
    assert "111" in fc.calls[2]["carts"] and "rooms" in fc.calls[2]  # cart_count 变了


def test_failed_sync_resends():
    mon, fc, s = make()
    mon.add_room("https://live.douyin.com/111")

    def boom(body):
        raise RuntimeError("network")

    fc.invoke, real = boom, fc.invoke
    try:
        run(s.tick())
    except RuntimeError:
        pass
    fc.invoke = real
    run(s.tick())
    assert "rooms" in fc.calls[-1]


def test_commands_and_results():
    mon, fc, s = make()
    fc.queue = [
        {"_id": "c1", "type": "add_room", "room": None, "payload": {"text": "看直播 https://live.douyin.com/222?from=x"}},
        {"_id": "c2", "type": "set_targets", "room": "222", "payload": {"targets": [{"id": "p1"}]}},
        {"_id": "c3", "type": "add_room", "room": None, "payload": {"text": "乱打的"}},
    ]
    assert run(s.tick()) == 3
    r = {x["id"]: x for x in s.results}
    assert r["c1"]["ok"] and r["c1"]["room"] == "222"
    assert not r["c2"]["ok"] and "购物车" in r["c2"]["message"]  # 没开播不能设
    assert not r["c3"]["ok"]
    run(s.tick())
    assert len(fc.calls[-1]["results"]) == 3  # 结果送上去了
    assert s.results == []


def test_set_targets_reports_missing():
    mon, fc, s = make()
    mon.add_room("https://live.douyin.com/333")
    mon.workers["333"].cart = [{"id": "p1", "index": 1, "title": "a", "price": 1}]
    fc.queue = [{"_id": "c1", "type": "set_targets", "room": "333", "payload": {"targets": [{"id": "p1"}, {"id": "gone"}]}}]
    run(s.tick())
    assert s.results[0]["ok"] and "1 件已不在购物车" in s.results[0]["message"]


def test_remove_room_drops_cart_cache():
    mon, fc, s = make()
    mon.add_room("https://live.douyin.com/444")
    mon.workers["444"].cart = [{"id": "p1", "index": 1, "title": "a", "price": 1}]
    run(s.tick())
    assert "444" in s.sent_carts
    fc.queue = [{"_id": "c1", "type": "remove_room", "room": "444", "payload": None}]
    run(s.tick())
    run(s.tick())
    assert "444" not in s.sent_carts
    assert fc.calls[-1]["rooms"] == []


def test_same_command_not_applied_twice():
    # 2026-11-10 实测：云端没把指令标成完成，电脑一直重做同一个指令
    mon, fc, s = make()
    mon.add_room("https://live.douyin.com/555")
    mon.workers["555"].cart = [{"id": "p1", "index": 1, "title": "a", "price": 1}]
    cmd = {"_id": "c1", "type": "set_targets", "room": "555", "payload": {"targets": [{"id": "p1"}]}}
    calls = []
    real = mon.set_targets
    mon.set_targets = lambda rid, t: (calls.append(rid), real(rid, t))
    fc.queue = [cmd]
    assert run(s.tick()) == 1
    fc.queue = [cmd]  # 云端又送来同一个
    assert run(s.tick()) == 0
    assert len(calls) == 1
    assert s.results and s.results[0]["id"] == "c1"  # 只重送结果


def test_pause_resume_commands():
    mon, fc, s = make()
    mon.paused = False

    async def pause():
        mon.paused = True

    async def resume():
        mon.paused = False

    mon.pause, mon.resume = pause, resume
    run(s.tick())  # 第一次带心跳
    fc.queue = [{"_id": "c1", "type": "pause", "room": None, "payload": None}]
    run(s.tick())
    assert mon.paused and s.results[0]["ok"]
    run(s.tick())
    assert fc.calls[-1]["pc"] == {"paused": True} and fc.calls[-1]["heartbeat"]  # 关着时每次都带心跳
    fc.queue = [{"_id": "c2", "type": "resume", "room": None, "payload": None}]
    run(s.tick())
    assert not mon.paused
    run(s.tick())
    assert fc.calls[-1]["pc"] == {"paused": False}  # 开关一变马上回报


def test_notify_credentials_sent_once():
    # 公众号数据只随心跳送一次，有变才再送；送失败下次重送
    mon, fc, s = make()
    mon.creds = {"appid": "a", "appsecret": "b", "openid": "c", "template_id": "d"}
    run(s.tick())
    assert fc.calls[0]["notify"] == mon.creds
    for _ in range(HEARTBEAT_EVERY):
        run(s.tick())
    assert fc.calls[-1].get("heartbeat") and "notify" not in fc.calls[-1]
    mon.creds = {**mon.creds, "openid": "changed"}
    for _ in range(HEARTBEAT_EVERY):
        run(s.tick())
    assert fc.calls[-1]["notify"]["openid"] == "changed"


def test_watch_and_captcha_commands():
    mon, fc, s = make()
    mon.add_room("https://live.douyin.com/666")
    calls = []

    async def watch(rid, on):
        calls.append((rid, on))

    mon.watch = watch
    w = mon.workers["666"]
    w.shot = None

    async def remote_input(payload):
        calls.append(("input", payload["kind"]))
        return "验证完成"

    w.remote_input = remote_input
    fc.queue = [{"_id": "c1", "type": "watch", "room": "666", "payload": None},
                {"_id": "c2", "type": "unwatch", "room": "666", "payload": None},
                {"_id": "c3", "type": "captcha_input", "room": "666", "payload": {"kind": "drag", "points": [[0, 0, 0]]}}]
    run(s.tick())
    assert calls == [("666", True), ("666", False), ("input", "drag")]
    assert all(r["ok"] for r in s.results) and s.results[2]["message"] == "验证完成"


def test_captcha_shot_sent_once_then_cleared():
    mon, fc, s = make()
    mon.add_room("https://live.douyin.com/777")
    w = mon.workers["777"]
    w.shot = None
    run(s.tick())
    assert "captchas" not in fc.calls[-1]
    w.shot = {"img": "abc", "w": 300, "h": 200, "v": 1, "t": 0}
    run(s.tick())
    assert fc.calls[-1]["captchas"]["777"]["v"] == 1
    run(s.tick())
    assert "captchas" not in fc.calls[-1]  # 没换就不重送
    w.shot = None
    run(s.tick())
    assert fc.calls[-1]["captchas"] == {"777": None}  # 验证完成要告诉云端


def test_resolve_room_url():
    assert cloud.resolve_room_url("https://live.douyin.com/470703347283?from_search=true") == "https://live.douyin.com/470703347283"


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
