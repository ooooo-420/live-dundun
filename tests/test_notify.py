"""通知的重試和多管道：不連網路。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import notify  # noqa: E402

notify.RETRY_WAIT = (0, 0)  # 測試不要真的等

CFG = {"wechat": {"appid": "a", "appsecret": "b", "openid": "c", "template_id": "d"},
       "bark": {"url": "https://api.day.app/key"}}


class Flaky:
    def __init__(self, fail_times):
        self.fail_times, self.calls = fail_times, 0

    def send(self, *a):
        self.calls += 1
        if self.calls <= self.fail_times:
            raise RuntimeError("網路抖")


def make(wechat_fail=0, bark_fail=None):
    n = notify.Notifier(CFG)
    n.channels = [("wechat", Flaky(wechat_fail))]
    if bark_fail is not None:
        n.channels.append(("bark", Flaky(bark_fail)))
    return n


def test_retry_then_ok():
    n = make(wechat_fail=2)
    assert n.send("r", "p", "s") == {"wechat": "ok"}
    assert n.channels[0][1].calls == 3


def test_all_fail_raises():
    n = make(wechat_fail=99, bark_fail=99)
    try:
        n.send("r", "p", "s")
        assert False, "應該要拋錯"
    except RuntimeError as e:
        assert "wechat" in str(e) and "bark" in str(e)


def test_one_channel_ok_is_success():
    n = make(wechat_fail=99, bark_fail=0)
    r = n.send("r", "p", "s")
    assert r["bark"] == "ok" and r["wechat"] != "ok"


def test_bark_only_when_filled():
    assert len(notify.Notifier(CFG).channels) == 2
    assert len(notify.Notifier({"wechat": CFG["wechat"]}).channels) == 1
    assert len(notify.Notifier({"wechat": CFG["wechat"], "bark": {"url": "選填。..."}}).channels) == 1


def test_credentials():
    assert notify.Notifier(CFG).credentials() == CFG["wechat"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
