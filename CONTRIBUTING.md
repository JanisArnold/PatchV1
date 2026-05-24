# Contributing

PATCH is an early-stage desktop companion project focused on a reusable local-first brain core that can later run on Raspberry Pi hardware.

## Before you start

1. Read [README.md](README.md).
2. Follow [docs/setup.md](docs/setup.md).
3. Use [docs/testing.md](docs/testing.md) for model comparisons and command behavior.

## Development expectations

- Keep changes small and focused.
- Prefer updating docs when behavior changes.
- Preserve the current architecture direction:
  - text-first V0
  - one production-style `default` profile
  - model-named local test profiles
  - cloud fallback disabled by default

## Local-only files

Do not commit local runtime artifacts such as:

- `.venv/`
- `config/settings.json`
- `data/patch.db`
- logs, caches, or machine-specific outputs

Use the committed example files instead:

- `config/settings.example.json`
- `config/persona.example.md`

## Testing

Run the documented local test flow from [docs/testing.md](docs/testing.md).

For automated checks, use your local Python environment:

```powershell
python -m unittest discover -s tests -v
```

## Pull request guidance

- Explain what changed and why.
- Note any user-visible behavior changes.
- Mention any docs you updated.
- If a change affects model testing, configuration, or deployment, update the relevant doc page in the same change.
