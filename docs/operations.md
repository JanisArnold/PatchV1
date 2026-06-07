# Operations

## Runtime files

Default local runtime files include:

- `data/patch.db`
- `data/voice_loop_input.wav`
- `data/voice_loop_reply.wav`
- `data/benchmarks/`

These are local-only and should not be committed.

## Database inspection

Inspect:

- `data/patch.db`

with any SQLite browser or the `sqlite3` CLI.

## Reset development state

Delete or move:

- `data/patch.db`

PATCH will recreate the schema on next launch.

## Debug mode

Inside PATCH:

```text
/debug on
/debug off
```

Debug mode prints the memory bundle, turn plan, timings, and state transitions.

## Performance logging

PATCH stores per-stage performance information in SQLite.

Common logged phases now include:

- `input.capture`
- `turn.classification`
- `memory.retrieval`
- `prompt.assembly`
- `llm.generate`
- `turn.total`
- `background.enqueue`
- `background.memory.fact_extraction`
- `background.memory.summary`
- `display.state_update`
- Pi voice-loop phases when used

Use:

```text
/perf
/system
```

## Common issues

### `llama.cpp` not reachable

Symptoms:

- `/models` shows provider errors
- chat fails before generation starts

Fix:

1. Start `llama-server`.
2. Verify the configured `providers.llama_cpp.base_url`.
3. Confirm the running server exposes the configured model IDs.

### Reasoning toggle unsupported

Symptoms:

- `/think off` reports that the provider does not support reasoning toggle

Explanation:

- `llama.cpp` does not currently use the Ollama-style think toggle in PATCH
- handle reasoning behavior through your chosen model, prompt, and server configuration instead

### Slow Pi replies

Check:

- `/perf` for `llm.generate` vs total turn time
- `/system` for temperature and throttling
- whether `fast` mode is active
- whether the selected model/context is too heavy for the Pi
