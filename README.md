# PATCH V0 Brain Platform

PATCH V0 is the Pi-first brain runtime for PATCH, a desktop AI companion. It currently supports:

- terminal chat
- SQLite memory with summaries and durable facts
- `llama.cpp` via external `llama-server`
- runtime modes tuned for Pi latency
- background memory maintenance
- per-stage performance logging
- a standalone Pi voice-loop harness using Vosk + Piper

## Repo status

- `V0` is still CLI-first, but the runtime is now structured for Pi audio, future eye-display states, and later camera support.
- `llama.cpp` is the default local runtime target.
- Cloud fallback is still planned, but disabled by default.
- Screen and camera support are planned into the architecture, but kept out of the hot path for now.

## Quick start

1. Install Python 3.9 or newer.
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
- `data/patch.db`
- `knowledgebase.md`
- local logs, temp WAV files, and model artifacts

## Documentation

- [Setup](docs/setup.md) - local PC setup and first run
- [Testing Guide](docs/testing.md) - commands, runtime modes, benchmarks, and Pi measurements
- [Pi Setup](docs/pi-setup.md) - Raspberry Pi provisioning, `llama.cpp`, ALSA, Vosk, and Piper
- [Deployment](docs/deployment.md) - moving PATCH from PC to Pi
- [Architecture](docs/architecture.md) - hot path, background work, and adapter boundaries
- [Configuration](docs/configuration.md) - config schema, profiles, and runtime modes
- [Memory](docs/memory.md) - SQLite schema and retrieval design
- [Operations](docs/operations.md) - runtime files and diagnostics
- [V1 Roadmap](docs/v1-roadmap.md) - summary pointer to the main roadmap
- [Roadmap](roadmap.md) - staged plan from CLI to voice, display, camera, and Pi optimization

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributor setup and local-file guidance.
