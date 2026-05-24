# Configuration

PATCH loads JSON configuration from:

1. `PATCH_CONFIG_PATH` if set
2. `config/settings.json`
3. `config/settings.example.json`

For public sharing and commits, only the example config should be tracked. Keep `config/settings.json` local.

## Main sections

### `app`

- `name`: assistant display name
- `data_dir`: location for database and runtime files
- `benchmark_prompt_path`: prompt set used by `/benchmark`
- `debug`: default debug mode
- `default_profile`: the profile PATCH starts with for normal use

### `memory`

- `recent_turn_limit`
- `max_fact_hits`
- `summary_turn_window`

### `providers`

- `active`: current provider key
- `ollama.base_url`
- `ollama.timeout_seconds`
- `cloud.enabled`: reserved for future cloud fallback
- `cloud.mode`: intended routing policy, currently `heavy_load_only`

### `model_profiles`

Each profile defines:

- `provider`
- `model`
- `temperature`
- `num_ctx`
- `top_p`
- `system_prompt`

Recommended structure:

- `default`: the current winning local model for normal use
- model-named test profiles such as `gemma4:e2b`, `qwen3.5:2b`, `qwen3.5:4b`

PATCH does not need to run all of these in production. They are primarily there so you can benchmark and switch clearly during testing, while `default` remains the one real startup choice.

## Example

See [config/settings.example.json](../config/settings.example.json).
