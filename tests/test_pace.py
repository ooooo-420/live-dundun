"""预估时间的测试。用法：.venv\\Scripts\\python.exe tests\\test_pace.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import pace


def seq(dwells, start=1, steps=None):
    t, i, out = 0.0, start, [(0.0, start)]
    for k, d in enumerate(dwells):
        t += d
        i += steps[k] if steps else 1
        out.append((t, i))
    return out


def test_too_few_samples():
    assert pace.per_item(seq([180, 180])) is None


def test_steady():
    p = pace.per_item(seq([180, 170, 190, 180]))
    assert p and 170 <= p["lo"] <= p["hi"] <= 190 and p["n"] == 4


def test_speed_up_is_followed():
    # 前一小时 3 分钟一件，后来赶进度变 1 分钟一件：只看最近 5 次，估算跟着变快
    p = pace.per_item(seq([180] * 20 + [60] * 5))
    assert p["hi"] <= 65


def test_one_long_item_does_not_skew():
    # 中间有一件讲了 10 分钟：下限仍是平常的速度，上限也不会被拉到 10 分钟
    p = pace.per_item(seq([60, 60, 600, 60, 60]))
    assert p["lo"] == 60 and p["hi"] == 60


def test_jumping_room_gives_none():
    ch = [(0, 1), (60, 8), (120, 3), (180, 20), (240, 5), (300, 30)]
    assert pace.per_item(ch) is None


def test_skip_two_counts_per_item():
    # 一次往后 2 件、花 4 分钟 → 每件 2 分钟
    p = pace.per_item(seq([240, 240, 240], steps=[2, 2, 2]))
    assert p["lo"] == 120 and p["hi"] == 120


def test_break_is_ignored():
    # 中场休息 40 分钟不算进去
    p = pace.per_item(seq([120, 120, 2400, 120, 120]))
    assert p and p["hi"] == 120


def test_minutes():
    assert pace.minutes({"lo": 90, "hi": 150, "n": 5}, 4) == (6, 10)
    assert pace.minutes({"lo": 10, "hi": 10, "n": 5}, 1) == (1, 1)
    assert pace.minutes(None, 4) is None and pace.minutes({"lo": 60, "hi": 60, "n": 3}, 0) is None


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
