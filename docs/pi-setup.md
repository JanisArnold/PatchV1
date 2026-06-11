# Pi Setup

## Goal

Use your PC for development and the Pi as the target integration machine. The current Pi-first runtime assumes:

- Raspberry Pi OS Lite 64-bit (no desktop saves ~300 MB RAM and idle CPU)
- `llama.cpp` as the local inference runtime, running `gemma-4-e2b-it-qat-q4_0`
- ALSA for first audio bring-up
- whisper.cpp `small.en` (int8) for STT, Vosk as fallback
- Piper for TTS

## Recommended baseline

- Raspberry Pi 4 with 8 GB RAM (Pi 5 with 8-16 GB is the upgrade path)
- Raspberry Pi OS Lite 64-bit
- SSH enabled
- reliable power supply
- **active cooling** — the Pi 4 throttles under sustained LLM load; a fan keeps clock speeds (and tok/s) stable. This is a measurable speed factor, not just longevity.
- NVMe HAT strongly recommended: model load and memory-mapping are dominated by storage I/O, and microSD is the biggest bottleneck after the CPU

## Honest speed expectations

| Hardware | Model | Generation speed |
|---|---|---|
| Pi 4 (8 GB) | Gemma 4 E2B Q4 | ~2-4 tok/s |
| Pi 5 (8 GB) | Gemma 4 E2B Q4 | ~2-5 tok/s |

A short reply lands in roughly 15-20 seconds end to end on a Pi 4. PATCH is designed around that: sentence-streamed TTS starts speaking after the first sentence, and the `thinking` display state makes the wait feel intentional.

## 1. Flash and boot

Use Raspberry Pi Imager and choose:

- `Raspberry Pi OS Lite (64-bit)`

Before writing the SD card, set:

- hostname: `patch-pi`
- username and password
- Wi-Fi if needed
- SSH enabled

If `patch-pi.local` does not resolve on your PC later, use the Pi IP address instead.

## 2. Base packages

```bash
sudo apt update
sudo apt full-upgrade -y
sudo apt install -y python3 python3-venv python3-pip git sqlite3 curl alsa-utils ffmpeg unzip cmake build-essential
```

Optional but recommended: zram swap, so a RAM spike compresses instead of thrashing the SD card:

```bash
sudo apt install -y zram-tools
```

## 3. Clone PATCH

```bash
git clone <your-repo-url> ~/patch
cd ~/patch
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp config/settings.example.json config/settings.json
```

## 4. Build and run `llama.cpp`

PATCH assumes you start `llama-server` yourself and keep it warm — never a fresh process per turn.

```bash
git clone https://github.com/ggml-org/llama.cpp ~/llama.cpp
cd ~/llama.cpp
cmake -B build -DGGML_NATIVE=ON
cmake --build build --config Release -j4
```

`-DGGML_NATIVE=ON` enables the ARM NEON/dotprod paths for the Pi's CPU.

Download the official QAT GGUF (`gemma-4-e2b-it-qat-q4_0-gguf` on Hugging Face — always the `-qat-` checkpoint, never a community PTQ quant of the base model; same RAM, meaningfully smarter). Unsloth's dynamic `UD-Q4_K_XL` GGUFs are worth comparing too.

Start the server with Pi-tuned flags:

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/gemma-4-e2b-it-qat-q4_0.gguf \
  --host 127.0.0.1 --port 8080 \
  -t 4 -tb 4 --prio 3 \
  -fa auto \
  --ctx-size 2048
```

- `-t 4 -tb 4`: use all 4 cores for generation and batch processing
- `--prio 3`: give inference scheduling priority
- `-fa auto`: enable Flash Attention
- `--ctx-size 2048`: smaller KV cache, less memory traffic per token (4096 on a Pi 5)

Keep the model ID aligned with the PATCH profile names in `config/settings.json`.

### Speculative decoding (test after the basic pipeline works)

Gemma 4 ships a matching draft model (`gemma-4-e2b-it-qat-q4_0-unquantized-assistant`). A tiny drafter proposes several tokens and the main model verifies them in one pass — lossless quality, meaningfully faster. This is the single biggest free speedup available:

```bash
~/llama.cpp/build/bin/llama-server \
  -m ~/models/gemma-4-e2b-it-qat-q4_0.gguf \
  -md ~/models/gemma-4-e2b-assistant.gguf \
  ... (same flags as above)
```

Compare `/perf` numbers with and without it.

### Run as a systemd service (after manual validation)

Running `llama-server` as a persistent systemd unit keeps the model loaded across PATCH restarts — no cold start per session.

## 5. First PATCH startup

```bash
cd ~/patch
source .venv/bin/activate
python3 -m patch.cli
```

First checks inside PATCH:

```text
/help
/models
/mode
/system
```

## 6. Audio bring-up

List devices:

```bash
arecord -l
aplay -l
```

Typical USB mic test:

```bash
arecord -D plughw:3,0 -vv -f cd -d 10 /dev/null
arecord -D plughw:3,0 -d 5 -f cd test-mic.wav
aplay -D plughw:0,0 test-mic.wav
```

If levels are too low, use:

```bash
alsamixer -c 3
```

For a simple mono speech output path, a clear single-speaker result is good enough for PATCH.

## 7. Install Pi voice dependencies

### whisper.cpp (default STT)

```bash
git clone https://github.com/ggml-org/whisper.cpp ~/whisper.cpp
cd ~/whisper.cpp
cmake -B build
cmake --build build --config Release -j4
# English-only small model, int8-quantized: smaller and faster than multilingual
./models/download-ggml-model.sh small.en-q8_0
```

Point the PATCH config at the binary and model:

```json
"stt_engine": "whisper_cpp",
"whisper_cpp_binary": "/home/<you>/whisper.cpp/build/bin/whisper-cli",
"whisper_model_path": "/home/<you>/whisper.cpp/models/ggml-small.en-q8_0.bin"
```

### Piper (TTS)

Inside the PATCH venv:

```bash
python3 -m pip install piper-tts
```

Download the `en_US-lessac-medium` voice into the configured `piper_voice_dir`. Piper stays under 100 MB RAM and synthesizes in well under 100 ms — keep it over Kokoro unless you specifically want the quality bump.

### Vosk (optional fallback)

```bash
python3 -m pip install vosk
```

Set `"stt_engine": "vosk"` if you want to compare.

### LanceDB episodic memory (optional upgrade)

```bash
python3 -m pip install lancedb sentence-transformers
```

Then set `"episodic_backend": "lancedb"`. Vectors live on disk (`data/lancedb/`), so memory growth never competes with the LLM for RAM.

## 8. First voice-loop test

```bash
python3 -m patch.voice_loop_test
```

This gives you:

- mic capture
- STT
- PATCH reply generation with sentence streaming
- Piper synthesis per sentence, played while the LLM keeps generating
- stage-level performance logs (including `tts.first_audio`)

## 9. Performance and temperature checks

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

If your fan is helping, repeated `/system` snapshots should show lower temperature and fewer throttling events during reply generation.

## Practical advice

- keep one model loaded and warm via `llama-server`
- use `fast` mode on the Pi first
- keep context small; let `max_tokens` and a "be concise" system prompt cap replies
- keep thinking on `auto` — the reasoning channel burns tokens you'll never speak
- keep camera disabled until the audio loop feels good
- treat the screen as an event-driven state consumer, not part of the reply bottleneck
