# Architecture

## Goal

PATCH is now organized around a Pi-first hot path:

1. capture input
2. classify the turn cheaply
3. retrieve only the minimum context needed
4. generate a reply through `llama.cpp`
5. return or speak the reply immediately
6. do memory maintenance in the background

The main rule is: display and camera features must react to state changes, not block the reply path.

## Runtime shape

- `orchestrator`
  Owns commands, turn lifecycle, runtime mode, state changes, and background task dispatch.
- `brain`
  Classifies turns, chooses a minimal retrieval plan, builds prompts, and talks to the configured provider.
- `memory`
  Stores turns, summaries, facts, benchmarks, performance logs, and system snapshots in SQLite.
- `providers`
  Runtime integrations. `llama.cpp` via external `llama-server` is the default target.
- `adapters`
  Input/output backends plus reserved display and vision slots.
- `background worker`
  Handles fact extraction and summary generation after the user already has the reply.

## Hot path vs background path

### Hot path

- text input now, STT transcript later
- cheap turn classification
- selective retrieval
- `llama.cpp` reply generation
- immediate terminal output or TTS handoff

### Background path

- durable fact extraction
- rolling summary generation
- future archival or annotation work

This split keeps the Pi focused on user-visible latency.

## Runtime modes

- `fast`
  Pi default. Minimal retrieval, low context expectations, reasoning off by default.
- `balanced`
  Richer retrieval for desktop or slower exploratory testing.
- `vision_test`
  Reserved for future camera-triggered turns without making camera part of normal chat.

## State channel

The orchestrator emits runtime states such as:

- `idle`
- `listening`
- `thinking`
- `speaking`
- `error`

The CLI can ignore them, debug mode can print them, and a future eye-display adapter can map them to animations.

## Voice loop proving ground

Before full app-level voice integration, the repo now supports a standalone Pi voice-loop harness:

1. record audio with ALSA
2. transcribe with Vosk
3. send transcript through PATCH
4. synthesize reply with Piper
5. play audio and log timings

This keeps audio bring-up measurable before it becomes part of the main runtime.
