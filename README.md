# PATCH V0 Brain Platform

PATCH V0 is a text-only prototype of the PATCH desktop companion brain. It is designed to validate the permanent core of the system before any Raspberry Pi hardware is connected.

PATCH V0 can:

- chat in the terminal
- store memory in SQLite
- summarize older conversations so context does not grow forever
- extract durable user facts
- switch between Ollama-backed local models
- benchmark multiple local models against the same prompt set
- keep one startup default profile for production-style use while testing model-named profiles
- record per-turn performance timings and Raspberry Pi system snapshots when available

## Repo status

- `V0` is text-only and runs in the terminal.
- `V1` is planned as a Raspberry Pi companion build with voice, camera, and display adapters.
- The current local runtime is `Ollama` first.
- Cloud fallback is planned but disabled by default and intended only for heavier tasks later.

## Quick start

1. Install Python 3.9 or newer.
2. Install Ollama and pull at least one model.
3. Create a virtual environment and install dependencies.
4. Copy the example config.
5. Start PATCH.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item config\settings.example.json config\settings.json
python -m patch.cli
```

For full setup instructions, see [docs/setup.md](docs/setup.md).

## Public repo safety

Local runtime state is intentionally not meant to be committed.

Use:

- `config/settings.example.json`
- `config/persona.example.md`

Do not commit:

- `.venv/`
- `config/settings.json`
- `data/patch.db`
- local logs or caches

## Current scope

V0 intentionally uses text input and text output only. The goal is to prove the memory, orchestration, provider abstraction, and model-testing infrastructure that V1 will reuse on the Raspberry Pi.

## Documentation

- [Setup](docs/setup.md) - local PC setup and first run
- [Testing Guide](docs/testing.md) - commands, clean model comparisons, and benchmark behavior
- [Pi Setup](docs/pi-setup.md) - Raspberry Pi provisioning and base packages
- [Deployment](docs/deployment.md) - moving PATCH from PC to Pi and optional `systemd`
- [Architecture](docs/architecture.md) - module responsibilities and data flow
- [Configuration](docs/configuration.md) - config schema and profile strategy
- [Memory](docs/memory.md) - SQLite schema and retrieval design
- [Operations](docs/operations.md) - runtime files and common issues
- [V1 Roadmap](docs/v1-roadmap.md) - future voice, camera, and display path
- [Roadmap](roadmap.md) - consolidated next steps from PC testing to Pi deployment and optimization

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for contributor setup, test, and local-file guidance.
