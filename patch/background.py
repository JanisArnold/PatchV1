from __future__ import annotations

import queue
import threading
from typing import Optional

from patch.brain import Brain
from patch.config import AppConfig
from patch.contracts import MemoryTask
from patch.memory import SQLiteMemoryStore


class MemoryMaintenanceWorker:
    def __init__(self, *, config: AppConfig, provider_registry: dict[str, object], persona: str) -> None:
        self._queue: queue.Queue[Optional[MemoryTask]] = queue.Queue()
        self._store = SQLiteMemoryStore(config.database_path)
        self._brain = Brain(
            config=config,
            memory_store=self._store,
            provider_registry=provider_registry,
            persona=persona,
        )
        self._thread = threading.Thread(target=self._run, name="patch-memory-worker", daemon=True)
        self._thread.start()

    def submit(self, task: MemoryTask) -> None:
        self._queue.put(task)

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=5)
        self._store.close()

    def _run(self) -> None:
        while True:
            task = self._queue.get()
            if task is None:
                self._queue.task_done()
                return
            self._brain.process_memory_task(task)
            self._queue.task_done()
