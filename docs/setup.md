# Setup

## Prerequisites

- Windows, Linux, or macOS
- Python 3.9+
- a running local inference server

The current default path is `llama.cpp` via external `llama-server`.

## 1. Install Python dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Start your local inference server

Start `llama-server` with a model ID that matches a profile in `config/settings.json`.

PATCH assumes the server is already running before you start the app.

## 3. Create your config

```powershell
Copy-Item config\settings.example.json config\settings.json
```

Optional environment variables:

- `PATCH_CONFIG_PATH`
- `PATCH_DATA_DIR`

## 4. Start PATCH

```powershell
python -m patch.cli
```

## 5. First commands

```text
/help
/models
/mode
/system
```

## 6. Next step after first run

Use [Testing Guide](testing.md) as the canonical workflow for:

- runtime mode testing
- model comparison
- benchmarks
- memory inspection
- Pi performance checks

For Raspberry Pi setup and deployment, see:

- [Pi Setup](pi-setup.md)
- [Deployment](deployment.md)
