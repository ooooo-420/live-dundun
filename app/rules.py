"""通知規則。純邏輯，不碰瀏覽器和網路，方便單獨測試。

用語：
- 快照：使用者設定目標時，購物車當下的商品順序（商品 ID 清單）。
- pos：商品在快照裡排第幾（從 1 起）。B 型直播間的 pos 就是畫面號碼。
"""

from __future__ import annotations

MISSED_MAX_STEP = 3  # 上一件和這件在快照裡相差超過這個數，就當作跳著講，不發錯過提醒


def snapshot_pos(snapshot: list[str], pid: str | None) -> int | None:
    if pid and pid in snapshot:
        return snapshot.index(pid) + 1
    return None


def evaluate(room: dict, explained_pid: str) -> list[tuple[dict, str, str]]:
    """主播換講解到 explained_pid 時呼叫。回傳要發的通知 [(目標, 種類, 狀態文字)]，並更新目標的已發記錄。

    room 需要的欄位：snapshot、targets、last_pos（上一件講解商品的快照位置，可為 None）。
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
                out.append((t, "arrive", "正在講解，快去搶"))
            continue

        if pos_now is None or t.get("explained"):
            continue

        ahead = int(t.get("ahead") or 0)
        if ahead > 0 and not sent.get("ahead"):
            d = tpos - pos_now
            if 0 < d <= ahead:
                sent["ahead"] = True
                out.append((t, "ahead", f"快到了，還差 {d} 件"))

        if t.get("missed") and not sent.get("missed"):
            # 只有「一件件往後講」時越過目標才算錯過；一下跳很遠表示是跳著講，不算
            if pos_now > tpos and prev is not None and prev < tpos and pos_now - prev <= MISSED_MAX_STEP:
                sent["missed"] = True
                out.append((t, "missed", "可能被跳過了"))

    if pos_now is not None:
        room["last_pos"] = pos_now
    return out


def detect_type(prev_index: int | None, new_index: int | None) -> str | None:
    """換講解後判斷直播間類型。A：講解中的商品被置頂成 1 號；B：號碼不變。"""
    if prev_index is None or new_index is None:
        return None
    if prev_index != 1 and new_index == 1:
        return "A"
    if prev_index == new_index:
        return "B"
    return None
