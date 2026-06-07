# Configuration

PATCH loads JSON configuration from:

1. `PATCH_CONFIG_PATH` if set
2. `config/settings.json`
3. `config/settings.example.json`

Only the example config should be committed.

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
- `display_enabled`
- `camera_enabled`

### `memory`

- `recent_turn_limit`
- `max_fact_hits`
- `summary_turn_window`

### `providers`

- `active`
- `llama_cpp.base_url`
- `llama_cpp.timeout_seconds`
- `llama_cpp.external_server`
- `ollama.*`
  Kept for compatibility and comparison, but no longer the default Pi path.
- `cloud.*`
  Reserved for future heavy-load fallback.

### `audio`

- `input_device`
- `output_device`
- `record_seconds`
- `vosk_model_path`
- `piper_voice_dir`
- `piper_voice_name`

These are used by the standalone Pi voice-loop harness and prepare the main runtime for later audio integration.

### `model_profiles`

Each profile defines:

- `provider`
- `model`
- `model_path`
  Stored now so PATCH is ready for future server-launch management later.
- `temperature`
- `top_p`
- `num_ctx`
- `system_prompt`

Recommended pattern:

- `default`
  The active Pi winner.
- model-named test profiles
  Separate local candidates for benchmarking and comparison.

## Current default strategy

- one active local `llama.cpp` model
- one runtime mode chosen at startup
- manual model switching only when testing
- reasoning off by default on the Pi

## Example

See [config/settings.example.json](../config/settings.example.json).
