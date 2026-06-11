from __future__ import annotations

import queue
import threading
import traceback
from typing import Optional

from patch.brain import Brain
from patch.config import AppConfig
from patch.contracts import MemoryTask
from patch.memory import SQLiteMemoryStore
from patch.memory.episodic import build_episodic_index
from patch.perf import PerfLogger


class MemoryMaintenanceWorker:
    """Runs episodic indexing and summary/fact distillation off the hot path.

    The worker owns its own SQLite connection and episodic index, both created
    inside the worker thread: sqlite3 connections are bound to the thread that
    creates them, and embedding models (LanceDB backend) should load off the
    main thread anyway.

    `idle_event` is set while no foreground turn is generating. The worker
    waits for it before each task so a background distillation LLM call never
    competes with the user's turn for the single llama-server.
    """

    def __init__(
        self,
        *,
        config: AppConfig,
        provider_registry: dict[str, object],
        persona: str,
        idle_event: Optional[threading.Event] = None,
        perf_logger: Optional[PerfLogger] = None,
    ) -> None:
        self._queue: queue.Queue[Optional[MemoryTask]] = queue.Queue()
        self._config = config
        self._provider_registry = provider_registry
        self._persona = persona
        self._idle_event = idle_event
        self._perf_logger = perf_logger
        self._thread = threading.Thread(target=self._run, name="patch-memory-worker", daemon=True)
        self._thread.start()

    def submit(self, task: MemoryTask) -> None:
        self._queue.put(task)

    def close(self) -> None:
        self._queue.put(None)
        self._thread.join(timeout=10)

    def _run(self) -> None:
        store = SQLiteMemoryStore(self._config.database_path)
        episodic_index = None
        if self._config.episodic_enabled:
            try:
                episodic_index = build_episodic_index(
                    backend=self._config.episodic_backend,
                    store=store,
                    data_dir=self._config.data_dir,
                )
            except RuntimeError as exc:
                print(f"[memory-worker] episodic backend unavailable: {exc}")
        brain = Brain(
            config=self._config,
            memory_store=store,
            provider_registry=self._provider_registry,
            persona=self._persona,
            episodic_index=episodic_index,
        )
        try:
            while True:
                task = self._queue.get()
                if task is None:
                    self._queue.task_done()
                    return
                if self._idle_event is not None:
                    self._idle_event.wait()
                try:
                    timings = brain.process_memory_task(task)
                    if self._perf_logger is not None:
                        self._perf_logger.log({"phase": "memory_task", **timings})
                except Exception:
                    # A failed memory task must never kill the worker thread;
                    # the user already has their reply.
                    traceback.print_exc()
                finally:
                    self._queue.task_done()
        finally:
            store.close()
