# Architecture

## Goal

PATCH is organized around a Pi-first hot path:

1. capture input
2. classify the turn cheaply
3. retrieve only the minimum context needed
4. generate a reply through `llama.cpp`, streaming tokens as they arrive
5. speak/print sentence-by-sentence while generation continues
6. do memory maintenance in the background

Two rules drive the design:

- display and camera features must react to state changes, not block the reply path
- the LLM is ~95% of the wait, so perceived speed comes from streaming and from keeping prompts small

## Runtime shape

- `orchestrator`
  Owns commands, turn lifecycle, runtime mode, state changes, streaming fan-out, and background task dispatch.
- `brain`
  Classifies turns, chooses a minimal retrieval plan (including per-turn thinking), builds prompts, and talks to the configured provider.
- `memory`
  Three tiers: recent turns, episodic exchanges, and durable facts, all in SQLite (episodic optionally in LanceDB). Also stores benchmarks, performance logs, and system snapshots.
- `streaming`
  `SentenceAssembler` turns the token stream into complete sentences so TTS can start speaking early.
- `providers`
  Runtime integrations. `llama.cpp` via external `llama-server` is the default target and supports SSE streaming, prompt caching, reply caps, and a thinking toggle.
- `adapters`
  Input/output backends plus reserved display and vision slots.
- `background worker`
  Handles fact extraction, episodic indexing, and summary generation after the user already has the reply. It owns its own SQLite connection (created inside the worker thread) and survives individual task failures.

## Hot path vs background path

### Hot path

- text input now, STT transcript later
- cheap turn classification (also decides thinking on/off for `think: "auto"` profiles)
- selective retrieval: facts + top-3 episodic memories only when the turn needs them
- `llama.cpp` reply generation, streamed
- token stream -> terminal, or sentence stream -> TTS

### Background path

- durable fact extraction
- episodic index writes (embedding happens here, never on the hot path)
- rolling summary generation
- future: consolidation of old episodes into compact facts

This split keeps the Pi focused on user-visible latency. SQLite runs in WAL mode so the two paths write through separate connections without blocking each other.

## Turn ordering

The user turn is saved to memory only after generation completes. This matters: recent-turn retrieval would otherwise include the current message, duplicating it in the prompt.

## Runtime modes

- `fast`
  Pi default. Minimal retrieval, small context, thinking off unless the turn is complex.
- `balanced`
  Richer retrieval for desktop or slower exploratory testing.
- `vision_test`
  Reserved for future camera-triggered turns without making camera part of normal chat.

## State channel

The orchestrator emits runtime states:

- `idle`
- `listening`
- `thinking` (from STT-finish until the first token — the natural "pondering eyes" window)
- `speaking` (from the first streamed token)
- `error`

The CLI can ignore them, debug mode can print them, and a future eye-display adapter can map them to animations.

## Voice loop proving ground

Before full app-level voice integration, the repo supports a standalone Pi voice-loop harness:

1. record audio with ALSA
2. transcribe with whisper.cpp `small.en` (or Vosk as fallback)
3. send transcript through PATCH with an `on_sentence` callback
4. synthesize each completed sentence with Piper while the LLM keeps generating
5. play sentences in order and log timings, including time-to-first-audio

This keeps audio bring-up measurable before it becomes part of the main runtime.
