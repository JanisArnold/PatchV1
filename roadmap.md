# PATCH Roadmap

## Goal

This roadmap shows the practical next steps from the current text-only V0 prototype to a Raspberry Pi companion build.

It is intentionally execution-oriented:

- what to finish now
- what to test next
- what to move to the Pi
- what to optimize later

## Current state

PATCH is currently in `V0`.

What exists now:

- terminal chat loop
- local Ollama model support
- SQLite memory
- fact extraction
- rolling summaries
- model benchmarking
- public contributor docs

What does not exist yet:

- speech-to-text
- text-to-speech
- camera integration
- face/display UI
- Pi deployment validation

## Phase 1: Finish V0 on PC

### Objective

Choose a realistic local default model and confirm the core brain behaves well before touching hardware.

### Tasks

1. Run clean model comparisons using [docs/testing.md](docs/testing.md).
2. Compare at least:
   - `gemma4:e2b`
   - `qwen3.5:2b`
   - `qwen3.5:4b`
   - `gemma4:e4b`
   - `phi4-mini`
3. Use a fresh `data/patch.db` for each clean comparison.
4. Evaluate:
   - latency
   - companion tone
   - planning quality
   - memory usefulness
   - practicalness of replies
5. Run `/benchmark` after manual testing for a rough speed snapshot.

### Expected outcome

Pick two likely winners:

- `PC winner`
- `Pi candidate`

Most likely:

- PC winner: `gemma4:e4b` or `qwen3.5:4b`
- Pi candidate: `gemma4:e2b`

## Phase 2: Lock the Pi-first model strategy

### Objective

Decide how PATCH should behave on constrained hardware.

### Current direction

- one local production-style default model
- model-named profiles kept for testing
- cloud disabled by default
- cloud later only for heavier tasks when connected

### Recommended Pi-first decision

- use `gemma4:e2b` as the default local Pi model unless testing proves otherwise
- avoid frequent local model switching
- keep context compact with retrieval and summaries instead of relying on giant prompts

## Phase 3: Provision the Raspberry Pi

### Objective

Prepare the Pi as a deployment target, not as the primary development machine.

### Tasks

1. Flash `Raspberry Pi OS 64-bit`.
2. Enable SSH and set hostname/user during imaging.
3. Boot and update the system.
4. Install:
   - `python3`
   - `python3-venv`
   - `python3-pip`
   - `git`
   - `sqlite3`
   - `curl`
5. Install Ollama on the Pi only if the Pi itself is expected to host the local model.
6. Pull `gemma4:e2b` first.

### References

- [docs/pi-setup.md](docs/pi-setup.md)

## Phase 4: Deploy PATCH to the Pi in terminal mode

### Objective

Prove that the current V0 brain runs on the Pi before adding any hardware adapters.

### Tasks

1. Clone the project on the Pi with Git.
2. Create a fresh `.venv` on the Pi.
3. Install requirements.
4. Create `config/settings.json` from the example file.
5. Start PATCH in terminal mode.

### Acceptance checks

PATCH should:

- start successfully
- reach Ollama
- create and use SQLite memory
- support `/models`
- support `/facts`
- support `/benchmark`

### References

- [docs/deployment.md](docs/deployment.md)
- [docs/testing.md](docs/testing.md)

## Phase 5: Add voice and audio

### Objective

Add natural interaction without overloading the Pi 4.

### Recommended first approach

- `push-to-talk`, not always-listening
- offline-first speech stack
- one full request-response pipeline at a time
- validate raw microphone and speaker behavior with ALSA before integrating STT or TTS

### Likely stack

- STT: `Vosk` first, `whisper.cpp` only if latency is acceptable
- local model: `gemma4:e2b`
- TTS: `Piper`
- low-level device testing: `arecord`, `aplay`, `alsamixer`
- useful Pi packages/tools: `alsa-utils`, `ffmpeg`, `piper-tts`, `vosk`

### Pipeline

1. user triggers listening
2. record audio
3. speech-to-text
4. retrieve memory
5. local model reply
6. text-to-speech
7. audio playback

### Acceptance checks

- microphone is understandable at close range
- mono speaker playback is clear enough for speech
- Piper can generate and play a clear local voice sample
- speech is transcribed reliably enough for short commands
- roundtrip latency feels acceptable
- voice does not break memory behavior

## Phase 6: Add camera and display

### Objective

Add the visual companion layer without turning the Pi 4 into a constant computer vision box.

### Recommended first approach

- camera snapshots only on demand
- no constant video processing
- one fullscreen eye/face UI

### Likely stack

- camera: `Picamera2`
- display UI: lightweight fullscreen app

### Initial use cases

- “What do you see?”
- snapshot-assisted context
- eye/emotion state based on runtime state:
  - idle
  - listening
  - thinking
  - speaking
  - error

## Phase 7: Optimize the Pi

### Objective

Measure real bottlenecks and reduce latency, CPU load, and instability.

### What to measure

- STT time
- retrieval time
- model generation time
- TTS time
- total roundtrip time
- CPU usage
- RAM usage
- thermal/throttling state
- real power usage if external measurement hardware is available

The current codebase now includes a first internal performance log for:

- turn timing
- model timing
- memory timing
- Raspberry Pi system snapshots via `vcgencmd` when available

### System-level tools to use later

- `htop`
- `pidstat`
- `/usr/bin/time -v`
- `vcgencmd measure_temp`
- `vcgencmd get_throttled`

### Optimization priorities

1. one local model only
2. small context windows
3. on-demand camera only
4. push-to-talk only
5. retrieval-based memory
6. cloud fallback only for genuinely heavier tasks

## Phase 8: Future upgrades

### After Pi 4 V1 is stable

Potential future directions:

- Raspberry Pi 5
- AI accelerators
- better microphone array
- servo control
- LEDs
- richer multimodal behavior
- smarter cloud escalation

### Architectural rule

Keep the brain core stable and swap adapters around it.

That means these should stay reusable:

- orchestrator
- provider abstraction
- memory schema
- summary logic
- fact extraction
- testing flow

## Immediate next step

The next practical step right now is:

1. finish clean V0 model comparisons on PC
2. choose the likely Pi default
3. then provision the Raspberry Pi

Do not start with hardware integration before terminal mode works well on the target model.
