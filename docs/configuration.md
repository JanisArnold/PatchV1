# Configuration

PATCH loads JSON configuration from:

1. `PATCH_CONFIG_PATH` if set
2. `config/settings.json`
3. `config/settings.example.json`

Only the example config should be committed. Missing keys fall back to sensible defaults, so older configs keep working.

## Main sections

### `app`

- `name`
- `data_dir`
- `benchmark_prompt_path`
- `debug`
- `default_profile`
- `runtime_mode`
  - `fast`
  - `balanced`
  - `vision_test`
- `stream_responses`
  Stream tokens as they generate (default `true`). This is what lets TTS start speaking the first sentence while the rest is still generating.
- `display_enabled`
- `camera_enabled`

### `memory`

- `recent_turn_limit`
- `max_fact_hits`
- `summary_turn_window`
- `episodic_enabled` (default `true`)
- `episodic_backend`
  - `keyword` (default): zero-dependency FTS5/BM25 retrieval in SQLite
  - `lancedb`: disk-based vectors + `all-MiniLM-L6-v2` embeddings (`pip install lancedb sentence-transformers`)
- `max_episodic_hits` (default `3` — keep retrieval aggressive; prompt size is latency)

### `providers`

- `active`
- `llama_cpp.base_url`
- `llama_cpp.timeout_seconds`
- `llama_cpp.external_server`
- `ollama.*`
  Kept for compatibility and desktop comparison, but not the Pi path.
- `cloud.*`
  Reserved for future heavy-load fallback.

### `audio`

- `input_device`
- `output_device`
- `record_seconds`
  Maximum recording length for the voice loop. Recording is push-to-talk style (Enter to stop), so this is a safety cap, not a fixed duration.
- `stt_engine`
  - `whisper_cpp` (default, per the spec: `small.en`, int8)
  - `vosk` (fallback)
- `whisper_cpp_binary` (default `whisper-cli`)
- `whisper_model_path` (e.g. `stt-models/ggml-small.en-q8_0.bin`)
- `vosk_model_path`
- `piper_voice_dir`
- `piper_voice_name`

These are used by the standalone Pi voice-loop harness and prepare the main runtime for later audio integration.

### `model_profiles`

Each profile defines:

- `provider`
- `model`
- `model_path`
  Stored so PATCH is ready for future server-launch management.
- `temperature`
- `top_p`
- `num_ctx`
  Cap at 2048 on a Pi 4 (4096 on a Pi 5): a smaller KV cache means less memory traffic per token.
- `max_tokens`
  Hard cap on reply length. A companion doesn't need to monologue, and every saved token is saved seconds on a Pi.
- `think`
  `true` / `false`. **Keep it `false` on the Pi**: thinking tokens are generated and discarded before the reply, and at ~2.3 tok/s a single thinking turn costs over a minute. Toggle per session with `/reasoning on|off` when a question genuinely needs it.
- `system_prompt`
  Ask for concise replies here; it is free latency.

Recommended pattern:

- `default`
  The active Pi model: `gemma-4-e2b-it-qat-q4_0`. Always prefer the official `-qat-` checkpoints over community PTQ quants — same RAM, meaningfully smarter.
- model-named test profiles
  Separate local candidates for benchmarking and comparison (e.g. `gemma-4-e4b-qat` for Pi 5 class hardware).

## Current default strategy

- one active local `llama.cpp` model, kept warm via external `llama-server`
- one runtime mode chosen at startup
- streaming on, reply caps on, thinking off
- manual model switching only when testing

## Example

See [config/settings.example.json](../config/settings.example.json).
