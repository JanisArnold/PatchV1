# Testing Guide

## Goal

This guide covers:

- normal PATCH CLI testing
- runtime mode testing
- clean model comparisons
- Pi performance inspection
- the standalone voice-loop harness

## Before you start

Make sure:

- your chosen inference server is already running
- `config/settings.json` exists
- the profile names in config match the models exposed by your runtime

Recommended first start:

```powershell
.\.venv\Scripts\python.exe -m patch.cli
```

## Important testing rule

For fair model comparisons, use a fresh database for each model unless you are explicitly testing long-term memory behavior.

## Core commands

- `/help`
- `/models`
- `/mode [fast|balanced|vision_test]`
- `/use <profile-or-model>`
- `/reasoning on|off` (session-only; `/use <profile>` restores the configured value)
- `/think on|off` (alias)
- `/stream on|off`
- `/memory`
- `/facts`
- `/episodes <query>`
- `/summary`
- `/perf`
- `/system`
- `/debug on|off`
- `/benchmark`
- `/exit`

## What changed in the new runtime

- `fast` mode is the Pi-first default.
- replies stream token-by-token; with a TTS sink they stream sentence-by-sentence.
- episodic memory (past exchanges) is retrieved on memory-related and complex turns.
- episodic indexing and summary/fact distillation happen in the background, gated to run only while no foreground turn is generating.
- thinking is off by default; `/reasoning on` enables it for the session when a question needs it.
- `/perf` shows the last 20 records from `data/perf.jsonl` — one compact record per turn with all stage timings.
- provider-visible model lists come from the active provider, not specifically from Ollama.

## Recommended smoke test

1. Start PATCH.
2. Run:

```text
/help
/models
/mode
/system
```

3. Send one short message:

```text
Hey Patch, say one short sentence about yourself.
```

4. Inspect:

```text
/perf
```

What you want to see:

- provider health is good
- the active runtime mode is correct
- the turn completes
- `/perf` contains a `turn` record with:
  - `classification_ms`, `retrieval_ms`, `prompt_build_ms`
  - `first_token_ms` (when streaming — the perceived-latency number)
  - `llm_ms` and `total_ms`
  - `prompt_tokens` / `response_tokens` (a `response_tokens` count far above the visible reply means hidden thinking tokens — investigate)
  - and, after a few turns, `memory_task` records from the background worker

## Runtime mode testing

### `fast`

Use when:

- testing on the Pi
- prioritizing lowest latency
- avoiding unnecessary memory retrieval

Expected behavior:

- greetings and trivial turns skip facts and summary
- memory maintenance is still preserved in the background

### `balanced`

Use when:

- comparing richer retrieval behavior
- testing on desktop
- checking whether the extra context is worth the latency

### `vision_test`

Use when:

- preparing for future camera-triggered flows
- confirming the architecture can reserve a vision path without making it default

## Clean model comparison

1. Stop PATCH.
2. Reset or rename `data/patch.db`.
3. Start PATCH.
4. Run `/mode fast`.
5. Switch to one test profile with `/use`.
6. Run the same prompts in the same order.
7. Record latency, naturalness, memory behavior, and practicality.
8. Exit and repeat for the next model.

## Benchmark behavior

`/benchmark` runs a shared prompt set across configured profiles and appends one `benchmark` record per prompt/profile pair to `data/perf.jsonl`.

Use it for:

- rough latency comparisons
- smoke-testing all configured profiles
- regression checks after provider/runtime changes

Do not use it as the only decision tool for PATCH personality or companion quality.

## Pi voice-loop test

After whisper.cpp (or Vosk) and Piper are installed on the Pi:

```bash
python3 -m patch.voice_loop_test
```

What it does:

1. records from the configured input device until you press Enter (push-to-talk; `record_seconds` is the safety cap)
2. transcribes with the configured `stt_engine` (whisper.cpp by default)
3. sends the transcript through PATCH with sentence streaming
4. synthesizes each completed sentence with Piper while the LLM keeps generating
5. plays sentences in order
6. records extra timing phases in `data/perf.jsonl`

Additional voice-loop phases:

- `audio.capture`
- `stt.whisper_cpp` or `stt.vosk`
- `tts.first_audio` (time until PATCH starts speaking — the number that matters most)
- `audio.playback_total`
- `turn.voice_roundtrip`

## Pi performance checks

Inside PATCH:

```text
/perf
/system
```

In the shell:

```bash
vcgencmd measure_temp
vcgencmd get_throttled
vcgencmd measure_clock arm
```

Watch for:

- model generation time vs total turn time
- memory retrieval staying small on trivial turns
- temperature trends with and without a fan
- throttling during repeated requests
- whether the provider runtime is staying warm between requests
