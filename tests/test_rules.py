import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.rules import detect_type, evaluate  # noqa: E402


def room(targets):
    return {"snapshot": [f"p{i}" for i in range(1, 51)], "targets": targets, "last_pos": None}


def kinds(out):
    return [k for _, k, _ in out]


def test_arrive_once():
    r = room([{"id": "p37", "pos": 37, "arrive": True}])
    assert kinds(evaluate(r, "p37")) == ["arrive"]
    assert kinds(evaluate(r, "p37")) == []


def test_ahead_sequential():
    r = room([{"id": "p37", "pos": 37, "arrive": True, "ahead": 3}])
    assert kinds(evaluate(r, "p30")) == []
    assert kinds(evaluate(r, "p34")) == ["ahead"]
    assert kinds(evaluate(r, "p35")) == []  # 只發一次
    assert kinds(evaluate(r, "p37")) == ["arrive"]


def test_missed_when_crossing():
    r = room([{"id": "p37", "pos": 37, "missed": True}])
    evaluate(r, "p36")
    assert kinds(evaluate(r, "p38")) == ["missed"]


def test_no_missed_on_big_jump():
    # 2026-11-09 實測：從 1 號直接跳到 8 號，不該說 4 號被跳過
    r = room([{"id": "p4", "pos": 4, "missed": True}])
    evaluate(r, "p1")
    assert kinds(evaluate(r, "p8")) == []


def test_no_missed_after_explained():
    r = room([{"id": "p37", "pos": 37, "missed": True}])
    evaluate(r, "p36")
    evaluate(r, "p37")
    assert kinds(evaluate(r, "p38")) == []


def test_unknown_product_ignored():
    r = room([{"id": "p37", "pos": 37, "ahead": 5}])
    assert evaluate(r, "new-item") == []
    assert r["last_pos"] is None


def test_detect_type():
    assert detect_type(15, 1) == "A"
    assert detect_type(15, 15) == "B"
    assert detect_type(1, 1) == "B"
    assert detect_type(None, 3) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
