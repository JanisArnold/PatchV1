# PATCH Brain Platform

PATCH is a self-contained, offline AI desktop companion: everything runs locally, no cloud calls, full privacy. This repo is the Pi-first brain runtime. It currently supports:

- terminal chat with token streaming
- three-tier memory: rolling context, episodic retrieval, and durable SQLite facts
- `llama.cpp` via external `llama-server` (Gemma 4 E2B QAT is the target model)
- per-turn thinking control (`auto` keeps reasoning off for chat, on for hard questions)
- runtime modes tuned for Pi latency
- background memory maintenance off the hot path
- per-stage performance logging, including time-to-first-token
- a standalone Pi voice-loop harness (whisper.cpp or Vosk + Piper) with sentence-streamed TTS

## Guiding constraints

Fast enough to feel alive, efficient enough to fit in 8 GB, and smart enough to remember you.

- The LLM is ~95% of the wait on a Pi, so perceived speed comes from streaming: PATCH starts speaking the first sentence while the rest still generates.
- Memory grows on disk, not in RAM: only the relevant slice (top facts + top-3 episodes + recent turns) enters each prompt.
- Always use `-qat-` model checkpoints: same RAM as a normal 4-bit quant, meaningfully smarter.

## Repo status

- CLI-first, structured for Pi audio, future eye-display states, and later camera support.
- `llama.cpp` is the default local runtime target; Ollama remains supported for desktop comparison.
- Episodic memory ships with a zero-dependency keyword backend; LanceDB + embeddings is the configured upgrade path on the Pi.
- Cloud fallback is still planned, but disabled by default.

## Quick start

1. Install Python 3.9 or newer (3.12 recommended).
2. Start an external `llama-server` with your chosen GGUF model.
3. Create a virtual environment and install dependencies.
4. Copy the example config.
5. Start PATCH.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config\settings.example.json config\settings.json
python -m patch.cli
```

For the full local and Pi flow, see [docs/setup.md](docs/setup.md) and [docs/pi-setup.md](docs/pi-setup.md).

## Public repo safety

Commit only tracked examples and source files.

Keep local-only:

- `.venv/`
- `config/settings.json`
- `data/patch.db` (plus `-wal`/`-shm` sidecars) and `data/lancedb/`
- `knowledgebase.md`
- local logs, temp WAV files, and model artifacts

## Documentation

- [Setup](docs/setup.md) - local PC setup and first run
- [Testing Guide](docs/testing.md) - commands, runtime modes, benchmarks, and Pi measurements
- [Pi Setup](docs/pi-setup.md) - Raspberry Pi provisioning, `llama.cpp`, ALSA, whisper.cpp, and Piper
- [Deployment](docs/deployment.md) - moving PATCH from PC to Pi
- [Architecture](docs/architecture.md) - hot path, streaming, background work, and adapter boundaries
- [Configuration](docs/configuration.md) - config schema, profiles, and runtime modes
- [Memory](docs/memory.md) - three-tier memory design and retrieval
- [Operations](docs/operations.md) - runtime files and diagnostics
- [V1 Roadmap](docs/v1-roadmap.md) - summary pointer to the main roadmap
- [Roadmap](roadmap.md) - staged plan from CLI to voice, display, camera, and Pi optimization

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributor setup and local-file guidance.
