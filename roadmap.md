# PATCH Roadmap

## Current state

PATCH now has:

- CLI chat with token streaming
- three-tier memory: rolling context, episodic retrieval (SQLite FTS5/BM25), durable facts
- background memory distillation (one LLM call for summary + facts) gated to idle time
- `llama.cpp` provider with prompt caching, reply caps, and thinking control
- thinking off by default (`/reasoning on|off` per session)
- runtime modes, JSONL performance logging (incl. first-token latency), Pi system snapshots
- a standalone Pi voice-loop harness with push-to-talk recording and sentence-streamed TTS (whisper.cpp or Vosk)

Still to add:

- silero-VAD push-free listening and an integrated voice runtime in the main app
- LanceDB + all-MiniLM-L6-v2 episodic backend validated on the Pi
- memory consolidation job (episodes -> compact facts)
- function calling (time, reminders, explicit memory queries)
- eye/display renderer
- camera snapshot path (Gemma 4 is natively multimodal, so no second model needed)

## Phase 1: Stabilize the Pi-first runtime

1. keep `llama-server` external and manually managed
2. run `gemma-4-e2b-it-qat-q4_0` until `fast` mode is acceptable (~2-4 tok/s on Pi 4 is expected)
3. compare `first_token_ms` and `llm_ms` vs `total_ms` in `/perf`
4. confirm background memory work is not hurting the hot path

## Phase 2: Validate the voice loop

1. record with ALSA
2. transcribe with whisper.cpp `small.en` (int8) — Vosk stays as fallback
3. reply through PATCH with sentence streaming
4. speak with Piper as sentences complete
5. inspect `/perf`

Acceptance target:

- PATCH starts speaking within a couple of seconds of the first generated sentence
- stage timings clearly show the biggest bottleneck

## Phase 3: Speed work on the model path

1. build llama.cpp with ARM NEON/dotprod flags; run with `-t 4 -tb 4 --prio 3 -fa auto`
2. cap `--ctx-size` at 2048 on Pi 4
3. test speculative decoding with the Gemma 4 `-assistant` drafter (biggest free speedup)
4. move models and DB to NVMe if available; add zram swap and active cooling

## Phase 4: Add display-state integration

1. keep orchestrator state changes as the source of truth
2. attach a lightweight eye/emotion display adapter (`idle`, `listening`, `thinking`, `speaking`, `error`)
3. use the `thinking` state as the wait indicator the moment STT finishes
4. confirm display updates do not slow reply timing

## Phase 5: Integrate the voice path into the main runtime

After the standalone voice loop feels good:

1. add silero-VAD so PATCH listens without push-to-talk
2. add real input/output adapters for STT and TTS using the existing `on_sentence` streaming hook
3. preserve the same hot path and performance logging

## Phase 6: Memory depth

1. switch episodic backend to LanceDB + embeddings on the Pi
2. add the consolidation job: summarize old episodes into compact SQLite facts
3. let PATCH reason about when things happened (timestamps already stored)

## Phase 7: On-demand camera support

1. keep camera disabled in normal chat
2. only invoke it on explicit vision turns; feed frames directly to Gemma 4's image input
3. measure camera overhead separately from chat latency

## Long-term direction

- Pi 5 / 16 GB + `gemma-4-e4b-it-qat-q4_0` for the cleanest intelligence jump; Jetson Orin Nano for a big one
- possible future PATCH-managed `llama-server` startup (systemd)
- optional cloud escalation for heavy tasks
- richer multimodal behavior only after the local fast path is solid
