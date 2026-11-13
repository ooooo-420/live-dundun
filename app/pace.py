"""主播讲一件商品大概多久。纯逻辑，不碰浏览器和网络。

做法：记下每次换讲解的（时间、号码）。只看最近几次“往后讲 1～3 件”的移动，算每件花几秒；
取中间值而不是平均（某一件讲特别久不会把估算拉歪），并给一个范围而不是单一数字。
跳着讲、样本太少时回 None（小程序就不显示预估时间）。
"""

from __future__ import annotations

import math

WINDOW = 5      # 只看最近几次移动：主播中途加快或放慢，几件之内就跟上
MIN_MOVES = 3   # 至少要有几次“照顺序往后讲”才估
MAX_STEP = 3    # 一次往后超过这么多件，当作跳着讲
MAX_DWELL = 30 * 60  # 一件超过半小时：多半是中场休息或断线，不算


def per_item(changes: list[tuple[float, int | None]]) -> dict | None:
    """changes：[(时间秒, 号码或 None), ...] 由旧到新。回 {"lo": 秒, "hi": 秒, "n": 样本数} 或 None。"""
    moves = list(zip(changes, changes[1:]))[-WINDOW:]
    per: list[float] = []
    for (t0, i0), (t1, i1) in moves:
        if i0 is None or i1 is None:
            continue
        step, dt = i1 - i0, t1 - t0
        if 1 <= step <= MAX_STEP and 0 < dt <= MAX_DWELL:
            per.append(dt / step)
    # 最近的移动里要大多数是照顺序的，才算“按顺序讲”的直播间
    if len(per) < MIN_MOVES or len(per) * 5 < len(moves) * 3:
        return None
    per.sort()
    n = len(per)
    lo = per[math.floor((n - 1) * 0.25)]
    hi = per[math.ceil((n - 1) * 0.75)]
    r5 = lambda x: max(5, int(round(x / 5.0)) * 5)  # 取整到 5 秒，免得每次都有一点点变动就重传云端
    return {"lo": r5(lo), "hi": r5(hi), "n": n}


def minutes(pace: dict | None, steps: int) -> tuple[int, int] | None:
    """还差 steps 件时，大约几分钟（下限, 上限）。"""
    if not pace or steps <= 0:
        return None
    lo = max(1, round(pace["lo"] * steps / 60))
    hi = max(lo, round(pace["hi"] * steps / 60))
    return lo, hi
