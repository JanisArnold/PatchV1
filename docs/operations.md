# Operations

## Runtime files

Default local runtime files include:

- `data/patch.db` (plus `patch.db-wal` and `patch.db-shm` — SQLite runs in WAL mode)
- `data/lancedb/` when the LanceDB episodic backend is active
- `data/voice_loop_input.wav`
- `data/voice_loop_tts/` (per-sentence TTS WAVs)
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
- `llm.first_token` (streaming only — the perceived-latency number)
- `llm.generate`
- `turn.total`
- `background.enqueue`
- `background.memory.fact_extraction`
- `background.memory.episodic_index`
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

### Reasoning toggle has no effect

Explanation:

- For `llama.cpp`, PATCH forwards the toggle as `chat_template_kwargs.enable_thinking`; models without a thinking channel simply ignore it.
- `/reasoning auto` is the recommended setting: thinking off for chat, on for complex turns.

### Episodic memory returns nothing

Explanation:

- The keyword backend excludes the latest few episodes (they are already in the rolling context), so a fresh database needs a few exchanges before `/episodes` returns results.
- The `lancedb` backend needs its optional dependencies; if they are missing, the background worker prints a warning and PATCH falls back to running without episodic writes.

### Slow Pi replies

Check:

- `/perf` for `llm.first_token` and `llm.generate` vs total turn time
- `/system` for temperature and throttling
- whether `fast` mode is active and streaming is on
- whether `max_tokens` and a concise system prompt are capping reply length
- whether the selected model/context is too heavy for the Pi (ctx 2048 on Pi 4)
