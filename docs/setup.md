# Setup

## Prerequisites

- Windows, Linux, or macOS
- Python 3.9+
- Ollama installed locally

Recommended first models:

- `gemma4:e2b`
- `qwen3.5:2b`
- `qwen3.5:4b`

## 1. Install Python dependencies

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 2. Install and verify Ollama

After installing Ollama, verify the daemon is running:

```powershell
ollama list
```

Pull at least one model:

```powershell
ollama pull gemma4:e2b
```

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

## 5. Next step after first run

After PATCH starts successfully, use [Testing Guide](testing.md) as the canonical workflow for:

- command reference
- model comparison
- benchmark usage
- memory inspection

## Clean-room reproduction checklist

Another collaborator should be able to:

1. Clone or copy the repo.
2. Install Python.
3. Install Ollama.
4. Pull at least one documented model.
5. Copy `config/settings.example.json`.
6. Run `python -m patch.cli`.
7. Run `/benchmark`.

## Next step for Raspberry Pi

This page covers local PC development.

For Raspberry Pi setup and deployment, see:

- [Pi Setup](pi-setup.md)
- [Deployment](deployment.md)
