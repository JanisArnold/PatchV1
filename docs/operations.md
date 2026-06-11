# Operations

## Runtime files

Default local runtime files include:

- `data/patch.db` (plus `patch.db-wal` and `patch.db-shm` — SQLite runs in WAL mode)
- `data/perf.jsonl` (append-only performance log, one JSON line per event)
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

PATCH appends performance records to `data/perf.jsonl` — one JSON line per event, never SQLite writes on the hot path. Record kinds (`phase` field):

- `turn`: one record per chat turn with all stage timings in one place:
  `classification_ms`, `retrieval_ms`, `prompt_build_ms`, `llm_ms`,
  `first_token_ms` (streaming only — the perceived-latency number), `total_ms`,
  plus token estimates, profile, model, and turn type
- `memory_task`: background worker timings (`episodic_ms`, `distill_ms`, `facts_extracted`)
- `benchmark`: one record per benchmark prompt/profile pair
- `system_snapshot`: Pi health captured by `/system` and after `/benchmark`
- voice-loop phases (`audio.capture`, `stt.*`, `tts.first_audio`, `audio.playback_total`, `turn.voice_roundtrip`)

Use:

```text
/perf      (last 20 records)
/system
```

The file is append-only and local-only; delete or truncate it whenever it grows annoying — nothing depends on its history.

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
- If the model keeps producing thinking tokens despite `think: false` (check `response_tokens` in `/perf` vs the visible reply length), disable thinking at the server instead: start `llama-server` with `--jinja --reasoning-budget 0`.

### Episodic memory returns nothing

Explanation:

- The keyword backend excludes the latest few episodes (they are already in the rolling context), so a fresh database needs a few exchanges before `/episodes` returns results.
- The `lancedb` backend needs its optional dependencies; if they are missing, the background worker prints a warning and PATCH falls back to running without episodic writes.

### Slow Pi replies

Check, in order of likely impact:

- `response_tokens` in `/perf` vs the reply you actually saw — a large gap means hidden thinking tokens; force them off (see above)
- whether `llama-server` runs with `--parallel 1` so background distillation queues instead of halving generation speed
- `first_token_ms` and `llm_ms` vs `total_ms` in `/perf`
- `/system` for temperature and throttling
- whether `fast` mode is active and streaming is on
- whether `max_tokens` and a concise system prompt are capping reply length
- whether the selected model/context is too heavy for the Pi (ctx 2048 on Pi 4)
