# PATCH Roadmap

## Current state

PATCH now has:

- CLI chat
- SQLite memory
- background fact extraction and summaries
- `llama.cpp` provider support
- runtime modes
- performance logging and Pi system snapshots
- a standalone Pi voice-loop harness

Still to add:

- integrated voice runtime inside the main app
- eye/display renderer
- camera snapshot path

## Phase 1: Stabilize the Pi-first runtime

1. keep `llama-server` external and manually managed
2. tune one GGUF model until `fast` mode is acceptable
3. compare `llm.generate` vs `turn.total`
4. confirm background memory work is not hurting the hot path

## Phase 2: Validate the voice loop

1. record with ALSA
2. transcribe with Vosk
3. reply through PATCH
4. speak with Piper
5. inspect `/perf`

Acceptance target:

- one complete spoken turn works reliably
- stage timings clearly show the biggest bottleneck

## Phase 3: Add display-state integration

1. keep orchestrator state changes as the source of truth
2. attach a lightweight eye/emotion display adapter
3. map:
   - `idle`
   - `listening`
   - `thinking`
   - `speaking`
   - `error`
4. confirm display updates do not slow reply timing

## Phase 4: Add on-demand camera support

1. keep camera disabled in normal chat
2. only invoke it on explicit vision turns
3. convert snapshots into compact text context
4. measure camera overhead separately from chat latency

## Phase 5: Integrate the voice path into the main runtime

After the standalone voice loop feels good:

1. add a real input adapter for STT
2. add a real output adapter for TTS
3. preserve the same hot path and performance logging

## Long-term direction

- Pi 5 and better cooling for stronger local models
- possible future PATCH-managed `llama-server` startup
- optional cloud escalation for heavy tasks
- richer multimodal behavior only after the local fast path is solid
