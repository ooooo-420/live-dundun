"""通知规则。纯逻辑，不碰浏览器和网络，方便单独测试。

用语：
- 快照：用户设置目标时，购物车当下的商品顺序（商品 ID 清单）。
- pos：商品在快照里排第几（从 1 起）。B 型直播间的 pos 就是画面号码。
"""

from __future__ import annotations

MISSED_MAX_STEP = 3  # 上一件和这件在快照里相差超过这个数，就当作跳着讲，不发错过提醒


def snapshot_pos(snapshot: list[str], pid: str | None) -> int | None:
    if pid and pid in snapshot:
        return snapshot.index(pid) + 1
    return None


def evaluate(room: dict, explained_pid: str) -> list[tuple[dict, str, str]]:
    """主播换讲解到 explained_pid 时调用。回传要发的通知 [(目标, 种类, 状态文本)]，并更新目标的已发记录。

    room 需要的字段：snapshot、targets、last_pos（上一件讲解商品的快照位置，可为 None）。
    """
    snapshot = room.get("snapshot", [])
    pos_now = snapshot_pos(snapshot, explained_pid)
    prev = room.get("last_pos")
    out: list[tuple[dict, str, str]] = []

    for t in room.get("targets", []):
        sent = t.setdefault("sent", {})
        tpos = t["pos"]

        if explained_pid == t["id"]:
            t["explained"] = True
            if t.get("arrive", True) and not sent.get("arrive"):
                sent["arrive"] = True
                out.append((t, "arrive", "正在讲解，快去抢"))
            continue

        if pos_now is None or t.get("explained"):
            continue

        ahead = int(t.get("ahead") or 0)
        if ahead > 0 and not sent.get("ahead"):
            d = tpos - pos_now
            if 0 < d <= ahead:
                sent["ahead"] = True
                out.append((t, "ahead", f"快到了，还差 {d} 件"))

        if t.get("missed") and not sent.get("missed"):
            # 只有“一件件往后讲”时越过目标才算错过；一下跳很远表示是跳着讲，不算
            if pos_now > tpos and prev is not None and prev < tpos and pos_now - prev <= MISSED_MAX_STEP:
                sent["missed"] = True
                out.append((t, "missed", "可能被跳过了"))

    if pos_now is not None:
        room["last_pos"] = pos_now
    return out


def detect_type(prev_index: int | None, new_index: int | None) -> str | None:
    """换讲解后判断直播间类型。A：讲解中的商品被置顶成 1 号；B：号码不变。"""
    if prev_index is None or new_index is None:
        return None
    if prev_index != 1 and new_index == 1:
        return "A"
    if prev_index == new_index:
        return "B"
    return None
