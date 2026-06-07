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

## Performance logging

PATCH now stores performance information in the local SQLite database.

Current logged categories include:

- total turn time
- model generation latency
- retrieval and prompt-building timing
- memory fact extraction timing
- memory summary timing
- Raspberry Pi system snapshots when available

Use these commands inside PATCH:

```text
/perf
/system
```

On Raspberry Pi, a manual shell-level check is also useful:

```bash
vcgencmd measure_temp
vcgencmd get_throttled
vcgencmd measure_clock arm
```

These are especially useful when testing fan effectiveness, thermal throttling, and model-related slowdowns.

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
