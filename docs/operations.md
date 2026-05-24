# Operations

## Runtime files

Default folders:

- `data/`
- `data/benchmarks/`
- `logs/`

These runtime files are local-only and should not be committed to a public repo.

## Inspect the database

Use any SQLite browser or the `sqlite3` CLI to inspect:

- `data/patch.db`

## Reset development state

Delete or move:

- `data/patch.db`

PATCH will recreate the schema on the next launch.

## Debug mode

Toggle inside the app:

```text
/debug on
/debug off
```

Debug mode prints the memory bundle used for a reply and extra provider information.

## Common issues

### Ollama not reachable

Symptoms:

- `/models` shows a provider error
- chat replies fail before generation starts

Fix:

1. Start the Ollama daemon.
2. Verify `ollama list`.
3. Confirm `providers.ollama.base_url` in config.

### No matching profile

Use `/models` to list configured profiles, then `/use <profile>`.
