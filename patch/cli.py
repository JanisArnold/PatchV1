from __future__ import annotations

import threading

from patch.adapters import NoOpDisplayAdapter, NoOpVisionAdapter, TextInputAdapter, TextOutputAdapter
from patch.background import MemoryMaintenanceWorker
from patch.brain import Brain
from patch.config import load_config
from patch.memory import SQLiteMemoryStore
from patch.memory.episodic import build_episodic_index
from patch.perf import PerfLogger
from patch.personality import load_persona
from patch.providers import LlamaCppChatProvider, OllamaChatProvider
from patch.orchestrator import Orchestrator


def build_app() -> Orchestrator:
    config = load_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    memory_store = SQLiteMemoryStore(config.database_path)
    persona = load_persona()
    perf_logger = PerfLogger(config.data_dir / "perf.jsonl")
    # Set while no foreground turn is generating; gates background LLM work.
    idle_event = threading.Event()
    idle_event.set()
    providers = {
        "llama_cpp": LlamaCppChatProvider(
            base_url=config.llama_cpp_base_url,
            timeout_seconds=config.llama_cpp_timeout_seconds,
        ),
        "ollama": OllamaChatProvider(
            base_url=config.ollama_base_url,
            timeout_seconds=config.ollama_timeout_seconds,
        )
    }
    episodic_index = None
    if config.episodic_enabled:
        episodic_index = build_episodic_index(
            backend=config.episodic_backend,
            store=memory_store,
            data_dir=config.data_dir,
        )
    brain = Brain(
        config=config,
        memory_store=memory_store,
        provider_registry=providers,
        persona=persona,
        episodic_index=episodic_index,
    )
    background_worker = MemoryMaintenanceWorker(
        config=config,
        provider_registry=providers,
        persona=persona,
        idle_event=idle_event,
        perf_logger=perf_logger,
    )
    return Orchestrator(
        config=config,
        brain=brain,
        memory_store=memory_store,
        input_adapter=TextInputAdapter(),
        output_adapter=TextOutputAdapter(),
        background_worker=background_worker,
        perf_logger=perf_logger,
        idle_event=idle_event,
        display_adapter=NoOpDisplayAdapter(),
        vision_adapter=NoOpVisionAdapter(),
    )


def main() -> None:
    app = build_app()
    try:
        app.run()
    finally:
        app.close()


if __name__ == "__main__":
    main()
