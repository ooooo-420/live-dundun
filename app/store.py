"""設定和狀態存檔：data/state.json。另外把每個事件寫進 logs/日期.jsonl。"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
LOGS = ROOT / "logs"
STATE = DATA / "state.json"


def room_id_from_url(url: str) -> str | None:
    m = re.search(r"live\.douyin\.com/(\d+)", url)
    return m.group(1) if m else None


def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {"rooms": {}}


def save(state: dict) -> None:
    DATA.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def log(event: str, **kw) -> None:
    LOGS.mkdir(exist_ok=True)
    rec = {"t": datetime.now().isoformat(timespec="seconds"), "event": event, **kw}
    with (LOGS / f"{datetime.now():%Y-%m-%d}.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
