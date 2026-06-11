"""Append-only JSONL performance log.

One line per event (one per turn on the hot path) instead of a dozen SQLite
rows with individual commits. On a Pi every fsync hits the SD card, so the
telemetry must stay cheaper than the work it measures.
"""
from __future__ import annotations

import json
import threading
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Dict, List


class PerfLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def log(self, record: Dict[str, object]) -> None:
        entry = {"ts": datetime.now().isoformat(timespec="seconds")}
        entry.update(record)
        line = json.dumps(entry, ensure_ascii=True)
        with self._lock:
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    def tail(self, limit: int = 20) -> List[Dict[str, object]]:
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as handle:
            lines = deque(handle, maxlen=limit)
        records: List[Dict[str, object]] = []
        for line in lines:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return records
