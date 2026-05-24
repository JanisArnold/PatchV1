from __future__ import annotations

from patch.adapters import TextInputAdapter, TextOutputAdapter
from patch.brain import Brain
from patch.config import load_config
from patch.memory import SQLiteMemoryStore
from patch.personality import load_persona
from patch.providers import OllamaChatProvider
from patch.orchestrator import Orchestrator


def build_app() -> Orchestrator:
    config = load_config()
    config.data_dir.mkdir(parents=True, exist_ok=True)
    memory_store = SQLiteMemoryStore(config.database_path)
    providers = {
        "ollama": OllamaChatProvider(
            base_url=config.ollama_base_url,
            timeout_seconds=config.ollama_timeout_seconds,
        )
    }
    brain = Brain(
        config=config,
        memory_store=memory_store,
        provider_registry=providers,
        persona=load_persona(),
    )
    return Orchestrator(
        config=config,
        brain=brain,
        memory_store=memory_store,
        input_adapter=TextInputAdapter(),
        output_adapter=TextOutputAdapter(),
    )


def main() -> None:
    app = build_app()
    try:
        app.run()
    finally:
        app.memory_store.close()


if __name__ == "__main__":
    main()
